"""What a RECONSTRUCTED pick did on its own session, so a base rate can exist.

WHAT THIS CLOSES. replay_session replays the shipped day screen on a real
premarket tape and writes picks rows carrying source='reconstructed'. It stops
at the screen's verdict. Nothing then asks the only question a reader has,
which is what those names went on to do, and without that the Precedent screen
has nothing to count. This module is the second half: the regular session for
each reconstructed pick, run through the SHIPPED paper rule, written to
research_outcomes.

paper_ledger.simulate is IMPORTED and not reimplemented. A base rate and the
live ledger have to be the same instrument or the screen is comparing a rule
against a different rule and calling the difference a finding. When [Paper]
rule_version moves, both move, and the version travels on every row here
exactly as it does on a live one.

TWO STAGES THAT NEVER RUN TOGETHER, the same split as backtest_pool and
replay_session and for the same reason. Fetching is network bound and dated;
evaluating must be reproducible from the same bytes every time, or two runs of
the same question measure two different things.

  fetch     the Alpaca REGULAR session bars, 09:30 to the close, for the names
            one replayed session actually admitted. Written to
            data/backtest/outcomes/<day>.json. The only stage that touches the
            network, and it spends no EODHD quota at all.

  evaluate  reads that cache, the premarket cache replay_session built and the
            reconstructed picks rows, cuts the six match bands, runs simulate,
            and returns rows. Writes nothing by itself.

THE BANDS ARE FROZEN ONTO THE ROW. gap_band, rvol_band, price_band and
cap_band are computed here and stored, not derived when the screen reads them.
A band edge moving in CRITERIA would otherwise silently re-cut every historical
group, and a base rate whose population changes when a config file is edited is
not reproducible from the bytes that produced it. Moving an edge means
re-running evaluate, which is the point.

THE FENCES, three of them, and all three are about the same danger: a
reconstructed number being read as the record.

  1. write_day refuses a whole day if picks holds any non reconstructed row for
     it. Same rule and same reason as replay_session.write_day, restated rather
     than inherited because the tables differ.
  2. research_outcomes is its own table. It is never paper_trades with a flag,
     because paper_trades is keyed on (date, ticker, rule_version) with no
     source in the key, so a reconstructed row over a live date would REPLACE
     the live one rather than sit beside it.
  3. Nothing here writes to picks, to picks outcome columns, or to
     paper_trades. A claim greps this module and fails if that stops being
     true.

WHAT IT DOES NOT MEASURE, named here rather than left for a reader to find as
a null column. score and conviction are NULL on every reconstructed row,
because the catalyst class needs EODHD news tags the session cache does not
hold. So this module cannot group by conviction and the Precedent screen must
not either. The one catalyst fact that IS reconstructible is whether the name
reported after the prior close, from the session cache's earnings list, and it
travels as earnings_overnight.

The match rule, the widening ladder and the confounds are pre-registered in
doc/research/PRECEDENT_PREREGISTRATION.md, which was written before this file
had a reader. Changing a band edge is an amendment there, not an edit to
CRITERIA on its own.

Run:

    set PYTHONPATH=%CD%\\src
    .venv\\Scripts\\python.exe -m research.replay_outcomes --fetch --day 2026-07-14
    .venv\\Scripts\\python.exe -m research.replay_outcomes --evaluate --day 2026-07-14
    .venv\\Scripts\\python.exe -m research.replay_outcomes --all
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from typing import Any

from core import config, criteria, ettime, files, lookalike, store
from night import paper_ledger
from research import backtest_pool, replay_session

# The band cutter and the overnight predicate live in core/lookalike.py and are
# re-exported here, because this module's callers and the desk's matcher have to
# cut identically or every group is empty forever. See that module's docstring
# for what went wrong when they did not.
band = lookalike.band
gap_band = lookalike.gap_band
bands_for = lookalike.bands_for
_edges = lookalike.edges

_CRIT = criteria.load()

SOURCE = replay_session.SOURCE
OUTCOMES_DIR = backtest_pool.CACHE_DIR / "outcomes"

# The pre-registration has to exist before a single outcome is written. It is
# not decoration: the bands below are only meaningful because they were fixed
# before anybody could see which bands flatter the desk, and that claim rests
# on a file with a date on it.
PREREGISTRATION = config.PROJECT_ROOT / "doc" / "research" / "PRECEDENT_PREREGISTRATION.md"

# Written onto a row that could not be graded, in words, instead of a zero.
NO_BARS = "no regular session bars for this name on this date"
NO_REFS = "the reconstructed screen produced no entry or stop reference"


def ensure_dirs() -> None:
    OUTCOMES_DIR.mkdir(parents=True, exist_ok=True)


def cache_path(day: str) -> Any:
    return OUTCOMES_DIR / f"{day}.json"


def cached_days() -> list[str]:
    if not OUTCOMES_DIR.is_dir():
        return []
    return sorted(p.stem for p in OUTCOMES_DIR.glob("*.json"))


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- the fetch --

def _reconstructed_rows(day: str) -> list[dict[str, Any]]:
    """The reconstructed picks for one day. Fenced on source, every time.

    CRITERIA [Picks] and every production reader filter source='live'. This is
    the mirror of that fence and it is written out rather than passed in, so a
    reader of this module can see which population it is standing in.
    """
    with store.session() as connection:
        store.init(connection)
        return [dict(row) for row in connection.execute(
            "SELECT ticker, day_eligible, gap_pct, pm_rvol, prior_high, "
            "pm_high, pm_low, entry_ref, stop_ref FROM picks "
            "WHERE date=? AND source=? ORDER BY ticker", (day, SOURCE))]


def fetch(day: str, force: bool = False, probe: Any = None) -> dict[str, Any]:
    """One session's regular hours minutes for its reconstructed picks.

    Only the names that produced an entry and a stop are fetched. A row with
    neither cannot be simulated under any rule, so bars for it would be
    requests spent on a question that has no answer.
    """
    ensure_dirs()
    path = cache_path(day)
    if path.is_file() and not force:
        return {"session_date": day, "skipped": "already cached", "path": str(path)}

    rows = _reconstructed_rows(day)
    if not rows:
        return {"session_date": day,
                "skipped": "no reconstructed picks rows for this date"}
    tradeable = [r for r in rows
                 if r["entry_ref"] is not None and r["stop_ref"] is not None]
    if not tradeable:
        return {"session_date": day,
                "skipped": "no reconstructed row carries an entry and a stop"}

    from night import true_volume
    import probe_alpaca

    probe = probe if probe is not None else probe_alpaca.Probe()
    start, end = paper_ledger.session_window(day)
    codes = sorted({r["ticker"].split(".", 1)[0] for r in tradeable})
    bars, error = true_volume.fetch_bars(probe, codes, start, end)
    if error:
        return {"session_date": day, "error": error}

    payload = {
        "session_date": day,
        "fetched_at": ettime.now_et().isoformat(),
        "window": f"{start.isoformat()} to {end.isoformat()}",
        "feed": _CRIT.text("truth", "feed"),
        "requested": codes,
        # Bars kept whole and in order. simulate reads them in sequence and an
        # OHLC fold here would destroy the one property it depends on.
        "bars": {code: bars.get(code) or [] for code in codes},
    }
    files.write_json_atomically(path, payload, indent=2, sort_keys=True,
                                attempts=files.ATTEMPTS, retry_s=files.RETRY_S)
    served = sum(1 for code in codes if payload["bars"][code])
    return {"session_date": day, "written": len(codes), "with_bars": served,
            "path": str(path)}


# ------------------------------------------------------------ the evaluate --

def _session_facts(day: str) -> tuple[dict[str, dict[str, Any]], set[str] | None,
                                      list[str]]:
    """(price and cap per symbol, the earnings names or None, notes).

    build_candidates is called rather than reimplemented, for the same reason
    replay_session calls scan.evaluate_eligibility: the price this bands on has
    to be the price the screen priced on, and a second definition of it here
    would be a different quantity wearing the same column name.

    THE EARNINGS SET IS None WHEN THE CALL FAILED, and that is the whole point
    of returning it separately. discover.earnings_reporters records a status,
    and a session whose calendar came back NOT_FETCHED has an EMPTY names list
    that is indistinguishable from a session on which nobody reported. Writing
    0 for every name on such a session stores an unasked question as a measured
    no, on the one condition the widening ladder may never drop, so the whole
    group for every name of that session would be drawn from the wrong
    population. This is CRITERIA's standing rule and the defect class that two
    thirds of this project's closed defects belong to.
    """
    candidates, notes = replay_session.build_candidates(day)
    facts = {c["symbol"]: {
        "price": _as_float(c.get("price")),
        "market_cap": _as_float((c.get("quote") or {}).get("marketCap")),
    } for c in candidates}
    inputs, _outcome = backtest_pool.load_session(day)
    block = (inputs.get("earnings") or {})
    status = str(block.get("status") or "").strip().lower()
    if status and status != "ok":
        notes.append(f"the earnings calendar for {day} came back '{status}', so "
                     "earnings_overnight is null on every row of this session "
                     "rather than zero")
        return facts, None, notes
    return facts, set(block.get("names") or []), notes


def evaluate(day: str) -> dict[str, Any]:
    """Grade one replayed session. Writes nothing."""
    path = cache_path(day)
    if not path.is_file():
        return {"day": day, "rows": [], "skipped": "no outcomes cache; run --fetch"}
    cache = json.loads(path.read_text(encoding="utf-8"))
    rows = _reconstructed_rows(day)
    if not rows:
        return {"day": day, "rows": [], "skipped": "no reconstructed picks rows"}

    facts, earnings, notes = _session_facts(day)
    versions = paper_ledger.rule_versions()
    stamp = ettime.stamp(ettime.now_et())
    out: list[dict[str, Any]] = []

    for row in rows:
        ticker = row["ticker"]
        code = ticker.split(".", 1)[0]
        fact = facts.get(ticker) or {}
        cap = fact.get("market_cap")
        cap_musd = (cap / 1_000_000.0) if cap is not None else None
        gap = _as_float(row["gap_pct"])
        rvol = _as_float(row["pm_rvol"])
        price = fact.get("price")
        cut = bands_for(gap, rvol, price, cap_musd)

        # An unmeasured prior high is not a name that failed the condition.
        # None travels as None and the screen refuses to match on it.
        prior_high = _as_float(row["prior_high"])
        above = None
        if prior_high is not None and price is not None:
            above = 1 if price > prior_high else 0

        entry = _as_float(row["entry_ref"])
        stop = _as_float(row["stop_ref"])
        bars = cache.get("bars", {}).get(code) or []

        # None, not 0, when the calendar was never read. See _session_facts.
        overnight = None if earnings is None else (1 if ticker in earnings else 0)

        for version, mode in versions.items():
            record: dict[str, Any] = {
                "date": day, "ticker": ticker, "rule_version": version,
                "earnings_overnight": overnight,
                "above_prior_high": above,
                "gap_pct": gap, "pm_rvol": rvol,
                "price_ref": price, "market_cap_musd": cap_musd,
                "booked": 0, "skip_reason": None,
                "entry_ref_used": entry, "stop_ref_used": stop,
                "entry_price": None, "exit_price": None, "exit_reason": None,
                "pnl_pct": None, "max_drawdown_pct": None, "mfe_pct_held": None,
                "minutes_to_trigger": None, "minutes_to_peak": None,
                "bars_held": None, "match_note": None, "computed_at": stamp,
            }
            record.update(cut)
            if entry is None or stop is None:
                # booked stays NULL, never 0. A 0 here is byte for byte what a
                # measured non trigger looks like, and the screen's headline
                # figure is "how many of this shape reached the buy". A name
                # that could not be graded at all belongs in NEITHER the
                # numerator nor the denominator of that, and desk/precedent
                # excludes it on skip_reason for exactly this reason.
                record["booked"] = None
                record["skip_reason"] = NO_REFS
            elif not bars:
                record["booked"] = None
                record["skip_reason"] = NO_BARS
            else:
                result = paper_ledger.simulate(bars, entry, stop, mode)
                for key in ("booked", "entry_price", "exit_price", "exit_reason",
                            "pnl_pct", "max_drawdown_pct", "mfe_pct_held",
                            "minutes_to_trigger", "minutes_to_peak", "bars_held"):
                    record[key] = result.get(key)
            # The one catalyst fact this population holds, said on every row so
            # a reader of the table is never left to infer it from an absence.
            record["match_note"] = (
                "catalyst class is null for a reconstructed row; the only "
                "catalyst fact here is earnings_overnight")
            out.append(record)

    return {"day": day, "rows": out, "notes": notes,
            "versions": sorted(versions), "window": cache.get("window")}


# --------------------------------------------------------------- the write --

def write_day(result: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    """Write one day's rows, or refuse the whole day and say why.

    THE REFUSAL IS THE POINT. A date that already holds a live picks row is a
    date the desk really ran, and grading it here would put a reconstruction
    beside the record where a later reader could pool them. The check is on
    picks and not on research_outcomes, because picks is where the live and
    reconstructed populations meet.
    """
    day = result["day"]
    rows = result.get("rows") or []
    if not rows:
        return {"day": day, "written": 0, "refused": result.get("skipped")}
    if not PREREGISTRATION.is_file():
        return {"day": day, "written": 0,
                "refused": f"{PREREGISTRATION.name} is missing. The bands are "
                           "only meaningful because they were fixed before any "
                           "outcome existed, and that rests on a dated file"}

    with store.session() as connection:
        store.init(connection)
        live = connection.execute(
            "SELECT COUNT(*) FROM picks WHERE date=? AND source IS NOT ?",
            (day, SOURCE)).fetchone()[0]
        if live:
            return {"day": day, "written": 0,
                    "refused": f"picks holds {live} non reconstructed row(s) for "
                               f"{day}; the record is not graded here"}
        if dry_run:
            return {"day": day, "written": 0, "dry_run": len(rows)}
        for record in rows:
            store.upsert(connection, "research_outcomes",
                         ["date", "ticker", "rule_version"], record)
        connection.commit()
    return {"day": day, "written": len(rows)}


def report(result: dict[str, Any]) -> None:
    day = result.get("day") or result.get("session_date")
    if result.get("skipped"):
        print(f"  {day}  skipped: {result['skipped']}")
        return
    if result.get("error"):
        print(f"  {day}  error: {result['error']}")
        return
    rows = result.get("rows") or []
    if rows:
        booked = sum(1 for r in rows if r.get("booked"))
        print(f"  {day}  {len(rows)} row(s), {booked} reached an entry")
        return
    print(f"  {day}  " + ", ".join(f"{k}={v}" for k, v in sorted(result.items())
                                   if k not in {"day", "session_date"}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grade reconstructed picks on their own session.")
    parser.add_argument("--fetch", action="store_true",
                        help="download regular session bars (network)")
    parser.add_argument("--evaluate", action="store_true",
                        help="grade from the cache and write research_outcomes")
    parser.add_argument("--all", action="store_true",
                        help="every day that replay_session has cached")
    parser.add_argument("--day", action="append", default=[],
                        help="one session date, repeatable")
    parser.add_argument("--force", action="store_true",
                        help="refetch a day that is already cached")
    parser.add_argument("--dry-run", action="store_true",
                        help="evaluate and print, write nothing")
    args = parser.parse_args(argv)

    if not (args.fetch or args.evaluate):
        parser.error("choose --fetch or --evaluate")
    days = list(args.day)
    if args.all:
        days = replay_session.cached_days() if args.fetch else cached_days()
    if not days:
        print("no days. Give --day or --all, and run replay_session first.")
        return 2

    if args.fetch:
        print(f"fetching regular session bars for {len(days)} day(s)")
        for day in days:
            report(fetch(day, force=args.force))
    if args.evaluate:
        print(f"evaluating {len(days)} day(s)")
        for day in days:
            result = evaluate(day)
            report(result)
            written = write_day(result, dry_run=args.dry_run)
            if written.get("refused"):
                print(f"    refused: {written['refused']}")
            elif written.get("dry_run"):
                print(f"    dry run: {written['dry_run']} row(s) would be written")
            elif written.get("written"):
                print(f"    wrote {written['written']} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
