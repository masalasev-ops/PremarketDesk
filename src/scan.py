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

def market_snapshot(api: eodhd.EodhdClient, packet: Packet) -> list[dict[str, Any]]:
    """Last and change versus prior close for the index and macro line.

    Live is tried first. Indices, government bonds and the dollar index come
    back as NA there but are current in the end of day feed, so that is the
    fallback, and each row records which source answered.
    """
    mapping = _CRIT.pair_map("scan_snapshot", "snapshot")
    proxies = {}
    try:
        proxies = _CRIT.pair_map("scan_snapshot", "proxy")
    except criteria.CriteriaError:
        pass

    labels = list(mapping)
    symbols = [mapping[label] for label in labels]
    live, error = api.live_quotes(symbols)
    if error and not live:
        packet.gap(f"market snapshot live call failed: {error}")
        live = {}

    today = ettime.today_et()
    rows: list[dict[str, Any]] = []
    for label in labels:
        symbol = mapping[label]
        row: dict[str, Any] = {
            "label": label,
            "symbol": symbol,
            "last": None,
            "prior_close": None,
            "change": None,
            "change_pct": None,
            "source": None,
        }
        if label.lower() in proxies:
            row["proxy_note"] = proxies[label.lower()]

        quote = live.get(symbol) or {}
        last = _as_float(quote.get("close"))
        prior = _as_float(quote.get("previousClose"))
        if last is not None and prior:
            row.update({"last": last, "prior_close": prior, "source": "live"})
        else:
            bars, eod_error = api.eod(symbol, start=today - dt.timedelta(days=15), end=today)
            if eod_error or not bars:
                packet.gap(f"market snapshot {label} ({symbol}) unavailable: "
                           f"{eod_error or 'no end of day rows'}")
                rows.append(row)
                continue
            last = _as_float(bars[-1].get("close"))
            prior = _as_float(bars[-2].get("close")) if len(bars) > 1 else None
            row.update({
                "last": last,
                "prior_close": prior,
                "source": "eod",
                "as_of": bars[-1].get("date"),
            })

        if row["last"] is not None and row["prior_close"]:
            row["change"] = round(row["last"] - row["prior_close"], 6)
            row["change_pct"] = round(
                (row["last"] - row["prior_close"]) / row["prior_close"] * 100.0, 4
            )
        rows.append(row)
    return rows


# ------------------------------------------------------- 2. final candidates

def final_candidates(
    api: eodhd.EodhdClient, packet: Packet, universe_payload: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rebuild the candidate list from a fresh bulk call.

    watchlist.json is not trusted for membership. It was written ninety minutes
    ago and the tape has moved. It is still consulted, but only to answer a
    different question: was the collector listening to this name.
    """
    keep = _CRIT.integer("scan", "candidate_count")
    price_rule = _CRIT.rule("discovery", "price")
    gap_rule = _CRIT.rule("discovery", "gap_pct")
    universe_symbols = set(universe.universe_symbols(universe_payload))

    rows, error = api.bulk_live_us()
    if error:
        packet.gap(f"the fresh bulk live call failed: {error}. No candidates could be built.")
        return [], {"universe_started_with": len(universe_symbols), "failed": error}

    live, feed_stats = discover.normalize_bulk_live(rows)
    candidates: list[dict[str, Any]] = []
    for symbol, row in live.items():
        if symbol not in universe_symbols:
            continue
        price = _as_float(row.get("close"))
        prior_close = _as_float(row.get("previousClose"))
        if price is None or not prior_close:
            continue
        gap = (price - prior_close) / prior_close * 100.0
        if not price_rule.test(price) or not gap_rule.test(abs(gap)):
            continue
        candidates.append(
            {
                "symbol": symbol,
                "gap_pct": round(gap, 4),
                "price": round(price, 4),
                "prior_close": round(prior_close, 4),
                "bulk_volume": _as_float(row.get("volume")),
                "quote_time": ettime.stamp(ettime.from_epoch_s(row.get("timestamp")))
                if row.get("timestamp") else None,
            }
        )

    candidates.sort(key=lambda r: abs(r["gap_pct"]), reverse=True)
    provenance = {
        "universe_started_with": len(universe_symbols),
        "universe_generated_at": universe_payload.get("generated_at"),
        "cleared_floors": len(candidates),
        "kept": min(keep, len(candidates)),
        "floors": {"price": price_rule.describe(), "gap_pct_absolute": gap_rule.describe()},
        "feed": feed_stats,
    }
    print(f"scan: universe started with {len(universe_symbols)} names, "
          f"{len(candidates)} cleared the floors, keeping the top {min(keep, len(candidates))}")
    return candidates[:keep], provenance


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
                       "so ethVolume, market cap and the 200 day average are missing")
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
    """Prior day high and 20 day average volume, from the end of day feed."""
    lookback = _CRIT.integer("universe", "lookback_sessions")
    today = ettime.today_et()
    start = today - dt.timedelta(days=lookback * 2 + 10)

    for candidate in candidates:
        bars, error = api.eod(candidate["symbol"], start=start, end=today)
        if error or not bars:
            packet.gap(f"{candidate['symbol']} end of day history unavailable: "
                       f"{error or 'no rows'}. Prior day high and 20 day average volume are null.")
            candidate["prior_high"] = None
            candidate["avg_volume_20d"] = None
            continue

        # Today's own row is excluded. The prior day high means yesterday.
        completed = [b for b in bars if ettime.parse_date(str(b.get("date"))) < today]
        if not completed:
            packet.gap(f"{candidate['symbol']} has no completed session before today")
            candidate["prior_high"] = None
            candidate["avg_volume_20d"] = None
            continue

        candidate["prior_high"] = _as_float(completed[-1].get("high"))
        candidate["prior_session_date"] = completed[-1].get("date")
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
    watchlist_symbols = {
        str(r.get("symbol", "")).upper() for r in watchlist.get("symbols", [])
    }
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


# ------------------------------------------------------- 5. premarket RVOL

def attach_premarket_rvol(
    candidates: list[dict[str, Any]], packet: Packet, cutoff: str,
    quote_skip_reason: str | None = None,
) -> None:
    """ethVolume divided by the cached baseline median for the same clock cutoff.

    Never full day relative volume. If the denominator is not trustworthy the
    answer is null and the reason is recorded, because a number computed off the
    wrong denominator is worse than no number.

    quote_skip_reason is set when the delayed quote call was skipped on
    purpose (the quota degrade path). The recorded reason must then say so:
    blaming a vendor response that was never requested would be recording the
    wrong reason, which is as bad as recording no reason.
    """
    with store.session() as connection:
        store.init(connection)
        for candidate in candidates:
            candidate["pm_rvol"] = None
            candidate["pm_rvol_reason"] = None
            candidate["baseline"] = None

            eth_volume = (candidate.get("quote") or {}).get("ethVolume")
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
            if eth_volume is None:
                if quote_skip_reason:
                    # The collective quota gap already covers these, so no per
                    # symbol gap line is added here.
                    candidate["pm_rvol_reason"] = (
                        f"ethVolume was never fetched: {quote_skip_reason}"
                    )
                else:
                    candidate["pm_rvol_reason"] = "the delayed quote returned no ethVolume"
                    packet.gap(f"{candidate['symbol']} premarket RVOL is null: no ethVolume")
                continue

            candidate["pm_rvol"] = round(eth_volume / row["median_volume"], 4)


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
    gap = abs(candidate.get("gap_pct") or 0.0)
    market_cap = quote.get("marketCap")
    prior_high = candidate.get("prior_high")
    sma200 = quote.get("twoHundredDayAveragePrice")

    day_failed: list[str] = []
    if not _CRIT.rule("day_setup", "gap_pct").test(gap):
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
    if not _CRIT.rule("swing_setup", "gap_pct").test(gap):
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

    if thin:
        packet.gap(f"market snapshot skipped: {quota_clause}, below the "
                   f"{quota['degrade_below']:,} threshold in CRITERIA.md [quota]")
        snapshot = []
    else:
        snapshot = market_snapshot(api, packet)
    candidates, provenance = final_candidates(api, packet, universe_payload)

    # Snapshot the collector file before parsing it. The collector appends
    # until 09:25, so at 08:45 this read overlaps the write; the copy freezes
    # the bytes and a trailing partial line is discarded, not raised on.
    session_date = now.date().isoformat()
    snapshot_path = config.run_dir(session_date) / "premarket_snapshot.jsonl"
    bars_by_symbol, collector_stats = collect_premarket.snapshot_bars(
        session_date, snapshot_path
    )
    run_stats = collect_premarket.read_run_stats(session_date)
    if collector_stats.get("partial_line_discarded"):
        print("scan: the collector was mid write, one partial trailing line discarded")
    if run_stats and (run_stats.get("reconnects") or 0) > 0:
        print(f"scan: the collector reconnected {run_stats['reconnects']} time(s) "
              "this morning, noted in the packet")

    if candidates:
        if thin:
            # The collector file and the baseline cache are local, so the
            # premarket path and RVOL denominators still run below. What is
            # skipped is exactly the per candidate REST spend.
            packet.gap(
                "delayed quotes, daily history and news skipped for every "
                f"candidate: {quota_clause}. Market cap, ethVolume, the 200 day "
                "average, prior day high and catalysts are null for quota "
                "reasons, not vendor ones."
            )
            for candidate in candidates:
                candidate["quote"] = {}
                candidate["prior_high"] = None
                candidate["avg_volume_20d"] = None
                candidate["catalyst_found"] = None
                candidate["catalyst_error"] = f"news call skipped: {quota_clause}"
                candidate["headlines"] = []
        else:
            attach_quotes(api, candidates, packet)
            attach_daily_history(api, candidates, packet)
        attach_premarket_path(candidates, watchlist, packet, bars_by_symbol)
        attach_premarket_rvol(candidates, packet, cutoff,
                              quote_skip_reason=quota_clause if thin else None)
        if not thin:
            attach_catalysts(api, candidates, packet)

    if thin:
        packet.gap(f"economic events and the earnings calendar skipped: {quota_clause}")
        events = {"events": [], "skipped": quota_clause}
        earnings_block = {"candidates": [], "notable_tomorrow": [], "skipped": quota_clause}
    else:
        events = economic_events(api, packet)
        earnings_block = earnings(api, candidates, packet)

    if candidates:
        stamp_all(candidates, earnings_block)

    late_window = [
        c["symbol"] for c in candidates
        if c.get("pm_window_starts_late") or not c.get("collector_covered")
    ]
    if late_window:
        packet.gap(
            "these candidates have a partial or absent premarket window and must be "
            f"labelled as such in the report: {', '.join(late_window)}"
        )

    return {
        "generated_at": ettime.stamp(now),
        "session_date": now.date().isoformat(),
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

    if thin_rerun_stands_down(payload):
        eodhd.print_call_report()
        return 0

    path = write_packet(payload)
    write_picks(payload, force_test=args.test)
    print("")
    print(f"scan: wrote {path}")
    print(f"scan: {len(payload['candidates'])} candidates, "
          f"{len(payload['gaps_to_fill'])} gaps to fill")
    for candidate in payload["candidates"]:
        if candidate["score"] is None:
            score_text = (f"unscored (partial {candidate.get('score_partial')}, "
                          f"missing {len(candidate.get('score_unavailable') or [])})")
        else:
            score_text = f"{candidate['score']:>4.1f} {candidate['conviction']:<7}"
        print(
            f"    {candidate['symbol']:<10} gap {candidate['gap_pct']:+7.2f}%  "
            f"score {score_text} "
            f"day={'Y' if candidate['day_eligible'] else 'n'} "
            f"swing={'Y' if candidate['swing_eligible'] else 'n'}  "
            f"rvol={candidate.get('pm_rvol')}  covered={candidate.get('collector_covered')}"
        )
    for gap in payload["gaps_to_fill"]:
        print(f"    gap: {gap}")
    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
