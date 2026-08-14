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

import baseline
import collect_premarket
import config
import criteria
import discover
import eodhd
import ettime
import store
import universe
import vintage

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
    for candidate in candidates:
        bars = bars_by_symbol.get(candidate["symbol"], [])
        price, price_at = _collector_last(bars)
        candidate["price"] = round(price, 4) if price is not None else None
        candidate["price_time"] = price_at
        candidate["price_source"] = "collector" if price is not None else None
        # Computed once, in attach_premarket_path, off these same bars.
        candidate["pm_volume"] = candidate.get("pm_volume_collected")


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
            "selection_gap_pct": candidate.get("selection_gap_pct"),
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
                "numerator_source": f"collector, from {numerator_window} ET",
                "denominator": row["median_volume"],
                "denominator_source": (
                    f"baseline median, accumulated from {denominator_window} ET "
                    f"to the {cutoff} cutoff over {row['sessions_used']} sessions"
                ),
                "is_lower_bound": numerator_window > denominator_window,
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


# ------------------------------------------------------ 7. economic events

def economic_events(api: eodhd.EodhdClient, packet: Packet) -> dict[str, Any]:
    """US only, high importance, today and tomorrow in ET."""
    country = _CRIT.text("scan", "economic_country")
    days_ahead = _CRIT.integer("scan", "economic_days_ahead")
    high_terms = [
        line.lower()
        for key, line in _CRIT.section("economic_importance").pairs
        if key == "high"
    ]

    today = ettime.today_et()
    end = today + dt.timedelta(days=days_ahead)
    rows, error = api.economic_events(country, today, end, limit=1000)
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
            when = dt.datetime.fromisoformat(raw_date).replace(tzinfo=ettime.ET)
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

    day_failed: list[str] = []
    if gap is None:
        day_failed.append(
            f"the gap was never computed: {candidate.get('gap_reason') or 'reason unrecorded'}"
        )
    elif not _CRIT.rule("day_setup", "gap_pct").test(gap):
        day_failed.append(f"gap_pct {gap:.2f} fails {_CRIT.rule('day_setup', 'gap_pct').describe()}")
    if not _CRIT.rule("day_setup", "price").test(price):
        day_failed.append(f"price {price} fails {_CRIT.rule('day_setup', 'price').describe()}")
    if not _CRIT.rule("day_setup", "market_cap").test(market_cap):
        day_failed.append(
            f"market_cap {market_cap} fails {_CRIT.rule('day_setup', 'market_cap').describe()}"
        )
    if not _CRIT.rule("day_setup", "premarket_rvol").test(candidate.get("pm_rvol")):
        day_failed.append(
            f"premarket_rvol {candidate.get('pm_rvol')} fails "
            f"{_CRIT.rule('day_setup', 'premarket_rvol').describe()}"
        )
    if _CRIT.flag("day_setup", "require_above_prior_high"):
        if prior_high is None or price is None or price <= prior_high:
            day_failed.append(f"price {price} is not above the prior day high {prior_high}")

    swing_failed: list[str] = []
    if gap is None:
        swing_failed.append(
            f"the gap was never computed: {candidate.get('gap_reason') or 'reason unrecorded'}"
        )
    elif not _CRIT.rule("swing_setup", "gap_pct").test(gap):
        swing_failed.append(
            f"gap_pct {gap:.2f} fails {_CRIT.rule('swing_setup', 'gap_pct').describe()}"
        )
    if not _CRIT.rule("swing_setup", "price").test(price):
        swing_failed.append(f"price {price} fails {_CRIT.rule('swing_setup', 'price').describe()}")
    if not _CRIT.rule("swing_setup", "market_cap").test(market_cap):
        swing_failed.append(
            f"market_cap {market_cap} fails {_CRIT.rule('swing_setup', 'market_cap').describe()}"
        )
    if _CRIT.flag("swing_setup", "require_open_above_prior_high"):
        if prior_high is None or price is None or price <= prior_high:
            swing_failed.append(
                f"premarket price {price} is not above the prior day high {prior_high}"
            )
    if _CRIT.flag("swing_setup", "require_open_above_200sma"):
        if sma200 is None or price is None or price <= sma200:
            swing_failed.append(f"premarket price {price} is not above the 200 day average {sma200}")
    if _CRIT.flag("swing_setup", "require_catalyst"):
        # Three states, not two. None means the news feed was never fetched
        # (failed call or quota skip), and an unchecked feed must not produce
        # a sentence claiming a search came back empty. Either way the
        # requirement is unmet, so both fail the screen; only the reason
        # differs, and the reason is what the report shows the reader.
        found = candidate.get("catalyst_found")
        if found is None:
            swing_failed.append("the news feed was never checked, so catalyst is unknown")
        elif not found:
            swing_failed.append("no catalyst was found")

    candidate["day_eligible"] = not day_failed
    candidate["day_failed"] = day_failed
    candidate["swing_eligible"] = not swing_failed
    candidate["swing_failed"] = swing_failed


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

    rvol = candidate.get("pm_rvol")
    if rvol is None:
        unknown("premarket_rvol", f"pm_rvol is null ({candidate.get('pm_rvol_reason')})")
    else:
        add("premarket_rvol", _CRIT.band_number("score_premarket_rvol", rvol),
            f"pm_rvol {rvol}")

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

def build_packet() -> dict[str, Any]:
    config.ensure_dirs()
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
    bars_by_symbol, collector_stats = collect_premarket.snapshot_bars(
        session_date, snapshot_path
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
    rank_stats: dict[str, Any] = {}
    if candidates:
        # All local: the premarket path, the price it implies, the drop, then
        # the ranking on that measured price. Not one API call has been spent
        # on a candidate yet, so the cut below costs nothing to be wrong about.
        attach_premarket_path(candidates, watchlist, packet, bars_by_symbol)
        price_from_collector(candidates, packet, bars_by_symbol)
        candidates, dropped = drop_uncovered(candidates, packet)

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
        if not thin:
            attach_catalysts(api, candidates, packet)

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
        },
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
        "gaps_to_fill": packet.gaps,
        "api_calls": eodhd.call_count(),
    }


def thin_rerun_stands_down(payload: dict[str, Any]) -> bool:
    """True when this quota thinned payload must not replace a fuller day.

    A rerun is only idempotent when it carries at least as much evidence as
    what it replaces. A quota thinned rerun of a day that already has a full
    width packet must not overwrite that packet, and must not upsert nulls
    over real values in picks, so it is written alongside as
    packet_degraded.json instead and the caller stands down. The watchdog's
    rerun of a broken chain then proceeds against the fuller packet.
    """
    quota = payload.get("quota_preflight") or {}
    if not quota.get("degraded"):
        return False
    existing_path = config.run_dir(payload["session_date"]) / "packet.json"
    if not existing_path.is_file():
        return False
    try:
        prior = json.loads(existing_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if (prior.get("quota_preflight") or {}).get("degraded"):
        return False  # equally thin; the fresher run may replace it
    side_path = config.run_dir(payload["session_date"]) / "packet_degraded.json"
    side_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"scan: a full width packet already exists for {payload['session_date']} "
          f"and this rerun is quota thinned. Wrote {side_path.name} for the "
          "record; packet.json and the picks table keep the fuller evidence.")
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
    raise SystemExit(main())
