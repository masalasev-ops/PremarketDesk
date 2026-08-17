"""Regression test for the vintage assertion.

Run directly: `python src\\test_vintage.py`, exit 0 on pass. Makes no network
calls: the exchange calendar is stubbed to a plain weekday rule so the test is
hermetic and gives the same answer on any machine. The real gate marker is
never touched; enforce() is pointed at a temporary file.

Four claims. The two notable movers claims run FIRST, ahead of everything that
needs the 2026-08-14 run on disk, because they are built entirely from
synthetic rows and the stubbed calendar. The two packet claims below them skip
on a machine that does not have that run:
  1. The packet from the 2026-08-14 run, the one that completed clean and
     published the previous session, is refused. Checks (a), (b) and (d) all
     fire, and the six rows whose prior_high sits below their own prior_close
     are each named in the marker file that enforce() writes.
  2. A synthetic packet whose timestamps really are from today passes every
     check and writes no marker. There are five, (a) to (e), and this packet
     carries no notable_movers key, so (e) passes it vacuously; claims 3 and 4
     are what actually exercise (e).
  3. Every notable movers row is validated against the leg it declares, and the
     fields that make that answerable are required rather than optional.
  4. A calendar that cannot answer silences check (e)'s session comparison and
     nothing else.
"""

from __future__ import annotations

import datetime as dt
import json
import sys

from core import config
from core import criteria
from core import ettime
from ops import market_today
from morning import verify_morning
from morning import vintage

_CRIT = criteria.load()
PACKET_PATH = config.RUNS_DIR / "2026-08-14" / "packet.json"

# The six candidates whose prior_high was below their own prior_close, which
# cannot happen inside one OHLC bar and is the cheapest possible proof that the
# two fields came from different sessions.
IMPOSSIBLE = ["CLBT.US", "SECZ.US", "LFTO.US", "REZI.US", "TPR.US", "BSP.US"]


def _clean_packet() -> dict:
    """A packet whose every timestamp is honestly from the session it claims."""
    return {
        "session_date": "2026-08-14",
        "candidates": [
            {
                "symbol": "WDAY.US",
                "price": 206.06,
                "price_time": "2026-08-14T08:43:00-04:00",
                "prior_close": 206.45,
                "prior_high": 227.49,
                "prior_session_date": "2026-08-13",
            },
            {
                # Dropped for no coverage: unpriced, so (a) has nothing to say
                # about it and (b) and (c) still hold it to its history.
                "symbol": "MH.US",
                "price": None,
                "price_time": None,
                "prior_close": 13.55,
                "prior_high": 13.57,
                "prior_session_date": "2026-08-13",
            },
        ],
        "market_snapshot": [
            {"label": "spy", "symbol": "SPY.US", "last": 778.73,
             "as_of": "2026-08-14T08:44:00-04:00", "source": "collector",
             "prior_session_only": False},
            {"label": "10y", "symbol": "US10Y.GBOND", "last": 4.664,
             "as_of": "2026-08-13", "source": "eod", "prior_session_only": True},
        ],
    }



def claim_notable_legs(failures: list[str]) -> None:
    """The briefing section is validated per row, against the leg it declares.

    Checks (a) to (d) ask "is this today's", which is right for the candidates
    and the market snapshot because they carry one vintage. The briefing
    section carries several on purpose: there is no universe wide premarket
    price, so names the collector never heard are measured on completed
    sessions while the fifty it did hear are measured this morning. Asking one
    vintage question of that section would either fail every honest row or pass
    every dishonest one.

    So the question changes to "does each row match the session its own leg
    declares", and the fields that make that answerable are REQUIRED. A row
    with no leg, or no as_of_session, fails rather than being skipped. Skipping
    it would let an unlabelled row through a gate whose entire purpose is that
    the labels are true.
    """
    today = ettime.today_et()
    session = today.isoformat()
    back = {n: vintage.sessions_back(today, n).isoformat() for n in (0, 1, 2, 3)}

    cases = (
        ("a correctly mixed vintage section", [
            {"symbol": "AAA", "leg": "premarket", "as_of_session": back[0]},
            {"symbol": "BBB", "leg": "prior_session", "as_of_session": back[1]},
            {"symbol": "CCC", "leg": "two_session", "as_of_session": back[1]},
        ], 0),
        ("a prior session row mis-stamped as premarket", [
            {"symbol": "EEE", "leg": "premarket", "as_of_session": back[1]},
        ], 1),
        ("a premarket row mis-stamped as a prior session", [
            {"symbol": "FFF", "leg": "prior_session", "as_of_session": back[0]},
        ], 1),
        ("a row with no leg", [{"symbol": "GGG", "as_of_session": back[0]}], 1),
        ("a row with no as_of_session", [{"symbol": "HHH", "leg": "premarket"}], 1),
        ("a row whose leg is not a leg", [
            {"symbol": "III", "leg": "weekly", "as_of_session": back[1]},
        ], 1),
        # Under freshness labelling a completed leg is stamped with the
        # NEWEST close it has, which for a name with no live price is the
        # prior session whatever window the leg spans. The two session leg
        # spans c3 to c1, so a row stamped three sessions back is stamped with
        # its BASELINE, and that is stale rather than correct: it is exactly
        # the gap_stats closes discover spends 100 credits to avoid.
        ("a two session row stamped with its baseline", [
            {"symbol": "JJJ", "leg": "two_session", "as_of_session": back[3]},
        ], 1),
    )
    for label, rows, expected in cases:
        found = vintage.check([], [], session, rows)
        if len(found) != expected:
            failures.append(f"{label} produced {len(found)} violation(s), expected "
                            f"{expected}: {found}")
            continue
        if expected and found[0]["check"] != "e":
            failures.append(f"{label} was caught by check {found[0]['check']!r}, "
                            "expected check e")

    # And the gate has to reach the whole packet path, not only check().
    mixed = {
        "session_date": session,
        "candidates": [],
        "market_snapshot": [],
        "notable_movers": {"rows": [
            {"symbol": "KKK", "leg": "prior_session", "as_of_session": back[0]},
        ]},
    }
    if not vintage.check_packet(mixed):
        failures.append("check_packet did not walk notable_movers, so a mis-stamped "
                        "briefing row would reach the report unchecked")

    print(f"  claim legs      {len(cases)} leg cases, a mis-stamped row and an "
          "unlabelled row both fail, and check_packet walks the section")


def claim_notable_legs_unknown_calendar(failures: list[str]) -> None:
    """A calendar that cannot answer silences the comparison, not the check.

    previous_trading_session states the rule the module runs on: None means the
    calendar could not answer, and the caller reads that as unknown rather than
    as a violation, because a check that cannot run must not fail a run it did
    not examine. (c) and (d) have stood down that way since they were written
    and (e) did not, so one unreachable exchange calendar flagged every row on
    a completed session leg at once and refused a packet in which nothing had
    actually been found wrong.

    The stand down is narrow on purpose. leg and as_of_session stay REQUIRED
    with the calendar dark, because a row missing either is malformed whatever
    the calendar says and skipping it would let an unlabelled row through a
    gate whose entire purpose is that the labels are true.

    The premarket window case at the end is a regression guard and not evidence
    of the stand down, and the distinction is worth writing down because the
    obvious reading of it is the wrong one. premarket maps to zero sessions
    back, so sessions_back returns today off the top without consulting the
    calendar at all: the expected session for a premarket row is known even
    with the calendar dark, and the window test therefore never depended on the
    stand down in the first place. It could not have been silenced by it. That
    is why the assertion checks WHICH violation fired rather than only how
    many, since a count alone is equally satisfied by the session comparison
    firing, which would be a different failure wearing the same number.
    """
    today = ettime.today_et()
    session = today.isoformat()

    # Built while the calendar still answers, so these are the stamps an honest
    # section would carry rather than stamps picked to survive the fault.
    #
    # Read into names and checked before .isoformat() touches them, rather than
    # chained onto the call: the subject of this whole claim is that
    # sessions_back can answer None, and a claim that calls a method on that
    # answer dies with an AttributeError traceback instead of the sentence the
    # try/except below exists to print. These calls are safe today only because
    # they sit above the line that installs the fault, and nothing obliges a
    # later edit to keep them there.
    newest = {n: vintage.sessions_back(today, n) for n in (0, 1)}
    if any(day is None for day in newest.values()):
        failures.append("the stubbed calendar could not date the honest fixture "
                        f"({newest}), so nothing below would be testing what it "
                        "claims")
        return
    honest = [
        {"symbol": "AAA", "leg": "premarket",
         "as_of_session": newest[0].isoformat()},
        {"symbol": "BBB", "leg": "prior_session",
         "as_of_session": newest[1].isoformat()},
        {"symbol": "CCC", "leg": "two_session",
         "as_of_session": newest[1].isoformat()},
    ]
    # One minute before premarket opens, read from the same criteria key the
    # check reads, so this fixture cannot drift away from what it is testing.
    opens = ettime.at_hm(today, _CRIT.clock("baseline", "session_start"))
    too_early = ettime.stamp(opens - dt.timedelta(minutes=1))

    # The same fault test_entrypoints uses on the calendar guard: is_trading_day
    # raising, which previous_trading_session catches and reports as unknown.
    # Restored to the weekday stub main() installed, not to the real calendar.
    stubbed = market_today.is_trading_day

    def exploding(day):
        raise RuntimeError("simulated calendar fault")

    market_today.is_trading_day = exploding
    try:
        if vintage.previous_trading_session(today) is not None:
            failures.append("the simulated calendar fault still produced a session "
                            "date, so nothing below is testing what it claims")
            return
        # Caught rather than allowed to escape, because the crash IS the defect
        # being tested: the walk used to carry the unknown into the next step
        # and subtract a timedelta from it. A claim that dies here reports a
        # traceback instead of the sentence explaining what went wrong.
        try:
            walked = vintage.sessions_back(today, 2)
        except TypeError:
            walked = "TypeError: it carried the unknown into the next step"
        if walked is not None:
            failures.append("sessions_back two sessions back has to report the "
                            "session as unknown under a calendar that cannot "
                            f"answer, and instead gave {walked!r}. The walk stops "
                            "at the first unknown; it never carries one forward")

        found = vintage.check([], [], session, honest)
        if found:
            failures.append("a well formed notable section was refused because the "
                            f"calendar could not date it: {found}")

        required = (
            ("a row with no leg", {"symbol": "GGG", "as_of_session": session}),
            ("a row with no as_of_session", {"symbol": "HHH", "leg": "premarket"}),
            ("a row whose leg is not a leg",
             {"symbol": "III", "leg": "weekly", "as_of_session": session}),
            ("a row with an unreadable as_of_session",
             {"symbol": "JJJ", "leg": "premarket", "as_of_session": "sometime"}),
        )
        for label, row in required:
            hit = vintage.check([], [], session, [row])
            if len(hit) != 1 or hit[0]["check"] != "e":
                failures.append(f"with the calendar dark, {label} produced {hit}, "
                                "expected exactly one check (e) violation: the "
                                "labels are required whether or not the calendar "
                                "can date them")

        # The premarket window still fires, and it fires for a reason the count
        # alone cannot show: premarket is zero sessions back, so this row's
        # expected session is today whether or not the calendar can be reached,
        # and the two session comparisons above the window test are satisfied
        # rather than stood down. The count is therefore checked alongside the
        # check id AND the detail. A bare "exactly one violation" would be just
        # as happy if the session comparison had fired and the window test had
        # gone quiet, which is the failure this is here to notice.
        outside = vintage.check([], [], session, [
            {"symbol": "KKK", "leg": "premarket", "as_of_session": session,
             "price_time": too_early},
        ])
        if (len(outside) != 1 or outside[0]["check"] != "e"
                or "outside the premarket window" not in outside[0]["detail"]):
            failures.append("with the calendar dark, a premarket row printed at "
                            f"{too_early} produced {outside}, expected exactly one "
                            "check (e) violation naming the premarket window. The "
                            "premarket leg is dated without asking the calendar "
                            "anything, so a fault must change nothing here at all")
    finally:
        market_today.is_trading_day = stubbed

    print("  claim dark cal  an unanswerable calendar silences the session "
          f"comparison only: {len(honest)} honest rows pass, {len(required)} "
          "unlabelled ones still fail, and the premarket leg is dated at zero "
          "sessions back without the calendar being asked at all")


def _report(failures: list[str]) -> int:
    """Print every failure and hand back the exit code the runner reads.

    Pulled out of main() because main() now has two exits, and the second one,
    the skip when the 2026-08-14 run is not on this machine, used to return 0
    without so much as looking at the list.
    """
    for failure in failures:
        print(f"FAIL  {failure}")
    return 1 if failures else 0


def main() -> int:
    failures: list[str] = []

    # Hermetic calendar: weekdays are open, weekends are not. 2026-08-13 and
    # 2026-08-14 are a Thursday and a Friday, so the prior session of the 14th
    # is the 13th under this rule exactly as it is under the real one.
    market_today.is_trading_day = lambda day: (day.weekday() < 5, "stubbed")

    prior = vintage.previous_trading_session(dt.date(2026, 8, 17))
    if prior != dt.date(2026, 8, 14):
        failures.append(f"the session before Monday 2026-08-17 came back as {prior}, "
                        "expected Friday 2026-08-14")

    # The two notable movers claims run HERE, above the packet check, and the
    # position is deliberate. Both are built entirely from synthetic rows and
    # the stubbed calendar above; neither reads the 2026-08-14 packet or
    # anything the packet block below creates. Sitting under the skip they
    # simply did not execute on a fresh checkout or on any CI box without that
    # run on disk, and the suite reported success with the regression guard for
    # the check (e) stand down never once having run. A guard that only runs on
    # the machine where the bug was first found is not a guard.
    claim_notable_legs(failures)
    claim_notable_legs_unknown_calendar(failures)

    # Claim 1: the real failing packet is refused.
    if not PACKET_PATH.is_file():
        print(f"SKIP  the 2026-08-14 packet is not on this machine ({PACKET_PATH})")
        return _report(failures)
    payload = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    violations = vintage.check_packet(payload)
    fired = {v["check"] for v in violations}
    for check_id in ("a", "b", "d"):
        if check_id not in fired:
            failures.append(f"check ({check_id}) did not fire on the 2026-08-14 packet")
    if "c" in fired:
        failures.append("check (c) fired, but that packet's prior_session_date was "
                        "correctly 2026-08-13, so it should not have")

    impossible_rows = sorted(v["row"] for v in violations if v["check"] == "b")
    if impossible_rows != sorted(IMPOSSIBLE):
        failures.append(f"check (b) named {impossible_rows}, expected {sorted(IMPOSSIBLE)}")

    # enforce() must refuse, and the marker it writes must name those rows.
    original_marker = verify_morning.UNVERIFIED_MARKER
    temporary = config.RUNS_DIR / "2026-08-14" / "test_vintage_UNVERIFIED"
    verify_morning.UNVERIFIED_MARKER = temporary
    try:
        temporary.unlink(missing_ok=True)
        try:
            vintage.enforce(payload)
            failures.append("enforce() accepted the 2026-08-14 packet")
        except vintage.StaleDataError:
            pass
        if not temporary.exists():
            failures.append("enforce() wrote no marker file")
        else:
            marker = temporary.read_text(encoding="utf-8")
            for symbol in IMPOSSIBLE:
                if symbol not in marker:
                    failures.append(f"the marker file does not name {symbol}")

        # Claim 2: a packet that really is from today passes, and writes nothing.
        temporary.unlink(missing_ok=True)
        clean = vintage.check_packet(_clean_packet())
        if clean:
            failures.append(f"the clean packet produced violations: {clean}")
        try:
            vintage.enforce(_clean_packet())
        except vintage.StaleDataError:
            failures.append("enforce() refused the clean packet")
        if temporary.exists():
            failures.append("enforce() wrote a marker for a clean packet")
    finally:
        temporary.unlink(missing_ok=True)
        verify_morning.UNVERIFIED_MARKER = original_marker

    if original_marker.exists():
        print(f"  the real gate marker is untouched at {original_marker}")

    if failures:
        return _report(failures)
    print(f"PASS  the 2026-08-14 packet is refused on checks {sorted(fired)} with all "
          f"{len(IMPOSSIBLE)} impossible rows named in the marker, and a packet whose "
          "timestamps are from today passes every check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
