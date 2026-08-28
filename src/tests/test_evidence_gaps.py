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

import json
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
         "catalyst_found": True},
    ],
    "full": [
        {"symbol": "AAA.US", "pm_rvol": None, "pm_rvol_reason": "why",
         "pm_window_starts_late": True,
         "pm_rvol_basis": {"is_lower_bound": True}, "catalyst_found": False,
         "catalyst_why": "checked and paid nothing"},
    ],
    "mixed": [
        {"symbol": "AAA.US", "pm_rvol": None, "pm_rvol_reason": "why",
         "catalyst_found": None, "catalyst_why": "the feed was never read"},
        {"symbol": "BBB.US", "pm_rvol": 2.0, "pm_window_starts_late": True,
         "pm_rvol_basis": {"is_lower_bound": True}, "catalyst_found": False},
        {"symbol": "CCC.US", "pm_rvol": 3.0, "pm_rvol_basis": {},
         "catalyst_found": True},
    ],
}


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
                  "catalyst_unknown": []},
        "full": {"rvol_null": ["AAA.US"], "window_starts_late": ["AAA.US"],
                 "rvol_lower_bound": ["AAA.US"], "catalyst_absent": ["AAA.US"],
                 "catalyst_unknown": []},
        "mixed": {"rvol_null": ["AAA.US"], "window_starts_late": ["BBB.US"],
                  "rvol_lower_bound": ["BBB.US"], "catalyst_absent": ["BBB.US"],
                  "catalyst_unknown": ["AAA.US"]},
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
    print("  roll         five predicates selected apart on an empty, a full "
          "and a mixed candidate set")


def claim_the_rolls_own_words_pass_the_quantifier_guard(failures: list[str]) -> None:
    """The roll is quoted word for word, so its words face the same guard.

    The notable movers section already holds this for its reasons and it is the
    same trap: a line reading "no candidate carries a null RVOL" would be built
    by Python, quoted by the model under instruction, and then flagged against
    the model on the quietest morning of the year. In enforcing mode that costs
    a regeneration and then the plain table, for words the packet put there.
    """
    from morning import analyst, scan

    seen = 0
    for case, candidates in _ROLL_CASES.items():
        for key, text in scan.evidence_roll(candidates)["text"].items():
            seen += 1
            for hit in analyst.quantifier_violations(text):
                failures.append(
                    f"the roll's {key} line on the {case} case asserts "
                    f"{hit['quantifier']!r} near {hit['set_word']!r}, and the "
                    f"report quotes it word for word: {text!r}")
            # A line that names nobody must still carry its denominator. "0 of
            # 5" tells a reader the screen examined five and found none; a bare
            # sentence with the names left out does not.
            if f"of {len(candidates)}" not in text:
                failures.append(f"the roll's {key} line on the {case} case does "
                                f"not carry its denominator: {text!r}")
    print(f"  roll words   {seen} quoted line(s) across 3 candidate sets, and "
          "not one asserts a quantifier over the screened set")


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
                  "evidence_roll.text.catalyst_absent",
                  "evidence_roll.text.catalyst_unknown"):
        if field not in text:
            failures.append(f"REPORT_TEMPLATE.md does not quote {field}, so the "
                            "model is left to derive that membership again")
    if "evidence_roll" not in prompt:
        failures.append("prompt_analyst.md rule 6 does not name evidence_roll, "
                        "so the prompt and the template disagree about who "
                        "performs the filter")
    if "score_roll.unscored" not in text:
        failures.append("REPORT_TEMPLATE.md must read score_roll.unscored for "
                        "the unscored names rather than scanning for a null score")

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


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pmd-gaps-") as raw:
        tmp = Path(raw)
        claim_a_refused_run_still_reports_what_it_heard(tmp, failures)
        claim_uncounted_is_not_zero(tmp, failures)
        claim_replay_is_tagged_and_never_totalled(tmp, failures)
    claim_a_failure_today_reaches_the_report(failures)
    claim_the_failure_line_stays_readable(failures)
    claim_a_lower_bound_reaches_gaps_to_fill(failures)
    claim_the_template_does_not_ask_for_the_false_sentences(failures)
    claim_the_roll_selects_by_the_predicate_it_names(failures)
    claim_the_rolls_own_words_pass_the_quantifier_guard(failures)
    claim_the_template_reads_the_roll_rather_than_deriving_it(failures)

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
