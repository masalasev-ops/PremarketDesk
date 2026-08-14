"""Run the whole suite inside the sandbox, and prove it stayed inside.

Two guarantees, and the second is the one that matters. The sandbox redirects
every writable root a test could reach through config, which stops the ordinary
mistake. The mtime check catches the extraordinary one: a test that hardcodes
an absolute path cannot be redirected, so instead the real runs/, data/ and site/
are photographed before and after and any difference fails the run.

  python src\\run_tests.py                  the suite, sandboxed and checked
  python src\\run_tests.py --prove-check    add a test that deliberately writes
                                            to the real runs/, to show the
                                            check catches it. Expected to FAIL.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import traceback

import conftest

SUITE = (
    "test_store",
    "test_scrub",
    "test_containment",
    "test_vintage",
    "test_repricing",
    "test_pool",
    "test_backtest",
    "test_txn_guard",
    "test_entrypoints",
)


def _misbehave() -> int:
    """A test that reaches around the sandbox, to prove the check is real."""
    target = conftest.REAL_RUNS / "sandbox-escape-probe.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("this test wrote to the real runs directory\n", encoding="utf-8")
    print(f"  misbehaving test wrote {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the suite under the sandbox.")
    parser.add_argument("--prove-check", action="store_true",
                        help="Append a test that writes to the real runs/, to "
                             "demonstrate the mtime check catches it.")
    parser.add_argument("--only", action="append", default=[],
                        help="Run only these modules, repeatable.")
    args = parser.parse_args(argv)

    modules = args.only or list(SUITE)
    before = conftest.snapshot(conftest.REAL_RUNS, conftest.REAL_DATA,
                               conftest.REAL_SITE)
    print(f"run_tests: {len(before)} files under the real runs/, data/ and site/ before")

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

    after = conftest.snapshot(conftest.REAL_RUNS, conftest.REAL_DATA,
                              conftest.REAL_SITE)
    changes = conftest.differences(before, after)
    print(f"run_tests: {len(after)} files after")

    if changes:
        print(f"run_tests: FAILED, the suite changed {len(changes)} file(s) under the "
              "real runs/, data/ or site/:")
        for line in changes[:20]:
            print(f"    {line}")
        if len(changes) > 20:
            print(f"    ... and {len(changes) - 20} more")
        return 1

    if failures:
        print(f"run_tests: FAILED, {len(failures)} suite(s) failed: {', '.join(failures)}")
        return 1

    print("run_tests: PASS, every suite green and not one byte changed under the "
          "real runs/, data/ or site/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
