"""Read, judge and measure the analyst quantifier guard's flags.

The guard in morning/analyst.py rejects a report that asserts a quantifier over
the candidate set. It is deliberately blunt, so some of what it catches is
noise, and the question that matters over months is HOW MUCH.

That question is answered here from data rather than from memory. When the
guard shipped on 2026-08-18 its false positive rate was eyeballed at one in six
across a single afternoon's reports. That is an impression, and this project has
a history of guards whose failures were rationalised away one at a time until
nobody could say whether they still worked. So every flag is written down with
room for a verdict, and the rate below is counted rather than recalled.

Read the pending list, judge each one, and after a month tune the word list in
analyst.py on what this prints.

    python -m ops.quantifier_flags
    python -m ops.quantifier_flags --mark 3 false-positive --note "each was about score components"

Marking is append safe: the file is rewritten from the records it already holds,
with one field changed, and a flag is never deleted. A wrong verdict is fixed by
marking it again.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from core import files
from core import ettime
from morning import analyst

# Public: monitor_jobs.py reads the same two words to tell a judged flag
# from a pending one. A second copy of this tuple over there would drift.
VERDICTS = ("true-positive", "false-positive")

# How to invoke this module, as a line that WORKS when pasted into cmd from
# the project root. Every message telling a human to judge a flag is built
# from this, because the bare "python -m ops.quantifier_flags" those messages
# carried fails two ways at once: the system python has none of this
# project's dependencies, and without PYTHONPATH the ops package is not
# importable at all. The owner hit exactly that on 2026-08-25, off a line the
# WATCHDOG had printed into its own log as the thing to do next. An
# instruction that does not run is the same defect as a field nobody reads,
# one step further out.
RUN_PREFIX = (r"set PYTHONPATH=%CD%\src && "
              r".venv\Scripts\python.exe -m ops.quantifier_flags")


def load_flags() -> list[dict[str, Any]]:
    """Every flag ever raised, oldest first. Missing file means none yet."""
    path = analyst.flag_log_path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def rate(flags: list[dict[str, Any]]) -> dict[str, Any]:
    """The measured false positive rate, what it cost, and how much is judged.

    judged is the denominator that matters. A rate over three judged flags is
    not a rate, and printing it beside the count is what stops it being quoted
    as though it were.

    by_outcome is the second measurement and answers a different question: not
    how often the guard is wrong, but how much being wrong costs. A flag the
    regeneration cleared cost the morning nothing. A flag that survived the
    regeneration cost it its narrative. Tuning the word list needs both, since
    a noisy word that regenerates away is a nuisance and a noisy word that
    reaches the fallback is a bill. Flags written before 2026-08-18 carry no
    outcome and count as unrecorded rather than as either.
    """
    judged = [f for f in flags if f.get("disposition") in VERDICTS]
    by_outcome: dict[str, int] = {}
    for flag in flags:
        key = str(flag.get("outcome") or "unrecorded")
        by_outcome[key] = by_outcome.get(key, 0) + 1
    false = [f for f in judged if f["disposition"] == "false-positive"]
    by_word: dict[str, dict[str, int]] = {}
    for flag in judged:
        row = by_word.setdefault(flag.get("quantifier") or "?",
                                 {"judged": 0, "false": 0})
        row["judged"] += 1
        if flag["disposition"] == "false-positive":
            row["false"] += 1
    return {
        "raised": len(flags),
        "judged": len(judged),
        "pending": len(flags) - len(judged),
        "false_positives": len(false),
        "false_positive_rate": (len(false) / len(judged)) if judged else None,
        "by_quantifier": by_word,
        "by_outcome": by_outcome,
    }


def mark(flag_id: int, verdict: str, note: str | None) -> int:
    path = analyst.flag_log_path()
    flags = load_flags()
    if not any(f.get("id") == flag_id for f in flags):
        print(f"quantifier_flags: no flag with id {flag_id}")
        return 1
    for flag in flags:
        if flag.get("id") == flag_id:
            flag["disposition"] = verdict
            flag["disposition_note"] = note
            flag["disposition_at"] = ettime.stamp(ettime.now_et())
    body = "".join(json.dumps(f, separators=(",", ":")) + "\n" for f in flags)
    # This was the seventh hand rolled copy of write to a temp sibling then
    # replace, and the only one with no retry and no cleanup of the sibling
    # a crash leaves behind.
    files.write_text_atomically(path, body,
                                attempts=files.ATTEMPTS, retry_s=files.RETRY_S)
    print(f"quantifier_flags: flag {flag_id} marked {verdict}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge and measure quantifier guard flags.")
    parser.add_argument("--mark", type=int, metavar="ID", default=None,
                        help="Record a verdict against one flag id.")
    parser.add_argument("verdict", nargs="?", choices=VERDICTS, default=None)
    parser.add_argument("--note", default=None, help="Why, in a few words.")
    parser.add_argument("--pending", action="store_true",
                        help="List only the flags nobody has judged yet. The "
                             "watchdog counts these and calls a week of them a "
                             "backlog, so this is the list it is pointing at.")
    args = parser.parse_args(argv)

    if args.mark is not None:
        if not args.verdict:
            print(f"quantifier_flags: --mark needs a verdict, one of {', '.join(VERDICTS)}")
            return 1
        return mark(args.mark, args.verdict, args.note)

    flags = load_flags()
    if not flags:
        print(f"quantifier_flags: no flags recorded yet in {analyst.flag_log_path()}")
        return 0

    shown = [f for f in flags if f.get("disposition") not in VERDICTS] if args.pending else flags
    for flag in shown:
        verdict = flag.get("disposition") or "PENDING"
        print(f"  {flag.get('id'):>4}  {flag.get('session')}  line {flag.get('line')}  "
              f"{flag.get('quantifier')!r} near {flag.get('set_word')!r}  [{verdict}]")
        print(f"        {flag.get('sentence')}")
        if flag.get("disposition_note"):
            print(f"        note: {flag['disposition_note']}")

    summary = rate(flags)
    print("")
    print(f"  raised {summary['raised']}, judged {summary['judged']}, "
          f"pending {summary['pending']}")
    outcomes = summary["by_outcome"]
    print(f"  cost: {outcomes.get('warned', 0)} published under warn mode, "
          f"{outcomes.get('regenerated', 0)} cleared by a regeneration, "
          f"{outcomes.get('fell_back', 0)} took the morning's narrative with them"
          + (f", {outcomes['unrecorded']} raised before outcomes were recorded"
             if outcomes.get("unrecorded") else ""))
    if outcomes.get("warned") and not outcomes.get("fell_back"):
        print("  Every flag so far was published rather than acted on, which is "
              "what warn mode means. See CRITERIA analyst.quantifier_guard for "
              "the three things that have to be true before it enforces.")
    if summary["false_positive_rate"] is None:
        print("  false positive rate: NOT MEASURABLE, nothing judged yet. "
              "The rate is not an estimate until this says otherwise.")
    else:
        print(f"  false positive rate: {summary['false_positive_rate']:.1%} "
              f"of {summary['judged']} judged")
        for word, row in sorted(summary["by_quantifier"].items()):
            print(f"    {word:<10} {row['false']} of {row['judged']} judged were false")
    if summary["judged"] < 20:
        print("  Fewer than 20 judged. Tune the word list on a month of these, "
              "not on this line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
