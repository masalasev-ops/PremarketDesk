"""Replay the shipped day screen on a REAL premarket tape for a completed session.

WHAT THIS CLOSES. backtest_pool.SCREEN_SKIPPED says of the premarket RVOL
condition: "needs the collector's premarket volume, which exists only for names
subscribed on the day. There is no premarket tape for a historical session, so
this condition cannot be replayed and is not applied." That was true of every
source this project had when it was written, and it stopped being true when the
Alpaca probe measured what the free plan serves. Alpaca returns SIP one minute
bars for a session that is OVER, premarket minutes included, which is the one
thing a historical replay of this screen was missing. Measured before it was
believed: 2026-08-13 04:00 to 08:30 returns 243 bars for AAPL and 8 for DQ, so
the thin names are thin rather than absent.

So screen_passed's count stops being an upper bound with one condition quietly
dropped, and becomes the screen. All five day_setup conditions are replayable
now: gap_pct, price and market_cap from the caches backtest_pool already
built, require_above_prior_high from the end of day cache, and premarket_rvol
from the tape below.

TWO STAGES THAT NEVER RUN TOGETHER, the same split as backtest_pool and for the
same reason. Fetching is network bound and dated; evaluating must be
reproducible from the same bytes every time, or two runs of the same question
measure two different things.

  fetch     the Alpaca premarket tape for the names one cached session would
            have subscribed to, plus the same window on the prior sessions for
            the RVOL baseline. Written to data/backtest/premarket/<day>.json.
            The only stage that touches the network. No EODHD quota at all.

  evaluate  reads that cache and the backtest session cache, runs the SHIPPED
            screen through scan.evaluate_eligibility, and writes picks rows
            carrying source='reconstructed'.

WHAT IT DOES NOT REPLAY, named here rather than left for a reader to discover
from a null column. The rule this project keeps is that a number nobody can
produce honestly is left null with a reason, never computed from a stand in.

  swing_eligible    needs twoHundredDayAveragePrice, which no cache here holds
                    and which the EODHD quote endpoint only serves for today.
                    Left NULL. Computing it off a 200 bar mean of the end of
                    day cache would be a different quantity wearing the same
                    column name.
  score             needs the catalyst CLASS, which comes from EODHD news TAGS
                    per article. The session cache stores the news sweep as a
                    newest title and timestamp per name, not the tag lists, so
                    the class cannot be rebuilt. Left NULL with the reason in
                    score_unavailable, which is the same shape the morning uses
                    when a component was never observed.
  conviction        follows the score, so it is null for the same reason.

THE FENCE. Reconstructed rows are not the record. They are never pooled with
live ones, and there are three separate reasons that holds rather than one:

  1. picks is keyed on (date, ticker) and NOT on source, so a reconstructed row
     written over a date that already holds a live one would REPLACE it rather
     than sit beside it. That is worse than pooling. write_day below refuses
     the whole day if any non reconstructed row exists for it, and
     claim_a_reconstruction_never_displaces_the_record pins the refusal.
  2. Every production read of picks filters source='live'. That was true of
     most of them already and is now true of all of them;
     claim_every_production_read_of_picks_is_fenced enforces it on the next one
     somebody writes.
  3. Nothing here writes paper_trades. The ledger is the judging count and no
     reconstruction may enter it.

WHAT THE REPLAY MAY AND MAY NOT CONCLUDE is in DECISIONS.md, 2026-09-01
twelfth, and the short version is that it may describe the SCREEN and may not
describe an EDGE. Nothing about a reconstructed row licenses a trade, a
threshold move, or a go live flag.

Run:

    PYTHONPATH=src .venv/Scripts/python.exe -m research.replay_session --fetch 2026-08-13
    PYTHONPATH=src .venv/Scripts/python.exe -m research.replay_session --evaluate 2026-08-13 --write
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import statistics
from typing import Any

import probe_alpaca

from collect import baseline as baseline_rules
from core import criteria
from core import ettime
from core import store
from morning import scan
from night import true_volume
from research import backtest_pool
from selection import universe

_CRIT = criteria.load()

SOURCE = "reconstructed"
PREMARKET_DIR = backtest_pool.CACHE_DIR / "premarket"


def metrics_before(day: str) -> tuple[dict[str, dict[str, Any]], str, str | None]:
    """(ranking metrics, the gap_stats as_of they came from, the universe vintage).

    THE AS_OF IS STRICTLY BEFORE THE REPLAYED SESSION, which is what
    backtest_pool.load_metrics documents and what a bare load_metrics() does
    not do: it reads the newest complete window, whose propensity was computed
    partly from the session being replayed, so every key derived from it
    carried a look ahead advantage into the pool this replay claims the
    morning would have had. The newest as_of on disk before the day is used,
    and a day with none before it is refused rather than served the future.

    The universe carries no vintage per name, so its market caps are whatever
    the last weekly rebuild wrote; generated_at is returned so the payload
    can say which one, rather than leaving a reader to assume the caps were
    the day's.
    """
    with store.session() as connection:
        try:
            row = connection.execute(
                "SELECT MAX(as_of) AS as_of FROM gap_stats WHERE as_of < ?",
                (day,)).fetchone()
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                f"gap_stats cannot be read ({exc}), so no ranking metrics dated "
                f"before {day} exist and the pool cannot be replayed without "
                "a look ahead") from exc
    as_of = row["as_of"] if row else None
    if not as_of:
        raise RuntimeError(
            f"no gap_stats as_of on disk is dated before {day}, so the pool "
            "cannot be ranked without a look ahead; build one with "
            "selection.gap_stats for an earlier as_of first")
    vintage = universe.load_universe(require_fresh=False).get("generated_at")
    return backtest_pool.load_metrics(as_of), str(as_of), (
        str(vintage) if vintage else None)


def ensure_dirs() -> None:
    PREMARKET_DIR.mkdir(parents=True, exist_ok=True)


def cache_path(day: str) -> Any:
    return PREMARKET_DIR / f"{day}.json"


def _as_float(value: Any) -> float | None:
    return backtest_pool._as_float(value)


# ---------------------------------------------------------------- fetch stage


def subscribed_symbols(day: str, metrics: dict[str, dict[str, Any]]) -> list[str]:
    """The names this session would have subscribed to, through the shipped path.

    build_pool calls discover.assemble, so the tiers are production's tiers,
    and apply_cap applies [Discovery] max_subscribed_candidates. Reimplementing
    any of that here would replay a screen against a pool the morning would not
    have had.
    """
    inputs, _outcome = backtest_pool.load_session(day)
    pool = backtest_pool.build_pool(inputs, metrics)
    ranked = backtest_pool.order_pool(
        pool, metrics, backtest_pool.ORDERINGS["SHIPPED"])
    cap = _CRIT.integer("discovery", "max_subscribed_candidates")
    # The tier floor production runs, not apply_cap's default of zero. With
    # zero the cut is strict priority, which discover.apply_slots's own
    # docstring records never gave tiers 3 or 4 a slot in 60 sessions, so the
    # replay was subscribing a pool the morning would not have had.
    capped = backtest_pool.apply_cap(
        ranked, cap, _CRIT.integer("discovery", "min_slots_per_tier"))
    return [row["symbol"] for row in capped if row["subscribed"]]


def fetch(day: str, force: bool = False,
          probe: Any = None) -> dict[str, Any]:
    """One session's premarket tape and RVOL baseline, cached to disk.

    The cutoff is [Scan] run_time, the clock the morning writes its report on,
    NOT a fixed 08:45 and not the open. A window wider than the one the screen
    ran on would hand the replay volume the morning never saw, and the whole
    point of the exercise is to ask what the morning could have known.
    """
    ensure_dirs()
    path = cache_path(day)
    if path.is_file() and not force:
        return {"session_date": day, "skipped": "already cached",
                "path": str(path)}

    metrics, metrics_as_of, universe_vintage = metrics_before(day)
    symbols = subscribed_symbols(day, metrics)
    if not symbols:
        return {"session_date": day, "skipped": "the pool subscribed nobody"}

    cutoff = _CRIT.clock_text("scan", "run_time")
    session = dt.date.fromisoformat(day)
    # Alpaca wants bare codes; the rest of this project speaks SYMBOL.US.
    codes = [s.split(".")[0] for s in symbols]
    by_code = dict(zip(codes, symbols))

    probe = probe if probe is not None else probe_alpaca.Probe()
    start, end = true_volume._window(session, cutoff)
    # fetch_bars rather than fetch_window, for one reason: the LAST CLOSE.
    # CRITERIA [Day setup] prices on "the latest premarket print" and compares
    # that same print against the prior high, and fetch_window folds the bars
    # into sums that no longer carry it. A window vwap would stand in for the
    # last print in both conditions at once, and it is systematically below it
    # on a name that rose all morning, which is exactly the population this
    # screen is looking for. So the fold happens here where the close survives.
    bars, error = true_volume.fetch_bars(probe, codes, start, end)
    if error:
        return {"session_date": day, "error": error}

    baselines, sessions_used = true_volume.prior_sessions(
        probe, codes, session, cutoff)

    rows = {}
    for code, ordered in bars.items():
        volume = 0.0
        high = low = last_close = None
        price_volume = 0.0
        last_at = None
        for bar in ordered:
            size = float(bar.get("v") or 0)
            volume += size
            top, bottom = _as_float(bar.get("h")), _as_float(bar.get("l"))
            if top is not None:
                high = top if high is None else max(high, top)
            if bottom is not None:
                low = bottom if low is None else min(low, bottom)
            close = _as_float(bar.get("c"))
            if close is not None:
                last_close, last_at = close, str(bar.get("t") or "")
            typical = _as_float(bar.get("vw"))
            if typical is None and top is not None and bottom is not None and close is not None:
                typical = (top + bottom + close) / 3.0
            if typical is not None:
                price_volume += typical * size
        # Zeros KEPT, as collect/baseline.py keeps them: a session the tape
        # traded on and this name did not is a premarket volume of zero, and
        # dropping it was a second definition of the denominator.
        volumes = list(baselines.get(code) or [])
        rows[by_code[code]] = {
            "bars": len(ordered),
            "volume": volume,
            "high": high,
            "low": low,
            "last_close": last_close,
            "last_bar_at": last_at,
            "price_volume": price_volume,
            "baseline_median": statistics.median(volumes) if volumes else None,
            "baseline_sessions": len(volumes),
        }

    payload = {
        "session_date": day,
        "fetched_at": ettime.now_et().isoformat(),
        "window": f"{start.isoformat()} to {end.isoformat()}",
        "cutoff_hhmm": cutoff,
        "feed": _CRIT.text("truth", "feed"),
        "baseline_sessions_walked": sessions_used,
        # What ranked the pool, so the cache says which propensity window and
        # which universe rebuild the subscription list rests on.
        "metrics_as_of": metrics_as_of,
        "universe_generated_at": universe_vintage,
        "symbols": rows,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8")
    return {"session_date": day, "written": len(rows), "path": str(path)}


def cached_days() -> list[str]:
    if not PREMARKET_DIR.is_dir():
        return []
    return sorted(p.stem for p in PREMARKET_DIR.glob("*.json"))


# ------------------------------------------------------------- evaluate stage


def build_candidates(day: str) -> tuple[list[dict[str, Any]], list[str]]:
    """(candidates carrying every day screen input, notes about what is missing).

    The candidate dicts are shaped exactly as scan builds them, because
    scan.evaluate_eligibility is what judges them. A field the screen reads is
    either measured here or left None, and None fails a condition as unmeasured
    rather than passing it as zero, which is the behaviour that module already
    has and the reason it is worth reusing rather than reimplementing.
    """
    tape = json.loads(cache_path(day).read_text(encoding="utf-8"))
    inputs, _outcome = backtest_pool.load_session(day)
    metrics, metrics_as_of, universe_vintage = metrics_before(day)
    prior_bars = backtest_pool._eod_cache(inputs["prior_session"])
    prior_closes = inputs.get("prior_closes") or {}

    notes: list[str] = [
        f"ranking metrics are gap_stats as of {metrics_as_of}, the newest "
        f"window before {day}; market caps are the universe generated at "
        f"{universe_vintage or 'an unrecorded time'}, not the day's own"]
    out: list[dict[str, Any]] = []
    for symbol, row in sorted(tape["symbols"].items()):
        bars = int(row.get("bars") or 0)
        volume = _as_float(row.get("volume")) or 0.0
        high, low = _as_float(row.get("high")), _as_float(row.get("low"))
        pv = _as_float(row.get("price_volume"))
        vwap = (pv / volume) if (pv is not None and volume > 0) else None
        baseline = _as_float(row.get("baseline_median"))

        # The last premarket print the screen would have quoted, which is what
        # CRITERIA [Day setup] prices on and what require_above_prior_high
        # compares. The vwap is a different quantity and the high is a third
        # one, and either standing in here would move both conditions in the
        # same direction on the same names.
        price = _as_float(row.get("last_close"))
        prior_close = _as_float(prior_closes.get(symbol))
        gap = (((price - prior_close) / prior_close * 100.0)
               if (price is not None and prior_close) else None)
        # THE MORNING'S OWN FLOORS on the denominator. The live scan asks
        # baseline.usable_for_rvol, which refuses a baseline resting on fewer
        # than [Baseline] min_sessions_for_rvol sessions or a median under
        # min_baseline_premarket_volume shares, and nulls pm_rvol with the
        # reason. Until 2026-09-02 this divided by any positive median, so a
        # replayed name could clear a screen off a denominator the morning
        # would have refused to divide by.
        baseline_row = {"sessions_used": int(row.get("baseline_sessions") or 0),
                        "median_volume": baseline}
        usable, why_not = baseline_rules.usable_for_rvol(baseline_row)
        rvol = (volume / baseline) if usable else None

        candidate = {
            "symbol": symbol,
            "price": price,
            "gap_pct": gap,
            "prior_high": _as_float((prior_bars.get(symbol) or {}).get("h")),
            "pm_high": high,
            "pm_low": low,
            "pm_vwap": vwap,
            "pm_volume": volume,
            "pm_rvol": rvol,
            "pm_rvol_reason": None if usable else why_not,
            "pm_bars": bars,
            "baseline_median": baseline,
            "baseline_sessions": int(row.get("baseline_sessions") or 0),
            "quote": {
                "marketCap": (metrics.get(symbol) or {}).get("market_cap"),
                # Absent on purpose. See the module docstring: no cache here
                # holds it, and the swing screen is left unjudged rather than
                # judged on a substitute.
                "twoHundredDayAveragePrice": None,
            },
            # Unknown, not absent. The session cache holds a newest title per
            # name and not the tag lists, so nothing here can say whether the
            # window carried a catalyst.
            "catalyst_found": None,
            "catalyst_class": None,
        }
        out.append(candidate)

    notes.append("swing_eligible is not judged: twoHundredDayAveragePrice is "
                 "in no cache and catalyst_found cannot be rebuilt from a "
                 "newest title")
    notes.append("score is not computed: the catalyst class needs the EODHD "
                 "news tags per article and the session cache holds none")
    return out, notes


def evaluate(day: str) -> dict[str, Any]:
    """Run the shipped day screen over one session's reconstructed candidates."""
    candidates, notes = build_candidates(day)
    for candidate in candidates:
        scan.evaluate_eligibility(candidate)
    passed = [c for c in candidates if c.get("day_eligible")]
    unmeasured = [c for c in candidates if c.get("day_failed_unmeasured")]
    return {
        "session_date": day,
        "candidates": candidates,
        "notes": notes,
        "subscribed": len(candidates),
        "day_eligible": len(passed),
        "failed_on_something_unmeasured": len(unmeasured),
        "tally": scan.screen_tally(candidates),
    }


# ---------------------------------------------------------------------- write


def write_day(result: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    """Write one session's rows as source='reconstructed', or refuse the day.

    THE REFUSAL IS THE FENCE and it is here rather than in a caller because
    picks is keyed on (date, ticker) and NOT on source. A reconstructed row
    written over a date that already holds a live one does not sit beside it,
    it REPLACES it, and the live row is the only record this project has of
    what a morning actually published. So a day holding any row that is not
    itself reconstructed is refused whole, and the refusal names what it found.

    A previous reconstruction of the same day IS overwritten, because a replay
    that could not be re-run after a bug fix would be a worse instrument than
    no replay at all.
    """
    day = result["session_date"]
    rows = result["candidates"]
    entry_field = _CRIT.text("picks", "entry_ref_field")
    stop_field = _CRIT.text("picks", "stop_ref_field")
    now = ettime.now_et().isoformat()

    with store.session() as connection:
        store.init(connection)
        held = [dict(r) for r in connection.execute(
            "SELECT source, COUNT(*) AS n FROM picks WHERE date=? "
            "GROUP BY source", (day,))]
        foreign = {r["source"]: r["n"] for r in held if r["source"] != SOURCE}
        if foreign:
            return {"session_date": day, "written": 0, "refused": (
                f"{day} already holds "
                + ", ".join(f"{n} {src!r} row(s)" for src, n in sorted(foreign.items()))
                + ". picks is keyed on (date, ticker) and not on source, so a "
                "reconstructed row here would replace the record rather than "
                "sit beside it")}
        if dry_run:
            return {"session_date": day, "written": 0,
                    "dry_run": f"would write {len(rows)} row(s)"}

        written = 0
        for candidate in rows:
            store.upsert(connection, "picks", ["date", "ticker"], {
                "date": day,
                "ticker": candidate["symbol"],
                "source": SOURCE,
                "day_eligible": 1 if candidate.get("day_eligible") else 0,
                # NULL rather than 0. Not judged is not judged and failed.
                "swing_eligible": None,
                "score": None,
                "conviction": None,
                "score_unavailable": "; ".join(result["notes"]),
                "gap_pct": candidate.get("gap_pct"),
                "pm_rvol": candidate.get("pm_rvol"),
                "pm_high": candidate.get("pm_high"),
                "pm_low": candidate.get("pm_low"),
                "pm_vwap": candidate.get("pm_vwap"),
                "pm_volume": candidate.get("pm_volume"),
                "prior_high": candidate.get("prior_high"),
                "entry_ref": candidate.get(entry_field),
                "stop_ref": candidate.get(stop_field),
                # The tape IS the truth for a completed session, so these are
                # measured rather than estimated and the _true columns say so.
                "pm_volume_true": candidate.get("pm_volume"),
                "pm_rvol_true": candidate.get("pm_rvol"),
                "true_baseline_median": candidate.get("baseline_median"),
                "true_baseline_sessions": candidate.get("baseline_sessions"),
                "true_bars": candidate.get("pm_bars"),
                "truth_source": "alpaca",
                "truth_at": now,
                # No socket ever ran for this session. 0 would say the
                # collector was there and saw nothing.
                "collector_covered": None,
            })
            written += 1
        connection.commit()
    return {"session_date": day, "written": written}


# ----------------------------------------------------------------------- main


def report(result: dict[str, Any]) -> None:
    print(f"replay {result['session_date']}: {result['subscribed']} subscribed "
          f"name(s), {result['day_eligible']} clear the day screen, "
          f"{result['failed_on_something_unmeasured']} failed on something "
          "that was never measured")
    for note in result["notes"]:
        print(f"  not replayed: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fetch", metavar="DAY",
                        help="fetch one cached session's premarket tape")
    parser.add_argument("--evaluate", metavar="DAY",
                        help="screen one session from its cached tape")
    parser.add_argument("--write", action="store_true",
                        help="with --evaluate, write source='reconstructed' rows")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --write, say what would be written")
    parser.add_argument("--force", action="store_true",
                        help="with --fetch, refetch a session already cached")
    parser.add_argument("--list", action="store_true",
                        help="list the sessions whose tape is cached")
    args = parser.parse_args(argv)

    if args.list:
        days = cached_days()
        print(f"{len(days)} session(s) with a cached premarket tape")
        for day in days:
            print(f"  {day}")
        return 0

    if args.fetch:
        outcome = fetch(args.fetch, force=args.force)
        print(json.dumps(outcome, indent=2, sort_keys=True))
        return 1 if outcome.get("error") else 0

    if args.evaluate:
        if not cache_path(args.evaluate).is_file():
            print(f"replay: no cached tape for {args.evaluate}. Run --fetch first.")
            return 1
        result = evaluate(args.evaluate)
        report(result)
        if args.write:
            outcome = write_day(result, dry_run=args.dry_run)
            if outcome.get("refused"):
                print(f"replay: REFUSED to write {outcome['refused']}")
                return 1
            print(f"replay: {outcome.get('dry_run') or str(outcome['written']) + ' row(s) written'} "
                  f"as source={SOURCE!r}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
