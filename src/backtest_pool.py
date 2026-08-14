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
sessions share it: session N's outcome read is session N+1's prior read. Sixty
sessions therefore cost sixty one bulk days, not a hundred and twenty.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from typing import Any, Callable

import config
import criteria
import discover
import eodhd
import ettime
import universe

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
    news_start_h, news_start_m = _CRIT.clock("discovery", "news_window_start")
    news_since = ettime.at(prior, news_start_h, news_start_m)

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
    dollar_volume = {symbol: (metric.get("avg_dollar_volume_20d") or 0.0)
                     for symbol, metric in metrics.items()}
    now = dt.datetime.fromisoformat(inputs["run_clock"])
    return discover.assemble(sources, dollar_volume, now)


ORDERINGS: dict[str, dict[str, Any]] = {
    "A": {
        "label": "20 day average dollar volume descending",
        "key": "avg_dollar_volume_20d",
        "shipped": True,
    },
    "B": {"label": "gap propensity descending", "key": "gap_propensity"},
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
    key = ordering["key"]
    floor = ordering.get("min_dollar_volume")

    rows = list(pool)
    if floor:
        rows = [
            row for row in rows
            if (metrics.get(row["symbol"], {}).get("avg_dollar_volume_20d") or 0.0) >= floor
        ]

    def sort_key(row: dict[str, Any]) -> tuple:
        value = metrics.get(row["symbol"], {}).get(key)
        return (row["pool_tier"], 0 if value is not None else 1,
                -(value or 0.0), row["symbol"])

    rows.sort(key=sort_key)
    for index, row in enumerate(rows):
        row = dict(row)
        rows[index] = row
        row["pool_rank"] = index + 1
    return rows


def apply_cap(
    rows: list[dict[str, Any]], cap: int, tier_floor: int = 0
) -> list[dict[str, Any]]:
    """Mark the subscribed rows, optionally guaranteeing each tier a minimum.

    With tier_floor zero this is strict priority: the cap is filled from the
    top of the overall order. Above zero, each tier that has candidates takes
    its floor first and the remainder fills by overall rank, so a heavy
    earnings morning cannot spend every slot on tier 1 and a light one cannot
    hand the whole cap to whatever sorts first below it.
    """
    chosen: list[dict[str, Any]] = []
    if tier_floor:
        by_tier: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            by_tier.setdefault(row["pool_tier"], []).append(row)
        for tier in sorted(by_tier):
            chosen.extend(by_tier[tier][:tier_floor])
            if len(chosen) >= cap:
                break
    picked = {id(row) for row in chosen}
    for row in rows:
        if len(chosen) >= cap:
            break
        if id(row) not in picked:
            chosen.append(row)
            picked.add(id(row))

    subscribed = {row["symbol"] for row in chosen[:cap]}
    out = []
    for row in rows:
        row = dict(row)
        row["subscribed"] = row["symbol"] in subscribed
        out.append(row)
    return out


def evaluate_session(
    session_date: str,
    metrics: dict[str, dict[str, Any]],
    ordering: dict[str, Any],
    cap: int,
    tier_floor: int = 0,
) -> dict[str, Any]:
    import pool_recall

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

    return {
        "session_date": session_date,
        "gapped": result["gapped"],
        "pool_held": result["pool_held"],
        "recall": result["recall"],
        "subscribed_held": result["subscribed_held"],
        "subscribed_recall": result["subscribed_recall"],
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
    import gap_stats

    universe_payload = universe.load_universe(require_fresh=False)
    metrics: dict[str, dict[str, Any]] = {}
    for row in universe_payload.get("symbols", []):
        symbol = str(row.get("symbol", "")).upper()
        if not symbol:
            continue
        metrics[symbol] = {
            "avg_dollar_volume_20d": _as_float(row.get("avg_dollar_volume_20d")) or 0.0,
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
    as_of: str | None = None,
) -> dict[str, Any]:
    cap = _CRIT.integer("discovery", "max_subscribed_candidates")
    metrics = load_metrics(as_of)
    sessions = sessions or cached_sessions()
    if not sessions:
        raise RuntimeError(f"no cached sessions under {SESSION_DIR}")

    results: dict[str, Any] = {}
    for name in orderings:
        ordering = ORDERINGS[name]
        for floor in floors:
            rows = [
                evaluate_session(session, metrics, ordering, cap, tier_floor=floor)
                for session in sessions
            ]
            results[f"{name}/floor{floor}"] = {
                "ordering": name,
                "label": ordering["label"],
                "tier_floor": floor,
                "sessions": rows,
            }
    return {"cap": cap, "sessions": sessions, "metrics_as_of": as_of,
            "results": results}


def summarise(rows: list[dict[str, Any]], heavy_threshold: int) -> dict[str, Any]:
    recalls = [r["subscribed_recall"] for r in rows if r["subscribed_recall"] is not None]
    heavy = [r for r in rows if r["earnings_names"] >= heavy_threshold]
    light = [r for r in rows if r["earnings_names"] < heavy_threshold]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def recall_of(subset: list[dict[str, Any]]) -> float | None:
        got = [r["subscribed_recall"] for r in subset if r["subscribed_recall"] is not None]
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

    return {
        "sessions": len(rows),
        "per_tier": dict(sorted(per_tier.items())),
        "mean_subscribed_recall": mean(recalls),
        "median_subscribed_recall": round(statistics.median(recalls), 4) if recalls else None,
        "min_subscribed_recall": round(min(recalls), 4) if recalls else None,
        "max_subscribed_recall": round(max(recalls), 4) if recalls else None,
        "stdev_subscribed_recall": (
            round(statistics.pstdev(recalls), 4) if len(recalls) > 1 else None
        ),
        "mean_pool_recall": mean([r["recall"] for r in rows if r["recall"] is not None]),
        "heavy_sessions": len(heavy),
        "heavy_mean_recall": recall_of(heavy),
        "light_sessions": len(light),
        "light_mean_recall": recall_of(light),
        "total_gapped": sum(r["gapped"] for r in rows),
        "total_subscribed_held": sum(r["subscribed_held"] for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest the candidate pool.")
    sub = parser.add_subparsers(dest="stage", required=True)

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
    evaluate.add_argument("--as-of", help="gap_stats window to rank with. Use a date "
                          "before the earliest session to stay out of sample.")
    evaluate.add_argument("--json", metavar="PATH", help="Write the full results here.")
    args = parser.parse_args(argv)

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
    outcome = sweep(orderings, floors, as_of=args.as_of)
    sessions = outcome["sessions"]
    print(f"backtest: {len(sessions)} cached sessions, {sessions[0]} to {sessions[-1]}, "
          f"cap {outcome['cap']}, ranking metrics as of {outcome['metrics_as_of'] or 'newest'}")
    print()
    header = (f"{'config':<12} {'ordering':<52} {'floor':>5} {'mean':>7} {'median':>7} "
              f"{'min':>6} {'max':>6} {'sd':>6} {'heavy':>7} {'light':>7} {'pool':>7}")
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
              f"{stats['mean_pool_recall']:>7}")

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

    if args.json:
        from pathlib import Path

        Path(args.json).write_text(json.dumps(outcome, indent=2), encoding="utf-8")
        print(f"\nbacktest: wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
