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


# The day_setup lines that can be evaluated without the premarket tape, and the
# reason each of the others is excluded. This split is the whole point of the
# addressable target: recall measured against every gapper conflates a name
# discovery never saw with a name the screen was built to reject, and only the
# first is a discovery failure.
#
#   gap_pct                  IN.  Already the filter that forms the gapper set,
#                                 measured at the open from end of day bars.
#   price                    IN.  Evaluated against the session's actual open,
#                                 which is a better measurement than the
#                                 premarket proxy the live screen has to use.
#   market_cap               IN.  A static property of the name.
#   premarket_rvol           OUT. Needs collector volume against a cached
#                                 baseline. Unknowable for a name that was
#                                 never subscribed, which is exactly the
#                                 population being measured.
#   require_above_prior_high OUT. Needs a premarket print. Same reason.
#
# Excluding the last two means the addressable target is an UPPER bound on what
# the day screen could publish. That direction is the safe one for this
# argument: it cannot flatter discovery.
_ADDRESSABLE_CONDITIONS = ("price", "market_cap")

# Sensitivity points for the market cap floor. These are NOT thresholds and
# nothing reads them to make a decision. They exist so the floor's cost is a
# recorded number rather than an assumption, per the open question in
# DECISIONS.md. The live floor is always the one in CRITERIA.md [day setup].
_MARKET_CAP_SENSITIVITY = (
    ("1B, the CRITERIA floor", 1_000_000_000.0),
    ("800M, the swing floor", 800_000_000.0),
    ("500M, the universe floor", 500_000_000.0),
    ("300M", 300_000_000.0),
    ("no floor", 0.0),
)


def addressable_target(
    gappers: dict[str, dict[str, Any]],
    universe_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Which gappers the day screen could ever publish, and what each floor costs.

    Returns the surviving set plus a funnel, because the interesting number is
    not only how many survive but which line removed the rest. A floor that
    deletes most of the population it is screening is a different object from
    one that trims an edge case, and the two are indistinguishable from the
    survivor count alone.
    """
    price_rule = _CRIT.rule("day_setup", "price")
    cap_rule = _CRIT.rule("day_setup", "market_cap")

    after_price: dict[str, dict[str, Any]] = {}
    failed_price = 0
    for symbol, gapper in gappers.items():
        if price_rule.test(gapper.get("open")):
            after_price[symbol] = gapper
        else:
            failed_price += 1

    addressable: dict[str, dict[str, Any]] = {}
    failed_cap = 0
    no_cap_data = 0
    for symbol, gapper in after_price.items():
        row = universe_rows.get(symbol) or {}
        cap = _as_float(row.get("market_cap"))
        if cap is None:
            # Not a pass and not a fail. A name with no market cap on file was
            # never examined against the floor, and counting it either way
            # would report a judgement that was never made.
            no_cap_data += 1
            continue
        if cap_rule.test(cap):
            addressable[symbol] = {**gapper, "market_cap": cap}
        else:
            failed_cap += 1

    sensitivity = {}
    for label, floor in _MARKET_CAP_SENSITIVITY:
        survivors = 0
        for symbol in after_price:
            cap = _as_float((universe_rows.get(symbol) or {}).get("market_cap"))
            if cap is not None and cap > floor:
                survivors += 1
        sensitivity[label] = survivors

    return {
        "addressable": addressable,
        "funnel": {
            "gapped": len(gappers),
            "after_price_floor": len(after_price),
            "failed_price_floor": failed_price,
            "addressable": len(addressable),
            "failed_market_cap_floor": failed_cap,
            "no_market_cap_on_file": no_cap_data,
            "market_cap_floor_cost": failed_cap,
        },
        "market_cap_sensitivity": sensitivity,
        "conditions_applied": list(_ADDRESSABLE_CONDITIONS),
        "conditions_excluded": ["premarket_rvol", "require_above_prior_high"],
    }


def published_symbols(session_date: str) -> tuple[set[str], str | None]:
    """What actually reached the report for one session.

    Read from the packet rather than the pool, because the pool is what
    discovery found and the packet is what a reader saw. The gap between them
    is candidate_count, and that cap belongs in the funnel too.
    """
    path = config.run_dir(session_date) / "packet.json"
    if not path.is_file():
        return set(), f"no packet.json for {session_date}, so nothing can be said about what was published"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return set(), f"packet.json for {session_date} unreadable: {type(exc).__name__}"
    out = {
        str(c.get("symbol", "")).upper()
        for c in (payload.get("candidates") or [])
        if c.get("symbol")
    }
    return out, None


def _rate(numerator: int, denominator: int) -> float | None:
    """A fraction, or null when there is nothing to divide by.

    Zero addressable names is a distinct outcome from zero found, so an empty
    denominator yields null rather than a misleading 0.0 that reads as total
    failure. Every caller names its denominator in the key it assigns this to.
    """
    return round(numerator / denominator, 4) if denominator else None


def measure(
    gappers: dict[str, dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    addressable: dict[str, dict[str, Any]] | None = None,
    published: set[str] | None = None,
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
    addressable = addressable or {}
    published = published or set()

    addressable_held = sum(1 for row in held if row["symbol"] in addressable)
    addressable_subscribed = sum(
        1 for row in held if row["symbol"] in addressable and row.get("subscribed")
    )
    addressable_published = sum(1 for symbol in addressable if symbol in published)

    return {
        # The three counts, named so no reader has to infer which is which.
        "gapped": total,
        "addressable": len(addressable),
        "published_gappers": len(published & set(gappers)),
        "published_addressable_gappers": addressable_published,

        # Intermediate stages, kept because they separate a source that is not
        # looking from a cap that is too small.
        "pool_held": len(held),
        "addressable_pool_held": addressable_held,
        "subscribed_held": subscribed_hits,
        "addressable_subscribed_held": addressable_subscribed,

        # Every rate below carries its denominator in its own name. There is
        # deliberately no bare "recall" key: the denominator is the entire
        # disagreement this measurement exists to settle, and a reader who has
        # to supply it from memory will supply the wrong one. The old `recall`
        # and `subscribed_recall` are now the *_all_gappers pair.
        #
        # HEADLINE, denominator is the set the day screen could ever publish.
        "recall_addressable": _rate(addressable_published, len(addressable)),
        "discovery_recall_addressable": _rate(addressable_held, len(addressable)),
        "subscribed_recall_addressable": _rate(addressable_subscribed, len(addressable)),

        # Kept beside the headline, as the raw count the screen never claimed
        # to reach. Useful for spotting a floor that deletes the population.
        "recall_all_gappers": _rate(len(published & set(gappers)), total),
        "discovery_recall_all_gappers": _rate(len(held), total),
        "subscribed_recall_all_gappers": _rate(subscribed_hits, total),

        "denominators": {
            "addressable": (
                "universe names that gapped past the discovery gap floor AND "
                "satisfy every non-premarket day_setup condition, which is "
                "price and market_cap. premarket_rvol and "
                "require_above_prior_high are excluded because they need a "
                "premarket print that a name never subscribed to cannot have, "
                "so this is an upper bound on what the day screen could publish"
            ),
            "all_gappers": (
                "every universe name that gapped past the discovery gap floor, "
                "including those the day screen is built to reject"
            ),
        },

        "missed": missed,
        "held": held,
    }


def build(session_date: str | None = None, write: bool = True,
          overwrite: bool = False) -> dict[str, Any]:
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

    universe_rows = {
        str(row.get("symbol", "")).upper(): row
        for row in (universe_payload.get("symbols") or [])
    }
    target = addressable_target(gappers, universe_rows)
    published, published_reason = published_symbols(today.isoformat())

    result = measure(gappers, pool_rows, target["addressable"], published)
    payload = {
        "addressable_funnel": target["funnel"],
        "market_cap_sensitivity": target["market_cap_sensitivity"],
        "addressable_conditions_applied": target["conditions_applied"],
        "addressable_conditions_excluded": target["conditions_excluded"],
        "published_source": published_reason or f"runs/{today.isoformat()}/packet.json",
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

    funnel = payload["addressable_funnel"]
    print(f"pool_recall: {payload['gapped']} universe names gapped "
          f"{gap_rule.describe()} percent at the open")
    print(f"pool_recall: of those, {funnel['after_price_floor']} cleared the price floor "
          f"and {payload['addressable']} also cleared market_cap "
          f"{_CRIT.rule('day_setup', 'market_cap').describe()}, which is the "
          f"addressable target")
    print(f"pool_recall: the market cap floor removed {funnel['market_cap_floor_cost']} "
          f"gapper(s) this session; {funnel['no_market_cap_on_file']} had no market cap "
          f"on file and were examined against nothing")
    print(f"pool_recall: published {payload['published_addressable_gappers']} of "
          f"{payload['addressable']} addressable "
          f"(recall {payload['recall_addressable']} against the addressable target), "
          f"and {payload['published_gappers']} of {payload['gapped']} raw "
          f"(recall {payload['recall_all_gappers']} against all gappers)")
    print(f"pool_recall: discovery held {payload['pool_held']} raw, "
          f"{payload['addressable_pool_held']} addressable "
          f"(recall {payload['discovery_recall_addressable']} against the "
          f"addressable target), of which {payload['subscribed_held']} were subscribed")
    if published_reason:
        print(f"pool_recall: {published_reason}")
    for row in payload["missed"][:15]:
        print(f"    missed {row['symbol']:<12} gap at open {row['gap_at_open_pct']:+8.2f}%")
    if len(payload["missed"]) > 15:
        print(f"    ... and {len(payload['missed']) - 15} more")

    if write:
        from core import artifacts

        path, _spared = artifacts.resolve(
            config.run_dir(today.isoformat()) / "pool_recall.json",
            overwrite or artifacts.scheduled_run(),
            what="pool_recall",
        )
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"pool_recall: wrote {path}")
    return payload


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure what the morning candidate pool missed."
    )
    parser.add_argument("--date", metavar="YYYY-MM-DD",
                        help="Session to measure. Defaults to today in ET.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write pool_recall.json.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace an existing pool_recall.json under runs/. "
                             "Without it a hand run is spared and the copy is "
                             "written beside the original. The scheduled nightly "
                             "always overwrites, because it owns the artifact.")
    args = parser.parse_args(argv)

    try:
        payload = build(session_date=args.date, write=not args.dry_run,
                        overwrite=args.overwrite)
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
    sys.exit(job_status.run("pool_recall", main, ok_codes=OK_CODES))
