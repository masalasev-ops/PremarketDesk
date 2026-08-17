"""The assertion that the morning's numbers are actually from this morning.

On 2026-08-14 the chain completed clean, exit zero at every step, and published
a report describing the previous session. Every field error traced to one
cause: the bulk /real-time endpoint serves the last COMPLETED session, so its
close was yesterday's close and its previousClose was the session before that,
while prior_high came from end of day history and was correct. Nothing in the
pipeline ever asked whether the data was from today, so nothing objected.

This module asks. It runs after pricing and before scoring, and a violation
ends the run: the gate marker is rewritten with the failing rows named, and
scan exits non-zero, which stops the morning chain before the analyst call.
There is deliberately no degrade path. A stale price is not thin evidence that
a report can hedge around, it is a wrong number wearing the costume of a right
one, and the only safe thing to do with it is refuse.

Check (b) is the cheapest and would have caught that morning on its own,
without one vendor call: six candidates carried a prior_high below their
prior_close, which cannot happen inside a single OHLC bar.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from core import criteria
from core import ettime
from ops import market_today

_CRIT = criteria.load()


class StaleDataError(RuntimeError):
    """Raised when the packet's own timestamps say it is not about today."""


# The premarket session bounds. Deliberately read from the two keys that
# already define them rather than introduced as a third copy: a second source
# of truth for when premarket starts is how these things drift apart in the
# first place, which is the entire subject of this module.
def _window() -> tuple[str, str]:
    return (
        _CRIT.clock_text("baseline", "session_start"),
        _CRIT.clock_text("backfill", "market_open"),
    )


def previous_trading_session(day: dt.date, limit: int = 10) -> dt.date | None:
    """The last session the exchange was actually open before day.

    Walks back through the cached exchange calendar rather than subtracting a
    day, so a Monday's prior session is Friday and the session before a holiday
    is the day before the holiday. Returns None when the calendar cannot answer
    within limit days, which the caller treats as unknown rather than as a
    violation: a check that cannot run must not fail a run it did not examine.
    """
    for back in range(1, limit + 1):
        candidate = day - dt.timedelta(days=back)
        try:
            open_that_day, _why = market_today.is_trading_day(candidate)
        except Exception:
            return None
        if open_that_day:
            return candidate
    return None


def _parse_stamp(text: Any) -> dt.datetime | None:
    if not text:
        return None
    try:
        when = dt.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=ettime.ET)


def _date_of(text: Any) -> dt.date | None:
    when = _parse_stamp(text)
    if when is not None:
        return when.date()
    try:
        return ettime.parse_date(str(text))
    except (TypeError, ValueError):
        return None


# How many trading sessions back the row's NEWEST datum sits, per leg.
#
# This is a freshness table, not a lookback table, and the distinction is the
# whole reason it exists. Vintage catches STALE DATA, so as_of_session has to
# name the newest number in the row, because that is the one that can go stale.
# Anchoring it on the baseline would point the gate at the oldest number, which
# is old by definition and therefore tells it nothing.
#
# The decisive case is already on this project's record. discover buys an extra
# bulk call at a flat hundred credits precisely so all three sessions carry one
# vintage, because reading the third from gap_stats would be free and wrong,
# its closes being five sessions old by Friday. Under baseline labelling that
# bug is invisible: a three_session row stamped three sessions back looks
# correct whether its closes are current or a week old. Under this one it fails
# immediately.
#
# So every completed session leg maps to 1. A name nobody subscribed to has no
# live price, so the newest close there is for it is the prior session's,
# whatever window the leg spans. THE LOOKBACK LIVES IN THE LEG LABEL ALONE.
#
# Known gap, recorded rather than papered over: a row whose leg says
# three_session while its move is arithmetically a one session move is caught
# by neither this table nor any other check here. Vintage verifies that the
# data is fresh, not that the move matches the window its label claims.
#
# A leg absent from this table is not a leg. It fails rather than passing
# unchecked, because an unrecognised label is indistinguishable from a typo,
# and a section whose entire premise is labelling cannot afford either.
_LEG_NEWEST_SESSION_BACK = {
    "premarket": 0,
    "prior_session": 1,
    "two_session": 1,
    "three_session": 1,
}


def sessions_back(today: dt.date, count: int) -> dt.date:
    """The trading session `count` sessions before `today`, walking the calendar."""
    day = today
    for _ in range(count):
        day = previous_trading_session(day)
    return day


def check(
    candidates: list[dict[str, Any]],
    snapshot: list[dict[str, Any]],
    session_date: str,
    notable: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every vintage violation in this packet. Empty means the data is today's.

    Each violation names the check that caught it and the row it caught, so
    the marker file written from this list is a list of rows to look at rather
    than a verdict to argue with.
    """
    today = ettime.parse_date(session_date)
    window_start, window_end = _window()
    prior_session = previous_trading_session(today)
    violations: list[dict[str, Any]] = []

    def fail(check_id: str, row: str, detail: str) -> None:
        violations.append({"check": check_id, "row": row, "detail": detail})

    # (a) every priced candidate's price timestamp is inside today's premarket
    # window. A candidate with no price was dropped for lack of coverage and is
    # not priced, so there is nothing here to assert about it.
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "?")
        if candidate.get("price") is None:
            continue
        stamp = candidate.get("price_time")
        when = _parse_stamp(stamp)
        if when is None:
            fail("a", symbol, f"priced at {candidate['price']} with no readable "
                              f"price_time ({stamp!r})")
            continue
        if when.date() != today:
            fail("a", symbol, f"price_time {stamp} is dated {when.date()}, not the "
                              f"session date {session_date}")
            continue
        hhmm = ettime.hhmm(when)
        if not window_start <= hhmm <= window_end:
            fail("a", symbol, f"price_time {stamp} at {hhmm} ET is outside the "
                              f"premarket window {window_start} to {window_end}")

    # (b) a session's high cannot be below its own close. When this trips, the
    # two fields came from different sessions.
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "?")
        prior_close = candidate.get("prior_close")
        prior_high = candidate.get("prior_high")
        if prior_close is None or prior_high is None:
            continue
        if prior_high < prior_close:
            fail("b", symbol, f"prior_high {prior_high} is below prior_close "
                              f"{prior_close}, so they are not from the same session")

    # (c) the prior close is the prior TRADING session, per the exchange
    # calendar, not merely some earlier date.
    if prior_session is not None:
        for candidate in candidates:
            symbol = str(candidate.get("symbol") or "?")
            if candidate.get("prior_close") is None:
                continue
            dated = _date_of(candidate.get("prior_session_date"))
            if dated is None:
                fail("c", symbol, "carries a prior_close with no readable "
                                  "prior_session_date to date it")
                continue
            if dated != prior_session:
                fail("c", symbol, f"prior_close is dated {dated}, but the prior "
                                  f"trading session was {prior_session}")

    # (d) the market snapshot is from today. A row explicitly labelled
    # prior_session_only is not claiming to be current, so it is held to the
    # weaker requirement of being correctly dated to the prior session; a row
    # that claims to be current and is not is exactly the 2026-08-14 defect,
    # where SPY's "up 0.70 percent" was the previous session's move.
    for row in snapshot or []:
        label = str(row.get("label") or row.get("symbol") or "?")
        if row.get("last") is None:
            continue
        dated = _date_of(row.get("as_of"))
        if dated is None:
            fail("d", label, f"has a last of {row.get('last')} with no readable "
                             f"as_of ({row.get('as_of')!r})")
            continue
        if row.get("prior_session_only"):
            if prior_session is not None and dated != prior_session:
                fail("d", label, f"is labelled prior session only but is dated "
                                 f"{dated}, and the prior trading session was "
                                 f"{prior_session}")
            continue
        if dated != today:
            fail("d", label, f"claims to be current but is dated {dated}, not the "
                             f"session date {session_date}")

    # (e) every notable movers row is the vintage its own label claims.
    #
    # Checks (a) to (d) all ask "is this today's". That is right for the
    # candidates and the market snapshot, which carry one vintage, and it is
    # wrong for this section by design: it mixes a premarket leg for the names
    # the collector heard with completed session legs for everyone else,
    # because there is no universe wide premarket price to be had. So the
    # question changes. Not "is the packet today's" but "does every row match
    # the session its leg declares".
    #
    # leg and as_of_session are REQUIRED. A row missing either fails and is
    # never skipped. Skipping it would let an unlabelled row through a gate
    # whose whole purpose is that the labels are true, and an unlabelled row in
    # a section built entirely on labelling is the exact failure this check
    # exists to catch.
    for row in notable or []:
        symbol = str(row.get("symbol") or row.get("ticker") or "?")
        leg = row.get("leg")
        stamped = row.get("as_of_session")
        if not leg:
            fail("e", symbol, "carries no leg, so there is nothing to date it "
                              "against. Every row in this section states which "
                              "leg produced it.")
            continue
        if leg not in _LEG_NEWEST_SESSION_BACK:
            fail("e", symbol, f"declares leg {leg!r}, which is not one of "
                              f"{', '.join(sorted(_LEG_NEWEST_SESSION_BACK))}. An "
                              "unrecognised leg cannot be dated.")
            continue
        if not stamped:
            fail("e", symbol, f"declares leg {leg} with no as_of_session, so the "
                              "row claims a vintage it does not state")
            continue
        dated = _date_of(stamped)
        if dated is None:
            fail("e", symbol, f"declares leg {leg} with an unreadable "
                              f"as_of_session ({stamped!r})")
            continue
        expected = sessions_back(today, _LEG_NEWEST_SESSION_BACK[leg])
        if dated != expected:
            fail("e", symbol, f"declares leg {leg}, whose newest datum is "
                              f"{expected}, but is stamped {dated}. A row stamped "
                              "with one leg's session while labelled another's is "
                              "how a three day old move gets read as an overnight "
                              "one.")
            continue
        # A row that carries a price timestamp is held to the same session its
        # leg declares, and the premarket leg additionally to the premarket
        # window, because that leg is the only one claiming to be intraday.
        when = _parse_stamp(row.get("price_time"))
        if row.get("price_time") and when is None:
            fail("e", symbol, f"carries an unreadable price_time "
                              f"({row.get('price_time')!r})")
            continue
        if when is not None:
            if when.date() != expected:
                fail("e", symbol, f"declares leg {leg} as of {expected} but its "
                                  f"price_time is dated {when.date()}")
                continue
            if leg == "premarket":
                hhmm = ettime.hhmm(when)
                if not window_start <= hhmm <= window_end:
                    fail("e", symbol, f"is on the premarket leg with a price_time "
                                      f"at {hhmm} ET, outside the premarket window "
                                      f"{window_start} to {window_end}")

    return violations


def check_packet(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """check() against a whole packet, for replaying one that is already on disk."""
    notable = payload.get("notable_movers") or {}
    return check(
        payload.get("candidates") or [],
        payload.get("market_snapshot") or [],
        str(payload.get("session_date") or ettime.today_et().isoformat()),
        # The section stores its rows under "rows"; a bare list is accepted too
        # so a hand written fixture does not have to know the wrapper's shape.
        notable if isinstance(notable, list) else (notable.get("rows") or []),
    )


def describe(violations: list[dict[str, Any]]) -> str:
    names = {
        "a": "price timestamp outside today's premarket window",
        "b": "prior_high below prior_close, so they are not one session",
        "c": "prior close is not the prior trading session",
        "d": "market snapshot is not from today",
    }
    lines: list[str] = []
    for check_id in sorted({v["check"] for v in violations}):
        hit = [v for v in violations if v["check"] == check_id]
        lines.append(f"  ({check_id}) {names.get(check_id, check_id)}: "
                     f"{len(hit)} row(s)")
        for violation in hit:
            lines.append(f"        {violation['row']}: {violation['detail']}")
    return "\n".join(lines)


def enforce(payload: dict[str, Any]) -> None:
    """Raise StaleDataError, and re-gate delivery, if this packet is not today's.

    Importing verify_morning here rather than at module scope keeps the gate
    marker's ownership in one place: verify_morning defines where it lives and
    a human deletes it, this module only ever writes it back.
    """
    violations = check_packet(payload)
    if not violations:
        return

    from morning import verify_morning

    session_date = payload.get("session_date")
    body = (
        f"Written by vintage.py on {ettime.stamp(ettime.now_et())}.\n\n"
        f"The {session_date} run was refused: its own timestamps say the data is "
        "not from today.\n"
        "Delivery is gated until a human has looked at the rows below and at the "
        "source they came from.\n\n"
        f"{describe(violations)}\n\n"
        "This marker was rewritten automatically. Deleting it re-enables email "
        "and does not fix the data.\n"
    )
    verify_morning.UNVERIFIED_MARKER.write_text(body, encoding="utf-8")

    print(f"scan: REFUSING the {session_date} packet, "
          f"{len(violations)} vintage violation(s):")
    print(describe(violations))
    print(f"scan: rewrote {verify_morning.UNVERIFIED_MARKER}. Nothing was scored, "
          "no packet was written, and the morning chain stops here rather than "
          "sending yesterday's numbers to the model.")
    raise StaleDataError(
        f"{len(violations)} vintage violation(s) in the {session_date} packet"
    )
