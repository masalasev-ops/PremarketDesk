"""The 08:45 gathering pass. Writes one packet.json and judges nothing.

Two jobs, kept strictly apart.

Gathering, which is everything numbered below. It fetches, it records where
each number came from, and when something fails it writes the failure into
gaps_to_fill and carries on. A network error never ends this run. A packet with
holes in it and an honest list of those holes is worth far more than no packet.

Stamping, which is the eligibility flags and the confluence score. Those are
computed here, in Python, straight from CRITERIA.md, with no model anywhere
near them. By the time the analyst pass runs, membership and conviction are
already decided and are not its to change.

The one rule that shapes the whole file: premarket high, low and VWAP come from
the collector file and from nowhere else. A quote snapshot tells you where a
name is, not where it has been, and a premarket high inferred from a snapshot
is a number that looks like evidence and is not. When the collector was not
listening, the answer is null and the packet says why.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from typing import Any
from urllib.parse import urlparse

from collect import baseline
from collect import collect_premarket
from core import config
from core import criteria
from selection import discover
from core import eodhd
from core import ettime
from ops import job_status
from core import store
from selection import universe
from morning import vintage

_CRIT = criteria.load()


def _as_float(value: Any) -> float | None:
    if value is None or value == "" or value == "NA":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


class Packet:
    """The morning's evidence, plus an honest list of what is missing from it."""

    def __init__(self) -> None:
        self.gaps: list[str] = []
        self.data: dict[str, Any] = {}

    def gap(self, note: str) -> None:
        print(f"scan: GAP  {note}")
        self.gaps.append(note)


# ------------------------------------------------------- 1. market snapshot

def _collector_last(bars: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    """The last premarket trade price the collector recorded, and its minute.

    The bar is stamped at the minute it opens, so the timestamp returned is the
    start of the last minute that carried a trade, never a wall clock read.
    """
    if not bars:
        return None, None
    last = max(bars, key=lambda b: b["minute_epoch"])
    return (
        _as_float(last.get("c")),
        ettime.stamp(ettime.from_epoch_s(last["minute_epoch"])),
    )


def collector_coverage(
    bars_by_symbol: dict[str, list[dict[str, Any]]], session_date: str
) -> dict[str, Any]:
    """Which subscribed symbols the socket actually served, and which stayed silent.

    Silence and absence are different failures and the packet has to tell them
    apart. A symbol that was never subscribed produced nothing because nobody
    asked; a symbol that was subscribed and produced nothing means the socket
    accepted the subscription and delivered no trade for it, which at fifty
    names on a socket load tested at thirty eight is the thing worth watching.
    Neither is inferable from the bar file alone, which is why the collector
    writes its subscription list at subscribe time.

    The peak trade rate comes out of the bars themselves, which carry a trade
    count per minute, so no counter had to be added to the hot path. The late
    trade count does not: it lives in the running builder and is only written
    to the stats sidecar when the collector stops at 09:25, which is after
    this packet is built. It stays null with that reason recorded rather than
    being filled with a number from a previous day's run.
    """
    subscriptions = collect_premarket.read_subscriptions(session_date)
    with_bars = {symbol for symbol, bars in bars_by_symbol.items() if bars}

    if not subscriptions:
        return {
            "requested": None,
            "produced_bars": len(with_bars),
            "silent": None,
            "silent_symbols": [],
            "unsubscribed_with_bars": [],
            "reason": (f"the collector wrote no subscription list for {session_date}, "
                       "so a silent symbol cannot be told from one that was never "
                       "subscribed"),
            "peak_trades_per_minute": _peak_trades_per_minute(bars_by_symbol),
            "late_trades": None,
            "late_trades_reason": (
                "the late trade count is held by the running collector and written "
                "when it stops at the CRITERIA.md [collector] stop_time, which is "
                "after this packet is built"
            ),
        }

    requested = [str(s) for s in subscriptions.get("symbols") or []]
    silent = sorted(set(requested) - with_bars)
    return {
        "subscribed_at": subscriptions.get("subscribed_at"),
        "requested": len(requested),
        "socket_cap": subscriptions.get("socket_cap"),
        "produced_bars": len(with_bars & set(requested)),
        "silent": len(silent),
        # Named, not counted. A count says the socket is lossy; the names say
        # which report rows are missing their evidence because of it.
        "silent_symbols": silent,
        "dropped_to_fit_cap": subscriptions.get("dropped_to_fit_cap") or [],
        "unsubscribed_with_bars": sorted(with_bars - set(requested)),
        "peak_trades_per_minute": _peak_trades_per_minute(bars_by_symbol),
        "late_trades": None,
        "late_trades_reason": (
            "the late trade count is held by the running collector and written "
            "when it stops at the CRITERIA.md [collector] stop_time, which is "
            "after this packet is built"
        ),
    }


def observed_collector_window(
    bars_by_symbol: dict[str, list[dict[str, Any]]], now: dt.datetime,
    collector_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The window the collector actually covered, against the one it was given.

    The scheduled window is a fact about CRITERIA.md; the observed window is a
    fact about this morning. They differ whenever the collector started late,
    died early, or lost the socket in the middle, and until now that only
    showed up in a status record the following day. A morning where the tape
    stops at 08:10 is visible here, in the packet, on the morning it happens.

    Silence at the end is the one that matters and is reported as its own
    number: minutes_since_last_bar is the distance from the newest bar in the
    whole file to the scan clock, so a socket that dropped at 08:10 reads as
    35 rather than as a slightly short window.
    """
    minutes = [
        int(bar["minute_epoch"])
        for bars in bars_by_symbol.values()
        for bar in bars
        if bar.get("minute_epoch") is not None
    ]
    scheduled_start = _CRIT.clock_text("collector", "start_time")
    scheduled_stop = _CRIT.clock_text("collector", "stop_time")

    # Replay is reported BESIDE the window, never inside it. The observed
    # window is the tape this morning; the replay span is what the file also
    # contains and what a previous version of this collector would have folded
    # into that window. Collapsing them is the defect: on 2026-08-18 the oldest
    # row in the premarket file was stamped 15:59 the previous afternoon, and a
    # single first_bar_et would have reported the collector as having covered
    # from then.
    stats = collector_stats or {}
    replay = {
        "replay_rows": stats.get("replay_rows"),
        "replay_volume": stats.get("replay_volume"),
        "replay_first_et": stats.get("replay_first_et"),
        "contains_replay": bool(stats.get("replay_rows")),
    }

    if not minutes:
        return {
            "scheduled_start_et": scheduled_start,
            "scheduled_stop_et": scheduled_stop,
            "first_bar_et": None,
            "last_bar_et": None,
            "minutes_since_last_bar": None,
            "reason": "the collector file holds no bars at all",
            **replay,
        }

    first = ettime.from_epoch_s(min(minutes))
    last = ettime.from_epoch_s(max(minutes))
    return {
        **replay,
        "scheduled_start_et": scheduled_start,
        "scheduled_stop_et": scheduled_stop,
        "first_bar_et": ettime.stamp(first),
        "last_bar_et": ettime.stamp(last),
        "started_late_minutes": round(
            (first - ettime.at_hm(now.date(),
                                  _CRIT.clock("collector", "start_time"))
             ).total_seconds() / 60.0, 1),
        "minutes_since_last_bar": round((now - last).total_seconds() / 60.0, 1),
    }


def _peak_trades_per_minute(
    bars_by_symbol: dict[str, list[dict[str, Any]]]
) -> int | None:
    """The busiest minute of the morning, summed across every symbol.

    Read off the bars, which already carry a trade count per minute, so this
    is a measurement of what the socket delivered rather than a new counter in
    the collector's receive loop.
    """
    per_minute: dict[int, int] = {}
    for bars in bars_by_symbol.values():
        for bar in bars:
            try:
                minute = int(bar["minute_epoch"])
            except (KeyError, TypeError, ValueError):
                continue
            per_minute[minute] = per_minute.get(minute, 0) + int(bar.get("trades") or 0)
    return max(per_minute.values()) if per_minute else None


def market_snapshot(
    api: eodhd.EodhdClient, packet: Packet, bars_by_symbol: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Last and change versus prior close for the index and macro line.

    The collector answers first, for the same reason it answers for candidates:
    the /real-time family serves the last COMPLETED session, so at 08:45 its
    close is yesterday's close and its previousClose is the day before that.
    Reading it here is what put "SPY up 0.70 percent" in the 2026-08-14 report
    when 0.70 percent was yesterday's move. See DECISIONS.md 2026-08-14.

    The eight context tickers are subscribed every morning, so the index and
    commodity rows come from the collector. Government bonds and the dollar
    index are not subscribed and have no premarket tape here, so they fall back
    to the end of day feed and the row says so: source 'eod' with
    prior_session_only true, which the vintage check reads as a row that is
    honestly labelled stale rather than one silently claiming to be current.
    """
    mapping = _CRIT.pair_map("scan_snapshot", "snapshot")
    proxies = {}
    try:
        proxies = _CRIT.pair_map("scan_snapshot", "proxy")
    except criteria.CriteriaError:
        pass

    today = ettime.today_et()
    rows: list[dict[str, Any]] = []
    for label in list(mapping):
        symbol = mapping[label]
        row: dict[str, Any] = {
            "label": label,
            "symbol": symbol,
            "last": None,
            "prior_close": None,
            "change": None,
            "change_pct": None,
            "source": None,
            "as_of": None,
            "prior_session_only": None,
        }
        if label.lower() in proxies:
            row["proxy_note"] = proxies[label.lower()]

        bars, eod_error = api.eod(symbol, start=today - dt.timedelta(days=15), end=today)
        completed = [
            b for b in (bars or []) if ettime.parse_date(str(b.get("date"))) < today
        ]
        if eod_error or not completed:
            packet.gap(f"market snapshot {label} ({symbol}) unavailable: "
                       f"{eod_error or 'no completed end of day rows'}")
            rows.append(row)
            continue

        collector_last, collector_at = _collector_last(bars_by_symbol.get(symbol, []))
        if collector_last is not None:
            row.update({
                "last": collector_last,
                "prior_close": _as_float(completed[-1].get("close")),
                "prior_session_date": completed[-1].get("date"),
                "source": "collector",
                "as_of": collector_at,
                "prior_session_only": False,
            })
        else:
            row.update({
                "last": _as_float(completed[-1].get("close")),
                "prior_close": _as_float(completed[-2].get("close"))
                if len(completed) > 1 else None,
                "prior_session_date": completed[-1].get("date"),
                "source": "eod",
                "as_of": completed[-1].get("date"),
                "prior_session_only": True,
            })

        if row["last"] is not None and row["prior_close"]:
            row["change"] = round(row["last"] - row["prior_close"], 6)
            row["change_pct"] = round(
                (row["last"] - row["prior_close"]) / row["prior_close"] * 100.0, 4
            )
        rows.append(row)
    return rows


# ------------------------------------------------------- 2. final candidates

def pool_candidates(
    watchlist: dict[str, Any], packet: Packet
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The names the collector was subscribed to, carrying their pool provenance.

    Membership is no longer rebuilt here. It cannot be: the collector is the
    only source of today's premarket tape and it only has bars for what
    discover subscribed to at 07:20, so a name discovered at 08:45 could not be
    priced anyway. What this pass does instead is RANK, on the gap actually
    measured from the collector, which is done further down once there is a
    price to measure.

    Until 2026-08-14 this function made a fresh bulk /real-time call and ranked
    the universe by its gap. That endpoint serves the last completed session,
    so the ranking was of yesterday's movers. Nothing in the morning path calls
    it now. The pool tier that put each name here is carried through as a
    recorded field, never as an ordering, because a prior about who might move
    must not reach the report looking like a finding.
    """
    rows = [r for r in watchlist.get("symbols", []) if r.get("symbol")]
    subscribed = [r for r in rows if r.get("subscribed", True)]

    candidates: list[dict[str, Any]] = []
    for row in subscribed:
        candidates.append({
            "symbol": str(row["symbol"]).upper(),
            "pool_source": row.get("pool_source") or [],
            "pool_tier": row.get("pool_tier"),
            "pool_tier_reason": row.get("pool_tier_reason"),
            "pool_rank": row.get("pool_rank"),
            "pool_evidence": row.get("pool_evidence") or {},
            # Ranking only. The published prior_close comes from
            # attach_daily_history together with prior_high, out of one record.
            "pool_prior_close": row.get("pool_prior_close"),
            "avg_dollar_volume_20d": row.get("avg_dollar_volume_20d"),
        })

    provenance = {
        "membership": "the names discover subscribed the collector to at 07:20",
        "pool_size": len(rows),
        "subscribed": len(subscribed),
        "not_subscribed": len(rows) - len(subscribed),
        "watchlist_generated_at": watchlist.get("generated_at"),
        "selection_method": watchlist.get("selection_method"),
        "pool_sources": watchlist.get("pool_sources"),
    }
    if watchlist.get("missing"):
        packet.gap("watchlist.json is missing, so there is no subscribed list and "
                   "no candidate can be built")
    elif not subscribed:
        # A watchlist that exists and subscribes nobody is not the same failure
        # as one that is not there, and until now only the second said
        # anything. The first left a packet with zero candidates and an empty
        # gaps_to_fill, so the report would have carried empty tables with no
        # sentence explaining them, which is the one thing this project's
        # rule about missing evidence forbids.
        packet.gap(
            f"watchlist.json was written at {watchlist.get('generated_at')} and "
            f"marks none of its {len(rows)} pool row(s) subscribed, so the "
            "collector was asked for nothing and there is no candidate to "
            "price. The report's tables are empty for that reason, not because "
            "the market was quiet."
        )
    print(f"scan: {len(subscribed)} subscribed names from a pool of {len(rows)}")
    return candidates, provenance


def rank_by_measured_gap(
    candidates: list[dict[str, Any]], packet: Packet, keep: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Order by the gap actually measured this morning, then cut to keep.

    This is the only ranking in the system that uses a number from today. The
    pool tier decided who got listened to; what they did is decided here, and
    a tier 5 recent runner with the morning's biggest gap ranks first.

    The gap used for ranking is provisional, measured against the prior close
    the pool carried from discover's bulk read. The published gap is recomputed
    in attach_gap from the authoritative prior close, so the two can differ in
    the last decimal without either being wrong.
    """
    price_rule = _CRIT.rule("discovery", "price")
    gap_rule = _CRIT.rule("discovery", "gap_pct")

    ranked: list[dict[str, Any]] = []
    below_floor = 0
    unrankable = 0
    for candidate in candidates:
        price = candidate.get("price")
        prior_close = candidate.get("pool_prior_close")
        if price is None or not prior_close:
            candidate["provisional_gap_pct"] = None
            unrankable += 1
            continue
        gap = (price - prior_close) / prior_close * 100.0
        candidate["provisional_gap_pct"] = round(gap, 4)
        if not price_rule.test(price) or not gap_rule.test(abs(gap)):
            below_floor += 1
            continue
        ranked.append(candidate)

    ranked.sort(key=lambda r: abs(r["provisional_gap_pct"]), reverse=True)
    kept = ranked[:keep]
    if unrankable:
        packet.gap(
            f"{unrankable} subscribed name(s) could not be ranked: no premarket "
            "price from the collector, or no prior session close carried by the pool"
        )
    stats = {
        "subscribed_considered": len(candidates),
        "cleared_floors": len(ranked),
        "kept": len(kept),
        "below_floor": below_floor,
        "unrankable": unrankable,
        "floors": {"price": price_rule.describe(), "gap_pct_absolute": gap_rule.describe()},
        "ranked_on": "the premarket gap measured from the collector, not the pool tier",
    }
    print(f"scan: {len(ranked)} of {len(candidates)} subscribed names cleared the "
          f"floors on their measured gap, keeping the top {len(kept)}")
    return kept, stats


# ----------------------------------- 3 and 4. enrichment and window provenance

def attach_quotes(
    api: eodhd.EodhdClient, candidates: list[dict[str, Any]], packet: Packet
) -> None:
    quotes, error = api.quote_delayed([c["symbol"] for c in candidates])
    if error:
        packet.gap(f"delayed quotes incomplete: {error}")
    quotes = quotes or {}
    for candidate in candidates:
        quote = quotes.get(candidate["symbol"]) or {}
        if not quote:
            packet.gap(f"{candidate['symbol']} has no delayed quote, "
                       "so market cap and the 200 day average are missing")
        candidate["quote"] = {
            "ethVolume": _as_float(quote.get("ethVolume")),
            "ethTime": quote.get("ethTime"),
            "ethTime_et": ettime.stamp(ettime.from_epoch_ms(quote.get("ethTime")))
            if quote.get("ethTime") else None,
            "marketCap": _as_float(quote.get("marketCap")),
            "sharesFloat": _as_float(quote.get("sharesFloat")),
            # Kept only so float rotation can sanity check the float against
            # it. A float far below shares outstanding, or above it, is a
            # vendor artifact rather than a small free float, and without the
            # second number there is no way to tell one from the other.
            "sharesOutstanding": _as_float(quote.get("sharesOutstanding")),
            "averageVolume": _as_float(quote.get("averageVolume")),
            "twoHundredDayAveragePrice": _as_float(quote.get("twoHundredDayAveragePrice")),
            "previousClosePrice": _as_float(quote.get("previousClosePrice")),
            "name": quote.get("name") or quote.get("companyStandardName"),
            "sector": quote.get("sector"),
        }


def attach_daily_history(
    api: eodhd.EodhdClient, candidates: list[dict[str, Any]], packet: Packet
) -> None:
    """Prior session close, high and 20 day average volume, from the end of day feed.

    prior_close and prior_high are read from THE SAME record and cannot be
    sourced separately. When they came from different places, one from the bulk
    feed's previousClose and one from this history, they silently drifted a
    session apart: on 2026-08-14 six candidates carried a prior_high below
    their prior_close, which cannot happen inside one OHLC bar, and the
    require_above_prior_high gate compared a session's close against its own
    high and could never pass. Aligned by construction here, that whole class
    of error is unreachable rather than merely unlikely.
    """
    lookback = _CRIT.integer("universe", "lookback_sessions")
    today = ettime.today_et()
    start = today - dt.timedelta(days=lookback * 2 + 10)

    def unknown(candidate: dict[str, Any]) -> None:
        candidate["prior_close"] = None
        candidate["prior_high"] = None
        candidate["prior_session_date"] = None
        candidate["avg_volume_20d"] = None

    for candidate in candidates:
        bars, error = api.eod(candidate["symbol"], start=start, end=today)
        if error or not bars:
            packet.gap(f"{candidate['symbol']} end of day history unavailable: "
                       f"{error or 'no rows'}. Prior session close, prior day high "
                       "and 20 day average volume are null.")
            unknown(candidate)
            continue

        # Today's own row is excluded. The prior day high means yesterday.
        completed = [b for b in bars if ettime.parse_date(str(b.get("date"))) < today]
        if not completed:
            packet.gap(f"{candidate['symbol']} has no completed session before today")
            unknown(candidate)
            continue

        prior = completed[-1]
        candidate["prior_close"] = _as_float(prior.get("close"))
        candidate["prior_high"] = _as_float(prior.get("high"))
        candidate["prior_session_date"] = prior.get("date")
        candidate["prior_source"] = (
            f"one end of day record dated {prior.get('date')}, close and high together"
        )
        volumes = [_as_float(b.get("volume")) for b in completed[-lookback:]]
        volumes = [v for v in volumes if v is not None]
        candidate["avg_volume_20d"] = round(sum(volumes) / len(volumes), 2) if volumes else None


def attach_premarket_path(
    candidates: list[dict[str, Any]],
    watchlist: dict[str, Any],
    packet: Packet,
    bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> None:
    """Premarket high, low and VWAP, from the collector snapshot and nowhere else.

    The bars come from a snapshot copy taken by build_packet, never from the
    live file, because the collector is still appending to it at 08:45.

    A candidate that was not on the watchlist was never subscribed, so the
    collector has nothing for it. That is recorded as collector_covered false
    with nulls, not filled in from a quote, because it started gapping after
    the collector had already chosen what to listen to.
    """
    watchlist_symbols = set(discover.subscribed_symbols(watchlist))
    collector_start = _CRIT.clock_text("collector", "start_time")

    if not bars_by_symbol:
        packet.gap(
            f"the collector file {collect_premarket.bar_path().name} is missing or empty. "
            "Every premarket high, low and VWAP is null, and premarket RVOL is null with it."
        )

    for candidate in candidates:
        symbol = candidate["symbol"]
        bars = bars_by_symbol.get(symbol, [])
        on_watchlist = symbol in watchlist_symbols

        candidate["collector_covered"] = bool(bars) and on_watchlist
        candidate["on_watchlist"] = on_watchlist
        candidate["bars_collected"] = len(bars)

        if not bars or not on_watchlist:
            candidate["pm_high"] = None
            candidate["pm_low"] = None
            candidate["pm_vwap"] = None
            candidate["pm_volume_collected"] = None
            candidate["pm_window_start"] = None
            candidate["pm_window_end"] = None
            candidate["pm_window_starts_late"] = None
            if not on_watchlist:
                candidate["pm_reason"] = (
                    "not on watchlist.json, so the collector never subscribed to it. "
                    "It started gapping after the collector chose its symbols."
                )
            else:
                candidate["pm_reason"] = (
                    "on the watchlist but the collector recorded no bars for it"
                )
            continue

        volume = sum(float(b.get("v") or 0) for b in bars)
        price_volume = sum(float(b.get("pv") or 0) for b in bars)
        candidate["pm_high"] = round(max(float(b["h"]) for b in bars), 4)
        candidate["pm_low"] = round(min(float(b["l"]) for b in bars), 4)
        candidate["pm_vwap"] = round(price_volume / volume, 4) if volume else None
        candidate["pm_volume_collected"] = volume
        candidate["pm_window_start"] = ettime.stamp(
            ettime.from_epoch_s(min(b["minute_epoch"] for b in bars))
        )
        candidate["pm_window_end"] = ettime.stamp(
            ettime.from_epoch_s(max(b["minute_epoch"] for b in bars) + 60)
        )
        candidate["pm_reason"] = None

        window_start_hhmm = candidate["pm_window_start"][11:16]
        # The intended start is recorded BESIDE the observed one rather than
        # standing in for it. pm_window_start has always been derived from the
        # bars, but nothing beside it said what it was being judged against, so
        # a reader could not see the two disagree without knowing CRITERIA by
        # heart. On 2026-08-19 the collector was an hour late and every field
        # describing the window still quoted 07:20.
        candidate["pm_window_intended_start"] = collector_start
        candidate["pm_window_start_source"] = (
            "the first minute this candidate actually has a bar for, not the "
            "configured collector start"
        )
        candidate["pm_window_starts_late"] = window_start_hhmm > collector_start


# --------------------------------- 4b. pricing, from the collector and nowhere else

def price_from_collector(
    candidates: list[dict[str, Any]],
    packet: Packet,
    bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> None:
    """Today's price and premarket volume, from the collector file and nowhere else.

    Runs straight after attach_premarket_path, before a single REST call is
    spent on enrichment, so that a candidate with no collector coverage can be
    dropped before it costs a quote and a history call.
    """
    now = ettime.now_et()
    for candidate in candidates:
        bars = bars_by_symbol.get(candidate["symbol"], [])
        price, price_at = _collector_last(bars)
        candidate["price"] = round(price, 4) if price is not None else None
        candidate["price_time"] = price_at
        candidate["price_source"] = "collector" if price is not None else None
        # How stale the print is against the scan clock. Recorded for every
        # candidate whether or not it passes, because "the price was 40
        # seconds old" and "the price was 83 minutes old" are different
        # reports even when both are inside today's premarket window.
        candidate["price_age_seconds"] = _price_age_seconds(price_at, now)
        # Computed once, in attach_premarket_path, off these same bars.
        candidate["pm_volume"] = candidate.get("pm_volume_collected")


def _price_age_seconds(price_at: Any, now: dt.datetime) -> float | None:
    if not price_at:
        return None
    try:
        when = dt.datetime.fromisoformat(str(price_at))
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=ettime.ET)
    return round((now - when).total_seconds(), 1)


def drop_stale_prices(
    candidates: list[dict[str, Any]], packet: Packet
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop candidates whose last print is older than the scan can stand behind.

    Counted separately from dropped_no_coverage because the two are different
    failures with different fixes. No coverage means the collector never heard
    the name and the answer is a subscription slot. A stale price means the
    collector heard it and then stopped, and the answer is to find out why the
    socket went quiet.

    The vintage gate cannot catch this: a print from 07:22 is genuinely from
    today's premarket window and passes every check it makes. This is the case
    a collector killed at 08:10 produces, and until now the packet published
    those prices as current.
    """
    limit = _CRIT.number("price_age", "max_price_age_seconds")
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for candidate in candidates:
        age = candidate.get("price_age_seconds")
        if age is not None and age > limit:
            dropped.append({
                "symbol": candidate["symbol"],
                "reason": (f"the last collector print is {age:,.0f}s old at the scan "
                           f"clock, past the {limit:,.0f}s limit in "
                           f"{config.CRITERIA_PATH.name} [price age]. It is inside "
                           "today's premarket window, so the vintage check passes, "
                           "but it is not this morning's price."),
                "price_age_seconds": age,
                "price_time": candidate.get("price_time"),
                "pool_tier": candidate.get("pool_tier"),
                "pool_source": candidate.get("pool_source") or [],
            })
            continue
        kept.append(candidate)

    if dropped:
        packet.gap(
            f"{len(dropped)} candidate(s) dropped for a stale premarket price, "
            "collected but too old to publish as this morning's: "
            + ", ".join(f"{d['symbol']} ({d['price_age_seconds']:,.0f}s)"
                        for d in dropped)
        )
    return kept, dropped


def attach_gap(candidates: list[dict[str, Any]]) -> None:
    """This morning's premarket price against the prior session close.

    The gap is recomputed here rather than carried over from selection. The
    selection gap was measured between two completed sessions and is a fact
    about yesterday; the published gap is this morning's premarket price
    against the prior session close, which is what the word gap means in this
    report and what CRITERIA.md's day and swing screens are written against.
    """
    for candidate in candidates:
        price = candidate.get("price")
        prior_close = candidate.get("prior_close")
        if price is None or not prior_close:
            candidate["gap_pct"] = None
            candidate["gap_reason"] = (
                "no premarket price from the collector"
                if price is None
                else "no prior session close to measure the gap against"
            )
            continue
        candidate["gap_pct"] = round((price - prior_close) / prior_close * 100.0, 4)
        candidate["gap_reason"] = None


def drop_uncovered(
    candidates: list[dict[str, Any]], packet: Packet
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split off the candidates the collector never subscribed to.

    Once price comes from the collector, a name the collector was not listening
    to has no price at all, and there is no honest way to publish it: the only
    other number available is the stale one this whole change exists to remove.
    Substituting it would be exactly the defect, reintroduced through the
    exception path. So the candidate leaves the packet's candidate list, is
    named with its reason in dropped_no_coverage, and never reaches picks.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("price") is not None:
            kept.append(candidate)
            continue
        dropped.append({
            "symbol": candidate["symbol"],
            "reason": candidate.get("pm_reason")
            or "the collector recorded no bars for it, so it has no premarket price",
            # Why this name was in front of the collector at all. These come
            # from the watchlist row and discover really writes them, which
            # selection_gap_pct did not: it was read here until 2026-08-14 and
            # no producer had written it since discover stopped computing a
            # selection gap at d224837. A key with no writer reads as missing
            # evidence rather than as a field nobody fills, and this project
            # has one rule about missing evidence, so it cannot afford fields
            # that fake it.
            "pool_tier": candidate.get("pool_tier"),
            "pool_source": candidate.get("pool_source") or [],
        })
    if dropped:
        packet.gap(
            f"{len(dropped)} candidate(s) dropped for having no collector coverage and "
            "therefore no premarket price, rather than being published at a stale one: "
            + ", ".join(f"{d['symbol']} ({d['reason']})" for d in dropped)
        )
    return kept, dropped


# ------------------------------------------------------- 5. premarket RVOL

def attach_premarket_rvol(
    candidates: list[dict[str, Any]], packet: Packet, cutoff: str
) -> None:
    """Collector premarket volume divided by the cached baseline median.

    Never full day relative volume. If the denominator is not trustworthy the
    answer is null and the reason is recorded, because a number computed off the
    wrong denominator is worse than no number.

    The numerator used to be the delayed quote's ethVolume. It cannot be: that
    field describes the previous extended session until the vendor rolls it,
    which measurement on 2026-08-14 put after 08:45 and before 08:56. At 08:45
    it gave ARX 20,744,130 shares, which was yesterday's post market, against a
    premarket median of 23.5 shares, for an RVOL of 882,728. The collector is
    the only source of today's premarket volume on this plan, so it is the
    numerator, matching the rule that already governs premarket high, low and
    VWAP.

    One asymmetry is recorded rather than hidden. The baseline accumulates from
    CRITERIA [baseline] session_start, 04:00, while the collector starts at
    07:20, so the numerator covers a shorter window than the denominator and
    the ratio is a LOWER BOUND. That direction is the safe one: it can only
    understate relative volume, so it can only withhold a candidate from a
    screen, never smuggle one in. Closing the gap needs a second baseline keyed
    to the collector window; see DECISIONS.md 2026-08-14.
    """
    numerator_window = _CRIT.clock_text("collector", "start_time")
    denominator_window = _CRIT.clock_text("baseline", "session_start")
    with store.session() as connection:
        store.init(connection)
        for candidate in candidates:
            candidate["pm_rvol"] = None
            candidate["pm_rvol_reason"] = None
            candidate["baseline"] = None

            pm_volume = candidate.get("pm_volume")
            row = baseline.get(candidate["symbol"], cutoff, connection)
            usable, why_not = baseline.usable_for_rvol(row)
            if row:
                candidate["baseline"] = {
                    "cutoff_hhmm": row["cutoff_hhmm"],
                    "median_volume": row["median_volume"],
                    "sessions_used": row["sessions_used"],
                    "computed_at": row["computed_at"],
                }

            if not candidate.get("collector_covered"):
                candidate["pm_rvol_reason"] = (
                    "the collector did not cover this name, so there is no evidence "
                    "for the premarket window and no RVOL is published"
                )
                continue
            if not usable:
                candidate["pm_rvol_reason"] = why_not
                packet.gap(f"{candidate['symbol']} premarket RVOL is null: {why_not}")
                continue
            if pm_volume is None:
                candidate["pm_rvol_reason"] = (
                    "the collector recorded no premarket volume for this name"
                )
                packet.gap(f"{candidate['symbol']} premarket RVOL is null: "
                           "no collector premarket volume")
                continue

            candidate["pm_rvol"] = round(pm_volume / row["median_volume"], 4)
            candidate["pm_rvol_basis"] = {
                "numerator": pm_volume,
                # The window this numerator COVERS, which is the candidate's
                # own first bar, not the hour the collector was scheduled for.
                # Quoting the schedule here asserted a 07:20 numerator on a
                # morning whose windows began at 08:14 and later.
                "numerator_source": (
                    f"collector, from {candidate.get('pm_window_start') or 'an unrecorded start'}"
                    f" (scheduled {numerator_window} ET)"
                ),
                "denominator": row["median_volume"],
                "denominator_source": (
                    f"baseline median, accumulated from {denominator_window} ET "
                    f"to the {cutoff} cutoff over {row['sessions_used']} sessions"
                ),
                "is_lower_bound": numerator_window > denominator_window,
            }

    _gap_for_lower_bound_rvol(candidates, packet, numerator_window,
                              denominator_window)


def _gap_for_lower_bound_rvol(
    candidates: list[dict[str, Any]], packet: Packet,
    numerator_window: str, denominator_window: str,
) -> None:
    """Say in gaps_to_fill which RVOLs can only understate, and by which of two causes.

    The asymmetry is recorded per candidate in pm_rvol_basis and was reaching
    no reader. A lower bound is not a low reading, and a report describing RVOL
    across the set without the distinction describes a data gap as a quiet
    tape. gaps_to_fill is where it goes because that is the one list the
    template requires the disclaimer to surface: on 2026-08-19 the disclaimer
    named only the two null RVOLs, which told the reader the other ten were
    complete when every one of them was a lower bound.

    Two causes, not one, and until 2026-08-20 this said only the first.

    The WINDOW cause is arithmetic: the numerator starts at the collector's
    start_time and the denominator at the baseline's session_start, so the
    ratio is bounded below by construction and no measurement is needed to
    know it.

    The FEED cause is empirical and is the bigger of the two. The numerator
    comes from the collector socket and the denominator from the vendor's
    intraday endpoint, so whatever those two feeds disagree by passes straight
    into the ratio. verify_against_intraday measures exactly that disagreement
    on identical minutes, the nightly writes it, and on 2026-08-20 it read
    90.0 percent across 73 symbols with none inside one percent. The morning
    report of that date told its reader RVOL was a lower bound and named only
    the window, which describes a ten-fold instrument error as an arithmetic
    detail. See the volume check note in CRITERIA.md.

    Silent about the bound when nothing is bounded, because a gaps list that
    always carries a sentence is a gaps list nobody reads. NOT silent about the
    feed, which is a property of the collector rather than of any candidate and
    is reported whether or not a single RVOL survived the morning.
    """
    bounded = [c["symbol"] for c in candidates
               if (c.get("pm_rvol_basis") or {}).get("is_lower_bound")]
    if bounded:
        packet.gap(
            "premarket RVOL understates for these candidates and must be called a "
            "lower bound wherever it is discussed: the numerator covers the "
            f"collector window from {numerator_window} ET while the denominator is "
            f"a baseline accumulated from {denominator_window} ET: "
            + ", ".join(bounded)
        )


def volume_check(session_date: str, packet: Packet) -> dict[str, Any] | None:
    """Read the nightly's collector-versus-vendor measurement and gap it.

    Costs nothing: the measurement is taken by the nightly and written to
    runs/<date>/verify_intraday.json, and this reads the newest one. Returned
    for the packet and stated in gaps_to_fill, because the size of this number
    decides how much the RVOL column is worth and the reader cannot see it
    anywhere else.

    An absent or stale check is itself a gap. An unmeasured feed is not a clean
    one, and a morning that says nothing about it reads exactly like a morning
    that measured zero.
    """
    check = collect_premarket.latest_volume_check(session_date)
    if check is None:
        packet.gap(
            "the collector volume check has never been written, so the "
            "disagreement between the collector socket that supplies the "
            "premarket RVOL numerators and the vendor intraday feed that "
            "supplies the denominators is UNMEASURED this morning. That is "
            "not the same as small. Run the nightly backfill to take the "
            "measurement."
        )
        return None

    detail = (
        f"the collector was last measured against the vendor's one minute bars "
        f"on identical minutes for {check['day']}: median absolute difference "
        f"{check['median_abs_pct']:.1f} percent across {check['compared']} "
        f"symbol(s), {check['within_one_percent']} of them within one percent"
    )
    if check["stale"]:
        packet.gap(
            f"the collector volume check is {check['age_days']} days old, past "
            f"the {check['max_age_days']} day limit in CRITERIA.md [collector], "
            f"so this morning's feed is effectively unmeasured. Last reading: "
            f"{detail}."
        )
    else:
        packet.gap(
            f"premarket RVOL and premarket float rotation both divide a "
            f"collector-sourced numerator by a vendor-sourced denominator, and "
            f"{detail}. That disagreement passes straight into the ratios in "
            "this packet and is LARGER than the window shortfall reported "
            "separately. An RVOL below is understated by about that much "
            "again, and a screen decided on RVOL this morning should be read "
            "as an instrument reading rather than as a fact about the tape."
        )
    return check


def rvol_only_day_failures(candidates: list[dict[str, Any]], packet: Packet) -> list[str]:
    """Candidates the day screen rejected on premarket RVOL and nothing else.

    The companion to volume_check above, and the reason it is worth carrying.
    A measured feed shortfall is an abstraction until somebody says which names
    it cost. On 2026-08-20, seven of twelve candidates cleared price, gap,
    market cap and the prior session high and failed on RVOL alone, against a
    numerator the nightly had measured at roughly a tenth of the vendor's for
    the same minutes. The report published "the day screen produced nothing
    today" as an observation about the market.

    Computed here rather than left to the model for the reason screen_tally
    argues at length: it is a count with one correct answer, and the model was
    getting counts wrong in prose.
    """
    blocked = [
        c["symbol"] for c in candidates
        if (c.get("day_failed_conditions") or []) == ["premarket_rvol"]
    ]
    if blocked:
        packet.gap(
            f"{len(blocked)} of {len(candidates)} candidates failed the day "
            "screen on premarket RVOL alone, having cleared the other day "
            "conditions: "
            + ", ".join(blocked)
            + ". Read that against the collector volume check in this packet: "
            "if the numerator understates, these are the tickers it cost, and "
            "an empty day watchlist is then an instrument reading rather than "
            "a quiet market."
        )
    return blocked


def attach_float_rotation(candidates: list[dict[str, Any]], packet: Packet) -> None:
    """Collector premarket volume divided by shares float.

    The second volume measure, and the reason it exists is the first one's
    blind spot. RVOL divides by a cached baseline, so it is null for any name
    that has never been baselined, which is every name on its first appearance
    and every name the weekly universe rebuild has just admitted. Those are not
    marginal names: a name showing up for the first time is often exactly the
    one worth looking at. Float rotation needs no history at all, so it is
    computable from the first minute a name trades, and the two are scored as
    alternatives filling one slot rather than as two requirements.

    The numerator is the same collector volume RVOL uses, so the same lower
    bound applies and is flagged the same way: the collector starts at 07:20
    and the premarket opens at 04:00, so this understates rotation over the
    full session. That direction is the safe one, as it can only hold a
    candidate down a band, never lift it up one.

    The denominator has no window, which is the whole point, but it does have a
    trustworthiness problem of its own. A float reported far below shares
    outstanding is a vendor artifact rather than a genuinely tiny free float,
    and a float above shares outstanding is impossible. Both are rejected with
    the reason recorded rather than divided by. That pair of checks needs a
    usable sharesOutstanding to check against, and the three ways a quote can
    fail to carry one are not one case. A missing sharesOutstanding and a zero
    one are both a share count the vendor never supplied, so the float faces
    the absolute share floor in place of the ratios. A negative one is a share
    count that cannot exist, so the quote is corrupt rather than incomplete and
    the float in it is refused outright. Every route that reaches the
    denominator question ends in a recorded reason AND a gap, so no float gets
    past every test and no such name is nulled in silence. The two routes above
    that question, a name the collector never covered and a name it covered
    without volume, follow attach_premarket_rvol exactly: the volume one gaps,
    and the coverage one does not, because collector_coverage already reports
    the uncovered names as a set and gapping each of them again would say the
    same thing twice. See CRITERIA.md [Float rotation] for the floors and what
    they were measured against.
    """
    numerator_window = _CRIT.clock_text("collector", "start_time")
    true_open = _CRIT.clock_text("baseline", "session_start")
    min_float = _CRIT.number("float_rotation", "min_shares_float")
    min_ratio = _CRIT.number("float_rotation", "min_float_to_shares_outstanding")
    max_ratio = _CRIT.number("float_rotation", "max_float_to_shares_outstanding")

    for candidate in candidates:
        candidate["pm_float_rotation"] = None
        candidate["pm_float_rotation_reason"] = None
        candidate["pm_float_rotation_basis"] = None

        quote = candidate.get("quote") or {}
        share_float = _as_float(quote.get("sharesFloat"))
        outstanding = _as_float(quote.get("sharesOutstanding"))
        pm_volume = candidate.get("pm_volume")

        if not candidate.get("collector_covered"):
            candidate["pm_float_rotation_reason"] = (
                "the collector did not cover this name, so there is no evidence "
                "for the premarket window and no float rotation is published"
            )
            continue
        if pm_volume is None:
            candidate["pm_float_rotation_reason"] = (
                "the collector recorded no premarket volume for this name"
            )
            packet.gap(f"{candidate['symbol']} float rotation is null: "
                       "no collector premarket volume")
            continue
        if share_float is None or share_float <= 0:
            candidate["pm_float_rotation_reason"] = (
                "the delayed quote carried no sharesFloat, so there is no denominator"
            )
            packet.gap(f"{candidate['symbol']} float rotation is null: no sharesFloat "
                       "in the delayed quote")
            continue
        # A negative sharesOutstanding is refused right here, before any of the
        # checks below get a look at it, because it is not a cross check that
        # happens to be missing, it is a quote that has reported something no
        # company can have. A record that carries a negative share count has
        # told us nothing trustworthy about this name, and that includes the
        # sharesFloat sitting beside it, so there is no honest number to
        # publish from it.
        #
        # Refusing is also what the code did before 2026-08-17, though by
        # accident rather than on purpose, and the accident is worth writing
        # down so nobody removes the guard a second time. The max ratio check
        # below then read "if outstanding and share_float > outstanding *
        # max_ratio". For a negative outstanding that product is negative, so
        # every positive float exceeded it and the quote was refused as "float
        # above shares outstanding". When that condition was rewritten to test
        # for a real share count, the accident went with it: a sharesFloat of
        # 20,000,000 beside a sharesOutstanding of -25,000,000 started
        # publishing a rotation of 0.0125, with the impossible -25,000,000
        # carried into packet.json beside it as though it were a fact. This
        # line puts the refusal back deliberately, and names the actual defect
        # rather than the arithmetic one the old truthiness test reported.
        if outstanding is not None and outstanding < 0:
            candidate["pm_float_rotation_reason"] = (
                f"sharesOutstanding is reported as {outstanding:,.0f}, a negative "
                "share count, so the quote is corrupt rather than merely missing a "
                "cross check and the sharesFloat in it is not divided by"
            )
            packet.gap(f"{candidate['symbol']} float rotation is null: negative "
                       "shares outstanding")
            continue
        # sharesOutstanding is a cross check only when it is a real share count,
        # so it is tested here the way the sharesFloat guard further above
        # already tests its own field: present AND strictly positive, rather
        # than merely truthy or merely not None. That guard set the standard and
        # these had not been held to it. Until 2026-08-17 the two ratio checks
        # below read "if outstanding and ...", which a sharesOutstanding of
        # exactly 0.0 skips because 0.0 is falsy, and the absolute floor read
        # "if outstanding is None", which the same 0.0 also skips because it is
        # not None. A quote carrying a zero outstanding therefore fell through
        # all three, and that is the worst case to leave unguarded rather than a
        # harmless one: rotation is premarket volume over the float, so an
        # unchecked fabricated float of a few thousand shares does not produce a
        # slightly wrong number, it produces a very large one, and the name
        # lands in the top rotation band on a denominator nothing ever looked
        # at. A zero now falls to the absolute floor, which is where a float
        # with no usable cross check has always belonged. Negatives never reach
        # this line, having been refused above.
        outstanding_usable = outstanding is not None and outstanding > 0

        if outstanding_usable and share_float > outstanding * max_ratio:
            candidate["pm_float_rotation_reason"] = (
                f"sharesFloat {share_float:,.0f} exceeds sharesOutstanding "
                f"{outstanding:,.0f}, which is impossible, so the vendor figure is "
                "not divided by"
            )
            packet.gap(f"{candidate['symbol']} float rotation is null: float above "
                       "shares outstanding")
            continue
        if outstanding_usable and share_float < outstanding * min_ratio:
            candidate["pm_float_rotation_reason"] = (
                f"sharesFloat {share_float:,.0f} is {share_float / outstanding * 100:.3f} "
                f"percent of sharesOutstanding {outstanding:,.0f}, below the "
                f"{min_ratio * 100:g} percent floor, so it reads as a vendor artifact "
                "rather than a small free float"
            )
            packet.gap(f"{candidate['symbol']} float rotation is null: float implausibly "
                       "small against shares outstanding")
            continue
        if not outstanding_usable and share_float < min_float:
            # Which kind of unusable it was is written into both the reason and
            # the gap, because a human reads both and the two cases are
            # different conversations to have with the vendor. A missing
            # sharesOutstanding is a field they did not populate for this name;
            # a zero is a field they populated with a number that cannot be a
            # share count, which says the record itself is suspect and not only
            # the float in it.
            if outstanding is None:
                no_cross_check = "there is no sharesOutstanding to check it against"
                unusable_state = "no shares outstanding"
            else:
                no_cross_check = (
                    "sharesOutstanding is reported as zero, which is not a share "
                    "count and cannot check it"
                )
                unusable_state = "shares outstanding reported as zero"
            candidate["pm_float_rotation_reason"] = (
                f"sharesFloat {share_float:,.0f} is below the {min_float:,.0f} share "
                f"floor and {no_cross_check}"
            )
            # Until 2026-08-17 this was the one refusal in the function that
            # recorded its reason and raised no gap, so the name was nulled
            # where only a reader of packet.json would ever find it. That was
            # survivable while the branch caught nothing but an unpopulated
            # field, which is the vendor's silence rather than a defect. It is
            # not survivable now that a zero outstanding lands here too: a
            # populated field holding an impossible value is exactly the kind
            # of thing gaps_to_fill exists to put in front of a human each
            # morning, and it cannot do that for a gap nobody raised.
            packet.gap(f"{candidate['symbol']} float rotation is null: sharesFloat "
                       f"below the {min_float:,.0f} share floor with "
                       f"{unusable_state}")
            continue

        # Only a real share count is published as one. A quote that carried no
        # sharesOutstanding, or carried a zero, reaches this line having been
        # cleared by the absolute floor rather than by the ratio checks, and
        # writing its absence or its 0.0 into the packet as a bare number would
        # read downstream as "this company has zero shares" rather than as
        # "there was nothing here to check against". Null is what this project
        # records for absent evidence, so null is what goes in the count field,
        # and the source line beside it carries which of the states it was and
        # what stood in for the cross check.
        if outstanding_usable:
            outstanding_source = "sharesOutstanding from the delayed quote"
        elif outstanding is None:
            outstanding_source = (
                "the delayed quote carried no sharesOutstanding, so the "
                f"{min_float:,.0f} share floor stood in for the ratio checks"
            )
        else:
            outstanding_source = (
                "the delayed quote reported sharesOutstanding as zero, which is not "
                f"a share count, so the {min_float:,.0f} share floor stood in for "
                "the ratio checks"
            )

        candidate["pm_float_rotation"] = round(pm_volume / share_float, 8)
        candidate["pm_float_rotation_basis"] = {
            "numerator": pm_volume,
            "numerator_source": f"collector, from {numerator_window} ET",
            "denominator": share_float,
            "denominator_source": "sharesFloat from the delayed quote",
            "shares_outstanding": outstanding if outstanding_usable else None,
            "shares_outstanding_source": outstanding_source,
            # True for the same reason RVOL's is: the collector starts after
            # the premarket does, so the numerator is short of the full window.
            "is_lower_bound": numerator_window > true_open,
        }


# ---------------------------------------------------------- 6. catalyst news

def _publisher_from(link: str | None) -> str | None:
    """EODHD news carries no publisher field, so it is taken from the url host.

    This is not keyword matching. It reads the domain of the link the feed gave
    us, and the packet labels it as derived so nobody mistakes it for a field
    the provider supplied.
    """
    if not link:
        return None
    host = urlparse(link).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def attach_catalysts(
    api: eodhd.EodhdClient, candidates: list[dict[str, Any]], packet: Packet
) -> None:
    """News carrying the EODHD symbol tag, over the last N hours.

    The symbol tag is the entire filter. No keyword matching, no company name
    regex, no stopword list. If the feed has nothing tagged with the symbol,
    catalyst_found is false and that is a finding, not a gap to paper over.
    """
    hours = _CRIT.integer("scan", "news_lookback_hours")
    keep = _CRIT.integer("scan", "news_keep")
    now = ettime.now_et()
    since = now - dt.timedelta(hours=hours)

    for candidate in candidates:
        rows, error = api.news(
            candidate["symbol"], start=since.date(), end=now.date()
        )
        if error:
            packet.gap(f"{candidate['symbol']} news call failed: {error}. "
                       "catalyst_found is unknown rather than false.")
            candidate["catalyst_found"] = None
            candidate["catalyst_error"] = error
            candidate["headlines"] = []
            continue

        recent: list[dict[str, Any]] = []
        for row in rows or []:
            published = row.get("date")
            when = None
            if published:
                try:
                    when = ettime.to_et(dt.datetime.fromisoformat(str(published)))
                except ValueError:
                    when = None
            if when is not None and when < since:
                continue
            # The symbol tag is the filter. Confirm the feed really tagged it.
            symbols = [str(s).upper() for s in (row.get("symbols") or [])]
            if symbols and candidate["symbol"] not in symbols:
                continue
            recent.append(
                {
                    "title": row.get("title"),
                    "publisher": _publisher_from(row.get("link")),
                    "publisher_source": "derived from the url host, the feed has no publisher field",
                    "url": row.get("link"),
                    "published_at": ettime.stamp(when) if when else published,
                    "sentiment": row.get("sentiment"),
                    "tags": row.get("tags") or [],
                }
            )

        recent.sort(key=lambda r: str(r.get("published_at") or ""), reverse=True)
        candidate["headlines"] = recent[:keep]
        candidate["catalyst_found"] = bool(recent)
        candidate["news_in_window"] = len(recent)


def attach_traps(candidates: list[dict[str, Any]], packet: Packet) -> None:
    """Is this gap up contradicted by the balance of its own headlines.

    Decided here and narrated by the report, which is the house rule and was
    not being followed. Until 2026-08-20 REPORT_TEMPLATE.md told the model that
    "a positive gap on headlines whose sentiment is negative is a trap", the
    packet carried no such field, and the model did what that sentence invites:
    it took the WORST SINGLE headline. On 2026-08-20 that published MSTR as a
    trap on "Bitcoin tops $71K as crypto rally gains momentum", which the
    vendor scored -0.914 against its own +0.963 and +0.833 that same morning,
    and FUTU as a trap on "Here are the major earnings before the open
    Thursday" at -0.422 against +0.836 and +0.691. Two vendor scoring errors
    reached a reader as statements about the market, which is the one thing
    the containment and quantifier guards do not catch: the tickers were real
    and the polarity was quoted accurately.

    So the rule reads the balance, strictly more negative than positive among
    the headlines the vendor actually scored, and the counts it decided on are
    kept next to the verdict. The vendor's polarity is the only sentiment
    source on this plan and it is unreliable per item; carrying the evidence is
    how a reader can disagree with the call.

    trap is NULL, never False, when there is nothing to weigh: no headlines,
    fewer than min_headlines_for_balance scored ones, a gap that is down or too
    small for the question to mean anything, or a news call that failed. A
    False that means "we could not look" is the failure mode this whole file
    is written against.
    """
    negative_at = _CRIT.number("traps", "negative_polarity")
    positive_at = _CRIT.number("traps", "positive_polarity")
    minimum = _CRIT.integer("traps", "min_headlines_for_balance")
    min_gap = _CRIT.number("traps", "min_gap_pct")

    flagged: list[str] = []
    for candidate in candidates:
        scored: list[float] = []
        unscored = 0
        for headline in candidate.get("headlines") or []:
            polarity = ((headline.get("sentiment") or {}).get("polarity"))
            value = _as_float(polarity)
            if value is None:
                unscored += 1
            else:
                scored.append(value)

        negatives = [v for v in scored if v <= negative_at]
        positives = [v for v in scored if v >= positive_at]
        basis = {
            "headlines_scored": len(scored),
            "headlines_unscored": unscored,
            "negative": len(negatives),
            "positive": len(positives),
            "negative_at_or_below": negative_at,
            "positive_at_or_above": positive_at,
            "mean_polarity": (round(sum(scored) / len(scored), 4) if scored else None),
            "rule": ("strictly more negative than positive headlines, not the "
                     "single worst one. See the balance note in CRITERIA.md"),
            "source": ("polarity as published by the EODHD news feed, which is "
                       "unreliable per item and is read here in aggregate for "
                       "that reason"),
        }
        candidate["trap_basis"] = basis

        gap = _as_float(candidate.get("gap_pct"))
        if candidate.get("catalyst_found") is None:
            candidate["trap"] = None
            candidate["trap_why"] = ("the news call failed, so there is no "
                                     "headline set to weigh and trap is unknown "
                                     "rather than absent")
        elif gap is None or gap < min_gap:
            candidate["trap"] = None
            candidate["trap_why"] = (
                f"a trap is a gap UP contradicted by its news; this gap is "
                f"{'null' if gap is None else format(gap, '.2f') + ' percent'}, "
                f"below the {min_gap:g} percent this question is asked above")
        elif len(scored) < minimum:
            candidate["trap"] = None
            candidate["trap_why"] = (
                f"{len(scored)} scored headline(s), below the {minimum} needed "
                "for a balance; on fewer than that the balance IS the single "
                "worst headline, which is the reading this rule exists to stop")
        elif len(negatives) > len(positives):
            candidate["trap"] = True
            candidate["trap_why"] = (
                f"gaps up {gap:.2f} percent while {len(negatives)} of "
                f"{len(scored)} scored headlines are negative at or below "
                f"{negative_at:g} against {len(positives)} positive at or above "
                f"{positive_at:g}")
            flagged.append(candidate["symbol"])
        else:
            candidate["trap"] = False
            candidate["trap_why"] = (
                f"gaps up {gap:.2f} percent and its headlines do not contradict "
                f"it: {len(negatives)} negative against {len(positives)} "
                f"positive of {len(scored)} scored")

    if flagged:
        packet.gap(
            f"{len(flagged)} of {len(candidates)} candidates gap up against "
            f"the balance of their own headlines and are traps: "
            f"{', '.join(flagged)}. The verdict is in the trap field and the "
            "counts it was decided on are in trap_basis; the report must quote "
            "those and must not re-derive a trap from a single headline's "
            "polarity."
        )


# ------------------------------------------------------ 7. economic events

def economic_events(api: eodhd.EodhdClient, packet: Packet) -> dict[str, Any]:
    """US only, high importance, today and tomorrow in ET.

    The vendor stamps this feed in UTC with no offset on the string. Until
    2026-08-20 the parse was `fromisoformat(raw).replace(tzinfo=ET)`, which
    keeps the wall clock digits and staples an ET offset onto them, so every
    event was published four hours late in daylight time and five in standard.
    It was not subtle and it was in every report: the 2026-08-19 packet carries
    Initial Jobless Claims at 12:30 ET and FOMC Minutes at 18:00 ET, against
    real release times of 08:30 and 14:00. A premarket briefing whose macro
    line moves the morning's only print from an hour before the open to after
    lunch has inverted the one thing that section is for.

    attach_catalysts had it right on the news feed, through ettime.to_et, which
    is the same call this now uses.

    The fetch window is widened a day past the ET window on purpose. The vendor
    is asked in dates and answers in UTC, so an event late in the ET evening
    carries the next UTC date; filtering after conversion is what decides
    membership, and the extra day costs nothing because it is the same call.
    """
    country = _CRIT.text("scan", "economic_country")
    days_ahead = _CRIT.integer("scan", "economic_days_ahead")
    high_terms = [
        line.lower()
        for key, line in _CRIT.section("economic_importance").pairs
        if key == "high"
    ]

    today = ettime.today_et()
    end = today + dt.timedelta(days=days_ahead)
    rows, error = api.economic_events(
        country, today, end + dt.timedelta(days=1), limit=1000)
    if error:
        packet.gap(f"economic events call failed: {error}")
        return {"events": [], "error": error}

    kept: list[dict[str, Any]] = []
    for row in rows or []:
        if str(row.get("country", "")).upper() != country.upper():
            continue
        event_type = str(row.get("type") or "")
        if not any(term in event_type.lower() for term in high_terms):
            continue
        raw_date = str(row.get("date") or "")
        try:
            # to_et, never replace(): the feed is UTC and replace() would keep
            # the digits and change their meaning. See this function's docstring.
            when = ettime.to_et(dt.datetime.fromisoformat(raw_date))
        except ValueError:
            when = None
        if when and not (today <= when.date() <= end):
            continue
        kept.append(
            {
                "time_et": ettime.stamp(when) if when else raw_date,
                "title": event_type,
                "forecast": row.get("estimate"),
                "previous": row.get("previous"),
                "actual": row.get("actual"),
                "period": row.get("period"),
            }
        )

    kept.sort(key=lambda r: str(r.get("time_et") or ""))
    print(f"scan: {len(kept)} high importance {country} events today and the next "
          f"{days_ahead} day(s)")
    return {
        "events": kept,
        "country": country,
        "window": [today.isoformat(), end.isoformat()],
        "importance_source": (
            "matched against the high importance list in CRITERIA.md, because the "
            "EODHD economic events feed has no importance field"
        ),
        "time_source": (
            "the vendor stamps this feed in UTC and every time_et above is a "
            "conversion, not a relabelling. Packets written before 2026-08-20 "
            "carry these times four hours late in daylight time and five in "
            "standard, and must not be compared against these"
        ),
    }


# ------------------------------------------------------------- 8. earnings

def earnings(
    api: eodhd.EodhdClient, candidates: list[dict[str, Any]], packet: Packet
) -> dict[str, Any]:
    """The candidates, plus notable names reporting tomorrow."""
    days_ahead = _CRIT.integer("scan", "earnings_days_ahead")
    today = ettime.today_et()
    end = today + dt.timedelta(days=days_ahead)
    symbols = [c["symbol"] for c in candidates]

    out: dict[str, Any] = {"candidates": [], "notable_tomorrow": [], "window": [
        today.isoformat(), end.isoformat()]}

    if symbols:
        rows, error = api.earnings_calendar(
            today - dt.timedelta(days=1), end, symbols=symbols
        )
        if error:
            packet.gap(f"earnings calendar for the candidates failed: {error}")
        for row in rows or []:
            out["candidates"].append(
                {
                    "symbol": row.get("code"),
                    "report_date": row.get("report_date") or row.get("date"),
                    "before_after_market": row.get("before_after_market"),
                    "estimate": row.get("estimate"),
                    "actual": row.get("actual"),
                }
            )

    rows, error = api.earnings_calendar(end, end)
    if error:
        packet.gap(f"earnings calendar for tomorrow failed: {error}")
        return out

    # Notable is defined by the universe, which is already a liquidity screen.
    try:
        universe_payload = universe.load_universe(require_fresh=False)
        notable = {
            row["symbol"]: row.get("market_cap") or 0
            for row in universe_payload.get("symbols", [])
        }
    except universe.StaleUniverseError:
        notable = {}

    tomorrow: list[dict[str, Any]] = []
    for row in rows or []:
        code = str(row.get("code") or "").upper()
        if code not in notable:
            continue
        tomorrow.append(
            {
                "symbol": code,
                "market_cap": notable[code],
                "report_date": row.get("report_date") or row.get("date"),
                "before_after_market": row.get("before_after_market"),
                "estimate": row.get("estimate"),
            }
        )
    tomorrow.sort(key=lambda r: r.get("market_cap") or 0, reverse=True)
    out["notable_tomorrow"] = tomorrow[:15]
    out["notable_definition"] = (
        "in the weekly universe, which is already a liquidity and market cap screen, "
        "ranked by market cap"
    )
    return out


# ------------------------- 9. deterministic flags and the confluence score

def classify_catalyst(
    candidate: dict[str, Any], earnings_symbols: set[str]
) -> tuple[str | None, str]:
    """Catalyst class from structured data only. Returns (class, why).

    Two sources, in order. The earnings calendar, which is a fact rather than an
    interpretation. Then the EODHD news tags, mapped through the table in
    CRITERIA.md. Headlines are never pattern matched.

    catalyst_found None means the news feed was never successfully checked
    (call failed, or skipped for quota). That is unknown, not absent: the
    class is None, the why names the real reason, and nothing downstream may
    read it as "the window was checked and empty".
    """
    class_points = {
        key: float(value) for key, value in _CRIT.pair_map("score_catalyst_class", "class").items()
    }
    tag_map = _CRIT.pair_map("score_catalyst_tags", "tag")

    if candidate["symbol"] in earnings_symbols:
        return "earnings", "on the earnings calendar in the window"

    if candidate.get("catalyst_found") is None:
        reason = candidate.get("catalyst_error") or "the news feed was never checked"
        return None, f"catalyst is unknown, not absent: {reason}"

    best_class = "none"
    best_points = -1.0
    matched_tag = None
    for headline in candidate.get("headlines") or []:
        for tag in headline.get("tags") or []:
            mapped = tag_map.get(str(tag).strip().lower().replace("-", " "))
            if not mapped:
                continue
            points = class_points.get(mapped, 0.0)
            if points > best_points:
                best_class, best_points, matched_tag = mapped, points, tag

    if matched_tag:
        return best_class, f"EODHD news tag {matched_tag!r} mapped through CRITERIA.md"
    if candidate.get("catalyst_found"):
        return "none", "news carries the symbol tag but no tag maps to a known class"
    return "none", "no news carried the symbol tag in the window"


def evaluate_eligibility(candidate: dict[str, Any]) -> None:
    """day_eligible and swing_eligible, straight from CRITERIA.md.

    Missing data never passes a condition. A null market cap is not a small
    market cap, it is an unknown one, and unknown does not clear a floor.

    Every failure is recorded twice: the sentence a human reads, and the
    CONDITION KEY screen_tally counts. Counting the sentences instead would
    work until the first time one is reworded, and the report's only
    explanation of an empty morning would silently start counting nothing.
    """
    quote = candidate.get("quote") or {}
    price = candidate.get("price")
    gap_raw = candidate.get("gap_pct")
    # None is unknown, not zero. `abs(x or 0.0)` would turn an ungapped
    # unknown into a confident "gap_pct 0.00 fails > 3", which is a claim
    # about the stock made out of a fact about the pipeline.
    gap = abs(gap_raw) if gap_raw is not None else None
    market_cap = quote.get("marketCap")
    prior_high = candidate.get("prior_high")
    sma200 = quote.get("twoHundredDayAveragePrice")

    day: list[tuple[str, str]] = []
    if gap is None:
        day.append(("gap_pct",
                    f"the gap was never computed: "
                    f"{candidate.get('gap_reason') or 'reason unrecorded'}"))
    elif not _CRIT.rule("day_setup", "gap_pct").test(gap):
        day.append(("gap_pct",
                    f"gap_pct {gap:.2f} fails {_CRIT.rule('day_setup', 'gap_pct').describe()}"))
    if not _CRIT.rule("day_setup", "price").test(price):
        day.append(("price",
                    f"price {price} fails {_CRIT.rule('day_setup', 'price').describe()}"))
    if not _CRIT.rule("day_setup", "market_cap").test(market_cap):
        day.append(("market_cap",
                    f"market_cap {market_cap} fails "
                    f"{_CRIT.rule('day_setup', 'market_cap').describe()}"))
    if not _CRIT.rule("day_setup", "premarket_rvol").test(candidate.get("pm_rvol")):
        day.append(("premarket_rvol",
                    f"premarket_rvol {candidate.get('pm_rvol')} fails "
                    f"{_CRIT.rule('day_setup', 'premarket_rvol').describe()}"))
    if _CRIT.flag("day_setup", "require_above_prior_high"):
        if prior_high is None or price is None or price <= prior_high:
            day.append(("require_above_prior_high",
                        f"price {price} is not above the prior day high {prior_high}"))

    swing: list[tuple[str, str]] = []
    if gap is None:
        swing.append(("gap_pct",
                      f"the gap was never computed: "
                      f"{candidate.get('gap_reason') or 'reason unrecorded'}"))
    elif not _CRIT.rule("swing_setup", "gap_pct").test(gap):
        swing.append(("gap_pct",
                      f"gap_pct {gap:.2f} fails "
                      f"{_CRIT.rule('swing_setup', 'gap_pct').describe()}"))
    if not _CRIT.rule("swing_setup", "price").test(price):
        swing.append(("price",
                      f"price {price} fails {_CRIT.rule('swing_setup', 'price').describe()}"))
    if not _CRIT.rule("swing_setup", "market_cap").test(market_cap):
        swing.append(("market_cap",
                      f"market_cap {market_cap} fails "
                      f"{_CRIT.rule('swing_setup', 'market_cap').describe()}"))
    if _CRIT.flag("swing_setup", "require_open_above_prior_high"):
        if prior_high is None or price is None or price <= prior_high:
            swing.append(("require_open_above_prior_high",
                          f"premarket price {price} is not above the prior day "
                          f"high {prior_high}"))
    if _CRIT.flag("swing_setup", "require_open_above_200sma"):
        if sma200 is None or price is None or price <= sma200:
            swing.append(("require_open_above_200sma",
                          f"premarket price {price} is not above the 200 day "
                          f"average {sma200}"))
    if _CRIT.flag("swing_setup", "require_catalyst"):
        # Three states, not two. None means the news feed was never fetched
        # (failed call or quota skip), and an unchecked feed must not produce
        # a sentence claiming a search came back empty. Either way the
        # requirement is unmet, so both fail the screen; only the reason
        # differs, and the reason is what the report shows the reader.
        found = candidate.get("catalyst_found")
        if found is None:
            swing.append(("require_catalyst",
                          "the news feed was never checked, so catalyst is unknown"))
        elif not found:
            swing.append(("require_catalyst", "no catalyst was found"))

    candidate["day_eligible"] = not day
    candidate["day_failed"] = [why for _key, why in day]
    candidate["day_failed_conditions"] = [key for key, _why in day]
    candidate["swing_eligible"] = not swing
    candidate["swing_failed"] = [why for _key, why in swing]
    candidate["swing_failed_conditions"] = [key for key, _why in swing]


def screen_tally(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Per condition counts of what cleared and what failed, for both screens.

    This exists because the report used to ask the MODEL for it. REPORT_TEMPLATE
    told the analyst to write "the most common failed condition" under an empty
    watchlist, the packet carried no such number, and so the one sentence a
    reader gets on a morning that published nothing was a statistic computed in
    prose from twelve per candidate lists. On 2026-08-18 it came out wrong in
    the strongest available form: the report said price above the prior day high
    was missed by "every candidate", when AS.US cleared it at 34.71 against
    33.4194 and failed on its null RVOL alone. Eleven of twelve failed that
    condition and ten of twelve failed the RVOL one, so the mode was right and
    the universal was false.

    A count is not a judgement and there is exactly one correct answer, which
    makes it the packet's job. See doc/research/TEMPLATE_DERIVATIONS.md for the
    full audit of what else the template asks the model to derive.

    cleared is counted as examined minus failed rather than by re-testing, so
    the two can never disagree with the eligibility decision they describe.
    """
    examined = len(candidates)
    out: dict[str, Any] = {"candidates_examined": examined}
    for screen, key in (("day", "day_failed_conditions"),
                        ("swing", "swing_failed_conditions")):
        counts: dict[str, int] = {}
        for candidate in candidates:
            for condition in candidate.get(key) or []:
                counts[condition] = counts.get(condition, 0) + 1
        eligible = sum(1 for c in candidates if c.get(f"{screen}_eligible"))
        # Ordered by how many failed, descending, so the template can quote the
        # list in that order without sorting anything itself.
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        out[screen] = {
            "eligible": eligible,
            "failed_by_condition": {
                name: {"failed": n, "cleared": examined - n} for name, n in ranked
            },
            # The sentence the template quotes, built here so the model neither
            # counts nor ranks. Empty when nothing failed, which is not the same
            # as a screen nobody ran.
            "failed_summary": ", ".join(f"{name} {n} of {examined}" for name, n in ranked),
        }
    return out


def score_candidate(candidate: dict[str, Any]) -> None:
    """Confluence score from 0 to 10, with the breakdown kept.

    The breakdown is the point. A total on its own cannot be argued with, and a
    score you cannot argue with is a score you cannot improve.

    A component whose input was never observed is unknown, and unknown must
    not price as zero: zero says "checked and weak", a claim about the stock,
    where unknown is a fact about the pipeline. When any component is unknown
    the total is null, the sum over the known components is kept as
    score_partial next to the names in score_unavailable, and the conviction
    bucket is null, rendered downstream as unscored, never red. Calibration
    queries exclude null scores rather than folding them into low.
    """
    quote = candidate.get("quote") or {}
    class_points = {
        key: float(value) for key, value in _CRIT.pair_map("score_catalyst_class", "class").items()
    }

    catalyst_class = candidate.get("catalyst_class", "none")
    components: list[dict[str, Any]] = []
    unavailable: list[str] = []

    def add(name: str, points: float, why: str) -> None:
        components.append({"component": name, "points": points, "why": why})

    def unknown(name: str, why: str) -> None:
        components.append({"component": name, "points": None, "why": why})
        unavailable.append(name)

    if catalyst_class is None:
        unknown("catalyst_class",
                candidate.get("catalyst_why") or "the news feed was never checked")
    else:
        add("catalyst_class", class_points.get(catalyst_class, 0.0),
            f"class {catalyst_class}: {candidate.get('catalyst_why', '')}")

    # The two volume measures are alternatives filling ONE slot, not two
    # components. Two components would break the 0 to 10 scale for any name
    # carrying both, and would leave a first-appearance name unscored anyway,
    # which is the thing this is here to fix.
    #
    # RVOL is preferred when it is available because it is the better measure:
    # it asks whether this name is busy against its own history, where rotation
    # asks only whether the float is turning over. Rotation is the fallback,
    # and it is the only one of the two computable on a name nobody has
    # baselined yet. Their bands are matched so the slot pays the same either
    # way; see CRITERIA.md [Score premarket float rotation].
    #
    # The component is NAMED for the measure that filled it, so the breakdown
    # says which one made the name scorable rather than hiding it behind a
    # neutral label. volume_measure_used carries the same fact under a stable
    # key for anything reading this programmatically.
    rvol = candidate.get("pm_rvol")
    rotation = candidate.get("pm_float_rotation")
    if rvol is not None:
        candidate["volume_measure_used"] = "premarket_rvol"
        add("premarket_rvol", _CRIT.band_number("score_premarket_rvol", rvol),
            f"pm_rvol {rvol}")
    elif rotation is not None:
        candidate["volume_measure_used"] = "premarket_float_rotation"
        add("premarket_float_rotation",
            _CRIT.band_number("score_premarket_float_rotation", rotation),
            f"float rotation {rotation:.6f} of the float traded since "
            f"{_CRIT.clock_text('collector', 'start_time')} ET, used because "
            f"pm_rvol is null ({candidate.get('pm_rvol_reason')})")
    else:
        candidate["volume_measure_used"] = None
        unknown("premarket_volume",
                f"neither measure is available. pm_rvol is null "
                f"({candidate.get('pm_rvol_reason')}) and float rotation is null "
                f"({candidate.get('pm_float_rotation_reason')})")

    gap_raw = candidate.get("gap_pct")
    if gap_raw is None:
        unknown("gap", "the gap itself was never computed")
    else:
        gap = abs(gap_raw)
        add("gap", _CRIT.band_number("score_gap", gap), f"absolute gap {gap:.2f} percent")

    price = candidate.get("price")
    prior_high = candidate.get("prior_high")
    if prior_high is None or price is None:
        unknown("above_prior_high",
                f"prior day high {prior_high} or price {price} was never observed")
    else:
        add("above_prior_high",
            _CRIT.number("score_booleans", "above_prior_high") if price > prior_high else 0.0,
            f"price {price} against prior day high {prior_high}")

    vwap = candidate.get("pm_vwap")
    if vwap is None or price is None:
        unknown("above_premarket_vwap", "no premarket VWAP was collected")
    else:
        add("above_premarket_vwap",
            _CRIT.number("score_booleans", "above_premarket_vwap") if price > vwap else 0.0,
            f"price {price} against premarket VWAP {vwap}")

    cap_rule = _CRIT.rule("score_booleans", "market_cap_above")
    market_cap = quote.get("marketCap")
    if market_cap is None:
        unknown("market_cap", "market cap was never observed")
    else:
        add("market_cap",
            _CRIT.number("score_booleans", "market_cap_above_points")
            if cap_rule.test(market_cap) else 0.0,
            f"market cap {market_cap} against {cap_rule.describe()}")

    known_total = sum(c["points"] for c in components if c["points"] is not None)
    candidate["score_components"] = components
    if unavailable:
        candidate["score"] = None
        candidate["score_partial"] = round(known_total, 4)
        candidate["score_unavailable"] = unavailable
        candidate["conviction"] = None
    else:
        candidate["score"] = round(known_total, 4)
        candidate["score_partial"] = None
        candidate["score_unavailable"] = []
        candidate["conviction"] = _CRIT.band_result("score_buckets", known_total)


def stamp_all(candidates: list[dict[str, Any]], earnings_block: dict[str, Any]) -> None:
    earnings_symbols = {
        str(row.get("symbol") or "").upper()
        for row in earnings_block.get("candidates", [])
        if row.get("symbol")
    }
    for candidate in candidates:
        catalyst_class, why = classify_catalyst(candidate, earnings_symbols)
        candidate["catalyst_class"] = catalyst_class
        candidate["catalyst_why"] = why
        evaluate_eligibility(candidate)
        score_candidate(candidate)


# ------------------------------------------------------------------- runner

def _calendar_cache_state() -> dict[str, Any]:
    from ops import market_today

    return market_today.cache_state(
        _CRIT.integer("calendar", "refresh_after_days"))


def build_packet() -> dict[str, Any]:
    config.ensure_dirs()
    # The 08:45 window does not spend itself fetching a calendar. The nightly
    # refreshes it; if it is stale anyway the run proceeds on the cached copy
    # and calendar_cache in the packet records that it did.
    from ops import market_today

    market_today.ALLOW_NETWORK = False

    packet = Packet()
    api = eodhd.client()

    # The shared key preflight, before anything is spent. Below the refuse
    # floor the exception ends the run. Below the degrade threshold the run
    # narrows to the one call it cannot skip, the bulk call that decides
    # membership, and every skipped section records the reading, because a
    # thin packet that says why it is thin beats a fat packet that burned the
    # last of a shared day's quota.
    quota = eodhd.preflight("scan")
    if quota["refused"]:
        raise eodhd.QuotaRefusal(
            "quota exhausted by another consumer on the shared key: "
            f"{eodhd.describe_preflight(quota)}, below the refuse floor of "
            f"{quota['refuse_below']:,} in CRITERIA.md [quota]"
        )
    thin = quota["degraded"]
    quota_clause = eodhd.describe_preflight(quota)

    now = ettime.now_et()
    cutoff = baseline.normalize_cutoff((now.hour, now.minute))
    # The baseline cache is warmed for the configured run time. Sixty seconds
    # of scheduler jitter must not miss it on an exact minute match, so a wall
    # clock within the snap window uses the run time cutoff instead. See the
    # cutoff snap note in CRITERIA.md.
    run_hour, run_minute = _CRIT.clock("scan", "run_time")
    snap_minutes = _CRIT.integer("scan", "rvol_cutoff_snap_minutes")
    if abs((now.hour * 60 + now.minute) - (run_hour * 60 + run_minute)) <= snap_minutes:
        cutoff = _CRIT.clock_text("scan", "run_time")

    try:
        universe_payload = universe.require_fresh_universe()
    except universe.StaleUniverseError as exc:
        raise

    watchlist = discover.load_watchlist()
    if watchlist.get("missing"):
        packet.gap("watchlist.json is missing, so no candidate can be marked collector covered")

    # Snapshot the collector file before parsing it. The collector appends
    # until 09:25, so at 08:45 this read overlaps the write; the copy freezes
    # the bytes and a trailing partial line is discarded, not raised on.
    #
    # This moved ahead of the market snapshot because the market snapshot now
    # prices from these bars too. Everything downstream reads one frozen copy.
    session_date = now.date().isoformat()
    snapshot_path = config.run_dir(session_date) / "premarket_snapshot.jsonl"
    # overwrite=True: scan owns today's snapshot. The watchdog reruns the
    # morning chain on purpose and that rerun must produce a fresh copy of the
    # collector file, not a numbered sibling the packet then fails to name.
    bars_by_symbol, collector_stats = collect_premarket.snapshot_bars(
        session_date, snapshot_path, overwrite=True
    )
    run_stats = collect_premarket.read_run_stats(session_date)

    if thin:
        packet.gap(f"market snapshot skipped: {quota_clause}, below the "
                   f"{quota['degrade_below']:,} threshold in CRITERIA.md [quota]")
        snapshot = []
    else:
        snapshot = market_snapshot(api, packet, bars_by_symbol)
    candidates, provenance = pool_candidates(watchlist, packet)
    if collector_stats.get("partial_line_discarded"):
        print("scan: the collector was mid write, one partial trailing line discarded")
    if run_stats and (run_stats.get("reconnects") or 0) > 0:
        print(f"scan: the collector reconnected {run_stats['reconnects']} time(s) "
              "this morning, noted in the packet")

    dropped: list[dict[str, Any]] = []
    # Bound here rather than inside the branch below, like dropped and
    # rank_stats beside it. A morning that reaches this point with no
    # subscribed names skips that branch entirely, and the payload at the
    # bottom of this function reads every one of these three. Two were bound
    # and this one was not, so an absent or empty watchlist ended the scan
    # with an UnboundLocalError instead of the zero candidate packet both
    # architecture pages describe, which cost the whole chain: no packet, no
    # report, no email, on the one morning the degrade path exists for.
    dropped_stale: list[dict[str, Any]] = []
    rank_stats: dict[str, Any] = {}
    if candidates:
        # All local: the premarket path, the price it implies, the drop, then
        # the ranking on that measured price. Not one API call has been spent
        # on a candidate yet, so the cut below costs nothing to be wrong about.
        attach_premarket_path(candidates, watchlist, packet, bars_by_symbol)
        price_from_collector(candidates, packet, bars_by_symbol)
        candidates, dropped = drop_uncovered(candidates, packet)
        # After the coverage cut, because a name with no bars at all has no age
        # to judge and belongs in dropped_no_coverage rather than here.
        candidates, dropped_stale = drop_stale_prices(candidates, packet)

        # Ranking needs a prior close per name. The pool normally carries one
        # out of discover's bulk read at no extra cost. A watchlist written
        # before the pool rewrite has none, and so would a morning where the
        # movers source failed, and in either case every name would be
        # unrankable and the report would come out empty for a reason that has
        # nothing to do with the market. So buy them here when they are absent.
        unpriced = [c for c in candidates if c.get("pool_prior_close") is None]
        if unpriced and not thin:
            packet.gap(
                f"{len(unpriced)} subscribed name(s) reached the scan without a prior "
                "close from the pool, so one end of day call each was spent here to "
                "make them rankable. A watchlist written before the pool rewrite, or "
                "a morning where the movers source failed, both look like this."
            )
            attach_daily_history(api, unpriced, packet)
            for candidate in unpriced:
                candidate["pool_prior_close"] = candidate.get("prior_close")

        candidates, rank_stats = rank_by_measured_gap(
            candidates, packet, _CRIT.integer("scan", "candidate_count")
        )
    provenance["ranking"] = rank_stats

    if candidates:
        if thin:
            # The collector file and the baseline cache are local, so the
            # premarket path, the price and the RVOL both sides still run.
            # What is skipped is exactly the per candidate REST spend.
            packet.gap(
                "delayed quotes, daily history and news skipped for every "
                f"candidate: {quota_clause}. Market cap, the 200 day average, "
                "the prior session close and high, the gap that is measured "
                "against that close, and catalysts are null for quota reasons, "
                "not vendor ones."
            )
            for candidate in candidates:
                candidate["quote"] = {}
                candidate["prior_close"] = None
                candidate["prior_high"] = None
                candidate["prior_session_date"] = None
                candidate["avg_volume_20d"] = None
                candidate["catalyst_found"] = None
                candidate["catalyst_error"] = f"news call skipped: {quota_clause}"
                candidate["headlines"] = []
        else:
            attach_quotes(api, candidates, packet)
            attach_daily_history(api, candidates, packet)
        attach_gap(candidates)
        attach_premarket_rvol(candidates, packet, cutoff)
        # After the quotes, which carry sharesFloat, and after the RVOL pass,
        # whose reason string this one quotes when it has to stand in.
        attach_float_rotation(candidates, packet)
        if not thin:
            attach_catalysts(api, candidates, packet)
        # After the catalysts, whose headlines it weighs, and after attach_gap,
        # whose gap_pct decides whether the question applies at all. On the thin
        # path headlines is empty and every trap comes out null with its reason,
        # which is the honest answer when the news was never fetched.
        attach_traps(candidates, packet)

    if thin:
        packet.gap(f"economic events and the earnings calendar skipped: {quota_clause}")
        events = {"events": [], "skipped": quota_clause}
        earnings_block = {"candidates": [], "notable_tomorrow": [], "skipped": quota_clause}
    else:
        events = economic_events(api, packet)
        earnings_block = earnings(api, candidates, packet)

    # After pricing, before scoring. A violation ends the run here: nothing is
    # stamped, no packet is written, and the chain stops before the analyst.
    vintage.enforce({
        "candidates": candidates,
        "market_snapshot": snapshot,
        "session_date": session_date,
    })

    if candidates:
        stamp_all(candidates, earnings_block)

    # Read, never computed: see volume_check's docstring. Placed after the
    # screens have run so rvol_only_day_failures has decisions to read, and
    # before the packet is assembled so both land in gaps_to_fill in the order
    # a reader needs them, the measurement first and then what it cost.
    volume_measurement = volume_check(session_date, packet)
    rvol_only = rvol_only_day_failures(candidates, packet)

    late_window = [c["symbol"] for c in candidates if c.get("pm_window_starts_late")]
    if late_window:
        packet.gap(
            "these candidates have a partial or absent premarket window and must be "
            f"labelled as such in the report: {', '.join(late_window)}"
        )

    return {
        "generated_at": ettime.stamp(now),
        "session_date": now.date().isoformat(),
        # Which build wrote this. A report that cannot be tied to a commit
        # cannot be explained six weeks later.
        "build": config.build_identifier(),
        "vintage": {
            "checked_at": ettime.stamp(ettime.now_et()),
            "violations": [],
            "note": "every check in vintage.py passed, or this packet would not exist",
        },
        "quota_preflight": quota,
        # Which scheduled steps have not succeeded inside their window. Empty
        # on a healthy machine, and analyst.py puts the line in front of the
        # reader when it is not, because a job that fails where nobody looks
        # is a job that has stopped running.
        "job_health": {
            "overdue": job_status.overdue(now.date()),
            "line": job_status.report_line(now.date()),
        },
        "run_time_et": ettime.hhmm(now),
        "rvol_cutoff_hhmm": cutoff,
        "collector_file": collect_premarket.bar_path().name,
        "collector_snapshot": {
            "file": snapshot_path.name,
            "bars_total": collector_stats.get("bars_total"),
            "last_complete_bar_et": collector_stats.get("last_bar_et"),
            "partial_line_discarded": collector_stats.get("partial_line_discarded"),
            "bad_lines_skipped": collector_stats.get("bad_lines_skipped"),
            # Connection health from the collector's own run stats sidecar. A
            # flaky morning (reconnects above zero) is a fact the report reader
            # deserves to see next to the bar count it explains.
            "runs": (run_stats or {}).get("runs"),
            "connections": (run_stats or {}).get("connections"),
            "reconnects": (run_stats or {}).get("reconnects"),
            "resubscriptions": (run_stats or {}).get("resubscriptions"),
            "messages": (run_stats or {}).get("messages"),
            # The last hop of the path the collector's declaration comment
            # argues for. Non fatal status frames are kept by the run loop,
            # persisted per run, and summed by read_run_stats, and without this
            # line all three stop short of the packet and the fact that a
            # morning saw odd frames reaches no reader. Null rather than zero
            # when no run carried a count, because a morning nobody counted is
            # not a morning that saw none.
            "status_frames": (run_stats or {}).get("status_frames"),
            # Rows the file holds and the window deliberately excludes. Null on
            # a file written before the tag existed, which is not the same as
            # zero: those sessions folded their replay into ordinary bars and
            # it cannot be recovered from the file.
            "replay_rows": collector_stats.get("replay_rows"),
            "replay_volume": collector_stats.get("replay_volume"),
            "replay_first_et": collector_stats.get("replay_first_et"),
        },
        # Did every name the socket was asked for actually produce anything.
        # Separate from collector_snapshot above, which describes the file;
        # this describes the subscription, and the two answer different
        # questions when a symbol is missing from the file.
        "collector_coverage": collector_coverage(bars_by_symbol, session_date),
        # What the tape actually covered this morning, against what the
        # collector was scheduled for.
        "collector_window_observed": observed_collector_window(
            bars_by_symbol, now, collector_stats),
        # The morning never fetches the exchange calendar. If it is stale, the
        # packet says so and the run proceeds on the cached copy rather than
        # blocking the 08:45 window on a fetch and its retries.
        "calendar_cache": _calendar_cache_state(),
        "collector_window_configured": [
            _CRIT.clock_text("collector", "start_time"),
            _CRIT.clock_text("collector", "stop_time"),
        ],
        "watchlist_generated_at": watchlist.get("generated_at"),
        "market_snapshot": snapshot,
        "candidate_provenance": provenance,
        "candidates": candidates,
        # Named, not silently absent. These cleared the floors and then had no
        # collector coverage, so they had no premarket price and were dropped
        # rather than published at a stale one.
        "dropped_no_coverage": dropped,
        # Collected but too old to publish as this morning's price. Separate
        # from the list above because the fixes differ: a subscription slot
        # versus a collector that stopped listening.
        "dropped_stale_price": dropped_stale,
        "economic": events,
        "earnings": earnings_block,
        "criteria_summary": {
            "day_setup": {
                key: value for key, value in _CRIT.section("day_setup").pairs
            },
            "swing_setup": {
                key: value for key, value in _CRIT.section("swing_setup").pairs
            },
            "score_buckets": [b.describe() for b in _CRIT.bands("score_buckets")],
        },
        # What cleared and what failed, per screen condition. The report quotes
        # this rather than counting; see screen_tally for why.
        "screen_tally": screen_tally(candidates),
        # What the collector's premarket volume is actually worth, measured by
        # the nightly against the vendor on identical minutes. Every pm_rvol
        # and every pm_float_rotation in this packet divides by a number from
        # a different feed than its numerator, and this is the size of that
        # difference. Null when no check has ever been written, which the gaps
        # list says in words.
        "collector_volume_check": volume_measurement,
        # The names that cost. Empty on a morning where RVOL was not the
        # deciding condition for anyone.
        "day_blocked_on_rvol_alone": rvol_only,
        "gaps_to_fill": packet.gaps,
        "api_calls": eodhd.call_count(),
    }


def evidence_width(payload: dict[str, Any]) -> dict[str, int]:
    """How much a packet actually knows, on the axes a rerun can lose.

    Counts rather than a score, because the point is to say WHICH kind of
    evidence a rerun would cost and a single number cannot.
    """
    candidates = payload.get("candidates") or []
    return {
        "candidates": len(candidates),
        "priced": sum(1 for c in candidates if c.get("price") is not None),
        "with_rvol": sum(1 for c in candidates if c.get("pm_rvol") is not None),
        "scored": sum(1 for c in candidates if c.get("score") is not None),
    }


def thinner_than(fresh: dict[str, int], prior: dict[str, int]) -> list[str]:
    """The axes on which fresh knows strictly less, empty unless it knows no more.

    A rerun that gains on any axis is not a thinner rerun even if it loses on
    another, because that is a different morning rather than a degraded copy of
    this one, and standing down on it would be the guard refusing an
    improvement.
    """
    if any(fresh[key] > prior[key] for key in prior):
        return []
    return sorted(key for key in prior if fresh[key] < prior[key])


def thin_rerun_stands_down(payload: dict[str, Any]) -> bool:
    """True when this payload must not replace a fuller one already on disk.

    A rerun is only idempotent when it carries at least as much evidence as
    what it replaces. A thinner rerun must not overwrite the packet and must
    not upsert nulls over real values in picks, so it is written alongside as
    packet_degraded.json instead and the caller stands down. The watchdog's
    rerun of a broken chain then proceeds against the fuller packet.

    Until 2026-08-20 this asserted exactly that and tested only one way of
    being thin, a quota degraded preflight. The audit found the other one, and
    it is the one the schedule actually produces. The RVOL cutoff is snapped to
    [scan] run_time only within rvol_cutoff_snap_minutes of it, while [picks]
    live_window_start to live_window_end is 07:00 to 09:30, so a watchdog rerun
    of a broken chain at 09:25, which [monitor] rerun_chain_until explicitly
    allows until 09:30, computes a 09:25 cutoff, finds no baseline row warmed
    for it, publishes a null pm_rvol for every candidate, flips day_eligible
    false for all of them, and upserts that over the 08:45 rows as source
    'live'. The morning's real evidence would have been replaced by a rerun
    whose only fault was the clock.

    So the test is now the sentence the docstring already made: is this payload
    thinner than what is on disk, on any axis, and better on none.
    """
    session_date = payload["session_date"]
    existing_path = config.run_dir(session_date) / "packet.json"
    if not existing_path.is_file():
        return False
    try:
        prior = json.loads(existing_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False

    quota = payload.get("quota_preflight") or {}
    prior_quota = prior.get("quota_preflight") or {}
    reasons: list[str] = []
    if quota.get("degraded") and not prior_quota.get("degraded"):
        reasons.append("this run was quota thinned and the one on disk was not")

    fresh_width, prior_width = evidence_width(payload), evidence_width(prior)
    lost = thinner_than(fresh_width, prior_width)
    if lost:
        reasons.append(
            "it knows less on " + ", ".join(
                f"{key} ({fresh_width[key]} against {prior_width[key]})"
                for key in lost
            )
        )
    if not reasons:
        return False

    side_path = config.run_dir(session_date) / "packet_degraded.json"
    side_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"scan: a fuller packet already exists for {session_date} and this rerun "
          f"stands down because {'; and '.join(reasons)}. Wrote {side_path.name} "
          "for the record; packet.json and the picks table keep the fuller "
          "evidence, and the rest of the chain runs against it.")
    return True


def write_packet(payload: dict[str, Any]) -> Any:
    """Every run gets its own dated directory. Nothing is overwritten across days."""
    run_directory = config.run_dir(payload["session_date"])
    path = run_directory / "packet.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_picks(payload: dict[str, Any], force_test: bool = False) -> int:
    """One picks row per candidate, upserted on (date, ticker).

    The natural key is what makes a re-run of the same day an update rather
    than a second copy. entry_ref and stop_ref follow the field choices
    documented in CRITERIA.md, and a null level stays null: a reference that
    was never observed is not a reference.

    Every row carries a source. 'live' only when this run happened inside
    the CRITERIA.md [picks] live window and --test was not passed; anything
    else is 'test', because a packet gathered at noon describes a different
    market than the one the report is about, and test rows must never
    interleave silently with the real record.
    """
    reference_fields = {"pm_high", "pm_low", "pm_vwap"}
    entry_field = _CRIT.text("picks", "entry_ref_field")
    stop_field = _CRIT.text("picks", "stop_ref_field")
    for field in (entry_field, stop_field):
        if field not in reference_fields:
            raise criteria.CriteriaError(
                f"picks reference field {field!r} is not one of {sorted(reference_fields)}"
            )

    window_start = _CRIT.clock_text("picks", "live_window_start")
    window_end = _CRIT.clock_text("picks", "live_window_end")
    run_hhmm = str(payload.get("run_time_et") or "")
    in_window = bool(run_hhmm) and window_start <= run_hhmm <= window_end
    source = "test" if (force_test or not in_window) else "live"
    if source == "test":
        why = ("--test was passed" if force_test else
               f"the run clock {run_hhmm or 'unknown'} is outside the live window "
               f"{window_start} to {window_end}")
        print(f"scan: picks rows will carry source='test' ({why})")

    written = 0
    with store.session() as connection:
        store.init(connection)
        for candidate in payload.get("candidates", []):
            store.upsert(connection, "picks", ["date", "ticker"], {
                "date": payload["session_date"],
                "ticker": candidate["symbol"],
                "day_eligible": int(bool(candidate.get("day_eligible"))),
                "swing_eligible": int(bool(candidate.get("swing_eligible"))),
                "score": candidate.get("score"),
                "conviction": candidate.get("conviction"),
                "gap_pct": candidate.get("gap_pct"),
                "pm_rvol": candidate.get("pm_rvol"),
                "pm_float_rotation": candidate.get("pm_float_rotation"),
                # Which of the two volume measures actually scored this row.
                # Without it a null pm_rvol next to a real score looks like a
                # bug, and calibration cannot separate the two populations.
                "volume_measure_used": candidate.get("volume_measure_used"),
                "pm_high": candidate.get("pm_high"),
                "pm_low": candidate.get("pm_low"),
                "pm_vwap": candidate.get("pm_vwap"),
                "collector_covered": int(bool(candidate.get("collector_covered"))),
                "pm_window_start": candidate.get("pm_window_start"),
                "prior_high": candidate.get("prior_high"),
                "catalyst_class": candidate.get("catalyst_class"),
                "entry_ref": candidate.get(entry_field),
                "stop_ref": candidate.get(stop_field),
                "source": source,
                "score_partial": candidate.get("score_partial"),
                "score_unavailable": ", ".join(candidate.get("score_unavailable") or []) or None,
                "pool_source": ", ".join(candidate.get("pool_source") or []) or None,
                "pool_tier": candidate.get("pool_tier"),
            })
            written += 1
        connection.commit()
        total, live = connection.execute(
            "SELECT COUNT(*), SUM(CASE WHEN source='live' THEN 1 ELSE 0 END) "
            "FROM picks WHERE date=?",
            (payload["session_date"],),
        ).fetchone()
    print(f"scan: picks upserted {written} rows for {payload['session_date']} "
          f"as source='{source}'; the day now holds {total} rows, {live or 0} live")
    return written


def rescore(path) -> dict[str, Any]:
    """Recompute flags and scores from an existing packet, changing nothing else.

    This is how the determinism claim is checked: two runs against the same
    packet must produce byte identical scores.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    stamp_all(payload.get("candidates", []), payload.get("earnings", {}))
    return payload


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gather the morning packet.")
    parser.add_argument("--rescore", metavar="PACKET",
                        help="Recompute scores from an existing packet and print them.")
    parser.add_argument("--test", action="store_true",
                        help="Force picks rows to source='test'. Off clock runs "
                             "are marked test automatically.")
    args = parser.parse_args(argv)

    if args.rescore:
        from pathlib import Path

        payload = rescore(Path(args.rescore))
        print(json.dumps(
            [
                {
                    "symbol": c["symbol"],
                    "day_eligible": c["day_eligible"],
                    "swing_eligible": c["swing_eligible"],
                    "score": c["score"],
                    "conviction": c["conviction"],
                    "components": c["score_components"],
                }
                for c in payload.get("candidates", [])
            ],
            indent=2,
            sort_keys=True,
        ))
        return 0

    try:
        payload = build_packet()
    except (universe.StaleUniverseError, eodhd.QuotaRefusal) as exc:
        print(f"REFUSING TO RUN: {exc}")
        eodhd.print_call_report()
        return 1
    except vintage.StaleDataError as exc:
        # enforce() has already named every failing row and rewritten the gate
        # marker. Exiting non-zero is what stops the chain before the analyst.
        print(f"REFUSING TO PUBLISH: {exc}")
        eodhd.print_call_report()
        return 1

    if thin_rerun_stands_down(payload):
        eodhd.print_call_report()
        return 0

    path = write_packet(payload)
    write_picks(payload, force_test=args.test)
    job_status.produced("candidates", len(payload["candidates"]))
    print("")
    print(f"scan: wrote {path}")
    dropped = payload.get("dropped_no_coverage") or []
    print(f"scan: {len(payload['candidates'])} candidates, "
          f"{len(dropped)} dropped for no collector coverage, "
          f"{len(payload['gaps_to_fill'])} gaps to fill")
    for candidate in payload["candidates"]:
        if candidate["score"] is None:
            score_text = (f"unscored (partial {candidate.get('score_partial')}, "
                          f"missing {len(candidate.get('score_unavailable') or [])})")
        else:
            score_text = f"{candidate['score']:>4.1f} {candidate['conviction']:<7}"
        gap = candidate.get("gap_pct")
        gap_text = f"{gap:+7.2f}%" if gap is not None else "      ?%"
        print(
            f"    {candidate['symbol']:<10} gap {gap_text}  "
            f"score {score_text} "
            f"day={'Y' if candidate['day_eligible'] else 'n'} "
            f"swing={'Y' if candidate['swing_eligible'] else 'n'}  "
            f"rvol={candidate.get('pm_rvol')}  price={candidate.get('price')} "
            f"from {candidate.get('price_source')}"
        )
    for row in dropped:
        print(f"    dropped: {row['symbol']:<10} {row['reason']}")
    for gap in payload["gaps_to_fill"]:
        print(f"    gap: {gap}")
    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(job_status.run("scan", main, ok_codes=OK_CODES))
