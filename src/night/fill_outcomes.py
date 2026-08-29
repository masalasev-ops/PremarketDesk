"""Nightly outcome fill: what actually happened after each pick.

CRITERIA.md opens by saying its thresholds are unvalidated seed values, and
this module is the other half of that sentence. Every pick eventually gets
next session and fifth session outcomes written next to the morning's
references, and once a few hundred rows exist the thresholds can be moved
because the data said so.

Trading sessions are counted on the session calendar symbol's end of day
history, never weekday arithmetic. A Monday holiday makes Friday plus one
land on Tuesday, and weekday math would quietly compare against a day the
market never traded.

Idempotent by construction: a row is only written when it still has an
outcome column null that the calendar says should be fillable, and a second
run straight after the first finds nothing left to do and changes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status
from core import store

_CRIT = criteria.load()

_OUTCOME_COLUMNS = (
    ("next_day_open", "REAL"),
    ("next_day_high", "REAL"),
    ("next_day_low", "REAL"),
    ("next_day_close", "REAL"),
    ("day5_close", "REAL"),
    # Why the fifth session was refused, on the rows where it was. A null
    # day5_close is also how a fill that is simply not due yet looks, and until
    # 2026-08-20 the units guard below had no way to say which of the two a
    # given null was. See the long leg in fill().
    ("day5_refused_reason", "TEXT"),
    ("pm_high_broke_next_day", "INTEGER"),
    ("mfe_pct", "REAL"),
    ("mae_pct", "REAL"),
    # The same two excursions against the reference levels night/true_volume.py
    # measured off the full SIP tape, rather than the ones the collector
    # sampled. See fill_true_excursions below and CRITERIA [Outcomes]. Written
    # beside, never over: the gap between the pairs is what says how much the
    # sampled record has been flattering its upside and overstating its
    # downside, and a corrected column with the original thrown away could not
    # say it.
    ("mfe_pct_true", "REAL"),
    ("mae_pct_true", "REAL"),
    ("outcomes_filled_at", "TEXT"),
)


def _session_calendar(api: eodhd.EodhdClient, back_days: int = 40) -> list[str]:
    """Real trading sessions, oldest first, from the calendar symbol's EOD bars."""
    symbol = _CRIT.text("universe", "session_calendar_symbol")
    today = ettime.today_et()
    bars, error = api.eod(symbol, start=today - dt.timedelta(days=back_days), end=today)
    if error or not bars:
        raise RuntimeError(f"session calendar unavailable from {symbol}: {error or 'no rows'}")
    return [str(b["date"]) for b in bars if b.get("date")]


class CalendarTooShort(LookupError):
    """The session calendar does not reach back far enough to answer for a pick."""


def _sessions_after(calendar: list[str], date: str, count: int) -> list[str]:
    """The next `count` sessions strictly after `date`, or fewer if not elapsed.

    Raises when `date` sits BEFORE the calendar's own first session, because
    then every entry satisfies `d > date` and the first one returned is the
    oldest session in the window rather than the session after the pick. That
    is not a smaller answer, it is a wrong one, and it was silent: the caller
    would fetch bars from the pick's date to a session weeks later, find the
    window's first day present in the response, and write it into
    next_day_open/high/low/close, pm_high_broke_next_day, mfe_pct and mae_pct
    as though it were the day after the pick.

    The path there is ordinary. A name halted the session after a pick leaves
    that row null, so it is re-selected every night and correctly reported as
    unavailable. Forty-one days later the calendar no longer reaches the pick,
    the guard that was refusing it stops applying, and the row is filled with
    excursions measured against a tape six weeks removed from the levels they
    are computed from. That table is the one CRITERIA says its thresholds will
    eventually be recalibrated against.
    """
    if not calendar:
        raise CalendarTooShort("the session calendar is empty")
    if date < calendar[0]:
        raise CalendarTooShort(
            f"the pick is dated {date} and the session calendar starts at "
            f"{calendar[0]}, so it cannot say which session follows it"
        )
    later = [d for d in calendar if d > date]
    return later[:count]


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _adjustment_factor(bar: dict[str, Any] | None) -> float | None:
    """close divided by adjusted_close for one end of day bar, or None.

    The vendor retro-adjusts: a corporate action rewrites the adjusted_close of
    every bar dated BEFORE its ex date and leaves the bars from the ex date
    onward alone. So this ratio is flat between actions and steps at each one,
    which is what makes a step between two dates evidence that an action fell
    between them.
    """
    close = _as_float((bar or {}).get("close"))
    adjusted = _as_float((bar or {}).get("adjusted_close"))
    if close is None or not adjusted:
        return None
    return close / adjusted


def _price_units_broke(
    pick_bar: dict[str, Any] | None,
    later_bar: dict[str, Any] | None,
    max_drift_pct: float,
    later_label: str,
) -> str | None:
    """Why the pick date and a later session are not in the same units, or None.

    Returns None when later_bar is missing, because the caller already refuses
    that case with a better sentence, and None when the two sides agree.

    later_label names the session on the far side of the comparison, and it is
    a parameter because this test now runs for whichever outcome leg is being
    written rather than only for D+1. It was written for the short leg alone
    and its sentences said "the next session" as a constant, which would have
    named the wrong bar the moment it was pointed at D+5.
    """
    if later_bar is None:
        return None
    before = _adjustment_factor(pick_bar)
    after = _adjustment_factor(later_bar)
    if before is None:
        return ("the end of day bar for the pick date carries no readable close "
                "and adjusted_close pair, so there is nothing to show that "
                f"{later_label} is priced in the same units as the morning's "
                "premarket levels")
    if after is None:
        return (f"the bar for {later_label} carries no readable close and "
                "adjusted_close pair, so there is nothing to show that it is "
                "priced in the same units as the morning's premarket levels")
    drift = abs(after / before - 1.0) * 100.0
    if drift <= max_drift_pct:
        return None
    return (f"the vendor's split adjustment factor moved {drift:.4f} percent "
            f"between the pick date and {later_label}, past the "
            f"{max_drift_pct:g} percent in {config.CRITERIA_PATH.name} [outcomes] "
            "max_adjustment_drift_pct, so a corporate action has its ex date in "
            f"between and the bar for {later_label} is not in the same price "
            "units as the entry_ref, stop_ref and pm_high recorded beside it")


def fill(day_limit: str | None = None) -> int:
    short_n = _CRIT.integer("outcomes", "horizon_sessions_short")
    long_n = _CRIT.integer("outcomes", "horizon_sessions_long")
    max_drift_pct = _CRIT.number("outcomes", "max_adjustment_drift_pct")
    api = eodhd.client()

    # Read, then fetch, then write. Three phases on purpose: a transaction must
    # never span a network call, because one held open across an end of day
    # request per pick locks the database for the length of the job and every
    # other writer fails with "database is locked" for reasons that have
    # nothing to do with it. See conftest.py for the incidents that taught this.
    with store.session() as connection:
        store.init(connection)
        added = store.ensure_columns(connection, "picks", _OUTCOME_COLUMNS)
        # source = 'live' only: outcomes are the record the thresholds will
        # one day be calibrated against, and test rows have no business in it.
        # A recorded day5 refusal takes the row out of the long leg's half of
        # this condition, because what that refusal names is a corporate
        # action's ex date and an ex date does not un-happen. Before the reason
        # column existed the only way to refuse was to leave day5_close null,
        # which is also what this query selects on, so a refused row came back
        # every night for as long as the session calendar still reached it and
        # spent one end of day call each time to be refused again. An operator
        # who believes a refusal was wrong clears day5_refused_reason and the
        # row is picked up on the next run.
        candidates = [dict(row) for row in connection.execute(
            "SELECT * FROM picks WHERE "
            "((next_day_close IS NULL AND next_day_refused_reason IS NULL) "
            "OR (day5_close IS NULL AND day5_refused_reason IS NULL)) "
            "AND source='live' ORDER BY date, ticker"
        ).fetchall()]

    if added:
        print(f"outcomes: widened picks with {', '.join(added)}")
    if not candidates:
        print("outcomes: every live pick already has its outcomes "
              "(test rows are never filled), nothing to do")
        job_status.produced("picks filled", 0)
        return 0

    calendar = _session_calendar(api, back_days=40)
    filled = skipped = unavailable = refused = 0
    now_stamp = ettime.stamp(ettime.now_et())
    writes: list[tuple[dict[str, Any], str, str]] = []

    if True:
        for pick in candidates:
            date, ticker = pick["date"], pick["ticker"]
            if day_limit and date > day_limit:
                skipped += 1
                continue
            try:
                next_sessions = _sessions_after(calendar, date, long_n)
            except CalendarTooShort as exc:
                # Loud and null, never guessed. A row this old with outcomes
                # still missing is a real question (halted, delisted, or the
                # vendor never published), and answering it with the wrong
                # sessions would put a fabricated excursion into the record.
                print(f"outcomes: {ticker} {date} left alone: {exc}. Widen "
                      "back_days if this row should still be fillable.")
                unavailable += 1
                continue
            wants_short = pick["next_day_close"] is None and len(next_sessions) >= short_n
            wants_long = (pick["day5_close"] is None
                          and pick["day5_refused_reason"] is None
                          and len(next_sessions) >= long_n)
            if not wants_short and not wants_long:
                skipped += 1
                continue

            window_end = ettime.parse_date(next_sessions[-1])
            bars, error = api.eod(ticker, start=ettime.parse_date(date), end=window_end)
            if error or not bars:
                print(f"outcomes: {ticker} {date} left alone: {error or 'no end of day rows'}")
                unavailable += 1
                continue
            by_date = {str(b.get("date")): b for b in bars}

            # Read once here rather than inside a leg, because both legs are
            # measured against it and each checks its own session's bar.
            pick_bar = by_date.get(date)
            updates: dict[str, Any] = {}
            if wants_short:
                next_bar = by_date.get(next_sessions[short_n - 1])

                # A corporate action with its ex date on the session after the
                # pick leaves the two sides of every excursion below in
                # different price units. mfe_pct, mae_pct and
                # pm_high_broke_next_day subtract entry_ref, stop_ref and
                # pm_high, which are the collector's RAW live premarket levels
                # from the pick date, from the high and low of the D+1 bar, and
                # retro-adjustment rewrites only bars dated before the ex date,
                # so that bar is post event under either vendor convention. A
                # 4-for-1 forward split therefore writes mfe_pct and mae_pct
                # near -75 percent and pm_high_broke_next_day 0, and a 1-for-10
                # reverse split lands near +900 percent, unflagged and
                # indistinguishable from a real excursion, into the table
                # CRITERIA.md and BUILD_PLAN.md both designate as the record the
                # seed thresholds will be recalibrated against. The screen's
                # price floor is only "> 3", so a reverse split candidate is not
                # an exotic case.
                #
                # Refused rather than rescaled, following the CalendarTooShort
                # branch above: this module's stated position is that it will
                # leave a row null rather than "put a fabricated excursion into
                # the record", and a rescaled excursion is a computed number in
                # a table meant to hold measured ones. The refusal takes the
                # whole row, day5_close included, because an ex date sitting
                # between the pick and D+1 also sits between the pick and D+5.
                units = _price_units_broke(pick_bar, next_bar, max_drift_pct,
                                           "the next session")
                if units is not None:
                    # RECORDED, not just skipped. The long leg has carried
                    # day5_refused_reason since the same argument was made for
                    # it; this branch did a bare continue, so the row kept a
                    # null next_day_close with nothing beside it. The candidate
                    # query selects on exactly that null, so the row came back
                    # every night and spent one end of day call each time to be
                    # refused again, forever, and the null was indistinguishable
                    # from a leg that is merely not due yet. An operator who
                    # believes a refusal was wrong clears the column and the row
                    # is picked up on the next run.
                    #
                    # Both legs, because the comment above already says an ex
                    # date between the pick and D+1 also sits between the pick
                    # and D+5, and the continue below skips the long leg too.
                    updates["next_day_refused_reason"] = units
                    updates["day5_refused_reason"] = units
                    print(f"outcomes: {ticker} {date} left alone: {units}")
                    unavailable += 1
                    writes.append((updates, date, ticker))
                    continue

                if next_bar is None:
                    print(f"outcomes: {ticker} {date} has no bar on {next_sessions[short_n - 1]}, "
                          "possibly halted or delisted, left null")
                    unavailable += 1
                elif _as_float(next_bar.get("close")) is None:
                    # The bar exists and its close does not parse. Writing the
                    # other three columns and a null close looks like progress
                    # and is not: the candidate query re-selects on
                    # `next_day_close IS NULL`, so the row came back every
                    # night, was re-fetched at one end of day call each time,
                    # was recounted in `filled`, and had outcomes_filled_at
                    # moved forward, which stopped that column recording when
                    # the outcome was obtained. The docstring's claim that a
                    # second run straight after the first changes nothing was
                    # false for exactly these rows. Treated as unavailable, the
                    # same as a missing bar, so the row stays honestly null.
                    print(f"outcomes: {ticker} {date} has a bar on "
                          f"{next_sessions[short_n - 1]} with no readable close, "
                          "left null rather than half filled")
                    unavailable += 1
                else:
                    next_open = _as_float(next_bar.get("open"))
                    next_high = _as_float(next_bar.get("high"))
                    next_low = _as_float(next_bar.get("low"))
                    updates["next_day_open"] = next_open
                    updates["next_day_high"] = next_high
                    updates["next_day_low"] = next_low
                    updates["next_day_close"] = _as_float(next_bar.get("close"))

                    pm_high = pick["pm_high"]
                    if pm_high is not None and next_high is not None:
                        updates["pm_high_broke_next_day"] = int(next_high > pm_high)

                    entry_ref, stop_ref = pick["entry_ref"], pick["stop_ref"]
                    if entry_ref and next_high is not None:
                        updates["mfe_pct"] = round((next_high - entry_ref) / entry_ref * 100.0, 4)
                    if stop_ref and next_low is not None:
                        updates["mae_pct"] = round((next_low - stop_ref) / stop_ref * 100.0, 4)

            if wants_long:
                day5_bar = by_date.get(next_sessions[long_n - 1])

                # The same units test as the short leg, run again against THIS
                # leg's bar. Until 2026-08-20 it sat inside the "if wants_short"
                # block above, so it guarded D+1 and nothing else, and on the
                # ordinary cadence that block does not run at all on the night
                # the long leg is written: the candidate query re-selects on
                # next_day_close or day5_close being null, so the short leg
                # fills on the night of D+1 and the long leg five nights later,
                # in a run where wants_short is already False. An ex date
                # anywhere from D+2 to D+5 therefore wrote a post action close
                # into the same row as the pre action entry_ref, stop_ref and
                # pm_high, silently and permanently, which is exactly the error
                # the guard was added to refuse one session earlier.
                units = _price_units_broke(pick_bar, day5_bar, max_drift_pct,
                                           "the fifth session")
                if units is not None:
                    # Written down rather than left as a bare null. A refused
                    # day5_close is otherwise indistinguishable from one that is
                    # merely not due yet, and this one is never coming back with
                    # a number, so the row says which of the two it is.
                    updates["day5_refused_reason"] = units
                    print(f"outcomes: {ticker} {date} day5_close refused: {units}")
                    refused += 1
                elif day5_bar is not None and _as_float(day5_bar.get("close")) is not None:
                    # Only when it parses, for the reason above: day5_close is the
                    # other half of the candidate query, so writing a null into it
                    # re-arms the row rather than completing it.
                    updates["day5_close"] = _as_float(day5_bar.get("close"))

            if not updates:
                skipped += 1
                continue
            # outcomes_filled_at records when an OUTCOME was obtained, so a row
            # whose only new column is a refusal reason must not move it. On the
            # ordinary cadence such a row already carries the stamp from the
            # night its short leg filled, and overwriting that with tonight's
            # would make the column say the measurement was taken five sessions
            # after it actually was.
            measured = [column for column in updates
                        if column not in ("day5_refused_reason",
                                          "next_day_refused_reason")]
            if measured:
                updates["outcomes_filled_at"] = now_stamp
                filled += 1
            writes.append((updates, date, ticker))

    with store.session() as connection:
        for updates, date, ticker in writes:
            assignments = ", ".join(f"{column}=?" for column in updates)
            connection.execute(
                f"UPDATE picks SET {assignments} WHERE date=? AND ticker=?",
                [*updates.values(), date, ticker],
            )
        connection.commit()

        # Rows are not observations. Candidates from one morning share the
        # same tape, so the sample unit for any threshold analysis is the
        # session, and both counts are reported so nobody mistakes twelve
        # correlated rows for twelve data points.
        total_rows, total_sessions = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT date) FROM picks "
            "WHERE next_day_close IS NOT NULL AND source='live'"
        ).fetchone()
        job_status.produced("picks filled", filled)
        print(f"outcomes: {filled} picks filled, {skipped} not yet due, "
              f"{unavailable} had no data")
        if refused:
            print(f"outcomes: {refused} pick(s) had a fifth session the vendor "
                  "reprices across, recorded in day5_refused_reason rather than "
                  "left null, and they are not re-selected")
        print(f"outcomes: the table now holds {total_rows} live outcome rows across "
              f"{total_sessions} sessions; the sample unit is the session")
    return 0


def fill_true_excursions() -> int:
    """mfe_pct_true and mae_pct_true. Arithmetic only, no vendor call.

    THE SAME TWO SUBTRACTIONS the short leg above performs, against the
    reference levels night/true_volume.py measured off Alpaca's full SIP tape
    instead of the ones the collector sampled. entry_ref is the extreme of a
    socket sample that carried a median 0.0296 of the tape, so it sits below
    the true premarket high, and mfe_pct measured up from it is overstated.
    stop_ref sits above the true premarket low, and mae_pct measured down from
    it is overstated too. The two point opposite ways as a judgement, which is
    exactly why both are computed rather than one being argued about.

    A SEPARATE PASS, not a branch of fill(), for two reasons. It needs no
    network call at all, so it must not sit behind a candidate query that
    exists to ration end of day requests. And that query selects on
    next_day_close being null, so a row whose short leg filled before these
    columns existed is never re-selected and would never have been measured;
    every such row is in the table today.

    Idempotent: a row is written only where an output is still null and both
    its inputs are present, so a second run straight after the first finds
    nothing and changes nothing.

    NO FALLBACK TO THE SAMPLED PAIR. A row true_volume could not reach keeps
    null excursions, and refs_true_reason on the same row says why. Substituting
    entry_ref there would put a column named _true in the table holding the
    number it exists to be compared against, which is the defect this project
    has now caught under four other names.
    """
    with store.session() as connection:
        store.init(connection)
        store.ensure_columns(connection, "picks", _OUTCOME_COLUMNS)
        # next_day_refused_reason IS NULL keeps the corporate action refusal.
        # A refused row has null next_day_high anyway so the arithmetic could
        # not run, but the condition is stated rather than relied on: the
        # refusal is a rule about price units and it applies to whichever
        # reference the excursion is measured from.
        rows = [dict(row) for row in connection.execute(
            "SELECT date, ticker, next_day_high, next_day_low, entry_ref_true, "
            "stop_ref_true FROM picks WHERE source='live' "
            "AND next_day_refused_reason IS NULL AND ("
            "  (mfe_pct_true IS NULL AND next_day_high IS NOT NULL "
            "   AND entry_ref_true IS NOT NULL)"
            "  OR (mae_pct_true IS NULL AND next_day_low IS NOT NULL "
            "      AND stop_ref_true IS NOT NULL))"
            " ORDER BY date, ticker")]

        written = 0
        for row in rows:
            updates: dict[str, Any] = {}
            entry, stop = row["entry_ref_true"], row["stop_ref_true"]
            if entry and row["next_day_high"] is not None:
                updates["mfe_pct_true"] = round(
                    (row["next_day_high"] - entry) / entry * 100.0, 4)
            if stop and row["next_day_low"] is not None:
                updates["mae_pct_true"] = round(
                    (row["next_day_low"] - stop) / stop * 100.0, 4)
            if not updates:
                continue
            assignments = ", ".join(f"{column}=?" for column in updates)
            connection.execute(
                f"UPDATE picks SET {assignments} WHERE date=? AND ticker=?",
                [*updates.values(), row["date"], row["ticker"]])
            written += 1
        connection.commit()
    print(f"outcomes: {written} row(s) given a true excursion")
    excursion_gap_report()
    return written


def _median(values: list[float]) -> float:
    return sorted(values)[len(values) // 2]


def excursion_gap_report() -> None:
    """What the sampled references cost the excursion record, both directions.

    Over the WHOLE table, and both denominators printed, because twelve names
    from one morning share a tape and are one observation. This is a
    measurement of a bias, not a result, and it names no threshold.
    """
    with store.session() as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT date, mfe_pct, mfe_pct_true, mae_pct, mae_pct_true "
            "FROM picks WHERE source='live' AND ("
            "(mfe_pct IS NOT NULL AND mfe_pct_true IS NOT NULL) OR "
            "(mae_pct IS NOT NULL AND mae_pct_true IS NOT NULL))")]
    if not rows:
        print("outcomes: no live row carries both a sampled and a true "
              "excursion yet, so the gap between them is not computable")
        return
    sessions = len({row["date"] for row in rows})
    favourable = [(r["mfe_pct"], r["mfe_pct_true"]) for r in rows
                  if r["mfe_pct"] is not None and r["mfe_pct_true"] is not None]
    adverse = [(r["mae_pct"], r["mae_pct_true"]) for r in rows
               if r["mae_pct"] is not None and r["mae_pct_true"] is not None]
    print(f"outcomes: THE EXCURSION GAP, across {sessions} session(s). The "
          "sample unit is the session.")
    for label, pairs in (("favourable", favourable), ("adverse", adverse)):
        if not pairs:
            print(f"  {label:<11} no row carries both halves")
            continue
        sampled = _median([p[0] for p in pairs])
        measured = _median([p[1] for p in pairs])
        drift = _median([p[1] - p[0] for p in pairs])
        print(f"  {label:<11} n={len(pairs):<4} median sampled {sampled:+.4f}%, "
              f"median measured {measured:+.4f}%, median row by row "
              f"difference {drift:+.4f} points")
    print("  Measured is the honest number. Sampled is what the record has "
          "carried, and it is kept because the difference between them is "
          "itself the measurement of the feed.")


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill pick outcomes from end of day history.")
    parser.add_argument("--before", metavar="YYYY-MM-DD", default=None,
                        help="Only consider picks dated on or before this date.")
    args = parser.parse_args(argv)
    code = fill(args.before)
    # After the end of day fill, so tonight's newly written next_day_high and
    # next_day_low are in it. It spends no vendor call, so it runs even on a
    # night fill() had nothing to do: the rows it reaches are mostly ones whose
    # short leg filled long before these columns existed.
    #
    # Deliberately NOT calling job_status.produced. The last call before exit
    # is the one recorded, and the number the watchdog reads for this step is
    # picks filled, not a backfill count that will be zero every night once it
    # has caught up.
    fill_true_excursions()
    return code


if __name__ == "__main__":
    sys.exit(job_status.run("outcomes", main, ok_codes=OK_CODES))
