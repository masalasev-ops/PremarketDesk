"""Weekly discovery universe.

Run this on Sunday evening. It answers one question: which US common stocks
are liquid enough to be worth looking at when they gap on Monday morning.

The market cap floor here is deliberately below the day setup floor in
CRITERIA.md. A 900M name that gaps 20 percent is a 1.1B name by the time the
gap is on the screen, so it has to already be in the population the night
before or the morning pass can never see it. Screening the population at the
trading threshold is how you build a universe that structurally cannot contain
the trades you are looking for.

Call cost, roughly:
    2    exchange symbol lists, NYSE and NASDAQ
    1    SPY end of day history, which supplies the real session dates
    20   bulk end of day, one per session
    ~100 delayed quotes in batches, only for names that already cleared price,
         liquidity and history, purely to attach market cap

Everything later in the day refuses to run against a stale universe. That gate
lives here in require_fresh_universe so there is one definition of stale.
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

_CRIT = criteria.load()


class StaleUniverseError(RuntimeError):
    """Raised when universe.json is missing or too old to trade against."""


def _norm_code(raw: str) -> str:
    """Bare ticker, no exchange suffix. The two bulk feeds disagree on this."""
    code = str(raw or "").strip().upper()
    return code.split(".", 1)[0] if code.endswith(".US") else code


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


# ---------------------------------------------------------------- freshness

def universe_age_days(payload: dict[str, Any]) -> float:
    generated = payload.get("generated_at")
    if not generated:
        return float("inf")
    try:
        when = dt.datetime.fromisoformat(generated)
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=ettime.ET)
    return (ettime.now_et() - when).total_seconds() / 86400.0


def load_universe(require_fresh: bool = True) -> dict[str, Any]:
    """Read universe.json, refusing a stale one and saying exactly why."""
    path = config.UNIVERSE_PATH
    max_age = _CRIT.integer("universe", "max_age_days")

    if not path.exists():
        raise StaleUniverseError(
            f"{path} does not exist. Run universe.py before anything else. "
            "Nothing downstream has a population to screen without it."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise StaleUniverseError(f"{path} could not be read: {exc}") from exc

    age = universe_age_days(payload)
    if require_fresh and age > max_age:
        stamp = payload.get("generated_at", "unknown")
        raise StaleUniverseError(
            f"{path.name} was generated at {stamp}, which is {age:.1f} days ago. "
            f"The limit in {config.CRITERIA_PATH.name} is max_age_days = {max_age}. "
            "Delistings, splits and new listings have moved since then. "
            "Re-run universe.py before trading off it."
        )
    return payload


def require_fresh_universe() -> dict[str, Any]:
    """For every later script. Refuses to run and says why, rather than guessing."""
    payload = load_universe(require_fresh=True)
    age = universe_age_days(payload)
    print(
        f"universe: {payload.get('count', 0)} names, generated {payload.get('generated_at')} "
        f"({age:.1f} days ago)"
    )
    return payload


def universe_symbols(payload: dict[str, Any]) -> list[str]:
    return [row["symbol"] for row in payload.get("symbols", []) if row.get("symbol")]


# ------------------------------------------------------------------- build

def _common_stock_index(api: eodhd.EodhdClient, notes: list[str]) -> dict[str, str]:
    """Bare ticker to exchange, common stock only.

    Everything that is not Type == Common Stock is dropped here, which is what
    removes ETFs, funds, preferreds, warrants, units, rights and notes in one
    move rather than by maintaining a suffix blacklist.
    """
    wanted_type = _CRIT.text("universe", "allowed_security_type")
    exchanges = _CRIT.text_list("universe", "exchanges")

    index: dict[str, str] = {}
    for exchange in exchanges:
        rows, error = api.exchange_symbol_list(exchange)
        if error:
            notes.append(f"exchange symbol list for {exchange} failed: {error}")
            continue
        kept = 0
        for row in rows:
            if str(row.get("Type", "")).strip().lower() != wanted_type.lower():
                continue
            code = _norm_code(row.get("Code", ""))
            if not code:
                continue
            index.setdefault(code, row.get("Exchange") or exchange)
            kept += 1
        print(f"universe: {exchange} listed {len(rows)}, kept {kept} as {wanted_type}")
    return index


def _session_dates(api: eodhd.EodhdClient, count: int, notes: list[str]) -> list[dt.date]:
    """Real trading session dates, taken from data rather than from a guess.

    Holidays are not enumerated anywhere in this project. A liquid reference
    symbol's own end of day history is the session calendar.
    """
    probe = _CRIT.text("universe", "session_calendar_symbol")
    today = ettime.today_et()
    # Enough calendar days to be sure of covering the requested sessions.
    start = today - dt.timedelta(days=count * 2 + 20)

    rows, error = api.eod(probe, start=start, end=today)
    if error or not rows:
        raise RuntimeError(
            f"could not read the session calendar from {probe}: {error or 'no rows'}"
        )

    dates = sorted({ettime.parse_date(str(r.get("date"))) for r in rows if r.get("date")})
    # Today's own session is excluded. It is either unfinished or not there.
    dates = [d for d in dates if d < today]
    if len(dates) < count:
        notes.append(
            f"session calendar only returned {len(dates)} sessions before {today}, wanted {count}"
        )
    return dates[-count:]


def _collect_bars(
    api: eodhd.EodhdClient,
    session_dates: list[dt.date],
    wanted: set[str],
    notes: list[str],
) -> dict[str, list[tuple[float, float]]]:
    """Per symbol list of (close, volume), oldest session first."""
    series: dict[str, list[tuple[float, float]]] = {}
    for day in session_dates:
        rows, error = api.eod_bulk_last_day("US", day=day)
        if error:
            notes.append(f"bulk end of day for {day} failed: {error}")
            continue
        matched = 0
        for row in rows:
            code = _norm_code(row.get("code") or row.get("Code") or "")
            if code not in wanted:
                continue
            close = _as_float(row.get("close") if "close" in row else row.get("Close"))
            volume = _as_float(row.get("volume") if "volume" in row else row.get("Volume"))
            if close is None or volume is None:
                continue
            series.setdefault(code, []).append((close, volume))
            matched += 1
        print(f"universe: {day} bulk returned {len(rows)} rows, {matched} in scope")
    return series


def _attach_market_caps(
    api: eodhd.EodhdClient,
    codes: list[str],
    notes: list[str],
) -> dict[str, float]:
    """Market cap from us-quote-delayed, the same field the morning scan reads."""
    caps: dict[str, float] = {}
    batch = _CRIT.integer("api", "quote_batch_size")
    total = len(codes)
    for start in range(0, total, batch):
        chunk = [f"{c}.US" for c in codes[start:start + batch]]
        data, error = api.quote_delayed(chunk)
        if error and not data:
            notes.append(f"market cap batch {start // batch} failed: {error}")
            continue
        for symbol, quote in (data or {}).items():
            cap = _as_float(quote.get("marketCap"))
            if cap is not None:
                caps[_norm_code(symbol)] = cap
        done = min(start + batch, total)
        if done % (batch * 25) == 0 or done == total:
            print(f"universe: market cap {done}/{total}")
    return caps


def build(write: bool = True) -> dict[str, Any]:
    config.ensure_dirs()
    api = eodhd.client()
    notes: list[str] = []

    price_rule = _CRIT.rule("universe", "price")
    dollar_volume_rule = _CRIT.rule("universe", "avg_dollar_volume_20d")
    market_cap_rule = _CRIT.rule("universe", "market_cap")
    min_sessions = _CRIT.integer("universe", "min_sessions")
    lookback = _CRIT.integer("universe", "lookback_sessions")
    count_min = _CRIT.integer("universe", "expected_count_min")
    count_max = _CRIT.integer("universe", "expected_count_max")

    print("universe: building")
    print(f"universe: admit when price {price_rule.describe()}, "
          f"20 day average dollar volume {dollar_volume_rule.describe()}, "
          f"market cap {market_cap_rule.describe()}, sessions >= {min_sessions}")

    exchange_of = _common_stock_index(api, notes)
    print(f"universe: {len(exchange_of)} common stocks across the listed exchanges")

    session_dates = _session_dates(api, lookback, notes)
    print(f"universe: {len(session_dates)} sessions, "
          f"{session_dates[0] if session_dates else 'n/a'} to "
          f"{session_dates[-1] if session_dates else 'n/a'}")

    series = _collect_bars(api, session_dates, set(exchange_of), notes)
    print(f"universe: {len(series)} symbols had at least one session")

    # Stage one, everything that costs no extra calls.
    staged: list[dict[str, Any]] = []
    for code, bars in series.items():
        sessions = len(bars)
        if sessions < min_sessions:
            continue
        price = bars[-1][0]
        if not price_rule.test(price):
            continue
        dollar_volume = sum(close * volume for close, volume in bars) / sessions
        if not dollar_volume_rule.test(dollar_volume):
            continue
        staged.append(
            {
                "code": code,
                "symbol": f"{code}.US",
                "exchange": exchange_of.get(code, "UNKNOWN"),
                "price": round(price, 4),
                "avg_dollar_volume_20d": round(dollar_volume, 2),
                "sessions": sessions,
            }
        )
    staged.sort(key=lambda row: row["avg_dollar_volume_20d"], reverse=True)
    print(f"universe: {len(staged)} cleared price, liquidity and history")

    # Stage two, the only part that spends calls per name.
    caps = _attach_market_caps(api, [row["code"] for row in staged], notes)

    admitted: list[dict[str, Any]] = []
    missing_cap = 0
    for row in staged:
        cap = caps.get(row["code"])
        if cap is None:
            missing_cap += 1
            continue
        if not market_cap_rule.test(cap):
            continue
        row["market_cap"] = round(cap, 2)
        admitted.append(row)
    if missing_cap:
        notes.append(f"{missing_cap} names were dropped because no market cap came back")

    admitted.sort(key=lambda row: row["symbol"])

    payload: dict[str, Any] = {
        "generated_at": ettime.stamp(),
        "count": len(admitted),
        "admitted_when": {
            "price": price_rule.describe(),
            "avg_dollar_volume_20d": dollar_volume_rule.describe(),
            "market_cap": market_cap_rule.describe(),
            "min_sessions": min_sessions,
            "security_type": _CRIT.text("universe", "allowed_security_type"),
            "exchanges": _CRIT.text_list("universe", "exchanges"),
        },
        "sessions": {
            "lookback": lookback,
            "used": len(session_dates),
            "first": session_dates[0].isoformat() if session_dates else None,
            "last": session_dates[-1].isoformat() if session_dates else None,
        },
        "expected_count_range": [count_min, count_max],
        "listed_common_stocks": len(exchange_of),
        "cleared_price_and_liquidity": len(staged),
        "notes": notes,
        "api_calls": eodhd.call_count(),
        "symbols": admitted,
    }

    if len(admitted) < count_min or len(admitted) > count_max:
        warning = (
            f"universe count {len(admitted)} is outside the expected range "
            f"{count_min} to {count_max}. A small result usually means the bulk feed "
            "was short, a large one usually means the security type filter let "
            "something through. Check the notes before trading off this file."
        )
        payload["count_warning"] = warning
        print(f"WARNING  {warning}")

    if write:
        config.UNIVERSE_PATH.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        print(f"universe: wrote {config.UNIVERSE_PATH} with {len(admitted)} names")

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the weekly discovery universe.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not rebuild. Report whether the existing universe.json is fresh.",
    )
    args = parser.parse_args(argv)

    if args.check:
        try:
            payload = require_fresh_universe()
        except StaleUniverseError as exc:
            print(f"REFUSING TO RUN: {exc}")
            eodhd.print_call_report()
            return 1
        print(f"universe: fresh, {payload['count']} names")
        eodhd.print_call_report()
        return 0

    try:
        payload = build()
    except RuntimeError as exc:
        print(f"universe: build failed, {exc}")
        eodhd.print_call_report()
        return 1

    for note in payload["notes"]:
        print(f"universe note: {note}")
    eodhd.print_call_report()
    count_min, count_max = payload["expected_count_range"]
    return 0 if count_min <= payload["count"] <= count_max else 1


if __name__ == "__main__":
    raise SystemExit(main())
