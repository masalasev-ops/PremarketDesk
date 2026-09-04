"""Measure what Alpaca's market data API actually serves, and BE the client that uses it.

**[corrected 2026-08-21: this file opened with "Standalone by construction.
Nothing imports this module." That was true when it was written and is now
false four times over, and the correction matters more than most because of
WHO imports it. night/true_volume.py is a scheduled nightly step, and its
Probe and build_session are how the record's premarket volume is fetched. A
reader who took the old sentence at face value would feel free to delete this
file, or to restructure Probe.get, and would break the only measurement that
says how wrong the morning's estimate was.

The four importers, so they can be found rather than guessed at:

  night/true_volume.py            PRODUCTION. The 22:15 truth pass.
  research/float_rotation_study.py  the Alpaca volume the shipped rotation
                                    bands were fitted on
  research/vwap_gappers.py        a closed study, kept because the code that
                                    produced a recorded result is part of it
  tests/conftest.py               swaps build_session for a blocked one, so
                                    the hermetic suite cannot reach Alpaca

What is still true: this imports no data client of its own, and main() writes
nothing except doc/ALPACA_PROBE.md. The module is now two things, a probe and
a transport, and only the first half is optional.]**

The measurement half runs against the most recent completed trading day, so it
needs no live premarket session and can be run and rerun on a weekend. Its
answers are in doc/ALPACA_PROBE.md, which CRITERIA [Truth] now rests on for the
one fact the truth pass depends on: the free plan serves the sip feed for a
session that is over and refuses it for one that is running.

It reads ALPACA_KEY_ID and ALPACA_SECRET_KEY from .env through config, so the
keys are never typed into a shell and never printed. It writes nothing except
doc/ALPACA_PROBE.md.

Run:

    PYTHONPATH=src .venv/Scripts/python.exe -m probe_alpaca
"""

from __future__ import annotations

import datetime as dt
import statistics
import time
from typing import Any

import requests

from core import config, ettime, files

# The premarket window this project cares about. 08:30 rather than 09:30
# because the report has to be written before the open, so what matters is
# what the vendor knows early, not what it knows by the bell.
WINDOW_START_HM = (4, 0)
WINDOW_END_HM = (8, 30)

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"

# Alpaca's documented ceiling for bars per page. Asking for the maximum keeps
# the page count, and therefore the round trip count, as low as the vendor allows.
PAGE_LIMIT = 10000

BATCH_SIZES_TO_TRY = (100, 500, 1000, 2000)

# A backstop against a pagination loop that never terminates. If a sweep ever
# reaches this the report says so, because a truncated sweep that reports a
# total looks exactly like a complete one.
MAX_PAGES_PER_CHUNK = 400

REQUEST_TIMEOUT_S = 90.0


class _TlsAdapter(requests.adapters.HTTPAdapter):
    """Carries our SSLContext into urllib3 so the trust decision actually applies.

    Same shape as the one in core/eodhd.py. Duplicated rather than imported
    because importing that module drags in the EODHD call ledger and prints an
    EODHD call report at exit, which would be noise in an Alpaca probe.
    """

    def __init__(self, context, **kwargs) -> None:
        self._context = context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._context
        return super().proxy_manager_for(*args, **kwargs)


def build_session() -> requests.Session:
    """A verifying session that also works behind a local TLS inspector."""
    session = requests.Session()
    session.headers.update({
        "APCA-API-KEY-ID": config.require("ALPACA_KEY_ID"),
        "APCA-API-SECRET-KEY": config.require("ALPACA_SECRET_KEY"),
        "User-Agent": "PremarketDesk-probe/1.0",
    })
    session.verify = config.ca_bundle()
    session.mount("https://", _TlsAdapter(config.tls_context()))
    return session


class Probe:
    """One session, and the counters every question reports against."""

    def __init__(self) -> None:
        self.session = build_session()
        self.request_count = 0
        self.retry_count = 0
        self.durations: list[float] = []
        self.last_headers: dict[str, str] = {}

    def get(self, params: dict[str, Any]) -> tuple[int, Any, float]:
        """One GET, timed and counted. Never raises, so a failure is data too."""
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                response = self.session.get(
                    BARS_URL, params=params, timeout=REQUEST_TIMEOUT_S
                )
                elapsed = time.monotonic() - started
                self.request_count += 1
                self.durations.append(elapsed)
                self.last_headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                }
                # A 429 is worth exactly one polite retry. More than that and
                # the honest answer is that the rate limit binds, which is
                # itself one of the seven questions.
                if response.status_code == 429 and attempt == 1:
                    self.retry_count += 1
                    time.sleep(float(response.headers.get("retry-after") or 2))
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    payload = {"_raw": response.text[:400]}
                return response.status_code, payload, elapsed
            except requests.RequestException as exc:
                elapsed = time.monotonic() - started
                self.request_count += 1
                self.durations.append(elapsed)
                return 0, {"_exception": config.scrub_secrets(exc)[:400]}, elapsed


def _window(day: dt.date) -> tuple[str, str]:
    """The 04:00 to 08:30 ET window on one day, as RFC3339 with a real offset."""
    start = ettime.at_hm(day, WINDOW_START_HM)
    end = ettime.at_hm(day, WINDOW_END_HM)
    return start.isoformat(), end.isoformat()


def _error_text(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("message", "_exception", "_raw", "error"):
            if payload.get(key):
                return str(payload[key])[:300]
    return str(payload)[:300]


def _count_bars(payload: Any) -> tuple[int, int]:
    """(total bars, symbols carrying at least one bar) in one response page."""
    bars = (payload or {}).get("bars") or {}
    if not isinstance(bars, dict):
        return 0, 0
    total = sum(len(rows or []) for rows in bars.values())
    present = sum(1 for rows in bars.values() if rows)
    return total, present


def load_universe() -> list[dict[str, Any]]:
    """The weekly discovery population, as rows so liquidity is available too."""
    import json

    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    return list(payload.get("symbols") or [])


def find_last_trading_day(probe: Probe) -> tuple[dt.date, str]:
    """Walk back until a day whose regular session actually printed bars.

    Measured rather than looked up. A holiday calendar would be another
    assumption to verify, and asking the vendor whether SPY traded that day
    answers the question directly and in the vendor's own terms.
    """
    day = ettime.today_et()
    for _ in range(10):
        day = day - dt.timedelta(days=1)
        if not ettime.is_weekday(day):
            continue
        status, payload, _ = probe.get({
            "symbols": "SPY",
            "timeframe": "1Min",
            "start": ettime.at_hm(day, (9, 30)).isoformat(),
            "end": ettime.at_hm(day, (16, 0)).isoformat(),
            "limit": 10,
            "feed": "sip",
        })
        total, _present = _count_bars(payload)
        if status == 200 and total:
            return day, f"SPY printed {total} regular session bars, status {status}"
    raise SystemExit("could not find a completed trading day in the last 10 days")


# ------------------------------------------------------------------ question 1

def _feed_volume(probe: Probe, symbol: str, start: str, end: str, feed: str) -> dict[str, Any]:
    """Total volume and bar count for one symbol, one feed, one window."""
    volume = 0.0
    bars = 0
    status_seen = None
    error = None
    token = None
    while True:
        params = {
            "symbols": symbol,
            "timeframe": "1Min",
            "start": start,
            "end": end,
            "limit": PAGE_LIMIT,
            "feed": feed,
        }
        if token:
            params["page_token"] = token
        status, payload, _ = probe.get(params)
        status_seen = status
        if status != 200:
            error = _error_text(payload)
            break
        rows = ((payload.get("bars") or {}).get(symbol)) or []
        bars += len(rows)
        volume += sum(float(r.get("v") or 0) for r in rows)
        token = payload.get("next_page_token")
        if not token:
            break
    return {"volume": volume, "bars": bars, "status": status_seen, "error": error}


def q1_sip_versus_iex(probe: Probe, day: dt.date) -> dict[str, Any]:
    """One liquid symbol, both feeds, same window. The ratio is the answer.

    Measured twice. The premarket window is the one the question asks about,
    but a ratio there is only interpretable against a control: IEX returning
    nothing at 05:00 means something different if IEX also returns nothing at
    10:00. The regular session pass is that control, and it is what makes the
    ratio a number rather than a division by zero.
    """
    symbol = "AAPL"
    pre_start, pre_end = _window(day)
    reg_start = ettime.at_hm(day, (10, 0)).isoformat()
    reg_end = ettime.at_hm(day, (11, 0)).isoformat()

    out: dict[str, Any] = {"symbol": symbol}
    for label, start, end in (
        ("premarket", pre_start, pre_end),
        ("regular", reg_start, reg_end),
    ):
        for feed in ("sip", "iex"):
            measured = _feed_volume(probe, symbol, start, end, feed)
            out[f"{label}_{feed}_volume"] = measured["volume"]
            out[f"{label}_{feed}_bars"] = measured["bars"]
            out[f"{label}_{feed}_status"] = measured["status"]
            if measured["error"]:
                out[f"{label}_{feed}_error"] = measured["error"]
        iex_volume = out.get(f"{label}_iex_volume") or 0
        sip_volume = out.get(f"{label}_sip_volume") or 0
        out[f"{label}_ratio"] = (
            round(sip_volume / iex_volume, 4) if iex_volume else None
        )
    return out


# ------------------------------------------------------------------ question 2

def q2_absent_symbols(probe: Probe, day: dt.date, universe: list[dict[str, Any]]) -> dict[str, Any]:
    """Do names that did not trade simply fall out of the response.

    The discovery design rests on this: if a silent symbol is absent rather
    than present with a zero, then absence is the signal and no separate
    liquidity filter is needed. Chosen from universe.json by measured dollar
    volume so the pick is reproducible rather than a hunch.
    """
    ranked = sorted(
        (row for row in universe if row.get("avg_dollar_volume_20d")),
        key=lambda row: float(row["avg_dollar_volume_20d"]),
    )
    illiquid = ranked[:3]
    liquid = ranked[-3:]
    picks = [row["code"] for row in liquid] + [row["code"] for row in illiquid]

    start, end = _window(day)
    status, payload, _ = probe.get({
        "symbols": ",".join(picks),
        "timeframe": "1Min",
        "start": start,
        "end": end,
        "limit": PAGE_LIMIT,
        "feed": "sip",
    })
    bars = (payload.get("bars") or {}) if status == 200 else {}
    detail = []
    for row in liquid + illiquid:
        code = row["code"]
        rows = bars.get(code)
        detail.append({
            "symbol": code,
            "group": "liquid" if row in liquid else "illiquid",
            "avg_dollar_volume_20d": row.get("avg_dollar_volume_20d"),
            "key_present": code in bars,
            "bars": len(rows or []) if rows is not None else 0,
        })

    # A deliberately invalid ticker, reported separately so the six name answer
    # above stays exactly the test that was asked for. Worth knowing whether a
    # bad symbol poisons the whole batch or is simply omitted like a quiet one.
    bogus_status, bogus_payload, _ = probe.get({
        "symbols": "AAPL,ZZZZQQ",
        "timeframe": "1Min",
        "start": start,
        "end": end,
        "limit": 5,
        "feed": "sip",
    })
    bogus_bars = (bogus_payload.get("bars") or {}) if bogus_status == 200 else {}

    return {
        "status": status,
        "error": None if status == 200 else _error_text(payload),
        "detail": detail,
        "keys_returned": sorted(bars.keys()),
        "bogus": {
            "status": bogus_status,
            "keys_returned": sorted(bogus_bars.keys()),
            "error": None if bogus_status == 200 else _error_text(bogus_payload),
        },
    }


# ------------------------------------------------------------------ question 3

def q3_batch_sizes(probe: Probe, day: dt.date, universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How many symbols fit in one request, measured by trying until it breaks."""
    codes = [row["code"] for row in universe]
    start, end = _window(day)
    results = []
    for size in BATCH_SIZES_TO_TRY:
        if size > len(codes):
            results.append({"size": size, "status": None, "note": "universe smaller than batch"})
            continue
        symbols = ",".join(codes[:size])
        status, payload, elapsed = probe.get({
            "symbols": symbols,
            "timeframe": "1Min",
            "start": start,
            "end": end,
            "limit": PAGE_LIMIT,
            "feed": "sip",
        })
        total, present = _count_bars(payload)
        results.append({
            "size": size,
            "status": status,
            "url_chars": len(symbols),
            "ok": status == 200,
            "bars_first_page": total,
            "symbols_with_bars_first_page": present,
            "seconds": round(elapsed, 3),
            "error": None if status == 200 else _error_text(payload),
        })
    return results


# ------------------------------------------------------------- questions 4,5,7

def sweep(
    probe: Probe,
    day: dt.date,
    universe: list[dict[str, Any]],
    timeframe: str,
    batch_size: int,
) -> dict[str, Any]:
    """One full universe sweep. Returns payload size, pages and wall clock."""
    codes = [row["code"] for row in universe]
    start, end = _window(day)
    started = time.monotonic()

    before_requests = probe.request_count
    before_durations = len(probe.durations)

    total_bars = 0
    symbols_with_bars: set[str] = set()
    pages = 0
    largest_page = 0
    truncated_chunks = 0
    errors: list[str] = []

    for index in range(0, len(codes), batch_size):
        chunk = codes[index:index + batch_size]
        token = None
        chunk_pages = 0
        while True:
            params = {
                "symbols": ",".join(chunk),
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": PAGE_LIMIT,
                "feed": "sip",
            }
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            pages += 1
            chunk_pages += 1
            if status != 200:
                errors.append(f"chunk at {index}: status {status}: {_error_text(payload)}")
                break
            page_bars, _present = _count_bars(payload)
            total_bars += page_bars
            largest_page = max(largest_page, page_bars)
            for symbol, rows in ((payload.get("bars") or {}).items()):
                if rows:
                    symbols_with_bars.add(symbol)
            token = payload.get("next_page_token")
            if not token:
                break
            if chunk_pages >= MAX_PAGES_PER_CHUNK:
                truncated_chunks += 1
                errors.append(
                    f"chunk at {index}: stopped at the {MAX_PAGES_PER_CHUNK} page backstop "
                    "with a next_page_token still outstanding, so this sweep is incomplete"
                )
                break

    wall = time.monotonic() - started
    durations = probe.durations[before_durations:]
    return {
        "timeframe": timeframe,
        "batch_size": batch_size,
        "symbols_requested": len(codes),
        "total_bars": total_bars,
        "symbols_with_bars": len(symbols_with_bars),
        "symbol_set": symbols_with_bars,
        "pages": pages,
        "largest_page_bars": largest_page,
        "requests": probe.request_count - before_requests,
        "wall_clock_s": round(wall, 2),
        "request_min_s": round(min(durations), 3) if durations else None,
        "request_median_s": round(statistics.median(durations), 3) if durations else None,
        "request_max_s": round(max(durations), 3) if durations else None,
        "truncated_chunks": truncated_chunks,
        "complete": truncated_chunks == 0 and not errors,
        "errors": errors[:8],
    }


def q7_boundary_bleed(
    probe: Probe, day: dt.date, extra_symbols: list[str]
) -> dict[str, Any]:
    """Why the hourly sweep reports MORE symbols than the minute sweep.

    An hourly bar is returned when its START falls inside the window, but the
    bar aggregates the whole hour, so the 08:00 bar carries trades up to 09:00.
    That makes the hourly sweep look like it covers 04:00 to 08:30 while
    actually reaching past the boundary. This measures how much of the extra
    symbol count is that bleed rather than real premarket activity.
    """
    if not extra_symbols:
        return {"extra_symbols": 0, "first_bar_after_window_end": 0, "samples": []}

    window_end = ettime.at_hm(day, WINDOW_END_HM)
    start = ettime.at_hm(day, WINDOW_START_HM).isoformat()
    end = ettime.at_hm(day, (WINDOW_END_HM[0] + 1, 0)).isoformat()

    first_bar_at: dict[str, dt.datetime] = {}
    for index in range(0, len(extra_symbols), 500):
        chunk = extra_symbols[index:index + 500]
        token = None
        while True:
            params = {
                "symbols": ",".join(chunk),
                "timeframe": "1Min",
                "start": start,
                "end": end,
                "limit": PAGE_LIMIT,
                "feed": "sip",
            }
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            if status != 200:
                break
            for symbol, rows in ((payload.get("bars") or {}).items()):
                for row in rows or []:
                    when = ettime.to_et(
                        dt.datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00"))
                    )
                    if symbol not in first_bar_at or when < first_bar_at[symbol]:
                        first_bar_at[symbol] = when
            token = payload.get("next_page_token")
            if not token:
                break

    after = [s for s, when in first_bar_at.items() if when >= window_end]
    samples = [
        {"symbol": s, "first_1min_bar_et": first_bar_at[s].strftime("%H:%M")}
        for s in sorted(after)[:5]
    ]
    return {
        "extra_symbols": len(extra_symbols),
        "with_any_1min_bar_in_widened_window": len(first_bar_at),
        "first_bar_after_window_end": len(after),
        "samples": samples,
    }


# ------------------------------------------------------------------ reporting

def _fmt(value: Any) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".") if value % 1 else f"{int(value):,}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def write_report(path, day: dt.date, day_note: str, results: dict[str, Any]) -> None:
    q1 = results["q1"]
    q2 = results["q2"]
    q3 = results["q3"]
    q4 = results["q4"]
    q7 = results["q7"]
    headers = results["q6"]["headers"]

    lines: list[str] = []
    add = lines.append

    add("# Alpaca probe")
    add("")
    add(f"Measured {ettime.stamp(ettime.now_et())}")
    add("")
    add(f"Trading day probed: **{day.isoformat()}** ({day_note})")
    add(f"Window: {WINDOW_START_HM[0]:02d}:{WINDOW_START_HM[1]:02d} to "
        f"{WINDOW_END_HM[0]:02d}:{WINDOW_END_HM[1]:02d} ET")
    add(f"Universe: {results['universe_size']:,} symbols from data/universe.json")
    add("")
    add("Every number below was observed. Nothing here is inferred from documentation.")
    add("")

    add("## 1. Does the free plan actually serve SIP")
    add("")
    add(f"Symbol {q1['symbol']}, one feed against the other, measured in two windows. "
        "The regular session pass is a control: without it, IEX returning nothing "
        "in premarket cannot be told apart from IEX not being served at all.")
    add("")
    add("| Window | Feed | Bars | Volume | Status |")
    add("| --- | --- | ---: | ---: | ---: |")
    for label in ("premarket", "regular"):
        for feed in ("sip", "iex"):
            add(f"| {label} | {feed} | {_fmt(q1.get(f'{label}_{feed}_bars'))} | "
                f"{_fmt(q1.get(f'{label}_{feed}_volume'))} | "
                f"{q1.get(f'{label}_{feed}_status')} |")
    add("")
    add(f"**SIP to IEX volume ratio, regular session control: "
        f"{q1.get('regular_ratio')}**")
    add("")
    pre_ratio = q1.get("premarket_ratio")
    if pre_ratio is None:
        add(f"**SIP to IEX volume ratio, premarket window: undefined. IEX returned "
            f"{_fmt(q1.get('premarket_iex_bars'))} bars and "
            f"{_fmt(q1.get('premarket_iex_volume'))} shares, so the denominator is zero "
            f"while SIP returned {_fmt(q1.get('premarket_sip_volume'))} shares.**")
    else:
        add(f"**SIP to IEX volume ratio, premarket window: {pre_ratio}**")
    add("")
    for label in ("premarket", "regular"):
        for feed in ("sip", "iex"):
            if q1.get(f"{label}_{feed}_error"):
                add(f"{label} {feed} error: {q1[f'{label}_{feed}_error']}")
                add("")

    add("## 2. Do non-trading symbols return nothing")
    add("")
    add("| Symbol | Group | 20d dollar volume | Key present in response | Bars |")
    add("| --- | --- | ---: | --- | ---: |")
    for row in q2["detail"]:
        add(f"| {row['symbol']} | {row['group']} | {_fmt(row['avg_dollar_volume_20d'])} | "
            f"{row['key_present']} | {_fmt(row['bars'])} |")
    add("")
    add(f"Keys returned: {', '.join(q2['keys_returned']) or 'none'}")
    add("")
    add(f"Extra observation, an invalid ticker alongside a good one: status "
        f"{q2['bogus']['status']}, keys returned "
        f"{', '.join(q2['bogus']['keys_returned']) or 'none'}"
        + (f", error {q2['bogus']['error']}" if q2['bogus']['error'] else ""))
    add("")

    add("## 3. How many symbols fit in one request")
    add("")
    add("| Batch | Status | URL chars for the symbol list | Bars on first page | Seconds | Error |")
    add("| ---: | ---: | ---: | ---: | ---: | --- |")
    for row in q3:
        add(f"| {_fmt(row['size'])} | {row.get('status')} | {_fmt(row.get('url_chars'))} | "
            f"{_fmt(row.get('bars_first_page'))} | {_fmt(row.get('seconds'))} | "
            f"{row.get('error') or row.get('note') or ''} |")
    add("")

    add("## 4. How much data actually comes back")
    add("")
    add(f"Full universe sweep at {q4['timeframe']}, batch size {_fmt(q4['batch_size'])}.")
    add("")
    add("| Measure | Value |")
    add("| --- | ---: |")
    add(f"| Symbols requested | {_fmt(q4['symbols_requested'])} |")
    add(f"| Total bars returned | {_fmt(q4['total_bars'])} |")
    add(f"| Distinct symbols with any bars | {_fmt(q4['symbols_with_bars'])} |")
    add(f"| Pages consumed | {_fmt(q4['pages'])} |")
    add(f"| Largest single page | {_fmt(q4['largest_page_bars'])} |")
    add(f"| Sweep complete | {q4['complete']} |")
    add("")
    if q4["errors"]:
        add("Errors during the sweep:")
        add("")
        for item in q4["errors"]:
            add(f"- {item}")
        add("")

    add("## 5. How long it takes")
    add("")
    add("| Measure | Value |")
    add("| --- | ---: |")
    add(f"| Wall clock, full 1Min sweep | {_fmt(q4['wall_clock_s'])} s |")
    add(f"| Requests used | {_fmt(q4['requests'])} |")
    add(f"| Per request minimum | {_fmt(q4['request_min_s'])} s |")
    add(f"| Per request median | {_fmt(q4['request_median_s'])} s |")
    add(f"| Per request maximum | {_fmt(q4['request_max_s'])} s |")
    add("")

    add("## 6. Rate limit headroom")
    add("")
    if headers:
        add("| Header | Value |")
        add("| --- | --- |")
        for key in sorted(headers):
            add(f"| {key} | {headers[key]} |")
    else:
        add("The vendor returned no rate limit headers on the last response.")
    add("")
    add(f"Requests used by the whole probe: {_fmt(results['q6']['total_requests'])}")
    add(f"Requests used by the 1Min sweep alone: {_fmt(q4['requests'])}")
    add(f"429 retries: {_fmt(results['q6']['retries'])}")
    add("")

    add("## 7. Whether a coarser timeframe is worth it")
    add("")
    add("| Measure | 1Min | 1Hour |")
    add("| --- | ---: | ---: |")
    add(f"| Total bars | {_fmt(q4['total_bars'])} | {_fmt(q7['total_bars'])} |")
    add(f"| Symbols with bars | {_fmt(q4['symbols_with_bars'])} | {_fmt(q7['symbols_with_bars'])} |")
    add(f"| Pages | {_fmt(q4['pages'])} | {_fmt(q7['pages'])} |")
    add(f"| Requests | {_fmt(q4['requests'])} | {_fmt(q7['requests'])} |")
    add(f"| Wall clock | {_fmt(q4['wall_clock_s'])} s | {_fmt(q7['wall_clock_s'])} s |")
    add(f"| Sweep complete | {q4['complete']} | {q7['complete']} |")
    add("")
    bleed = results["q7_bleed"]
    add("The hourly sweep reports MORE symbols than the minute sweep, which cannot be "
        "true of the same window and is the measurement that decides this question.")
    add("")
    add("| Measure | Value |")
    add("| --- | ---: |")
    add(f"| Symbols in 1Hour but not in 1Min | {_fmt(bleed['extra_symbols'])} |")
    add(f"| Of those, first 1Min bar falls AFTER the window end | "
        f"{_fmt(bleed['first_bar_after_window_end'])} |")
    add("")
    if bleed["samples"]:
        add(f"Window ends at {WINDOW_END_HM[0]:02d}:{WINDOW_END_HM[1]:02d} ET. Examples:")
        add("")
        for sample in bleed["samples"]:
            add(f"- {sample['symbol']} first 1Min bar at ET {sample['first_1min_bar_et']}")
        add("")
    add("An hourly bar is returned when its START falls inside the window, but the bar "
        "aggregates the whole hour, so the bar stamped 08:00 carries trades through "
        "09:00. A coarse first stage therefore reads past the boundary it appears to "
        "respect, and a symbol can show hourly premarket activity that had not "
        "happened yet at the moment the report is written.")
    add("")
    if q7["errors"]:
        add("Errors during the hourly sweep:")
        add("")
        for item in q7["errors"]:
            add(f"- {item}")
        add("")

    files.write_text_atomically(path, "\n".join(lines) + "\n",
                                attempts=files.ATTEMPTS, retry_s=files.RETRY_S)


# ---------------------------------------------------------------------- runner

def main(argv: list[str] | None = None) -> int:
    probe = Probe()
    universe = load_universe()
    print(f"probe: universe holds {len(universe):,} symbols")

    day, day_note = find_last_trading_day(probe)
    start, end = _window(day)
    print(f"probe: most recent completed trading day is {day.isoformat()} ({day_note})")
    print(f"probe: window {start} to {end}")
    print()

    print("probe: 1. SIP versus IEX on one liquid symbol")
    q1 = q1_sip_versus_iex(probe, day)
    for label in ("premarket", "regular"):
        for feed in ("sip", "iex"):
            print(f"    {label:<9} {feed} volume {q1.get(f'{label}_{feed}_volume', 0):>16,.0f} "
                  f"across {q1.get(f'{label}_{feed}_bars', 0):>6,} bars, "
                  f"status {q1.get(f'{label}_{feed}_status')}"
                  + (f", error {q1[f'{label}_{feed}_error']}"
                     if q1.get(f"{label}_{feed}_error") else ""))
        print(f"    {label:<9} SIP to IEX volume ratio: {q1.get(f'{label}_ratio')}")
    print()

    print("probe: 2. do non-trading symbols return nothing")
    q2 = q2_absent_symbols(probe, day, universe)
    for row in q2["detail"]:
        print(f"    {row['symbol']:<8} {row['group']:<9} "
              f"dollar_vol {row['avg_dollar_volume_20d']:>18,.0f}  "
              f"key_present {str(row['key_present']):<5} bars {row['bars']:,}")
    print(f"    keys returned: {', '.join(q2['keys_returned']) or 'none'}")
    print(f"    invalid ticker alongside a good one: status {q2['bogus']['status']}, "
          f"keys {', '.join(q2['bogus']['keys_returned']) or 'none'}")
    print()

    print("probe: 3. how many symbols fit in one request")
    q3 = q3_batch_sizes(probe, day, universe)
    for row in q3:
        print(f"    {row['size']:>5} symbols  status {str(row.get('status')):<5} "
              f"ok {str(row.get('ok')):<5} {row.get('error') or row.get('note') or ''}")
    print()

    widest = max((row["size"] for row in q3 if row.get("ok")), default=100)
    print(f"probe: widest batch that succeeded is {widest}, sweeping with that")
    print()

    print("probe: 4 and 5. full universe sweep at 1Min")
    q4 = sweep(probe, day, universe, "1Min", widest)
    print(f"    total bars                {q4['total_bars']:,}")
    print(f"    symbols with any bars     {q4['symbols_with_bars']:,}")
    print(f"    pages consumed            {q4['pages']:,}")
    print(f"    largest single page       {q4['largest_page_bars']:,}")
    print(f"    requests                  {q4['requests']:,}")
    print(f"    wall clock                {q4['wall_clock_s']:,} s")
    print(f"    per request min/med/max   {q4['request_min_s']} / "
          f"{q4['request_median_s']} / {q4['request_max_s']} s")
    print(f"    sweep complete            {q4['complete']}")
    for item in q4["errors"]:
        print(f"    error: {item}")
    print()

    print("probe: 6. rate limit headroom")
    rate_headers = {
        key: value for key, value in probe.last_headers.items()
        if "ratelimit" in key or key in ("retry-after",)
    }
    for key in sorted(rate_headers):
        print(f"    {key}: {rate_headers[key]}")
    if not rate_headers:
        print("    the vendor returned no rate limit headers on the last response")
    print(f"    requests used by the whole probe so far: {probe.request_count:,}")
    print(f"    429 retries: {probe.retry_count:,}")
    print()

    print("probe: 7. same sweep at 1Hour")
    q7 = sweep(probe, day, universe, "1Hour", widest)
    print(f"    total bars                {q7['total_bars']:,}")
    print(f"    symbols with any bars     {q7['symbols_with_bars']:,}")
    print(f"    pages consumed            {q7['pages']:,}")
    print(f"    requests                  {q7['requests']:,}")
    print(f"    wall clock                {q7['wall_clock_s']:,} s")
    print(f"    sweep complete            {q7['complete']}")
    for item in q7["errors"]:
        print(f"    error: {item}")

    # The hourly sweep reporting MORE symbols than the minute sweep is not a
    # bug in either sweep, and it is the whole answer to whether a coarse first
    # stage is safe. Measure it rather than explain it away.
    extra = sorted(q7["symbol_set"] - q4["symbol_set"])
    bleed = q7_boundary_bleed(probe, day, extra)
    print(f"    symbols in 1Hour but not 1Min: {bleed['extra_symbols']:,}")
    print(f"    of those, first 1Min bar falls AFTER the window end: "
          f"{bleed['first_bar_after_window_end']:,}")
    for sample in bleed["samples"]:
        print(f"        {sample['symbol']:<8} first 1Min bar at ET "
              f"{sample['first_1min_bar_et']}")
    print()

    results = {
        "universe_size": len(universe),
        "q1": q1,
        "q2": q2,
        "q3": q3,
        "q4": q4,
        "q7": q7,
        "q7_bleed": bleed,
        "q6": {
            "headers": rate_headers,
            "total_requests": probe.request_count,
            "retries": probe.retry_count,
        },
    }

    out_path = config.DOC_DIR / "ALPACA_PROBE.md"
    write_report(out_path, day, day_note, results)
    print(f"probe: wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
