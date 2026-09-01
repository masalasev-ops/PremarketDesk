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
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from collect import baseline
from collect import collect_premarket
from core import artifacts
from core import config
from core import criteria
from selection import discover
from core import eodhd
from core import ettime
from night import paper_ledger
from ops import job_status
from core import store
from selection import universe
from morning import vintage

_CRIT = criteria.load()

# Below this many collected minutes a premarket window is THIN, which is a
# different fact from opening late and had been sharing a word with it. See the
# thin window note in CRITERIA.md.
MIN_BARS_FOR_FULL_WINDOW = _CRIT.integer("scan", "min_bars_for_full_window")
# Percent between the two vendor prior closes above which the packet says they
# disagree. See the two prior closes note in CRITERIA.md.
PRIOR_CLOSE_DISAGREEMENT_PCT = _CRIT.number("scan", "prior_close_disagreement_pct")


def _as_float(value: Any) -> float | None:
    if value is None or value == "" or value == "NA":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def gap_direction(gap_pct: Any) -> str | None:
    """"up", "down", or None when the gap was never computed.

    One rule in one place, because two copies of it is how the score roll and
    the candidate stamp come to disagree about a name. The roll has carried
    this since 2026-08-20 and it lived inline there; the candidate dict
    carried nothing at all, which is why the report could name a score with
    no way to say which way the name was moving.

    Exactly 0.0 reads as up, and the boundary is stated rather than left to
    be discovered. It is not a third state because no candidate can sit on it
    in practice: rank_by_measured_gap applies the [Discovery] gap floor to the
    ABSOLUTE gap, so a name reaching the pool has moved. attach_gap then
    recomputes the published gap against a different prior close, which makes
    an exact zero arithmetically reachable, and it has never occurred. A
    "flat" state would buy a distinction for a case that does not arise and
    would have to be quoted into the report by name.

    NULL, never a default. A gap that was never computed has no direction, and
    the reason it was never computed is already recorded once, in gap_reason.
    Two copies of one reason is how they drift.
    """
    value = _as_float(gap_pct)
    if value is None:
        return None
    return "up" if value >= 0 else "down"


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
    # .get with a floor, not [.]. Every caller used to be the candidate path,
    # where the bars come straight from read_bars_file and always carry the
    # key. The notable movers section reads bars_by_symbol for every subscribed
    # symbol, so one malformed line in the collector file would raise KeyError
    # out of build_packet and stop the morning chain rather than costing one
    # symbol its row.
    dated = [b for b in bars if b.get("minute_epoch") is not None]
    if not dated:
        return None, None
    last = max(dated, key=lambda b: b["minute_epoch"])
    return (
        _as_float(last.get("c")),
        ettime.stamp(ettime.from_epoch_s(last["minute_epoch"])),
    )


def collector_coverage(
    bars_by_symbol: dict[str, list[dict[str, Any]]], session_date: str,
    replay_by_symbol: dict[str, int] | None = None,
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
    replay_only = set(replay_by_symbol or {}) - with_bars

    if not subscriptions:
        return {
            "requested": None,
            "produced_bars": len(with_bars),
            "silent": None,
            "silent_symbols": [],
            "silent_with_replay_only": [],
            "silent_with_nothing": [],
            "replay_by_symbol": {},
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
        # Of the silent ones, which delivered a REPLAYED print from outside the
        # window and which delivered nothing at all. Both are absent from the
        # bars and they are not the same failure: a replayed print proves the
        # subscription was accepted and the symbol exists on the feed, so the
        # socket went quiet during the window rather than never answering. The
        # report said "the socket delivered no trade for them" about both on
        # 2026-08-20, which is exact for one group and wrong for the other.
        "silent_with_replay_only": sorted(replay_only & set(requested)),
        "silent_with_nothing": sorted(set(silent) - replay_only),
        "replay_by_symbol": {
            symbol: count for symbol, count in sorted((replay_by_symbol or {}).items())
            if symbol in replay_only
        },
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
    # Whether it is TODAY'S watchlist, which is a different question from
    # whether it has names in it and was asked by nobody until 2026-08-24. The
    # field below has been in the packet since the packet existed, and CRITERIA
    # [Monitor] rested on it: "scan records watchlist_generated_at, so the
    # wrong names case stays visible in the morning rather than silent". It was
    # recorded and never read, which is not the same as visible. On 2026-08-24
    # a collector subscribed to the previous session's file and nothing
    # anywhere said so. Now it goes in gaps_to_fill, which the analyst reads
    # and the report prints.
    generated_on = None
    if not watchlist.get("missing"):
        try:
            generated_on = ettime.parse_date(str(watchlist.get("generated_at")))
        except (TypeError, ValueError):
            generated_on = None
        if generated_on != ettime.today_et():
            packet.gap(
                f"watchlist.json was written at {watchlist.get('generated_at')}, "
                f"which is not today, {ettime.today_et().isoformat()}. The "
                "collector subscribed to whatever that file named, so the names "
                "with premarket coverage below may belong to another session and "
                "today's real candidates may be absent entirely. A candidate "
                "reported here as having no collector bars is NOT evidence the "
                "tape was quiet. See CRITERIA [Monitor], the stale watchlist note.")

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


def _empty_ranking() -> dict[str, Any]:
    """The ranking record for a morning with nothing to rank.

    Same keys as rank_by_measured_gap returns, all zero, plus the one field it
    has no need of: why the ranking never ran. A reader comparing this against a
    real morning gets zeros where a real morning gets counts, rather than a
    missing object they have to interpret.
    """
    price_rule = _CRIT.rule("discovery", "price")
    gap_rule = _CRIT.rule("discovery", "gap_pct")
    return {
        "subscribed_considered": 0,
        "cleared_floors": 0,
        "kept": 0,
        "below_floor": 0,
        "unrankable": 0,
        "cap": _CRIT.integer("scan", "candidate_count"),
        "cap_source": "CRITERIA.md [Scan] candidate_count",
        "capped_out": 0,
        "capped_out_symbols": [],
        "floors": {"price": price_rule.describe(),
                   "gap_pct_absolute": gap_rule.describe()},
        "ranked_on": "the premarket gap measured from the collector, not the pool tier",
        "not_ranked_reason": (
            "no subscribed name reached the ranking, so nothing was ordered and "
            "every count here is a measured zero rather than an absence"
        ),
    }


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
    # Named, not merely subtracted. "18 cleared the floors and 12 were kept" is
    # arithmetic a reader can do and an explanation they cannot: the six that
    # vanished were TRUNCATED by candidate_count, not rejected by a screen, and
    # the packet recorded no difference between the two. On 2026-08-20 the
    # report published both numbers and could say nothing about the gap between
    # them, because nothing here told it there was a cap.
    capped_out = [
        {"symbol": c["symbol"], "gap_pct": c["provisional_gap_pct"]}
        for c in ranked[keep:]
    ]
    if unrankable:
        packet.gap(
            f"{unrankable} subscribed name(s) could not be ranked: no premarket "
            "price from the collector, or no prior session close carried by the pool"
        )
    if capped_out:
        packet.gap(
            f"{len(capped_out)} name(s) cleared the price and gap floors and were "
            f"then CUT BY THE RANK CAP of {keep} in CRITERIA.md [Scan] "
            "candidate_count, not by any screen: "
            + ", ".join(f"{row['symbol']} at {row['gap_pct']:+.2f} percent"
                        for row in capped_out)
            + ". A reader comparing the cleared count against the kept count "
            "cannot tell a rejected name from a truncated one, and these are "
            "the truncated ones."
        )
    stats = {
        "subscribed_considered": len(candidates),
        "cleared_floors": len(ranked),
        "kept": len(kept),
        "below_floor": below_floor,
        "unrankable": unrankable,
        # Why cleared_floors and kept differ, which is the question those two
        # numbers raise and neither answers.
        "cap": keep,
        "cap_source": "CRITERIA.md [Scan] candidate_count",
        "capped_out": len(capped_out),
        "capped_out_symbols": capped_out,
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

        # The OTHER prior close, and whether it agrees. attach_quotes has
        # already run, so previousClosePrice is on the candidate; the packet
        # carried both numbers and never compared them. On 2026-08-20 they were
        # 1.67 percent apart for SCSC, 51.42 here against 52.2909 there, which
        # is the difference between a published gap of 16.34 and one of 14.4.
        # The end of day record still wins: this is a disclosure and not a
        # tiebreak, for the reason the two prior closes note in CRITERIA.md
        # gives. Recorded as a magnitude like pm_source_disagreement, so feed
        # noise and a real disagreement stay distinguishable.
        quoted = _as_float((candidate.get("quote") or {}).get("previousClosePrice"))
        candidate["prior_close_quoted"] = quoted
        candidate["prior_close_disagreement_pct"] = None
        if quoted and candidate["prior_close"]:
            drift = abs(candidate["prior_close"] - quoted) / quoted * 100.0
            candidate["prior_close_disagreement_pct"] = round(drift, 4)
            if drift > PRIOR_CLOSE_DISAGREEMENT_PCT:
                packet.gap(
                    f"{candidate['symbol']} has two vendor prior closes "
                    f"{drift:.2f} percent apart: the end of day record dated "
                    f"{prior.get('date')} says {candidate['prior_close']} and the "
                    f"delayed quote says {quoted}. The gap in this packet is "
                    "measured from the end of day record; measured from the "
                    "quote it would differ by about that much."
                )
        volumes = [_as_float(b.get("volume")) for b in completed[-lookback:]]
        volumes = [v for v in volumes if v is not None]
        candidate["avg_volume_20d"] = round(sum(volumes) / len(volumes), 2) if volumes else None


# The three states the morning's fill warning may carry. Named rather than
# spelled as literals, so a claim can assert the set is closed and a typo
# cannot invent a fourth state that reads as real. Deliberately NOT the same
# words as [Truth] fill_plausible: that column is a verdict and this one is a
# warning, and a reader who sees 'plausible' in a morning report will take it
# for the night's answer.
_BAND_PCT = _CRIT.number("truth", "fill_band_pct")
_MIN_BAND_NOTIONAL = _CRIT.number("fill_warning", "min_morning_band_notional")

BAND_THIN = "thin"
BAND_NOT_FLAGGED = "not flagged"
BAND_UNKNOWN = "unknown"
BAND_STATES = (BAND_THIN, BAND_NOT_FLAGGED, BAND_UNKNOWN)


def band_at_level(bars: list[dict[str, Any]], level: float | None,
                  band_pct: float) -> tuple[float | None, int | None]:
    """(shares, minutes) the COLLECTOR saw within band_pct of one level.

    The same shape as night/true_volume.band_stats and the same band width,
    read from the same [Truth] fill_band_pct key, so the morning's band and the
    night's are the same width by construction rather than by inspection. What
    differs is the tape underneath: this walks the socket's sample, which
    carried a median 0.115 of the night's figure over the 54 rows where both
    exist, with a 68 fold spread around it.

    A minute counts when its RANGE reaches the band. Counting it by its own
    average price was tried on 2026-08-29 and measures the wrong thing: the
    premarket high is an extreme no whole minute averages near, so a wide
    ranging name scores zero however much it traded.

    Null, not zero, when there is no level or no bar. A window nobody could
    look at and a window with nothing in it are different facts.
    """
    if level is None or not level or not bars:
        return None, None
    floor, ceiling = level * (1.0 - band_pct), level * (1.0 + band_pct)
    volume = 0.0
    minutes = 0
    for bar in bars:
        high, low = bar.get("h"), bar.get("l")
        if high is None or low is None:
            continue
        if float(high) < floor or float(low) > ceiling:
            continue
        volume += float(bar.get("v") or 0)
        minutes += 1
    return round(volume, 2), minutes


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
            candidate["pm_window_thin"] = None
            candidate["pm_window_bars"] = 0
            candidate["pm_window_thin_reason"] = None
            # No bars means no evidence about the level either. UNKNOWN, and
            # never "not flagged", which a reader would take for a clean bill.
            candidate["pm_band_volume"] = None
            candidate["pm_band_minutes"] = None
            candidate["pm_band_notional"] = None
            candidate["pm_band_state"] = BAND_UNKNOWN
            candidate["pm_band_why"] = (
                "the collector has no bars for this name, so nothing is known "
                "about what traded near its premarket high")
            if not on_watchlist:
                candidate["pm_reason"] = (
                    "not on watchlist.json, so the collector never subscribed to it. "
                    "It started gapping after the collector chose its symbols."
                )
            else:
                candidate["pm_reason"] = (
                    "on the watchlist but the collector recorded no bars INSIDE "
                    "THE COLLECTION WINDOW for it. A replayed print from before "
                    "the window is filtered out upstream and is not a bar here, "
                    "so this does not assert the socket was silent all morning"
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

        # THE MORNING'S FILL WARNING. Whether the level this report is about to
        # print as a trigger is one anybody could have transacted at, answered
        # from the only evidence 08:45 has. See CRITERIA [Fill warning] for how
        # weak it is: four of ten genuinely untradeable levels get past it.
        band_volume, band_minutes = band_at_level(
            bars, candidate["pm_high"], _BAND_PCT)
        candidate["pm_band_volume"] = band_volume
        candidate["pm_band_minutes"] = band_minutes
        candidate["pm_band_notional"] = (
            round(band_volume * candidate["pm_high"], 2)
            if band_volume is not None and candidate["pm_high"] else None)
        if candidate["pm_band_notional"] is None:
            candidate["pm_band_state"] = BAND_UNKNOWN
            candidate["pm_band_why"] = (
                "the collector recorded no premarket high for this name, so "
                "there is no level to measure trading around")
        elif candidate["pm_band_notional"] < _MIN_BAND_NOTIONAL:
            candidate["pm_band_state"] = BAND_THIN
            candidate["pm_band_why"] = (
                f"the collector saw {band_volume:,.0f} share(s) over "
                f"{band_minutes} minute(s) within {_BAND_PCT * 100:g} percent "
                f"of {candidate['pm_high']:g}, which is "
                f"{candidate['pm_band_notional']:,.0f} dollars, below the "
                f"{_MIN_BAND_NOTIONAL:,.0f} dollar warning floor. This level "
                "may be a print rather than a market")
        else:
            candidate["pm_band_state"] = BAND_NOT_FLAGGED
            candidate["pm_band_why"] = (
                f"the collector saw {band_volume:,.0f} share(s) over "
                f"{band_minutes} minute(s) within {_BAND_PCT * 100:g} percent "
                f"of {candidate['pm_high']:g}, which is "
                f"{candidate['pm_band_notional']:,.0f} dollars. NOT an "
                "approval: the socket sees a fraction of the tape and this "
                "test misses four of every ten untradeable levels")

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
        # Independent of the flag above and a different fact. A window that
        # opened on time can still hold four minutes of prints, and a window
        # that opened twenty minutes late can hold fifty. Until 2026-08-20 both
        # were "partial", which is true of both and useful about neither: SCSC
        # carried a 16.34 percent gap, a VWAP and a high off FOUR bars holding
        # 1,487 shares that morning, described in the same word as AAP's fifty.
        # See the thin window note in CRITERIA.md.
        candidate["pm_window_thin"] = len(bars) < MIN_BARS_FOR_FULL_WINDOW
        candidate["pm_window_bars"] = len(bars)
        if candidate["pm_window_thin"]:
            candidate["pm_window_thin_reason"] = (
                f"{len(bars)} minute(s) carried a print, below the "
                f"{MIN_BARS_FOR_FULL_WINDOW} in CRITERIA.md [Scan] "
                "min_bars_for_full_window. Every premarket level for this name "
                "rests on those minutes."
            )
        else:
            candidate["pm_window_thin_reason"] = None


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
    """The consolidated premarket volume estimate over the baseline median.

    Never full day relative volume. If the denominator is not trustworthy the
    answer is null and the reason is recorded, because a number computed off the
    wrong denominator is worse than no number.

    The NUMERATOR is not what the collector saw. It is what the collector saw
    divided by that symbol's measured share of the consolidated tape, which
    attach_capture_estimate puts on the candidate as pm_volume_consolidated
    before this runs. The observation itself stays on the row as pm_volume, and
    pm_capture_share and pm_capture_basis say what was done to it and on what
    evidence. Both are on the gate table, so the two divisions can be redone by
    hand. See CRITERIA [Collector] the capture rate note for why: the socket
    carries about a ninth of the tape and the baseline is built from the
    vendor's consolidated bars, so dividing the raw socket count by it compared
    two different tapes and the day screen's 1.5 floor could not be reached.

    The observation used to be the delayed quote's ethVolume. It cannot be:
    that field describes the previous extended session until the vendor rolls
    it, which measurement on 2026-08-14 put after 08:45 and before 08:56. At
    08:45 it gave ARX 20,744,130 shares, which was yesterday's post market,
    against a premarket median of 23.5 shares, for an RVOL of 882,728. The
    collector is still the only OBSERVATION of today's premarket volume on this
    plan, matching the rule that already governs premarket high, low and VWAP.
    Estimating the tape it is a share of does not breach that rule: the
    estimate is derived from the observation and a measured ratio, and no value
    is substituted from another source.

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
                    # How old the DENOMINATOR is. The 07:15 warm recomputes
                    # anything past [Baseline] refresh_after_days and reuses
                    # the rest, which is the design and is invisible: on
                    # 2026-08-20 the report set BLSH's RVOL, whose denominator
                    # was computed six days earlier, beside COIN's, computed
                    # that morning, with nothing to tell them apart. Legal is
                    # not the same as current.
                    "age_days": _baseline_age_days(row.get("computed_at")),
                    "computed_today": _baseline_age_days(row.get("computed_at")) == 0,
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

            # The ESTIMATE, not the observation. The denominator below is the
            # median of the vendor's own consolidated minutes, so dividing the
            # socket's shares by it compares two different tapes. See
            # attach_capture_estimate.
            estimated = _consolidated_volume(candidate)
            if estimated is None:
                candidate["pm_rvol_reason"] = (
                    "the collector recorded no premarket volume for this name"
                )
                continue

            candidate["pm_rvol"] = round(estimated / row["median_volume"], 4)
            candidate["pm_rvol_basis"] = {
                "numerator": estimated,
                "numerator_socket_shares": pm_volume,
                "capture_share": candidate.get("pm_capture_share"),
                "capture_basis": candidate.get("pm_capture_basis"),
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
    _gap_for_stale_baselines(candidates, packet)
    _gap_for_thin_baselines(candidates, packet)


def _baseline_age_days(computed_at: str | None) -> int | None:
    """Whole days between a baseline's computation and this session."""
    if not computed_at:
        return None
    try:
        when = ettime.parse_date(str(computed_at)[:10])
    except ValueError:
        return None
    return (ettime.today_et() - when).days


def _gap_for_subscription_divergence(
    watchlist: dict[str, Any], session_date: str, packet: Packet
) -> None:
    """Say when the collector subscribed to something other than this watchlist.

    The date check in pool_candidates asks whether the FILE ON DISK is today's,
    and that is not the question 2026-08-24 asked. There the collector read the
    previous session's watchlist at 07:55:13 and discover replaced it with a
    today stamped one in the same second. By 08:45 the file was today's, so a
    date check passes, and the collector was still listening to eleven context
    tickers and none of the day's 42 candidates. The file is not the evidence.

    What the collector actually asked the socket for is, and it writes that
    down at subscribe time for exactly this kind of question. Comparing the two
    catches the race the date cannot see, and it also catches the case the date
    does: a collector started on a previous session's file has none of today's
    names in its list however the file is stamped afterwards.

    Silent when they agree, and silent when there is no subscription list at
    all, because build_volume_check already owns and reports that state.
    """
    subscriptions = collect_premarket.read_subscriptions(session_date)
    if not subscriptions:
        return
    requested = {str(s).upper() for s in subscriptions.get("symbols") or []}
    if not requested:
        return
    # Names discover marked subscribed and the collector then cut to fit the
    # socket cap are absent for a reason the collector recorded, so they are
    # not evidence of the wrong file.
    #
    # write_subscriptions serialises this as a list of plain STRINGS,
    # [row.get("symbol") for row in dropped]. The first version of this filter
    # demanded dicts, so the set was always empty and a capped name was
    # reported as proof the collector had been started on another session's
    # file: a false accusation of the one failure this check exists to catch,
    # printed into gaps_to_fill and from there into the report. It stayed
    # latent only because [Discovery] max_subscribed_candidates plus the
    # context tickers lands exactly on the socket cap today, so nothing has
    # been dropped yet. Both shapes are read now, because the cost of being
    # liberal here is nothing and the cost of being wrong is a fabricated
    # accusation in the one document a human reads every morning.
    for_cap = set()
    for row in subscriptions.get("dropped_to_fit_cap") or []:
        name = row.get("symbol") if isinstance(row, dict) else row
        if name:
            for_cap.add(str(name).upper())
    expected = {str(r["symbol"]).upper()
                for r in watchlist.get("symbols", [])
                if r.get("symbol") and r.get("subscribed", True)}
    missing = sorted(expected - requested - for_cap)
    if not missing:
        return
    named = ", ".join(missing[:8])
    more = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
    packet.gap(
        f"the collector subscribed to {len(requested)} symbol(s) at "
        f"{subscriptions.get('subscribed_at') or 'an unrecorded time'}, and "
        f"{len(missing)} of the {len(expected)} name(s) this watchlist marks "
        f"subscribed are NOT among them: {named}{more}. The collector reads the "
        "watchlist once, at subscribe time, so it was started on a different "
        "file from the one in this packet. Any of those names reported below "
        "as having no collector bars was never listened to, and that is NOT "
        "evidence the tape was quiet. See CRITERIA [Monitor], the stale "
        "watchlist note.")


def _gap_for_stale_baselines(candidates: list[dict[str, Any]], packet: Packet) -> None:
    """Name the RVOLs whose denominator was not computed this morning.

    Not a fault and not a threshold. [Baseline] refresh_after_days is 7 and the
    warm legitimately reuses anything younger, so every one of these is inside
    policy. What was missing is that the report presented a denominator from
    six days ago beside one from this morning with no way to tell, and a reader
    comparing two RVOLs was comparing two different vintages without knowing.
    Reported as a fact with its age, never as a warning.
    """
    aged = [
        (c["symbol"], (c.get("baseline") or {}).get("age_days"))
        for c in candidates
        if c.get("pm_rvol") is not None
        and (c.get("baseline") or {}).get("age_days")
    ]
    if not aged:
        return
    aged.sort(key=lambda row: (-(row[1] or 0), row[0]))
    packet.gap(
        f"{len(aged)} premarket RVOL denominator(s) were not computed this "
        "morning and were reused from the baseline cache, which is the design "
        "under CRITERIA.md [Baseline] refresh_after_days and is stated here "
        "because the report otherwise sets them beside same-day ones with "
        "nothing to tell them apart: "
        + ", ".join(f"{symbol} {age} day(s) old" for symbol, age in aged)
    )


THIN_BASELINE_VOLUME = _CRIT.number("baseline", "thin_baseline_premarket_volume")


def _gap_for_thin_baselines(candidates: list[dict[str, Any]], packet: Packet) -> None:
    """Name the RVOLs whose denominator is legal and thin.

    The same shape as _gap_for_stale_baselines above, and for the same reason.
    That one exists because the report set a six day old denominator beside a
    same day one with nothing to tell them apart. This one exists because it
    sets a 1,078 share denominator beside a 740,086 share one, and the reader
    comparing two RVOLs has even less to go on.

    Every row here is INSIDE policy. It cleared
    [Baseline] min_baseline_premarket_volume, its ratio is published, it is
    screened on and it is scored. Nothing is refused and nothing is capped:
    see the floor note in CRITERIA.md for why a cap would be the worse of the
    two errors, and why raising the floor instead is a two part change coupled
    to the float rotation bands.

    The number quoted is measured rather than asserted. On 2026-08-28 the 20
    prior sessions behind all 241 cached baselines were refetched and divided
    by their own medians: below 10,000 shares, 15 to 30 percent of a name's own
    ORDINARY sessions score into the top RVOL band, against 5 percent for names
    above 100,000. A ratio built here is not evidence in the way the same ratio
    on a liquid name is, and the report now says so instead of leaving the two
    looking alike.
    """
    thin = [
        (c["symbol"], (c.get("baseline") or {}).get("median_volume"))
        for c in candidates
        if c.get("pm_rvol") is not None
        and (c.get("baseline") or {}).get("median_volume") is not None
        and (c.get("baseline") or {}).get("median_volume") < THIN_BASELINE_VOLUME
    ]
    if not thin:
        return
    thin.sort(key=lambda row: (row[1], row[0]))
    packet.gap(
        f"{len(thin)} premarket RVOL(s) rest on a THIN denominator: at or above "
        f"the {baseline.MIN_BASELINE_VOLUME:,.0f} share floor in "
        f"{config.CRITERIA_PATH.name} "
        f"[Baseline] min_baseline_premarket_volume, and below the "
        f"{THIN_BASELINE_VOLUME:,.0f} shares that floor note measures as where a "
        "name's own ordinary sessions stop reaching the top band by construction. "
        "Measured 2026-08-28: under 10,000 shares, 15 to 30 percent of a name's own "
        "ordinary premarket sessions score above 3 times its own median, against 5 "
        "percent above 100,000. These ratios are published, screened on and scored "
        "like the rest, and they are named here because the report otherwise sets "
        "them beside a ratio built on a denominator hundreds of times larger with "
        "nothing to tell them apart: "
        + ", ".join(f"{symbol} on a {median:,.0f} share median"
                    for symbol, median in thin)
    )


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

    The DIRECTION comes from the check and is never assumed. Until 2026-08-20
    this function wrote "an RVOL below is understated by about that much again"
    off a median ABSOLUTE difference, which cannot carry a sign, and
    doc/research/COLLECTOR_VOLUME.md had already recorded the collector wrong
    in both directions: 2026-08-14 came back 3.83 times the vendor in aggregate
    against 2026-08-17 at -88.49 percent. So the check now returns a signed
    median, an aggregate ratio and the direction those two agree on, this reads
    it, and a reading that carries no sign, which every summary written before
    that date does, says the direction is unknown rather than guessing it.
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
    signed = check.get("median_signed_pct")
    if signed is not None:
        detail += f", signed median {signed:+.1f} percent"
    ratio = check.get("aggregate_ratio")
    if ratio is not None:
        detail += f", aggregate {ratio:.2f} times the vendor's volume"
    # The symbols the measurement never reached. Publishing compared and
    # unavailable alone read as though they partitioned the subscription, and
    # on 2026-08-20 two subscribed names were in neither.
    silent = check.get("collector_silent")
    if silent:
        detail += (f", with {silent} subscribed symbol(s) the collector never "
                   "heard and so never compared")
    zero = check.get("vendor_zero_volume")
    if zero:
        detail += (f" and {zero} where the vendor reported no volume on the "
                   "common minutes")

    # What this check MEANS changed on 2026-08-21 and this text did not follow
    # it for one morning. Until commit a62429b the disagreement measured here
    # passed straight into both ratios, so the honest consequence was that
    # every RVOL was wrong by about this much. attach_capture_estimate now
    # divides that exact disagreement out per symbol before either ratio is
    # computed: this check is the SOURCE of the correction factor, not an error
    # sitting on top of it.
    #
    # Saying otherwise is not a stale sentence, it is a double count in the
    # reader's head, and the size of it is the size of the defect the
    # correction was built to fix. runs/2026-08-21/report.md published it
    # twice, telling a reader that MSTR's 3.38 understates by 87 percent when
    # 3.38 already carries that correction.
    #
    # What actually survives the correction is the DISPERSION of the share, not
    # its level: a symbol's share moves about 1.5 times across sessions where
    # the level is about nine. See CRITERIA [Collector] premarket_capture_rate.
    direction = check.get("direction") or "unknown"
    if direction in ("under", "over"):
        consequence = (
            "That gap is what the capture correction divides out: it IS "
            "pm_capture_share, applied per symbol, so it is the input to every "
            "RVOL and float rotation here rather than an error left inside "
            "them. What survives is the share's session to session dispersion, "
            "about 1.5 times against a level of about nine, so a ratio here is "
            "an estimate with that much play in it")
    elif direction == "mixed":
        consequence = (
            "The disagreement ran in BOTH directions on that session, the "
            "typical symbol falling on one side of the vendor and the aggregate "
            "tape on the other. The correction is applied per symbol, so each "
            "row is divided by its own share and the mixed aggregate does not "
            "describe any single row, but a session whose symbols disagree in "
            "sign is a session whose shares are less trustworthy than usual")
    else:
        consequence = (
            "That reading carries no sign, having been written before the check "
            "recorded one, so the DIRECTION of the disagreement is unknown and "
            "must not be described as understatement. The per symbol shares "
            "are still read from it where it carries them, and a symbol it "
            "does not carry falls back to the measured default")
    consequence += (
        ". The remaining reason a ratio here is a LOWER BOUND is the window, "
        "not the feed: the numerator covers the collector window and the "
        "denominator covers the whole premarket.")

    if check["stale"]:
        packet.gap(
            f"the collector volume check is {check['age_days']} days old, past "
            f"the {check['max_age_days']} day limit in CRITERIA.md [collector], "
            f"so the per symbol capture shares this morning's ratios are built "
            f"on are that old too, and a symbol it does not carry falls back to "
            f"CRITERIA [Collector] premarket_capture_rate. Last reading: "
            f"{detail}."
        )
    else:
        packet.gap(f"{detail}. {consequence}")
    return _packet_safe_volume_check(check)


# The keys the packet may carry from the volume check. Everything the report
# and the fallback quote is a SCALAR; the four per symbol structures the check
# also returns exist for a human reading runs/<date>/verify_intraday.json.
#
# They must not reach the packet, and the reason is the containment checker.
# analyst._packet_uppercase_tokens builds the allowed set out of the raw packet
# TEXT, and _TOKEN_RE finds AVGO inside the key "AVGO.US", so every symbol in
# minutes_compared_by_symbol, unavailable_symbols, vendor_zero_volume_symbols
# and collector_silent_symbols would become a claimable ticker for the morning.
# That is the PREVIOUS session's collector roster, 73 names on 2026-08-19, and
# the morning holds no evidence about any of them. Measured on the real
# 2026-08-20 packet: ten large liquid listings, AMAT, AVGO, DE, HOOD, MU, NOK,
# RIOT, SAP, TLT and TSM, moved from invented to allowed, which is exactly the
# set a model reaches for when it writes a market context sentence. The guard
# that exists to catch invented evidence would have been widened by the
# instrument it reports on.
_PACKET_VOLUME_CHECK_KEYS = (
    "day", "compared", "within_one_percent", "median_abs_pct",
    "median_signed_pct", "aggregate_ratio", "direction", "direction_phrase",
    "collector_volume_total", "intraday_volume_total",
    "symbols_collector_below_vendor", "symbols_collector_above_vendor",
    "minutes_compared_total", "unavailable", "vendor_zero_volume",
    "collector_silent", "subscribed", "subscribed_reason", "sign_recorded",
    "age_days", "max_age_days", "stale", "source",
)


def _packet_safe_volume_check(check: dict[str, Any]) -> dict[str, Any]:
    """The check with its per symbol evidence left in the file it came from.

    A whitelist rather than a blacklist, so a key added to the check later
    stays out of the packet until somebody decides it belongs there. See
    _PACKET_VOLUME_CHECK_KEYS above for what a blacklist would have cost.
    """
    return {key: check[key] for key in _PACKET_VOLUME_CHECK_KEYS if key in check}


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
        c for c in candidates
        if (c.get("day_failed_conditions") or []) == ["premarket_rvol"]
    ]
    # A FAILED CONDITION AND AN UNMEASURED ONE ARE NOT THE SAME FACT, which is
    # the distinction screen_tally was given a third count for on 2026-08-20 and
    # this line then undid. A candidate whose pm_rvol is null failed the RVOL
    # line because there was nothing to test, not because a corrected numerator
    # fell short, and the sentence below asserted "their RVOL already carries
    # the capture correction" over both. For a null RVOL that is a statement
    # about a number that does not exist, and it points a reader at the feed
    # shortfall as an answer where the answer is that nothing was measured.
    measured = [c["symbol"] for c in blocked
                if _as_float(c.get("pm_rvol")) is not None]
    unmeasured = [c["symbol"] for c in blocked
                  if _as_float(c.get("pm_rvol")) is None]
    if measured:
        packet.gap(
            f"{len(measured)} of {len(candidates)} candidates failed the day "
            "screen on a MEASURED premarket RVOL alone, having cleared the "
            "other day conditions: "
            + ", ".join(measured)
            + ". Their RVOL already carries the capture correction, so these "
            "are names the corrected numerator still could not lift over the "
            "floor, NOT names the feed shortfall cost. capture_correction in "
            "this packet names the ones the correction did carry."
        )
    if unmeasured:
        packet.gap(
            f"{len(unmeasured)} of {len(candidates)} candidates failed the day "
            "screen on premarket RVOL alone and have NO RVOL AT ALL: "
            + ", ".join(unmeasured)
            + ". Nothing was measured for them, so the capture correction "
            "carries nothing here and the floor was not tested against a "
            "number. This is a missing instrument, not a verdict about the "
            "name, and it is counted apart from the names above for that "
            "reason."
        )
    return measured + unmeasured


def _consolidated_volume(candidate: dict[str, Any]) -> float | None:
    """The consolidated volume estimate, whether or not the attach step ran.

    Both ratio measures need it and both used to divide the raw socket volume,
    so a caller that skips attach_capture_estimate must not quietly get the old
    broken arithmetic back. It must also not get a null, because the fallback
    that matters here is CRITERIA's measured default and that is available to
    anybody: a hard ordering dependency between two attach functions is a seam,
    and this repository has paid for those before.

    So: use the attached estimate when there is one, and otherwise compute one
    from the default and RECORD that this is what happened, so a reader of the
    basis can tell a per symbol measurement from a file wide default.
    """
    estimated = _as_float(candidate.get("pm_volume_consolidated"))
    if estimated is not None:
        return estimated
    volume = _as_float(candidate.get("pm_volume"))
    if volume is None:
        return None
    share = _CRIT.number("collector", "premarket_capture_rate")
    candidate["pm_capture_share"] = round(share, 6)
    candidate["pm_capture_basis"] = (
        "CRITERIA [Collector] premarket_capture_rate, reached without a volume "
        "check having been attached")
    estimated = round(volume / share, 2)
    candidate["pm_volume_consolidated"] = estimated
    return estimated


def attach_capture_estimate(
        candidates: list[dict[str, Any]],
        check: dict[str, Any] | None,
        packet: Packet) -> None:
    """Scale collector volume to what the consolidated tape would have shown.

    The collector hears a fraction of the consolidated tape. Both volume RATIOS
    divide it by a denominator measured on the WHOLE tape: RVOL by a baseline
    collect/baseline.py builds from the vendor's 1m intraday bars, and float
    rotation by a share count, against bands fitted on Alpaca volume. So both
    understate by about the reciprocal of that fraction, and the [Day setup]
    premarket_rvol floor of 1.5 was being applied to a number that could not
    reach it. Six mornings, 62 candidates, zero day eligible, 19 of them
    failing on that line alone.

    pm_volume stays exactly what it was, the shares the collector actually saw,
    because that is an observation and observations are not adjusted here.
    pm_volume_consolidated is the ESTIMATE, named as one, and it is what the
    two ratios divide.

    The share comes from the symbol's own collector over vendor ratio in the
    newest verify_intraday.json where that check carries one, and from
    CRITERIA [Collector] premarket_capture_rate where it does not. Never from a
    guess and never from 1.0: a check written before 2026-08-21 carries no per
    symbol volumes at all, and treating that absence as agreement between the
    tapes is the mistake this whole correction exists to undo.

    Why this is allowed to be one number per symbol rather than a distribution:
    measured over the four sessions from 2026-08-17, a symbol's share varies by
    a median of 1.48 times across sessions while the error being corrected is
    about nine. See CRITERIA's capture rate note for the derivation and for
    what would retire it.
    """
    default = _CRIT.number("collector", "premarket_capture_rate")
    min_vendor = _CRIT.number("collector", "min_capture_vendor_volume")
    min_minutes = _CRIT.integer("collector", "min_capture_minutes")
    per_symbol = (check or {}).get("volume_by_symbol") or {}
    minutes_by = (check or {}).get("minutes_compared_by_symbol") or {}
    measured_day = (check or {}).get("day")

    for candidate in candidates:
        candidate["pm_volume_consolidated"] = None
        candidate["pm_capture_share"] = None
        candidate["pm_capture_basis"] = None
        candidate["pm_capture_minutes"] = None

        volume = _as_float(candidate.get("pm_volume"))
        row = per_symbol.get(candidate["symbol"])
        minutes = minutes_by.get(candidate["symbol"])
        share = None
        basis = None
        if isinstance(row, dict):
            vendor = _as_float(row.get("vendor"))
            mine = _as_float(row.get("collector"))
            # A share is a RATIO OF TWO VOLUMES and it inherits the frailty of
            # the smaller one. Measured across 202 symbol sessions: UUP was ten
            # vendor shares against ten collector shares over one minute, which
            # produced a share of 1.0 and therefore no correction at all for a
            # symbol that ordinarily captures about a tenth; VNET produced
            # 1.18, which is impossible for a venue subset. Every share above
            # 0.9 in that population sat under a thousand vendor shares.
            #
            # This is the same guard, and the same argument, as [Baseline]
            # min_baseline_premarket_volume: floor the EVIDENCE, never cap the
            # ratio, because a cap turns a visible absurdity into an invisible
            # one. Below the floor the symbol takes the measured default, which
            # is a worse estimate than a good measurement and a far better one
            # than a bad measurement.
            thin = None
            if vendor is None or mine is None or vendor <= 0:
                thin = "the check carries no usable volume pair for this symbol"
            elif vendor < min_vendor:
                thin = (f"it rested on {vendor:,.0f} vendor share(s), under the "
                        f"{min_vendor:,.0f} floor")
            elif minutes is not None and minutes < min_minutes:
                thin = (f"it rested on {minutes} common minute(s), under the "
                        f"{min_minutes} floor")
            elif mine / vendor >= 1.0:
                thin = (f"it came out at {mine / vendor:.2f}, and a socket that "
                        "carries a subset of the tape cannot report all of it")
            if thin is None:
                share = mine / vendor
                candidate["pm_capture_minutes"] = minutes
                basis = (f"this symbol's own collector over vendor share on "
                         f"{measured_day}, over "
                         f"{minutes if minutes is not None else 'an unrecorded number of'} "
                         f"common minute(s)")
            else:
                basis = ("CRITERIA [Collector] premarket_capture_rate, because "
                         f"this symbol's measured share was refused: {thin}")
        if share is None or share <= 0:
            if basis is None:
                basis = ("CRITERIA [Collector] premarket_capture_rate, because "
                         "the newest volume check carries no share for this "
                         "symbol")
            share = default

        candidate["pm_capture_share"] = round(share, 6)
        candidate["pm_capture_basis"] = basis
        if volume is not None:
            candidate["pm_volume_consolidated"] = round(volume / share, 2)


def capture_correction_report(
        candidates: list[dict[str, Any]], packet: Packet) -> dict[str, Any] | None:
    """What the correction moved, so it is auditable rather than invisible.

    A correction that silently changes which names reach a watchlist is worse
    than the defect it fixes, because the defect at least produced a number
    somebody could disbelieve. This reports the raw ratio beside the corrected
    one for every candidate and names the ones the correction carried across
    the day screen's floor.
    """
    floor = _CRIT.rule("day_setup", "premarket_rvol")
    rows: list[dict[str, Any]] = []
    carried: list[str] = []
    onto: list[str] = []
    for candidate in candidates:
        corrected = _as_float(candidate.get("pm_rvol"))
        share = _as_float(candidate.get("pm_capture_share"))
        if corrected is None or not share:
            continue
        raw = round(corrected * share, 4)
        rows.append({"symbol": candidate["symbol"], "pm_rvol": corrected,
                     "on_socket_volume": raw,
                     "capture_share": candidate.get("pm_capture_share"),
                     "capture_minutes": candidate.get("pm_capture_minutes"),
                     "capture_basis": candidate.get("pm_capture_basis")})
        if floor.test(corrected) and not floor.test(raw):
            carried.append(candidate["symbol"])
            # Clearing ONE condition is not reaching a watchlist. On the first
            # live morning HOOD cleared this floor on the correction and failed
            # the prior day high, and the report named it as though the
            # correction had put it on the day list. Two sets, because they
            # answer two questions.
            if candidate.get("day_eligible"):
                onto.append(candidate["symbol"])

    if not rows:
        return None
    block = {
        "floor": floor.describe(),
        "candidates": len(rows),
        "clear_on_socket_volume": sum(
            1 for r in rows if floor.test(r["on_socket_volume"])),
        "clear_on_consolidated_estimate": sum(
            1 for r in rows if floor.test(r["pm_rvol"])),
        "carried_across_the_floor": carried,
        "carried_onto_the_day_watchlist": onto,
        "shares_from_this_symbols_own_measurement": sum(
            1 for r in rows if str(r["capture_basis"] or "").startswith("this symbol")),
        # The number every name without its own measurement was divided by,
        # carried so the disclaimer can quote it rather than the model being
        # asked to remember a CRITERIA value it cannot see.
        "default_capture_share": _CRIT.number(
            "collector", "premarket_capture_rate"),
        "rows": rows,
    }
    packet.gap(
        "premarket RVOL and float rotation are computed on an ESTIMATE of "
        "consolidated premarket volume, not on the shares the collector saw: "
        "the socket carries a measured fraction of the tape and both "
        "denominators are whole tape measurements. Against the raw socket "
        f"numerator {block['clear_on_socket_volume']} of {len(rows)} "
        f"candidates would clear the day screen's {floor.describe()}; on the "
        f"estimate {block['clear_on_consolidated_estimate']} do"
        + (", and the correction carried " + ", ".join(carried)
           + " across that floor" if carried
           else ", and the correction carried none of them across that floor")
        + (", of which " + ", ".join(onto) + " reached the day watchlist"
           if onto else ", and none of them reached the day watchlist")
        + ". Clearing the volume floor is one condition, not membership. Every "
          "row states the share used, how many common minutes backed it, and "
          "where it came from. See CRITERIA [Collector] "
          "premarket_capture_rate.")
    return block


def attach_float_rotation(candidates: list[dict[str, Any]], packet: Packet) -> None:
    """The consolidated premarket volume estimate divided by shares float.

    The second volume measure, and the reason it exists is the first one's
    blind spot. RVOL divides by a cached baseline, so it is null for any name
    that has never been baselined, which is every name on its first appearance
    and every name the weekly universe rebuild has just admitted. Those are not
    marginal names: a name showing up for the first time is often exactly the
    one worth looking at. Float rotation needs no history at all, so it is
    computable from the first minute a name trades, and the two are scored as
    alternatives filling one slot rather than as two requirements.

    The numerator is the same pm_volume_consolidated RVOL uses, and it has to
    be: the bands below were fitted on Alpaca volume, which is consolidated, so
    a socket numerator would be scored against edges measured on a tape nine
    times larger. The window lower bound still applies and is flagged the same
    way: the collector starts at 07:20 and the premarket opens at 04:00, so
    this understates rotation over the full session. That direction is the safe
    one, as it can only hold a candidate down a band, never lift it up one.
    What is NOT a lower bound any more is the feed gap, which the capture
    correction divides out before this function sees the number.

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

    # Named once at the end rather than gapped one by one. On the thin quota
    # path this is every candidate and the same sentence twelve times is not
    # twelve findings, it is one.
    quote_never_fetched: list[str] = []

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
        # Tested before the quote is blamed for anything. A quote that was
        # never fetched is not a quote the vendor answered thinly, and until
        # 2026-08-20 this function could not tell the two apart: it saw an
        # empty dict either way and reported the vendor's silence. The thin
        # quota path sets quote_skipped one line after it sets catalyst_error,
        # so the real reason is on the candidate and only had to be read.
        if candidate.get("quote_skipped") and share_float is None:
            candidate["pm_float_rotation_reason"] = (
                "the delayed quote was never fetched, so there is no sharesFloat "
                "to divide by: " + str(candidate["quote_skipped"])
            )
            quote_never_fetched.append(candidate["symbol"])
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

        # Same estimate as RVOL uses, and for the same reason twice over:
        # a float is a whole company share count, and the bands in
        # CRITERIA were fitted on Alpaca volume, which is consolidated.
        # DECISIONS.md 2026-08-17 seventh recorded that mismatch and this
        # is what answers it.
        estimated = _consolidated_volume(candidate)
        if estimated is None:
            candidate["pm_float_rotation_reason"] = (
                "the collector recorded no premarket volume for this name"
            )
            continue
        candidate["pm_float_rotation"] = round(estimated / share_float, 8)
        candidate["pm_float_rotation_basis"] = {
            "numerator": estimated,
            "numerator_socket_shares": pm_volume,
            "capture_share": candidate.get("pm_capture_share"),
            "capture_basis": candidate.get("pm_capture_basis"),
            "numerator_source": f"collector, from {numerator_window} ET",
            "denominator": share_float,
            "denominator_source": "sharesFloat from the delayed quote",
            "shares_outstanding": outstanding if outstanding_usable else None,
            "shares_outstanding_source": outstanding_source,
            # True for the same reason RVOL's is: the collector starts after
            # the premarket does, so the numerator is short of the full window.
            "is_lower_bound": numerator_window > true_open,
        }

    if quote_never_fetched:
        packet.gap(
            f"float rotation is null for {len(quote_never_fetched)} of "
            f"{len(candidates)} candidates because the delayed quote was never "
            "fetched, not because the vendor carried no sharesFloat: "
            + ", ".join(quote_never_fetched)
        )


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


def _article_key(headline: dict[str, Any]) -> str:
    """One article, one key, so the same story is recognised across candidates.

    The url when the feed gave one, because two candidates handed the same
    story are handed the same link. The title is the fallback. A row carrying
    neither is unique to itself rather than silently merged with every other
    untitled row, since merging them would invent a breadth nobody measured.
    """
    url = str(headline.get("url") or "").strip()
    if url:
        return f"url:{url}"
    title = str(headline.get("title") or "").strip()
    return f"title:{title}" if title else f"row:{id(headline)}"


def _scope_articles(
    fetched: dict[str, list[dict[str, Any]]], candidate_count: int
) -> None:
    """Decide, per candidate, which of its articles are actually ABOUT it.

    EODHD news tags are ARTICLE scoped, not company scoped, and until
    2026-08-20 every tag on every kept headline was read as a tag about
    whichever name the feed had returned it for. A multi company roundup
    therefore conferred its strongest class on every one of them. That morning
    the CNBC piece "Stocks making the biggest moves premarket: Walmart,
    Coinbase, Moderna, Alibaba and more" carried 46 tags naming 45 companies,
    EARNINGS among them, which belongs to Walmart. MSTR, COIN and MARA were
    all classed earnings off it and BLSH off "Biggest stock movers Thursday:
    Crypto stocks, WOLF, and more". Class earnings is worth 3 of the score's
    10 points, so MSTR published green at 7.0 on a class it does not have and
    three more names published yellow at 6.0.

    The obvious fix does not work and it is worth saying why, because it is
    the first thing a reader will reach for. attach_catalysts already filters
    on the feed's own symbols array, and every roundup in that packet carried
    an EMPTY one, so the filter was skipped and could not be tightened into
    anything. The article really is associated with the candidate. What is
    wrong is treating all of its tags as tags about the candidate.

    So breadth is measured instead, by two counts, because neither one sees
    the whole thing and this project holds no offline list of company names to
    count issuers against directly.

      tag_count     how many tags the article carries. A wire roundup lists
                    every issuer it touched, so the CNBC piece ran to 46
                    against a maximum of 7 on the single company releases the
                    same morning. This is the count that catches a roundup
                    even on a morning where only one candidate was handed it.
      returned_for  how many of this morning's candidates the feed handed this
                    same article to. A story given to seven of twelve names is
                    not about any one of them, and this is the only count that
                    catches a roundup tagged by TOPIC rather than by issuer:
                    "Biggest stock movers Thursday" carries seven purely
                    topical tags, so its tag count is unremarkable, and it went
                    to three candidates. It is counted over the candidates
                    whose news call ANSWERED, which is what the scope publishes
                    as its denominator; the packet count is published beside it
                    because the two differ on any morning that lost a call, and
                    a numerator taken from one set against a denominator taken
                    from the other is not a ratio.

    Both have to sit inside their CRITERIA.md [Score catalyst tags] limits
    before an article's tags are allowed to classify a name. A name whose
    every article is a roundup comes out class "none" with catalyst_found
    still true, which is the existing legal state meaning the window was
    checked and paid nothing. It is NOT null: null means the feed was never
    checked at all, and the two must not be confused.
    """
    max_tags = _CRIT.integer("score_catalyst_tags", "max_tags_for_one_company")
    max_sharing = _CRIT.integer("score_catalyst_tags", "max_candidates_sharing_article")

    returned_for: dict[str, set[str]] = {}
    for symbol, articles in fetched.items():
        for article in articles:
            returned_for.setdefault(_article_key(article), set()).add(symbol)

    # The denominator the sharing count actually belongs to. `fetched` holds
    # one entry per candidate whose news call ANSWERED, and candidate_count is
    # the whole packet, so on a morning where some calls failed the two are
    # different numbers and until 2026-08-20 the second one was published
    # beside a numerator drawn from the first: "returned for 3 of this
    # morning's 12 candidates" when only five were ever asked. The threshold
    # is absolute, so nothing about which articles are called roundups moves
    # here, but the ratio a reader and the model are handed does, and it moves
    # in the direction that makes a wire roundup look narrow.
    checked = len(fetched)
    unchecked = max(candidate_count - checked, 0)
    # And with a call missing, `shared` is a floor rather than a count: an
    # article the feed would have handed to an unchecked candidate cannot be
    # seen to have been. Said out loud rather than acted on, because guessing
    # the missing side would invent breadth, and the cost of being wrong here
    # is a class withheld rather than a class invented.
    floor = (f"; {unchecked} candidate(s) had no news call answered, so this "
             "sharing count is a floor") if unchecked else ""

    for symbol, articles in fetched.items():
        for article in articles:
            shared = len(returned_for.get(_article_key(article)) or {symbol})
            tags = len(article.get("tags") or [])
            wide_tags = tags > max_tags
            wide_feed = shared > max_sharing
            if wide_tags and wide_feed:
                why = (f"a roundup on both counts: {tags} tags, above {max_tags}, "
                       f"and returned for {shared} of the {checked} candidate(s) "
                       f"whose news was checked, above {max_sharing}{floor}")
            elif wide_tags:
                why = (f"a roundup: {tags} tags, above the {max_tags} a single "
                       "company article carries, so its tags name the issuers it "
                       "lists rather than this one")
            elif wide_feed:
                why = (f"a roundup: the feed returned it for {shared} of the "
                       f"{checked} candidate(s) whose news was checked, above "
                       f"{max_sharing}, so its tags are not about any one of "
                       f"them{floor}")
            else:
                why = (f"about this name: {tags} tag(s), returned for {shared} of "
                       f"the {checked} candidate(s) whose news was checked{floor}")
            article["article_scope"] = {
                "tag_count": tags,
                "returned_for_candidates": shared,
                "candidates_checked": checked,
                "candidates_in_packet": candidate_count,
                "about_this_name": not (wide_tags or wide_feed),
                "why": why,
            }


def _polarity_counts(
    headlines: list[dict[str, Any]], negative_at: float, positive_at: float
) -> dict[str, Any]:
    """Split a headline list by the vendor's polarity, counting what it cannot score.

    Its own function because two callers need it over two different lists.
    attach_catalysts counts over the WHOLE window, which is the balance the
    trap rule was written for; attach_traps falls back to the displayed list
    when it is handed a candidate nobody counted, and says which it used.
    """
    scored: list[float] = []
    unscored = 0
    for headline in headlines:
        value = _as_float((headline.get("sentiment") or {}).get("polarity"))
        if value is None:
            unscored += 1
        else:
            scored.append(value)
    return {
        "scored": len(scored),
        "unscored": unscored,
        "negative": sum(1 for v in scored if v <= negative_at),
        "positive": sum(1 for v in scored if v >= positive_at),
        "mean_polarity": (round(sum(scored) / len(scored), 4) if scored else None),
    }


def attach_catalysts(
    api: eodhd.EodhdClient, candidates: list[dict[str, Any]], packet: Packet
) -> None:
    """News carrying the EODHD symbol tag, over the last N hours.

    The symbol tag is the entire filter. No keyword matching, no company name
    regex, no stopword list. If the feed has nothing tagged with the symbol,
    catalyst_found is false and that is a finding, not a gap to paper over.

    Two things are settled here that used to be settled downstream on the
    truncated list, and both were wrong for the same reason: news_keep is a
    DISPLAY cap and nothing more.

    The polarity balance is the first. attach_traps weighed candidate
    ["headlines"], which is recent[:news_keep] with news_keep at 3, while
    news_in_window recorded the true count beside it. On 2026-08-20 WMT
    published trap=False on 3 of 45 headlines, COIN on 3 of 24 and BABA on 3
    of 17, and since min_headlines_for_balance is 2 and the sample can never
    exceed 3, one negative against zero positives satisfied "strictly more
    negative than positive". That is a verdict resting on one mis-scored
    headline, which is exactly what the balance rule was written that same day
    to stop. So the counts are taken over the whole window here and handed on.

    Article scope is the second, and _scope_articles carries the argument.
    """
    hours = _CRIT.integer("scan", "news_lookback_hours")
    keep = _CRIT.integer("scan", "news_keep")
    negative_at = _CRIT.number("traps", "negative_polarity")
    positive_at = _CRIT.number("traps", "positive_polarity")
    now = ettime.now_et()
    since = now - dt.timedelta(hours=hours)

    fetched: dict[str, list[dict[str, Any]]] = {}
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
        fetched[candidate["symbol"]] = recent

    # After every candidate, because how many of them the feed handed an
    # article to is one of the two breadth counts and it cannot be known one
    # candidate at a time.
    _scope_articles(fetched, len(candidates))

    for candidate in candidates:
        recent = fetched.get(candidate["symbol"])
        if recent is None:
            # The news call failed for this one; the loop above already
            # recorded the error and left catalyst_found unknown.
            continue
        counts = _polarity_counts(recent, negative_at, positive_at)
        counts["counted_over"] = len(recent)
        counts["source"] = ("every headline the feed returned inside the window, "
                            "not the news_keep displayed beside it")
        candidate["headline_polarity"] = counts
        candidate["headlines"] = recent[:keep]
        candidate["catalyst_found"] = bool(recent)
        candidate["news_in_window"] = len(recent)
        candidate["headlines_note"] = (
            f"{len(recent)} headline(s) carried the symbol tag in the window and "
            f"the {len(recent[:keep])} newest are kept here, a display cap from "
            "CRITERIA.md [Scan] news_keep. The trap balance is decided over all "
            "of them; the catalyst class is read from the ones kept.")


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

    trap_basis obeys the same rule, and until 2026-08-20 it did not. Where the
    window was never read the headline counts are NULL with the reason beside
    them, because a zero there is a claim that the feed was checked and held
    nothing, which is a different fact and one this packet may not invent.
    """
    negative_at = _CRIT.number("traps", "negative_polarity")
    positive_at = _CRIT.number("traps", "positive_polarity")
    minimum = _CRIT.integer("traps", "min_headlines_for_balance")
    min_gap = _CRIT.number("traps", "min_gap_pct")

    flagged: list[str] = []
    for candidate in candidates:
        displayed = candidate.get("headlines") or []
        counts = candidate.get("headline_polarity")
        over_window = counts is not None
        # catalyst_found None means the window was never read at all: the news
        # call failed, or the thin quota path skipped it to protect the shared
        # meter. Until this line existed such a candidate fell into the
        # fallback below, counted an empty displayed list, and published
        # headlines_scored 0, headlines_unscored 0 and headlines_in_window 0.
        # That is byte for byte the trap_basis of a name whose window WAS read
        # and held nothing, which is what SCSC and ASST published on
        # 2026-08-20, so the packet gave a reader no way to tell an unknown
        # from a measured zero. An unknown written as a zero is the failure
        # this file spends its length on, so the counts are null here and the
        # reason the feed went unread sits beside them in counted_over.
        unchecked = candidate.get("catalyst_found") is None
        if unchecked:
            counts = {"scored": None, "unscored": None, "negative": None,
                      "positive": None, "mean_polarity": None,
                      "counted_over": None}
        elif not over_window:
            # A candidate nobody counted: a packet rescored from before
            # attach_catalysts recorded the window counts, or a caller handing
            # this function a bare headline list. The displayed list is then
            # all there is, and the basis says which one it read rather than
            # presenting three of forty five as though they were the window.
            counts = _polarity_counts(displayed, negative_at, positive_at)
            counts["counted_over"] = len(displayed)

        if unchecked:
            counted_over = (
                "nothing was counted, because the news feed was never read for "
                "this candidate. The counts above are unknown and not zero: "
                + (candidate.get("catalyst_error")
                   or "no reason for that was recorded"))
        elif over_window:
            counted_over = "every headline the feed returned inside the window"
        else:
            counted_over = ("the displayed headlines only, because no window "
                            "count was recorded for this candidate")

        scored_count = counts["scored"]
        negatives = counts["negative"]
        positives = counts["positive"]
        basis = {
            # Over the WHOLE window, not the displayed three. Until 2026-08-20
            # these were counted off candidate["headlines"], which news_keep
            # caps at 3, and trap_basis then published headlines_scored 3 and
            # headlines_unscored 0 for a name with 45 headlines: 42 counted
            # nowhere, in a pair of fields that read as a partition of the
            # coverage. The two below plus nothing else now sum to
            # headlines_in_window, and all three are null together when the
            # window was never read, because a partition of nothing measured
            # is not a partition of zero headlines.
            "headlines_scored": scored_count,
            "headlines_unscored": counts["unscored"],
            "headlines_in_window": counts["counted_over"],
            # Measured either way: this is how many headlines the packet puts
            # in front of a reader, and on the unread path that really is zero.
            "headlines_displayed": len(displayed),
            "counted_over": counted_over,
            "negative": negatives,
            "positive": positives,
            "negative_at_or_below": negative_at,
            "positive_at_or_above": positive_at,
            "mean_polarity": counts["mean_polarity"],
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
            # The reason is quoted from catalyst_error rather than asserted.
            # This line used to read "the news call failed" whatever had
            # happened, and on the thin quota path nothing had failed: the call
            # was skipped to protect a shared meter, which the packet already
            # said one function earlier and this one contradicted.
            candidate["trap_why"] = (
                "there is no headline set to weigh, so trap is unknown rather "
                "than absent: "
                + (candidate.get("catalyst_error")
                   or "the news feed was never checked"))
        elif gap is None or gap < min_gap:
            candidate["trap"] = None
            candidate["trap_why"] = (
                f"a trap is a gap UP contradicted by its news; this gap is "
                f"{'null' if gap is None else format(gap, '.2f') + ' percent'}, "
                f"below the {min_gap:g} percent this question is asked above")
        elif scored_count < minimum:
            candidate["trap"] = None
            candidate["trap_why"] = (
                f"{scored_count} scored headline(s) of {counts['counted_over']} "
                f"in the window, below the {minimum} needed for a balance; on "
                "fewer than that the balance IS the single worst headline, "
                "which is the reading this rule exists to stop")
        elif negatives > positives:
            candidate["trap"] = True
            candidate["trap_why"] = (
                f"gaps up {gap:.2f} percent while {negatives} of "
                f"{scored_count} scored headlines are negative at or below "
                f"{negative_at:g} against {positives} positive at or above "
                f"{positive_at:g}, counted over "
                f"{counts['counted_over']} headline(s) in the window")
            flagged.append(candidate["symbol"])
        else:
            candidate["trap"] = False
            candidate["trap_why"] = (
                f"gaps up {gap:.2f} percent and its headlines do not contradict "
                f"it: {negatives} negative against {positives} "
                f"positive of {scored_count} scored, counted over "
                f"{counts['counted_over']} headline(s) in the window")

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
        today.isoformat(), end.isoformat()],
        # WHETHER THE CALENDAR WAS ASKED, not what it answered. Empty means two
        # different things and until 2026-08-22 the block could not tell them
        # apart: a calendar that was read and held no candidate, and a call that
        # failed. classify_catalyst reads "on the earnings calendar" as a fact
        # rather than an interpretation and consults it FIRST, so an empty list
        # off a failed call made every candidate not-on-the-calendar, changed
        # catalyst_class, changed the score it is worth in
        # [Score catalyst class], changed the conviction, and changed swing
        # membership through require_catalyst. The report then read the same
        # empty list as "no notable earnings".
        "candidates_checked": None, "tomorrow_checked": None}

    if symbols:
        rows, error = api.earnings_calendar(
            today - dt.timedelta(days=1), end, symbols=symbols
        )
        out["candidates_checked"] = not error
        if error:
            out["candidates_error"] = str(error)
            packet.gap(
                f"earnings calendar for the candidates failed: {error}. Every "
                "candidate's catalyst class was decided WITHOUT it, so a name "
                "reporting today reads as one that is not on the calendar")
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
    out["tomorrow_checked"] = not error
    if error:
        # `skipped` is the field REPORT_TEMPLATE.md and analyst.fallback_report
        # both branch on, and it was set only on the quota degrade path. A
        # failed call returned here with notable_tomorrow empty and no marker at
        # all, so both renderers published "No notable earnings in the packet
        # window" for a window nobody looked at.
        out["skipped"] = f"the earnings calendar call failed: {error}"
        out["tomorrow_error"] = str(error)
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

    Only tags from an article that is ABOUT this candidate are read. EODHD
    tags are article scoped, so a multi company roundup used to confer its
    strongest class on every name the feed returned it for, which is how MSTR,
    COIN, MARA and BLSH came out class earnings on 2026-08-20 while none of
    them was on the calendar. _scope_articles decides which is which and the
    why below names the article that paid, and how wide it was, so a reader
    can audit the call rather than take it.

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

    kept = candidate.get("headlines") or []
    best_class = "none"
    best_points = -1.0
    matched_tag = None
    matched_article: dict[str, Any] | None = None
    roundups = 0
    widest: tuple[int, Any, Any] | None = None
    for headline in kept:
        scope = headline.get("article_scope") or {}
        # An article naming dozens of issuers classifies none of them. A
        # headline carrying no scope at all is read as before, because a packet
        # written before _scope_articles existed must still rescore.
        if scope and not scope.get("about_this_name", True):
            roundups += 1
            shared = int(scope.get("returned_for_candidates") or 0)
            if widest is None or shared > widest[0]:
                widest = (shared, scope.get("tag_count"), headline.get("title"))
            continue
        for tag in headline.get("tags") or []:
            mapped = tag_map.get(str(tag).strip().lower().replace("-", " "))
            if not mapped:
                continue
            points = class_points.get(mapped, 0.0)
            if points > best_points:
                best_class, best_points, matched_tag = mapped, points, tag
                matched_article = headline

    if matched_tag:
        article = matched_article or {}
        scope = article.get("article_scope") or {}
        breadth = ""
        if scope:
            # The candidates whose news call answered, which is the set the
            # sharing count was taken over. It used to read candidates_in_packet,
            # a wider set that includes the names nobody asked the feed about,
            # so a morning that lost calls published a ratio whose halves came
            # from different populations. A packet written before that key
            # existed keeps the old number rather than printing None.
            denominator = (scope.get("candidates_checked")
                           or scope.get("candidates_in_packet"))
            breadth = (f", an article carrying {scope.get('tag_count')} tag(s) and "
                       f"returned for {scope.get('returned_for_candidates')} of "
                       f"this morning's {denominator} candidates")
        return best_class, (
            f"EODHD news tag {matched_tag!r} mapped through CRITERIA.md, from "
            f"{str(article.get('title') or 'an untitled headline')!r}{breadth}")
    if roundups and candidate.get("catalyst_found"):
        detail = ""
        if widest:
            detail = (f". The widest was {str(widest[2] or 'an untitled headline')!r}, "
                      f"carrying {widest[1]} tag(s) and returned for {widest[0]} of "
                      "this morning's candidates")
        return "none", (
            "no tag from an article about this name maps to a known class. "
            f"Roundups set aside: {roundups} of the {len(kept)} kept article(s), "
            "whose tags name the issuers they list rather than this one"
            + detail)
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

    rvol = candidate.get("pm_rvol")
    catalyst = candidate.get("catalyst_found")

    # Each entry is (key, why, MEASURED). The third element is the 2026-08-20
    # finding: a condition can fail because the input was measured and came in
    # low, or because it was never measured at all, and screen_tally counted
    # both as one number. "premarket_rvol 10 of 12" that morning folded in AAP
    # and SCSC, whose RVOL is null because the baseline denominator is
    # unusable, alongside eight names that were measured and read low.
    # Withholding an unmeasured name from a screen is right. Reporting the two
    # under one count contradicts the rule that missing evidence stays visibly
    # missing, which the rest of this file spends hundreds of lines enforcing.
    day: list[tuple[str, str, bool]] = []
    if gap is None:
        day.append(("gap_pct",
                    f"the gap was never computed: "
                    f"{candidate.get('gap_reason') or 'reason unrecorded'}", False))
    elif not _CRIT.rule("day_setup", "gap_pct").test(gap):
        day.append(("gap_pct",
                    f"gap_pct {gap:.2f} fails {_CRIT.rule('day_setup', 'gap_pct').describe()}",
                    True))
    if not _CRIT.rule("day_setup", "price").test(price):
        day.append(("price",
                    f"price {price} fails {_CRIT.rule('day_setup', 'price').describe()}",
                    price is not None))
    if not _CRIT.rule("day_setup", "market_cap").test(market_cap):
        day.append(("market_cap",
                    f"market_cap {market_cap} fails "
                    f"{_CRIT.rule('day_setup', 'market_cap').describe()}",
                    market_cap is not None))
    if not _CRIT.rule("day_setup", "premarket_rvol").test(rvol):
        day.append(("premarket_rvol",
                    (f"premarket_rvol {rvol} fails "
                     f"{_CRIT.rule('day_setup', 'premarket_rvol').describe()}")
                    if rvol is not None else
                    (f"premarket_rvol was never measured: "
                     f"{candidate.get('pm_rvol_reason') or 'reason unrecorded'}"),
                    rvol is not None))
    if _CRIT.flag("day_setup", "require_above_prior_high"):
        if prior_high is None or price is None or price <= prior_high:
            day.append(("require_above_prior_high",
                        f"price {price} is not above the prior day high {prior_high}",
                        prior_high is not None and price is not None))

    swing: list[tuple[str, str, bool]] = []
    if gap is None:
        swing.append(("gap_pct",
                      f"the gap was never computed: "
                      f"{candidate.get('gap_reason') or 'reason unrecorded'}", False))
    elif not _CRIT.rule("swing_setup", "gap_pct").test(gap):
        swing.append(("gap_pct",
                      f"gap_pct {gap:.2f} fails "
                      f"{_CRIT.rule('swing_setup', 'gap_pct').describe()}", True))
    if not _CRIT.rule("swing_setup", "price").test(price):
        swing.append(("price",
                      f"price {price} fails {_CRIT.rule('swing_setup', 'price').describe()}",
                      price is not None))
    if not _CRIT.rule("swing_setup", "market_cap").test(market_cap):
        swing.append(("market_cap",
                      f"market_cap {market_cap} fails "
                      f"{_CRIT.rule('swing_setup', 'market_cap').describe()}",
                      market_cap is not None))
    if _CRIT.flag("swing_setup", "require_open_above_prior_high"):
        if prior_high is None or price is None or price <= prior_high:
            swing.append(("require_open_above_prior_high",
                          f"premarket price {price} is not above the prior day "
                          f"high {prior_high}",
                          prior_high is not None and price is not None))
    if _CRIT.flag("swing_setup", "require_open_above_200sma"):
        if sma200 is None or price is None or price <= sma200:
            swing.append(("require_open_above_200sma",
                          f"premarket price {price} is not above the 200 day "
                          f"average {sma200}",
                          sma200 is not None and price is not None))
    if _CRIT.flag("swing_setup", "require_catalyst"):
        # Three states, not two. None means the news feed was never fetched
        # (failed call or quota skip), and an unchecked feed must not produce
        # a sentence claiming a search came back empty. Either way the
        # requirement is unmet, so both fail the screen; only the reason
        # differs, and the reason is what the report shows the reader.
        if catalyst is None:
            swing.append(("require_catalyst",
                          "the news feed was never checked, so catalyst is unknown",
                          False))
        elif not catalyst:
            swing.append(("require_catalyst", "no catalyst was found", True))

    candidate["day_eligible"] = not day
    candidate["day_failed"] = [why for _key, why, _m in day]
    candidate["day_failed_conditions"] = [key for key, _why, _m in day]
    # The subset of the list above whose input was never observed. Named rather
    # than counted, because the fix for an unmeasured condition is an
    # instrument and the fix for a failed one is nothing at all.
    candidate["day_failed_unmeasured"] = [key for key, _why, m in day if not m]
    candidate["swing_eligible"] = not swing
    candidate["swing_failed"] = [why for _key, why, _m in swing]
    candidate["swing_failed_conditions"] = [key for key, _why, _m in swing]
    candidate["swing_failed_unmeasured"] = [key for key, _why, m in swing if not m]


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
        unmeasured: dict[str, int] = {}
        for candidate in candidates:
            never_seen = set(candidate.get(f"{screen}_failed_unmeasured") or [])
            for condition in candidate.get(key) or []:
                counts[condition] = counts.get(condition, 0) + 1
                if condition in never_seen:
                    unmeasured[condition] = unmeasured.get(condition, 0) + 1
        eligible = sum(1 for c in candidates if c.get(f"{screen}_eligible"))
        # Ordered by how many failed, descending, so the template can quote the
        # list in that order without sorting anything itself.
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        out[screen] = {
            "eligible": eligible,
            "failed_by_condition": {
                name: {
                    "failed": n,
                    "cleared": examined - n,
                    # Of the failures, how many were never measured. A
                    # condition failing on a null input is a missing
                    # instrument; a condition failing on a real number is a
                    # verdict. See the (key, why, measured) comment above.
                    "unmeasured": unmeasured.get(name, 0),
                    "measured_and_failed": n - unmeasured.get(name, 0),
                }
                for name, n in ranked
            },
            # The sentence the template quotes, built here so the model neither
            # counts nor ranks. Empty when nothing failed, which is not the same
            # as a screen nobody ran. A condition with unmeasured failures says
            # so inline rather than hiding them inside its total.
            "failed_summary": ", ".join(
                (f"{name} {n} of {examined}"
                 + (f" ({unmeasured[name]} of those never measured)"
                    if unmeasured.get(name) else ""))
                for name, n in ranked
            ),
        }
    return out


def score_roll(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Who is in which conviction bucket, with the direction of the move.

    Two 2026-08-20 findings meet here and the same sentence caused both.

    The report wrote "MSTR and WMT green at 7" on a morning where SCSC also
    scored 7.0 green. Nothing false; the enumeration simply read as complete
    and was not. That is the model summarising a set the packet already knows
    exactly, which is the shape screen_tally exists to prevent.

    And it wrote "the strongest scored names, both green at 8, are AAP and
    FUTU" when AAP was down 21.75 percent on an earnings miss, below its VWAP,
    its prior high and its 200 day average. The gap component scores the
    ABSOLUTE gap, so the score has no sign, and a sentence ranking names by it
    without saying so points a reader the wrong way. So direction travels with
    every entry here and the summary string carries it, which makes the
    omission impossible to write rather than merely discouraged.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    unscored: list[str] = []
    for candidate in candidates:
        score = candidate.get("score")
        if score is None:
            unscored.append(candidate["symbol"])
            continue
        gap = _as_float(candidate.get("gap_pct"))
        buckets.setdefault(candidate.get("conviction") or "unbucketed", []).append({
            "symbol": candidate["symbol"],
            "score": score,
            "gap_pct": gap,
            "direction": gap_direction(gap),
        })
    for rows in buckets.values():
        rows.sort(key=lambda r: (-r["score"], r["symbol"]))

    # Bucket order comes from CRITERIA's own band list, so the report reads
    # them strongest first without this file holding a second copy of the
    # names. Band.result IS the bucket label; there is no separate field.
    order: list[str] = []
    for band in _CRIT.bands("score_buckets"):
        if band.result in buckets and band.result not in order:
            order.append(band.result)
    order += sorted(name for name in buckets if name not in order)

    # THE QUOTABLE FORM, on the evidence_roll.text precedent. direction_note
    # below is written for a code reader and nothing quotes it: it carries
    # ABSOLUTE in capitals, which prompt_analyst rule 8 forbids the model from
    # reproducing, so REPORT_TEMPLATE asked for the sense of it instead and got
    # six different sentences on six mornings.
    #
    # Every constraint on this wording is load bearing. It says "rows" and
    # never name, candidate or watchlist, so analyst.quantifier_violations
    # cannot fire on it at any counts. It carries no capitals, so it can be
    # reproduced verbatim. Each count carries its own denominator. And a gap
    # that was never computed is counted APART rather than folded into up.
    #
    # THE NEVER-COMPUTED COUNT IS TAKEN OVER THE CANDIDATES AND NOT OVER THE
    # SCORED ROWS, which is where it lives. A row reaches `buckets` only when
    # its score is not None, and score_candidate marks the gap component
    # unavailable when gap_pct is None, which sets the score to None. So such
    # a row is always in `unscored` and never in `buckets`, and counting it
    # over the scored rows returned zero on every morning that has ever run,
    # including the mornings where a gap really was never computed.
    #
    # The quota-degraded branch is the sharp case rather than a corner: it
    # sets prior_close to None for EVERY candidate, so every gap_pct is None,
    # buckets is empty, and the sentence read "Of 0 scored rows, 0 gapped up,
    # 0 gapped down and 0 carry a gap that was never computed" on precisely
    # the morning when nothing had a gap. A never-checked population published
    # as a checked-and-empty count of zero, in the sentence written to stop
    # exactly that.
    scored_rows = [row for rows in buckets.values() for row in rows]
    up_rows = sum(1 for row in scored_rows if row["direction"] == "up")
    down_rows = sum(1 for row in scored_rows if row["direction"] == "down")
    no_gap_rows = sum(1 for candidate in candidates
                      if _as_float(candidate.get("gap_pct")) is None)
    direction_text = (
        "The score weighs the absolute gap, so it ranks confluence and not "
        "direction: a faller and a riser can tie at the same number. Of "
        "{scored} scored rows, {up} gapped up and {down} gapped down. Rows "
        "whose gap was never computed are unscored and sit in neither "
        "count: {no_gap} today."
    ).format(scored=len(scored_rows), up=up_rows, down=down_rows,
             no_gap=no_gap_rows)

    def phrase(row: dict[str, Any]) -> str:
        if row["gap_pct"] is None:
            return f"{row['symbol']} {row['score']:.1f} (gap unknown)"
        return (f"{row['symbol']} {row['score']:.1f} "
                f"({row['direction']} {abs(row['gap_pct']):.2f} percent)")

    return {
        "by_bucket": {name: buckets[name] for name in order},
        "unscored": unscored,
        "score_is_direction_blind": True,
        "direction_note": (
            "the gap component scores the ABSOLUTE gap, so this score ranks how "
            "much confluence a name has and not which way it is moving. A name "
            "falling hard and a name rising hard can tie. Direction is carried "
            "on every row here for that reason and must be given wherever names "
            "are grouped or ranked by score."
        ),
        "text": {"direction": direction_text},
        "summary": "; ".join(
            f"{name}: " + ", ".join(phrase(row) for row in buckets[name])
            for name in order
        ),
    }


def evidence_roll(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """The membership lists the template used to make the model filter for.

    TEMPLATE_DERIVATIONS.md rows T2, T3, T15 and P1. Each of them asks the
    model to walk the candidate list and select the names matching a
    predicate: pm_rvol is null, pm_window_starts_late is true,
    pm_rvol_basis.is_lower_bound is true, catalyst_found is false, catalyst_found
    is null. Python decides all five before the model runs, and until now it
    threw the answers away and asked for them back in prose.

    That is the same shape as T9, the derivation that produced the false claim
    this whole audit started from: the 2026-08-18 report said a condition was
    missed by "every candidate" when one of the twelve had cleared it. A filter
    performed in prose over a set the packet already holds is a claim about
    membership that nothing checks, and this section publishes five of them.

    Every string built here is QUOTED into the report word for word and is then
    scanned by analyst.quantifier_violations, so all of them are written in
    counts rather than quantifiers, the same rule the notable movers section's
    reasons follow. A line reading "no candidate carries a null RVOL" would put
    a set quantifier into the model's mouth on the quietest morning of the year.
    Counts also say strictly more: "0 of 5" carries the denominator, so a reader
    can tell a screen that examined five names from a morning that found none to
    examine. claim_the_rolls_own_words_pass_the_quantifier_guard walks every
    string this can produce and holds that.

    unscored is deliberately NOT here. score_roll already owns it and two
    copies of one list is how the two drift apart; the template quotes
    score_roll.unscored for T3.

    coverage_absent is the one list here that is not a row on
    TEMPLATE_DERIVATIONS, and it exists because of the drift this docstring
    just warned about. analyst.fallback_report marks a candidate's premarket
    levels "(partial)" on `pm_window_starts_late OR NOT collector_covered`,
    and the first draft of this roll carried only the first half. Two
    renderers of one morning would then disagree about which names a reader
    should distrust, and arming the quantifier guard made the second renderer
    reachable rather than theoretical.

    The second half is not dead. drop_uncovered splits on `price is not None`
    and NOT on collector_covered, while collector_covered is
    `bool(bars) and on_watchlist`, so a name the collector heard that is not
    on today's watchlist keeps its price, survives the drop and carries
    collector_covered false. That is exactly what a subscription list which
    does not match the watchlist produces, which is a failure this project
    has already had. It happened on 2026-08-13 with WDAY and on 2026-08-21
    with AAPL.

    Kept as its own list rather than folded into window_starts_late, because
    the two are different facts and the sentences say different things: a late
    window is partial path evidence, and no coverage at all is absent path
    evidence. claim_the_roll_and_the_fallback_agree_on_partial_evidence holds
    that their union is what the fallback marks.
    """
    examined = len(candidates)

    def bare(symbol: str) -> str:
        return str(symbol or "").upper().removesuffix(".US")

    def names(rows: list[dict[str, Any]]) -> str:
        return ", ".join(bare(r["symbol"]) for r in rows)

    def line(rows: list[dict[str, Any]], what: str) -> str:
        """One count led sentence, and the same shape when the list is empty.

        Written the same way at zero rather than switching to prose, for the
        reason the Summary counts are: prose written only for the empty case is
        prose that runs on the mornings nobody scrutinises, and that is exactly
        where both false universals of 2026-08-18 were published.
        """
        if not rows:
            return f"0 of {examined} candidates {what}."
        return f"{len(rows)} of {examined} candidates {what}: {names(rows)}."

    rvol_null = [{"symbol": c["symbol"], "reason": c.get("pm_rvol_reason")}
                 for c in candidates if c.get("pm_rvol") is None]
    late = [{"symbol": c["symbol"]}
            for c in candidates if c.get("pm_window_starts_late")]
    uncovered = [{"symbol": c["symbol"]}
                 for c in candidates if not c.get("collector_covered")]
    lower_bound = [{"symbol": c["symbol"]} for c in candidates
                   if (c.get("pm_rvol_basis") or {}).get("is_lower_bound")]
    # catalyst_found false and catalyst_found null are DIFFERENT rows, and the
    # template has said so since 2026-08-14: false is a name the feed was read
    # for and paid nothing, null is a name the feed was never read for or came
    # back unreadable. Folding them loses which of the two a reader is holding.
    absent = [{"symbol": c["symbol"], "catalyst_why": c.get("catalyst_why")}
              for c in candidates if c.get("catalyst_found") is False]
    unknown = [{"symbol": c["symbol"], "catalyst_why": c.get("catalyst_why")}
               for c in candidates if c.get("catalyst_found") is None]

    # THE MORNING'S FILL WARNING, as a membership list like the six above, so
    # the report quotes a count rather than filtering the candidate table in
    # prose. Only the flagged names are listed: "not flagged" is not an
    # approval and a list of names that failed to trip a weak test is not a
    # thing any report should print as a group.
    band_thin = [{"symbol": c["symbol"], "why": c.get("pm_band_why")}
                 for c in candidates if c.get("pm_band_state") == BAND_THIN]

    # THE THIN DENOMINATOR, as a membership list for the same reason as the
    # seven above. _gap_for_thin_baselines already computes this and puts it in
    # gaps_to_fill, and gaps_to_fill reaches the report only through the
    # Summary's "anything that materially weakens this morning's evidence",
    # which is a judgement call the model makes. On 2026-08-31 it made it the
    # other way: both candidates rested on a denominator under the threshold,
    # the top scored name of the morning drew 2 of its 10 points from an RVOL of
    # 27.01 built on a 1,002 share median, and the report said neither. A
    # disclosure that survives only when the model agrees it matters is not a
    # disclosure, which is the whole argument this roll was built on.
    thin_baseline = [
        {"symbol": c["symbol"],
         "median_volume": (c.get("baseline") or {}).get("median_volume"),
         "why": (
             f"its denominator is a "
             f"{(c.get('baseline') or {}).get('median_volume'):,.0f} share "
             f"median, at or above the "
             f"{baseline.MIN_BASELINE_VOLUME:,.0f} share floor and below "
             f"{THIN_BASELINE_VOLUME:,.0f}, where 15 to 30 percent of a name's "
             "own ordinary sessions reach the top RVOL band by construction "
             "against 5 percent above 100,000")}
        for c in candidates
        if c.get("pm_rvol") is not None
        and (c.get("baseline") or {}).get("median_volume") is not None
        and (c.get("baseline") or {}).get("median_volume") < THIN_BASELINE_VOLUME
    ]
    thin_baseline.sort(key=lambda r: (r["median_volume"], r["symbol"]))

    return {
        "candidates_examined": examined,
        "rvol_null": rvol_null,
        "window_starts_late": late,
        "coverage_absent": uncovered,
        "rvol_lower_bound": lower_bound,
        "catalyst_absent": absent,
        "catalyst_unknown": unknown,
        "band_thin": band_thin,
        "thin_baseline": thin_baseline,
        "text": {
            "rvol_null": line(
                rvol_null, "carry a null premarket RVOL, so their premarket "
                           "volume evidence is missing"),
            "window_starts_late": line(
                late, "opened their premarket window late, so their premarket "
                      "path evidence is partial"),
            "coverage_absent": line(
                uncovered, "carry no collector coverage, so their premarket "
                           "path evidence is absent rather than partial, and "
                           "any level published for them rests on something "
                           "other than this morning's tape"),
            "rvol_lower_bound": line(
                lower_bound, "carry a premarket RVOL that understates as a "
                             "lower bound, because the numerator covers a "
                             "shorter window than the baseline denominator"),
            "catalyst_absent": line(
                absent, "were read for news and carry a found catalyst of "
                        "class none, which is a window that was checked and "
                        "paid nothing"),
            "catalyst_unknown": line(
                unknown, "carry an unknown catalyst status, which is a window "
                         "that was never read rather than one that came back "
                         "empty"),
            "band_thin": line(
                band_thin, "traded so little near their own premarket high "
                           "that the level may be a print rather than a price "
                           "anyone could transact at. This is a WARNING and "
                           "its silence is not an approval: measured over 54 "
                           "past rows it missed 4 of the 10 levels the nightly "
                           "check went on to call untradeable"),
            "thin_baseline": line(
                thin_baseline, "carry a premarket RVOL built on a THIN "
                               "denominator: at or above the "
                               f"{baseline.MIN_BASELINE_VOLUME:,.0f} share "
                               "floor and below "
                               f"{THIN_BASELINE_VOLUME:,.0f} shares, measured "
                               "2026-08-28 as where 15 to 30 percent of a "
                               "name's own ordinary premarket sessions reach "
                               "the top RVOL band by construction, against 5 "
                               "percent above 100,000. These ratios are "
                               "published, screened on and scored like the "
                               "rest"),
        },
    }


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
    # Stamped on BOTH branches and before either, because this is the line
    # where the sign is thrown away and it is therefore the line that owes a
    # reader the record of it. A candidate the gap could not be scored for
    # still has a direction if it has a gap at all.
    candidate["gap_direction"] = gap_direction(gap_raw)
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
    """Classify, screen and score every candidate against the earnings calendar.

    THE CALENDAR IS CONSULTED FIRST AND IS TREATED AS A FACT, so a run that
    could not read it must not let that read as a fact about the candidate.
    candidates_checked is False when the call failed and None when it was never
    made (no candidates, or the whole block skipped for quota); in both cases
    the absence of a symbol from earnings_symbols says nothing, and every
    candidate whose class was decided without the calendar carries that in
    catalyst_why. The class itself is still whatever the news supports, because
    inventing an earnings class for a name nothing puts on the calendar would be
    the same defect pointing the other way.
    """
    earnings_symbols = {
        str(row.get("symbol") or "").upper()
        for row in earnings_block.get("candidates", [])
        if row.get("symbol")
    }
    unchecked = earnings_block.get("candidates_checked") is False
    unchecked_why = (earnings_block.get("candidates_error")
                     or earnings_block.get("skipped")
                     or "the call failed")
    for candidate in candidates:
        catalyst_class, why = classify_catalyst(candidate, earnings_symbols)
        if unchecked and candidate["symbol"] not in earnings_symbols:
            why = (f"{why}. The earnings calendar was NOT checked this run "
                   f"({unchecked_why}), so this class was decided without it and "
                   "a name reporting today would not be recognised")
        candidate["catalyst_class"] = catalyst_class
        candidate["catalyst_why"] = why
        evaluate_eligibility(candidate)
        score_candidate(candidate)


# ------------------------------------------------------------------- runner

# ------------------------------------------- Layer 4, the notable movers section
#
# The briefing section, and nothing else. BUILD_PLAN.md "Layer 4" is the design,
# CRITERIA.md [Notable] holds every threshold, and DECISIONS.md carries the calls
# that were made here rather than by the owner. Read those before changing this.
#
# The fence from 4.1, repeated because it is the part most likely to be eroded by
# a later change that means well: this section is ADDITIVE TO THE REPORT ONLY. It
# writes no picks row, touches no score, no eligibility, no conviction and no
# CRITERIA setup block, and it shares no code with pool_recall. It reads exactly
# two files it does not own, universe.json for market caps and
# universe-closes-<date>.json for prices, plus the collector bars the scan
# already holds and the gap statistics table. None of that costs an EODHD call,
# which is why a quota degraded morning loses this section no leg at all.
#
# If a change here seems to need a picks column, stop and report rather than
# adding one: picks is the record of what the trading screen claimed, and mixing
# briefing names into it destroys the recall measurement.

NOTABLE_LIST_SIZE = _CRIT.integer("notable", "list_size")
NOTABLE_MIN_ABS_GAP_PCT = _CRIT.number("notable", "min_abs_gap_pct")
NOTABLE_MIN_RETURN_STDEV_PCT = _CRIT.number("notable", "min_return_stdev_pct")
NOTABLE_MIN_SESSIONS_FOR_SIGMA = _CRIT.integer("notable", "min_sessions_for_move_sigma")

# How many sessions each leg's move SPANS. This is the sigma scaling in 4.3.1
# and it is NOT the vintage offset: vintage._LEG_NEWEST_SESSION_BACK maps
# two_session to 1 because that row is stamped with c1's session, while the move
# itself spans 2. Two different questions about the same leg, and conflating
# them is how a two session move gets divided by a one session denominator.
_LEG_SPAN_SESSIONS = {
    "premarket": 1,
    "prior_session": 1,
    "two_session": 2,
}

# The four ranked lists of 4.4. Every list ranks WITHIN ONE LEG: ranking a
# premarket move against a prior session one would order a fresher window
# against an older one, and would put the 50 collector names, already selected
# for gap propensity and news, into the same ordering as the 2,704 names nothing
# selected. They would dominate systematically and the section would end up
# restating the watchlist it exists not to restate.
NOTABLE_LISTS = (
    "prior_session_by_sigma",
    "prior_session_by_market_cap",
    "two_session_by_move",
    "premarket_by_sigma",
)

# The four states a ranked list can end a morning in, and they are four rather
# than one empty list because the FIXES differ.
#
# UNCOMPUTABLE is an input this project has not produced. Either the leg's own
# file was lost, or the column the list ranks on is null for every row the leg
# carries, and the answer in both cases is to go and compute the input.
# NOTHING_TO_RANK is an input that arrived and carried nothing for this leg to
# measure, which is a fact about the file rather than about the market.
# BELOW_THE_FLOOR is a quiet window: the leg measured rows, the ranking key
# exists, and not one row passed this list's own floor. RANKED is a list
# holding at least one name, whether or not it filled to list_size.
#
# Until 2026-08-22 all four came out as an empty list plus one sentence about
# being "short", and two of the four have been empty every morning since the
# section shipped, because return_stdev_20d is null across the whole database.
# A reader could not tell that from a quiet market, which is precisely the
# distinction 4.9 already publishes one level up for the legs.
#
# The words are chosen to be quantifier free. They are quoted into the report
# and then scanned by analyst.quantifier_violations, so a state spelled "none
# cleared the floor" would put a set quantifier into the model's mouth every
# morning the list was empty. See the note on how these read, below.
LIST_RANKED = "ranked"
LIST_UNCOMPUTABLE = "uncomputable"
LIST_NOTHING_TO_RANK = "nothing to rank"
LIST_BELOW_THE_FLOOR = "below the floor"
NOTABLE_LIST_STATES = (LIST_RANKED, LIST_UNCOMPUTABLE, LIST_NOTHING_TO_RANK,
                       LIST_BELOW_THE_FLOOR)

# What each list RANKS ON, in the words its reason uses when the column is
# null. A list whose ranking key is null across its leg has not found a quiet
# market, it has found an input nobody has computed, and the state says which.
_LIST_RANKING_KEY = {
    "prior_session_by_sigma": "a move_sigma",
    "prior_session_by_market_cap": "a market cap on file",
    "two_session_by_move": "a move over this window",
    "premarket_by_sigma": "a move_sigma",
}

# The floor each list applies BEFORE it asks for the ranking key. Three of the
# four apply none at all: every row the leg measured is a candidate for them,
# so they come back empty only when the leg does, and BELOW_THE_FLOOR is
# unreachable for them by construction rather than by accident.
_LIST_FLOOR_TEXT = {
    "prior_session_by_sigma": None,
    "prior_session_by_market_cap": (
        f"a move of at least {NOTABLE_MIN_ABS_GAP_PCT} percent, which is "
        f"CRITERIA.md [Notable] min_abs_gap_pct"),
    "two_session_by_move": None,
    "premarket_by_sigma": None,
}


# ------------------------------------------------- a note on how these read
#
# Every reason string below is quoted into the report WORD FOR WORD, because
# REPORT_TEMPLATE.md tells the model to quote them rather than paraphrase, and
# the model's output is then scanned by analyst.quantifier_violations. That
# guard flags a quantifier near a set word: "every", "all", "none", "each",
# "most", "majority" within six words either side of "candidate", "name" or
# "watchlist", and "no" within six words AFTER one. It is in warn mode today
# and CRITERIA.md says what has to be true before it flips to enforcing; on the
# day it flips, a reason reading "no name on this leg carries a move_sigma"
# would be quoted into the report, flagged, regenerated twice and then fall
# back to the Python report. The section's own words would have cost the
# narrative.
#
# So these are written in COUNTS rather than quantifiers, which is the same
# rule fallback_report's prose already follows. Note that "no" is forward only:
# "this symbol has no gap statistics row" is fine and "no gap statistics row
# for this name" is not, because the set word has to come after.
#
# claim_the_sections_own_words_pass_the_quantifier_guard walks every string the
# section can produce and holds this, so a new reason cannot quietly reintroduce
# one.


def move_sigma(move_pct: float | None,
               stats_row: dict[str, Any] | None,
               span_sessions: int,
               table_unreadable: str | None = None) -> tuple[float | None, str | None]:
    """The move in units of the name's own daily volatility, or null and why.

    THE SCALING ASSUMES DAILY RETURNS ARE INDEPENDENT, and they are not. The
    denominator return_stdev_20d is a ONE DAY return standard deviation, so an n
    session move is divided by that times the square root of n. Consecutive
    moves in one name frequently are dependent: momentum and a multi day
    catalyst both produce runs, and dependent returns accumulate faster than the
    square root allows. The scaled sigma is therefore an UNDERESTIMATE of how
    unusual a sustained run is. That is the safe direction for a briefing,
    because it cannot inflate a name into the section, only keep one out.

    Where the sustained mover is still caught, so this is not re-litigated: a
    large quiet name up 2 percent on each of two consecutive sessions surfaces
    on list 1 for the unusualness of its prior session move, since a quiet
    name's sigma is small and 2 percent over it is large, and on list 3 for the
    size of its two session move. The scaling's work is to stop the two session
    leg overstating that name by the square root of 2, not to move it between
    lists.

    Four null outcomes and they are four, not one, because the fixes differ. A
    name absent from the gap statistics table was never measured; a name present
    with a null column has fewer than [Notable] min_sessions_for_move_sigma
    returns behind it; a name whose stdev is below min_return_stdev_pct has
    barely moved in twenty sessions and would otherwise report an enormous sigma
    on any move at all; and a null move has nothing to scale. Never a
    substituted number, never a silent drop.
    """
    if move_pct is None:
        return None, "no move on this leg to scale"
    if stats_row is None:
        # A table nobody could open and a name the table does not carry are
        # different facts with different fixes, and the first was being written
        # as the second on every row at once. "This symbol was never measured"
        # sends a reader to look up one name; "the table could not be read"
        # sends them to the database.
        return None, (table_unreadable or
                      "this symbol has no gap statistics row, so its daily "
                      "volatility was never measured")
    stdev = _as_float(stats_row.get("return_stdev_20d"))
    if stdev is None:
        # A null column has TWO causes and the reason has to say which. Every
        # one of the 10,997 rows in the database is null today, and not one of
        # them is null for the reason this used to give: return_stdev_20d was
        # added to gap_stats.py on 2026-08-17 and the last rebuild ran on
        # 2026-08-16, so the column exists and has never been computed. Telling
        # a reader that 10,997 names each have fewer than twenty sessions of
        # history is not a smaller mistake for being repeated.
        #
        # sessions_used is what separates them. It is the bar list's count
        # rather than the close only list's, so it is evidence and not proof,
        # and the wording says so.
        covered = _as_float(stats_row.get("sessions_used"))
        if covered is None:
            return None, ("return_stdev_20d is null and this row records no "
                          "session count, so it cannot say whether the column "
                          "was never computed or the history is too short")
        if covered < NOTABLE_MIN_SESSIONS_FOR_SIGMA:
            return None, (f"return_stdev_20d is null and this row covers "
                          f"{covered:,.0f} sessions, fewer than the "
                          f"{NOTABLE_MIN_SESSIONS_FOR_SIGMA} the denominator "
                          "needs")
        return None, (f"return_stdev_20d is null on a row covering "
                      f"{covered:,.0f} sessions, which is enough for it, so the "
                      "column was written before it was computed. The Sunday "
                      "21:00 universe rebuild fills it.")
    if stdev < NOTABLE_MIN_RETURN_STDEV_PCT:
        return None, (f"daily return stdev {stdev:.4f} percent is below "
                      f"{NOTABLE_MIN_RETURN_STDEV_PCT} in CRITERIA.md [Notable] "
                      "min_return_stdev_pct, too small to divide by")
    denominator = stdev * math.sqrt(span_sessions)
    return round(move_pct / denominator, 4), None


def load_universe_closes(session_date: str, packet: Packet) -> dict[str, Any] | None:
    """Today's universe closes sidecar, or None with the reason recorded.

    THE SECTION'S ONLY PRICE SOURCE for every name the collector did not hear,
    written by discover at 07:15 and holding one vintage across all three
    closes. A name missing from a session is null there and is never backfilled
    from a neighbouring session, so this reader never does either.

    The session_date check is not defensive padding. data/ accumulates these
    files, three of them are on disk as this is written, and nothing else in the
    project compares the file's own session_date against today. A morning where
    discover did not run would otherwise read yesterday's closes and publish
    them under today's leg labels, which is precisely the failure the leg
    labelling exists to prevent. generated_at is not usable for this: the
    2026-08-19 file is stamped 08:21:27 rather than 07:15, so a rule derived
    from the scheduled time would refuse a legitimate file.
    """
    path = config.DATA_DIR / f"universe-closes-{session_date}.json"
    if not path.is_file():
        packet.gap(
            f"{path.name} is absent, so the notable movers section lost both "
            "universe legs. discover writes it at 07:15 and returns before "
            "writing when the calendar cannot name the prior sessions or the "
            "first bulk call comes back empty."
        )
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        packet.gap(f"{path.name} could not be read ({type(exc).__name__}), so the "
                   "notable movers section lost both universe legs")
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("closes"), dict):
        packet.gap(f"{path.name} does not carry a closes map, so the notable "
                   "movers section lost both universe legs")
        return None
    # The sessions block is read with .get in three places and the closes map is
    # walked in three more, and a JSON file is whatever is on disk rather than
    # whatever the writer meant. A list where a mapping belongs raised
    # AttributeError out of build_packet, which stops the morning chain over a
    # briefing table; the section refuses the file instead and says which shape
    # was wrong.
    if not isinstance(payload.get("sessions"), dict):
        packet.gap(f"{path.name} carries a sessions block that is not a mapping "
                   f"({type(payload.get('sessions')).__name__}), so the notable "
                   "movers section could not date either universe leg and "
                   "refused the file")
        return None
    stamped = str(payload.get("session_date") or "")
    if stamped != session_date:
        packet.gap(
            f"{path.name} carries session_date {stamped or 'nothing'} rather than "
            f"{session_date}, so it is not this morning's file and the notable "
            "movers section refused it rather than publishing its closes under "
            "today's leg labels"
        )
        return None
    return payload


def closes_denominators(payload: dict[str, Any]) -> dict[str, Any]:
    """What the closes file examined, read from it where it says and derived where not.

    4.9 asks the section to report universe_examined and, per leg, how many
    names carried BOTH of the closes that leg needs, and BUILD_PLAN says not to
    recompute them because discover already writes them. It writes them as of
    2026-08-20, and the writer landed about six hours AFTER that morning's 07:15
    run, so the first file carrying them is 2026-08-21's. Every file on disk
    before then has universe_examined and names_with_at_least_one_close and
    neither of the other two.

    So they are read when present and counted from the closes map when not, and
    the block says which of the two happened. Deriving silently would violate
    4.9 in the other direction: a count nobody can tell apart from a written one
    is a count whose provenance is false.
    """
    closes = payload.get("closes") or {}
    written_per_session = payload.get("names_with_close")
    written_per_leg = payload.get("names_with_both_closes_for_leg")
    read_from_file = (isinstance(written_per_session, dict)
                      and isinstance(written_per_leg, dict))
    if read_from_file:
        per_session = {key: written_per_session.get(key) for key in ("c1", "c2", "c3")}
        per_leg = {leg: written_per_leg.get(leg)
                   for leg in ("prior_session", "two_session")}
    else:
        per_session = {
            key: sum(1 for row in closes.values()
                     if isinstance(row, dict) and row.get(key) is not None)
            for key in ("c1", "c2", "c3")
        }
        per_leg = {
            "prior_session": sum(
                1 for row in closes.values()
                if isinstance(row, dict)
                and row.get("c1") is not None and row.get("c2") is not None),
            "two_session": sum(
                1 for row in closes.values()
                if isinstance(row, dict)
                and row.get("c1") is not None and row.get("c3") is not None),
        }
    return {
        "universe_examined": payload.get("universe_examined"),
        "names_with_at_least_one_close": payload.get("names_with_at_least_one_close"),
        "names_with_close": per_session,
        "names_with_both_closes_for_leg": per_leg,
        "third_session_available": payload.get("third_session_available"),
        # "read" means discover wrote these counts; "derived" means this section
        # counted them off the closes map because the file predates the writer.
        "counter_source": "read" if read_from_file else "derived",
    }


def _readable_date(value: Any) -> dt.date | None:
    """The session a stamp names, or None when it names nothing readable.

    Used to decide whether the universe legs can be dated at all. ettime is the
    only clock in this project and parse_date is its reader; this wraps it so a
    null, an empty string and a malformed date all come back as one answer,
    which is the only answer the caller acts on.
    """
    if not value:
        return None
    try:
        return ettime.parse_date(str(value))
    except (TypeError, ValueError):
        return None


def _pct_move(newer: Any, older: Any) -> float | None:
    """The percent move from older to newer, or None when either is unusable."""
    a, b = _as_float(newer), _as_float(older)
    if a is None or b is None or b <= 0:
        return None
    return round((a - b) / b * 100.0, 4)


def attach_notable_candidate_fields(
    candidates: list[dict[str, Any]],
    closes: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    table_unreadable: str | None = None,
) -> None:
    """4.2's three report fields, beside gap_pct on every candidate.

    move_sigma, gap_2session and gap_3session are REPORT FIELDS, not screen
    conditions. Nothing in evaluate_eligibility or score_candidate reads them
    and no CRITERIA setup block gains a key for them.

    They are also NOT LEGS, which is the one place 4.2 and 4.3 read as though
    they contradict each other. gap_2session is c2 against this morning's
    premarket price and spans two sessions; the two_session LEG is c3 against
    c1 and spans two completed sessions. gap_3session spans three and there is
    no three session leg at all, deliberately, because a three session move
    universe wide would need a fourth close where the sidecar holds three. A row
    in the section can only carry a leg from vintage._LEG_NEWEST_SESSION_BACK,
    so neither of these two fields ever becomes one. They travel on the
    candidate, where the report can quote them beside its gap.
    """
    for candidate in candidates:
        symbol = candidate.get("symbol")
        row = closes.get(symbol) if isinstance(closes, dict) else None
        if not isinstance(row, dict):
            row = {}
        price = candidate.get("price")
        # Null WITH a reason, like every other absent number in this packet. A
        # bare null here reads the same whether the sidecar is missing, the
        # session was never bought, or the candidate has no premarket price,
        # and those are three different mornings.
        candidate["gap_2session"] = _pct_move(price, row.get("c2"))
        candidate["gap_3session"] = _pct_move(price, row.get("c3"))
        for field, close_key, span in (("gap_2session", "c2", "two"),
                                       ("gap_3session", "c3", "three")):
            if candidate[field] is not None:
                candidate[f"{field}_reason"] = None
            elif price is None:
                candidate[f"{field}_reason"] = (
                    "no premarket price from the collector to measure the "
                    f"{span} session move from")
            elif not row:
                candidate[f"{field}_reason"] = (
                    "the universe closes sidecar carries no row for this symbol")
            elif row.get(close_key) is None:
                candidate[f"{field}_reason"] = (
                    f"the sidecar carries no {close_key} close for this symbol, "
                    f"so the {span} session baseline is missing")
            else:
                candidate[f"{field}_reason"] = (
                    f"the {close_key} close is zero or negative, which is not a "
                    "price to measure a move against")
        sigma, reason = move_sigma(candidate.get("gap_pct"), stats.get(symbol),
                                   _LEG_SPAN_SESSIONS["premarket"],
                                   table_unreadable)
        candidate["move_sigma"] = sigma
        candidate["move_sigma_reason"] = reason


def mark_notable_watchlist(notable: dict[str, Any],
                          candidates: list[dict[str, Any]]) -> tuple[int, int]:
    """Fill in each row's also_on_watchlist, AFTER the screens have decided.

    This is a second pass because of an ordering nothing in the spec mentions
    and nothing in the section could see. day_eligible and swing_eligible are
    set by evaluate_eligibility inside stamp_all, and stamp_all runs AFTER
    vintage.enforce, which is where the section has to be assembled because
    enforce is handed a dict built by hand and check (e) reads it. So at
    assembly time those keys do not exist on any candidate yet, and the mark
    4.4 asks for came out null on every row of every run.

    The mark is presentational: it is not a leg, not a vintage and not
    something check (e) reads, so filling it after the gate costs nothing the
    gate was protecting.

    Returns (on_a_watchlist, screened_and_neither). TWO COUNTS, because the mark
    has five states and only three of them mean the symbol is on a watchlist.
    Counting every non-null mark made the packet's gap say "N row(s) name a
    symbol that is also on a watchlist this morning" over rows whose mark is
    exactly the opposite: the screens looked at that name and refused it for
    both lists. That count is the one a reader uses to judge how much the two
    sections overlap.
    """
    by_symbol = {str(c.get("symbol") or "").upper(): c for c in candidates}
    on_watchlist = 0
    screened_neither = 0
    for row in notable.get("rows") or []:
        mark = _watchlist_mark(by_symbol.get(str(row.get("symbol") or "").upper()))
        row["also_on_watchlist"] = mark
        if mark == SCREENED_NEITHER:
            screened_neither += 1
        elif mark:
            on_watchlist += 1
    return on_watchlist, screened_neither


# The one mark of the five that does NOT mean the symbol is on a watchlist. A
# module constant because the counter below and the reader of the mark have to
# agree on it: counting it as a watchlist row is what made the packet say five
# names were on a watchlist on a morning when two of them had been screened and
# refused for both.
SCREENED_NEITHER = "screened, neither"


def _watchlist_mark(candidate: dict[str, Any] | None) -> str | None:
    """Which watchlist a notable symbol is already on, or how it missed.

    A symbol on a watchlist appears in this section anyway and the row says so.
    It is not suppressed: two sections selecting one symbol on different
    grounds is information, and hiding it is not. Expect most premarket rows to
    carry a mark, since that leg draws from the pool the watchlist came from,
    which is precisely why the premarket leg was given its own list instead of
    being allowed to crowd the others.

    FIVE answers, not three, because "screened and did not qualify" and "never
    screened at all" are different facts about a symbol and were both coming
    out as a bare null. Roughly 2,742 of the 2,754 symbols this section can
    reach were never screened, and reading their blank cell as "the screen
    looked and said no" is the wrong conclusion in nearly every case.
    """
    if not candidate:
        return None
    day = bool(candidate.get("day_eligible"))
    swing = bool(candidate.get("swing_eligible"))
    if day and swing:
        return "day and swing"
    if day:
        return "day"
    if swing:
        return "swing"
    return SCREENED_NEITHER


def _catalyst_of(candidate: dict[str, Any] | None) -> tuple[str | None, str]:
    """The headline where one was fetched, and which of three states this is.

    4.6: no news is fetched for any name outside the existing candidate set,
    because doing so would multiply the call count over a set an order of
    magnitude larger and this section is a briefing rather than a screen. A name
    with no news fetched is NOT CHECKED and never "no catalyst": the two are
    different facts and the report says which one it is holding.
    """
    if not candidate:
        return None, "not checked"
    if candidate.get("catalyst_error"):
        return None, "not checked"
    if candidate.get("catalyst_found") is None:
        return None, "not checked"
    headlines = candidate.get("headlines") or []
    if candidate.get("catalyst_found") and headlines:
        title = headlines[0].get("title") if isinstance(headlines[0], dict) else None
        return (str(title) if title else None), "fetched"
    return None, "no catalyst found"


# Which leg each of the four lists ranks within. One table, read by the
# shortfall note and by the row assembly, because two copies of this mapping is
# how a list ends up ranking one leg and stamping another.
_LIST_LEG = {
    "prior_session_by_sigma": "prior_session",
    "prior_session_by_market_cap": "prior_session",
    "two_session_by_move": "two_session",
    "premarket_by_sigma": "premarket",
}


def leg_of_list_key(name: str) -> str:
    """The leg a ranked list draws from. Every list ranks within exactly one."""
    return _LIST_LEG[name]


def empty_notable_block(reason: str) -> dict[str, Any]:
    """The section, present and saying why it holds nothing.

    An ABSENT notable_movers key and an EMPTY one are different facts and the
    packet must not write them the same way: absent says the packet predates the
    section, empty says today's section could not be built. Every leg and every
    list carries the same reason, because whatever stopped the assembly stopped
    all of them.
    """
    reports: dict[str, Any] = {}
    for name in NOTABLE_LISTS:
        # UNCOMPUTABLE and not one of the other three: nothing was read, so
        # nothing was measured, cleared or ranked. considered is 0 because the
        # section counted 0, which is a different statement from the null the
        # legs carry for a denominator nobody could look up.
        report = {"state": LIST_UNCOMPUTABLE, "reason": reason,
                  "leg": leg_of_list_key(name),
                  "ranks_on": _LIST_RANKING_KEY[name],
                  "considered": 0, "qualified": 0, "selected": 0}
        report["text"] = _list_report_text(name, report)
        reports[name] = report
    return {
        "rows": [],
        "lists": {name: [] for name in NOTABLE_LISTS},
        "list_reports": reports,
        "list_reasons": {name: reason for name in NOTABLE_LISTS},
        "list_size": NOTABLE_LIST_SIZE,
        "legs": {leg: _leg_report(False, reason, None, 0, False)
                 for leg in _LEG_SPAN_SESSIONS},
        "sessions": None,
        "universe_examined": None,
        "counter_source": None,
        "names_with_close": None,
        "names_with_both_closes_for_leg": None,
        "third_session_available": None,
        "context_symbols_excluded": 0,
        "names_without_market_cap": 0,
        "instrument_names_on_file": 0,
        "instrument_name_reason": reason,
        "skipped": reason,
    }


def _leg_report(available: bool, reason: str | None, examined: Any,
                selected: int, input_present: bool) -> dict[str, Any]:
    """One leg's line in the section's own accounting.

    examined and selected are both reported because 4.9 says zero examined is a
    different outcome from zero selected. A leg that looked at 2,754 names and
    picked none is a quiet market; a leg that looked at none is a lost input,
    and a section that published one number could not tell you which it had.

    input_present splits the second of those in half, which is what the ranked
    lists read. A leg comes back unavailable for two different reasons: the
    file it reads was missing or unusable, or the file was read and carried
    nothing this leg could measure. Both leave available false, and the fixes
    are a lost input against a quiet window, so a list reporting one as the
    other sends its reader to the wrong place. It is a required argument rather
    than a defaulted one, so that a new call site has to decide.
    """
    return {"available": available, "reason": reason,
            "examined": examined, "selected": selected,
            "input_present": input_present}


def _list_report_text(name: str, report: dict[str, Any]) -> str:
    """One ranked list's whole outcome, as the one sentence the report quotes.

    Built HERE rather than once in REPORT_TEMPLATE.md and again in
    fallback_report, because a sentence assembled in two renderers says two
    different things the first time one of them is edited, and this project has
    already paid for that with the table headers. Both quote this string.

    The counts come first and the state names them: selected of qualified of
    considered, then the state, then the reason. A list that filled says so in
    the same shape as a list that could not be computed, so a reader comparing
    four lines is comparing four of the same thing.
    """
    text = (f"The {name} list is {report['state']}: {report['selected']} "
            f"selected of {report['qualified']} qualified of "
            f"{report['considered']} considered on the {report['leg']} leg.")
    reason = str(report.get("reason") or "").strip()
    if reason:
        said = f"{reason[:1].upper()}{reason[1:]}"
        text += " " + (said if said.endswith(".") else said + ".")
    return text


def _key_absence(name: str, leg_rows: dict[str, tuple[Any, ...]],
                 block: dict[str, Any]) -> str:
    """Why the key a list ranks on is null, in the section's own count.

    A list reporting UNCOMPUTABLE has said that its ranking key is absent; this
    says what made it absent, which is the whole difference between "the Sunday
    rebuild has not run" and "these particular names are too young to measure".
    move_sigma already produces four distinct reasons and puts one on every leg
    row, so this tallies those rather than inventing a fifth.

    The tally is quoted rather than summarised: the count that carries a reason
    is given beside the leg's own size, so a leg where one cause dominates and a
    leg where four causes split evenly read differently. Ties break on the text,
    so the sentence is the same on two runs over the same input.

    Written in counts, never in quantifiers, like every other string this
    section hands the model. See the note on how these read.
    """
    if name == "prior_session_by_market_cap":
        missing = block.get("names_without_market_cap") or 0
        return (f"{missing} cleared the floor and carry nothing in the "
                "universe file's market cap field, so 0 of them could be "
                "ranked by it.")
    tally: dict[str, int] = {}
    for value in leg_rows.values():
        if value[1] is None and value[2]:
            tally[str(value[2])] = tally.get(str(value[2]), 0) + 1
    if not tally:
        return ""
    said, hits = max(tally.items(), key=lambda item: (item[1], item[0]))
    return f"{hits} of {len(leg_rows)} report: {said}"


def notable_section(
    session_date: str,
    universe_payload: dict[str, Any],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    candidates: list[dict[str, Any]],
    packet: Packet,
) -> dict[str, Any]:
    """notable_movers, and the morning surviving a defect inside it.

    This section is ADDITIVE. Nothing downstream reads it, no score depends on
    it, no eligibility or conviction touches it, and no picks row comes from
    it. A defect in it that raised would take build_packet down with it, and
    the morning chain stops on the first non-zero exit, so there would be no
    packet, no report and no email over a briefing table. That trade is not
    close, and the alternative to catching here is a section that can end the
    morning it is only a section of.

    Nothing is swallowed: the exception type and message go into the packet's
    gaps and into the section's own skipped reason, so the report says what
    raised in the same place it says what was lost.

    BaseException is deliberately not caught. A KeyboardInterrupt or a
    SystemExit is somebody stopping the run, not a defect in this section, and
    turning one of those into a thin briefing would be worse than useless.

    A separate function rather than a try around the call site, because a guard
    written inline in build_packet is a guard no claim can reach, and this
    project decided on 2026-08-20 that a guard nobody has watched fail is not
    known to be a guard.
    """
    try:
        return notable_movers(session_date, universe_payload, bars_by_symbol,
                              candidates, packet)
    except Exception as exc:  # noqa: BLE001
        reason = (f"the notable movers section raised {type(exc).__name__}: "
                  f"{exc}. It is additive to the report, so the morning went on "
                  "without it rather than stopping over it.")
        packet.gap(reason)
        print(f"scan: {reason}")
        return empty_notable_block(reason)


def notable_movers(
    session_date: str,
    universe_payload: dict[str, Any],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    candidates: list[dict[str, Any]],
    packet: Packet,
) -> dict[str, Any]:
    """The notable movers block, and 4.2's three fields on every candidate.

    Three legs, four ranked lists, and every list ranks within one leg. The
    denominator is the UNIVERSE and not the survivors: the block reports what
    each leg examined beside what it selected, so a quiet morning and a lost
    input are told apart.

    Two calls were made here rather than by the owner and are cheap to overrule,
    which is why they are named rather than buried.

    ONE: the eight [Collector] context_symbols are excluded from the premarket
    leg. They are subscribed, so they are in bars_by_symbol, and 4.3 says every
    subscribed name is eligible. But they are ETFs, and the universe is common
    stock, so they are in NONE of the three joins this section needs: no row in
    universe.json, no row in the closes sidecar, no row in gap_stats. A row for
    SPY would carry a price and a null in every other column, including the
    move it is supposed to be notable for, because there is no c1 to measure it
    against. Their moves are already in market_snapshot, which is where a reader
    looks for them. The count is reported rather than the exclusion being
    silent.

    TWO: list 2's floor is read as "at least min_abs_gap_pct", not "more than".
    Every other min_ threshold in this file is a floor a value may sit exactly
    on, and a name moving exactly 1.00 percent is not the one this floor was
    written to exclude.
    """
    from selection import gap_stats

    block: dict[str, Any] = {
        "rows": [],
        "lists": {name: [] for name in NOTABLE_LISTS},
        "list_reports": {},
        "list_size": NOTABLE_LIST_SIZE,
        "legs": {},
        "sessions": None,
        "universe_examined": None,
        "counter_source": None,
        "names_with_close": None,
        "names_with_both_closes_for_leg": None,
        "third_session_available": None,
        "context_symbols_excluded": 0,
        "names_without_market_cap": 0,
        "instrument_names_on_file": 0,
        "instrument_name_reason": None,
        "skipped": None,
    }

    caps: dict[str, float] = {}
    # The vendor's own name for the instrument, which the universe build kept
    # from 2026-08-20. It is here for one reason: this section's second list
    # ranks by market cap, so the largest caps on file are read by a human every
    # morning, and a bare ticker cannot tell that reader whether a very large
    # one is a real company or a vendor error. It took a vendor call to
    # establish that SPCX and SKHY, both written up as implausible, are SpaceX
    # and SK Hynix and that both caps were right. See DECISIONS.md 2026-08-20.
    names: dict[str, str] = {}
    for row in (universe_payload.get("symbols") or []):
        symbol = str(row.get("symbol") or "").upper()
        cap = _as_float(row.get("market_cap"))
        if symbol and cap is not None:
            caps[symbol] = cap
        label = str(row.get("name") or "").strip()
        if symbol and label:
            names[symbol] = label

    # THE CAP'S VINTAGE. One fact about the file, not a column repeated on
    # every row: every cap here is read from the same universe.json, which is
    # rebuilt on Sundays, while the candidate blocks' market_cap is the live
    # 08:45 quote. Those two disagree by the size of whatever the name has done
    # since the rebuild, and on 2026-08-31 they disagreed inside one document
    # with nothing to tell a reader they were measured at different moments:
    # SAIC 5.43 billion here against 5.84 billion in Premarket gappers, MNSO
    # 3.07 against 2.84. Neither is wrong and neither is fixable. Ranking one of
    # these lists by cap means a cap for the whole universe, and that many live
    # quotes is not something the morning can buy. Saying which one it is costs
    # nothing and was the part that was missing.
    block["market_cap_as_of"] = (
        str(universe_payload.get("generated_at") or "").strip() or None)
    # NOT "market_cap_reason": the ROWS already carry that name for a different
    # fact, a cap missing for one symbol. Two scopes, one spelling, two meanings
    # is how a reader ends up holding the wrong one.
    block["market_cap_as_of_reason"] = None if block["market_cap_as_of"] else (
        "the universe file carries no generated_at, so the age of every market "
        "cap in this section is unknown rather than merely old")
    block["instrument_names_on_file"] = len(names)
    # A file with no names at all is a file that predates the field, which is a
    # different fact from a name missing for one symbol, and the template needs
    # to be able to tell them apart or it prints a per row absence for a whole
    # file's worth of them.
    block["instrument_name_reason"] = None if names else (
        "the universe file was built before the vendor's instrument name began "
        "to be kept, so it carries nothing in that field for any symbol")

    # SELECT * over the newest as_of, so every row already carries
    # return_stdev_20d. Local import on discover.load_metrics's precedent, and
    # it opens the database rather than the network: no EODHD call is made
    # anywhere in this section.
    stats_unreadable: str | None = None
    try:
        stats = gap_stats.load_all()
    except Exception as exc:  # a missing table is a lost sigma, not a lost run
        stats = {}
        stats_unreadable = (f"the gap statistics table could not be read "
                            f"({type(exc).__name__}: {exc}), so no name has a "
                            "volatility denominator this morning")
        packet.gap(f"notable movers: {stats_unreadable}. Lists 1 and 4 have no "
                   "ranking key as a result, and this is a database fault rather "
                   "than a fact about any one symbol.")

    closes_payload = load_universe_closes(session_date, packet)
    closes = (closes_payload or {}).get("closes") or {}
    sessions = (closes_payload or {}).get("sessions") or {}
    attach_notable_candidate_fields(candidates, closes, stats, stats_unreadable)

    by_symbol = {str(c.get("symbol") or "").upper(): c for c in candidates}

    if closes_payload is None:
        lost = ("data/universe-closes-<date>.json is not readable for this "
                "session, so both universe legs were lost")
        block["skipped"] = lost
        block["legs"]["prior_session"] = _leg_report(False, lost, None, 0, False)
        block["legs"]["two_session"] = _leg_report(False, lost, None, 0, False)
    else:
        counters = closes_denominators(closes_payload)
        block["universe_examined"] = counters["universe_examined"]
        block["counter_source"] = counters["counter_source"]
        block["names_with_close"] = counters["names_with_close"]
        block["names_with_both_closes_for_leg"] = \
            counters["names_with_both_closes_for_leg"]
        block["third_session_available"] = counters["third_session_available"]
        block["sessions"] = {key: sessions.get(key) for key in ("c1", "c2", "c3")}

    # ------------------------------------------------------------- the legs
    # Every value is (move_pct, sigma, sigma_reason, price_time, price_age_s).
    #
    # The age is carried rather than discarded because the premarket gate below
    # computes it, drops the rows past the limit and then throws the number
    # away, so a row that SURVIVED the gate published a bare timestamp and left
    # the reader to subtract it from a scan clock the report does not print. A
    # print 400 seconds old is inside the limit and is still not the price the
    # reader is looking at. Null on both universe legs, where a close has no
    # intraday age at all.
    legs: dict[str, dict[str, tuple[Any, ...]]] = {name: {} for name in _LEG_SPAN_SESSIONS}
    malformed = 0

    # Both universe legs are stamped with c1's SESSION, not with its value, and
    # a row that cannot be stamped is a row vintage check (e) refuses. enforce
    # raises on that, so the packet is never written and the whole morning chain
    # stops before the analyst. A briefing section must not be able to do that
    # to the report it is only a section of, so an undated c1 costs the two
    # universe legs and nothing else. The premarket leg stamps today and reads
    # c1 as a NUMBER, so it is unaffected and keeps running.
    # What the vendor said, against what the calendar asked for. Written by
    # discover from 2026-08-20; a sidecar older than that carries no
    # vendor_dates and this reads as unknown, which is the honest answer for a
    # file that never recorded it.
    vendor_dates = (closes_payload or {}).get("vendor_dates")
    if not isinstance(vendor_dates, dict):
        vendor_dates = {}
    block["vendor_dates"] = dict(vendor_dates) if vendor_dates else None
    mismatched = {
        key: sorted(vendor_dates.get(key) or [])
        for key in ("c1", "c2", "c3")
        if (vendor_dates.get(key)
            and sessions.get(key)
            and str(sessions[key]) not in {str(d) for d in vendor_dates[key]})
    }
    block["vendor_date_mismatch"] = mismatched or None

    undated: str | None = None
    if closes_payload is not None and "c1" in mismatched:
        undated = (
            f"the sidecar asked the vendor for {sessions.get('c1')} and the rows "
            f"came back stamped {mismatched['c1']}. Both universe legs are dated "
            "from c1's session, so publishing them would put one session's "
            "closes under another session's label, which is the one thing the "
            "leg labels exist to prevent. vintage check (e) cannot catch it: "
            "the stamp and the expectation are the same calendar call.")
        packet.gap(f"notable movers: {undated}")
        for leg in ("prior_session", "two_session"):
            block["legs"][leg] = _leg_report(
                False, undated,
                (block["names_with_both_closes_for_leg"] or {}).get(leg), 0,
                False)
    elif closes_payload is not None and _readable_date(sessions.get("c1")) is None:
        undated = (f"the closes sidecar carries sessions.c1 "
                   f"{sessions.get('c1')!r}, which is not a session this section "
                   "can date a row with, so both universe legs were lost rather "
                   "than emitting rows the vintage gate would refuse")
        packet.gap(f"notable movers: {undated}")
        for leg in ("prior_session", "two_session"):
            block["legs"][leg] = _leg_report(
                False, undated,
                (block["names_with_both_closes_for_leg"] or {}).get(leg), 0,
                False)

    if closes_payload is not None and undated is None:
        for symbol, row in closes.items():
            if not isinstance(row, dict):
                malformed += 1
                continue
            c1, c2, c3 = row.get("c1"), row.get("c2"), row.get("c3")
            # A c2 or c3 from a session nobody asked for makes the MOVE wrong
            # even where the stamp is right, so the leg that reads it is lost
            # rather than published against the wrong end.
            if "c2" in mismatched:
                c2 = None
            if "c3" in mismatched:
                c3 = None
            prior = _pct_move(c1, c2)
            if prior is not None:
                sigma, reason = move_sigma(prior, stats.get(symbol),
                                           _LEG_SPAN_SESSIONS["prior_session"],
                                           stats_unreadable)
                legs["prior_session"][symbol] = (prior, sigma, reason,
                                                 None, None)
            two = _pct_move(c1, c3)
            if two is not None:
                sigma, reason = move_sigma(two, stats.get(symbol),
                                           _LEG_SPAN_SESSIONS["two_session"],
                                           stats_unreadable)
                legs["two_session"][symbol] = (two, sigma, reason,
                                               None, None)

        per_leg = block["names_with_both_closes_for_leg"] or {}
        # A third session the vendor never answered for and a third session
        # every symbol happened to be missing from produce the same empty leg
        # and are not the same fact. discover records which it was in
        # third_session_available; the two_session leg quotes it rather than
        # reporting a quiet market.
        never_bought = block["third_session_available"] is False
        # Which close each leg's FAR end comes from, so a mismatch on that
        # close can be reported by the leg that lost it. c1 is the near end of
        # both and is handled above, where it costs both legs together.
        far_close = {"prior_session": "c2", "two_session": "c3"}
        for leg in ("prior_session", "two_session"):
            # input_present is the same fork the reason above already makes. A
            # third session nobody bought is a LOST INPUT and reads as
            # uncomputable one level down; a sidecar that was read and carried
            # no pair of closes for this leg is a file with nothing in it, and
            # reads as nothing to rank.
            present = True
            if legs[leg]:
                reason = None
            elif far_close[leg] in mismatched:
                # THE SAME FACT c1 ALREADY REPORTS, one close along. A c2 or c3
                # the vendor stamped with a session nobody asked for is nulled
                # on every row above, correctly, because it would make the MOVE
                # wrong even where the row's own stamp is right. The leg that
                # reads it then came out empty with the generic sentence below,
                # which says the file held nothing and sends a reader to the
                # vendor for missing data when the data arrived and was refused.
                key = far_close[leg]
                reason = (
                    f"the sidecar asked the vendor for {sessions.get(key)} as "
                    f"{key} and the rows came back stamped {mismatched[key]}, so "
                    f"{key} was refused on every row. The {leg} leg measures from "
                    "it, so this leg has no far end rather than no movers. "
                    "Publishing it would date one session's close with another "
                    "session's label, which is what the leg labels exist to "
                    "prevent.")
                present = False
                packet.gap(f"notable movers: {reason}")
            elif leg == "two_session" and never_bought:
                reason = ("the third session was never bought: discover's third "
                          "bulk call did not answer, so third_session_available "
                          "is false and c3 is null on every row. This leg has no "
                          "baseline rather than no movers.")
                present = False
            else:
                reason = f"0 rows carried both of the closes the {leg} leg needs"
            block["legs"][leg] = _leg_report(
                bool(legs[leg]), reason, per_leg.get(leg), 0, present)

    context = {collect_premarket._full(s)
               for s in _CRIT.text_list("collector", "context_symbols")}
    heard = [s for s in bars_by_symbol if s not in context]
    block["context_symbols_excluded"] = len(
        [s for s in bars_by_symbol if s in context])
    # The SAME floor the candidate path applies in drop_stale_prices, and for
    # the same reason. A print from 07:22 is genuinely inside today's premarket
    # window, so the vintage gate passes it, and it is still not this morning's
    # price at 08:45. The candidate path drops those names; this leg was
    # publishing them as notable premarket moves, off exactly the bars that had
    # already been rejected two hundred lines up. One rule, one clock, both
    # readers.
    price_age_limit = _CRIT.number("price_age", "max_price_age_seconds")
    scan_clock = ettime.now_et()
    stale = 0
    if closes_payload is not None:
        # Reads c1 as a NUMBER and stamps today, so an undated sessions.c1 does
        # not reach it.
        for symbol in heard:
            price, price_time = _collector_last(bars_by_symbol.get(symbol) or [])
            age = _price_age_seconds(price_time, scan_clock)
            if age is not None and age > price_age_limit:
                stale += 1
                continue
            baseline_close = (closes.get(symbol) or {}).get("c1")
            move = _pct_move(price, baseline_close)
            if move is None:
                continue
            sigma, reason = move_sigma(move, stats.get(symbol),
                                       _LEG_SPAN_SESSIONS["premarket"],
                                       stats_unreadable)
            legs["premarket"][symbol] = (move, sigma, reason, price_time, age)
    block["premarket_prices_too_old"] = stale
    if stale:
        packet.gap(
            f"notable movers: {stale} subscribed symbol(s) were left off the "
            f"premarket leg because their last collector print is older than "
            f"the {price_age_limit:,.0f}s limit in {config.CRITERIA_PATH.name} "
            "[price age]. The same floor drops them from the candidate path.")

    # premarket_input is the same fork again. A collector file with no bars and
    # an unreadable sidecar are both inputs this leg never got; a collector that
    # was heard and a sidecar that was read, with no symbol carrying both, is a
    # leg with nothing in it.
    premarket_input = True
    if not bars_by_symbol:
        premarket_reason = ("the collector file carried no bars, so the "
                            "premarket leg had nothing to measure")
        premarket_input = False
    elif closes_payload is None:
        premarket_reason = ("the closes sidecar is unreadable, so the premarket "
                            "leg had no c1 baseline to measure against")
        premarket_input = False
    elif not legs["premarket"]:
        premarket_reason = ("0 subscribed symbols outside the context "
                            "tickers carried both a collector price and a c1 "
                            "close")
    else:
        premarket_reason = None
    # examined is what the leg actually looked at. With no sidecar it looked
    # at nothing, whatever the collector heard, because there is no baseline to
    # measure a move against; reporting the collector count there would say the
    # leg examined 39 symbols and selected none, which is the reading 4.9 is
    # written to prevent.
    block["legs"]["premarket"] = _leg_report(
        bool(legs["premarket"]), premarket_reason,
        len(heard) if closes_payload is not None else None, 0, premarket_input)

    # ------------------------------------------------------------ the lists
    def top(leg: str, key, population=None) -> list[str]:
        source = population if population is not None else legs[leg]
        ranked = sorted(source, key=key, reverse=True)
        return ranked[:NOTABLE_LIST_SIZE]

    picks: dict[str, list[str]] = {name: [] for name in NOTABLE_LISTS}
    populations: dict[str, dict[str, tuple[Any, ...]]] = {}
    # What cleared each list's own FLOOR, before its ranking key is asked for.
    # Two stages rather than one, because "0 cleared the floor" and "0 carry
    # the key" are two different empties with two different fixes, and a single
    # population count collapses them into one number nobody can read. Three of
    # the four lists apply no floor, so cleared is the whole leg for them.
    cleared: dict[str, dict[str, tuple[Any, ...]]] = {}

    def with_sigma(leg: str) -> dict[str, tuple[Any, ...]]:
        return {s: v for s, v in legs[leg].items() if v[1] is not None}

    # Lists 1 and 4 rank on the SIZE of the sigma, not on its sign. They are
    # the unusualness lists and unusualness has no direction: a name 8 sigma
    # down is more unusual than one 6 sigma up, and ranking on the signed value
    # drops every large decliner off both of them. This is the same defect list
    # 3 carried until abs() was put on its key, and it survived here because
    # the fixture's only faller sat on the two session leg, so no claim could
    # tell the two orderings apart on these two.
    #
    # It was never hypothetical. On 2026-08-28 the premarket list published
    # five names at 0.26 sigma and below while MNSO sat on the same leg at
    # -2.51, and the prior session list dropped HRL at -8.00, the second most
    # unusual move in the whole 2,769 name universe, to publish VEEV at +6.04.
    # Across the five mornings the premarket list has run it lost the leg's
    # largest move on three of them.
    #
    # The row still carries the SIGNED sigma, so the direction stays on the
    # page and a reader sees which way the name went. Only the ordering is
    # taken on the size.
    cleared["prior_session_by_sigma"] = dict(legs["prior_session"])
    populations["prior_session_by_sigma"] = with_sigma("prior_session")
    picks["prior_session_by_sigma"] = top(
        "prior_session", lambda s: abs(legs["prior_session"][s][1]),
        populations["prior_session_by_sigma"])

    # See call TWO in the docstring: at least, not more than.
    cleared["prior_session_by_market_cap"] = {
        s: v for s, v in legs["prior_session"].items()
        if abs(v[0]) >= NOTABLE_MIN_ABS_GAP_PCT}
    populations["prior_session_by_market_cap"] = {
        s: v for s, v in cleared["prior_session_by_market_cap"].items()
        if s in caps}
    block["names_without_market_cap"] = len(
        [s for s in cleared["prior_session_by_market_cap"] if s not in caps])
    picks["prior_session_by_market_cap"] = top(
        "prior_session", lambda s: caps[s],
        populations["prior_session_by_market_cap"])

    cleared["two_session_by_move"] = dict(legs["two_session"])
    populations["two_session_by_move"] = dict(legs["two_session"])
    picks["two_session_by_move"] = top(
        "two_session", lambda s: abs(legs["two_session"][s][0]))

    cleared["premarket_by_sigma"] = dict(legs["premarket"])
    populations["premarket_by_sigma"] = with_sigma("premarket")
    picks["premarket_by_sigma"] = top(
        "premarket", lambda s: abs(legs["premarket"][s][1]),
        populations["premarket_by_sigma"])

    block["lists"] = dict(picks)

    # 4.9's rule applied one level down, and it is the part of this section
    # that was still missing. A list that comes back with nothing has to say
    # WHICH nothing it is, in one of four fixed states, beside the count it
    # considered, because "the column this ranks on does not exist yet" and
    # "the market was quiet" are different facts and a bare empty list cannot
    # tell them apart. It has not been hypothetical for one morning: every
    # return_stdev_20d in the database is null until the Sunday 21:00 rebuild,
    # so lists 1 and 4 have come back empty on their ranking key on every run
    # the section has ever made while their legs were perfectly available, and
    # the report said only that they were "short".
    #
    # The denominator travels with the state for the same reason the Summary
    # quotes "day eligible 3 of 12" rather than "day eligible 3": a count with
    # nothing under it cannot be read. considered is what the leg MEASURED,
    # qualified is what cleared this list's floor and carried its ranking key,
    # and selected is what it published. Three stages, and each pair of them
    # names a different failure.
    def list_report(name: str, leg: str) -> dict[str, Any]:
        leg_report = block["legs"].get(leg) or {}
        considered = len(legs[leg])
        qualified = len(populations[name])
        selected = len(picks[name])
        key = _LIST_RANKING_KEY[name]

        if not leg_report.get("available"):
            lost = leg_report.get("reason") or f"the {leg} leg is unavailable"
            if leg_report.get("input_present"):
                state = LIST_NOTHING_TO_RANK
                reason = (f"the {leg} leg's input was read and carried 0 rows "
                          f"this list could rank: {lost}")
            else:
                state = LIST_UNCOMPUTABLE
                reason = (f"the {leg} leg's input is missing, so this list "
                          f"could not be computed at all: {lost}")
        elif not cleared[name]:
            # Reachable only for a list that HAS a floor, which is list 2
            # alone. The other three rank whatever the leg measured, so an
            # empty cleared set means an empty leg, and the branch above has
            # already taken it.
            state = LIST_BELOW_THE_FLOOR
            reason = (f"0 of {considered} on the {leg} leg cleared this list's "
                      f"floor, {_LIST_FLOOR_TEXT[name]}. The leg was measured "
                      "and nothing in it reached that line.")
        elif qualified == 0:
            state = LIST_UNCOMPUTABLE
            reason = (f"0 of {considered} on the {leg} leg carry {key}, which "
                      f"is the key this list ranks on, so it could not be "
                      "computed.")
            absence = _key_absence(name, legs[leg], block)
            if absence:
                reason = f"{reason} {absence}"
        elif selected < NOTABLE_LIST_SIZE:
            state = LIST_RANKED
            reason = (f"{qualified} of {considered} on the {leg} leg qualified "
                      f"for this list, fewer than the {NOTABLE_LIST_SIZE} it "
                      "holds")
        else:
            state = LIST_RANKED
            reason = None

        report = {"state": state, "reason": reason, "leg": leg,
                  "ranks_on": key, "considered": considered,
                  "qualified": qualified, "selected": selected}
        report["text"] = _list_report_text(name, report)
        return report

    block["list_reports"] = {
        name: list_report(name, leg_of_list_key(name)) for name in NOTABLE_LISTS}
    # The reason strings on their own, because REPORT_TEMPLATE.md and
    # fallback_report have quoted list_reasons since the section shipped and
    # the archive holds packets carrying it. DERIVED from the reports above and
    # never written a second time, so the two cannot drift apart.
    block["list_reasons"] = {
        name: report["reason"]
        for name, report in block["list_reports"].items()}

    # ------------------------------------------------------------- the rows
    # Deduplication is WITHIN a leg and never across legs. A name selected by
    # both list 1 and list 2 becomes ONE row carrying both reasons, on the
    # pool_source precedent. A name selected on two different legs stays TWO
    # rows, because they are two measurements of different windows at different
    # vintages and a row can carry only one leg and one as_of_session. The
    # template must therefore not imply one row per name.
    selected_by: dict[tuple[str, str], list[str]] = {}
    order: list[tuple[str, str]] = []
    for name in NOTABLE_LISTS:
        leg = leg_of_list_key(name)
        for symbol in picks[name]:
            key = (leg, symbol)
            if key not in selected_by:
                selected_by[key] = []
                order.append(key)
            selected_by[key].append(name)

    stamp_for = {
        "premarket": session_date,
        "prior_session": sessions.get("c1"),
        "two_session": sessions.get("c1"),
    }
    rows: list[dict[str, Any]] = []
    unmeasured = 0
    for leg, symbol in order:
        # .get, not [.]. A list ranks one leg and stamps rows with the leg
        # _LIST_LEG names, and if those two ever disagree the symbol picked
        # from one leg is looked up in the other. That raised KeyError out of
        # notable_movers, which notable_section then catches, so a one word
        # mistake in a lookup table cost the whole section and reported itself
        # as a generic raise. It costs the row now, counted and named.
        entry = legs[leg].get(symbol)
        if entry is None:
            unmeasured += 1
            continue
        move, sigma, sigma_reason, price_time, price_age = entry
        candidate = by_symbol.get(symbol)
        catalyst, catalyst_state = _catalyst_of(candidate)
        rows.append({
            # Keyed "symbol" and uppercase, deliberately, and the reason
            # first written here was wrong.
            #
            # It said a row keyed "ticker" would pass vintage and then be
            # reported as invented by containment. It would not.
            # analyst._packet_uppercase_tokens starts with
            # `set(_TOKEN_RE.findall(packet_text))`, the RAW text of the whole
            # packet, before it walks the structure at all, and _TOKEN_RE stops
            # at the dot, so "AAPL.US" under any key at all already puts AAPL in
            # the allowed set. The structured walk over keys named symbol or
            # label adds both spellings a second time and changes nothing here.
            #
            # The real reasons are duller and they hold. vintage.py reads
            # `row.get("symbol") or row.get("ticker")`, so one spelling has to
            # be chosen and every other structure in this packet uses "symbol".
            # And the raw text scan is why the section's OTHER strings matter
            # more than its keys: measured on the real 2026-08-20 packet, adding
            # this block moved the allowed set from 139 tokens to 159, and all
            # twenty were the ten published symbols in both spellings.
            # claim_the_section_widens_containment_only_by_its_own_rows holds
            # that, and it is the check worth having rather than this one.
            "symbol": symbol,
            "leg": leg,
            "as_of_session": stamp_for[leg],
            "move_pct": move,
            "move_sigma": sigma,
            "move_sigma_reason": sigma_reason,
            "market_cap": caps.get(symbol),
            "name": names.get(symbol),
            "name_reason": None if symbol in names or not names else
                           "the universe file carries this field but has "
                           "nothing in it for this symbol",
            "market_cap_reason": None if symbol in caps else
                                 "this symbol has no market cap on file, so it "
                                 "was never examined against the floor",
            "catalyst": catalyst,
            "catalyst_state": catalyst_state,
            "also_on_watchlist": _watchlist_mark(candidate),
            # The premarket leg is the only one with an intraday price, and
            # vintage holds that one to the premarket window as well as to the
            # session. Null elsewhere means not applicable, not missing.
            "price_time": price_time,
            # The same print's age against the scan clock, in seconds, which
            # the gate above already computed to decide whether to keep this
            # row at all. A name that SURVIVES the gate can still be materially
            # old, and a reader given a bare timestamp has to subtract it from
            # a clock the report never prints. Null wherever price_time is.
            "price_age_seconds": price_age,
            "selected_by": selected_by[(leg, symbol)],
        })
    block["rows"] = rows
    block["malformed_closes_rows"] = malformed
    block["rows_without_a_measurement"] = unmeasured
    if unmeasured:
        packet.gap(f"notable movers: {unmeasured} selected row(s) name a symbol "
                   "the leg they are stamped with holds no measurement for, "
                   "which means a list ranked one leg and labelled another. The "
                   "rows are dropped rather than published against a window "
                   "nobody measured them over.")
    if malformed:
        packet.gap(f"notable movers: {malformed} row(s) in the closes sidecar "
                   "are not objects and were skipped. The examined counts come "
                   "from the file's own denominators, so they still count those "
                   "rows and the two numbers will not reconcile.")
    for leg in _LEG_SPAN_SESSIONS:
        if leg in block["legs"]:
            block["legs"][leg]["selected"] = sum(1 for r in rows if r["leg"] == leg)

    return block


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

    # Deliberately unguarded. A stale universe stops the morning, and
    # require_fresh_universe raises with the reason; catching it here only to
    # re-raise it said nothing and read as though something was handled.
    universe_payload = universe.require_fresh_universe()

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
    # WRITTEN BESIDE, AND PROMOTED ONLY IF THIS RUN'S PACKET IS KEPT.
    #
    # This used to copy straight over premarket_snapshot.jsonl, near the top of
    # build_packet, while thin_rerun_stands_down decides at the END of main
    # whether this run's packet is thinner than the one already on disk. A
    # rerun that stood down had therefore already replaced the snapshot the
    # KEPT packet describes: the packet's collector_stats counted one file and
    # the file beside it was another, and the fuller morning's capture was
    # gone. The stand-down exists to preserve the fuller evidence and was
    # destroying half of it on the way to doing so.
    #
    # main promotes this into place with os.replace when it keeps the packet,
    # and renames it to premarket_snapshot.superseded.jsonl when it stands
    # down, which is the same shape as the packet_degraded.json the stand-down
    # already writes: the thinner run is kept for the record and not over the
    # record.
    snapshot_path = config.run_dir(session_date) / "premarket_snapshot.pending.jsonl"
    # overwrite=True: this is a name only this run writes, so there is nothing
    # of an earlier morning's to spare here.
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
    # After pool_candidates, because that one asks whether the file is today's
    # and this one asks whether the collector was ever started on it. They are
    # different failures and 2026-08-24 was the second.
    _gap_for_subscription_divergence(watchlist, session_date, packet)
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
    # THE ZERO SHAPE, NOT AN EMPTY OBJECT. rank_by_measured_gap is only reached
    # inside `if candidates`, so a watchlist that subscribed nobody left
    # candidate_provenance["ranking"] as {} while REPORT_TEMPLATE.md's Summary
    # quotes ranking.subscribed_considered, cleared_floors, kept, cap and
    # capped_out by name and says in terms that the sentence is written the same
    # way on a morning when nothing is eligible, "the numbers are then zeros".
    # An absent key is not a zero: it leaves the model with nothing to quote on
    # exactly the morning the degrade path exists for, and the instruction it
    # cannot follow is the one that produces invented prose.
    rank_stats: dict[str, Any] = _empty_ranking()
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
        if unpriced and thin:
            # The one skip on the thin path that recorded nothing. These names
            # come out with provisional_gap_pct null and are counted into
            # rank_stats["unrankable"], whose note attributes the cause to the
            # collector or the pool. Neither is true here and the packet said
            # so nowhere.
            packet.gap(
                f"{len(unpriced)} subscribed name(s) reached the scan without a "
                "prior close from the pool, and the one end of day call each "
                f"that would have made them rankable was skipped: {quota_clause}. "
                "They are unrankable for that reason and not for the two "
                "rank_stats names."
            )
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
                # An empty dict cannot say WHY it is empty, and everything
                # downstream that reads a missing field out of it was blaming
                # the vendor. attach_float_rotation wrote "the delayed quote
                # carried no sharesFloat" for the whole watchlist on
                # 2026-08-20's degrade path, and REPORT_TEMPLATE.md tells the
                # model to quote the packet's reason rather than invent one, so
                # the report told its reader the vendor had no float data for
                # any name. No number was wrong; the provenance was false.
                candidate["quote_skipped"] = quota_clause
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
        # Before both ratio measures, because both divide the estimate it
        # attaches rather than the shares the socket saw.
        attach_capture_estimate(
            candidates, collect_premarket.latest_volume_check(session_date),
            packet)
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
        earnings_block = {"candidates": [], "notable_tomorrow": [],
                          "skipped": quota_clause,
                          "candidates_checked": False,
                          "tomorrow_checked": False}
    else:
        events = economic_events(api, packet)
        earnings_block = earnings(api, candidates, packet)

    # Layer 4. Assembled HERE rather than down in the packet literal, and the
    # position is forced rather than preferred: vintage.enforce runs on the next
    # statement against a hand built dict, so anything computed after it is
    # never vintage checked in this process. Check (e) exists entirely for these
    # rows, and until they were passed to it, it walked zero rows on every run
    # the project has ever made.
    #
    # It also attaches 4.2's three report fields to every candidate, off the
    # same closes file and gap statistics read, so the section and the candidate
    # rows cannot disagree about a name's sigma.
    notable = notable_section(session_date, universe_payload, bars_by_symbol,
                              candidates, packet)

    # After pricing, before scoring. A violation ends the run here: nothing is
    # stamped, no packet is written, and the chain stops before the analyst.
    vintage.enforce({
        "candidates": candidates,
        "market_snapshot": snapshot,
        "session_date": session_date,
        "notable_movers": notable,
    })

    if candidates:
        stamp_all(candidates, earnings_block)

    # AFTER stamp_all, because evaluate_eligibility runs inside it and the
    # section is assembled before vintage.enforce. See mark_notable_watchlist.
    notable_marked, notable_screened_neither = mark_notable_watchlist(
        notable, candidates)
    if notable_marked:
        packet.gap(
            f"notable movers: {notable_marked} row(s) name a symbol that is also "
            "on a watchlist this morning, and the row says so rather than being "
            "suppressed. Two sections selecting one symbol on different grounds "
            "is information.")
    if notable_screened_neither:
        packet.gap(
            f"notable movers: {notable_screened_neither} row(s) name a symbol "
            "the screens looked at and refused for BOTH watchlists. That is not "
            "an overlap between the two sections, it is the opposite, and it is "
            "counted apart from the line above for that reason.")

    # Read, never computed: see volume_check's docstring. Placed after the
    # screens have run so rvol_only_day_failures has decisions to read, and
    # before the packet is assembled so both land in gaps_to_fill in the order
    # a reader needs them, the measurement first and then what it cost.
    volume_measurement = volume_check(session_date, packet)
    rvol_only = rvol_only_day_failures(candidates, packet)
    # After the screens, because it reports what the correction MOVED and
    # there have to be decisions for it to have moved.
    capture_adjusted = capture_correction_report(candidates, packet)

    late_window = [c["symbol"] for c in candidates if c.get("pm_window_starts_late")]
    if late_window:
        packet.gap(
            "these candidates have a partial or absent premarket window and must be "
            f"labelled as such in the report: {', '.join(late_window)}"
        )

    thin_window = [c for c in candidates if c.get("pm_window_thin")]
    if thin_window:
        packet.gap(
            "these candidates have a THIN premarket window, which is a separate "
            "fact from a late one and a stronger one: every premarket level "
            "published for them rests on the handful of minutes named here, and "
            "the report must say so rather than calling them partial: "
            + ", ".join(
                f"{c['symbol']} on {c.get('pm_window_bars')} minute(s) "
                f"and {c.get('pm_volume') or 0:,.0f} shares"
                for c in thin_window)
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
            # The name this copy is promoted to when the packet is kept, never
            # the pending sibling it is written as: the packet is read long
            # after the promotion and must name the file that is there.
            "file": "premarket_snapshot.jsonl",
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
        "collector_coverage": collector_coverage(
            bars_by_symbol, session_date,
            collector_stats.get("replay_by_symbol")),
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
        # The briefing section. Three legs, four ranked lists, universe wide
        # for two of them, and no name here is screened, scored, given a
        # conviction or written to picks. See notable_movers.
        "notable_movers": notable,
        # WHAT THE RECORD HAS OBSERVED SO FAR, in counts with their own
        # denominators. Last week's winners and losers are worth nothing to
        # somebody reading this morning's report; the SHAPE of what those
        # trades did is worth something, and it is a different quantity.
        #
        # One local table read, no vendor call, so the 08:45 window is not
        # touched. It describes the ledger as of LAST NIGHT, because tonight's
        # pass has not run, and the report says so.
        "record_so_far": paper_ledger.record_so_far(),
        # Who is in which conviction bucket, and which way each one is moving.
        # Built here so the report neither enumerates a set it can miscount nor
        # ranks by a score that has no sign without saying so.
        "score_roll": score_roll(candidates),
        # The five membership lists the disclaimer and Skips and traps used to
        # ask the model to filter for. TEMPLATE_DERIVATIONS T2, T3, T15 and P1.
        # Each carries a ready to quote sentence written in counts, because the
        # report quotes these word for word and the quantifier guard scans what
        # comes back. See evidence_roll.
        "evidence_roll": evidence_roll(candidates),
        # Transient. main pops this before write_packet, so it never reaches
        # disk; the leading underscore is the convention true_volume uses for
        # the same reason.
        "_snapshot_pending": str(snapshot_path),
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
        # See capture_correction_report. The rows carry only symbols that
        # are candidates this morning, so this widens the containment allow
        # set by nothing. It stopped being "evidence, not a decision" on
        # 2026-08-21: the owner instructed the correction and both ratios
        # divide the estimate now, so this block is the audit trail for a
        # decision rather than a preview of one.
        "capture_correction": capture_adjusted,
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
        # Layer 4's axis. Without it a rerun that produced the full watchlist
        # and lost the whole notable section is thinner on nothing, and
        # thin_rerun_stands_down lets it overwrite a fuller packet.
        #
        # [corrected 2026-08-20: the second half of this note said "a packet
        # written before the section existed carries no such key, and
        # thinner_than iterates the PRIOR packet's keys, so an old one on disk
        # is compared on the axes it actually has". That is wrong in a way that
        # mattered. prior is evidence_width(prior_payload), computed by THIS
        # function, so an old packet yields notable_rows 0 rather than a missing
        # axis, and the axis was live on both sides from the first rerun. It is
        # excluded from _CANCELLING_AXES instead, which is the fix that was
        # actually needed.]
        "notable_rows": len((payload.get("notable_movers") or {}).get("rows") or []),
    }


# The axes on which a GAIN means "a different, better morning" rather than "a
# degraded copy". All four are candidate derived and move together: a rerun
# that priced more names also scored more of them, so a gain on one is evidence
# the whole morning improved.
#
# notable_rows is deliberately NOT here, and leaving it out is the whole point.
# It is universe derived and independent of the candidate path: the section
# reads the closes sidecar and the universe file, neither of which the watchlist
# touches, so it can gain while every candidate axis collapses. With it in the
# cancelling set, a rerun that lost every price, every RVOL and every score and
# published ten notable rows was judged "not thinner" and overwrote the 08:45
# packet, then upserted nulls over live picks rows as source='live'. Measured
# against the real 2026-08-20 packet: prior {'candidates': 12, 'priced': 12,
# 'with_rvol': 10, 'scored': 12, 'notable_rows': 0} against fresh
# {'candidates': 12, 'priced': 0, 'with_rvol': 0, 'scored': 0,
# 'notable_rows': 10} returned [], meaning not thinner.
#
# A LOSS on notable_rows still counts, which is why the axis was added at all.
_CANCELLING_AXES = ("candidates", "priced", "with_rvol", "scored")


def thinner_than(fresh: dict[str, int], prior: dict[str, int]) -> list[str]:
    """The axes on which fresh knows strictly less, empty unless it knows no more.

    A rerun that gains on a CANDIDATE axis is not a thinner rerun even if it
    loses on another, because that is a different morning rather than a
    degraded copy of this one, and standing down on it would be the guard
    refusing an improvement.

    A gain on an axis outside _CANCELLING_AXES cancels nothing. See the note
    above that constant: a briefing section that filled while the screen
    emptied is not an improved morning, and reading it as one let a gutted
    rerun replace a full packet.
    """
    if any(fresh[key] > prior[key]
           for key in prior if key in _CANCELLING_AXES):
        return []
    return sorted(key for key in prior if fresh[key] < prior[key])


def _promote_snapshot(pending: str | None, overwrite: bool = False) -> Path | None:
    """Move this run's collector copy into the name the packet names.

    THROUGH THE GUARD, because the name this promotes INTO is the morning's
    frozen capture and until 2026-08-31 this was a bare os.replace onto it.

    [corrected 2026-09-01: this said the name is "one of the two artifacts the
    nightly backup holds as having no route back". It is wrong on both halves:
    that backup copies FOUR artifacts, and this file is not among them. It
    holds data/premarket/<date>.jsonl, that file's two sidecars, and
    runs/<date>/packet.json, and this
    file is a byte prefix of the first, truncated at the last complete bar the
    packet records, so it is reconstructible from a file the backup does hold.
    Guarding it is still right, because reconstructing it needs the raw
    capture AND the packet that says where to cut, and the wrong reason for a
    correct guard is what a maintainer reasons from next.]

    snapshot_bars already resolves through artifacts, and reading that as
    cover was the mistake: what it guards is
    premarket_snapshot.pending.jsonl, a name only this run writes and which
    therefore has nothing to spare. scan passes overwrite=True there for
    exactly that reason. The frozen artifact is the name PROMOTED into, and
    this line reached it with no guard at all, so the protection added on
    2026-08-15 stopped at the caller it was written for.

    The failure it was written for is on record. A hand run of snapshot_bars
    replaced the frozen 08:45 snapshot for 2026-08-14 with the whole trading
    day, and it was noticed only because test_repricing reads that file.

    [corrected 2026-09-01: this went on to say "a hand run of THIS module at
    15:46 on 2026-08-21 replaced that morning's capture and its packet". The
    loss is real and the cause is not this module. That packet carries
    build.commit "stub" and collector_snapshot null, and build_packet can emit
    neither, so the run never went through main at all: it was the claim sweep
    writing fixture data directly, which is what the nightly backup module and
    conftest.py both already record. The guard here is still right and its
    justification is the 2026-08-14 morning above, which WAS a hand run.]

    thin_rerun_stands_down is not the answer either, and the same morning is
    why. It refuses a rerun carrying LESS evidence, and a hand run on a live
    tape hours after the open carries MORE: the whole session against the
    premarket window. It stands down on the case that was never dangerous
    and waves through the one that is.
    """
    if not pending:
        return None
    source = Path(pending)
    if not source.is_file():
        return None
    destination, _spared = artifacts.resolve(
        source.with_name("premarket_snapshot.jsonl"),
        overwrite or artifacts.scheduled_run(), what="scan snapshot")
    os.replace(source, destination)
    # The DESTINATION, so the caller can stamp it into the packet. A spared
    # run lands the capture beside the frozen one and the packet has to name
    # the file it actually describes; every number in its collector_snapshot
    # block was counted off this copy.
    return destination


def _demote_snapshot(pending: str | None) -> None:
    """Keep a stood-down run's collector copy beside the record, not over it.

    Same shape as the packet_degraded.json the stand-down already writes: what
    the thinner rerun saw is worth keeping and is not worth replacing the
    fuller morning's copy with.
    """
    if not pending:
        return
    source = Path(pending)
    if not source.is_file():
        return
    destination = source.with_name("premarket_snapshot.superseded.jsonl")
    os.replace(source, destination)
    print(f"scan: this rerun's collector copy was kept as {destination.name} "
          "rather than replacing the one the packet on disk describes.")


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
    existing_path = config.run_path(session_date) / "packet.json"
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


def write_packet(payload: dict[str, Any], overwrite: bool = False) -> Any:
    """Every run gets its own dated directory. Nothing is overwritten across days.

    ACROSS DAYS was the whole of the protection until 2026-08-31, and the
    hazard was never a second day. It is a second RUN of the same day, which
    is the operator path core/artifacts.py was written for and which this
    file was the last writer of an artifact not to be routed through.

    Nine call sites resolve through that guard: the collector snapshot, the
    midday packet and both midday renders, report.md, analyst_usage.json,
    report.html, verify_intraday.json and the nightly's recall file, which
    is not named here because the notable movers scope fence greps this
    module for it and is right to stay blunt. packet.json was not among
    them, and it is the one artifact whose own docstring, three lines down,
    says everything after this step reads it and a re-read of a past session
    reads it rather than picks. The nightly backup does hold it, as one of
    the four artifacts it copies.

    The atomic write below is kept and is a different guarantee: it stops a
    run interrupted mid write from leaving a packet that parses as nothing.
    It has never stopped a complete run from replacing a frozen one.

    runs/2026-08-21 carries what that costs: a packet stamped 15:46:38 holding
    one candidate, AAPL.US, beside twelve picks rows from that morning naming
    none of it. [corrected 2026-09-01: this attributed that packet to "a hand
    run at 15:46" of this module. It carries build.commit "stub" and
    collector_snapshot null, neither of which build_packet emits, so it was
    the claim sweep writing directly and it never reached main or the stand
    down. It is what a lost morning LOOKS like, which is why it is still
    quoted here, and it is not evidence about this code path.]

    A scheduled run owns today and overwrites freely, because a watchdog
    rerun of the morning chain is supposed to produce a fresh packet. A hand
    run is spared by default and writes beside, and --overwrite is how an
    operator says otherwise.

    Through a temp sibling and os.replace, on universe.write_atomically's
    precedent, because this is one of the two files CRITERIA [Backup] says has
    no route back. Everything after this step reads it, every _true column is
    later measured against the window it records, and a re-read of a past
    session reads it rather than picks. A plain write_text truncates the
    destination before it writes, so a run interrupted here left the morning
    with a packet that parses as nothing, and the 08:45 evidence a rerun then
    replaces was gathered off a different clock. That is the same loss the
    nightly backup exists to answer, an hour before the backup runs.

    Inline rather than through universe.write_atomically because that helper
    serialises without sort_keys and this file's readers are diffed across
    sessions.
    """
    run_directory = config.run_dir(payload["session_date"])
    path, _spared = artifacts.resolve(
        run_directory / "packet.json",
        overwrite or artifacts.scheduled_run(), what="scan")
    temporary = path.with_name(path.name + ".partial")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True),
                             encoding="utf-8")
        os.replace(temporary, path)
    finally:
        # A crash between the write and the replace leaves the partial behind;
        # nothing reads it, but it should not accumulate.
        temporary.unlink(missing_ok=True)
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
                # The estimate's own inputs, so the nightly truth pass can
                # compare like with like and CRITERIA's capture rate can be
                # re-derived from rows rather than re-argued. pm_volume is what
                # the socket saw; pm_volume_estimated is what both ratios above
                # actually divided.
                "pm_volume": candidate.get("pm_volume"),
                "pm_volume_estimated": candidate.get("pm_volume_consolidated"),
                "pm_capture_share": candidate.get("pm_capture_share"),
                "pm_capture_basis": candidate.get("pm_capture_basis"),
                "pm_high": candidate.get("pm_high"),
                "pm_low": candidate.get("pm_low"),
                "pm_vwap": candidate.get("pm_vwap"),
                # The morning's fill warning, so the night's verdict lands
                # beside what the morning was able to say rather than replacing
                # a blank. The two are different bands on different tapes and
                # the gap between them is worth keeping.
                "pm_band_volume": candidate.get("pm_band_volume"),
                "pm_band_minutes": candidate.get("pm_band_minutes"),
                "pm_band_notional": candidate.get("pm_band_notional"),
                "pm_band_state": candidate.get("pm_band_state"),
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
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace this session's packet and collector copy "
                             "rather than writing beside them. A scheduled run "
                             "does this anyway and owns today's artifacts; a "
                             "hand run is spared by default.")
    args = parser.parse_args(argv)

    if args.rescore:
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

    # Leading underscore: a transient this run needs and the frozen packet must
    # not carry. Same convention as true_volume's record keys.
    pending = payload.pop("_snapshot_pending", None)
    if thin_rerun_stands_down(payload):
        _demote_snapshot(pending)
        eodhd.print_call_report()
        return 0

    # THE PACKET NAMES THE COPY IT DESCRIBES. Both writes resolve through the
    # guard independently, so on a spared run the capture lands at
    # premarket_snapshot.handrun.jsonl while the packet lands at
    # packet.handrun.json, and the block inside it counted bars off the
    # former. A packet naming a file it did not describe is the pairing
    # failure the pending and promote design exists to prevent, reached again
    # on the new path.
    promoted = _promote_snapshot(pending, args.overwrite)
    if promoted is not None and isinstance(payload.get("collector_snapshot"), dict):
        payload["collector_snapshot"]["file"] = promoted.name
    path = write_packet(payload, args.overwrite)
    # Spared is readable off the name rather than threaded back through the
    # return, which four call sites unpack as a single value.
    spared = Path(path).name != "packet.json"
    # AND THE PICKS TABLE IS THE THIRD ARTIFACT OF THAT MORNING. write_picks
    # upserts on (date, ticker) with source among the updated columns, so a
    # hand run outside the [picks] live window rewrites the morning's rows and
    # flips them to test. Every nightly consumer filters on source='live', so
    # those names drop out of the ledger, the outcome fill and the weekly page
    # while the spared packet still lists them. Before the packet was spared
    # the two moved together and the record stayed self consistent; sparing
    # one and rewriting the other is what splits it.
    if spared:
        print("scan: REFUSED to rewrite the picks table. The packet was "
              "spared, so the rows on disk belong to the run that wrote the "
              "packet beside them, and upserting over them would flip that "
              "morning's source to test while its packet still names them. "
              "Pass --overwrite to replace both together.")
    else:
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
