"""Regression test for five ways the packet or the template understated a gap.

All five were found by reading runs/2026-08-19 against its own packet, and
every one of them is the same shape: something the code already knew was
missing, incomplete or broken, reaching the reader as nothing at all.

  1. A refused collector run recorded the refusal INSTEAD OF its counters, so
     a morning that folded 14,680 trades before the server refused a reconnect
     reached the packet as messages 0, connections 0.
  2. read_run_stats summed a missing counter as zero, so even a run that
     genuinely never counted read as a run that counted none.
  3. job_health measures staleness of last_success in whole trading sessions,
     every window being one session or more, so a step that failed at 08:16
     and was rerun at 08:37 was current by every measure the packet had. The
     morning report said nothing about a collector that had died.
  4. That new failure line has to survive a bad morning without becoming
     unreadable, which is the same argument the overdue side already won.
  5. pm_rvol_basis.is_lower_bound was computed per candidate, stored in the
     packet, and surfaced nowhere, so the report described a ratio that can
     only understate as a ratio that came out low.

Claim 6 is the drift guard for the two sentences the template asked for and
the packet contradicted. A seventh claim, added later, pins the replayed
opening print: an out of window trade is written to the bar file tagged rather
than dropped, and is never totalled into the morning's own minutes.
"""

from __future__ import annotations

from tests.conftest import run_claim

import json
import pathlib
import re
import sys
import tempfile
from pathlib import Path

from collect import collect_premarket
from core import config
from ops import job_status

TEMPLATE = config.PROJECT_ROOT / "doc" / "REPORT_TEMPLATE.md"


# ----------------------------------------------------------------- 1 and 2

def _stats_file(directory: Path, rows: list[dict]) -> Path:
    path = directory / "2026-01-02-stats.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _read_stats(path: Path) -> dict | None:
    """read_run_stats against a temporary sidecar rather than the real one."""
    original = collect_premarket.stats_path
    collect_premarket.stats_path = lambda day=None: path
    try:
        return collect_premarket.read_run_stats("2026-01-02")
    finally:
        collect_premarket.stats_path = original


def claim_a_refused_run_still_reports_what_it_heard(tmp: Path, failures: list[str]) -> None:
    """The refusal is a fact about the run, not a replacement for it."""
    path = _stats_file(tmp, [
        # What a refused run writes now: its counters, plus the marker.
        {"connections": 1, "reconnects": 0, "resubscriptions": 1,
         "messages": 14680, "status_frames": 0, "subscription_refused": True},
        {"connections": 1, "reconnects": 0, "resubscriptions": 1,
         "messages": 39727, "status_frames": 0},
    ])
    totals = _read_stats(path)
    if totals is None or totals.get("messages") != 14680 + 39727:
        failures.append(
            "a refused run's messages must reach the aggregate, got "
            f"{(totals or {}).get('messages')!r} rather than 54407")
    if (totals or {}).get("connections") != 2:
        failures.append("a refused run's connection must be counted, got "
                        f"{(totals or {}).get('connections')!r} rather than 2")
    if (totals or {}).get("runs") != 2:
        failures.append(f"two runs must count as two, got {(totals or {}).get('runs')!r}")
    print("  claim refused  a refused run's counters reach the aggregate")


def claim_uncounted_is_not_zero(tmp: Path, failures: list[str]) -> None:
    """A morning nobody counted must not read as a morning that saw none."""
    path = _stats_file(tmp, [{"subscription_refused": True}])
    totals = _read_stats(path)
    if (totals or {}).get("messages") is not None:
        failures.append("a run carrying no message count must leave messages null, "
                        f"got {(totals or {}).get('messages')!r}")
    if (totals or {}).get("runs") != 1:
        failures.append("the run itself still counts even when its counters do not")

    # And the other direction: a run that really did see zero says zero.
    path = _stats_file(tmp, [{"connections": 1, "messages": 0}])
    totals = _read_stats(path)
    if (totals or {}).get("messages") != 0:
        failures.append("a run that counted zero must report zero, not null, got "
                        f"{(totals or {}).get('messages')!r}")
    print("  claim uncounted a missing counter stays null and a real zero stays zero")


# ---------------------------------------------------------------- 3 and 4

def _record(step: str, at: str, status: str = "error", exception: str | None = None,
            exit_code: int | None = 1) -> dict:
    return {"step": step, "started_at": at, "ended_at": at, "status": status,
            "exit_code": exit_code, "exception": exception, "job": "test"}


def claim_a_failure_today_reaches_the_report(failures: list[str]) -> None:
    """The morning of 2026-08-19, in miniature."""
    import datetime as dt
    day = dt.date(2026, 1, 2)
    rows = [
        _record("collector", "2026-01-02T08:16:51-04:00",
                exception="SubscriptionRefused: the server refused the subscription"),
        _record("collector", "2026-01-02T08:37:13-04:00", status="ok", exit_code=0),
        _record("scan", "2026-01-02T08:45:00-04:00", status="ok", exit_code=0),
    ]
    if job_status.overdue(day, rows):
        failures.append("nothing here is overdue, so the old measure must stay silent")
    line = job_status.report_line(day, rows)
    if not line or "collector" not in line:
        failures.append(f"a step that failed today must be named, got {line!r}")
    if line and "08:16" not in line:
        failures.append(f"the failure's own time must be in the line, got {line!r}")
    if line and "later run succeeded" not in line:
        failures.append(f"a recovered failure must say so, got {line!r}")

    # A morning where nothing failed says nothing at all. Silence is the
    # normal case and a line that appears every morning is a line nobody reads.
    clean = [_record("collector", "2026-01-02T07:20:00-04:00", status="ok", exit_code=0),
             _record("scan", "2026-01-02T08:45:00-04:00", status="ok", exit_code=0)]
    if job_status.report_line(day, clean) is not None:
        failures.append("a clean morning must produce no line at all")

    # A failure nothing picked back up reads differently from one that recovered.
    stuck = [_record("collector", "2026-01-02T08:16:51-04:00", exit_code=1)]
    stuck_line = job_status.report_line(day, stuck) or ""
    if "has not run again since" not in stuck_line:
        failures.append(f"an unrecovered failure must say so, got {stuck_line!r}")
    print("  claim today    a step that failed this morning is named, and a clean "
          "morning stays silent")


def claim_the_failure_line_stays_readable(failures: list[str]) -> None:
    """Five retries of one step is one problem, not five."""
    import datetime as dt
    day = dt.date(2026, 1, 2)
    rows = [_record("analyst", f"2026-01-02T15:5{n}:00-04:00", status="failed",
                    exit_code=2) for n in range(5)]
    rows.append(_record("analyst", "2026-01-02T16:10:00-04:00", status="ok", exit_code=0))
    line = job_status.report_line(day, rows) or ""
    if line.count("analyst failed") != 1:
        failures.append(f"one step must be named once, got {line!r}")
    if "5 times" not in line:
        failures.append(f"the repeat count must survive the collapse, got {line!r}")

    # Past the CRITERIA cap the list stops being a list of problems and
    # becomes one problem, exactly as the overdue side already argues.
    limit = job_status._CRIT.integer("job_status", "max_steps_named_in_report")
    many = [_record(step, "2026-01-02T08:00:00-04:00", status="failed", exit_code=1)
            for step in job_status.tracked_steps()[:limit + 3]]
    crowded = job_status.report_line(day, many) or ""
    named = len(re.findall(r"failed (?:at \d|\d+ times)", crowded))
    if named > limit:
        failures.append(f"the failure list must be capped at {limit}, named {named}")
    if str(len(many)) not in crowded:
        failures.append(f"the total must be stated when the list is capped, got {crowded!r}")
    print("  claim readable repeats collapse with a count and the list is capped")


# ---------------------------------------------------------------------- 5

def claim_a_lower_bound_reaches_gaps_to_fill(failures: list[str]) -> None:
    """A ratio that can only understate is not a ratio that came out low."""
    from morning import scan

    packet = scan.Packet()
    candidates = [
        {"symbol": "AAA.US", "pm_rvol_basis": {"is_lower_bound": True}},
        {"symbol": "BBB.US", "pm_rvol_basis": {"is_lower_bound": True}},
        {"symbol": "CCC.US", "pm_rvol_basis": {"is_lower_bound": False}},
        {"symbol": "DDD.US", "pm_rvol": None},
    ]
    scan._gap_for_lower_bound_rvol(candidates, packet, "07:20", "04:00")
    joined = " ".join(packet.gaps)
    if not packet.gaps:
        failures.append("a lower bound RVOL must produce a gap, got none")
    for symbol in ("AAA.US", "BBB.US"):
        if symbol not in joined:
            failures.append(f"{symbol} is a lower bound and must be named")
    for symbol in ("CCC.US", "DDD.US"):
        if symbol in joined:
            failures.append(f"{symbol} is not a lower bound and must not be named")
    if "lower bound" not in joined:
        failures.append(f"the gap must say what it is, got {joined!r}")

    # No lower bound anywhere means no sentence. The gaps list is what the
    # disclaimer surfaces, and padding it teaches the reader to skip it.
    quiet = scan.Packet()
    scan._gap_for_lower_bound_rvol(
        [{"symbol": "CCC.US", "pm_rvol_basis": {"is_lower_bound": False}}],
        quiet, "07:20", "04:00")
    if quiet.gaps:
        failures.append(f"no lower bound must mean no gap, got {quiet.gaps!r}")
    print("  claim bound    a lower bound RVOL is named in gaps_to_fill and a "
          "complete one is not")


# ---------------------------------------------------------------------- 6

def claim_replay_is_tagged_and_never_totalled(tmp: Path, failures: list[str]) -> None:
    """A replayed print is in the file and out of every total.

    Before this, an out of window trade was counted in a log line and dropped.
    That stopped the vintage defect and left no way to ask afterwards how much
    replay a session carried: the 2026-08-19 audit had to reconstruct it from a
    subscription time held in another file, and for 2026-08-14 that file does
    not exist.
    """
    path = tmp / "bars.jsonl"
    now = 1787000000.0
    builder = collect_premarket.BarBuilder(path, source="ws", window=(now, now + 3600))
    builder.add_trade("SPY.US", 100.0, 500, now + 10, False, "extended-hours")
    builder.add_trade("SPY.US", 99.0, 300, now - 86400, False, "extended-hours")
    builder.add_trade("QQQ.US", 50.0, 200, now - 60, False, "extended-hours")
    builder.flush(now + 7200, force=True)

    if builder.rows_written != 1:
        failures.append("rows_written counts this morning's minutes only, got "
                        f"{builder.rows_written} rather than 1")
    if builder.replay_rows_written != 2:
        failures.append(f"two replayed minutes must be written, got "
                        f"{builder.replay_rows_written}")

    written = [json.loads(line) for line in
               path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tagged = [r for r in written if r.get("replay")]
    if len(tagged) != 2:
        failures.append(f"the file must carry both replayed rows tagged, got {len(tagged)}")
    if any("replay_reason" not in r for r in tagged):
        failures.append("a tagged row must say why it is tagged")

    bars, stats = collect_premarket.read_bars_file(path)
    if sorted(bars) != ["SPY.US"]:
        failures.append(f"replay must not reach the bars, got symbols {sorted(bars)}")
    if len(bars.get("SPY.US", [])) != 1:
        failures.append("the replayed SPY minute must not join its real one")
    if stats.get("replay_rows") != 2 or stats.get("replay_volume") != 500.0:
        failures.append("the replay must be counted in stats, got "
                        f"{stats.get('replay_rows')!r} rows, "
                        f"{stats.get('replay_volume')!r} shares")
    if stats.get("bars_total") != 1:
        failures.append(f"bars_total must exclude replay, got {stats.get('bars_total')}")

    # An ordinary file carries no tag, and that must read as no replay rather
    # than as unknown replay in the count.
    plain = tmp / "plain.jsonl"
    quiet = collect_premarket.BarBuilder(plain, source="ws", window=(now, now + 3600))
    quiet.add_trade("SPY.US", 100.0, 500, now + 10, False, "extended-hours")
    quiet.flush(now + 7200, force=True)
    _, plain_stats = collect_premarket.read_bars_file(plain)
    if plain_stats.get("replay_rows") != 0:
        failures.append("a file with no replay must count zero, got "
                        f"{plain_stats.get('replay_rows')!r}")
    print("  claim replay   a replayed print is written tagged, filtered from the "
          "bars, and counted apart")


# ---------------------------------------------------------------------- 7

def claim_the_template_does_not_ask_for_the_false_sentences(failures: list[str]) -> None:
    """Two sentences the template asked for that the packet contradicted."""
    text = TEMPLATE.read_text(encoding="utf-8")

    # The names dropped for no coverage are required in the disclaimer BY THIS
    # SAME TEMPLATE, so a report claiming they appear nowhere else is false
    # every time it is written.
    if "appear nowhere else in the report" in text:
        failures.append("the template asks the report to claim the dropped names "
                        "appear nowhere else, which its own disclaimer rule falsifies")

    # subscribed_considered counts what reached the ranking, after the
    # no-coverage and stale-price drops. Calling it what the collector heard
    # asserts the stale-price names were never heard, and the same sentence
    # goes on to name them.
    if "names the collector\nheard" in text or "names the collector heard" in text:
        failures.append("the template calls subscribed_considered the number of "
                        "names the collector heard, which is a different count")

    # And the fix has to still be there, not merely the defect gone.
    if "names ranked" not in text:
        failures.append("the funnel sentence must name what the count actually is")
    if "is_lower_bound" not in text:
        failures.append("the template must require the lower bound qualifier")
    print("  claim drift    the template no longer asks for either sentence the "
          "packet contradicts")


# ------------------------------------------------- 8, 9 and 10, the roll

# Every shape the roll has to answer in, chosen so that a predicate read the
# wrong way round shows up. FULL sets every flag on one name, MIXED splits them
# across three so a roll that ORs its predicates together fails, and EMPTY is
# the quiet morning where each line has to read 0 of N rather than disappear.
_ROLL_CASES = {
    "empty": [
        {"symbol": "AAA.US", "pm_rvol": 1.0, "pm_rvol_basis": {},
         "catalyst_found": True, "collector_covered": True},
    ],
    "full": [
        {"symbol": "AAA.US", "pm_rvol": None, "pm_rvol_reason": "why",
         "pm_window_starts_late": True, "collector_covered": False,
         "pm_rvol_basis": {"is_lower_bound": True}, "catalyst_found": False,
         "catalyst_why": "checked and paid nothing"},
    ],
    "mixed": [
        # Heard, and NOT on the watchlist, so it keeps a price, survives
        # drop_uncovered and carries collector_covered false. The live shape,
        # seen with WDAY on 2026-08-13 and AAPL on 2026-08-21.
        {"symbol": "AAA.US", "pm_rvol": None, "pm_rvol_reason": "why",
         "catalyst_found": None, "catalyst_why": "the feed was never read",
         "collector_covered": False},
        {"symbol": "BBB.US", "pm_rvol": 2.0, "pm_window_starts_late": True,
         "pm_rvol_basis": {"is_lower_bound": True}, "catalyst_found": False,
         "collector_covered": True},
        {"symbol": "CCC.US", "pm_rvol": 3.0, "pm_rvol_basis": {},
         "catalyst_found": True, "collector_covered": True},
    ],
}


_SHAPE_CANDIDATES = [
    {"symbol": "AAA.US", "quote": {"sector": "Information Technology"},
     "gap_direction": "up",
     "catalyst_class": "earnings", "pm_rvol": 2.0, "pm_window_start": "07:20",
     "pm_window_thin": False, "score": 7.0, "pm_band_state": "thin",
     "catalyst_found": True, "pm_rvol_basis": {"is_lower_bound": True}},
    {"symbol": "BBB.US", "quote": {"sector": "Information Technology"},
     "gap_direction": "down",
     "catalyst_class": "earnings", "pm_rvol": 3.0, "pm_window_start": "07:20",
     "pm_window_thin": False, "score": 5.0, "pm_band_state": "not flagged",
     "catalyst_found": True, "pm_rvol_basis": {"is_lower_bound": True}},
    # No RVOL at all, so the lower bound question cannot be ASKED of it. This
    # row is what makes the shared/askable split observable.
    {"symbol": "CCC.US", "quote": {"sector": "Health Care"},
     "gap_direction": "down",
     "catalyst_class": None, "pm_rvol": None, "pm_window_start": "07:41",
     "pm_window_starts_late": True,
     "pm_window_thin": False, "score": 2.0, "pm_band_state": "unknown",
     "catalyst_found": None, "pm_rvol_basis": {}},
]


def claim_a_prior_outcome_is_read_off_the_right_session(
        failures: list[str]) -> None:
    """The record speaks about a name, and it speaks about the correct day.

    THIS IS THE ONE THAT COULD HAVE SHIPPED A WRONG NUMBER QUIETLY. picks holds
    mfe_pct, mae_pct and pm_high_broke_next_day, they are the obvious columns
    to reach for, and every one of them describes the session AFTER the one the
    pick was about. AXTI picked 2026-08-27 opened 70.30 against an entry
    reference of 70.94 and reached 70.85, a miss by 0.13 percent, while its
    mfe_pct reads -7.79 off the following day's high of 65.4155. A sentence
    reading "when this name was last picked its premarket high did not break"
    built from those columns is a statement about the wrong day, in the one
    place whose whole value is that it is about the right one.

    paper_ledger fetches its own bars for its own session, which is precisely
    why it exists, so paper_trades is the source and this claim holds that.
    CRITERIA [Outcomes] records why the picks columns are not repointed:
    repointing rewrites the meaning of every row already in the table.

    THREE STATES AGAIN. A booked trade has a return. A trigger that never fired
    is not a loss. A row skipped on evidence was never asked. Collapsing any
    two of them turns a morning the rule sat out into a morning it lost.

    And ONE RULE VERSION, the earliest. Every version books the same trades and
    differs only in position size, so per trade percent returns are identical
    under all of them and reading two would double every count in the sentence.
    """
    from core import store
    from morning import scan

    with store.session() as connection:
        store.init(connection)
        connection.execute("DELETE FROM picks")
        connection.execute("DELETE FROM paper_trades")
        for date, ticker, source in (
                ("2026-01-01", "AAA.US", "live"),
                ("2025-12-31", "AAA.US", "live"),
                ("2025-12-30", "AAA.US", "live"),
                ("2025-12-30", "BBB.US", "reconstructed"),
                ("2026-01-02", "AAA.US", "live")):
            connection.execute(
                "INSERT INTO picks (date, ticker, source) VALUES (?, ?, ?)",
                (date, ticker, source))
        for date, ticker, version, booked, pnl, exit_reason, skip in (
                # One traded, one that never triggered, one refused on
                # evidence. Three sessions, three states.
                ("2026-01-01", "AAA.US", "v1", 1, -2.5, "stop", None),
                ("2025-12-31", "AAA.US", "v1", 0, None, "trigger never fired", None),
                ("2025-12-30", "AAA.US", "v1", 0, None, None, "fill implausible"),
                # A second rule version over the same trade. Reading both
                # would report two trades where one happened.
                ("2026-01-01", "AAA.US", "v2", 1, -2.5, "stop", None),
                # A reconstruction, which nobody ever read.
                ("2025-12-30", "BBB.US", "v1", 1, 9.9, "session close", None)):
            connection.execute(
                "INSERT INTO paper_trades (date, ticker, rule_version, booked, "
                "pnl_pct, exit_reason, skip_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (date, ticker, version, booked, pnl, exit_reason, skip))
        connection.commit()

    got = scan.prior_outcomes(["AAA.US", "BBB.US"], "2026-01-02", 5)
    record = got.get("AAA.US") or {}
    if [b["date"] for b in record.get("booked") or []] != ["2026-01-01"]:
        failures.append(
            f"the booked sessions read {record.get('booked')}. One trade was "
            "booked, under two rule versions, and reading both would report it "
            "twice")
    if [n["date"] for n in record.get("never_triggered") or []] != ["2025-12-31"]:
        failures.append(
            f"the untriggered sessions read {record.get('never_triggered')}. A "
            "trigger that never fired is its own state and is not a loss")
    if [s["date"] for s in record.get("skipped") or []] != ["2025-12-30"]:
        failures.append(
            f"the skipped sessions read {record.get('skipped')}. A row the rule "
            "declined on evidence was never asked and is not an outcome")
    if "BBB.US" in got:
        failures.append(
            "a reconstruction reached the prior outcomes, and no reader ever "
            f"saw that session published: {got.get('BBB.US')}")

    # The sentence says nothing rather than reporting a zero, where the ledger
    # has no answer at all.
    with store.session() as connection:
        connection.execute("DELETE FROM paper_trades")
        connection.commit()
    silent = scan.list_shape(
        [{"symbol": "AAA.US", "quote": {"sector": "X"},
          "catalyst_class": "earnings", "gap_direction": "up"}],
        "2026-01-02")["text"]["repeat_appearances"]
    if "no booked outcome yet" not in silent:
        failures.append(
            "a repeat with no ledger row does not say so, so an absent outcome "
            f"reads as an outcome: {silent!r}")

    # THE SOURCE ITSELF. If someone later swaps paper_trades for the picks
    # outcome columns, this is what fails.
    source = pathlib.Path(scan.__file__).read_text(encoding="utf-8")
    body = source.split("def prior_outcomes(", 1)[1].split("\ndef ", 1)[0]
    for wrong in ("mfe_pct", "mae_pct", "pm_high_broke_next_day"):
        if f'"{wrong}"' in body or f"t.{wrong}" in body:
            failures.append(
                f"prior_outcomes reads picks.{wrong}, which describes the "
                "session AFTER the pick. The whole value of this sentence is "
                "that it is about the pick's own session")
    if "paper_trades" not in body:
        failures.append("prior_outcomes does not read paper_trades, which is "
                        "the only table holding the pick's own session")

    with store.session() as connection:
        connection.execute("DELETE FROM picks")
        connection.commit()

    print("  prior what a repeat did is read off the paper ledger's own "
          "session, in three states, under one rule version, and never off the "
          "outcome columns that describe the next day")


def claim_the_composition_carries_direction_and_a_scale(
        failures: list[str]) -> None:
    """Up against down, and a share with something to read it against.

    THE DIRECTION SPLIT IS NOT DECORATION. Rule 3c tells the model the score is
    unsigned, so a falling name can tie a rising one, and the mix is what makes
    that readable. It is also the whole explanation for an empty watchlist on a
    heavy down morning, because both screens are long only: on 2026-08-18
    eleven of twelve gapped down and nothing could pass, and the report had no
    way to say why.

    THE SCALE IS THE DENOMINATOR RULE APPLIED TO A COMPOSITION. Nine of twelve
    in one sector may be the most concentrated morning of the month or the
    fourth this week. picks gained its sector column on 2026-09-02, so for now
    the honest answer is that the comparison does not exist yet, and this holds
    that the sentence SAYS SO rather than printing a median over five sessions
    or omitting the question. A statistic computed correctly over a sample too
    small to mean anything is worse than none, because it looks like one.

    A session is one observation: the share is taken per session and the median
    across sessions, never over rows pooled together.
    """
    from core import store
    from morning import analyst, scan

    with store.session() as connection:
        store.init(connection)
        connection.execute("DELETE FROM picks")
        connection.commit()

    candidates = [
        {"symbol": "AAA.US", "quote": {"sector": "Tech"},
         "catalyst_class": "earnings", "gap_direction": "up"},
        {"symbol": "BBB.US", "quote": {"sector": "Tech"},
         "catalyst_class": "earnings", "gap_direction": "down"},
        {"symbol": "CCC.US", "quote": {"sector": "Health"},
         "catalyst_class": "none", "gap_direction": "down"},
    ]
    shape = scan.list_shape(candidates, "2026-01-02")

    if shape["gap_direction"] != {"down": ["BBB", "CCC"], "up": ["AAA"]}:
        failures.append(f"the direction split reads {shape['gap_direction']}")
    line = shape["text"]["gap_direction"]
    if "3 candidates" not in line or "down 2" not in line or "up 1" not in line:
        failures.append(f"the direction sentence carries no counts against its "
                        f"denominator: {line!r}")
    if "unsigned" not in line:
        failures.append(
            "the direction sentence does not say the score is unsigned, which "
            f"is the reason the split is worth printing: {line!r}")

    # No history at all, so the sector line says why rather than going quiet.
    sectors = shape["text"]["sectors"]
    if "no historical comparison" not in sectors:
        failures.append(
            "the sector sentence carries neither a comparison nor a reason "
            f"there is none: {sectors!r}")
    if shape["sector_history"]["median_top_sector_share"] is not None:
        failures.append(
            "a median was computed over an empty record: "
            f"{shape['sector_history']}")

    # Under the floor, it still refuses. One session is not twenty.
    with store.session() as connection:
        for ticker in ("AAA.US", "BBB.US"):
            connection.execute(
                "INSERT INTO picks (date, ticker, source, sector) "
                "VALUES (?, ?, 'live', 'Tech')", ("2026-01-01", ticker))
        connection.commit()
    thin = scan.sector_history("2026-01-02")
    if thin["median_top_sector_share"] is not None:
        failures.append(
            f"a median printed over {thin['sessions']} session(s) against a "
            f"floor of {thin['min_sessions']}: {thin}")
    if thin["sessions"] != 1:
        failures.append(f"the session count is {thin['sessions']} and one "
                        "session carries a sector")

    for key, sentence in shape["text"].items():
        for hit in analyst.quantifier_violations(sentence):
            failures.append(
                f"list_shape's {key} sentence asserts {hit['quantifier']!r} "
                f"near {hit['set_word']!r}: {sentence!r}")

    with store.session() as connection:
        connection.execute("DELETE FROM picks")
        connection.commit()

    print("  composition the up and down counts carry their denominator, and "
          "the sector share states why it has nothing to be read against yet")


def claim_the_list_shape_is_counted_and_never_derived(
        failures: list[str]) -> None:
    """What the twelve look like TOGETHER, on the screen_tally pattern.

    The report has always said a great deal about one candidate at a time and
    nothing about the list as a group. Nine of twelve names in one sector is a
    fact about the morning rather than about any of the nine, and a name picked
    on three of the last five recorded sessions is a different object from a
    first appearance. Neither is a property of a candidate, so neither is
    visible from a per candidate block however carefully it is read.

    COUNTED HERE BECAUSE IT IS A COUNT ACROSS THE SET, which is the exact shape
    of derivation that produced the false universal of 2026-08-18. There is one
    correct answer to "how many share a sector" and a filter performed in prose
    over a set the packet already holds is a membership claim nothing can
    check.

    Every sentence faces the quantifier guard here, because the report quotes
    them word for word. That includes the SECTOR LABELS, which are vendor text
    rather than this project's, so a label carrying a banned word would be
    built by Python, quoted under instruction, and flagged against the model.

    A null sector is its own named bucket. Folding it into the smallest real
    one would report a concentration that nobody measured.
    """
    from morning import analyst, scan

    shape = scan.list_shape(_SHAPE_CANDIDATES, "2026-01-02")

    if shape["sectors"] != {"Information Technology": ["AAA", "BBB"],
                            "Health Care": ["CCC"]}:
        failures.append(f"the sector grouping is {shape['sectors']}, and the "
                        "fixture holds two technology names and one health care")
    if shape["catalyst_classes"] != {"earnings": ["AAA", "BBB"],
                                     "unknown": ["CCC"]}:
        failures.append(
            f"the catalyst class grouping is {shape['catalyst_classes']}. A "
            "null class is its own named bucket, never folded into a real one")

    for key, line in shape["text"].items():
        for hit in analyst.quantifier_violations(line):
            failures.append(
                f"list_shape's {key} sentence asserts {hit['quantifier']!r} "
                f"near {hit['set_word']!r} and the report quotes it word for "
                f"word: {line!r}")
        # Three shapes carry the denominator: "N of M", "M candidates
        # across K groups", and "M candidates by ...". What matters is that
        # the population is stated, never that a particular wording is.
        if str(len(_SHAPE_CANDIDATES)) not in line:
            failures.append(f"list_shape's {key} sentence carries no "
                            f"denominator: {line!r}")

    # A null sector is NAMED rather than dropped or folded.
    unknown_sector = scan.list_shape(
        [{"symbol": "DDD.US", "quote": {}, "catalyst_class": "earnings"}],
        "2026-01-02")
    if "unknown" not in unknown_sector["sectors"]:
        failures.append("a candidate whose vendor quote carries no sector is "
                        "not bucketed as unknown: "
                        f"{unknown_sector['sectors']}")

    # And it describes rather than screens: nothing it touches is a decision.
    for candidate in _SHAPE_CANDIDATES:
        for decided in ("day_eligible", "swing_eligible", "conviction", "score"):
            if decided in candidate and decided == "day_eligible":
                failures.append("the shape fixture carries an eligibility "
                                "field, so this claim cannot show that "
                                "list_shape leaves one alone")

    print("  list shape  sector, catalyst class and repeat counts are computed "
          "against their denominators, a null sector is named, and not one "
          "sentence asserts a quantifier over the screened set")


def claim_a_repeat_appearance_reads_only_live_rows_before_today(
        failures: list[str]) -> None:
    """The repeat count is fenced twice, and both fences carry weight.

    SOURCE. The picks table holds live, test and reconstructed rows. Only live
    is the record of what a morning actually published, so a replayed session
    or a hand run would otherwise report a name as a repeat appearance when no
    reader ever saw it named.

    DATE. Today's own picks rows are written by this same scan a few lines
    after this runs. A read that did not exclude them would report every
    candidate as having appeared today, which is true and useless, and the
    order of two calls inside one function is a bad place to keep a fact.

    Sessions are counted as DISTINCT DATES ALREADY IN THE TABLE rather than as
    calendar days back, because five calendar days over a long weekend is three
    sessions and over a holiday week is fewer. A calendar window would silently
    shrink in exactly the weeks a reader is least able to remember what ran.
    """
    from core import store
    from morning import scan

    with store.session() as connection:
        store.init(connection)
        connection.execute("DELETE FROM picks")
        rows = [
            # Two live sessions before today, one of them holding AAA twice
            # over, which a DISTINCT date read must not double count.
            ("2026-01-01", "AAA.US", "live"),
            ("2026-01-01", "BBB.US", "live"),
            ("2025-12-31", "AAA.US", "live"),
            # A reconstruction and a hand run on a third date. Neither was ever
            # published, so neither is a prior appearance.
            ("2025-12-30", "AAA.US", "reconstructed"),
            ("2025-12-30", "CCC.US", "test"),
            # Today. Written by this morning's own scan.
            ("2026-01-02", "AAA.US", "live"),
        ]
        for date, ticker, source in rows:
            connection.execute(
                "INSERT INTO picks (date, ticker, source) VALUES (?, ?, ?)",
                (date, ticker, source))
        connection.commit()

    seen = scan.prior_appearances(
        ["AAA.US", "BBB.US", "CCC.US"], "2026-01-02", 5)
    if seen.get("AAA.US") != ["2026-01-01", "2025-12-31"]:
        failures.append(
            f"AAA's prior appearances read {seen.get('AAA.US')}. They are the "
            "two live sessions before today: not today's own row, and not the "
            "reconstruction on 2025-12-30")
    if seen.get("BBB.US") != ["2026-01-01"]:
        failures.append(f"BBB's prior appearances read {seen.get('BBB.US')}")
    if seen.get("CCC.US"):
        failures.append(
            f"CCC has prior appearances {seen.get('CCC.US')}, and its only row "
            "is a hand run nobody ever read")

    # The lookback counts SESSIONS, not calendar days: one session back from
    # today is 2026-01-01 alone, even though 2025-12-31 is two days away.
    one_back = scan.prior_appearances(["AAA.US"], "2026-01-02", 1)
    if one_back.get("AAA.US") != ["2026-01-01"]:
        failures.append(
            f"a one session lookback returned {one_back.get('AAA.US')}, so the "
            "window is counting days rather than recorded sessions")

    with store.session() as connection:
        connection.execute("DELETE FROM picks")
        connection.commit()

    print("  repeats     a prior appearance is a live row on an earlier "
          "recorded session, never a reconstruction, a hand run or today's own")


def claim_a_gap_the_whole_list_shares_is_said_once(failures: list[str]) -> None:
    """Per name when it differs, once when it does not, on the askable set.

    The report only describes what the packet holds, which reads as
    completeness to a reader who cannot see the fields that came back empty.
    The disclaimer names these as SETS, and a set says somebody is short of
    evidence without saying which name in front of them is the one.

    THE SUPPRESSION IS WHAT MAKES IT READABLE and it was learned from output.
    Measured on 2026-09-01, ELEVEN OF THE ELEVEN candidates it could be asked
    of carried rvol_lower_bound, because it is structural: the numerator covers
    07:20 onward and the denominator accumulates from 04:00. Printed per name
    that is the same sentence eleven times, which buries the one missing
    baseline and the four partial windows that actually differed.

    SHARED IS MEASURED OVER THE ASKABLE SET, not over every row, and that is
    the whole subtlety. A name with no RVOL did not answer no to "is your RVOL
    a lower bound", it was never asked. Counting it as a no turns a cause the
    entire measurable list shares into one that only most of it shares, and the
    only alternative is a percentage threshold picked inside a continuum, which
    this project refuses elsewhere for the same reason.
    """
    from morning import analyst, scan

    candidates = [dict(c) for c in _SHAPE_CANDIDATES]
    shared = scan.attach_evidence_missing(candidates)

    if shared["shared_by_all"] != ["rvol_lower_bound"]:
        failures.append(
            f"the shared causes read {shared['shared_by_all']}. Both names "
            "carrying an RVOL carry a lower bound, and the third has no RVOL "
            "to ask the question of, so the lower bound is shared")
    if shared["asked_of"].get("rvol_lower_bound") != 2:
        failures.append(
            f"the shared denominator is {shared['asked_of']}, and the question "
            "could be asked of two of the three")
    for hit in analyst.quantifier_violations(shared["text"]):
        failures.append(
            f"the shared sentence asserts {hit['quantifier']!r} near "
            f"{hit['set_word']!r} and the disclaimer quotes it: "
            f"{shared['text']!r}")

    by_symbol = {c["symbol"]: c["evidence_missing"] for c in candidates}
    if by_symbol["AAA.US"]["causes"]:
        failures.append(
            "AAA carries a per name gap and its only gap is the one the whole "
            f"list shares: {by_symbol['AAA.US']}")
    if by_symbol["AAA.US"]["text"]:
        failures.append(
            "a candidate with nothing specific to it carries a line anyway, "
            "which is what teaches a reader to skip the ones that do: "
            f"{by_symbol['AAA.US']['text']!r}")
    if by_symbol["AAA.US"]["shared_by_all"] != ["rvol_lower_bound"]:
        failures.append(
            "the suppressed cause is not recorded against the name it was "
            f"suppressed for: {by_symbol['AAA.US']}")
    for want in ("catalyst_unchecked", "no_baseline", "window_partial",
                 "fill_untested"):
        if want not in by_symbol["CCC.US"]["causes"]:
            failures.append(
                f"CCC does not carry {want}, and the fixture gives it an "
                f"unchecked feed, no baseline, a late window and no band "
                f"evidence: {by_symbol['CCC.US']['causes']}")
    for hit in analyst.quantifier_violations(by_symbol["CCC.US"]["text"]):
        failures.append(
            f"a per name gap line asserts {hit['quantifier']!r} near "
            f"{hit['set_word']!r}: {by_symbol['CCC.US']['text']!r}")

    # ONE CANDIDATE IS ITS OWN LIST. Suppressing there would leave a lone name
    # with an empty line and the fact nowhere.
    lone = [dict(_SHAPE_CANDIDATES[0])]
    lone_shared = scan.attach_evidence_missing(lone)
    if lone_shared["shared_by_all"]:
        failures.append(
            "a single candidate morning suppressed a cause as shared, so the "
            f"only name in the report carries no line and neither does the "
            f"disclaimer: {lone_shared['shared_by_all']}")
    if "lower bound" not in lone[0]["evidence_missing"]["text"]:
        failures.append(
            "a single candidate's own gap did not reach its line: "
            f"{lone[0]['evidence_missing']['text']!r}")

    # IDEMPOTENT, and the packet depends on it: stamp_all calls this for the
    # attachment and build_packet calls it again for the shared half, so one
    # function stays the only place either answer is worked out. A second call
    # that read the key it wrote rather than the underlying fields would
    # suppress the already suppressed and empty the disclaimer line.
    again = scan.attach_evidence_missing(candidates)
    if again != shared or [c["evidence_missing"] for c in candidates] != [
            by_symbol[c["symbol"]] for c in candidates]:
        failures.append(
            "attach_evidence_missing is not idempotent, and build_packet calls "
            "it a second time to publish the shared block")

    print("  what is not a gap the measurable list shares is said once in the "
          "disclaimer, a gap one name carries is said against that name, and a "
          "name missing nothing carries no line")


def claim_the_instructions_ask_for_the_shape_and_the_absence(
        failures: list[str]) -> None:
    """Both documents quote the new fields rather than describing them.

    The same pairing every supplied sentence in this project needs. Dropping
    the old wording without naming the field leaves the model to invent the
    section; naming the field while an instruction to derive it stands leaves
    two ways to answer and no reason to prefer either.

    The aboutness sentence is checked differently, because it is the one thing
    here Python does not supply: what is asserted is that it is asked for where
    the headline is PRINTED. That placement is the entire safeguard. A reader
    can check "about a peer" against the headline on the line above at a
    glance; the same words in a table three sections away are a claim nobody
    verifies, which is worse than no claim.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    prompt = (config.PROJECT_ROOT / "doc" / "prompt_analyst.md").read_text(
        encoding="utf-8")

    for field in ("list_shape.text.sectors",
                  "list_shape.text.catalyst_classes",
                  "list_shape.text.repeat_appearances",
                  "evidence_missing.text",
                  "evidence_missing_shared.text"):
        for label, document in (("REPORT_TEMPLATE.md", template),
                                ("prompt_analyst.md", prompt)):
            if field not in document:
                failures.append(
                    f"{label} does not name {field}, so the model either "
                    "derives that sentence or omits it")

    # The aboutness sentence belongs under the printed headline. Premarket
    # gappers is the section that prints headline titles; Skips and traps
    # names symbols and reasons and prints no headline text.
    gappers = template.split("## Premarket gappers", 1)
    if len(gappers) != 2:
        failures.append("REPORT_TEMPLATE.md has no Premarket gappers section, "
                        "which is where the headline titles are printed")
    else:
        block = gappers[1].split("\n## ", 1)[0]
        if "about the company" not in block:
            failures.append(
                "the aboutness sentence is not asked for in Premarket gappers, "
                "which is the only section that prints the headline itself. "
                "Asked for anywhere else, the reader cannot check it against "
                "the text it describes")
        if "evidence_missing.text" not in block:
            failures.append(
                "the per name evidence gap line is not asked for in the "
                "section that carries one block per candidate")

    print("  asked for   both documents quote the shape and the absence, and "
          "the aboutness sentence is asked for under the printed headline")


def claim_the_roll_selects_by_the_predicate_it_names(failures: list[str]) -> None:
    """Five filters the template used to make the model perform in prose.

    TEMPLATE_DERIVATIONS T2, T3, T15 and P1. The failure this guards is not
    arithmetic, it is a predicate read the wrong way round or two of them
    conflated, which is invisible in a report that reads fluently. So the
    mixed case puts a different flag on each of three names: a roll that ORs
    them, or that reuses one list for another, cannot pass all five.
    """
    from morning import scan

    expected = {
        "empty": {"rvol_null": [], "window_starts_late": [],
                  "rvol_lower_bound": [], "catalyst_absent": [],
                  "catalyst_unknown": [], "coverage_absent": []},
        "full": {"rvol_null": ["AAA.US"], "window_starts_late": ["AAA.US"],
                 "rvol_lower_bound": ["AAA.US"], "catalyst_absent": ["AAA.US"],
                 "catalyst_unknown": [], "coverage_absent": ["AAA.US"]},
        "mixed": {"rvol_null": ["AAA.US"], "window_starts_late": ["BBB.US"],
                  "rvol_lower_bound": ["BBB.US"], "catalyst_absent": ["BBB.US"],
                  "catalyst_unknown": ["AAA.US"],
                  "coverage_absent": ["AAA.US"]},
    }
    for case, candidates in _ROLL_CASES.items():
        roll = scan.evidence_roll(candidates)
        if roll["candidates_examined"] != len(candidates):
            failures.append(f"the roll examined {roll['candidates_examined']} "
                            f"on the {case} case and was handed {len(candidates)}")
        for key, want in expected[case].items():
            got = [row["symbol"] for row in roll[key]]
            if got != want:
                failures.append(f"the roll's {key} on the {case} case is {got} "
                                f"and the predicate selects {want}")

    # catalyst_found False and catalyst_found None must never land in one list.
    # They are the two states the template has separated since 2026-08-14: a
    # window read and paid nothing against a window never read.
    mixed = scan.evidence_roll(_ROLL_CASES["mixed"])
    overlap = {r["symbol"] for r in mixed["catalyst_absent"]} & {
        r["symbol"] for r in mixed["catalyst_unknown"]}
    if overlap:
        failures.append(f"{sorted(overlap)} is on both catalyst lists, so false "
                        "and null have been folded into one state")
    print("  roll         six predicates selected apart on an empty, a full "
          "and a mixed candidate set")


def claim_the_roll_and_the_fallback_agree_on_partial_evidence(
        failures: list[str]) -> None:
    """Two renderers of one morning must not disagree about whom to distrust.

    analyst.fallback_report marks a candidate's premarket levels "(partial)" on
    `pm_window_starts_late OR NOT collector_covered`. The roll the narrative
    quotes carries those as two lists, because a late window and no window at
    all are different facts that deserve different sentences. Their UNION has
    to be what the fallback marks, or the same morning says one thing when the
    model writes it and another when the plain table does.

    Reachable, not theoretical, and it became more so when the quantifier guard
    was armed on 2026-08-28: the fallback is now what a twice flagged narrative
    degrades to. drop_uncovered splits on `price is not None` rather than on
    collector_covered, and collector_covered is `bool(bars) and on_watchlist`,
    so a name the collector heard that is not on today's watchlist keeps its
    price and survives with collector_covered false. WDAY did on 2026-08-13 and
    AAPL on 2026-08-21, and a subscription list that does not match the
    watchlist is a failure this project has already had.
    """
    from morning import scan

    for case, candidates in _ROLL_CASES.items():
        roll = scan.evidence_roll(candidates)
        union = ({r["symbol"] for r in roll["window_starts_late"]}
                 | {r["symbol"] for r in roll["coverage_absent"]})
        # analyst.fallback_report's own predicate, kept spelled out here rather
        # than imported. Re-deriving it from the function under test is what
        # would make this claim agree with itself instead of with the report.
        fallback = {c["symbol"] for c in candidates
                    if c.get("pm_window_starts_late")
                    or not c.get("collector_covered")}
        if union != fallback:
            failures.append(
                f"on the {case} case the roll names {sorted(union)} as having "
                f"partial or absent premarket evidence and the fallback report "
                f"marks {sorted(fallback)} partial. One morning, two renderers, "
                "two answers.")
    print("  roll v table the narrative and the plain table agree on which "
          "names carry partial or absent premarket evidence")


def claim_the_rolls_own_words_pass_the_quantifier_guard(failures: list[str]) -> None:
    """The roll is quoted word for word, so its words face the same guard.

    The notable movers section already holds this for its reasons and it is the
    same trap: a line reading "no candidate carries a null RVOL" would be built
    by Python, quoted by the model under instruction, and then flagged against
    the model on the quietest morning of the year. In enforcing mode that costs
    a regeneration and then the plain table, for words the packet put there.
    """
    from morning import analyst, scan

    # THE DROPPED LIST IS EXERCISED IN EVERY SHAPE, because it is the one line
    # whose members are not in `candidates` and whose denominator is therefore
    # its own. Empty is the case it was built for: the natural prose for a
    # morning that dropped nobody puts a banned word inside six words of a set
    # word, so before the packet supplied this sentence the model was being
    # asked for one and then flagged for writing it.
    drop_shapes = {
        "none dropped": [],
        "one dropped": [{"symbol": "CCC.US",
                         "reason": "the collector recorded no bars for it"}],
        "two dropped": [
            {"symbol": "CCC.US", "reason": "not on watchlist.json"},
            {"symbol": "DDD.US", "reason": "no bars inside the window"}],
    }

    seen = 0
    for case, candidates in _ROLL_CASES.items():
        for shape, dropped in drop_shapes.items():
            roll = scan.evidence_roll(candidates, dropped)
            # Each line's own denominator, not one shared number. dropped names
            # left the candidate list before the roll saw them, so counting
            # them against candidates_examined would report "1 of 12" on a
            # morning that reached thirteen names and dropped one.
            denominators = {
                "dropped_no_coverage": len(candidates) + len(dropped),
            }
            for key, line in roll["text"].items():
                seen += 1
                for hit in analyst.quantifier_violations(line):
                    failures.append(
                        f"the roll's {key} line on the {case} case with "
                        f"{shape} asserts {hit['quantifier']!r} near "
                        f"{hit['set_word']!r}, and the report quotes it word "
                        f"for word: {line!r}")
                # A line that names nobody must still carry its denominator.
                # "0 of 5" tells a reader the screen examined five and found
                # none; a bare sentence with the names left out does not.
                want = denominators.get(key, len(candidates))
                if f"of {want}" not in line:
                    failures.append(
                        f"the roll's {key} line on the {case} case with "
                        f"{shape} does not carry its denominator, which is "
                        f"{want}: {line!r}")

            # The dropped line names whom it says it names, and nobody else.
            named = roll["text"]["dropped_no_coverage"]
            for row in dropped:
                if row["symbol"].removesuffix(".US") not in named:
                    failures.append(
                        f"the dropped line on {case}/{shape} does not name "
                        f"{row['symbol']}: {named!r}")
            if not dropped and ":" in named:
                failures.append(
                    f"the dropped line names somebody on an empty drop list: "
                    f"{named!r}")
            if [r["symbol"] for r in roll["dropped_no_coverage"]] != [
                    r["symbol"] for r in dropped]:
                failures.append(
                    f"the roll's structured dropped rows on {case}/{shape} are "
                    f"{roll['dropped_no_coverage']} against {dropped}")

    # A ROLL CALLED THE OLD WAY STILL ANSWERS, because the packet is not the
    # only caller and a signature change that breaks a hand run breaks the
    # instrument somebody reaches for when a morning has gone wrong.
    plain = scan.evidence_roll(_ROLL_CASES["mixed"])
    if "0 of" not in plain["text"]["dropped_no_coverage"]:
        failures.append("evidence_roll called without a dropped list does not "
                        "report zero dropped: "
                        f"{plain['text']['dropped_no_coverage']!r}")

    print(f"  roll words   {seen} quoted line(s) across 3 candidate sets and 3 "
          "drop shapes, and not one asserts a quantifier over the screened set")


def claim_the_template_reads_the_roll_rather_than_deriving_it(
        failures: list[str]) -> None:
    """The instructions quote the roll, and no longer ask for the filter.

    Both halves matter. Dropping the old wording without naming the new field
    leaves the model to invent the section; naming the field while the old
    instruction stands leaves it two ways to answer and no reason to prefer
    either. TEMPLATE_DERIVATIONS calls this pattern SUPPLY IN PACKET AND QUOTE,
    and T9 and T10 are the ones that already did it.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    prompt = (config.PROJECT_ROOT / "doc" / "prompt_analyst.md").read_text(
        encoding="utf-8")

    for field in ("evidence_roll.text.rvol_null",
                  "evidence_roll.text.window_starts_late",
                  "evidence_roll.text.rvol_lower_bound",
                  # The dropped line, which the template DESCRIBED for as long
                  # as the packet did not supply it. An instruction reading
                  # "if dropped_no_coverage is not empty, name the symbols"
                  # leaves the empty morning to the model, and the phrasing it
                  # reaches for there is the one the quantifier guard refuses.
                  "evidence_roll.text.dropped_no_coverage",
                  "evidence_roll.text.catalyst_absent",
                  "evidence_roll.text.catalyst_unknown",
                  "evidence_roll.text.thin_baseline"):
        if field not in text:
            failures.append(f"REPORT_TEMPLATE.md does not quote {field}, so the "
                            "model is left to derive that membership again")
    if "evidence_roll" not in prompt:
        failures.append("prompt_analyst.md rule 6a does not name evidence_roll, "
                        "so the prompt and the template disagree about who "
                        "performs the filter")
    if "evidence_roll.text.dropped_no_coverage" not in prompt:
        failures.append(
            "prompt_analyst.md does not tell the model to quote "
            "evidence_roll.text.dropped_no_coverage, so on a morning that "
            "dropped nobody it composes that clause itself and the phrasing it "
            "reaches for is refused by the guard")
    if "score_roll.unscored" not in text:
        failures.append("REPORT_TEMPLATE.md must read score_roll.unscored for "
                        "the unscored names rather than scanning for a null score")
    # The unsigned score caveat has to be QUOTED, not described. The template
    # asked for the sense of score_roll.direction_note for six mornings and
    # got six different sentences, because direction_note writes ABSOLUTE in
    # capitals and rule 8 forbids reproducing that.
    if "score_roll.text.direction" not in text:
        failures.append("REPORT_TEMPLATE.md does not quote "
                        "score_roll.text.direction, so the unsigned score "
                        "caveat is composed by the model again")
    if "score_roll.text.direction" not in prompt:
        failures.append("prompt_analyst.md does not name "
                        "score_roll.text.direction, so the prompt and the "
                        "template disagree about who writes that sentence")
    if 'direction_note says it in words' in text:
        failures.append("REPORT_TEMPLATE.md still tells the model that "
                        "direction_note \"says it in words\", which is the "
                        "instruction that produced six different sentences")

    # And the instruction that asked for the filter has to be GONE, not merely
    # supplemented. These are the exact phrases T2 and T15 were written against.
    for phrase in ("name the candidates whose\npm_rvol is null",
                   "name the candidates whose score is null",
                   "pm_rvol null means unverifiable volume"):
        if phrase in text:
            failures.append("REPORT_TEMPLATE.md still asks the model to filter: "
                            f"{phrase!r}")
    print("  roll quoted  the template and the prompt read the five lists and "
          "ask for none of the five filters")


# ------------------------------------------------------- 11, the thin one

def claim_a_thin_denominator_is_named_and_never_refused(failures: list[str]) -> None:
    """A legal but thin RVOL denominator reaches the reader as a fact.

    The floor at [Baseline] min_baseline_premarket_volume is a seed, and on
    2026-08-28 it was measured for the first time: below 10,000 shares, 15 to
    30 percent of a name's OWN ordinary premarket sessions score above 3 times
    its own median, against 5 percent above 100,000. So a ratio just over the
    floor is not evidence the way the same ratio on a liquid name is, and 25 of
    the 80 RVOLs ever published stood there.

    Three things have to hold together, and the third is the one worth pinning.
    The thin rows are NAMED. The ratio is still published, still carries a
    score, and is not nulled, because refusing it is the two part change the
    floor note refuses to make here: a refused name is rescued onto the float
    rotation bands, and those were fitted on the population the CURRENT floor
    rescues. And a row at or above the thin line is not named, or the sentence
    says nothing.
    """
    from morning import analyst, scan

    candidates = [
        # Just over the floor, and the case that prompted the measurement.
        {"symbol": "THIN.US", "pm_rvol": 316.1,
         "baseline": {"median_volume": 1077.5}, "score": 6.0},
        # Comfortably over the thin line: must NOT be named.
        {"symbol": "DEEP.US", "pm_rvol": 1.84,
         "baseline": {"median_volume": 740086.0}, "score": 7.0},
        # Exactly ON the line, which is the off by one this would hide.
        {"symbol": "EDGE.US", "pm_rvol": 2.0,
         "baseline": {"median_volume": 10000.0}, "score": 5.0},
        # Null RVOL: refused upstream, so it is not a thin ratio, it is no
        # ratio, and naming it here would double count the same name.
        {"symbol": "NULL.US", "pm_rvol": None,
         "baseline": {"median_volume": 12.0}, "score": None},
    ]
    packet = scan.Packet()
    scan._gap_for_thin_baselines(candidates, packet)
    text = " ".join(packet.gaps)

    if "THIN.US" not in text:
        failures.append("a 1,077 share denominator carrying a published RVOL is "
                        "not named in gaps_to_fill, so the report sets it beside "
                        "a 740,086 share one with nothing to tell them apart")
    for quiet in ("DEEP.US", "EDGE.US", "NULL.US"):
        if quiet in text:
            failures.append(f"{quiet} is named as thin. DEEP is 74x the line, "
                            "EDGE sits exactly on it and the test is below, and "
                            "NULL has no ratio to rest on anything")

    # Named, NOT refused. The ratio and the score survive untouched: this gap
    # is disclosure, and turning it into a refusal silently re-fits the float
    # rotation bands onto a population they were not measured on.
    thin = candidates[0]
    if thin["pm_rvol"] != 316.1 or thin["score"] != 6.0:
        failures.append("the thin gap changed the candidate's ratio or score. "
                        "It is disclosure only; refusing here is the two part "
                        "change the floor note declines to make.")

    # It is quoted into the report like every other gap, so it faces the guard.
    for hit in analyst.quantifier_violations(text):
        failures.append(f"the thin denominator gap asserts {hit['quantifier']!r} "
                        f"near {hit['set_word']!r} and the report quotes it")

    # AND IT HAS TO REACH THE REPORT, which for a long time it did not.
    # gaps_to_fill arrives at the reader only through the Summary's "anything
    # in gaps_to_fill that materially weakens this morning's evidence", which
    # is the model's judgement. On 2026-08-31 that judgement went the other
    # way: both of the morning's candidates rested on a denominator under the
    # line, the top scored name drew 2 of its 10 points from an RVOL of 27.01
    # built on a 1,002 share median, and the published report said neither.
    # So the same membership is also a roll list with its own required
    # sentence, which the template quotes word for word.
    roll = scan.evidence_roll(candidates)
    if "thin_baseline" not in roll or "thin_baseline" not in roll["text"]:
        failures.append(
            "evidence_roll carries no thin_baseline list, so the disclosure "
            "reaches the reader only if the model decides gaps_to_fill was "
            "worth quoting. A disclosure that survives on a judgement call is "
            "not a disclosure")
        return
    named = {r["symbol"] for r in roll["thin_baseline"]}
    if named != {"THIN.US"}:
        failures.append(
            f"the roll's thin_baseline names {sorted(named)}, not ['THIN.US']. "
            "DEEP is 74x the line, EDGE sits exactly on it and the test is "
            "below, and NULL has no ratio to rest on anything")
    for row in roll["thin_baseline"]:
        if not row.get("why") or f"{row['median_volume']:,.0f}" not in row["why"]:
            failures.append(
                f"{row['symbol']} carries no per row why naming its own median. "
                "The sentence cannot carry it: the whole point is that one row "
                "is at 1,077 shares and another at 740,086")
    line = roll["text"]["thin_baseline"]
    if "of " not in line or "THIN" not in line:
        failures.append(f"the roll's thin_baseline line does not carry its "
                        f"denominator and its names: {line!r}")
    # The two must not drift: whatever the gap names, the roll names.
    if ("THIN.US" in text) != ("THIN.US" in str(named)):
        failures.append("the gap and the roll disagree about who is thin, and "
                        "two lists of one fact is how they come apart")

    print("  thin denom   a 1,077 share median is named, a 740,086 and a 10,000 "
          "are not, and the ratio it names is still published and scored")


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pmd-gaps-") as raw:
        tmp = Path(raw)
        run_claim(failures, claim_a_refused_run_still_reports_what_it_heard, tmp, failures)
        run_claim(failures, claim_uncounted_is_not_zero, tmp, failures)
        run_claim(failures, claim_replay_is_tagged_and_never_totalled, tmp, failures)
    run_claim(failures, claim_a_failure_today_reaches_the_report, failures)
    run_claim(failures, claim_the_failure_line_stays_readable, failures)
    run_claim(failures, claim_a_lower_bound_reaches_gaps_to_fill, failures)
    run_claim(failures, claim_the_template_does_not_ask_for_the_false_sentences, failures)
    run_claim(failures, claim_the_roll_selects_by_the_predicate_it_names, failures)
    run_claim(failures, claim_the_list_shape_is_counted_and_never_derived, failures)
    run_claim(failures, claim_a_prior_outcome_is_read_off_the_right_session, failures)
    run_claim(failures, claim_the_composition_carries_direction_and_a_scale, failures)
    run_claim(failures, claim_a_repeat_appearance_reads_only_live_rows_before_today, failures)
    run_claim(failures, claim_a_gap_the_whole_list_shares_is_said_once, failures)
    run_claim(failures, claim_the_instructions_ask_for_the_shape_and_the_absence, failures)
    run_claim(failures, claim_the_roll_and_the_fallback_agree_on_partial_evidence, failures)
    run_claim(failures, claim_the_rolls_own_words_pass_the_quantifier_guard, failures)
    run_claim(failures, claim_the_template_reads_the_roll_rather_than_deriving_it, failures)
    run_claim(failures, claim_a_thin_denominator_is_named_and_never_refused, failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  a refused run, an uncounted run, a replayed print, a step that "
          "failed this morning and an understating ratio all reach the reader")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
