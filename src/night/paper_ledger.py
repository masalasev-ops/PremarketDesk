"""The paper ledger: what ONE written rule would have done with each pick.

CRITERIA.md [Paper] holds the rule and this module applies it. Nothing here
decides anything: entry, stop, exit, size and every refusal are read from that
section, and a rule that lives in code is a rule nobody can argue with.

WHY A LEDGER AND NOT MORE EXCURSIONS. mfe_pct is a BOUND, not a return. It says
how far the tape ran past a reference at its best moment, which a real rule
captures only with perfect exit timing and usually does not capture at all.
Reading it as a result is the most common way to be wrong with this table, and
CRITERIA has said so since the column existed: "not a simulation of any trade".
This module is the simulation, so mfe_pct can go back to being a diagnostic and
the two are reported on the same line.

THE SESSION IT TRADES IS THE PICK'S OWN, and that is NOT the session
night/fill_outcomes.py measures. The scan runs 08:45 on the pick date and the
report is about the open ninety minutes later, so the rule trades that open.
[Outcomes] fills next_day_open through mae_pct_true from the session AFTER
that one, and the session the report was actually about appears in none of
them. AXTI on 2026-08-27 is the plainest case: entry_ref 70.94, its own session
opened 70.30 and reached 70.85, a miss by 0.13 percent, while next_day_high is
65.4155 from 2026-08-28 and mfe_pct reads -7.79. Nothing in [Outcomes] is
changed by this module; it fetches its own bars for its own session and the
two horizons are kept apart on purpose.

EVERY RULE VERSION IS BOOKED, SIDE BY SIDE, over the same trades. CRITERIA
[Paper]'s sizing map is the registry: each version named there gets its own row
per pick, keyed on (date, ticker, rule_version), so a new version lands BESIDE
what the old one produced and never over it. A ledger that overwrote itself on
every rule change could not answer whether the change helped, which is most of
what a ledger is for.

v2 differs from v1 in exactly one thing, the position size, and the versions
are otherwise byte for byte identical. That is the design: two changes at once
would leave no way to say which of them moved the number.

IT BOOKS AGAINST THE MEASURED REFERENCES AND THE ALPACA TAPE. entry_ref and
stop_ref are the collector's raw live levels, which are the extremes of a
socket sample, and a ledger built on a level that was never available books a
P&L that is wrong from its first row. entry_ref_true and stop_ref_true are the
same references off the full SIP tape, and fill_plausible says whether that
level was a price anyone could have transacted at. A row that is not
'plausible' is SKIPPED WITH ITS REASON WRITTEN DOWN, never silently dropped.

    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger
    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger --date 2026-08-27
    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger --all
    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys
from typing import Any

from core import criteria
from core import ettime
from core import store
from ops import job_status

_CRIT = criteria.load()

# Every column the ledger writes. store.ensure_table builds it from this, so
# the schema and the writer cannot drift apart.
LEDGER_COLUMNS = (
    ("date", "TEXT NOT NULL"),
    ("ticker", "TEXT NOT NULL"),
    # Rows are keyed on the rule version, so changing the rule books BESIDE
    # what the old one produced rather than over it. A ledger that overwrote
    # itself on every rule change could not answer whether the change helped.
    ("rule_version", "TEXT NOT NULL"),
    ("session", "TEXT"),
    # The screen's verdict, carried as a GROUPING column and never as a filter.
    # Booking only what the screen admitted makes "did the screen separate
    # outcomes" unaskable, and that is the question the ledger exists to feed.
    ("day_eligible", "INTEGER"),
    ("swing_eligible", "INTEGER"),
    ("conviction", "TEXT"),
    ("score", "REAL"),
    # 1 when a trade was taken. 0 covers both a skipped row and one whose
    # trigger never fired, and skip_reason and exit_reason say which.
    ("booked", "INTEGER"),
    ("skip_reason", "TEXT"),
    ("entry_ref_used", "REAL"),
    ("stop_ref_used", "REAL"),
    ("entry_at", "TEXT"),
    ("entry_price", "REAL"),
    ("exit_at", "TEXT"),
    ("exit_price", "REAL"),
    ("exit_reason", "TEXT"),
    ("shares", "INTEGER"),
    ("notional", "REAL"),
    # What this trade could actually LOSE, in dollars: the stop distance times
    # the shares. Under v1 it is whatever the stop distance happens to be and
    # ran 253 to 2,141 over the first sixteen trades; under v2 it is the same
    # on every trade by construction. Recorded rather than derived so a reader
    # can see the two sizings side by side without recomputing either.
    ("risk_notional_taken", "REAL"),
    ("sizing_mode", "TEXT"),
    # NULL, never zero, on a row that took no trade. A zero P&L is a flat
    # trade and a null one is no trade, and a median that mixes them is the
    # defect this project has now found under five other names.
    ("pnl", "REAL"),
    ("pnl_pct", "REAL"),
    ("max_drawdown_pct", "REAL"),
    # WHEN things happened, which is the only part of this table that is any
    # use before the record is large enough to judge. minutes_to_trigger is
    # from the open; minutes_to_peak is from the ENTRY, so the two answer
    # "should I still be watching this at 10:00" and "is this one done" and
    # neither answers the other.
    ("minutes_to_trigger", "INTEGER"),
    ("minutes_to_peak", "INTEGER"),
    ("mfe_pct_held", "REAL"),
    ("bars_held", "INTEGER"),
    ("booked_at", "TEXT"),
)

# The sizing modes CRITERIA [Paper]'s sizing map may name. A tuple rather than
# three literals scattered through the module, so a claim can assert the set is
# closed and a typo in the file cannot invent a fourth mode that reads as real.
SIZING_NOTIONAL = "notional"
SIZING_RISK = "risk"
SIZING_MODES = (SIZING_NOTIONAL, SIZING_RISK)


def rule_versions() -> dict[str, str]:
    """{version: sizing mode}, from CRITERIA [Paper]'s sizing map.

    THE SIZING MAP IS THE VERSION REGISTRY. There is deliberately no separate
    list of versions: a version with no sizing mode could not be booked, and a
    sizing mode for a version nobody lists would be dead configuration, so the
    two are one line and cannot disagree.
    """
    modes = _CRIT.pair_map("paper", "sizing")
    for version, mode in modes.items():
        if mode not in SIZING_MODES:
            raise criteria.CriteriaError(
                f"[Paper] sizing names {mode!r} for {version!r}, which is not "
                f"one of {sorted(SIZING_MODES)}")
    return modes


def position_size(mode: str, entry_price: float, stop_level: float,
                  ) -> tuple[int, str | None]:
    """(whole shares, why not). The one thing that differs between v1 and v2.

    notional  the same dollar POSITION on every trade. What each trade can lose
              is then whatever its own stop distance happens to be, which over
              v1's first sixteen trades ran from 253 dollars to 2,141: an eight
              fold spread across trades the rule treats as equals.

    risk      the same dollar RISK on every trade. The position is the risk
              budget over the stop distance, capped, so a wide stop buys a
              small position and a tight one buys a large position up to the
              cap. Without the cap this stops being a sizing rule and becomes a
              leverage rule: a two percent stop would buy 37,500 dollars.

    A size that works out below one whole share books NO TRADE and says so,
    rather than rounding up to one and inventing a position the budget does not
    cover.
    """
    if mode not in SIZING_MODES:
        raise criteria.CriteriaError(
            f"sizing mode {mode!r} is not one of {sorted(SIZING_MODES)}")
    # A STOP AT OR ABOVE THE ENTRY IS REFUSED IN EVERY MODE. This lived inside
    # the risk branch alone, where it was forced: that branch divides by the
    # stop distance. Notional sizing divides by nothing, so it sized the
    # position happily and handed it to simulate, whose very first bar then
    # reads low <= stop_level and exits AT THE STOP, a price at or above the
    # entry. The row books exit_reason "stop" carrying a NON NEGATIVE P&L: a
    # phantom win wearing the name of a loss, which is the one disguise that
    # would survive every summary this table feeds, because nothing sums
    # losses expecting them to be positive.
    #
    # A guard rather than a repair. No pick has ever carried such a pair, and
    # the smallest true gap on the 56 rows carrying both is 0.33. But the
    # night measures entry_ref_true and stop_ref_true INDEPENDENTLY off the
    # tape, and nothing between there and here checks that they are still in
    # the order the morning published them in.
    if entry_price - stop_level <= 0:
        return 0, (
            f"the stop {stop_level:g} is at or above the entry "
            f"{entry_price:g}, so the trade risks nothing and no sizing mode "
            "has an answer. Nothing is booked: a position sized here would "
            "exit at its stop on the first bar and book that exit as a gain")
    if mode == SIZING_NOTIONAL:
        notional = _CRIT.number("paper", "position_notional")
    else:
        risk = entry_price - stop_level
        budget = _CRIT.number("paper", "risk_notional")
        cap = _CRIT.number("paper", "max_position_notional")
        notional = min(budget * entry_price / risk, cap)
    shares = int(notional // entry_price)
    if shares < 1:
        return 0, (
            f"one share costs {entry_price:,.2f} and the {mode} sizing allows "
            f"{notional:,.0f}, so the rule cannot be applied at this size")
    return shares, None


EXIT_STOP = "stop"
EXIT_CLOSE = "session close"
EXIT_NEVER = "trigger never fired"
# The third exit_reason a booked=0 row can carry, and it is NOT a sizing
# refusal: the trade was sized, it entered, and the window ran out before a
# readable close. Named here so the three way split can tell it apart from
# the two position_size refusals rather than sweeping it in with them.
EXIT_OPEN_AT_END = ("the session's minutes end with the position still open, "
                    "so there is no exit price and the trade is not booked")


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def session_window(day: str) -> tuple[dt.datetime, dt.datetime]:
    """The regular session on the pick's OWN date, 09:30 to the close.

    The open comes from [Backfill] market_open because that is the same fact
    already written down once, and the close from [Paper] session_close. The
    rule trades regular hours only: the trigger level is a premarket high and
    premarket is precisely where item 2 measured the thin liquidity, so a rule
    that let itself fill there would book the fills fill_plausible exists to
    doubt.
    """
    date = ettime.parse_date(day)
    open_h, open_m = _CRIT.clock("backfill", "market_open")
    close_h, close_m = _CRIT.clock("paper", "session_close")
    return (dt.datetime(date.year, date.month, date.day, open_h, open_m,
                        tzinfo=ettime.ET),
            dt.datetime(date.year, date.month, date.day, close_h, close_m,
                        tzinfo=ettime.ET))


def simulate(bars: list[dict[str, Any]], entry_level: float, stop_level: float,
             sizing_mode: str = SIZING_NOTIONAL) -> dict[str, Any]:
    """Apply the rule to one session's minutes. Returns what it did and why.

    Reads the bars in ORDER, which is the whole reason this fetches one minute
    data instead of using the end of day bar already in picks. An OHLC bar
    cannot say whether its high came before its low, so it cannot say whether a
    stop was reached before a target, and every ledger built on one is
    answering a question the data does not contain.

    THE SAME MINUTE CASE IS BOOKED AS A LOSS. A minute whose high reaches the
    trigger and whose low reaches the stop carries no sequence inside it, so
    the order is unknowable. The losing reading is taken because the flattering
    one is a choice that would show up in every summary this table feeds.

    A trigger that never fires books NO TRADE and a NULL P&L. Zero would read
    as a flat trade, and those are different facts.
    """
    out: dict[str, Any] = {
        "booked": 0, "entry_at": None, "entry_price": None,
        "exit_at": None, "exit_price": None, "exit_reason": EXIT_NEVER,
        "shares": None, "notional": None, "pnl": None, "pnl_pct": None,
        "max_drawdown_pct": None, "bars_held": None,
    }
    out["minutes_to_trigger"] = None
    out["minutes_to_peak"] = None
    out["mfe_pct_held"] = None
    entry_price = None
    entry_index = None
    for index, bar in enumerate(bars):
        high, low = _as_float(bar.get("h")), _as_float(bar.get("l"))
        opened = _as_float(bar.get("o"))
        if high is None or low is None or opened is None:
            continue
        if high >= entry_level:
            # A session that gaps straight through the resting order fills at
            # the open, not at the level. That is the honest treatment and the
            # common case for a gap candidate, and the flattering alternative
            # would book the level every time.
            entry_price = max(entry_level, opened)
            entry_index = index
            # Bars, not wall clock. The vendor publishes a one minute bar only
            # for a minute that traded, so on a thin name this UNDERSTATES the
            # elapsed time and the column is a bar count wearing a minute's
            # name. Said here because a reader will otherwise take it for a
            # clock reading. It is exact on any name that trades every minute,
            # which is every name the fill check calls plausible.
            out["minutes_to_trigger"] = index
            out["entry_at"] = str(bar.get("t") or "")
            break
    if entry_price is None or entry_index is None:
        return out

    # The ONE thing that differs between versions. Everything above and below
    # this line is identical for every rule version by design.
    shares, refused = position_size(sizing_mode, entry_price, stop_level)
    if refused:
        out["exit_reason"] = refused
        return out

    lowest = None
    highest = None
    peak_at = 0
    exit_price = None
    exit_at = None
    exit_reason = EXIT_CLOSE
    held = 0
    for bar in bars[entry_index:]:
        high, low = _as_float(bar.get("h")), _as_float(bar.get("l"))
        close = _as_float(bar.get("c"))
        if low is None or high is None:
            continue
        held += 1
        lowest = low if lowest is None else min(lowest, low)
        if highest is None or high > highest:
            highest, peak_at = high, held - 1
        if low <= stop_level:
            exit_price = stop_level
            exit_at = str(bar.get("t") or "")
            exit_reason = EXIT_STOP
            break
        if close is not None:
            exit_price, exit_at = close, str(bar.get("t") or "")
    if exit_price is None:
        # Entered on a bar with no readable close and nothing after it. The
        # trade is open at the end of the data, which is not a result.
        out["exit_reason"] = EXIT_OPEN_AT_END
        return out

    out.update({
        "booked": 1,
        "entry_price": round(entry_price, 4),
        "exit_at": exit_at, "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "shares": shares, "notional": round(shares * entry_price, 2),
        "risk_notional_taken": round((entry_price - stop_level) * shares, 2),
        "pnl": round((exit_price - entry_price) * shares, 2),
        "pnl_pct": round((exit_price - entry_price) / entry_price * 100.0, 4),
        "max_drawdown_pct": (
            round((lowest - entry_price) / entry_price * 100.0, 4)
            if lowest is not None else None),
        # The best the position was ever worth, and when. mfe_pct_held is NOT
        # picks.mfe_pct_true: that one is a bound over the whole of the FOLLOWING
        # session measured from a reference level, and this one is what this
        # position was actually worth while it was actually open.
        "mfe_pct_held": (
            round((highest - entry_price) / entry_price * 100.0, 4)
            if highest is not None else None),
        "minutes_to_peak": peak_at,
        "minutes_to_trigger": out["minutes_to_trigger"],
        "bars_held": held,
    })
    return out


def book(day: str, probe: Any = None) -> dict[str, Any]:
    """Every live pick of one session, through EVERY rule version. Writes nothing.

    One fetch of the session's minutes serves every version, because the
    versions differ only in how much they buy and not in what they look at.
    Fetching per version would multiply the request count to re-read identical
    bars.
    """
    versions = rule_versions()
    # IMPORTED HERE, not at module scope, and probe_alpaca below for the same
    # reason. record_so_far is read by the 08:45 scan, and true_volume pulls
    # the research HTTP client the morning path has never loaded. Nothing that
    # answers a question from one local table should drag a socket client into
    # the window.
    from night import true_volume

    with store.session() as connection:
        store.init(connection)
        rows = [dict(row) for row in connection.execute(
            "SELECT ticker, day_eligible, swing_eligible, conviction, score, "
            "entry_ref_true, stop_ref_true, fill_plausible, "
            "fill_plausible_reason FROM picks "
            "WHERE date=? AND source='live' ORDER BY ticker", (day,))]
    if not rows:
        return {"day": day, "rows": [], "skipped": "no live picks rows",
                "versions": list(versions)}

    start, end = session_window(day)
    stamp = ettime.stamp(ettime.now_et())
    window_text = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

    # Only the rows the rule will actually trade are fetched. A skipped row
    # needs no bars, and the skip is decided from columns already in the table.
    tradeable = [r for r in rows
                 if r["fill_plausible"] == true_volume.FILL_PLAUSIBLE
                 and r["entry_ref_true"] is not None
                 and r["stop_ref_true"] is not None]
    bare = {r["ticker"]: r["ticker"].split(".", 1)[0] for r in rows}
    bars: dict[str, list[dict[str, Any]]] = {}
    error = None
    if tradeable:
        # IMPORTED HERE, not at module scope. record_so_far below is read by
        # the 08:45 scan, and probe_alpaca is a research client the morning
        # path has never loaded and should not start loading to answer a
        # question that is one local table read.
        import probe_alpaca

        probe = probe if probe is not None else probe_alpaca.Probe()
        bars, error = true_volume.fetch_bars(
            probe, sorted({bare[r["ticker"]] for r in tradeable}), start, end)

    out: list[dict[str, Any]] = []
    for row in rows:
      for version, mode in versions.items():
        record: dict[str, Any] = {
            "date": day, "ticker": row["ticker"], "rule_version": version,
            "sizing_mode": mode, "session": window_text,
            "day_eligible": row["day_eligible"],
            "swing_eligible": row["swing_eligible"],
            "conviction": row["conviction"], "score": row["score"],
            "booked": 0, "skip_reason": None,
            "entry_ref_used": row["entry_ref_true"],
            "stop_ref_used": row["stop_ref_true"],
            "entry_at": None, "entry_price": None, "exit_at": None,
            "exit_price": None, "exit_reason": None, "shares": None,
            "notional": None, "risk_notional_taken": None,
            "pnl": None, "pnl_pct": None,
            "max_drawdown_pct": None, "bars_held": None,
            "booked_at": stamp,
        }
        # WRITTEN WITH ITS REASON, never dropped. A pick that vanishes from
        # the ledger is one nobody can ask about later, and the count of rows
        # the rule declined is as much a result as the ones it took.
        if row["fill_plausible"] != true_volume.FILL_PLAUSIBLE:
            record["skip_reason"] = (
                f"fill_plausible is {row['fill_plausible']!r}, not "
                f"{true_volume.FILL_PLAUSIBLE!r}: "
                f"{row['fill_plausible_reason'] or 'no reason recorded'}")
        elif row["entry_ref_true"] is None or row["stop_ref_true"] is None:
            record["skip_reason"] = (
                "no measured entry or stop reference, so the rule has no level "
                "to trigger on. The sampled entry_ref is NOT substituted: it "
                "is the number the measured one exists to be compared against")
        elif error:
            record["skip_reason"] = (
                f"the session's minutes could not be fetched ({error}), so "
                "nothing is known about what the rule would have done")
        else:
            record.update(simulate(
                bars.get(bare[row["ticker"]]) or [],
                float(row["entry_ref_true"]), float(row["stop_ref_true"]),
                mode))
            if not (bars.get(bare[row["ticker"]]) or []):
                record["skip_reason"] = (
                    f"alpaca returned no minutes for {window_text}, so the "
                    "rule was not applied rather than read as no trigger")
                record["exit_reason"] = None
        out.append(record)
    return {"day": day, "rows": out, "skipped": None,
            "versions": list(versions),
            "session": window_text, "fetch_error": error,
            "requests": getattr(probe, "request_count", 0)}


def write(result: dict[str, Any], dry_run: bool = False) -> int:
    """Upsert on (date, ticker, rule_version). A re-run replaces its own rows.

    Keyed on the rule version, so bumping [Paper] rule_version books a second
    set beside the first rather than over it. Re-running the SAME version is an
    update, because it is the same rule over the same tape and a second copy of
    it would be a duplicate rather than a second observation.
    """
    if dry_run or not result["rows"]:
        return 0
    with store.session() as connection:
        store.init(connection)
        # The table is in store's own schema and store.init creates it, so
        # there is one place a column is declared. LEDGER_COLUMNS below is the
        # writer's list and a claim holds the two in step.
        for record in result["rows"]:
            store.upsert(connection, "paper_trades",
                         ["date", "ticker", "rule_version"], record)
        connection.commit()
    return len(result["rows"])


def record_so_far(rule: str | None = None) -> dict[str, Any]:
    """What the ledger has observed, as plain counts with their denominators.

    THIS IS WHAT THE MORNING CAN USE, and it is the only part of the ledger
    that is any use before the record is large enough to judge. Last Tuesday's
    winners and losers are worth nothing to somebody reading Wednesday's
    report; the SHAPE of what those trades did is worth something, and it is a
    different quantity.

    Every figure carries its own n and its own session count, and nothing here
    is a threshold, a recommendation or a rule. It is a description of a record
    that currently spans a handful of sessions, and scan puts it in the packet
    so the report can state it with those denominators attached rather than
    leaving a reader to assume it rests on something.

    NO NETWORK AND NO VENDOR CALL. One read of a local table, which is why the
    08:45 scan may call it.
    """
    rule = rule or sorted(rule_versions())[0]
    with store.session() as connection:
        store.init(connection)
        rows = [dict(r) for r in connection.execute(
            "SELECT * FROM paper_trades WHERE rule_version=?", (rule,))]
    booked = [r for r in rows if r["booked"] and r["pnl_pct"] is not None]
    timed = [r for r in booked if r["minutes_to_trigger"] is not None]
    peaked = [r for r in booked if r["minutes_to_peak"] is not None
              and r["pnl_pct"] is not None]
    # THREE STATES BELOW A BOOKED TRADE, not two. This read "booked=0 and no
    # skip_reason" and called the result never_triggered, which also caught
    # every row whose trigger DID fire and was then refused by position_size:
    # that path sets exit_reason and returns with booked still 0 and
    # skip_reason still unset (see simulate, the `if refused:` branch). The
    # report quotes this count verbatim as "picks never reached their trigger
    # at all", so a pick that reached its trigger would be published as one
    # that did not.
    #
    # EXIT_NEVER is what the never-fired path actually writes, so it is what
    # this asks. No live row has been mislabelled yet, because the sizing
    # refusals need a zero or near zero stop distance and the smallest on
    # record is 0.33, but the count is wrong by construction and the first
    # row to hit it would be silent.
    # Reached its trigger and bought nothing. A different fact from both
    # neighbours: the screen found the setup and the SIZING declined it, so
    # the fix is in [Paper] and not in the screen.
    #
    # Identified POSITIVELY, by an exit_reason that is present and is not
    # EXIT_NEVER, rather than by "anything that is not EXIT_NEVER". A
    # booked=0 row may legitimately carry a null exit_reason, and reading a
    # null as a refusal would move rows into this bucket on the absence of
    # evidence, which is the same mistake one level down.
    # FIVE STATES, because simulate reaches booked=0 by three different
    # roads and only two of them are a refusal to buy. EXIT_OPEN_AT_END is
    # the third: that row WAS sized and DID enter, and the window ran out
    # before a readable close. Counting it as unsized would have the report
    # publish it under "the sizing rule declined to buy anything", which is
    # false about it, and print a reason that says nothing about sizing.
    unsized = [r for r in rows
               if not r["booked"] and not r["skip_reason"]
               and r["exit_reason"]
               and r["exit_reason"] not in (EXIT_NEVER, EXIT_OPEN_AT_END)]
    open_at_end = [r for r in rows
                   if not r["booked"] and not r["skip_reason"]
                   and r["exit_reason"] == EXIT_OPEN_AT_END]
    accounted = {(r["date"], r["ticker"]) for r in unsized + open_at_end}
    never = [r for r in rows
             if not r["booked"] and not r["skip_reason"]
             and (r["date"], r["ticker"]) not in accounted]
    skipped = [r for r in rows if r["skip_reason"]]

    def denom(held: list[dict[str, Any]]) -> dict[str, int]:
        return {"rows": len(held), "sessions": len({r["date"] for r in held})}

    early = [r for r in timed if r["minutes_to_trigger"] <= 30]
    fast_peak = [r for r in peaked if r["minutes_to_peak"] <= 10]
    slow_peak = [r for r in peaked if r["minutes_to_peak"] >= 100]
    return {
        "rule_version": rule,
        "picks": denom(rows), "booked": denom(booked),
        "skipped": denom(skipped), "never_triggered": denom(never),
        # Named even at zero. A count that appears only when it is non zero
        # is a count nobody learns to read, and this one exists to be seen
        # the first time it moves.
        "triggered_but_unsized": denom(unsized),
        "triggered_but_unsized_reasons": sorted(
            {r["exit_reason"] for r in unsized if r["exit_reason"]}),
        # Entered and never resolved. Named at zero for the same reason as
        # the bucket above it.
        "open_at_session_end": denom(open_at_end),
        "triggered_within_30_min": len(early),
        "triggered_total": len(timed),
        "peaked_within_10_min": len(fast_peak),
        "peaked_within_10_min_closed_red":
            sum(1 for r in fast_peak if r["pnl_pct"] <= 0),
        "peaked_after_100_min": len(slow_peak),
        "peaked_after_100_min_closed_green":
            sum(1 for r in slow_peak if r["pnl_pct"] > 0),
        "median_minutes_to_trigger": (
            statistics.median(r["minutes_to_trigger"] for r in timed)
            if timed else None),
        "median_best_while_held": (
            statistics.median(r["mfe_pct_held"] for r in booked
                              if r["mfe_pct_held"] is not None)
            if any(r["mfe_pct_held"] is not None for r in booked) else None),
        "median_booked_pct": (
            statistics.median(r["pnl_pct"] for r in booked) if booked else None),
    }


def report(result: dict[str, Any]) -> None:
    if result.get("skipped"):
        print(f"paper: nothing booked for {result['day']}: {result['skipped']}")
        return
    rows = result["rows"]
    versions = result.get("versions") or []
    booked = [r for r in rows if r["booked"]]
    picks = len({r["ticker"] for r in rows})
    print(f"paper: {result['day']} over {result['session']}, "
          f"{len(booked)} trades booked from {picks} live picks across "
          f"{len(versions)} rule version(s) {', '.join(versions)}, "
          f"{result.get('requests', 0)} alpaca requests, no EODHD quota")
    print(f"  {'rule':<5} {'ticker':<10} {'entry':>10} {'exit':>10} "
          f"{'why':>14} {'shares':>7} {'position':>11} {'at risk':>9} "
          f"{'pnl':>10} {'pnl %':>8}")
    for record in rows:
        if not record["booked"]:
            continue
        print(f"  {record['rule_version']:<5} {record['ticker']:<10} "
              f"{record['entry_price']:>10} {record['exit_price']:>10} "
              f"{record['exit_reason']:>14} {record['shares']:>7} "
              f"{record['notional']:>11,.0f} "
              f"{record['risk_notional_taken']:>9,.0f} "
              f"{record['pnl']:>10,.2f} {record['pnl_pct']:>+7.2f}%")
    # The refusals are per TICKER, not per version: the skip rule is deliberately
    # the same for every version so they all trade one population. Printing them
    # once keeps that visible rather than repeating each reason per version.
    seen: set[str] = set()
    for record in rows:
        if record["booked"] or record["ticker"] in seen:
            continue
        seen.add(record["ticker"])
        why = record["skip_reason"] or record["exit_reason"] or "no reason"
        print(f"  {'':5} {record['ticker']:<10} not traded: {why}")


def ledger_report() -> None:
    """The one line the report can carry, and the diagnostics beside it.

    THE RULE VERSION IS NAMED because a P&L without the rule that produced it
    is not a number anybody can act on or argue with.

    BOTH DENOMINATORS, because twelve names from one morning share a tape and
    are one observation. Every summary here prints rows and sessions.

    mfe_pct_true SITS BESIDE THE BOOKED P&L, which is the point of the ledger.
    The bound is what was available at the tape's best moment and the booking
    is what one written rule captured, and the gap between them is what a
    target would have been trying to take. They are also measured over
    DIFFERENT SESSIONS, which is stated on the line rather than left to be
    discovered: the ledger trades the pick's own session and [Outcomes]
    measures the one after it.
    """
    with store.session() as connection:
        store.init(connection)
        rows = [dict(row) for row in connection.execute(
            "SELECT p.*, k.mfe_pct_true, k.mae_pct_true FROM paper_trades p "
            "LEFT JOIN picks k ON k.date=p.date AND k.ticker=p.ticker "
            # The ledger is the judging count, so the join has to say which
            # picks row it is borrowing an excursion from. paper_trades has no
            # source column of its own and nothing but the live path writes
            # it, but the JOIN reaches into a table that now holds
            # reconstructed rows too.
            "AND k.source='live'")]
    if not rows:
        print("paper: the ledger is empty")
        return

    by_version: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_version.setdefault(row["rule_version"], []).append(row)

    print("")
    summaries: dict[str, dict[str, Any]] = {}
    for version, held in sorted(by_version.items()):
        booked = [r for r in held if r["booked"] and r["pnl_pct"] is not None]
        picks = len({r["ticker"] + r["date"] for r in held})
        sessions = len({r["date"] for r in held})
        skipped = [r for r in held if r["skip_reason"]]
        # Same three way split as record_so_far, and for the same reason.
        unsized = [r for r in held
                   if not r["booked"] and not r["skip_reason"]
                   and r["exit_reason"]
                   and r["exit_reason"] not in (EXIT_NEVER, EXIT_OPEN_AT_END)]
        open_at_end = [r for r in held
                       if not r["booked"] and not r["skip_reason"]
                       and r["exit_reason"] == EXIT_OPEN_AT_END]
        accounted = {(r["date"], r["ticker"]) for r in unsized + open_at_end}
        never = [r for r in held
                 if not r["booked"] and not r["skip_reason"]
                 and (r["date"], r["ticker"]) not in accounted]
        if not booked:
            print(f"paper: rule {version} booked NO trades across "
                  f"{picks} picks in {sessions} session(s). "
                  f"{len(skipped)} skipped, {len(never)} never triggered, "
                  f"{len(unsized)} triggered and could not be sized, "
                  f"{len(open_at_end)} still open at the session end.")
            continue
        wins = [r for r in booked if r["pnl_pct"] > 0]
        drawdowns = [r["max_drawdown_pct"] for r in booked
                     if r["max_drawdown_pct"] is not None]
        risks = [r["risk_notional_taken"] for r in booked
                 if r["risk_notional_taken"] is not None]
        summaries[version] = {
            "booked": booked, "sessions": sessions, "picks": picks,
            "pnl": sum(r["pnl"] for r in booked),
            "worst_trade": min(r["pnl"] for r in booked),
            "risks": risks,
        }
        # THE ONE LINE. Rule version, both denominators, median booked P&L,
        # win rate, worst drawdown. The drawdown clause is appended rather than
        # made a condition on the whole line: written the other way round the
        # `if` bound to the entire f-string, so a ledger with no readable
        # drawdown printed a BLANK LINE instead of the summary.
        worst = (f", worst drawdown {min(drawdowns):+.2f}%" if drawdowns
                 else ", worst drawdown unknown, no row carries one")
        print(f"paper: rule {version} booked {len(booked)} trades from "
              f"{picks} picks across {sessions} session(s): median "
              f"{statistics.median(r['pnl_pct'] for r in booked):+.2f}%, "
              f"win rate {len(wins)}/{len(booked)}{worst}")
        # EVERY state, so the printed counts reconcile against picks. This
        # branch computed unsized and never printed it, so the first sizing
        # refusal on a version that had booked anything would have left an
        # unexplained shortfall in the one place a reader tallies the record.
        print(f"  not traded: {len(skipped)} skipped on evidence, "
              f"{len(never)} never reached the trigger, "
              f"{len(unsized)} triggered and could not be sized, "
              f"{len(open_at_end)} still open at the session end")
        stopped = [r for r in booked if r["exit_reason"] == EXIT_STOP]
        print(f"  exits: {len(stopped)} stopped, "
              f"{len(booked) - len(stopped)} held to the close")
        # The sizing is NAMED on the line rather than assumed, because the two
        # versions put different amounts of money to work and a dollar total
        # read without it is not comparable to anything.
        mode = (booked[0].get("sizing_mode") or "unrecorded")
        if risks:
            print(f"  sized by {mode}: total P&L {summaries[version]['pnl']:+,.2f} "
                  f"dollars, {sum(r['notional'] for r in booked):,.0f} deployed, "
                  f"{sum(risks):,.0f} put at risk "
                  f"({min(risks):,.0f} to {max(risks):,.0f} per trade)")

        paired = [r for r in booked if r["mfe_pct_true"] is not None]
        if paired:
            print(f"  beside it, mfe_pct_true over the SAME picks: median "
                  f"{statistics.median(r['mfe_pct_true'] for r in paired):+.2f}%"
                  f" over n={len(paired)}. That is a BOUND at the tape's best "
                  "moment, on the session AFTER the one the rule traded, and "
                  "it is not a return.")

    # ------------------------------------------------------- head to head
    #
    # The comparison the versions exist for, and the ONLY honest way to read
    # two sizing rules against each other: the same trades, so the difference
    # is the sizing and nothing else. The pre-registered verdict in
    # CRITERIA [Paper] is stated but NOT evaluated here, because the count is
    # nowhere near its judging point and a verdict printed early is a verdict
    # that gets read.
    if len(summaries) < 2:
        return
    print("")
    print("paper: HEAD TO HEAD, over the trades every version booked")
    common = set.intersection(*[
        {(r["date"], r["ticker"]) for r in s["booked"]}
        for s in summaries.values()])
    if not common:
        print("  no trade was booked by every version, so there is nothing to "
              "compare that is not confounded by a different population")
        return
    print(f"  {'rule':<5} {'mode':<9} {'trades':>7} {'total P&L':>12} "
          f"{'deployed':>12} {'at risk':>10} {'worst trade':>12}")
    for version, s in sorted(summaries.items()):
        shared = [r for r in s["booked"] if (r["date"], r["ticker"]) in common]
        risks = [r["risk_notional_taken"] for r in shared
                 if r["risk_notional_taken"] is not None]
        print(f"  {version:<5} {shared[0].get('sizing_mode') or '?':<9} "
              f"{len(shared):>7} "
              f"{sum(r['pnl'] for r in shared):>+12,.2f} "
              f"{sum(r['notional'] for r in shared):>12,.0f} "
              f"{sum(risks):>10,.0f} "
              f"{min(r['pnl'] for r in shared):>+12,.2f}")
    print(f"  {len(common)} trade(s) booked by every version, across "
          f"{len({d for d, _ in common})} session(s). The sample unit is the "
          "session.")
    print("  CRITERIA [Paper] pre-registers the verdict and its judging point, "
          "200 booked trades across 60 sessions. Nothing here is that verdict.")


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the CRITERIA [Paper] rule to each live pick.")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                        help="The session to book. Defaults to today.")
    parser.add_argument("--all", action="store_true",
                        help="Book every session with live picks rows.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apply the rule and print, write nothing.")
    args = parser.parse_args(argv)

    if args.all:
        with store.session() as connection:
            store.init(connection)
            days = [row[0] for row in connection.execute(
                "SELECT DISTINCT date FROM picks WHERE source='live' "
                "ORDER BY date")]
    else:
        days = [args.date or ettime.today_str()]

    written = 0
    for day in days:
        result = book(day)
        written += write(result, dry_run=args.dry_run)
        report(result)
    if not args.dry_run:
        ledger_report()
    job_status.produced("paper trades booked", written)
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("paper", main, ok_codes=OK_CODES))
