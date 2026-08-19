"""Regression test for the suite's own isolation check.

The tree check photographs every path under the working tree before and after
the suite and fails on anything that moved. That is what stops a test with a
hardcoded absolute path writing into the real runs/, data/ or site/, and it has
caught exactly that more than once.

It has one exemption, added 2026-08-19, and this module exists because an
exemption nobody tests is a hole nobody sees. The scheduled meter sampler
appends to logs/ from outside the suite at :00 and :30 every hour, so a run
straddling one of those instants failed on a path the suite never touched. That
is an intermittent isolation failure, which is worse than a reproducible one:
it cannot be chased, so it gets rationalised away.

The exemption is deliberately NOT "logs/ may change". A test writing there
would pollute the meter trail and data/quantifier-flags.jsonl is the telemetry
the analyst guard's word list is about to be tuned on, so blinding the check to
that directory would blind it to the one contamination that would corrupt the
measurement. What is exempt is the sampler's behaviour: the two files it writes
by name, growing by a pure append, with the appended bytes parsing as what that
file holds. Every one of those three conditions is required, and each of the
claims below removes exactly one of them and asserts the change is refused.

One looseness, stated rather than left to be discovered. The trail file is
JSONL and every appended row has to parse and carry the four keys the meter
trail writes, which is tight. The stdout file is a shell redirect of the
sampler's own printing, so its grammar is by line prefix: the sampler's own
lines, the EODHD call report header, and that report's indented rows. An
indented line of anything therefore passes. Tightening it to require a
"sampler: " line in every appended chunk was considered and rejected, because a
snapshot taken between two of the sampler's own flushes would then see a chunk
of report rows with no such line and fail, which trades this intermittent for a
rarer one. Reaching the looseness requires a test to append indented text to a
file called meter-sampler.log, having first left every prior byte intact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests import conftest

# One row of the meter trail, shaped as ops/job_status.record_meter writes it.
ROW = {
    "at": "2026-08-19T00:00:01-04:00", "quota_day": "2026-08-19",
    "source": "sampler", "step": "sampler", "when": "tick", "job": "manual",
    "api_requests": 1957, "daily_limit": 100000, "remaining": 98043,
    "delta_since_previous": 0, "error": None,
}
# One tick of the sampler's stdout, as tasks/job_meter_sampler.bat redirects it.
TICK = (
    "sampler: meter at tick 50,506 of 100,000 used, 49,494 remaining, +0\n"
    "\n"
    "EODHD call report\n"
    "  total http calls   1\n"
    "  quota day          2026-08-19 (the shared counter resets 00:00 UTC)\n"
)


def row(**overrides: object) -> str:
    return json.dumps({**ROW, **overrides}, separators=(",", ":")) + "\n"


def build(tmp: Path) -> Path:
    """A miniature tree with a logs/ directory in it, and nothing else moving."""
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "meter-2026-08-19.log").write_text(row() + row(), encoding="utf-8")
    (logs / "meter-sampler.log").write_text(TICK, encoding="utf-8")
    (logs / "morning-chain-2026-08-19.log").write_text(
        "===== scan started =====\n", encoding="utf-8")
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    (tmp / "data" / "quantifier-flags.jsonl").write_text(
        json.dumps({"id": 1, "disposition": None}) + "\n", encoding="utf-8")
    return logs


def changes(tmp: Path, logs: Path, mutate) -> list[str]:
    """Snapshot, apply mutate(), snapshot again, and report what the check says."""
    before = conftest.snapshot_tree(root=tmp, logs_root=logs)
    mutate()
    after = conftest.snapshot_tree(root=tmp, logs_root=logs)
    return conftest.differences(before, after, logs_root=logs)


def claim_a_sampler_tick_is_not_a_breach(tmp: Path, failures: list[str]) -> None:
    """A run straddling :00 or :30 passes. This is the whole point of it.

    Both files the sampler writes move on every tick, so both have to be
    covered or the exemption buys nothing.
    """
    logs = build(tmp)

    def tick() -> None:
        with (logs / "meter-2026-08-19.log").open("a", encoding="utf-8") as handle:
            handle.write(row(at="2026-08-19T00:30:01-04:00"))
        with (logs / "meter-sampler.log").open("a", encoding="utf-8") as handle:
            handle.write(TICK)

    found = changes(tmp, logs, tick)
    if found:
        failures.append(f"a scheduled sampler tick was called an isolation "
                        f"breach: {found}")
    else:
        print("  claim tick     a sampler append to both of its files passes")


def claim_utc_midnight_is_handled(tmp: Path, failures: list[str]) -> None:
    """The new dated trail at 00:00 UTC is a CREATION, not an append.

    Left alone it would fail on the one night a month somebody runs the suite
    late, which is exactly the frequency at which a failure gets waved through.
    """
    logs = build(tmp)
    found = changes(tmp, logs, lambda: (logs / "meter-2026-08-20.log").write_text(
        row(quota_day="2026-08-20"), encoding="utf-8"))
    if found:
        failures.append(f"the sampler starting the next day's trail was called a "
                        f"breach: {found}")
    # ...and a created file under logs/ that is NOT a dated sampler trail is
    # still a breach, or the midnight case would be a hole shaped like a date.
    logs = build(tmp)
    found = changes(tmp, logs, lambda: (logs / "discover-2026-08-20.log").write_text(
        row(), encoding="utf-8"))
    if not found:
        failures.append("a test creating a non sampler file under logs/ passed, so "
                        "the midnight exemption is really a directory exemption")
    if not failures:
        print("  claim midnight a new dated trail passes and a new job log does not")


def claim_only_a_pure_append_passes(tmp: Path, failures: list[str]) -> None:
    """Condition two on its own. Truncation and rewrite are not appends.

    A same length overwrite is the interesting one: it leaves mtime moved and
    size identical, which is the shape the check's own docstring warns reads
    like an external toucher. The digest is what tells them apart.
    """
    for label, mutate in (
        ("truncation", lambda logs: (logs / "meter-2026-08-19.log").write_text(
            row(), encoding="utf-8")),
        ("same length rewrite", lambda logs: (logs / "meter-2026-08-19.log").write_text(
            row(step="tampered") + row(), encoding="utf-8")),
        ("prefix rewrite plus append", lambda logs: (logs / "meter-2026-08-19.log").write_text(
            row(step="tampered") + row() + row(), encoding="utf-8")),
    ):
        logs = build(tmp)
        found = changes(tmp, logs, lambda: mutate(logs))
        if not found:
            failures.append(f"a {label} of the sampler trail passed as an append")
    if not failures:
        print("  claim append   truncation, a same length rewrite and a rewritten "
              "prefix are all refused")


def claim_the_appended_bytes_must_parse(tmp: Path, failures: list[str]) -> None:
    """Condition three on its own. The right filename is not enough.

    Without this, any test could reach the exemption by choosing its filename,
    which would make the exemption a naming convention rather than a check.
    """
    cases = {
        "prose appended to the trail": (
            "meter-2026-08-19.log", "a test wrote this line\n"),
        "a row missing the trail keys": (
            "meter-2026-08-19.log", json.dumps({"hello": "world"}) + "\n"),
        "unparseable json": (
            "meter-2026-08-19.log", "{not json at all}\n"),
        "prose appended to the stdout log": (
            "meter-sampler.log", "a test wrote this line\n"),
    }
    for label, (name, payload) in cases.items():
        logs = build(tmp)
        target = logs / name
        original = target.read_bytes()

        def mutate() -> None:
            target.write_bytes(original + payload.encode("utf-8"))

        found = changes(tmp, logs, mutate)
        if not found:
            failures.append(f"{label} passed the sampler exemption")

    # A touch that adds no bytes, with the mtime moved explicitly. Rewriting
    # the same bytes and hoping the clock ticks is not a test, it is a race:
    # this claim passed alone and failed inside the full suite, because there
    # the mtime happened to land on the same value and the snapshot saw no
    # change at all rather than a change the exemption refused.
    import os
    logs = build(tmp)
    target = logs / "meter-2026-08-19.log"
    stamp = target.stat().st_mtime

    def touch() -> None:
        os.utime(target, (stamp + 120, stamp + 120))

    found = changes(tmp, logs, touch)
    if not found:
        failures.append("an mtime touch adding no bytes passed the sampler "
                        "exemption, so an append is not actually required")
    if not failures:
        print(f"  claim parse    {len(cases)} appends the sampler would not have "
              "written are refused, and so is an mtime touch that appends nothing")


def claim_a_test_writing_to_logs_still_fails(tmp: Path, failures: list[str]) -> None:
    """The reason logs/ was not exempted wholesale.

    Three writes a test could plausibly make, none of them the sampler, and the
    last is the one that mattered: data/quantifier-flags.jsonl is the telemetry
    the analyst word list is about to be tuned on, and a check that stopped
    watching it would let a test corrupt the measurement silently.
    """
    cases = {
        "a job log under logs/": lambda logs: (
            logs / "morning-chain-2026-08-19.log").write_text(
                "===== scan started =====\n===== a test wrote this =====\n",
                encoding="utf-8"),
        "a new file under logs/": lambda logs: (
            logs / "sandbox-escape-probe.txt").write_text("escaped\n", encoding="utf-8"),
        "the quantifier flag log": lambda logs: (
            logs.parent / "data" / "quantifier-flags.jsonl").write_text(
                json.dumps({"id": 1, "disposition": "false-positive"}) + "\n",
                encoding="utf-8"),
    }
    for label, mutate in cases.items():
        logs = build(tmp)
        found = changes(tmp, logs, lambda: mutate(logs))
        if not found:
            failures.append(f"a test writing {label} was not caught")
    if not failures:
        print("  claim escape   a job log, a new file under logs/ and the "
              "quantifier flag log are all still caught")


def claim_the_real_logs_are_watched_by_default(failures: list[str]) -> None:
    """The exemption is anchored to the REAL logs directory, not to a name.

    conftest redirects config.LOGS_DIR into the sandbox for the duration of the
    suite. If the exemption read config.LOGS_DIR at check time it would be
    pointing at a temporary directory and would exempt nothing, which would
    look exactly like it working until the next sampler tick.
    """
    from core import config

    if conftest.REAL_LOGS != config.PROJECT_ROOT / "logs":
        failures.append(f"REAL_LOGS is not the repository's logs directory: "
                        f"{conftest.REAL_LOGS}")
    inside = conftest.REAL_LOGS / "meter-2026-08-19.log"
    outside = config.PROJECT_ROOT / "meter-2026-08-19.log"
    if conftest._sampler_kind(inside, conftest.REAL_LOGS) != "trail":
        failures.append("the sampler trail inside the real logs directory is "
                        "not recognised")
    if conftest._sampler_kind(outside, conftest.REAL_LOGS) is not None:
        failures.append("a sampler shaped filename OUTSIDE logs/ is exempt, so "
                        "the exemption travels with the name rather than the place")
    if not failures:
        print("  claim anchor   the exemption is bound to the real logs directory "
              "and does not travel with the filename")


def main() -> int:
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pmd-sandbox-") as raw:
        for claim in (claim_a_sampler_tick_is_not_a_breach,
                      claim_utc_midnight_is_handled,
                      claim_only_a_pure_append_passes,
                      claim_the_appended_bytes_must_parse,
                      claim_a_test_writing_to_logs_still_fails):
            before = len(failures)
            claim(Path(raw) / claim.__name__, failures)
            del before
    claim_the_real_logs_are_watched_by_default(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  the scheduled sampler may append to its own two log files and "
          "nothing else about logs/ or data/ has stopped being watched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
