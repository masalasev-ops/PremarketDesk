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
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

import config
import criteria
import eodhd
import ettime
import job_status

_CRIT = criteria.load()

CACHE_PATH = config.DATA_DIR / "exchange-details.json"
EXIT_CLOSED = 3

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


def get_details(refresh_after_days: int) -> dict[str, Any] | None:
    """Cached exchange details, refreshed weekly, stale cache over nothing."""
    cache = _load_cache()
    age = _cache_age_days(cache) if cache else None
    if cache is not None and age is not None and age <= refresh_after_days:
        return cache

    exchange = _CRIT.text("calendar", "exchange")
    details, error = eodhd.client().exchange_details(exchange)
    if error or not isinstance(details, dict):
        if cache is not None:
            print(f"calendar: refresh failed ({error}), using the cache from "
                  f"{cache.get('fetched_at')}")
            return cache
        print(f"calendar: exchange-details unavailable ({error}) and no cache exists")
        return None

    payload = dict(details)
    payload["fetched_at"] = ettime.stamp(ettime.now_et())
    config.ensure_dirs()
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"calendar: refreshed {CACHE_PATH.name} from exchange-details")
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


def is_trading_day(date: dt.date) -> tuple[bool, str]:
    """(trades_today, reason). Unknowable counts as open, see the module doc."""
    refresh_after_days = _CRIT.integer("calendar", "refresh_after_days")
    details = get_details(refresh_after_days)
    if details is None:
        return True, "calendar unavailable, assuming the market is open"

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Is the market open today?")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Check a specific date instead of today, for testing.")
    args = parser.parse_args(argv)

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
    sys.exit(job_status.run("calendar", main, ok_codes=(0, EXIT_CLOSED)))
