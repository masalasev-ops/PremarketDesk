"""Nightly measurement of what the morning's candidate pool missed.

Selection is a prior now: four things knowable before the open, unioned and
ranked, with no reading of today's tape because no source on this plan has one
for the whole universe at 07:15. A prior has blind spots by construction, and
the honest thing to do with a blind spot is price it rather than argue about
it.

So every night this reads today's end of day for the whole exchange, works out
which universe names actually gapped at the open, and asks how many of them the
morning pool held. The answer is a recall fraction and, more usefully, the list
of names it missed together with which source would have caught each one had
that source been looking. That list is what tells you whether the tier ordering
in CRITERIA.md is wrong, whether a source needs widening, or whether the
subscription cap is simply too small.

It costs two bulk end of day calls, today's and the prior session's, because
the gap is measured open against prior close and one call gives only one of
them. At a measured 98 counted calls each that is the nightly's whole bulk
spend; nothing else in that pass makes one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status
from selection import universe

_CRIT = criteria.load()


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def actual_gappers(
    rows: list[dict[str, Any]],
    prior_closes: dict[str, float],
    universe_symbols: set[str],
    gap_rule: Any,
) -> dict[str, dict[str, Any]]:
    """Universe names whose open gapped beyond the floor against the prior close.

    The open, not the close. A name that opened up nine percent and gave it all
    back by four o'clock was a premarket gapper and belongs in this set; judging
    it on its close would quietly redefine the thing being measured.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        symbol = code if "." in code else f"{code}.US"
        if symbol not in universe_symbols:
            continue
        open_price = _as_float(row.get("open"))
        prior_close = prior_closes.get(symbol)
        if open_price is None or not prior_close:
            continue
        gap = (open_price - prior_close) / prior_close * 100.0
        if not gap_rule.test(abs(gap)):
            continue
        out[symbol] = {
            "symbol": symbol,
            "gap_at_open_pct": round(gap, 4),
            "open": open_price,
            "prior_close": prior_close,
            "volume": _as_float(row.get("volume")),
        }
    return out


def measure(
    gappers: dict[str, dict[str, Any]],
    pool_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recall of the pool against the set that actually gapped.

    Held means the pool carried the name at all, subscribed or not. The cap is
    reported separately, because a name the pool found and then cut is a
    different failure from one it never found: the first is a cap that is too
    small, the second is a source that is not looking in the right place.
    """
    by_symbol = {str(r.get("symbol", "")).upper(): r for r in pool_rows}
    held: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    subscribed_hits = 0

    for symbol, gapper in sorted(gappers.items()):
        row = by_symbol.get(symbol)
        if row is None:
            missed.append({
                **gapper,
                "sources_that_would_have_caught_it": [],
            })
            continue
        subscribed = bool(row.get("subscribed", True))
        subscribed_hits += 1 if subscribed else 0
        held.append({
            **gapper,
            "pool_source": row.get("pool_source") or [],
            "pool_tier": row.get("pool_tier"),
            "pool_rank": row.get("pool_rank"),
            "subscribed": subscribed,
        })

    total = len(gappers)
    return {
        "gapped": total,
        "pool_held": len(held),
        "recall": round(len(held) / total, 4) if total else None,
        "subscribed_held": subscribed_hits,
        "subscribed_recall": round(subscribed_hits / total, 4) if total else None,
        "missed": missed,
        "held": held,
    }


def build(session_date: str | None = None, write: bool = True) -> dict[str, Any]:
    config.ensure_dirs()
    from selection import discover
    from morning import vintage

    today = ettime.parse_date(session_date) if session_date else ettime.today_et()
    # The same floor the morning screen uses, so recall is measured against the
    # set the system claims to be looking for rather than a second definition.
    gap_rule = _CRIT.rule("discovery", "gap_pct")

    universe_payload = universe.load_universe(require_fresh=False)
    universe_symbols = set(universe.universe_symbols(universe_payload))

    watchlist = discover.load_watchlist()
    pool_rows = watchlist.get("symbols", []) or []

    api = eodhd.client()
    prior = vintage.previous_trading_session(today)
    if prior is None:
        raise RuntimeError("the exchange calendar could not name the prior trading session")

    today_rows, error = api.eod_bulk_last_day("US", day=today)
    if error:
        raise RuntimeError(f"today's bulk end of day failed: {error}")
    prior_rows, error = api.eod_bulk_last_day("US", day=prior)
    if error:
        raise RuntimeError(f"the prior session bulk end of day failed: {error}")

    prior_closes: dict[str, float] = {}
    for row in prior_rows or []:
        code = str(row.get("code") or "").strip().upper()
        close = _as_float(row.get("close"))
        if code and close:
            prior_closes[code if "." in code else f"{code}.US"] = close

    gappers = actual_gappers(today_rows, prior_closes, universe_symbols, gap_rule)
    result = measure(gappers, pool_rows)
    payload = {
        "session_date": today.isoformat(),
        "generated_at": ettime.stamp(ettime.now_et()),
        "gap_floor": gap_rule.describe(),
        "measured_against": (
            "the open of today's end of day bar versus the prior session close, "
            "for every name in universe.json"
        ),
        "universe_size": len(universe_symbols),
        "pool_size": len(pool_rows),
        "watchlist_generated_at": watchlist.get("generated_at"),
        **result,
    }

    print(f"pool_recall: {payload['gapped']} universe names gapped "
          f"{gap_rule.describe()} percent at the open")
    print(f"pool_recall: the pool held {payload['pool_held']}, recall "
          f"{payload['recall']}, of which {payload['subscribed_held']} were "
          f"actually subscribed (recall {payload['subscribed_recall']})")
    for row in payload["missed"][:15]:
        print(f"    missed {row['symbol']:<12} gap at open {row['gap_at_open_pct']:+8.2f}%")
    if len(payload["missed"]) > 15:
        print(f"    ... and {len(payload['missed']) - 15} more")

    if write:
        path = config.run_dir(today.isoformat()) / "pool_recall.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"pool_recall: wrote {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure what the morning candidate pool missed."
    )
    parser.add_argument("--date", metavar="YYYY-MM-DD",
                        help="Session to measure. Defaults to today in ET.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write pool_recall.json.")
    args = parser.parse_args(argv)

    try:
        payload = build(session_date=args.date, write=not args.dry_run)
        job_status.produced("gappers measured", payload.get("gapped"))
    except Exception as exc:
        # A recall measurement that cannot be made is not a reason to fail the
        # nightly pass: nothing downstream depends on it. Broad on purpose,
        # and it prints the type: this used to catch RuntimeError only, so a
        # NameError in build() escaped into a non zero exit that the nightly
        # batch file ignores, and the step wrote nothing for a week without
        # anyone noticing.
        #
        # The exit code stays zero, because the chain must not break on a
        # diagnostic. The status record does not, because that is the half
        # that was missing: a week of NameError looked exactly like a week of
        # success from every angle a human could see. Tomorrow morning's
        # report will name this step.
        print(f"pool_recall: skipped, {type(exc).__name__}: {exc}")
        job_status.failed(f"{type(exc).__name__}: {exc}")
        eodhd.print_call_report()
        return 0

    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("pool_recall", main))
