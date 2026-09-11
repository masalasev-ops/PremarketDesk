"""Run the whole suite inside the sandbox, and prove it stayed inside.

Two guarantees, and the second is the one that matters. The sandbox redirects
every writable root a test could reach through config, which stops the ordinary
mistake. The tree check catches the extraordinary one: a test that hardcodes an
absolute path cannot be redirected, so the whole working tree is photographed
before and after, and anything that changes outside a short allowlist fails the
run.

The check used to name the roots it watched and gained one per escape, most
recently site/ when build_archive was caught rewriting the published archive
from inside the sandbox. It is inverted now: everything under the repository is
guarded and the allowlist is the exception, so there is no next root to forget.

Set PYTHONPATH to src/ first, the way every .bat does. src/ is the import root,
so running this file by its path puts src/tests on sys.path instead and the
`from tests import conftest` below fails before the suite starts.

  python -m tests.run_tests                         the suite, sandboxed and checked
  python -m tests.run_tests --prove-check           write to the real runs/, to show
                                                    the check catches it. FAILs.
  python -m tests.run_tests --prove-check-outside   write to tasks/, which no version
                                                    of the enumerated check ever
                                                    watched. FAILs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import sys
import time
import traceback
from typing import Any

from tests import conftest

# The wall clock this suite is expected to stay under, in seconds. Not a
# threshold anything fails on and deliberately not in CRITERIA.md: that file
# holds numbers the MARKET decisions read, and how long a test run takes is a
# fact about this machine. Eight minutes leaves headroom under the ten a CI
# step is usually given.
BUDGET_SECONDS = 8 * 60

SUITE = (
    "tests.test_store",
    "tests.test_scrub",
    "tests.test_containment",
    "tests.test_vintage",
    "tests.test_repricing",
    "tests.test_pool",
    "tests.test_backtest",
    "tests.test_txn_guard",
    "tests.test_midday",
    "tests.test_entrypoints",
    "tests.test_publish",
    "tests.test_sandbox",
    "tests.test_evidence_gaps",
    "tests.test_notable",
    "tests.test_regressions",
)


def _misbehave() -> int:
    """A test that reaches around the sandbox, to prove the check is real."""
    target = conftest.REAL_RUNS / "sandbox-escape-probe.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("this test wrote to the real runs directory\n", encoding="utf-8")
    print(f"  misbehaving test wrote {target}")
    return 0


def _misbehave_outside() -> int:
    """A write to a root the enumerated check never watched.

    tasks/ is in the repository, is written by nothing at runtime, and was
    outside every version of the old check. If the tree-wide photograph is
    real, this is caught; if it is still a list of roots in disguise, this
    passes and says so.
    """
    target = conftest.TREE_ROOT / "tasks" / "sandbox-escape-probe.bat"
    target.write_text("rem this test wrote outside the old enumerated roots\n",
                      encoding="utf-8")
    print(f"  misbehaving test wrote {target}")
    return 0


# The time of day every frozen run uses. Held constant across the sweep so the
# only thing varying between runs is the calendar day: a suite that fails on
# some days and not others is day dependent, and one that fails on all six is
# time dependent or simply broken at this hour, which the matrix tells apart.
FREEZE_HHMM = (9, 0)


def _freeze_clock(day: str) -> str:
    """Pin the ET date so a day dependent assertion shows itself.

    The clock is SHIFTED, not stopped. A truly frozen clock deadlocks the
    project: `run_websocket` spins on `while ettime.now_et() < stop_at`, and a
    now() that never advances never leaves that loop. The first attempt at this
    sweep hung there and produced a zero byte log.

    So time runs forward from the chosen hour at real speed. The date is what
    was asked for, every wait loop still terminates, and the only thing varying
    between runs of the sweep is the calendar day.

    Patches the module rather than adding an environment variable, because the
    shipped code must not grow a way to lie about the date. Nothing in src/
    binds these functions directly (`from core.ettime import now_et`), so
    replacing them on the module reaches every caller.
    """
    from core import ettime

    base = ettime.at_hm(ettime.parse_date(day), FREEZE_HHMM)
    origin = time.monotonic()

    def now_et() -> dt.datetime:
        return base + dt.timedelta(seconds=time.monotonic() - origin)

    ettime.now_et = now_et
    ettime.today_et = lambda: now_et().date()
    ettime.today_str = lambda: now_et().date().isoformat()
    return f"{base.isoformat()} ({base.strftime('%A')}), running forward from there"


def _restamp_universe() -> None:
    """Age the universe fixture relative to the frozen clock, not to 2026-08-13.

    universe.json carries a fixed generated_at, and CRITERIA [universe]
    max_age_days refuses anything older than ten days. Freezing the clock more
    than ten days from that stamp therefore fails two suites for a reason that
    has nothing to do with the day being tested: a Monday holiday 25 days out
    and a plain Tuesday 26 days out fail identically, while a Friday 8 days out
    passes.

    That made the holiday case untestable, since every holiday in the cached
    exchange calendar is more than ten days from the fixture. Restamping to one
    day before the frozen clock removes the distance variable and leaves the
    calendar as the only thing changing.

    Writes to the sandbox copy, because config.DATA_DIR is already redirected
    by the time this runs. The real fixture is never touched.
    """
    from core import config, ettime

    path = config.DATA_DIR / "universe.json"
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    was = payload.get("generated_at")
    payload["generated_at"] = ettime.stamp(ettime.now_et() - dt.timedelta(days=1))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"run_tests: universe.json restamped {was} -> {payload['generated_at']}, "
          "so the frozen day is the only variable")


def _live_claims(module: Any) -> list[str]:
    """Claims in a module marked live by name, which is the whole marking.

    A claim that must reach the vendor is named `claim_live_...` or `..._live`,
    so the marking is visible in the source, in this listing and in the failure
    output, rather than living in a decorator or a registry someone has to know
    to consult. The claim itself is responsible for standing down when
    conftest.live_allowed() is false; this only finds and reports them, so a
    live claim cannot sit in the suite unnoticed.

    Matched on those two exact shapes rather than on the substring 'live',
    which caught `claim_deliver` on the first run of this function. A marking
    convention that silently captures an unrelated claim is worse than none:
    it would have reported a hermetic claim as skipped and nobody would have
    run it again.
    """
    return sorted(
        f"{module.__name__}.{name}"
        for name in dir(module)
        if (name.startswith("claim_live_") or name.endswith("_live"))
        and callable(getattr(module, name))
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the suite under the sandbox.")
    parser.add_argument("--freeze", metavar="YYYY-MM-DD",
                        help="Freeze the ET clock to "
                             f"{FREEZE_HHMM[0]:02d}:{FREEZE_HHMM[1]:02d} on that "
                             "date, so day dependent assertions can be found.")
    parser.add_argument("--prove-check", action="store_true",
                        help="Append a test that writes to the real runs/, to "
                             "demonstrate the tree check catches it.")
    parser.add_argument("--prove-check-outside", action="store_true",
                        help="Append a test that writes to tasks/, a root no "
                             "version of the old enumerated check watched.")
    parser.add_argument("--only", action="append", default=[],
                        help="Run only these modules, repeatable.")
    parser.add_argument("--live", action="store_true",
                        help="Allow the network and run claims marked live. OFF by "
                             "default: the suite is hermetic, and a claim that "
                             "reaches the vendor decides its result on someone "
                             "else's account state rather than on this code.")
    args = parser.parse_args(argv)

    modules = args.only or list(SUITE)
    conftest.ALLOW_LIVE = bool(args.live)
    if args.live:
        print("run_tests: --live, the network is NOT blocked and live claims will "
              "run. Results now depend on the shared account and the vendor.")
    else:
        print("run_tests: the network is blocked and the quota meter reads a fixed "
              f"{conftest.HEALTHY_METER['dailyRateLimit'] - conftest.HEALTHY_METER['apiRequests']:,} "
              "remaining. Live claims are skipped; pass --live to run them.")
    if args.freeze:
        print(f"run_tests: clock frozen to {_freeze_clock(args.freeze)}")

    # BEFORE the photograph, because it touches only TEMP and the photograph is
    # of the working tree, and because a run that is about to copy data/ into a
    # new sandbox should first give back the ones its predecessors abandoned. A
    # killed run cannot clean up after itself, so its successor does it.
    swept, freed, stuck = conftest.sweep_stale_sandboxes()
    if swept:
        print(f"run_tests: swept {swept} abandoned sandbox(es), "
              f"{freed / 1024 / 1024:,.0f} MB, left by runs that ended before "
              "their cleanup could run")
    if stuck:
        print(f"run_tests: {len(stuck)} abandoned sandbox(es) would not delete: "
              f"{', '.join(stuck)}")

    before = conftest.snapshot_tree()
    enumerated = len([
        path for path in before
        if path.startswith((str(conftest.REAL_RUNS), str(conftest.REAL_DATA),
                            str(conftest.REAL_SITE)))
    ])
    print(f"run_tests: {len(before)} paths under the working tree before, of which "
          f"{enumerated} were what the enumerated check watched. The other "
          f"{len(before) - enumerated} were the exposure.")

    failures: list[str] = []
    started = time.monotonic()
    took: list[tuple[float, str]] = []
    with conftest.activate() as sandbox:
        print(f"run_tests: sandbox at {sandbox}")
        if args.freeze:
            _restamp_universe()
        skipped_live: list[str] = []
        for name in modules:
            module = importlib.import_module(name)
            importlib.reload(module)
            skipped_live.extend(_live_claims(module))
            module_started = time.monotonic()
            try:
                code = module.main()
            except Exception:
                traceback.print_exc()
                code = 1
            elapsed = time.monotonic() - module_started
            took.append((elapsed, name))
            status = "ok" if code == 0 else f"EXIT {code}"
            # THE CLOCK IS PRINTED BECAUSE IT CREPT ONCE WITHOUT ANYONE
            # CHOOSING IT. On 2026-09-05 the 240 session backtest cache was
            # refetched, activate() started copying 701 MB of rows no claim
            # reads, and 90 activations turned a four minute suite into an
            # eleven minute one with not one test having changed. Nothing in
            # the output said so, and the first symptom was a timeout. A
            # number nobody sees is a budget nobody keeps.
            print(f"run_tests: {name:<18} {status}  {elapsed:6.1f}s")
            if code != 0:
                failures.append(name)
        if args.prove_check:
            _misbehave()
        if args.prove_check_outside:
            _misbehave_outside()

    after = conftest.snapshot_tree()
    changes = conftest.differences(before, after)
    print(f"run_tests: {len(after)} paths after")

    total = time.monotonic() - started
    slowest = ", ".join(f"{name.split('.')[-1]} {secs:.0f}s"
                        for secs, name in sorted(took, reverse=True)[:3])
    print(f"run_tests: {total / 60:.1f} minutes, slowest {slowest}")
    if total > BUDGET_SECONDS:
        # A WARNING AND NOT A FAILURE, because the number this compares against
        # is one machine's and a slower one is not a broken suite. It is here
        # so the creep is announced the first time rather than discovered by a
        # timeout, and so anyone wiring this into CI has a figure to set a
        # timeout from.
        print(f"run_tests: SLOW, that is over the {BUDGET_SECONDS / 60:.0f} minute "
              "budget in BUDGET_SECONDS. Profile before adding claims: the last "
              "time this moved it was activate() copying a directory no claim "
              "reads, not the tests getting bigger.")

    if changes:
        print(f"run_tests: FAILED, the suite changed {len(changes)} path(s) under the "
              f"working tree. Only {', '.join(sorted(conftest.ALLOWED_DIR_NAMES))} "
              "may change, plus a pure append by the scheduled meter sampler to "
              "its own two log files:")
        for line in changes[:20]:
            print(f"    {line}")
        if len(changes) > 20:
            print(f"    ... and {len(changes) - 20} more")
        return 1

    if failures:
        print(f"run_tests: FAILED, {len(failures)} suite(s) failed: {', '.join(failures)}")
        return 1

    if skipped_live:
        word = "ran" if conftest.ALLOW_LIVE else "SKIPPED, pass --live to run"
        print(f"run_tests: {len(skipped_live)} live claim(s) {word}: "
              f"{', '.join(skipped_live)}")
    else:
        print("run_tests: no claim is marked live, so the whole suite is hermetic")

    print("run_tests: PASS, every suite green and not one path changed anywhere "
          "under the working tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
