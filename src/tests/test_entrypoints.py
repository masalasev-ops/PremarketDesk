"""Every entrypoint the scheduler invokes, run end to end.

pool_recall.build referred to a name that no longer existed and raised
NameError on every nightly run for a week. The suite at the time exercised
pool_recall.measure, the pure function underneath it, which had no wiring in
it to be wrong. The pure function was easy to test so it got tested, and the
place the bug lived did not. That is the general shape of the problem, not a
fact about that one module, so this file is organised by what the scheduler
calls rather than by what is convenient to call.

One test per scheduled step, each invoking the module's own main with the
arguments the .bat passes it. Where a step needs the network the HTTP client
is stubbed and the call shape asserted, because "which endpoints did this
step actually ask for" is most of what an end to end test of a data job can
usefully claim. Two steps reach the outside world through something other
than the HTTP client and are stubbed at the equivalent layer, each noted
where it happens: the collector's socket, and the analyst's claude CLI.

Every step is also checked through its status record, which is what catches
the pool_recall shape specifically: a main that swallows its exception and
returns zero still records the failure, so asserting the record catches a
bug that asserting the exit code cannot.

Run directly with `python src\\test_entrypoints.py`, or as part of
`python src\\run_tests.py`, which is the sandboxed way.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import ettime
from ops import job_status

_CRIT = criteria.load()

# The scheduler's own invocations: step name, module, and the arguments the
# .bat passes. Kept as data so the CRITERIA.md step list can be checked
# against it, since a step missing from that list is never reported overdue.
SCHEDULED = [
    ("calendar", "ops.market_today", []),
    ("universe", "selection.universe", []),
    ("gap_stats", "selection.gap_stats", []),
    ("discover", "selection.discover", []),
    ("baseline", "collect.baseline", []),
    ("collector", "collect.collect_premarket", []),
    ("scan", "morning.scan", []),
    ("analyst", "morning.analyst", []),
    ("render", "morning.render_report", []),
    ("verify", "morning.verify_morning", []),
    ("deliver", "morning.deliver", []),
    ("archive", "night.build_archive", []),
    ("backfill", "night.backfill_premarket", []),
    ("outcomes", "night.fill_outcomes", []),
    ("pool_recall", "night.pool_recall", []),
    ("monitor", "ops.monitor_jobs", ["--dry-run"]),
]


# ------------------------------------------------------------- the HTTP stub

class _Response:
    """Just enough of requests.Response for eodhd._request."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload)


class _ScriptedSession:
    """Answers EODHD paths from a script and records what was asked for.

    Records the path and the parameters with the token removed, which is the
    call shape a test can assert against without any risk of a credential
    reaching an assertion message.
    """

    def __init__(self, routes: list[tuple[str, Any]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.unrouted: list[str] = []

    def get(self, url: str, params: dict[str, Any] | None = None,
            timeout: float | None = None) -> _Response:
        path = url.split("/api/", 1)[-1]
        safe = {k: v for k, v in (params or {}).items()
                if k not in ("api_token", "fmt")}
        self.calls.append((path, safe))
        for needle, payload in self.routes:
            if needle in path:
                body = payload(path, safe) if callable(payload) else payload
                return _Response(body)
        self.unrouted.append(path)
        return _Response({"error": f"no route for {path}"}, status_code=404)

    def endpoints(self) -> list[str]:
        """Distinct leading path segments asked for, in first-seen order."""
        seen: list[str] = []
        for path, _params in self.calls:
            head = path.split("/")[0]
            if head not in seen:
                seen.append(head)
        return seen


def _install(routes: list[tuple[str, Any]]) -> _ScriptedSession:
    """Point the shared client at a scripted session."""
    from core import eodhd

    session = _ScriptedSession(routes)
    client = eodhd.EodhdClient(token="stub-token", ledger=eodhd.CallLedger())
    client._session = session
    eodhd._default_client = client
    return session


def _uninstall() -> None:
    from core import eodhd

    eodhd._default_client = None


# --------------------------------------------------------------- canned data

TODAY = ettime.today_et()
YESTERDAY = TODAY - dt.timedelta(days=1)

# The three names every other step works on, and a filler list that exists
# only so a full universe rebuild lands inside the CRITERIA.md count range.
# A rebuild that produced three names would exit non zero, correctly, and the
# test would then be asserting the size of its own fixture.
SYMBOLS = ["AAPL.US", "MSFT.US", "NVDA.US"]
_FILLER_COUNT = _CRIT.integer("universe", "expected_count_min") + 10
BULK_SYMBOLS = SYMBOLS + [f"TST{n:04d}.US" for n in range(_FILLER_COUNT)]


def _eod_series(symbol: str, days: int = 300) -> list[dict[str, Any]]:
    """A flat price history, long enough for every lookback in the project."""
    out = []
    for back in range(days, 0, -1):
        day = TODAY - dt.timedelta(days=back)
        if not ettime.is_weekday(day):
            continue
        base = 100.0 + (hash(symbol) % 50)
        out.append({
            "date": day.isoformat(),
            "open": base, "high": base + 2, "low": base - 2,
            "close": base, "adjusted_close": base, "volume": 5_000_000,
        })
    return out


def _bulk_rows(day: dt.date) -> list[dict[str, Any]]:
    rows = []
    for symbol in BULK_SYMBOLS:
        base = 100.0 + (hash(symbol) % 50)
        rows.append({
            "code": symbol.split(".")[0], "exchange_short_name": "US",
            "date": day.isoformat(),
            "open": base, "high": base + 2, "low": base - 2, "close": base,
            "adjusted_close": base, "volume": 5_000_000, "prev_close": base,
        })
    return rows


def _intraday_rows(day: dt.date) -> list[dict[str, Any]]:
    """One minute bars across the premarket window."""
    out = []
    start = ettime.at(day, 4, 0)
    for minute in range(0, 300, 5):
        when = start + dt.timedelta(minutes=minute)
        out.append({
            "datetime": when.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": ettime.epoch_s(when),
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
            "volume": 10_000,
        })
    return out


ROUTES: list[tuple[str, Any]] = [
    ("exchange-details/", {
        "Name": "USA Stocks", "Code": "US", "Timezone": "America/New_York",
        "ExchangeHolidays": {},
        "TradingHours": {"Open": "09:30", "Close": "16:00"},
    }),
    ("exchange-symbol-list/", [
        {"Code": s.split(".")[0], "Name": f"{s} Inc", "Country": "USA",
         "Exchange": "NASDAQ", "Currency": "USD", "Type": "Common Stock"}
        for s in BULK_SYMBOLS
    ]),
    ("eod-bulk-last-day/", lambda path, params: _bulk_rows(
        ettime.parse_date(params["date"]) if params.get("date") else YESTERDAY)),
    ("eod/", lambda path, params: _eod_series(path.split("/", 1)[1])),
    ("intraday/", lambda path, params: _intraday_rows(YESTERDAY)),
    ("us-quote-delayed", lambda path, params: {"data": {
        symbol: {
            "symbol": symbol, "previousClosePrice": 100.0,
            "ethVolume": 250_000, "ethTime": ettime.epoch_s(ettime.now_et()),
            "marketCap": 2_000_000_000, "sharesFloat": 500_000_000,
            "averageVolume": 8_000_000, "twoHundredDayAveragePrice": 98.0,
        }
        for symbol in str(params.get("s", "")).split(",") if symbol
    }}),
    ("calendar/earnings", {"earnings": [
        {"code": "AAPL.US", "report_date": TODAY.isoformat(),
         "before_after_market": "BeforeMarket", "estimate": 1.2},
    ]}),
    ("news", [
        {"date": f"{TODAY.isoformat()}T05:00:00+00:00", "title": "MSFT news",
         "symbols": ["MSFT.US"], "content": "overnight", "sentiment": {}},
    ]),
    ("economic-events", []),
    ("user", {"apiRequests": 100, "dailyRateLimit": 100_000,
              "apiRequestsDate": TODAY.isoformat()}),
    ("real-time/", {"code": "AAPL.US", "close": 100.0, "previousClose": 100.0,
                    "timestamp": ettime.epoch_s(ettime.now_et()), "volume": 1000}),
]


# ------------------------------------------------------- sandbox preparation

def _write_universe() -> None:
    """A three name universe, so a full rebuild is seconds rather than minutes."""
    payload = {
        "generated_at": ettime.stamp(ettime.now_et()),
        "count": len(SYMBOLS),
        "expected_count_range": [1, 10_000],
        "notes": [],
        "symbols": [
            {"symbol": s, "name": f"{s} Inc", "exchange": "NASDAQ",
             "avg_dollar_volume_20d": 500_000_000, "close": 100.0,
             "avg_volume_20d": 5_000_000}
            for s in SYMBOLS
        ],
    }
    config.UNIVERSE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _write_watchlist() -> None:
    payload = {
        "generated_at": ettime.stamp(ettime.now_et()),
        "pool_size": len(SYMBOLS),
        "subscribed_count": len(SYMBOLS),
        "max_subscribed_candidates": 50,
        "gaps_to_fill": [],
        "symbols": [
            {"symbol": s, "subscribed": True, "tier": "earnings_before_open",
             "pool_sources": ["earnings_before_open"], "prior_close": 100.0,
             "rank_value": 0.3}
            for s in SYMBOLS
        ],
    }
    config.WATCHLIST_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _write_report() -> Path:
    """A report.md for render, and a packet for verify and analyst."""
    run = config.run_dir(TODAY.isoformat())
    (run / "report.md").write_text(
        "# Premarket, " + TODAY.isoformat() + "\n\n"
        "## Watchlist\n\n| Ticker | Gap |\n| --- | --- |\n| AAPL | +3.1% |\n\n"
        "Nothing here is advice.\n",
        encoding="utf-8",
    )
    return run


def _write_packet() -> Path:
    run = config.run_dir(TODAY.isoformat())
    packet = {
        "session_date": TODAY.isoformat(),
        "generated_at": ettime.stamp(ettime.now_et()),
        "build": {"commit": "stub", "dirty": False},
        "job_health": {"overdue": [], "line": None},
        "candidates": [{
            "symbol": "AAPL.US", "price": 100.0, "gap_pct": 3.1,
            "price_time": ettime.stamp(ettime.now_et()), "pm_volume": 250_000,
            "pm_rvol": 1.4, "bars_collected": 40, "baseline": {"median_volume": 180_000},
            "day_eligible": True, "swing_eligible": False, "score": 6.0,
            "conviction": "medium", "catalyst": {"headline": "earnings"},
        }],
        "dropped_no_coverage": [],
        "gaps_to_fill": [],
        "market": {},
    }
    path = run / "packet.json"
    path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return path


# -------------------------------------------------------------- the harness

class Outcome:
    def __init__(self, step: str, code: Any, record: dict[str, Any] | None,
                 session: _ScriptedSession | None, error: str | None) -> None:
        self.step = step
        self.code = code
        self.record = record or {}
        self.session = session
        self.error = error

    @property
    def status(self) -> str:
        return self.record.get("status", "no record")


def _drive(step: str, module_name: str, argv: list[str],
           routes: list[tuple[str, Any]] | None = None) -> Outcome:
    """Run one entrypoint the way the scheduler runs it, and read the record."""
    import importlib

    session = _install(routes if routes is not None else ROUTES)
    before = len(job_status.records())
    error = None
    code: Any = None
    try:
        module = importlib.import_module(module_name)
        code = job_status.run(step, module.main, argv)
    except SystemExit as exc:
        code = exc.code
    except BaseException as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _uninstall()

    rows = job_status.records()
    record = rows[before] if len(rows) > before else None
    return Outcome(step, code, record, session, error)


def _check(outcome: Outcome, failures: list[str], *,
           expect_status: str = job_status.STATUS_OK,
           expect_endpoints: list[str] | None = None,
           expect_code: Any = 0) -> None:
    label = outcome.step
    if outcome.error:
        failures.append(f"{label} raised out of main: {outcome.error}")
        return
    if outcome.code != expect_code:
        failures.append(f"{label} exited {outcome.code}, expected {expect_code}")
    if outcome.status != expect_status:
        failures.append(f"{label} recorded status {outcome.status!r}, expected "
                        f"{expect_status!r} (exception: "
                        f"{outcome.record.get('exception')})")
    if expect_endpoints is not None and outcome.session is not None:
        asked = outcome.session.endpoints()
        for wanted in expect_endpoints:
            if wanted not in asked:
                failures.append(f"{label} never asked for {wanted}; it asked for "
                                f"{asked or 'nothing'}")
    produced = outcome.record.get("produced_count")
    print(f"  {label:<12} exit {str(outcome.code):<5} {outcome.status:<7} "
          f"produced {produced if produced is not None else '-'}  "
          f"endpoints {','.join(outcome.session.endpoints()) if outcome.session else '-'}")


# ------------------------------------------------------------------- claims

def claim_step_list_matches(failures: list[str]) -> None:
    """Every scheduled step is in CRITERIA.md, and every listed step is real.

    A step the scheduler runs but CRITERIA.md does not list is never reported
    overdue, which is the one way the whole mechanism can fail silently.
    """
    listed = set(job_status.tracked_steps())
    driven = {step for step, _module, _argv in SCHEDULED}
    for missing in sorted(driven - listed):
        failures.append(f"{missing} is invoked by a .bat but is not in "
                        "CRITERIA.md [job status steps], so it can never be "
                        "reported overdue")
    for extra in sorted(listed - driven):
        failures.append(f"{extra} is in CRITERIA.md [job status steps] but no "
                        "test drives it, so it is either unscheduled or untested")
    print(f"  step list    {len(listed)} steps in CRITERIA.md, all driven here")


def claim_calendar(failures: list[str]) -> None:
    outcome = _drive("calendar", "ops.market_today", [])
    # A trading day exits 0, a holiday exits 3, and both are successes.
    _check(outcome, failures, expect_code=outcome.code,
           expect_status=job_status.STATUS_OK)
    if outcome.code not in (0, 3):
        failures.append(f"calendar exited {outcome.code}, expected 0 or 3")


def claim_universe(failures: list[str]) -> None:
    outcome = _drive("universe", "selection.universe", [])
    _check(outcome, failures,
           expect_endpoints=["exchange-symbol-list", "eod-bulk-last-day"])


def claim_gap_stats(failures: list[str]) -> None:
    _write_universe()
    outcome = _drive("gap_stats", "selection.gap_stats", [])
    _check(outcome, failures, expect_endpoints=["eod"])


def claim_discover(failures: list[str]) -> None:
    _write_universe()
    outcome = _drive("discover", "selection.discover", [])
    _check(outcome, failures, expect_endpoints=["calendar", "news"])


def claim_baseline(failures: list[str]) -> None:
    _write_watchlist()
    outcome = _drive("baseline", "collect.baseline", [])
    _check(outcome, failures)


def claim_collector(failures: list[str]) -> None:
    """The collector, driven through a replayed socket.

    Stubbed at _connect rather than at the HTTP client, because the collector
    does not use the HTTP client: _connect is its equivalent, the one call
    that reaches the outside world. The replay feeds real shaped trade frames
    for two of the three subscribed symbols, which is also what proves the
    coverage report distinguishes a silent symbol from an absent one.
    """
    from collect import collect_premarket

    _write_watchlist()
    real_connect = collect_premarket._connect
    collect_premarket._connect = lambda symbols: _ReplaySocket(symbols)
    try:
        outcome = _drive("collector", "collect.collect_premarket", ["--minutes", "0.05"])
    finally:
        collect_premarket._connect = real_connect
    _check(outcome, failures)
    if (outcome.record.get("produced_count") or 0) <= 0:
        failures.append("the collector recorded zero minutes written from a "
                        "replay that fed it trades")


class _ReplaySocket:
    """A socket that yields canned trades for all but the last symbol."""

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.sent = 0
        # Deliberately silent, to exercise the coverage report.
        self.silent = symbols[-1] if symbols else None

    def recv(self) -> str | None:
        import websocket

        speaking = [s for s in self.symbols if s != self.silent]
        if self.sent >= len(speaking) * 3:
            raise websocket.WebSocketTimeoutException("replay exhausted")
        symbol = speaking[self.sent % len(speaking)]
        self.sent += 1
        return json.dumps({
            "s": symbol.split(".")[0], "p": 100.0, "v": 500,
            "t": ettime.epoch_ms(ettime.now_et()), "dp": False, "ms": "extended-hours",
        })

    def close(self) -> None:
        pass

    def settimeout(self, value: float) -> None:
        pass


def claim_scan(failures: list[str]) -> None:
    _write_universe()
    _write_watchlist()
    outcome = _drive("scan", "morning.scan", [])
    # The vintage gate can legitimately refuse canned data, and a refusal is
    # the gate working. What must not happen is an unhandled exception.
    if outcome.error:
        failures.append(f"scan raised out of main: {outcome.error}")
    elif outcome.code not in (0, 1):
        failures.append(f"scan exited {outcome.code}, expected 0 or 1")
    else:
        print(f"  {'scan':<12} exit {str(outcome.code):<5} {outcome.status:<7} "
              f"endpoints {','.join(outcome.session.endpoints())}")


def claim_analyst(failures: list[str]) -> None:
    """The analyst, with the claude CLI stubbed at invoke_claude.

    The subprocess is this module's outside world, the same role the HTTP
    client plays elsewhere. Nothing here shells out and nothing reads or sets
    an API key, which is a hard rule of this project rather than a test
    convenience.
    """
    from morning import analyst

    _write_packet()
    real = analyst.invoke_claude
    analyst.invoke_claude = lambda packet_text: (
        "# Premarket\n\n## Watchlist\n\n| Ticker | Gap |\n| --- | --- |\n"
        "| AAPL | +3.1% |\n\nNothing here is advice.\n",
        {"total_cost_usd": 0.0, "duration_ms": 1, "num_turns": 1},
        None,
        "ok",
    )
    try:
        outcome = _drive("analyst", "morning.analyst", [])
    finally:
        analyst.invoke_claude = real
    _check(outcome, failures)


def claim_render(failures: list[str]) -> None:
    _write_report()
    outcome = _drive("render", "morning.render_report", [])
    _check(outcome, failures)


def claim_verify(failures: list[str]) -> None:
    _write_packet()
    outcome = _drive("verify", "morning.verify_morning", [])
    _check(outcome, failures)


def claim_deliver(failures: list[str]) -> None:
    """Delivery must refuse while the gate marker exists, and record refusing."""
    from morning import verify_morning

    _write_report()
    _drive("render", "morning.render_report", [])
    verify_morning.ensure_marker()
    outcome = _drive("deliver", "morning.deliver", [])
    _check(outcome, failures)
    if outcome.record.get("produced_count") != 0:
        failures.append("deliver recorded a non zero recipient count while the "
                        "UNVERIFIED gate marker exists")


def claim_archive(failures: list[str]) -> None:
    outcome = _drive("archive", "night.build_archive", [])
    _check(outcome, failures)


def claim_backfill(failures: list[str]) -> None:
    outcome = _drive("backfill", "night.backfill_premarket", [])
    _check(outcome, failures)


def claim_outcomes(failures: list[str]) -> None:
    outcome = _drive("outcomes", "night.fill_outcomes", [])
    _check(outcome, failures)


def claim_pool_recall(failures: list[str]) -> None:
    """The step whose absence started this, driven the way the nightly runs it.

    Two assertions, and the second is the one that would have caught the bug.
    The exit code is zero whether or not build() worked, by design, so a test
    that only asserted the exit code would have passed all week. The status
    record is what tells the two apart.
    """
    _write_universe()
    outcome = _drive("pool_recall", "night.pool_recall", [])
    if outcome.error:
        failures.append(f"pool_recall raised out of main: {outcome.error}")
        return
    if outcome.code != 0:
        failures.append(f"pool_recall exited {outcome.code}; it must always exit "
                        "zero so the nightly chain is never broken by a diagnostic")
    if outcome.status != job_status.STATUS_OK:
        failures.append(f"pool_recall exited zero but recorded {outcome.status}: "
                        f"{outcome.record.get('exception')}")
    print(f"  {'pool_recall':<12} exit {str(outcome.code):<5} {outcome.status:<7} "
          f"produced {outcome.record.get('produced_count')}")


def claim_monitor(failures: list[str]) -> None:
    """The watchdog, with Task Scheduler stubbed at the subprocess boundary."""
    from ops import monitor_jobs

    real = monitor_jobs.query_task
    monitor_jobs.query_task = lambda task_name: {
        "exists": True, "last_run": ettime.now_et(), "last_result": "0",
        "status": "Ready",
    }
    try:
        outcome = _drive("monitor", "ops.monitor_jobs", ["--dry-run"])
    finally:
        monitor_jobs.query_task = real
    if outcome.error:
        failures.append(f"monitor raised out of main: {outcome.error}")
    elif outcome.code not in (0, 1):
        failures.append(f"monitor exited {outcome.code}, expected 0 or 1")
    else:
        print(f"  {'monitor':<12} exit {str(outcome.code):<5} {outcome.status:<7}")


def claim_failure_is_recorded(failures: list[str]) -> None:
    """Killing a step mid run leaves a failure record, and a clean run leaves none.

    The clause's own done condition, checked directly rather than inferred.
    """
    before = len(job_status.records())

    def dying_main(argv=None):
        raise KeyboardInterrupt("simulated kill")

    try:
        job_status.run("pool_recall", dying_main)
    except KeyboardInterrupt:
        pass

    rows = job_status.records()[before:]
    if not rows:
        failures.append("a step killed mid run left no status record at all")
        return
    killed = rows[-1]
    if killed.get("status") != job_status.STATUS_ERROR:
        failures.append(f"a killed step recorded {killed.get('status')!r}, not error")
    if "KeyboardInterrupt" not in (killed.get("exception") or ""):
        failures.append("a killed step did not record how it died")

    # And the pool_recall shape: exit zero, record the failure anyway.
    def swallowing_main(argv=None):
        job_status.failed("NameError: name 'floor' is not defined")
        return 0

    code = job_status.run("pool_recall", swallowing_main)
    swallowed = job_status.records()[-1]
    if code != 0:
        failures.append("a declared failure changed the exit code, which would "
                        "break the chain it is designed not to break")
    if swallowed.get("status") != job_status.STATUS_ERROR:
        failures.append("a step that exited zero and declared failure recorded "
                        f"{swallowed.get('status')!r}")
    print("  recording   a killed step and a swallowed failure both recorded, "
          "exit code unchanged")


def claim_broad_catches_record(failures: list[str]) -> None:
    """A main that swallows an exception keeps its exit code and records the failure.

    The calendar guard is the sharpest case and the most repeated: it runs at
    the head of five of the six jobs, catches every exception, and returns
    zero so that a guard fault can never kill a real morning. That decision is
    right and is not changed here. What changes is that the assumption it
    proceeds on, that the market is open, now appears in the record instead of
    only in a log line.
    """
    from ops import market_today

    real = market_today.is_trading_day

    def exploding(date):
        raise RuntimeError("simulated calendar fault")

    market_today.is_trading_day = exploding
    try:
        outcome = _drive("calendar", "ops.market_today", [])
    finally:
        market_today.is_trading_day = real

    if outcome.error:
        failures.append(f"the calendar guard raised out of main: {outcome.error}. "
                        "It must never kill a morning.")
        return
    if outcome.code != 0:
        failures.append(f"the calendar guard exited {outcome.code} on an internal "
                        "fault; it must exit zero and assume the market is open")
    if outcome.status != job_status.STATUS_ERROR:
        failures.append(f"the calendar guard swallowed an exception and recorded "
                        f"{outcome.status!r}")
    if "RuntimeError" not in (outcome.record.get("exception") or ""):
        failures.append("the calendar guard did not record the exception type: "
                        f"{outcome.record.get('exception')!r}")
    print(f"  broad catch  calendar exited {outcome.code} and recorded "
          f"{outcome.status}: {(outcome.record.get('exception') or '')[:48]}")


def claim_watchdog_reads_steps(failures: list[str]) -> None:
    """The nightly that reported OK every night now reports the failed step.

    Two cases, and both have to hold. A nightly whose pool_recall failed and
    whose archive succeeded is the exact shape that hid for a week: the task
    fired, the final marker is present, and the marker is the archive's. A
    nightly killed before the archive writes no pool_recall record at all, so
    the step check sees nothing wrong and the marker check is what catches it.
    """
    from ops import monitor_jobs

    day = TODAY.isoformat()
    log_dir = config.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"nightly-{day}.log"

    def record(step: str, status: str, exception: str | None = None) -> None:
        job_status.append({
            "job": "nightly", "step": step,
            "started_at": f"{day} 22:15:00 ET", "ended_at": f"{day} 22:16:00 ET",
            "status": status, "exit_code": 0, "exception": exception,
            "produced_label": None, "produced_count": None, "seconds": 1.0,
        })

    # Case one: every step finished, the marker is present, pool_recall failed.
    log_path.write_text("===== archive finished rc=0 =====\n", encoding="utf-8")
    for step in ("backfill", "outcomes", "archive"):
        record(step, job_status.STATUS_OK)
    record("pool_recall", job_status.STATUS_ERROR,
           "NameError: name 'floor' is not defined")

    verdict = monitor_jobs.log_verdict("nightly", monitor_jobs.JOBS["nightly"][3], day)
    broken, examined = monitor_jobs.failed_steps("nightly", day)
    if verdict != "finished":
        failures.append(f"the marker check should still say finished, said {verdict}")
    if not any("pool_recall" in line for line in broken):
        failures.append("the watchdog did not name pool_recall as a failed step "
                        f"in a nightly whose marker says finished: {broken}")
    if any("archive" in line for line in broken):
        failures.append(f"the watchdog named a step that succeeded: {broken}")

    # A rerun that succeeded clears it, because the last record is the state.
    record("pool_recall", job_status.STATUS_OK)
    if monitor_jobs.failed_steps("nightly", day)[0]:
        failures.append("a step that was rerun successfully is still reported "
                        f"as failed: {monitor_jobs.failed_steps('nightly', day)[0]}")

    # Case two: killed before the archive. No record for it, marker absent.
    log_path.write_text("===== backfill finished rc=0 =====\n", encoding="utf-8")
    verdict = monitor_jobs.log_verdict("nightly", monitor_jobs.JOBS["nightly"][3], day)
    if verdict == "finished":
        failures.append("a nightly killed before the archive was reported finished")
    if monitor_jobs.failed_steps("nightly", day)[0]:
        failures.append("the step check invented a failure for a job that simply "
                        "never got that far; that case belongs to the marker")

    log_path.unlink(missing_ok=True)
    print("  watchdog     names pool_recall in a nightly whose marker says "
          "finished, and the marker still catches one killed early")


def claim_report_line(failures: list[str]) -> None:
    """A stale step reaches the morning report, and a healthy machine says nothing."""
    from morning import analyst

    fresh = [
        {"step": step, "status": job_status.STATUS_OK,
         "started_at": ettime.stamp(ettime.now_et())}
        for step in job_status.tracked_steps()
    ]
    if job_status.report_line(rows=fresh) is not None:
        failures.append("a machine with every step current produced a report line")

    stale_day = TODAY - dt.timedelta(days=30)
    stale = [dict(row) for row in fresh]
    stale[0]["started_at"] = f"{stale_day.isoformat()} 22:15:00 ET"
    line = job_status.report_line(rows=stale)
    if not line or stale[0]["step"] not in line:
        failures.append(f"an overdue step did not reach the report line: {line!r}")

    report = analyst.annotate_job_health(
        "# Premarket\n\nNothing here is advice.\n",
        {"job_health": {"line": line}},
    )
    if "overdue" not in report:
        failures.append("the overdue line never reached the report text")
    clean = analyst.annotate_job_health(
        "# Premarket\n\nNothing here is advice.\n",
        {"job_health": {"line": None}},
    )
    if clean.strip() != "# Premarket\n\nNothing here is advice.".strip():
        failures.append("a healthy machine still altered the report")
    print("  report line  an overdue step is named, a current machine is silent")


# ---------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    failures: list[str] = []

    if config.RUNS_DIR == config.PROJECT_ROOT / "runs":
        print("SKIP  not running under the sandbox; use python src\\run_tests.py")
        return 0

    try:
        config.eodhd_token()
    except config.ConfigError:
        pass  # the stub supplies its own token, no real one is needed

    config.ensure_dirs()

    print("scheduled entrypoints, each run the way its .bat runs it:")
    claim_step_list_matches(failures)
    claim_calendar(failures)
    claim_universe(failures)
    claim_gap_stats(failures)
    claim_discover(failures)
    claim_baseline(failures)
    claim_collector(failures)
    claim_scan(failures)
    claim_analyst(failures)
    claim_render(failures)
    claim_verify(failures)
    claim_deliver(failures)
    claim_archive(failures)
    claim_backfill(failures)
    claim_outcomes(failures)
    claim_pool_recall(failures)
    claim_monitor(failures)
    print("")
    print("the recording itself:")
    claim_failure_is_recorded(failures)
    claim_broad_catches_record(failures)
    claim_watchdog_reads_steps(failures)
    claim_report_line(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("")
    print(f"PASS  all {len(SCHEDULED)} scheduled entrypoints run end to end, each "
          "records its outcome, and a failure reaches the morning report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
