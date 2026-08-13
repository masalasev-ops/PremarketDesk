"""US Eastern clock helpers.

Everything in this project is scheduled and reasoned about in US Eastern time,
so there is exactly one place that knows how to build one.

Windows ships no IANA time zone database, and the tzdata package is not one of
the three dependencies this project is allowed. So zoneinfo is tried first and
a small fixed rule implementation is used when it is not available. The rule
has been stable since the Energy Policy Act of 2005 took effect in 2007:
daylight time starts on the second Sunday in March at 02:00 local and ends on
the first Sunday in November at 02:00 local.

If tzdata ever lands in the environment, zoneinfo wins automatically and this
fallback stops being used.
"""

from __future__ import annotations

import datetime as dt

_ZERO = dt.timedelta(0)
_HOUR = dt.timedelta(hours=1)
_STD_OFFSET = dt.timedelta(hours=-5)
_DST_OFFSET = dt.timedelta(hours=-4)

# Transition points expressed in local wall clock terms, year filled in later.
# Second Sunday in March, first Sunday in November, both at 02:00.
_DST_START_MONTH, _DST_START_WEEK = 3, 2
_DST_END_MONTH, _DST_END_WEEK = 11, 1
_TRANSITION_HOUR = 2
_SUNDAY = 6


def _nth_sunday(year: int, month: int, nth: int) -> dt.datetime:
    """The nth Sunday of a month at the transition hour, naive local."""
    first = dt.datetime(year, month, 1, _TRANSITION_HOUR)
    days_ahead = (_SUNDAY - first.weekday()) % 7
    return first + dt.timedelta(days=days_ahead + 7 * (nth - 1))


class _USEasternFallback(dt.tzinfo):
    """US Eastern under the post 2007 daylight saving rule."""

    def utcoffset(self, when: dt.datetime | None) -> dt.timedelta:
        return _DST_OFFSET if self._is_dst(when) else _STD_OFFSET

    def dst(self, when: dt.datetime | None) -> dt.timedelta:
        return _HOUR if self._is_dst(when) else _ZERO

    def tzname(self, when: dt.datetime | None) -> str:
        return "EDT" if self._is_dst(when) else "EST"

    def _is_dst(self, when: dt.datetime | None) -> bool:
        if when is None:
            return False
        naive = when.replace(tzinfo=None)
        start = _nth_sunday(naive.year, _DST_START_MONTH, _DST_START_WEEK)
        end = _nth_sunday(naive.year, _DST_END_MONTH, _DST_END_WEEK)
        return start <= naive < end

    def __repr__(self) -> str:
        return "US/Eastern (fixed rule fallback)"


def _build_eastern() -> dt.tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/New_York")
    except Exception:
        return _USEasternFallback()


ET = _build_eastern()
UTC = dt.timezone.utc

TZ_SOURCE = "zoneinfo" if ET.__class__.__name__ == "ZoneInfo" else "fixed rule fallback"


def now_et() -> dt.datetime:
    return dt.datetime.now(tz=ET)


def today_et() -> dt.date:
    return now_et().date()


def today_str() -> str:
    return today_et().isoformat()


def at(day: dt.date, hour: int, minute: int = 0, second: int = 0) -> dt.datetime:
    """An aware ET datetime on the given day."""
    return dt.datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ET)


def at_hm(day: dt.date, hhmm: tuple[int, int]) -> dt.datetime:
    return at(day, hhmm[0], hhmm[1])


def to_et(when: dt.datetime) -> dt.datetime:
    """Convert any datetime to ET. A naive value is assumed to be UTC."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(ET)


def from_epoch_s(seconds: float | int | None) -> dt.datetime | None:
    if seconds is None:
        return None
    return dt.datetime.fromtimestamp(float(seconds), tz=UTC).astimezone(ET)


def from_epoch_ms(millis: float | int | None) -> dt.datetime | None:
    if millis is None:
        return None
    return from_epoch_s(float(millis) / 1000.0)


def epoch_s(when: dt.datetime) -> int:
    if when.tzinfo is None:
        when = when.replace(tzinfo=ET)
    return int(when.timestamp())


def epoch_ms(when: dt.datetime) -> int:
    return epoch_s(when) * 1000


def stamp(when: dt.datetime | None = None) -> str:
    """ISO 8601 with the ET offset attached. Used for every generated_at field."""
    return (when or now_et()).isoformat(timespec="seconds")


def hhmm(when: dt.datetime) -> str:
    return when.strftime("%H:%M")


def parse_date(text: str) -> dt.date:
    return dt.date.fromisoformat(text[:10])


def is_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def previous_weekdays(count: int, before: dt.date | None = None) -> list[dt.date]:
    """Weekdays strictly before the given day, newest first.

    Weekdays are not trading days. Market holidays are handled by taking the
    session dates from the data the API actually returned, never by guessing
    here. This helper only exists to bound a request window.
    """
    day = before or today_et()
    out: list[dt.date] = []
    while len(out) < count:
        day -= dt.timedelta(days=1)
        if is_weekday(day):
            out.append(day)
    return out


def _self_check() -> int:
    print(f"tz source     {TZ_SOURCE} ({ET!r})")
    now = now_et()
    print(f"now ET        {stamp(now)}  {now.tzname()}")
    print(f"today         {today_str()}")
    print(f"0400 ET today {stamp(at(today_et(), 4, 0))}")
    print(f"0930 ET today {stamp(at(today_et(), 9, 30))}")

    # Both sides of both 2026 transitions, checked against the known offsets.
    checks = [
        (dt.datetime(2026, 1, 15, 9, 30), "EST", -5),
        (dt.datetime(2026, 3, 7, 9, 30), "EST", -5),
        (dt.datetime(2026, 3, 9, 9, 30), "EDT", -4),
        (dt.datetime(2026, 7, 1, 9, 30), "EDT", -4),
        (dt.datetime(2026, 10, 30, 9, 30), "EDT", -4),
        (dt.datetime(2026, 11, 2, 9, 30), "EST", -5),
    ]
    failures = 0
    for naive, want_name, want_hours in checks:
        aware = naive.replace(tzinfo=ET)
        offset_hours = aware.utcoffset().total_seconds() / 3600
        ok = aware.tzname() == want_name and offset_hours == want_hours
        failures += 0 if ok else 1
        print(
            f"  {naive:%Y-%m-%d}  {aware.tzname():<4} UTC{offset_hours:+.0f}  "
            f"{'ok' if ok else 'FAIL expected ' + want_name}"
        )

    round_trip = from_epoch_ms(1784147337000)
    print(f"epoch ms 1784147337000 -> {stamp(round_trip)}")
    print("OK" if failures == 0 else f"FAIL {failures} transition checks")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_self_check())
