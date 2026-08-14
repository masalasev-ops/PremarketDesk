"""Premarket volume baseline, cached and never fetched in the morning.

Premarket relative volume needs a denominator, and the honest denominator is
"how much volume did this name normally have done by this exact clock time".
Not full day average volume. A name that has traded 400k shares by 08:45 is
either interesting or ordinary depending entirely on what it usually does by
08:45, and the two questions have different answers.

So for each ticker and each cutoff time we sum volume from 04:00 ET to the
cutoff across the prior twenty sessions and keep the median. The median rather
than the mean, because one earnings morning in the window would drag a mean
somewhere useless.

This is a nightly or on demand job. The 08:45 scan reads the cache and never
computes, because spending twenty seconds per name fetching a month of minute
bars is not something you do while the market is about to open. A cache entry
older than refresh_after_days is recomputed, everything else is free.
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
from typing import Any

import config
import criteria
import eodhd
import ettime
import store

_CRIT = criteria.load()

LOOKBACK_SESSIONS = _CRIT.integer("baseline", "lookback_sessions")
SESSION_START = _CRIT.clock("baseline", "session_start")
REFRESH_AFTER_DAYS = _CRIT.integer("baseline", "refresh_after_days")
MIN_SESSIONS_FOR_RVOL = _CRIT.integer("baseline", "min_sessions_for_rvol")


def normalize_cutoff(value: str | tuple[int, int]) -> str:
    """Cutoffs are stored as HH:MM in ET so the table is readable by hand."""
    if isinstance(value, tuple):
        return f"{value[0]:02d}:{value[1]:02d}"
    text = str(value).strip()
    if ":" not in text and len(text) == 4:
        text = f"{text[:2]}:{text[2:]}"
    hour, _, minute = text.partition(":")
    return f"{int(hour):02d}:{int(minute):02d}"


def _cutoff_minutes(cutoff: str) -> int:
    hour, minute = cutoff.split(":")
    return int(hour) * 60 + int(minute)


def _start_minutes() -> int:
    return SESSION_START[0] * 60 + SESSION_START[1]


# ------------------------------------------------------------------- reading

def get(ticker: str, cutoff: str, connection=None) -> dict[str, Any] | None:
    if connection is None:
        with store.session() as owned:
            return get(ticker, cutoff, owned)
    cutoff = normalize_cutoff(cutoff)
    store.init(connection)
    row = connection.execute(
        "SELECT * FROM baseline WHERE ticker=? AND cutoff_hhmm=?",
        (ticker.upper(), cutoff),
    ).fetchone()
    return dict(row) if row else None


def is_fresh(row: dict[str, Any] | None) -> bool:
    if not row or not row.get("computed_at"):
        return False
    try:
        computed = dt.datetime.fromisoformat(row["computed_at"])
    except ValueError:
        return False
    if computed.tzinfo is None:
        computed = computed.replace(tzinfo=ettime.ET)
    age_days = (ettime.now_et() - computed).total_seconds() / 86400.0
    return age_days <= REFRESH_AFTER_DAYS


def usable_for_rvol(row: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Whether this baseline may be used as an RVOL denominator, and why not."""
    if not row:
        return False, "no cached baseline for this ticker and cutoff"
    sessions = int(row.get("sessions_used") or 0)
    if sessions < MIN_SESSIONS_FOR_RVOL:
        return False, (
            f"baseline used only {sessions} sessions, the minimum is {MIN_SESSIONS_FOR_RVOL}"
        )
    median = row.get("median_volume")
    if median is None or median <= 0:
        return False, "baseline median volume is zero or missing"
    return True, None


# ----------------------------------------------------------------- computing

def compute(
    api: eodhd.EodhdClient, ticker: str, cutoff: str
) -> tuple[float | None, int, dict[str, float], str | None]:
    """Sum 04:00 to cutoff volume per session and return the median.

    One intraday call covers the whole window. Session dates are taken from the
    bars themselves, so holidays need no table and never count as a zero volume
    session.
    """
    cutoff = normalize_cutoff(cutoff)
    start_minute = _start_minutes()
    end_minute = _cutoff_minutes(cutoff)
    if end_minute <= start_minute:
        return None, 0, {}, f"cutoff {cutoff} is not after the session start"

    today = ettime.today_et()
    # Enough calendar days to be confident of covering the requested sessions.
    window_start = ettime.at(today - dt.timedelta(days=LOOKBACK_SESSIONS * 2 + 5), 0, 0)
    window_end = ettime.at(today, 0, 0)

    rows, error = api.intraday(ticker, window_start, window_end, "1m")
    if error:
        return None, 0, {}, error
    if not rows:
        return None, 0, {}, f"no intraday bars returned for {ticker}"

    per_session: dict[str, float] = {}
    session_seen: set[str] = set()
    for row in rows:
        stamp = row.get("timestamp")
        if stamp is None:
            continue
        when = ettime.from_epoch_s(stamp)
        if when is None or when.date() >= today:
            continue
        day = when.date().isoformat()
        session_seen.add(day)
        minute_of_day = when.hour * 60 + when.minute
        if start_minute <= minute_of_day < end_minute:
            try:
                per_session[day] = per_session.get(day, 0.0) + float(row.get("volume") or 0)
            except (TypeError, ValueError):
                continue

    # Any date with bars was a trading day. A genuine zero premarket volume is
    # a real observation and is kept, rather than being filtered into optimism.
    for day in session_seen:
        per_session.setdefault(day, 0.0)

    ordered = sorted(per_session)[-LOOKBACK_SESSIONS:]
    volumes = [per_session[day] for day in ordered]
    if not volumes:
        return None, 0, {}, f"no sessions in the window for {ticker}"

    note = None
    if len(volumes) < LOOKBACK_SESSIONS:
        note = (
            f"only {len(volumes)} sessions available, wanted {LOOKBACK_SESSIONS}"
        )
    return statistics.median(volumes), len(volumes), {d: per_session[d] for d in ordered}, note


def ensure(
    api: eodhd.EodhdClient | None,
    ticker: str,
    cutoff: str,
    force: bool = False,
    connection=None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return a baseline row, computing it only when the cache is stale.

    A fresh cache entry costs zero API calls. That is the whole point: the
    morning run must never wait on this.
    """
    if connection is None:
        with store.session() as owned:
            return ensure(api, ticker, cutoff, force=force, connection=owned)
    ticker = ticker.upper()
    cutoff = normalize_cutoff(cutoff)
    store.init(connection)
    existing = get(ticker, cutoff, connection)
    if existing and is_fresh(existing) and not force:
        return existing, None

    if api is None:
        return existing, "cache is stale and no API client was supplied"

    median, sessions_used, _per_session, note = compute(api, ticker, cutoff)
    if median is None:
        # Keep a stale row rather than throwing away the only number we have.
        return existing, note or f"could not compute a baseline for {ticker}"

    values = {
        "ticker": ticker,
        "cutoff_hhmm": cutoff,
        "median_volume": float(median),
        "sessions_used": int(sessions_used),
        "computed_at": ettime.stamp(),
    }
    store.upsert(connection, "baseline", ["ticker", "cutoff_hhmm"], values)
    connection.commit()
    return get(ticker, cutoff, connection), note


def warm(tickers: list[str], cutoff: str, force: bool = False) -> dict[str, Any]:
    """Populate the cache for a list of tickers ahead of the morning."""
    api = eodhd.client()
    cutoff = normalize_cutoff(cutoff)
    computed = 0
    cached = 0
    failed: list[str] = []

    with store.session() as connection:
        store.init(connection)
        for ticker in tickers:
            before = eodhd.call_count()
            row, note = ensure(api, ticker, cutoff, force=force, connection=connection)
            spent = eodhd.call_count() - before
            if row is None:
                failed.append(f"{ticker}: {note}")
                print(f"baseline: {ticker:<10} FAILED  {note}")
                continue
            if spent:
                computed += 1
                print(
                    f"baseline: {ticker:<10} computed median {row['median_volume']:>12,.0f} "
                    f"from {row['sessions_used']} sessions"
                    + (f"  ({note})" if note else "")
                )
            else:
                cached += 1
    print(f"baseline: {computed} computed, {cached} already fresh, {len(failed)} failed")
    return {"computed": computed, "cached": cached, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Premarket volume baseline cache.")
    parser.add_argument("--ticker", action="append", default=[],
                        help="Ticker to warm, repeatable. Defaults to the watchlist.")
    parser.add_argument("--cutoff", default=None,
                        help="Clock cutoff in ET, defaults to the CRITERIA.md scan run time.")
    parser.add_argument("--force", action="store_true", help="Recompute even if fresh.")
    parser.add_argument("--show", action="store_true", help="Print the cache and exit.")
    args = parser.parse_args(argv)

    cutoff = normalize_cutoff(args.cutoff or _CRIT.clock("scan", "run_time"))

    if args.show:
        store.init()
        with store.session() as connection:
            rows = connection.execute(
                "SELECT * FROM baseline ORDER BY ticker, cutoff_hhmm"
            ).fetchall()
        print(f"{'ticker':<12} {'cutoff':<7} {'median volume':>15} {'sessions':>9}  computed_at")
        for row in rows:
            print(f"{row['ticker']:<12} {row['cutoff_hhmm']:<7} "
                  f"{row['median_volume'] or 0:>15,.0f} {row['sessions_used']:>9}  "
                  f"{row['computed_at']}")
        print(f"{len(rows)} rows")
        return 0

    tickers = [t.upper() for t in args.ticker]
    if not tickers:
        import discover

        watchlist = discover.load_watchlist()
        tickers = [r["symbol"] for r in watchlist.get("symbols", []) if r.get("symbol")]
        tickers += [
            s if "." in s else f"{s}.US"
            for s in _CRIT.text_list("collector", "context_symbols")
        ]
    if not tickers:
        print("baseline: nothing to warm. Pass --ticker or run discover.py first.")
        return 1

    # The warm is skippable spend: one intraday call per stale ticker, up to
    # the whole watchlist plus the context symbols. The scan survives a cold
    # baseline honestly (pm_rvol null with the reason recorded), so on a
    # degraded shared meter this job stands down rather than burn the calls
    # the 08:45 scan needs for the packet. Exit 0 either way: a skipped warm
    # is a completed job, not a failed one, and must not trip the watchdog.
    quota = eodhd.preflight("baseline")
    if quota["degraded"]:
        print("baseline: standing down without warming anything. The warm is "
              "skippable spend and the reading above says the shared key cannot "
              "afford it; the scan will record null RVOL with this reason for "
              "any name whose cache is stale.")
        eodhd.print_call_report()
        return 0

    print(f"baseline: cutoff {cutoff} ET, {len(tickers)} tickers, "
          f"{LOOKBACK_SESSIONS} session lookback, refresh after {REFRESH_AFTER_DAYS} days")
    warm(tickers, cutoff, force=args.force)
    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
