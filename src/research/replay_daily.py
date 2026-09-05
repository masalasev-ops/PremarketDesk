"""What a name the desk never traded did on a session, from its daily bar.

WHAT THIS CLOSES, and why it is not research_outcomes. That table is paper
trade shaped: it is keyed on a rule_version and it carries an entry, a stop,
a fill and a booked flag, because every row in it is a name the reconstructed
screen priced. Two of the Precedent screen's sections ask about names that were
never priced at all:

  what the desk missed          a name that gapped and was never subscribed has
                                no premarket tape, so no pm_high, so no entry
                                and no stop. simulate cannot be run on it under
                                any rule: there is no level to reach.

  how these events resolved     a company that reported overnight is an event
                                the calendar names, and most of the names it
                                lists were never in the pool either.

So the honest outcome for both is the DAILY BAR, which this project already
pays for, and it is a different measurement from a simulated trade: open to
close and open to high, with no entry, no stop and no rule version. Putting
such a row in research_outcomes would join precedent._select's own denominator,
whose only exclusion is skip_reason, and quietly change what every count on the
shipped screen means. Hence a table of its own.

WHAT IT COSTS: nothing. Every byte is already on disk. data/backtest/eod/<day>
holds one daily bar per universe name, data/backtest/sessions/<day>/outcome
holds the gappers the session produced, and inputs holds discover's own earnings
tiers. No vendor is called and no quota is spent, at write time or render time.

WHAT IT CANNOT SAY, named here rather than left as a null column:

  There is no premarket anything. A name outside the pool was never listened
  to, so RVOL, the premarket high and the gap measured at the scan clock do not
  exist for it. gap_at_open_pct is measured at the OPEN, against the prior
  close, which is a different quantity from the gap the morning screens on.

  The universe is today's, so a name delisted during the replayed year is
  absent from every session it actually traded in. Every count drawn from this
  reads high for that reason and the screen says so.

Run:

    set PYTHONPATH=%CD%\\src
    .venv\\Scripts\\python.exe -m research.replay_daily --evaluate --all
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from core import criteria, ettime, lookalike, store
from research import backtest_pool
from selection import discover

_CRIT = criteria.load()

# Why a row carries no outcome, in words, never as a zero.
NO_BAR = "the daily bar cache holds no bar for this name on this date"

SURVIVORSHIP = ("the replayed universe is today's, so a name delisted during "
                "the year is absent from sessions it really traded in and "
                "every count here reads high")


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _eod(day: str) -> dict[str, Any]:
    path = backtest_pool.CACHE_DIR / "eod" / f"{day}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def subscribed_for(day: str) -> tuple[set[str], str | None]:
    """The names the replayed pool subscribed, or why they cannot be named.

    Read from the reconstructed picks rows rather than rebuilt, because those
    ARE the subscription list replay_session produced and rebuilding it here
    would be a second definition of the same thing. A day the replay has not
    reached yet returns an empty set and a reason, and every name on it is then
    recorded with subscribed NULL rather than 0: not subscribed and not yet
    replayed are different facts.
    """
    with store.session() as connection:
        store.init(connection)
        rows = [r[0] for r in connection.execute(
            "SELECT ticker FROM picks WHERE date=? AND source=?",
            (day, backtest_pool.SOURCE if hasattr(backtest_pool, "SOURCE")
             else "reconstructed"))]
    if not rows:
        return set(), ("the replay has not screened this session, so whether a "
                       "name was subscribed is unknown rather than false")
    return set(rows), None


def evaluate(day: str) -> dict[str, Any]:
    """Grade one session's gappers and overnight reporters. Writes nothing."""
    try:
        inputs, outcome = backtest_pool.load_session(day)
    except (OSError, ValueError) as exc:
        return {"day": day, "rows": [], "skipped": f"no session cache ({exc})"}

    bars = _eod(day)
    if not bars:
        return {"day": day, "rows": [],
                "skipped": "no daily bar cache for this date"}

    subscribed, unknown_why = subscribed_for(day)
    block = inputs.get("earnings") or {}
    status = str(block.get("status") or "").strip().lower()
    # The same vocabulary check replay_outcomes carries, and for the same
    # reason: a calendar that was never read must not be recorded as a session
    # on which nobody reported.
    reporters = (dict(block.get("names") or {})
                 if status in (discover.FETCHED, discover.FETCHED_EMPTY) else None)

    gappers = outcome.get("gappers") or {}
    wanted: dict[str, dict[str, Any]] = {}
    for symbol, row in gappers.items():
        wanted[symbol] = {"gapper": row, "report": None}
    for symbol, row in (reporters or {}).items():
        wanted.setdefault(symbol, {"gapper": None, "report": None})
        wanted[symbol]["report"] = row

    stamp = ettime.stamp(ettime.now_et())
    out: list[dict[str, Any]] = []
    for symbol, found in sorted(wanted.items()):
        bar = bars.get(symbol) or {}
        opened = _as_float(bar.get("o"))
        high = _as_float(bar.get("h"))
        low = _as_float(bar.get("l"))
        close = _as_float(bar.get("c"))
        gapper = found["gapper"] or {}
        report = found["report"] or {}
        prior_close = _as_float(gapper.get("prior_close"))
        gap = _as_float(gapper.get("gap_at_open_pct"))

        record: dict[str, Any] = {
            "date": day, "ticker": symbol,
            # NULL and not 0 when the replay has not screened this session.
            "subscribed": (None if unknown_why is not None
                           else (1 if symbol in subscribed else 0)),
            "gapped": 1 if found["gapper"] else 0,
            "gap_at_open_pct": gap,
            "gap_band": lookalike.gap_band(gap),
            "open_price": opened, "high_price": high, "low_price": low,
            "close_price": close, "prior_close": prior_close,
            "volume": _as_float(gapper.get("volume") or bar.get("v")),
            "open_to_close_pct": None, "open_to_high_pct": None,
            "open_to_low_pct": None,
            "earnings_tier_key": report.get("tier_key"),
            "earnings_timing": report.get("timing"),
            "earnings_estimate": _as_float(report.get("estimate")),
            "earnings_actual": _as_float(report.get("actual")),
            "skip_reason": None,
            "note": unknown_why,
            "computed_at": stamp,
        }
        if opened is None or not opened:
            record["skip_reason"] = NO_BAR
        else:
            record["open_to_close_pct"] = (
                None if close is None else round((close - opened) / opened * 100, 4))
            record["open_to_high_pct"] = (
                None if high is None else round((high - opened) / opened * 100, 4))
            record["open_to_low_pct"] = (
                None if low is None else round((low - opened) / opened * 100, 4))
        out.append(record)
    return {"day": day, "rows": out, "gappers": len(gappers),
            "reporters": None if reporters is None else len(reporters)}


def write_day(result: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    """Write one day's rows, or refuse and say why.

    THE SAME REFUSAL research_outcomes CARRIES. A date holding a live picks row
    is a date the desk really ran, and a reconstruction of it must not sit
    where a later reader could pool the two.
    """
    day = result["day"]
    rows = result.get("rows") or []
    if not rows:
        return {"day": day, "written": 0, "refused": result.get("skipped")}
    with store.session() as connection:
        store.init(connection)
        live = connection.execute(
            "SELECT COUNT(*) FROM picks WHERE date=? AND source IS NOT ?",
            (day, "reconstructed")).fetchone()[0]
        if live:
            return {"day": day, "written": 0,
                    "refused": f"picks holds {live} non reconstructed row(s) "
                               f"for {day}; the record is not graded here"}
        if dry_run:
            return {"day": day, "written": 0, "dry_run": len(rows)}
        for record in rows:
            store.upsert(connection, "research_daily", ["date", "ticker"], record)
        connection.commit()
    return {"day": day, "written": len(rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grade the gappers and overnight reporters of a replayed "
                    "session from their daily bars.")
    parser.add_argument("--evaluate", action="store_true",
                        help="grade from the caches and write research_daily")
    parser.add_argument("--all", action="store_true",
                        help="every session the pool has cached")
    parser.add_argument("--day", action="append", default=[],
                        help="one session date, repeatable")
    parser.add_argument("--dry-run", action="store_true",
                        help="evaluate and print, write nothing")
    args = parser.parse_args(argv)

    if not args.evaluate:
        parser.error("choose --evaluate; this module makes no network call")
    days = list(args.day)
    if args.all:
        days = backtest_pool.cached_sessions()
    if not days:
        print("no days. Give --day or --all, and fetch the pool first.")
        return 2

    written = skipped = 0
    for day in days:
        result = evaluate(day)
        if result.get("skipped"):
            skipped += 1
            print(f"  {day}  skipped: {result['skipped']}")
            continue
        outcome = write_day(result, dry_run=args.dry_run)
        if outcome.get("refused"):
            skipped += 1
            print(f"  {day}  refused: {outcome['refused']}")
            continue
        count = outcome.get("dry_run") or outcome.get("written") or 0
        written += count
        print(f"  {day}  {count} row(s), {result['gappers']} gapper(s), "
              f"{result['reporters']} overnight reporter(s)")
    print(f"replay_daily: {written} row(s) over {len(days) - skipped} session(s), "
          f"{skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
