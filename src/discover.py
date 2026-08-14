"""Morning discovery pass. Runs at 07:15 ET and writes the watchlist.

One bulk live call against the whole universe, one gap calculation, one sort.
That is the entire job. It costs exactly one API call no matter how large the
universe is, which is the reason the universe is allowed to be large.

This pass does not judge anything. It does not score, it does not check
catalysts, it does not decide what is tradeable. It answers one question: which
names are moving enough that the collector should be listening to them from
07:20. The scan at 08:45 rebuilds the candidate list from a fresh call and does
not trust this file for membership.

A note on what the live feed can and cannot tell us at 07:15. The bulk live
endpoint reports a last trade price and its timestamp. If that timestamp is
from yesterday's close rather than this morning, the gap is not a gap, it is
the absence of a premarket print. So every run reports how fresh the feed
actually was, and the watchlist carries those numbers. Do not skip that line.
"""

from __future__ import annotations

import argparse
import json
import statistics
from typing import Any

import config
import criteria
import eodhd
import ettime
import universe

_CRIT = criteria.load()


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def gap_percent(price: float, prior_close: float) -> float | None:
    """Percent versus prior close. A zero or missing prior close has no gap."""
    if not prior_close:
        return None
    return (price - prior_close) / prior_close * 100.0


def normalize_bulk_live(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Deduplicate the bulk live feed and throw away its ghost rows.

    The feed returns some tickers twice: one current row and one frozen
    snapshot from an old session that never aged out. Both look perfectly well
    formed. On 2026-08-13 the AZN ghost row read 188.41 against a 92.77 prior
    close, which is a fabricated +103 percent gap, and it sorted to the top of
    the watchlist ahead of every real mover. The ADT ghost was from 2023.

    Two defences. Keep only the newest timestamp per ticker, and drop anything
    older than max_quote_age_hours outright. Both counts are reported, because
    a sudden change in them means the feed changed and this code needs looking
    at again.

    Returns the surviving rows keyed by symbol, plus the statistics.
    """
    max_age_seconds = _CRIT.number("discovery", "max_quote_age_hours") * 3600.0
    now = ettime.now_et()

    newest: dict[str, dict[str, Any]] = {}
    duplicates_collapsed = 0
    for row in rows:
        symbol = str(row.get("code") or "").strip().upper()
        if not symbol:
            continue
        existing = newest.get(symbol)
        if existing is None:
            newest[symbol] = row
            continue
        duplicates_collapsed += 1
        if (_as_float(row.get("timestamp")) or 0) > (_as_float(existing.get("timestamp")) or 0):
            newest[symbol] = row

    kept: dict[str, dict[str, Any]] = {}
    dropped_stale: list[str] = []
    for symbol, row in newest.items():
        stamp = _as_float(row.get("timestamp"))
        if stamp is None:
            dropped_stale.append(symbol)
            continue
        age = (now - ettime.from_epoch_s(stamp)).total_seconds()
        if age > max_age_seconds:
            dropped_stale.append(symbol)
            continue
        kept[symbol] = row

    stats = {
        "rows_in": len(rows),
        "unique_symbols": len(newest),
        "duplicate_rows_collapsed": duplicates_collapsed,
        "dropped_as_stale": len(dropped_stale),
        "dropped_examples": sorted(dropped_stale)[:10],
        "max_quote_age_hours": _CRIT.number("discovery", "max_quote_age_hours"),
    }
    return kept, stats


def build(write: bool = True) -> dict[str, Any]:
    config.ensure_dirs()

    # The shared key preflight. The one bulk call below is the call this job
    # cannot skip: without it there is no watchlist and the collector has
    # nothing to subscribe to. So a degraded reading changes nothing here
    # except being recorded, and only the refuse floor stops the run.
    quota = eodhd.preflight("discover")
    if quota["refused"]:
        raise eodhd.QuotaRefusal(
            f"quota exhausted by another consumer on the shared key: "
            f"{eodhd.describe_preflight(quota)}, below the refuse floor of "
            f"{quota['refuse_below']:,} in CRITERIA.md [quota]"
        )

    universe_payload = universe.require_fresh_universe()
    universe_symbols = set(universe.universe_symbols(universe_payload))
    universe_started_with = len(universe_symbols)

    price_rule = _CRIT.rule("discovery", "price")
    gap_rule = _CRIT.rule("discovery", "gap_pct")
    keep = _CRIT.integer("discovery", "watchlist_size")

    print(f"discover: universe started with {universe_started_with} names")
    print(f"discover: floors are price {price_rule.describe()} and "
          f"absolute gap {gap_rule.describe()} percent")

    api = eodhd.client()
    rows, error = api.bulk_live_us()
    if error:
        raise RuntimeError(f"the single bulk live call failed: {error}")

    live, feed_stats = normalize_bulk_live(rows)
    print(f"discover: feed had {feed_stats['rows_in']} rows, "
          f"{feed_stats['duplicate_rows_collapsed']} duplicate rows collapsed, "
          f"{feed_stats['dropped_as_stale']} dropped as older than "
          f"{feed_stats['max_quote_age_hours']:g}h")

    now = ettime.now_et()
    today = now.date()
    matched = 0
    ages: list[float] = []
    stale_rows = 0
    candidates: list[dict[str, Any]] = []

    for symbol, row in live.items():
        if symbol not in universe_symbols:
            continue
        matched += 1

        price = _as_float(row.get("close"))
        prior_close = _as_float(row.get("previousClose"))
        if price is None or prior_close is None:
            continue

        stamp = _as_float(row.get("timestamp"))
        if stamp is not None:
            bar_time = ettime.from_epoch_s(stamp)
            ages.append((now - bar_time).total_seconds())
            if bar_time.date() < today:
                stale_rows += 1

        gap = gap_percent(price, prior_close)
        if gap is None:
            continue
        if not price_rule.test(price):
            continue
        if not gap_rule.test(abs(gap)):
            continue

        candidates.append(
            {
                "symbol": symbol,
                "gap_pct": round(gap, 4),
                "prior_close": round(prior_close, 4),
                "price": round(price, 4),
                "volume": _as_float(row.get("volume")),
                "quote_time": ettime.stamp(ettime.from_epoch_s(stamp)) if stamp else None,
            }
        )

    passed = len(candidates)
    candidates.sort(key=lambda row: abs(row["gap_pct"]), reverse=True)
    watchlist = candidates[:keep]

    median_age = statistics.median(ages) if ages else None
    feed = dict(feed_stats)
    feed.update(
        {
            "matched_universe": matched,
            "median_quote_age_seconds": round(median_age, 1) if median_age is not None else None,
            "rows_timestamped_before_today": stale_rows,
        }
    )

    # The same contract as the packet: reasons for degraded evidence live in
    # gaps_to_fill. Discover's one bulk call is unskippable, so a degraded
    # reading skips nothing here, but the reading itself is a gap the morning
    # must know about, and the baseline warm that follows in the same
    # scheduled job reads its own preflight and skips itself.
    gaps: list[str] = []
    if quota["degraded"]:
        gaps.append(
            f"quota preflight: {eodhd.describe_preflight(quota)}, below the "
            f"{quota['degrade_below']:,} threshold in CRITERIA.md [quota]. The one "
            "bulk call this job cannot skip was still made; everything skippable "
            "downstream should stand down."
        )

    payload: dict[str, Any] = {
        "generated_at": ettime.stamp(now),
        "quota_preflight": quota,
        "gaps_to_fill": gaps,
        "universe_started_with": universe_started_with,
        "universe_generated_at": universe_payload.get("generated_at"),
        "floors": {
            "price": price_rule.describe(),
            "gap_pct_absolute": gap_rule.describe(),
        },
        "passed_floors": passed,
        "watchlist_size": len(watchlist),
        "feed": feed,
        "api_calls": eodhd.call_count(),
        "symbols": watchlist,
    }

    print(f"discover: {len(live)} usable symbols, {matched} matched the universe")
    if median_age is not None:
        print(f"discover: median quote age {median_age:.0f}s, "
              f"{stale_rows} rows still carry a timestamp from before today")
        if stale_rows > matched / 2:
            warning = (
                f"{stale_rows} of {matched} live rows are timestamped before today. "
                "The bulk live feed is not printing premarket for most names, so these "
                "gaps are close to close, not premarket gaps. Treat the watchlist as "
                "provisional and check the 08:45 scan."
            )
            payload["feed_warning"] = warning
            print(f"WARNING  {warning}")
    print(f"discover: {passed} cleared the floors, keeping the top {len(watchlist)} by absolute gap")

    for row in watchlist[:10]:
        print(f"    {row['symbol']:<12} gap {row['gap_pct']:+7.2f}%  "
              f"prior close {row['prior_close']:>9.2f}  last {row['price']:>9.2f}")

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the morning watchlist.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write watchlist.json.")
    args = parser.parse_args(argv)

    try:
        build(write=not args.dry_run)
    except (universe.StaleUniverseError, eodhd.QuotaRefusal) as exc:
        print(f"REFUSING TO RUN: {exc}")
        eodhd.print_call_report()
        return 1
    except RuntimeError as exc:
        print(f"discover: failed, {exc}")
        eodhd.print_call_report()
        return 1

    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
