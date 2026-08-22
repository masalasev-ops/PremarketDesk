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
them. At a measured 100 credits each that is the nightly's whole bulk
spend; nothing else in that pass makes one.
"""

from __future__ import annotations

import argparse
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


def published_symbols(session_date: str) -> tuple[set[str] | None, str | None]:
    """What actually reached the report for one session, or None for unknown.

    Read from the packet rather than the pool, because the pool is what
    discovery found and the packet is what a reader saw. The gap between them
    is candidate_count, and that cap belongs in the funnel too.

    None, not an empty set, for the two failure cases. An empty set is a
    measurement, "the report published nothing", and handing one back for a
    packet that is missing or unreadable puts a zero numerator over a real
    denominator. _rate below already argues that case for the denominator, "an
    empty denominator yields null rather than a misleading 0.0 that reads as
    total failure", and the reasoning was never carried across to the numerator.
    runs/2026-08-20/pool_recall.json is what that cost: a morning that produced
    no packet at all was recorded as having published none of what gapped.
    """
    path = config.run_path(session_date) / "packet.json"
    if not path.is_file():
        return None, f"no packet.json for {session_date}, so nothing can be said about what was published"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"packet.json for {session_date} unreadable: {type(exc).__name__}"
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
    published_reason: str | None = None,
) -> dict[str, Any]:
    """Recall of the pool against the set that actually gapped.

    Held means the pool carried the name at all, subscribed or not. The cap is
    reported separately, because a name the pool found and then cut is a
    different failure from one it never found: the first is a cap that is too
    small, the second is a source that is not looking in the right place.

    published None means nobody knows what reached the report, which is a
    different fact from a report that published nothing, and every published_*
    count and every recall_* rate built on one comes back null with
    published_unknown_reason beside it. The discovery_* and subscribed_* rates
    never read it and stay measured either way.
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
    # This line used to read `published = published or set()`, which collapsed an
    # unknown into a measured zero and then published it as one. A missing or
    # unreadable packet became published_gappers 0 and recall_addressable 0.0
    # against a real denominator, which reads as a morning that found 145
    # addressable gappers and published none of them.
    published_known = published is not None
    known = published if published_known else set()

    addressable_held = sum(1 for row in held if row["symbol"] in addressable)
    addressable_subscribed = sum(
        1 for row in held if row["symbol"] in addressable and row.get("subscribed")
    )
    addressable_published = sum(1 for symbol in addressable if symbol in known)
    published_gappers = len(known & set(gappers))

    return {
        # The three counts, named so no reader has to infer which is which.
        "gapped": total,
        "addressable": len(addressable),
        "published_gappers": published_gappers if published_known else None,
        "published_addressable_gappers": (
            addressable_published if published_known else None),
        # A null count is useless without this next to it, which is why the
        # reason is repeated here rather than left in the payload key that
        # names the packet path.
        "published_unknown_reason": None if published_known else (
            published_reason
            or "what the report published for this session is not known"),

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
        "recall_addressable": (
            _rate(addressable_published, len(addressable)) if published_known else None),
        "discovery_recall_addressable": _rate(addressable_held, len(addressable)),
        "subscribed_recall_addressable": _rate(addressable_subscribed, len(addressable)),

        # Kept beside the headline, as the raw count the screen never claimed
        # to reach. Useful for spotting a floor that deletes the population.
        "recall_all_gappers": (
            _rate(published_gappers, total) if published_known else None),
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


class NotMeasurable(RuntimeError):
    """There is nothing to measure yet, which is not the same as a failure.

    build() refuses rather than writing a payload of zeros, and that refusal is
    right. Reporting it as a FAILED step is not, because one shape of it
    happens every single weekday: the 07:00 nightly-catchup asks for a session
    that has not opened. Until 2026-08-20 that wrote zeros over the previous
    evening's real measurement; refusing fixed the artifact and would have put
    a red step in every morning report instead, which is how a real failure
    stops being visible.

    So a refusal on the evidence is a SKIP with its reason recorded, and
    anything else out of build() is still a failure. The distinction is
    deliberately not a clock: this module does not own the hour at which a
    session counts as complete, and a clock rule would make it behave
    differently depending on when a person ran it.
    """


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
    if not today_rows:
        # The test is on the DATA, not on the error, which is the rule
        # discover.prior_session_movers now applies to its own two bulk calls. A
        # 200 carrying an empty array is not an error, so this fell straight
        # through and every count below was computed from nothing: gapped 0,
        # addressable 0, pool_held 0, missed [], and no reason recorded anywhere
        # in the file. That artifact is on disk, runs/2026-08-20/pool_recall.json
        # stamped 07:01:18.
        #
        # 07:00 was the whole of it. tasks/register_tasks.ps1 registers
        # job_nightly.bat a second time at that hour as nightly-catchup, and
        # until 2026-08-20 that firing passed no argument and ran the whole
        # job, so this step asked the vendor for TODAY's end of day bars
        # before today's session had opened. On an ordinary day the 22:15 pass
        # overwrote the morning zeros; on a night that did not reach this
        # step, the surviving artifact read as a measured total failure of a
        # morning that produced no report at all. That firing passes "catchup"
        # now and job_nightly.bat exits before pool recall, so the schedule can
        # no longer reach this branch. A hand run still can.
        #
        # Refused on the evidence rather than on a clock. A clock guard would
        # have to name the hour at which a session counts as complete, which is
        # a threshold this file does not own, and it would make the step behave
        # differently depending on the hour somebody ran it.
        catchup = ""
        if today == ettime.today_et():
            catchup = (
                " This is the shape the 07:00 nightly-catchup invocation had "
                "before 2026-08-20, when it began passing 'catchup' and "
                "job_nightly.bat began exiting before pool recall. Reaching it "
                "now means a run asked for today's session before it closed, "
                "so pass --date with the prior session instead.")
        raise NotMeasurable(
            f"the bulk end of day for {today.isoformat()} came back with no rows, "
            "so there is nothing to measure, and a payload of zeros would be "
            "published as a morning that caught none of what gapped." + catchup)
    prior_rows, error = api.eod_bulk_last_day("US", day=prior)
    if error:
        raise RuntimeError(f"the prior session bulk end of day failed: {error}")
    if not prior_rows:
        # The same rule one call down. Every gap below is measured against a
        # prior close taken from this payload, so an empty one produces zero
        # gappers for the same reason an empty today produces zero opens, and
        # writes the same silent nothing.
        raise NotMeasurable(
            f"the prior session bulk end of day for {prior.isoformat()} came back "
            "with no rows, so no gap can be measured against a prior close and "
            "the run would publish zero gappers it never looked for")

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

    result = measure(gappers, pool_rows, target["addressable"], published,
                     published_reason=published_reason)
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
    if payload["published_unknown_reason"]:
        print("pool_recall: what the report published is not known, so every "
              "published count and every recall rate built on one is null: "
              f"{payload['published_unknown_reason']}")
    else:
        print(f"pool_recall: published {payload['published_addressable_gappers']} of "
              f"{payload['addressable']} addressable "
              f"(recall {payload['recall_addressable']} against the addressable target), "
              f"and {payload['published_gappers']} of {payload['gapped']} raw "
              f"(recall {payload['recall_all_gappers']} against all gappers)")
    print(f"pool_recall: discovery held {payload['pool_held']} raw, "
          f"{payload['addressable_pool_held']} addressable "
          f"(recall {payload['discovery_recall_addressable']} against the "
          f"addressable target), of which {payload['subscribed_held']} were subscribed")
    # published_reason used to be printed here as well. It is now named by the
    # branch above, which fires on exactly the same two cases, and printing the
    # same sentence twice teaches a reader to skim it.
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
    except NotMeasurable as exc:
        # Nothing to measure is not a failure. See NotMeasurable above: the
        # 07:00 catch-up hits this every weekday, and a step that reports FAILED
        # every weekday teaches its reader to stop reading it.
        print(f"pool_recall: nothing to measure, {exc}")
        job_status.produced("gappers measured", None)
        eodhd.print_call_report()
        return 0
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
