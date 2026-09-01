"""Replay the candidate pool against sessions whose real gappers are known.

This is the instrument that decides the tier ordering, so it is version
controlled, tested, and split into two stages that never run together.

  fetch     reconstructs one historical session's INPUTS, the earnings
            calendar, the overnight news sweep, the prior session end of day
            and the universe membership, together with its OUTCOME, the open
            against the prior close for every universe name. Both are written
            to a cache keyed by session date. This stage is the only one that
            touches the network.

  evaluate  reads the cache and nothing else, applies a named ordering
            configuration, and reports pool recall, subscribed recall, per
            tier hit rates and the names that were missed. Zero network calls,
            asserted in test_backtest.py.

The split is the point. Fetching is slow, expensive and dated: sixty sessions
cost about six thousand counted calls against a shared key and can only be
afforded once. Evaluating is free and will be run many times, once per ordering
candidate, and must be reproducible from the same bytes every time. A harness
that refetched while it evaluated would make every comparison a measurement of
two different things.

Bulk end of day is cached per DAY rather than per session, because consecutive
sessions share it: session N's outcome read is session N+1's prior read. A
session needs three days, its own, its prior and the one before that, so sixty
consecutive sessions cost sixty two bulk days rather than a hundred and eighty.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from typing import Any

from core import config
from core import criteria
from selection import discover
from core import eodhd
from core import ettime
from selection import universe

_CRIT = criteria.load()

CACHE_DIR = config.DATA_DIR / "backtest"
EOD_DIR = CACHE_DIR / "eod"
SESSION_DIR = CACHE_DIR / "sessions"


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def ensure_dirs() -> None:
    EOD_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------- fetch stage

def eod_day(api: eodhd.EodhdClient, day: dt.date, wanted: set[str]) -> dict[str, Any] | None:
    """One session of end of day bars, trimmed to the universe and cached.

    Trimmed because the raw call returns about 45,000 rows and the universe is
    2,745 of them; keeping the rest would make the cache ten times its size for
    names no screen can ever select.
    """
    path = EOD_DIR / f"{day.isoformat()}.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass

    rows, error = api.eod_bulk_last_day("US", day=day)
    if error:
        print(f"backtest: bulk end of day for {day} failed: {error}")
        return None

    out: dict[str, Any] = {}
    for row in rows or []:
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        symbol = code if "." in code else f"{code}.US"
        if symbol not in wanted:
            continue
        out[symbol] = {
            "o": _as_float(row.get("open")),
            "h": _as_float(row.get("high")),
            "l": _as_float(row.get("low")),
            "c": _as_float(row.get("close")),
            "v": _as_float(row.get("volume")),
        }
    path.write_text(json.dumps(out), encoding="utf-8")
    return out


def fetch_session(
    api: eodhd.EodhdClient,
    session: dt.date,
    prior: dt.date,
    earlier: dt.date,
    universe_symbols: set[str],
    dollar_volume_20d: dict[str, float],
    force: bool = False,
) -> dict[str, Any] | None:
    """Cache one session's inputs and its outcome. Returns the session record."""
    directory = SESSION_DIR / session.isoformat()
    inputs_path = directory / "inputs.json"
    outcome_path = directory / "outcome.json"
    if not force and inputs_path.is_file() and outcome_path.is_file():
        return {
            "inputs": json.loads(inputs_path.read_text(encoding="utf-8")),
            "outcome": json.loads(outcome_path.read_text(encoding="utf-8")),
            "cached": True,
        }
    directory.mkdir(parents=True, exist_ok=True)

    prior_bars = eod_day(api, prior, universe_symbols)
    earlier_bars = eod_day(api, earlier, universe_symbols)
    session_bars = eod_day(api, session, universe_symbols)
    if prior_bars is None or earlier_bars is None or session_bars is None:
        print(f"backtest: {session} skipped, an end of day read failed")
        return None

    run_clock = ettime.at(session, *_CRIT.clock("discovery", "run_time"))
    # The same function production calls, so a replayed session sees the
    # window the live run would have seen. Passing through discover rather
    # than recomputing from `prior` here is the whole point: the two drifting
    # apart is what made every Monday in this cache unrepresentative.
    news_since = discover.news_window_start(session)

    earnings = discover.earnings_before_open(api, universe_symbols, session)
    news = discover.overnight_news(api, universe_symbols, news_since, run_clock)

    # The movers source, recomputed here from the cached bars rather than by
    # calling discover's version, which would refetch the same two days.
    move_floor = _CRIT.number("discovery", "prior_session_move_pct")
    dollar_multiple = _CRIT.number("discovery", "prior_session_dollar_multiple")
    movers: dict[str, Any] = {}
    prior_closes: dict[str, float] = {}
    for symbol, bar in prior_bars.items():
        close = bar.get("c")
        if close is None:
            continue
        prior_closes[symbol] = close
        earlier_close = (earlier_bars.get(symbol) or {}).get("c")
        if not earlier_close:
            continue
        move = (close - earlier_close) / earlier_close * 100.0
        dollar_volume = close * (bar.get("v") or 0.0)
        average = dollar_volume_20d.get(symbol) or 0.0
        heavy = bool(average) and dollar_volume >= average * dollar_multiple
        if abs(move) < move_floor and not heavy:
            continue
        movers[symbol] = {
            "prior_session": prior.isoformat(),
            "move_pct": round(move, 4),
            "dollar_volume": round(dollar_volume, 2),
        }

    inputs = {
        "session_date": session.isoformat(),
        "prior_session": prior.isoformat(),
        "earlier_session": earlier.isoformat(),
        "run_clock": ettime.stamp(run_clock),
        "earnings": {"status": earnings["status"], "names": earnings["names"]},
        "news": {"status": news["status"], "names": news["names"],
                 "truncated": news.get("truncated"), "pages": news.get("pages")},
        "movers": {"status": discover.FETCHED if movers else discover.FETCHED_EMPTY,
                   "names": movers},
        "prior_closes": prior_closes,
        # Recent runners are deliberately absent. They come from the picks
        # table, which holds one live session, so any value replayed here would
        # be an artefact of this project's own history rather than the market's.
        "runners_note": (
            "not reconstructed: the picks table holds too little live history "
            "to replay this source honestly"
        ),
        "universe_size": len(universe_symbols),
    }

    gap_rule = _CRIT.rule("discovery", "gap_pct")
    gappers: dict[str, Any] = {}
    for symbol, bar in session_bars.items():
        open_price = bar.get("o")
        prior_close = prior_closes.get(symbol)
        if open_price is None or not prior_close:
            continue
        gap = (open_price - prior_close) / prior_close * 100.0
        if not gap_rule.test(abs(gap)):
            continue
        gappers[symbol] = {
            "symbol": symbol,
            "gap_at_open_pct": round(gap, 4),
            "open": open_price,
            "prior_close": prior_close,
            "volume": bar.get("v"),
        }
    outcome = {
        "session_date": session.isoformat(),
        "gap_floor": gap_rule.describe(),
        "measured_against": "the session open versus the prior session close",
        "gappers": gappers,
    }

    inputs_path.write_text(json.dumps(inputs), encoding="utf-8")
    outcome_path.write_text(json.dumps(outcome), encoding="utf-8")
    return {"inputs": inputs, "outcome": outcome, "cached": False}


def fetch_range(count: int, end: dt.date, force: bool = False) -> dict[str, Any]:
    """Cache `count` consecutive trading sessions ending at `end`.

    Stops cleanly when the shared quota will not carry the rest, reporting how
    many sessions were cached before it stopped. A partial cache is usable: the
    evaluate stage takes whatever sessions it finds.
    """
    ensure_dirs()
    api = eodhd.client()

    quota = eodhd.preflight("backtest")
    if quota["refused"]:
        raise eodhd.QuotaRefusal(
            f"quota exhausted on the shared key: {eodhd.describe_preflight(quota)}"
        )
    spend_floor = quota["degrade_below"]
    started_with = quota.get("api_requests")
    print(f"backtest: preflight {eodhd.describe_preflight(quota)}")

    universe_payload = universe.load_universe(require_fresh=False)
    universe_symbols = set(universe.universe_symbols(universe_payload))
    dollar_volume_20d = {
        str(row.get("symbol", "")).upper(): _as_float(row.get("avg_dollar_volume_20d")) or 0.0
        for row in universe_payload.get("symbols", [])
        if row.get("symbol")
    }

    # Two extra sessions so the earliest one still has a prior and an earlier.
    sessions = session_calendar(api, count + 2, end)
    if len(sessions) < 3:
        raise RuntimeError("the session calendar returned too few sessions")
    targets = sessions[2:]
    print(f"backtest: caching {len(targets)} sessions from {targets[0]} to {targets[-1]}")

    cached = 0
    stopped_early: str | None = None
    for index, session in enumerate(targets):
        position = sessions.index(session)
        prior = sessions[position - 1]
        earlier = sessions[position - 2]

        if index % 10 == 0 and index:
            reading = eodhd.preflight("backtest")
            if reading.get("remaining") is not None and reading["remaining"] < spend_floor:
                stopped_early = (
                    f"stopped after {cached} sessions: the shared key is down to "
                    f"{reading['remaining']:,} remaining, at or below the "
                    f"{spend_floor:,} degrade threshold in CRITERIA.md [quota]"
                )
                print(f"backtest: {stopped_early}")
                break

        record = fetch_session(api, session, prior, earlier, universe_symbols,
                               dollar_volume_20d, force=force)
        if record is None:
            continue
        cached += 1
        mark = "cached" if record["cached"] else "fetched"
        print(f"backtest: {session} {mark:>7}  "
              f"{len(record['inputs']['earnings']['names']):>3} earnings, "
              f"{len(record['inputs']['news']['names']):>4} news, "
              f"{len(record['inputs']['movers']['names']):>4} movers, "
              f"{len(record['outcome']['gappers']):>3} gapped")

    after = eodhd.preflight("backtest")
    spent = None
    if started_with is not None and after.get("api_requests") is not None:
        spent = after["api_requests"] - started_with
    print(f"backtest: {cached} sessions cached. Counted calls spent {spent}, "
          f"meter {started_with} to {after.get('api_requests')}")
    return {"cached": cached, "spent": spent, "stopped_early": stopped_early,
            "meter_before": started_with, "meter_after": after.get("api_requests")}


def session_calendar(api: eodhd.EodhdClient, count: int, end: dt.date) -> list[dt.date]:
    """Real session dates ending at `end`, from a liquid symbol's own history."""
    probe = _CRIT.text("universe", "session_calendar_symbol")
    start = end - dt.timedelta(days=count * 2 + 30)
    rows, error = api.eod(probe, start=start, end=end)
    if error or not rows:
        raise RuntimeError(f"could not read the session calendar from {probe}: "
                           f"{error or 'no rows'}")
    dates = sorted({ettime.parse_date(str(r.get("date"))) for r in rows if r.get("date")})
    dates = [d for d in dates if d <= end]
    return dates[-count:]


# ------------------------------------------------------------ evaluate stage

def cached_sessions() -> list[str]:
    if not SESSION_DIR.is_dir():
        return []
    out = []
    for directory in sorted(SESSION_DIR.iterdir()):
        if (directory / "inputs.json").is_file() and (directory / "outcome.json").is_file():
            out.append(directory.name)
    return out


def load_session(session_date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = SESSION_DIR / session_date
    return (
        json.loads((directory / "inputs.json").read_text(encoding="utf-8")),
        json.loads((directory / "outcome.json").read_text(encoding="utf-8")),
    )


def build_pool(inputs: dict[str, Any], metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The pool for one cached session, tiered by the shipped assemble().

    discover.assemble is called rather than reimplemented, so the tiers under
    test are the tiers production assigns. Only the ORDER is varied afterwards,
    by re-sorting on a different key, which is exactly equivalent to having
    assembled with that key since the tier is decided per name and not per
    ranking.
    """
    sources = {
        "earnings": {"status": inputs["earnings"]["status"], "names": inputs["earnings"]["names"]},
        "news": {"status": inputs["news"]["status"], "names": inputs["news"]["names"]},
        "movers": {"status": inputs["movers"]["status"], "names": inputs["movers"]["names"],
                   "closes": {}},
        "runners": {"status": discover.FETCHED_EMPTY, "names": {}},
    }
    now = dt.datetime.fromisoformat(inputs["run_clock"])
    return discover.assemble(sources, metrics, now)


ORDERINGS: dict[str, dict[str, Any]] = {
    "SHIPPED": {
        # Not a copy of the shipped rule, the shipped rule itself: this config
        # sorts with discover.rank_value, which reads CRITERIA. If someone
        # changes the key in CRITERIA, this row moves and the others do not.
        "label": "shipped, CRITERIA within_tier_key through discover.rank_value",
        "use_shipped_rank": True,
    },
    "A": {
        "label": "20 day average dollar volume descending",
        "key": "avg_dollar_volume_20d",
    },
    "B": {"label": "gap propensity descending", "key": "gap_propensity"},
    "COLLAPSED": {
        # Tiers 2, 3 and 4 all convert at 0.35 to 0.40 under a floor, so the
        # boundaries between them may be structure the ranking key then has to
        # fight. This config keeps tier 1 and merges the rest into one tier.
        "label": "tier 1 kept, tiers 2 to 4 collapsed into one",
        "use_shipped_rank": True,
        "collapse_tiers": {3: 2, 4: 2},
    },
    "C": {"label": "median absolute gap descending", "key": "median_abs_gap_pct"},
    "D": {"label": "20 day ATR as a percent of price descending", "key": "atr_pct_20d"},
    "E": {
        # The filter has to bite to mean anything. universe.json already floors
        # avg_dollar_volume_20d at 5M, so a 5M filter here removes nothing and
        # E collapses onto B exactly, which is what a first run of this sweep
        # showed. 25M is the smallest round figure above the universe floor
        # that actually excludes names.
        "label": "gap propensity descending, 25M dollar volume as a filter",
        "key": "gap_propensity",
        "min_dollar_volume": 25_000_000.0,
    },
}


def order_pool(
    pool: list[dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    ordering: dict[str, Any],
) -> list[dict[str, Any]]:
    """Re-rank a tiered pool by the configuration's key. Tier order is kept.

    A name with a null metric sorts last within its tier rather than as zero.
    Null means never measured and measured zero means a name that has not
    gapped in 250 sessions, and collapsing the two would quietly promote every
    name with too little history above every name with a real, low reading.
    """
    floor = ordering.get("min_dollar_volume")

    rows = list(pool)
    if floor:
        rows = [
            row for row in rows
            if (metrics.get(row["symbol"], {}).get("avg_dollar_volume_20d") or 0.0) >= floor
        ]

    if ordering.get("use_shipped_rank"):
        def sort_key(row: dict[str, Any]) -> tuple:
            return (row["pool_tier"], *discover.rank_value(row["symbol"], metrics),
                    row["symbol"])
    else:
        key = ordering["key"]

        def sort_key(row: dict[str, Any]) -> tuple:
            value = metrics.get(row["symbol"], {}).get(key)
            return (row["pool_tier"], 0 if value is not None else 1,
                    -(value or 0.0), row["symbol"])

    collapse = ordering.get("collapse_tiers") or {}
    if collapse:
        rows = [dict(row) for row in rows]
        for row in rows:
            row["pool_tier"] = collapse.get(row["pool_tier"], row["pool_tier"])

    rows.sort(key=sort_key)
    for index, row in enumerate(rows):
        row = dict(row)
        rows[index] = row
        row["pool_rank"] = index + 1
    return rows


def apply_cap(
    rows: list[dict[str, Any]], cap: int, tier_floor: int = 0
) -> list[dict[str, Any]]:
    """Mark the subscribed rows, guaranteeing each tier a minimum.

    Delegates to discover.apply_slots so the harness measures the slot
    allocation production actually runs. A sweep that scored a private copy of
    the shipped logic would be measuring the copy.
    """
    return discover.apply_slots(rows, cap, tier_floor)


def _eod_cache(day: str) -> dict[str, Any]:
    path = EOD_DIR / f"{day}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


# Which CRITERIA day_setup conditions this cache can and cannot test. Named
# here rather than left implicit, because a "screen pass" count that quietly
# skipped a condition would read as stronger evidence than it is.
SCREEN_APPLIED = ("gap_pct", "price", "market_cap", "require_above_prior_high")
SCREEN_SKIPPED = {
    "premarket_rvol": (
        "needs premarket volume, which THIS module has no source for: it reads "
        "the end of day cache, and a daily bar carries no premarket at all. So "
        "the condition is not applied here and this count stays an upper bound "
        "on the real screen. [corrected 2026-09-01: this used to say 'there is "
        "no premarket tape for a historical session', which was true of every "
        "source this project had when it was written and is not true now. "
        "Alpaca's free plan serves SIP minute bars for a session that is over, "
        "premarket included, and research/replay_session.py applies all five "
        "day_setup conditions off that tape. The limitation is this cache's, "
        "not the world's, and a reader deciding whether the question is "
        "answerable needed to be told which.]"
    ),
}


def screen_passed(
    subscribed_rows: list[dict[str, Any]],
    inputs: dict[str, Any],
    outcome: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
) -> int:
    """Subscribed names that would have cleared the replayable day screen.

    Recall counts names that gapped. This counts names the morning could have
    actually published, which is what the product is made of: a name that
    gapped three percent on no volume against a prior high it never cleared is
    not a candidate, it is a row in a feed.

    Only the conditions in SCREEN_APPLIED are tested. premarket_rvol cannot be
    replayed for a historical session at all, so this is an upper bound on the
    real screen rather than the screen itself.
    """
    session_bars = _eod_cache(inputs["session_date"])
    prior_bars = _eod_cache(inputs["prior_session"])
    if not session_bars or not prior_bars:
        return 0

    price_rule = _CRIT.rule("day_setup", "price")
    gap_rule = _CRIT.rule("day_setup", "gap_pct")
    cap_rule = _CRIT.rule("day_setup", "market_cap")
    require_high = _CRIT.flag("day_setup", "require_above_prior_high")
    prior_closes = inputs.get("prior_closes") or {}

    passed = 0
    for row in subscribed_rows:
        symbol = row["symbol"]
        bar = session_bars.get(symbol) or {}
        open_price = bar.get("o")
        prior_close = prior_closes.get(symbol)
        prior_high = (prior_bars.get(symbol) or {}).get("h")
        if open_price is None or not prior_close:
            continue
        gap = (open_price - prior_close) / prior_close * 100.0
        if not gap_rule.test(abs(gap)) or not price_rule.test(open_price):
            continue
        if not cap_rule.test((metrics.get(symbol) or {}).get("market_cap")):
            continue
        if require_high and (prior_high is None or open_price <= prior_high):
            continue
        passed += 1
    return passed


def evaluate_session(
    session_date: str,
    metrics: dict[str, dict[str, Any]],
    ordering: dict[str, Any],
    cap: int,
    tier_floor: int = 0,
) -> dict[str, Any]:
    from night import pool_recall

    inputs, outcome = load_session(session_date)
    pool = build_pool(inputs, metrics)
    ranked = order_pool(pool, metrics, ordering)
    capped = apply_cap(ranked, cap, tier_floor=tier_floor)
    gappers = outcome["gappers"]
    result = pool_recall.measure(gappers, capped)

    per_tier: dict[int, dict[str, int]] = {}
    for row in capped:
        if not row["subscribed"]:
            continue
        bucket = per_tier.setdefault(row["pool_tier"], {"subscribed": 0, "gapped": 0})
        bucket["subscribed"] += 1
        if row["symbol"] in gappers:
            bucket["gapped"] += 1

    # How many subscribed names the primary key could not score, which is the
    # population the fallback exists for. Reported per session because it is
    # the number that says whether the fallback is doing anything at all.
    primary = _CRIT.text("discovery", "within_tier_key")
    subscribed_rows = [row for row in capped if row["subscribed"]]
    without_primary = [
        row["symbol"] for row in subscribed_rows
        if (metrics.get(row["symbol"]) or {}).get(primary) is None
    ]

    return {
        "session_date": session_date,
        "gapped": result["gapped"],
        "pool_held": result["pool_held"],
        "discovery_recall_all_gappers": result["discovery_recall_all_gappers"],
        "subscribed_held": result["subscribed_held"],
        "subscribed_recall_all_gappers": result["subscribed_recall_all_gappers"],
        "screen_passed": screen_passed(subscribed_rows, inputs, outcome, metrics),
        "subscribed_without_primary": len(without_primary),
        "without_primary_that_gapped": sum(
            1 for symbol in without_primary if symbol in gappers
        ),
        "pool_size": len(ranked),
        "earnings_names": len(inputs["earnings"]["names"]),
        "per_tier": per_tier,
        "missed": [row["symbol"] for row in result["missed"]],
    }


def load_metrics(as_of: str | None = None) -> dict[str, dict[str, Any]]:
    """Per name ranking inputs: dollar volume from the universe, the rest from gap_stats.

    as_of picks which gap_stats window to read. For a sweep it must name a date
    BEFORE the earliest session being replayed, or the propensity was computed
    partly from the sessions it is being scored on and every key derived from it
    gets a look ahead advantage over dollar volume, which has none.
    """
    from selection import gap_stats

    universe_payload = universe.load_universe(require_fresh=False)
    metrics: dict[str, dict[str, Any]] = {}
    for row in universe_payload.get("symbols", []):
        symbol = str(row.get("symbol", "")).upper()
        if not symbol:
            continue
        metrics[symbol] = {
            "avg_dollar_volume_20d": _as_float(row.get("avg_dollar_volume_20d")) or 0.0,
            "market_cap": _as_float(row.get("market_cap")),
            "gap_propensity": None,
            "median_abs_gap_pct": None,
            "atr_pct_20d": None,
        }
    for symbol, stats in gap_stats.load_all(as_of).items():
        if symbol in metrics:
            metrics[symbol].update({
                "gap_propensity": stats.get("gap_propensity"),
                "median_abs_gap_pct": stats.get("median_abs_gap_pct"),
                "atr_pct_20d": stats.get("atr_pct_20d"),
            })
    return metrics


def sweep(
    orderings: list[str], floors: list[int], sessions: list[str] | None = None,
    as_of: str | None = None, caps: list[int] | None = None,
) -> dict[str, Any]:
    caps = caps or [_CRIT.integer("discovery", "max_subscribed_candidates")]
    cap = caps[0]
    metrics = load_metrics(as_of)
    sessions = sessions or cached_sessions()
    if not sessions:
        raise RuntimeError(f"no cached sessions under {SESSION_DIR}")

    results: dict[str, Any] = {}
    for name in orderings:
        ordering = ORDERINGS[name]
        for floor in floors:
            for this_cap in caps:
                rows = [
                    evaluate_session(session, metrics, ordering, this_cap,
                                     tier_floor=floor)
                    for session in sessions
                ]
                label = f"{name}/floor{floor}"
                if len(caps) > 1:
                    label += f"/cap{this_cap}"
                results[label] = {
                    "ordering": name,
                    "label": ordering["label"],
                    "tier_floor": floor,
                    "cap": this_cap,
                    "sessions": rows,
                }
    return {"cap": cap, "sessions": sessions, "metrics_as_of": as_of,
            "results": results}


def summarise(rows: list[dict[str, Any]], heavy_threshold: int) -> dict[str, Any]:
    recalls = [r["subscribed_recall_all_gappers"] for r in rows if r["subscribed_recall_all_gappers"] is not None]
    heavy = [r for r in rows if r["earnings_names"] >= heavy_threshold]
    light = [r for r in rows if r["earnings_names"] < heavy_threshold]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def recall_of(subset: list[dict[str, Any]]) -> float | None:
        got = [r["subscribed_recall_all_gappers"] for r in subset if r["subscribed_recall_all_gappers"] is not None]
        return mean(got)

    # Per tier hit rate: of the slots this tier was given across every session,
    # how many went to a name that actually gapped. This is the number that
    # says whether a tier is worth its slots, which the recall total cannot,
    # because a tier that never gets a slot never shows up in a recall figure.
    per_tier: dict[int, dict[str, int]] = {}
    for row in rows:
        for tier, bucket in (row.get("per_tier") or {}).items():
            target = per_tier.setdefault(int(tier), {"subscribed": 0, "gapped": 0})
            target["subscribed"] += bucket["subscribed"]
            target["gapped"] += bucket["gapped"]
    for bucket in per_tier.values():
        bucket["hit_rate"] = (
            round(bucket["gapped"] / bucket["subscribed"], 4) if bucket["subscribed"] else None
        )

    screens = [r.get("screen_passed") for r in rows if r.get("screen_passed") is not None]
    return {
        "sessions": len(rows),
        "per_tier": dict(sorted(per_tier.items())),
        "mean_screen_passed": round(sum(screens) / len(screens), 4) if screens else None,
        # The socket decision reads off this number, and it is a mean over a
        # population whose gapper counts run 42 to 518 a session. A report is
        # thin or full on a given morning, never on average, so the whole
        # distribution is reported and the median is the figure to plan on.
        "screen_passed_distribution": _distribution(screens),
        "total_screen_passed": sum(screens),
        "mean_without_primary": round(
            sum(r.get("subscribed_without_primary", 0) for r in rows) / len(rows), 3
        ) if rows else None,
        "without_primary_that_gapped": sum(
            r.get("without_primary_that_gapped", 0) for r in rows
        ),
        "mean_subscribed_recall": mean(recalls),
        "median_subscribed_recall": round(statistics.median(recalls), 4) if recalls else None,
        "min_subscribed_recall": round(min(recalls), 4) if recalls else None,
        "max_subscribed_recall": round(max(recalls), 4) if recalls else None,
        "stdev_subscribed_recall": (
            round(statistics.pstdev(recalls), 4) if len(recalls) > 1 else None
        ),
        "mean_pool_recall": mean([r["discovery_recall_all_gappers"] for r in rows if r["discovery_recall_all_gappers"] is not None]),
        "heavy_sessions": len(heavy),
        "heavy_mean_recall": recall_of(heavy),
        "light_sessions": len(light),
        "light_mean_recall": recall_of(light),
        "total_gapped": sum(r["gapped"] for r in rows),
        "total_subscribed_held": sum(r["subscribed_held"] for r in rows),
    }


HISTORY_BUCKETS = ((0, 10), (10, 25), (25, 50), (50, 100))


def blindspot(as_of: str | None = None) -> dict[str, Any]:
    """How many of the day's real gappers propensity structurally cannot score.

    The fallback tying told us about the SUBSCRIBED set: only 0.2 names a
    session reach the cap without a propensity. That is a different question
    from this one. If a large share of the names that actually gap carry under
    100 sessions of history, propensity ranking has a blind spot the fallback
    cannot reach, because those names never get near the cap to be reordered.

    Broken out by how much history each had, because a name 10 sessions short
    of a propensity and one 95 short are not the same problem: the first fixes
    itself in a fortnight.
    """
    from selection import gap_stats

    stats = gap_stats.load_all(as_of)
    sessions = cached_sessions()
    rows: list[dict[str, Any]] = []
    buckets = {f"{low}-{high - 1}": 0 for low, high in HISTORY_BUCKETS}
    buckets["not in gap_stats"] = 0
    total_gapped = 0
    total_null = 0

    for session_date in sessions:
        _inputs, outcome = load_session(session_date)
        gappers = outcome["gappers"]
        null_names = []
        for symbol in gappers:
            row = stats.get(symbol)
            if row is None:
                null_names.append(symbol)
                buckets["not in gap_stats"] += 1
                continue
            if row.get("gap_propensity") is not None:
                continue
            null_names.append(symbol)
            used = int(row.get("sessions_used") or 0)
            for low, high in HISTORY_BUCKETS:
                if low <= used < high:
                    buckets[f"{low}-{high - 1}"] += 1
                    break
        total_gapped += len(gappers)
        total_null += len(null_names)
        rows.append({
            "session_date": session_date,
            "gapped": len(gappers),
            "null_propensity": len(null_names),
            "fraction": round(len(null_names) / len(gappers), 4) if gappers else None,
            "names": sorted(null_names),
        })

    return {
        "as_of": as_of or "newest",
        "sessions": rows,
        "total_gapped": total_gapped,
        "total_null": total_null,
        "overall_fraction": round(total_null / total_gapped, 4) if total_gapped else None,
        "history_buckets": buckets,
        # The count per session, not just its mean. The distribution is
        # strongly right skewed (42 to 518 over the sixty cached sessions),
        # so the mean sits well above the typical session and reading it as
        # "a normal morning" makes any single session look anomalous when it
        # is not. Reported as a distribution for that reason.
        "gappers_per_session": _distribution([row["gapped"] for row in rows]),
    }


def _distribution(values: list[int]) -> dict[str, Any]:
    """Mean, median and the tails. A mean alone hides a skew this wide."""
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "sessions": len(ordered),
        "mean": round(statistics.mean(ordered), 1),
        "median": round(statistics.median(ordered), 1),
        "min": ordered[0],
        "p25": ordered[len(ordered) // 4],
        "p75": ordered[3 * len(ordered) // 4],
        "max": ordered[-1],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest the candidate pool.")
    sub = parser.add_subparsers(dest="stage", required=True)

    blind = sub.add_parser("blindspot", help="Gappers propensity cannot score. Cache only.")
    blind.add_argument("--as-of", help="gap_stats window. Defaults to the newest.")
    blind.add_argument("--sessions", type=int, default=12,
                       help="How many per session rows to print. 0 for all.")

    fetch = sub.add_parser("fetch", help="Cache historical sessions. Touches the network.")
    fetch.add_argument("--sessions", type=int, default=60)
    fetch.add_argument("--end", default="2026-08-13")
    fetch.add_argument("--force", action="store_true")

    evaluate = sub.add_parser("evaluate", help="Read the cache only. No network.")
    evaluate.add_argument("--ordering", action="append", default=[],
                          help="One of A B C D E, repeatable. Defaults to all.")
    evaluate.add_argument("--floor", action="append", type=int, default=[],
                          help="Tier floor, repeatable. Defaults to 0.")
    evaluate.add_argument("--heavy-threshold", type=int, default=20,
                          help="Earnings names at or above which a session counts as heavy.")
    evaluate.add_argument("--cap", action="append", type=int, default=[],
                          help="Subscription cap, repeatable. Defaults to CRITERIA.")
    evaluate.add_argument("--as-of", help="gap_stats window to rank with. Use a date "
                          "before the earliest session to stay out of sample.")
    evaluate.add_argument("--json", metavar="PATH", help="Write the full results here.")
    args = parser.parse_args(argv)

    if args.stage == "blindspot":
        report = blindspot(args.as_of)
        print(f"backtest: {len(report['sessions'])} sessions, gap_stats as of "
              f"{report['as_of']}")
        print(f"{'session':<12} {'gapped':>7} {'null':>6} {'fraction':>9}")
        shown = report["sessions"] if args.sessions == 0 else report["sessions"][:args.sessions]
        for row in shown:
            print(f"{row['session_date']:<12} {row['gapped']:>7} "
                  f"{row['null_propensity']:>6} {row['fraction']:>9}")
        if args.sessions and len(report["sessions"]) > args.sessions:
            print(f"... {len(report['sessions']) - args.sessions} more sessions")
        print()
        dist = report["gappers_per_session"]
        print(f"gappers per session: mean {dist['mean']}, median {dist['median']}, "
              f"min {dist['min']}, p25 {dist['p25']}, p75 {dist['p75']}, "
              f"max {dist['max']}")
        print("  the mean sits well above the median because the distribution is "
              "right skewed; a session near the median is a normal session, not "
              "a light one")
        print(f"total gapped {report['total_gapped']}, of which "
              f"{report['total_null']} carried a null propensity, "
              f"fraction {report['overall_fraction']}")
        print("history of the null ones, in sessions:")
        for bucket, count in report["history_buckets"].items():
            print(f"    {bucket:>16}: {count}")
        return 0

    if args.stage == "fetch":
        try:
            fetch_range(args.sessions, ettime.parse_date(args.end), force=args.force)
        except (eodhd.QuotaRefusal, RuntimeError) as exc:
            print(f"backtest: {exc}")
            eodhd.print_call_report()
            return 1
        eodhd.print_call_report()
        return 0

    orderings = args.ordering or list(ORDERINGS)
    floors = args.floor or [0]
    outcome = sweep(orderings, floors, as_of=args.as_of, caps=args.cap or None)
    sessions = outcome["sessions"]
    print(f"backtest: {len(sessions)} cached sessions, {sessions[0]} to {sessions[-1]}, "
          f"cap {outcome['cap']}, ranking metrics as of {outcome['metrics_as_of'] or 'newest'}")
    print()
    header = (f"{'config':<12} {'ordering':<52} {'floor':>5} {'mean':>7} {'median':>7} "
              f"{'min':>6} {'max':>6} {'sd':>6} {'heavy':>7} {'light':>7} {'pool':>7} {'screen':>7} {'noKey':>6}")
    print(header)
    print("-" * len(header))
    for key, block in outcome["results"].items():
        stats = summarise(block["sessions"], args.heavy_threshold)
        block["summary"] = stats
        print(f"{key:<12} {block['label']:<52} {block['tier_floor']:>5} "
              f"{stats['mean_subscribed_recall']:>7} {stats['median_subscribed_recall']:>7} "
              f"{stats['min_subscribed_recall']:>6} {stats['max_subscribed_recall']:>6} "
              f"{stats['stdev_subscribed_recall']:>6} "
              f"{stats['heavy_mean_recall']:>7} {stats['light_mean_recall']:>7} "
              f"{stats['mean_pool_recall']:>7} {stats['mean_screen_passed']:>7} "
              f"{stats['mean_without_primary']:>6}")

    print()
    print("per tier hit rate: subscribed slots given to that tier, and how many gapped")
    tier_header = f"{'config':<12} " + " ".join(f"{'tier ' + str(t):>16}" for t in (1, 2, 3, 4, 5))
    print(tier_header)
    print("-" * len(tier_header))
    for key, block in outcome["results"].items():
        cells = []
        for tier in (1, 2, 3, 4, 5):
            bucket = block["summary"]["per_tier"].get(tier)
            cells.append(f"{'-':>16}" if not bucket else
                         f"{bucket['gapped']}/{bucket['subscribed']} = {bucket['hit_rate']:.2f}".rjust(16))
        print(f"{key:<12} " + " ".join(cells))

    # Screen passes per session, distributed. The mean alone is what the cap
    # decision was first read off, and on this population the median is two
    # thirds of it and steps very differently, so both are printed together.
    print("")
    print("screen passes per session, distributed")
    print(f"{'config':<20} {'min':>5} {'p25':>5} {'median':>7} {'mean':>7} "
          f"{'p75':>5} {'max':>5}")
    for key, block in outcome["results"].items():
        dist = block["summary"].get("screen_passed_distribution") or {}
        if not dist:
            continue
        print(f"{key:<20} {dist['min']:>5} {dist['p25']:>5} {dist['median']:>7} "
              f"{dist['mean']:>7} {dist['p75']:>5} {dist['max']:>5}")

    if args.json:
        from pathlib import Path

        Path(args.json).write_text(json.dumps(outcome, indent=2), encoding="utf-8")
        print(f"\nbacktest: wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
