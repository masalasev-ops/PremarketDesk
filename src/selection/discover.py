"""Morning discovery pass. Runs at 07:15 ET and builds the candidate pool.

This pass decides one thing: which names the collector should be listening to
from 07:20. Everything downstream is limited by that choice, because the
collector is the only source of today's premarket tape and it can only tell you
about names it subscribed to.

It used to answer that question by ranking the whole universe by gap off one
bulk /real-time call and keeping the top 30. That endpoint serves the last
COMPLETED session, so the ranking was of yesterday's movers wearing this
morning's label, and the error was structural: every morning's evidence was
gathered for the wrong names before the scan ever ran. Fixing the scan's
pricing did not touch it.

So nothing here reads a price from today. At 07:15 no source on this plan has
one for the whole universe, and pretending otherwise is what caused the
problem. Instead the pass assembles a PRIOR from four things that are all
knowable before the open:

  earnings before open today   the largest single source of premarket gaps,
                               and known in advance by definition
  overnight news               what was said between yesterday's close and now
  prior session movers         continuation, correctly labelled as a prior
                               rather than mistaken for today's gap
  recent runners               names that have been in play lately

The four are unioned, deduplicated, intersected with universe.json, ranked by
tier and then by 20 day average dollar volume, and cut at the subscription cap.
The names below the cut are written out too, marked not_subscribed, so the cut
is auditable rather than invisible.

A prior has blind spots by construction. pool_recall.json, written by the
nightly pass, measures them against what actually gapped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status
from core import store
from selection import universe
from morning import vintage

_CRIT = criteria.load()

# A source that failed and a source that succeeded with nothing are different
# facts and must never collapse into "the pool has no earnings names today".
# The same distinction catalyst_why already draws for the news feed.
FETCHED = "fetched"
FETCHED_EMPTY = "fetched_and_empty"
NOT_FETCHED = "not_fetched"


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _source(status: str, names: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"status": status, "names": names, **extra}


# --------------------------------------------------- source 1, earnings today

def earnings_before_open(
    api: eodhd.EodhdClient, universe_symbols: set[str], today: dt.date
) -> dict[str, Any]:
    """Names in the universe reporting before today's open.

    EODHD's calendar gives before_after_market and a report_date. It does NOT
    give a clock time, so a name reporting at 07:00 and one reporting at 08:30
    are indistinguishable in this feed. The field is recorded as the vendor
    supplies it rather than invented, and timing_precision says so.
    """
    rows, error = api.earnings_calendar(today, today)
    if error:
        return _source(NOT_FETCHED, {}, error=error)

    names: dict[str, Any] = {}
    for row in rows or []:
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        symbol = code if "." in code else f"{code}.US"
        if symbol not in universe_symbols:
            continue
        timing = str(row.get("before_after_market") or "").strip()
        if timing.lower() != "beforemarket":
            continue
        names[symbol] = {
            "timing": timing,
            "timing_precision": (
                "before or after market only; EODHD's calendar carries no clock "
                "time, so 07:00 and 08:30 reporters are not distinguishable here"
            ),
            "report_date": row.get("report_date"),
            "estimate": row.get("estimate"),
        }
    return _source(FETCHED if names else FETCHED_EMPTY, names,
                   rows_in_window=len(rows or []))


# ---------------------------------------------------- source 2, overnight news

class UnrankedPoolError(RuntimeError):
    """Raised when too little of the universe carries a ranking key to cut on."""


def news_window_start(session: dt.date) -> dt.datetime:
    """When the overnight news window opens for a session, in ET.

    The prior TRADING session's close, not yesterday's. Both are the same
    thing from Tuesday to Friday and they are two days apart on a Monday,
    which is exactly when the difference costs the most: a calendar day back
    from Monday is Sunday 16:00, and the window then never reaches Friday's
    close or anything published over the weekend.

    Production used the calendar day and backtest_pool used the trading
    session, so every Monday and post-holiday session in the cache was
    measured with a window production would not have used. The drift between
    them was the defect rather than either choice, so both now call this.

    A calendar the guard cannot answer falls back to one calendar day, which
    is the old behaviour: too narrow rather than too wide, because a window
    that reaches back too far pulls in news that is already priced in.
    """
    from morning import vintage

    prior = vintage.previous_trading_session(session)
    if prior is None:
        prior = session - dt.timedelta(days=1)
    hour, minute = _CRIT.clock("discovery", "news_window_start")
    return ettime.at(prior, hour, minute)


def overnight_news(
    api: eodhd.EodhdClient, universe_symbols: set[str], since: dt.datetime,
    until: dt.datetime,
) -> dict[str, Any]:
    """Universe names carrying news between the prior close and now.

    One symbol-less sweep of the feed, paged, then intersected with the
    universe. Asking per symbol is not affordable across 2,745 names, and the
    feed is global, so most of what comes back is discarded here.
    """
    page_size = _CRIT.integer("discovery", "news_sweep_page_size")
    max_pages = _CRIT.integer("discovery", "news_sweep_max_pages")

    names: dict[str, Any] = {}
    items_seen = 0
    pages = 0
    truncated = False
    for page in range(max_pages):
        rows, error = api.news_feed(
            since.date(), until.date(), limit=page_size, offset=page * page_size
        )
        if error:
            if page == 0:
                return _source(NOT_FETCHED, {}, error=error)
            # A later page failing still leaves a usable, partial sweep.
            truncated = True
            break
        pages += 1
        rows = rows or []
        items_seen += len(rows)

        oldest_on_page: dt.datetime | None = None
        for row in rows:
            when = _news_time(row.get("date"))
            if when is None:
                continue
            if oldest_on_page is None or when < oldest_on_page:
                oldest_on_page = when
            if not since <= when <= until:
                continue
            for raw in row.get("symbols") or []:
                symbol = str(raw).strip().upper()
                if symbol not in universe_symbols:
                    continue
                current = names.get(symbol)
                if current is None or when > dt.datetime.fromisoformat(current["newest_item_at"]):
                    names[symbol] = {
                        "newest_item_at": when.isoformat(),
                        "newest_title": row.get("title"),
                        "items": (current or {}).get("items", 0) + 1,
                    }
                else:
                    current["items"] += 1

        if len(rows) < page_size:
            break
        # The feed runs newest first, so once a whole page predates the window
        # there is nothing older worth paging for.
        if oldest_on_page is not None and oldest_on_page < since:
            break
        if page == max_pages - 1:
            truncated = True

    return _source(
        FETCHED if names else FETCHED_EMPTY, names,
        items_seen=items_seen, pages=pages, truncated=truncated,
        window=[since.isoformat(), until.isoformat()],
    )


def _news_time(raw: Any) -> dt.datetime | None:
    if not raw:
        return None
    try:
        when = dt.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return ettime.to_et(when)


# ----------------------------------------------- source 3, prior session movers

def prior_session_movers(
    api: eodhd.EodhdClient, universe_symbols: set[str],
    dollar_volume_20d: dict[str, float], today: dt.date,
) -> dict[str, Any]:
    """Names that moved hard, or traded unusually heavily, in the prior session.

    Two bulk end of day calls, the prior trading session and the one before it,
    so the move is close to close. A single call would only give the intraday
    move and would miss a name that gapped and held, which is exactly the kind
    of name this source exists to catch.

    This is the input the pool has always had. What changed is the label: it is
    a continuation prior about yesterday, not a reading of today.
    """
    prior = vintage.previous_trading_session(today)
    if prior is None:
        return _source(NOT_FETCHED, {}, error="the exchange calendar could not "
                                              "name the prior trading session")
    before = vintage.previous_trading_session(prior)
    if before is None:
        return _source(NOT_FETCHED, {}, error="the exchange calendar could not "
                                              "name the session before the prior one")

    move_floor = _CRIT.number("discovery", "prior_session_move_pct")
    dollar_multiple = _CRIT.number("discovery", "prior_session_dollar_multiple")

    prior_rows, error = api.eod_bulk_last_day("US", day=prior)
    if error:
        return _source(NOT_FETCHED, {}, error=f"prior session bulk failed: {error}")
    before_rows, error = api.eod_bulk_last_day("US", day=before)
    if error:
        return _source(NOT_FETCHED, {}, error=f"earlier session bulk failed: {error}")

    def by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            code = str(row.get("code") or "").strip().upper()
            if not code:
                continue
            out[code if "." in code else f"{code}.US"] = row
        return out

    prior_by = by_symbol(prior_rows)
    before_by = by_symbol(before_rows)

    names: dict[str, Any] = {}
    for symbol in universe_symbols:
        prior_row = prior_by.get(symbol)
        before_row = before_by.get(symbol)
        if not prior_row or not before_row:
            continue
        close = _as_float(prior_row.get("close"))
        prior_close = _as_float(before_row.get("close"))
        volume = _as_float(prior_row.get("volume")) or 0.0
        if close is None or not prior_close:
            continue

        move = (close - prior_close) / prior_close * 100.0
        dollar_volume = close * volume
        average = dollar_volume_20d.get(symbol) or 0.0
        heavy = bool(average) and dollar_volume >= average * dollar_multiple
        if abs(move) < move_floor and not heavy:
            continue
        names[symbol] = {
            "prior_session": prior.isoformat(),
            "move_pct": round(move, 4),
            "dollar_volume": round(dollar_volume, 2),
            "dollar_volume_multiple": round(dollar_volume / average, 3) if average else None,
            "qualified_on": (
                ["move", "dollar_volume"] if abs(move) >= move_floor and heavy
                else ["move"] if abs(move) >= move_floor else ["dollar_volume"]
            ),
        }

    # The prior session close for every universe name, carried out of the same
    # two calls at no extra cost. The 08:45 scan needs one to rank the
    # subscribed names by measured gap, and buying it again there would be a
    # third bulk call for a number already in hand. It is used for RANKING
    # only: the published prior_close and prior_high still come together out of
    # one per name end of day record, so they cannot drift a session apart.
    closes = {
        symbol: {"close": _as_float(row.get("close")), "date": row.get("date")}
        for symbol, row in prior_by.items()
        if symbol in universe_symbols and _as_float(row.get("close")) is not None
    }

    # The whole universe's recent closes, written to a sidecar rather than into
    # watchlist.json, which carries only the subscribed names. The report's
    # notable movers section is universe wide and has no other source: the
    # collector hears at most the subscription cap, so for every other name the
    # most recent evidence is a completed session. Both maps above are already
    # bought and were previously discarded, so two of the three sessions cost
    # nothing. Sidecar rather than watchlist because 2,754 names of closes in
    # the watchlist would be read by the collector and the scan, neither of
    # which wants them, and this file is briefing data with no trading path.
    write_universe_closes(api, universe_symbols, prior_by, before_by, prior, before, today)

    return _source(FETCHED if names else FETCHED_EMPTY, names,
                   prior_session=prior.isoformat(), earlier_session=before.isoformat(),
                   closes=closes)


def write_universe_closes(
    api: eodhd.EodhdClient,
    universe_symbols: set[str],
    prior_by: dict[str, dict[str, Any]],
    before_by: dict[str, dict[str, Any]],
    prior: dt.date,
    before: dt.date,
    today: dt.date,
) -> dict[str, Any]:
    """Three completed session closes per universe name, for the briefing only.

    The briefing measures two legs from these: prior_session is c2 to c1, and
    two_session is c3 to c1. Sessions minus one and minus two are already in
    hand. The third costs one more bulk end of day call, a flat hundred credits
    in CRITERIA [quota costs], and it is bought rather than read from gap_stats
    so that all three closes carry the SAME vintage. gap_stats is rebuilt on
    Sundays, so by Friday its closes are five sessions old, and a two session
    move measured from a five session old baseline is the silent vintage mixing
    this project has been bitten by before.

    Every close carries its own session date. A name missing from any of the
    three maps is written with a null for that close and is never backfilled
    from a neighbouring session, because a move measured across a gap of
    unknown width is not the move its label claims.

    Always returns the payload. A failed third call costs the two session leg
    and nothing else, and that is recorded in third_session_available rather
    than signalled by a return value nobody checks.

    A calendar that cannot NAME the third session reaches the same outcome by a
    different route, and it has to be answered before the call rather than
    after it. previous_trading_session returns None when market_today cannot
    answer, and eod-bulk-last-day only sends a date parameter when the day is
    truthy, so handing that None straight to the vendor buys the LATEST
    completed session and files it as c3. That is c1 again under another name:
    every two session move in the briefing would measure a close against
    itself, print as zero, and be indistinguishable from a genuinely flat name.
    The line that dates the sessions below would then call .isoformat() on the
    None and raise AttributeError, which discover.main does not catch, so the
    07:15 pass would die before writing watchlist.json and the collector would
    start the morning with nothing to subscribe to. So the call is skipped
    entirely and the leg is simply absent, which is what the paragraph above
    already promises for a third call that fails.
    """
    third = vintage.previous_trading_session(before)
    third_by: dict[str, dict[str, Any]] = {}
    if third is None:
        print("discover: the exchange calendar could not name the third session, "
              "so the briefing's two session leg is absent this morning. The prior "
              "session leg is unaffected, and the bulk call that would have bought "
              "the wrong session was not made.")
    else:
        third_rows, error = api.eod_bulk_last_day("US", day=third)
        if error:
            print(f"discover: the third session bulk call failed ({error}), so the "
                  "briefing's two session leg is absent this morning. The prior "
                  "session leg is unaffected.")
        else:
            for row in third_rows or []:
                code = str(row.get("code") or "").strip().upper()
                if code:
                    third_by[code if "." in code else f"{code}.US"] = row

    def close_of(source: dict[str, dict[str, Any]], symbol: str) -> float | None:
        row = source.get(symbol)
        return _as_float(row.get("close")) if row else None

    rows: dict[str, Any] = {}
    for symbol in sorted(universe_symbols):
        c1 = close_of(prior_by, symbol)
        c2 = close_of(before_by, symbol)
        c3 = close_of(third_by, symbol) if third_by else None
        if c1 is None and c2 is None and c3 is None:
            continue
        rows[symbol] = {"c1": c1, "c2": c2, "c3": c3}

    payload = {
        "generated_at": ettime.stamp(ettime.now_et()),
        "session_date": today.isoformat(),
        "sessions": {
            "c1": prior.isoformat(),
            "c2": before.isoformat(),
            # Both halves, not the populated map alone. third_by can only fill
            # under a named session today, so "third is not None" is redundant
            # here right now, and it is precisely the half that keeps this line
            # from raising AttributeError again if a later edit fills that map
            # by some other route. A date that cannot be written is a null,
            # never an exception thrown out of a function whose stated contract
            # is that it always returns the payload.
            "c3": third.isoformat() if (third is not None and third_by) else None,
        },
        "universe_examined": len(universe_symbols),
        "names_with_at_least_one_close": len(rows),
        "third_session_available": bool(third_by),
        "closes": rows,
    }
    path = config.DATA_DIR / f"universe-closes-{today.isoformat()}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"discover: wrote {len(rows)} universe closes over "
          f"{3 if third_by else 2} completed sessions to {path.name}, for the "
          "report's notable movers section only")
    return payload


# ------------------------------------------------- source 4, recent runners

def recent_runners(universe_symbols: set[str], today: dt.date) -> dict[str, Any]:
    """Names that were candidates recently, weighted so recent counts for more.

    Reads the picks table, live rows only. An empty table is a normal state on
    a new install and returns nothing rather than failing.
    """
    lookback = _CRIT.integer("discovery", "recent_runner_lookback")
    decay = _CRIT.number("discovery", "recent_runner_decay")

    try:
        with store.session() as connection:
            store.init(connection)
            dates = [
                row[0] for row in connection.execute(
                    "SELECT DISTINCT date FROM picks WHERE source='live' AND date < ? "
                    "ORDER BY date DESC LIMIT ?",
                    (today.isoformat(), lookback),
                ).fetchall()
            ]
            if not dates:
                return _source(FETCHED_EMPTY, {}, sessions_considered=0)
            placeholders = ", ".join("?" for _ in dates)
            rows = connection.execute(
                f"SELECT ticker, date FROM picks WHERE source='live' "
                f"AND date IN ({placeholders})",
                dates,
            ).fetchall()
    except Exception as exc:  # a missing or unreadable database is not fatal here
        return _source(NOT_FETCHED, {}, error=f"{type(exc).__name__}: {exc}")

    sessions_ago = {date: index for index, date in enumerate(dates)}
    names: dict[str, Any] = {}
    for ticker, date in rows:
        symbol = str(ticker).strip().upper()
        if symbol not in universe_symbols:
            continue
        weight = decay ** sessions_ago.get(date, len(dates))
        current = names.get(symbol)
        if current is None or weight > current["weight"]:
            names[symbol] = {
                "weight": round(weight, 6),
                "last_seen": date,
                "sessions_ago": sessions_ago.get(date),
                "appearances": (current or {}).get("appearances", 0) + 1,
            }
        else:
            current["appearances"] += 1
    return _source(FETCHED if names else FETCHED_EMPTY, names,
                   sessions_considered=len(dates))


# ------------------------------------------------------- assembling and ranking

def _tier_map() -> dict[str, int]:
    return {key: int(value) for key, value in _CRIT.pair_map("pool_tiers", "tier").items()}


def load_metrics() -> dict[str, dict[str, Any]]:
    """Per name ranking inputs: dollar volume from the universe, the rest cached.

    Both are free at 07:15. avg_dollar_volume_20d was written by the weekly
    universe rebuild and the gap statistics by gap_stats.py on the same
    schedule, so nothing here is computed or fetched in the morning.
    """
    from selection import gap_stats

    try:
        universe_payload = universe.load_universe(require_fresh=False)
    except Exception as exc:  # noqa: BLE001
        # Empty metrics do not stop the pool being built, they stop it being
        # ranked: every name falls to the bottom band with no propensity and
        # no ATR, so the cut becomes arbitrary. That used to happen in silence
        # behind a zero exit.
        print(f"discover: ranking metrics unavailable, {type(exc).__name__}: {exc}. "
              "Every name will rank in the fallback band.")
        job_status.failed(f"{type(exc).__name__}: the universe could not be read "
                          "for ranking metrics, so the pool was cut without "
                          "propensity or ATR to rank on")
        universe_payload = {"symbols": []}

    metrics: dict[str, dict[str, Any]] = {}
    for row in universe_payload.get("symbols", []):
        symbol = str(row.get("symbol", "")).upper()
        if symbol:
            metrics[symbol] = {
                "avg_dollar_volume_20d": _as_float(row.get("avg_dollar_volume_20d")) or 0.0,
                "gap_propensity": None,
                "atr_pct_20d": None,
                "median_abs_gap_pct": None,
            }
    for symbol, stats in gap_stats.load_all().items():
        if symbol in metrics:
            metrics[symbol].update({
                "gap_propensity": stats.get("gap_propensity"),
                "atr_pct_20d": stats.get("atr_pct_20d"),
                "median_abs_gap_pct": stats.get("median_abs_gap_pct"),
            })
    return metrics


def rank_value(symbol: str, metrics: dict[str, dict[str, Any]]) -> tuple[int, float]:
    """The within tier sort value for one name. Three bands, best first.

    The leading band is what keeps a null out of the way of a measured zero: a
    name nobody has measured and a name that has not gapped in a year are
    different facts, and collapsing them would promote every recent listing
    above every genuinely quiet name. See the null note in CRITERIA.md.

    Band 0 is the primary key. Band 1 is the fallback, for names the primary
    structurally cannot score: gap propensity needs 100 sessions, and newly
    listed names are over-represented among hard gappers, so ranking them last
    cuts the population most worth watching. SECZ gapped 25.6 percent on
    2026-08-13 with a null propensity. The fallback needs only 20 sessions.
    Band 2 is neither, which is recorded by the caller rather than left silent.
    """
    row = metrics.get(symbol) or {}
    value = row.get(_CRIT.text("discovery", "within_tier_key"))
    if value is not None:
        return (0, -float(value))
    fallback_key = _CRIT.text("discovery", "within_tier_fallback")
    fallback = row.get(fallback_key) if fallback_key else None
    if fallback is not None:
        return (1, -float(fallback))
    return (2, 0.0)


def apply_slots(
    ranked: list[dict[str, Any]], cap: int, min_slots_per_tier: int
) -> list[dict[str, Any]]:
    """Mark subscribed rows, giving each populated tier its floor first.

    With a floor of zero this is strict priority, which in 60 replayed sessions
    never gave tiers 3 or 4 a single slot. Above zero each tier that has
    candidates takes its floor before the remainder fills by overall rank, so a
    heavy earnings morning cannot spend the whole cap on tier 1 and a light one
    cannot hand it all to whatever sorts first below.
    """
    chosen: list[dict[str, Any]] = []
    picked: set[int] = set()
    if min_slots_per_tier:
        by_tier: dict[int, list[dict[str, Any]]] = {}
        for row in ranked:
            by_tier.setdefault(row["pool_tier"], []).append(row)
        for tier in sorted(by_tier):
            for row in by_tier[tier][:min_slots_per_tier]:
                if len(chosen) >= cap:
                    break
                chosen.append(row)
                picked.add(id(row))
            if len(chosen) >= cap:
                break
    for row in ranked:
        if len(chosen) >= cap:
            break
        if id(row) not in picked:
            chosen.append(row)
            picked.add(id(row))

    subscribed = {id(row) for row in chosen}
    for row in ranked:
        row["subscribed"] = id(row) in subscribed
        row["not_subscribed"] = not row["subscribed"]
    return ranked


def assemble(
    sources: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    now: dt.datetime,
) -> list[dict[str, Any]]:
    """Union the sources, assign each name its best tier, and rank the pool.

    Ranking is by tier, then by the CRITERIA within_tier_key descending, then
    by symbol so the order is total and a rerun is reproducible. No field from
    today is involved, because none exists yet.

    The key is gap propensity, chosen by measurement rather than assumption;
    see the ordering note in CRITERIA.md for the sweep that picked it over the
    20 day dollar volume it replaced.
    """
    tiers = _tier_map()
    fresh_hours = _CRIT.number("discovery", "news_fresh_hours")

    pool: dict[str, dict[str, Any]] = {}

    def touch(symbol: str) -> dict[str, Any]:
        row = metrics.get(symbol) or {}
        return pool.setdefault(symbol, {
            "symbol": symbol,
            "pool_source": [],
            "pool_tier": None,
            "pool_evidence": {},
            "avg_dollar_volume_20d": row.get("avg_dollar_volume_20d"),
            "gap_propensity": row.get("gap_propensity"),
            "atr_pct_20d": row.get("atr_pct_20d"),
        })

    def claim(symbol: str, source_name: str, tier_key: str, evidence: Any) -> None:
        entry = touch(symbol)
        if source_name not in entry["pool_source"]:
            entry["pool_source"].append(source_name)
        entry["pool_evidence"][source_name] = evidence
        tier = tiers[tier_key]
        if entry["pool_tier"] is None or tier < entry["pool_tier"]:
            entry["pool_tier"] = tier
            entry["pool_tier_reason"] = tier_key

    for symbol, evidence in sources["earnings"]["names"].items():
        claim(symbol, "earnings", "earnings_before_open", evidence)

    for symbol, evidence in sources["news"]["names"].items():
        when = dt.datetime.fromisoformat(evidence["newest_item_at"])
        age_hours = (now - when).total_seconds() / 3600.0
        evidence = {**evidence, "age_hours": round(age_hours, 3)}
        claim(symbol, "news",
              "news_fresh" if age_hours <= fresh_hours else "news_stale", evidence)

    for symbol, evidence in sources["movers"]["names"].items():
        claim(symbol, "prior_session_mover", "prior_session_mover", evidence)

    for symbol, evidence in sources["runners"]["names"].items():
        claim(symbol, "recent_runner", "recent_runner", evidence)

    closes = sources["movers"].get("closes") or {}
    for symbol, entry in pool.items():
        prior = closes.get(symbol) or {}
        entry["pool_prior_close"] = prior.get("close")
        entry["pool_prior_session_date"] = prior.get("date")

    ranked = sorted(
        pool.values(),
        key=lambda row: (row["pool_tier"], *rank_value(row["symbol"], metrics),
                         row["symbol"]),
    )
    return ranked


def build(write: bool = True) -> dict[str, Any]:
    config.ensure_dirs()

    quota = eodhd.preflight("discover")
    if quota["refused"]:
        raise eodhd.QuotaRefusal(
            f"quota exhausted by another consumer on the shared key: "
            f"{eodhd.describe_preflight(quota)}, below the refuse floor of "
            f"{quota['refuse_below']:,} in CRITERIA.md [quota]"
        )

    universe_payload = universe.require_fresh_universe()
    # require_fresh_universe answers "is it too old". This answers "is it whole".
    # A stale universe is a usable input and every later script knows how to
    # refuse one; a half written one is not usable, and until the Sunday job
    # wrote atomically nothing distinguished them.
    incomplete = universe.check_admissible(universe_payload)
    if incomplete:
        raise universe.StaleUniverseError(incomplete)

    universe_symbols = set(universe.universe_symbols(universe_payload))
    metrics = load_metrics()
    dollar_volume_20d = {
        symbol: (row.get("avg_dollar_volume_20d") or 0.0)
        for symbol, row in metrics.items()
    }
    cap = _CRIT.integer("discovery", "max_subscribed_candidates")
    min_slots = _CRIT.integer("discovery", "min_slots_per_tier")
    ranking_key = _CRIT.text("discovery", "within_tier_key")
    scored = sum(1 for row in metrics.values() if row.get(ranking_key) is not None)

    # An unranked pool must not be cut. When load_metrics cannot read the
    # universe or the gap_stats table is empty, the pool still builds and the
    # cap still applies, but every name sits in the fallback band with no key,
    # so which 42 get subscribed is arbitrary. Nothing downstream can tell that
    # from a real selection: the watchlist looks normal, the collector
    # subscribes, the report publishes. A missing report is recoverable. A
    # plausible one built from a random sample is not.
    ranked_floor = _CRIT.number("discovery", "min_ranked_fraction_to_subscribe")
    ranked_fraction = (scored / len(universe_symbols)) if universe_symbols else 0.0
    if ranked_fraction < ranked_floor:
        raise UnrankedPoolError(
            f"only {scored} of {len(universe_symbols)} universe names carry a "
            f"{ranking_key}, a fraction of {ranked_fraction:.3f} against the "
            f"{ranked_floor:g} floor in {config.CRITERIA_PATH.name} [discovery] "
            "min_ranked_fraction_to_subscribe. The pool would be cut to the cap "
            "with nothing to rank on, and an arbitrary selection is "
            "indistinguishable from a real one everywhere downstream. Run "
            "gap_stats.py, or check that universe.json is readable."
        )

    now = ettime.now_et()
    today = now.date()
    news_since = news_window_start(today)

    print(f"discover: universe started with {len(universe_symbols)} names")
    print(f"discover: building a pool from four priors, no price from today is read")

    api = eodhd.client()
    sources = {
        "earnings": earnings_before_open(api, universe_symbols, today),
        "news": overnight_news(api, universe_symbols, news_since, now),
        "movers": prior_session_movers(api, universe_symbols, dollar_volume_20d, today),
        "runners": recent_runners(universe_symbols, today),
    }

    gaps: list[str] = []
    for name, source in sources.items():
        count = len(source["names"])
        print(f"discover: source {name:<20} {source['status']:<18} {count:>5} names"
              + (f"  ({source['error']})" if source.get("error") else ""))
        if source["status"] == NOT_FETCHED:
            gaps.append(
                f"the {name} pool source was never fetched: {source.get('error')}. "
                "The pool is missing whatever that source would have contributed, "
                "which is not the same as that source having nothing to contribute."
            )

    ranked = assemble(sources, metrics, now)
    for index, row in enumerate(ranked):
        row["pool_rank"] = index + 1
    apply_slots(ranked, cap, min_slots)

    subscribed = [row for row in ranked if row["subscribed"]]
    unscored = [row["symbol"] for row in subscribed
                if (metrics.get(row["symbol"]) or {}).get(ranking_key) is None]
    if unscored:
        gaps.append(
            f"{len(unscored)} subscribed name(s) have no {ranking_key} and were "
            f"ranked last within their tier: {', '.join(sorted(unscored)[:10])}"
            + (" and more" if len(unscored) > 10 else "")
        )

    if quota["degraded"]:
        gaps.append(
            f"quota preflight: {eodhd.describe_preflight(quota)}, below the "
            f"{quota['degrade_below']:,} threshold in CRITERIA.md [quota]."
        )
    if not subscribed:
        gaps.append(
            "the pool is empty, so the collector has nothing to subscribe to and "
            "the morning will have no premarket evidence for any name"
        )

    payload: dict[str, Any] = {
        "generated_at": ettime.stamp(now),
        "quota_preflight": quota,
        "gaps_to_fill": gaps,
        "universe_started_with": len(universe_symbols),
        "universe_generated_at": universe_payload.get("generated_at"),
        "selection_method": (
            "a prior assembled from earnings, overnight news, prior session "
            "movers and recent runners. No price from today is read here, "
            "because no source on this plan has one for the whole universe at "
            "07:15. See DECISIONS.md 2026-08-14."
        ),
        # names and closes are per symbol payloads carried on the pool rows
        # themselves; repeating them here would put the whole universe's closes
        # into watchlist.json.
        "pool_sources": {
            name: {
                key: value for key, value in source.items()
                if key not in ("names", "closes")
            }
            for name, source in sources.items()
        },
        "tier_order": _CRIT.pair_map("pool_tiers", "tier"),
        "ranking": {
            "within_tier_key": ranking_key,
            "min_slots_per_tier": min_slots,
            "universe_names_with_a_key": scored,
            "universe_names_without": len(metrics) - scored,
            "basis": (
                "measured over 60 sessions by src/backtest_pool.py, see the "
                "ordering note in CRITERIA.md"
            ),
        },
        "max_subscribed_candidates": cap,
        "pool_size": len(ranked),
        "subscribed_count": len(subscribed),
        "api_calls": eodhd.call_count(),
        "symbols": ranked,
    }

    print(f"discover: pool holds {len(ranked)} names, "
          f"subscribing to the top {len(subscribed)} of a {cap} cap")
    by_tier: dict[int, int] = {}
    for row in ranked:
        by_tier[row["pool_tier"]] = by_tier.get(row["pool_tier"], 0) + 1
    for tier in sorted(by_tier):
        print(f"    tier {tier}: {by_tier[tier]:>4} names")
    print(f"discover: ranking within tier by {ranking_key} descending, "
          f"{min_slots} slot(s) floored per tier, {scored} of {len(metrics)} "
          "universe names carry that key")
    for row in subscribed[:10]:
        value = (metrics.get(row["symbol"]) or {}).get(ranking_key)
        shown = "null" if value is None else f"{value:.4f}"
        print(f"    {row['symbol']:<12} tier {row['pool_tier']}  "
              f"{'+'.join(row['pool_source']):<40} {ranking_key} {shown:>8}")

    if write:
        config.WATCHLIST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"discover: wrote {config.WATCHLIST_PATH}")

    return payload


def load_watchlist() -> dict[str, Any]:
    path = config.WATCHLIST_PATH
    if not path.exists():
        return {"symbols": [], "generated_at": None, "missing": True}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"symbols": [], "generated_at": None, "missing": True}


def subscribed_symbols(watchlist: dict[str, Any]) -> list[str]:
    """The names the collector was asked to listen to.

    Rows written before the pool rewrite carry no subscribed flag. They were
    all subscribed, so a missing flag reads as true rather than as false, which
    would silently empty the collector's subscription list on the first run
    after an upgrade.
    """
    out: list[str] = []
    for row in watchlist.get("symbols", []):
        symbol = str(row.get("symbol", "")).upper()
        if symbol and row.get("subscribed", True):
            out.append(symbol)
    return out


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the morning candidate pool.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write watchlist.json.")
    args = parser.parse_args(argv)

    try:
        payload = build(write=not args.dry_run)
        job_status.produced("names subscribed", payload.get("subscribed_count"))
        # A source that raised is already recorded in watchlist.json as
        # not_fetched with its reason, which is the right place for the audit
        # trail and the wrong place for a human to find out. The pool is built
        # from four priors and losing one narrows what the morning can see, so
        # it belongs in the status record too.
        broken = sorted(
            name for name, source in (payload.get("pool_sources") or {}).items()
            if source.get("status") == NOT_FETCHED
        )
        if broken:
            job_status.failed(
                f"{len(broken)} pool source(s) could not be fetched: "
                + ", ".join(broken)
            )
    except (universe.StaleUniverseError, eodhd.QuotaRefusal, UnrankedPoolError) as exc:
        print(f"REFUSING TO RUN: {exc}")
        # Non zero exit and no watchlist written, so the collector finds either
        # nothing or yesterday's file and says which. The record carries the
        # reason so the next morning's report names it even though this job
        # never got far enough to write anything else.
        job_status.failed(f"{type(exc).__name__}: {exc}")
        eodhd.print_call_report()
        return 1
    except RuntimeError as exc:
        print(f"discover: failed, {exc}")
        eodhd.print_call_report()
        return 1

    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(job_status.run("discover", main, ok_codes=OK_CODES))
