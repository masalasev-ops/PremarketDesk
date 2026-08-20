"""The is it a trading day guard.

Every weekday scheduled job runs this first. Exit 0 means the market trades
today (or the guard could not tell, which counts as open on purpose). Exit 3
means the market is closed, weekend or official holiday, and the job's .bat
logs one line and stops cleanly instead of building a watchlist from stale
quotes and emailing a report about a session that does not exist.

The holiday list comes from EODHD exchange-details, cached to
data/exchange-details.json so the 07:15 decision does not hang on a live
call. The cache refreshes weekly; a fetch failure falls back to the stale
cache; no cache at all assumes open. The failure direction is deliberate: a
false closed silently loses a real morning, a false open produces one
honestly thin report that says its own numbers are stale.

That assumption is right for the exit code and wrong for anyone asking a
question the exit code does not answer, so there are two ways in. Callers
deciding whether to run today read is_trading_day, which never says it does
not know. Callers asking which dates were sessions read trading_day_state,
which answers None when there is no holiday list to answer from, so an
assumption cannot be mistaken for a fact about the calendar.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status

_CRIT = criteria.load()

CACHE_PATH = config.DATA_DIR / "exchange-details.json"
EXIT_CLOSED = 3

# The exit codes that mean this step did its job, read by __main__ below AND by
# the entrypoint test harness. It is a module constant rather than a literal in
# the __main__ line because the harness cannot reach inside that line: it
# imports the module and calls main() directly, so a literal there is invisible
# to the test that exists to prove this entrypoint behaves. That drift made the
# suite pass Monday to Friday and fail on a Saturday, when a closed market is
# the only time EXIT_CLOSED is returned at all.
OK_CODES = (0, EXIT_CLOSED)

_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _load_cache() -> dict[str, Any] | None:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_age_days(cache: dict[str, Any]) -> float | None:
    fetched = cache.get("fetched_at")
    if not fetched:
        return None
    try:
        stamp = dt.datetime.fromisoformat(fetched)
    except ValueError:
        return None
    return (ettime.now_et() - stamp).total_seconds() / 86400.0


# One parse per process. is_trading_day is called once per step per day walked
# by job_status.overdue(), which scan calls twice, so a ten day gap across
# sixteen steps was several hundred re-reads of the same file. Harmless while
# the cache is fresh and a few hundred sequential HTTP attempts inside the
# 08:45 window once it is not.
_MEMO: dict[str, Any] = {"details": None, "loaded": False, "refreshed": False}

# Set by the morning path so a stale cache is used as-is rather than blocking
# on a fetch. The nightly is what refreshes it.
ALLOW_NETWORK = True


def reset_memo() -> None:
    """Forget the in-process copy. For tests and for the nightly refresh."""
    _MEMO.update({"details": None, "loaded": False, "refreshed": False})


def cache_state(refresh_after_days: int) -> dict[str, Any]:
    """Age and staleness of the calendar cache, for the packet and the record."""
    cache = _load_cache()
    age = _cache_age_days(cache) if cache else None
    return {
        "present": cache is not None,
        "fetched_at": (cache or {}).get("fetched_at"),
        "age_days": round(age, 2) if age is not None else None,
        "stale": age is None or age > refresh_after_days,
        "refresh_after_days": refresh_after_days,
    }


def get_details(refresh_after_days: int, force: bool = False) -> dict[str, Any] | None:
    """Cached exchange details, refreshed weekly, stale cache over nothing.

    Three layers now. The in-process memo answers repeat calls without
    touching the disk; the file answers a cold process; the network answers
    only when the file is stale AND the caller allows it. The morning chain
    sets ALLOW_NETWORK false, so a stale calendar degrades to the cached copy
    with the staleness recorded rather than blocking the 08:45 window on a
    fetch and its retries.

    force skips the memo and the age check and goes to the vendor, which is
    what the nightly --refresh wants: leave the cache young enough that
    tomorrow morning finds it fresh, on six days out of seven when an age
    test would decline. It does NOT skip the fallback below. The refresh used
    to delete the cache first and then fetch, which turned one 22:15 vendor
    outage into no holiday list at all, and this module's whole failure
    direction is that an unknown calendar reads as open. A Christmas Eve
    outage would have run the full pipeline on a closed market. The old file
    now stands until a new one is actually in hand.
    """
    if _MEMO["loaded"] and not force:
        return _MEMO["details"]

    cache = _load_cache()
    age = _cache_age_days(cache) if cache else None
    if not force and cache is not None and age is not None and age <= refresh_after_days:
        _MEMO.update({"details": cache, "loaded": True})
        return cache

    if not ALLOW_NETWORK:
        # Stale, and this caller must not spend the morning fetching. A stale
        # exchange calendar is wrong only across a holiday list revision,
        # which is a rare and slow moving fact; blocking the morning on it
        # would be the more expensive mistake.
        if cache is not None:
            print(f"calendar: cache is {age:.1f} days old and this run does not "
                  "fetch; using it as it stands")
        _MEMO.update({"details": cache, "loaded": True})
        return cache

    exchange = _CRIT.text("calendar", "exchange")
    details, error = eodhd.client().exchange_details(exchange)
    if error or not isinstance(details, dict):
        if cache is not None:
            print(f"calendar: refresh failed ({error}), using the cache from "
                  f"{cache.get('fetched_at')}")
            _MEMO.update({"details": cache, "loaded": True})
            return cache
        print(f"calendar: exchange-details unavailable ({error}) and no cache exists")
        _MEMO.update({"details": None, "loaded": True})
        return None

    payload = dict(details)
    payload["fetched_at"] = ettime.stamp(ettime.now_et())
    config.ensure_dirs()
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"calendar: refreshed {CACHE_PATH.name} from exchange-details")
    _MEMO.update({"details": payload, "loaded": True, "refreshed": True})
    return payload


def _holidays(details: dict[str, Any]) -> dict[str, str]:
    """Date -> holiday name, tolerating both dict and list payload shapes."""
    raw = details.get("ExchangeHolidays") or {}
    rows = raw.values() if isinstance(raw, dict) else raw
    out: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("Date"):
            out[str(row["Date"])] = str(row.get("Holiday") or "holiday")
    return out


def _working_days(details: dict[str, Any]) -> set[str]:
    raw = ((details.get("TradingHours") or {}).get("WorkingDays")
           or "Mon,Tue,Wed,Thu,Fri")
    return {part.strip() for part in str(raw).split(",") if part.strip()}


# The one sentence is_trading_day says when there is no holiday list to answer
# from. A module constant because it is a signal as well as a sentence: it is
# how trading_day_state below tells an assumption from an answer, and both
# halves of that have to be the same string.
CALENDAR_ASSUMED_REASON = "calendar unavailable, assuming the market is open"

# The one sentence trading_day_state says beside its None. A module constant
# because a caller that wants to print WHY it stood down should quote the
# guard rather than compose its own wording for a state the guard defines.
CALENDAR_UNKNOWN_REASON = "there is no exchange calendar to answer from"


def decide(details: dict[str, Any] | None,
           date: dt.date) -> tuple[bool | None, str]:
    """(trades_today, reason) for one date against a calendar already in hand.

    The whole holiday rule, in one place, reading a details payload it is
    handed rather than fetching one of its own. Both ways into this module
    reach it and neither has another route to the calendar, which is what
    makes it a seam: replacing this function, or replacing is_trading_day
    below, replaces the answer BOTH of them give.

    There was a second route until 2026-08-20, and it made a test machine
    dependent. trading_day_state asked calendar_known() whether there was a
    holiday list at all before delegating the date to is_trading_day, so a
    suite that had replaced is_trading_day with a plain weekday rule still took
    that half of the answer from whatever was on the machine's disk:
    test_vintage's stubbed walk answered Friday 2026-08-14 on the machine the
    stub was written on and None on a fresh clone, where data/ is gitignored
    and the cache does not exist. A stub that cannot control the unknown is not
    a stub of the calendar, and the claim resting on it was measuring the real
    file rather than the rule it had installed.

    A trades_today of None is that unknown, and the two entry points read it
    differently on purpose: is_trading_day reads it as open, because a morning
    that refuses to run over a missing cache file is worse than one that runs,
    and trading_day_state hands it on as unknown.
    """
    if details is None:
        return None, CALENDAR_UNKNOWN_REASON

    day_name = _WEEKDAY_NAMES[date.weekday()]
    if day_name not in _working_days(details):
        return False, f"{date} is a {day_name}, not a working day"

    holidays = _holidays(details)
    if date.isoformat() in holidays:
        return False, f"{date} is {holidays[date.isoformat()]}"

    early = details.get("ExchangeEarlyCloseDays") or {}
    early_rows = early.values() if isinstance(early, dict) else early
    for row in early_rows:
        if isinstance(row, dict) and str(row.get("Date")) == date.isoformat():
            return True, (f"{date} is a trading day with an early close "
                          f"({row.get('Holiday') or 'early close'})")
    return True, f"{date} is a regular trading day"


def is_trading_day(date: dt.date) -> tuple[bool, str]:
    """(trades_today, reason). Unknowable counts as open, see the module doc.

    This function cannot say "I do not know" and must not learn to. Every
    scheduled .bat runs `python -m ops.market_today` first and branches on the
    EXIT CODE alone, so an assumption is exactly what is wanted here: refusing
    to run the morning because a cache file is missing is worse than running
    it. A caller that needs to tell an answer from an assumption calls
    trading_day_state below instead, which reads the assumption back out of
    this same call rather than asking the calendar a second question.

    Cheap to call in a loop: get_details answers from the in-process memo after
    the first read, which is why the walk in vintage can ask per day.
    """
    details = get_details(_CRIT.integer("calendar", "refresh_after_days"))
    trades, reason = decide(details, date)
    if trades is None:
        return True, CALENDAR_ASSUMED_REASON
    return trades, reason


def trading_day_state(date: dt.date) -> tuple[bool | None, str]:
    """(trades_today, reason), where a trades_today of None means unknown.

    The same question is_trading_day answers, for the callers that can act on
    "I do not know". is_trading_day answers True for EVERY date when
    data/exchange-details.json is missing or unreadable, weekends included,
    and that is deliberate for the exit code path. It was not deliberate
    anywhere else. With no cache, vintage.previous_trading_session walked one
    day back from a Monday, was told Sunday trades, and returned Sunday; the
    2026-08-17 packet then failed vintage checks (c) and (d) on every
    candidate and every prior session snapshot row it had, six violations on
    a packet whose dates were all correct. enforce() rewrote the delivery gate
    over the human's note and the chain stopped before the analyst, accusing
    the vendor of stale data when the only thing missing was a holiday list.

    Everything here comes back through is_trading_day, including the unknown.
    That is what changed on 2026-08-20 and it is the whole point of the
    arrangement: is_trading_day says CALENDAR_ASSUMED_REASON in exactly one
    place and nowhere else, so that sentence IS the assumption, and this reads
    it back. The version before this one asked calendar_known() first and
    delegated only afterwards, which consulted the calendar twice and, the
    half that mattered, decided the unknown OUTSIDE the function a caller can
    replace. See decide() above for the machine dependent test that came of it.
    """
    trades, reason = is_trading_day(date)
    if reason == CALENDAR_ASSUMED_REASON:
        # Not a sniff at a message. That constant is returned from exactly one
        # branch, the one with no calendar to answer from, and this is its only
        # reader, so the two cannot drift apart the way a literal here would.
        return None, CALENDAR_UNKNOWN_REASON
    return trades, reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Is the market open today?")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Check a specific date instead of today, for testing.")
    parser.add_argument("--refresh", action="store_true",
                        help="Force the exchange calendar to be re-fetched. The "
                             "nightly runs this so the morning never has to.")
    args = parser.parse_args(argv)

    if args.refresh:
        # Deliberately ignores the age check: the point is to leave the cache
        # young enough that tomorrow's morning finds it fresh, which a
        # refresh_after_days test would skip on six days out of seven. The
        # existing cache is NOT removed first; get_details(force=True) writes
        # over it only once the vendor has answered, so a failed refresh
        # leaves yesterday's holiday list in place instead of leaving none.
        reset_memo()
        details = get_details(_CRIT.integer("calendar", "refresh_after_days"),
                              force=True)
        state = cache_state(_CRIT.integer("calendar", "refresh_after_days"))
        print(f"calendar: refresh {'succeeded' if details else 'FAILED'}, "
              f"cache {state}")
        job_status.produced("calendar refreshed", 1 if details else 0)
        if not details:
            job_status.failed("the exchange calendar could not be refreshed, so "
                              "the morning will run on whatever cache exists")
        return 0

    date = ettime.parse_date(args.date) if args.date else ettime.today_et()
    try:
        trades, reason = is_trading_day(date)
    except Exception as exc:  # the guard must never kill a real morning
        # Exit zero so the day proceeds, but say so in the record. A guard
        # that has been erroring for a fortnight is running every job on the
        # assumption that the market is open, which is the right assumption
        # and still something the reader should know is being assumed.
        print(f"calendar: guard errored ({exc}), assuming the market is open")
        job_status.failed(f"{type(exc).__name__}: {exc}, assumed open")
        return 0
    print(f"calendar: {reason}")
    job_status.produced("trading day", 1 if trades else 0)
    return 0 if trades else EXIT_CLOSED


if __name__ == "__main__":
    # A closed market is this guard working, not this guard failing.
    sys.exit(job_status.run("calendar", main, ok_codes=OK_CODES))
