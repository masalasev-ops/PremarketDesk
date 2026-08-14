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

  python src\\run_tests.py                        the suite, sandboxed and checked
  python src\\run_tests.py --prove-check          write to the real runs/, to show
                                                  the check catches it. FAILs.
  python src\\run_tests.py --prove-check-outside  write to tasks/, which no version
                                                  of the enumerated check ever
                                                  watched. FAILs.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import traceback

from tests import conftest

SUITE = (
    "tests.test_store",
    "tests.test_scrub",
    "tests.test_containment",
    "tests.test_vintage",
    "tests.test_repricing",
    "tests.test_pool",
    "tests.test_backtest",
    "tests.test_txn_guard",
    "tests.test_entrypoints",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the suite under the sandbox.")
    parser.add_argument("--prove-check", action="store_true",
                        help="Append a test that writes to the real runs/, to "
                             "demonstrate the tree check catches it.")
    parser.add_argument("--prove-check-outside", action="store_true",
                        help="Append a test that writes to tasks/, a root no "
                             "version of the old enumerated check watched.")
    parser.add_argument("--only", action="append", default=[],
                        help="Run only these modules, repeatable.")
    args = parser.parse_args(argv)

    modules = args.only or list(SUITE)
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
    with conftest.activate() as sandbox:
        print(f"run_tests: sandbox at {sandbox}")
        for name in modules:
            module = importlib.import_module(name)
            importlib.reload(module)
            try:
                code = module.main()
            except Exception:
                traceback.print_exc()
                code = 1
            status = "ok" if code == 0 else f"EXIT {code}"
            print(f"run_tests: {name:<18} {status}")
            if code != 0:
                failures.append(name)
        if args.prove_check:
            _misbehave()
        if args.prove_check_outside:
            _misbehave_outside()

    after = conftest.snapshot_tree()
    changes = conftest.differences(before, after)
    print(f"run_tests: {len(after)} paths after")

    if changes:
        print(f"run_tests: FAILED, the suite changed {len(changes)} path(s) under the "
              f"working tree. Only {', '.join(sorted(conftest.ALLOWED_DIR_NAMES))} "
              "may change:")
        for line in changes[:20]:
            print(f"    {line}")
        if len(changes) > 20:
            print(f"    ... and {len(changes) - 20} more")
        return 1

    if failures:
        print(f"run_tests: FAILED, {len(failures)} suite(s) failed: {', '.join(failures)}")
        return 1

    print("run_tests: PASS, every suite green and not one path changed anywhere "
          "under the working tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
