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

import contextlib
import io
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import ettime
from ops import job_status
from tests import conftest

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
        # pool_prior_close, pool_source and pool_tier are the keys
        # scan.pool_candidates actually reads. The older tier/pool_sources/
        # prior_close spellings are kept beside them because nothing else
        # reads either set and removing them would be an unrelated change,
        # but they are NOT what makes a candidate rankable: without
        # pool_prior_close every name reaches the scan with no prior close and
        # a thinned run, which cannot spend a call to fetch one, drops the lot.
        "symbols": [
            {"symbol": s, "subscribed": True,
             "pool_tier": 1, "pool_source": ["earnings_before_open"],
             "pool_prior_close": 100.0 + (hash(s) % 50),
             "avg_dollar_volume_20d": 5e8,
             "tier": "earnings_before_open",
             "pool_sources": ["earnings_before_open"], "prior_close": 100.0,
             "rank_value": 0.3}
            for s in SYMBOLS
        ],
    }
    config.WATCHLIST_PATH.write_text(json.dumps(payload), encoding="utf-8")


@contextlib.contextmanager
def _clock_pinned_to_scan_time():
    """Run a block as if it were the scan's configured run time today.

    Shifted rather than stopped, for the reason run_tests._freeze_clock gives:
    a now() that never advances deadlocks anything waiting on a clock. Only
    the three ettime readers are replaced, and they are restored afterwards,
    so this cannot leak into a later claim.
    """
    import time as _time

    base = ettime.at_hm(TODAY, _CRIT.clock("scan", "run_time"))
    origin = _time.monotonic()
    saved = (ettime.now_et, ettime.today_et, ettime.today_str)

    def now_et() -> dt.datetime:
        return base + dt.timedelta(seconds=_time.monotonic() - origin)

    ettime.now_et = now_et
    ettime.today_et = lambda: now_et().date()
    ettime.today_str = lambda: now_et().date().isoformat()
    try:
        yield base
    finally:
        ettime.now_et, ettime.today_et, ettime.today_str = saved


def _write_collector_bars(day: dt.date | None = None) -> Path:
    """A premarket bar file, so candidates survive the coverage screen.

    Without one the scan correctly drops every candidate for having no
    collector evidence, and a claim about what a packet says per candidate has
    nothing to say. The first version of the degrade claim hit exactly that and
    reported an empty packet as a defect.

    Shaped like the real collector's output because that is what read_bars
    parses: one JSON object per minute per symbol, with the fields the scan
    reads for price, window and volume.
    """
    from collect import collect_premarket

    session = day or TODAY
    path = collect_premarket.bar_path(session.isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    # Anchored so the LAST bar is the current minute, not the premarket clock.
    # CRITERIA [price age] max_price_age_seconds drops a price older than its
    # limit, correctly, and a fixture written at a fixed 07:20 is stale by
    # hours whenever the suite runs outside the morning. That dropped every
    # candidate and made this claim untestable in the evening while passing
    # at 08:45, which is the day-dependence the frozen clock sweep exists to
    # find.
    now = ettime.now_et().replace(second=0, microsecond=0)
    start = now - dt.timedelta(minutes=85)
    lines = []
    for symbol in SYMBOLS:
        base = 100.0 + (hash(symbol) % 50)
        for minute in range(0, 86):
            when = start + dt.timedelta(minutes=minute)
            price = base * 1.05
            lines.append(json.dumps({
                "symbol": symbol,
                "minute_epoch": ettime.epoch_s(when),
                "o": price, "h": price, "l": price, "c": price,
                "v": 5_000.0, "pv": price * 5_000.0, "trades": 20,
                "dark_pool_volume": 0.0, "market_status": "extended-hours",
                "src": "ws", "vwap": price,
                "minute_et": ettime.stamp(when),
            }, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_report() -> Path:
    """A report.md for render, and a packet for verify and analyst."""
    run = config.run_dir(TODAY.isoformat())
    # Both watchlist tables, with the literal header rows from
    # REPORT_TEMPLATE.md. The stub used to carry one improvised "| Ticker | Gap |"
    # table, which satisfied a guard that counted ticker columns and does not
    # satisfy one that requires these two tables by name. A fixture that would
    # be rejected in production should not pass here either.
    # Tables built from REPORT_TEMPLATE.md, not from header literals:
    # the containment guard matches these two by name, so a fixture
    # with its own header stops testing production the moment the
    # template moves.
    (run / "report.md").write_text(
        "# Premarket, " + TODAY.isoformat() + "\n\n"
        + conftest.watchlist_table("day watchlist",
                                   ["| AAPL | +3.1% | 100.00 | 1.8 | 101.00 | 100.50 | 6.0 | green |"])
        + "\n"
        + conftest.watchlist_table("swing watchlist")
        + "\nNothing here is advice.\n",
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
        # The scheduler runs each entrypoint through its own __main__ line, and
        # that line is what carries ok_codes. This harness calls main() directly,
        # so it has to read the same constant or it is not driving the
        # entrypoint the way the scheduler does. Omitting it recorded the
        # calendar guard's legitimate closed-market exit as a failure.
        ok_codes = getattr(module, "OK_CODES", (0,))
        code = job_status.run(step, module.main, argv, ok_codes=ok_codes)
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


def claim_subscription_refusal_is_fatal(failures: list[str]) -> None:
    """A 422 from the socket stops the run instead of being printed and ignored.

    The 50 symbol pool is account wide, measured on 2026-08-15 by subscribing
    25 on one socket and 25 on a second and watching the second be refused at
    its own 25. So a refusal means another process holds the slots, and
    reconnecting is refused again every time until the window is gone.

    Until 2026-08-15 this frame reached the branch for authorisation and status
    messages, printed one line and returned. The collector then ran to its stop
    time, folded zero trades, wrote an empty bar file and exited zero. Nothing
    downstream could tell that from a quiet morning.
    """
    import websocket

    from collect import collect_premarket

    builder = collect_premarket.BarBuilder(
        config.DATA_DIR / "refusal-probe.jsonl", "ws")
    log: list[dict[str, Any]] = []

    refusal = json.dumps({"status_code": 422, "message": "Symbols limit reached"})
    try:
        collect_premarket._handle_message(refusal, builder, log)
    except collect_premarket.SubscriptionRefused as exc:
        if "account wide" not in str(exc):
            failures.append("SubscriptionRefused did not explain the account wide pool")
    else:
        failures.append("a 422 'Symbols limit reached' frame did NOT raise "
                        "SubscriptionRefused, so a refused collector would again "
                        "run to its stop time and fold nothing")

    # The reconnect loop catches these three. If the refusal were any of them
    # it would be retried instead of ending the run, which is the bug wearing
    # a different hat.
    for retried in (ConnectionError, OSError, websocket.WebSocketException):
        if issubclass(collect_premarket.SubscriptionRefused, retried):
            failures.append(f"SubscriptionRefused is a {retried.__name__}, so the "
                            "reconnect loop would swallow and retry it")

    # A non fatal status frame is recorded, not raised, and not lost either.
    log.clear()
    collect_premarket._handle_message(
        json.dumps({"status_code": 500, "message": "Server error"}), builder, log)
    if len(log) != 1:
        failures.append(f"a non fatal status frame was not recorded, log holds {log}")

    # A real trade still folds normally through the same function.
    before = builder.trades_seen
    collect_premarket._handle_message(
        json.dumps({"s": "AAPL", "p": 10.0, "v": 5, "t": 1786700000000}), builder, log)
    if builder.trades_seen != before + 1:
        failures.append("a normal trade frame stopped folding after the 422 change")

    print("  refusal      a 422 raises SubscriptionRefused, is not a retryable "
          "error, and normal frames still fold")


def claim_operator_tools_spare_artifacts(failures: list[str]) -> None:
    """A hand run against a past session does not destroy that session's evidence.

    snapshot_bars is the tool that proved this was needed: it mutates whatever
    run directory it is pointed at, and pointing it at 2026-08-14 on 2026-08-15
    replaced a frozen 1,419 bar artifact with the whole trading day. conftest
    cannot reach it because it is not a test.

    Driven here so that an accidental mutation from a tool is caught by the
    same whole tree photograph that catches one from a test. TREE_ROOT is
    already PROJECT_ROOT, so every tool path is photographed; what was missing
    was anything invoking the tools inside the suite.
    """
    import importlib

    from collect import collect_premarket
    from core import artifacts

    day = "2026-05-04"
    source = collect_premarket.bar_path(day)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        '{"symbol":"AAA.US","minute_epoch":1,"o":1,"h":1,"l":1,"c":1,"v":1,"pv":1}\n'
        '{"symbol":"AAA.US","minute_epoch":61,"o":2,"h":2,"l":2,"c":2,"v":1,"pv":2}\n',
        encoding="utf-8",
    )
    run_dir = config.run_dir(day)
    frozen = run_dir / "premarket_snapshot.jsonl"
    frozen.write_text('{"symbol":"FROZEN.US","minute_epoch":1,"o":9,"h":9,"l":9,'
                      '"c":9,"v":9,"pv":9}\n', encoding="utf-8")
    original = frozen.read_bytes()

    # Default: the frozen artifact must survive and the copy must land beside it.
    _bars, stats = collect_premarket.snapshot_bars(day, frozen)
    if frozen.read_bytes() != original:
        failures.append("snapshot_bars replaced a frozen artifact without --overwrite")
    if not stats.get("spared"):
        failures.append("snapshot_bars did not report that it spared the original")
    beside = Path(stats["destination"])
    if beside == frozen or not beside.exists():
        failures.append(f"snapshot_bars wrote to {beside}, expected a sibling of {frozen}")
    if artifacts.SPARED_INFIX not in beside.name:
        failures.append(f"the spared copy {beside.name} does not carry "
                        f"{artifacts.SPARED_INFIX!r} in its name")

    # Explicit overwrite: the artifact is replaced, and only then.
    _bars, stats = collect_premarket.snapshot_bars(day, frozen, overwrite=True)
    if frozen.read_bytes() == original:
        failures.append("snapshot_bars refused to replace the artifact even with overwrite=True")
    if stats.get("spared"):
        failures.append("snapshot_bars reported sparing the original despite overwrite=True")

    print(f"  operator     snapshot_bars spared the frozen artifact and wrote "
          f"{beside.name}; --overwrite replaced it")

    # The owner rule. A scheduled run sets PMD_JOB and owns what it writes,
    # including past dates: backfill's 07:00 catch-up pass legitimately fills
    # yesterday, so "a past date is always spared" would break the schedule
    # rather than protect it. A hand run sets nothing and is spared.
    import os

    saved = os.environ.get(job_status.JOB_ENV_VAR)
    try:
        os.environ.pop(job_status.JOB_ENV_VAR, None)
        if artifacts.scheduled_run():
            failures.append("scheduled_run() is true with PMD_JOB unset")
        os.environ[job_status.JOB_ENV_VAR] = "nightly"
        if not artifacts.scheduled_run():
            failures.append("scheduled_run() is false with PMD_JOB set")
    finally:
        os.environ.pop(job_status.JOB_ENV_VAR, None)
        if saved is not None:
            os.environ[job_status.JOB_ENV_VAR] = saved

    # Every module a human can point at a past run directory routes through
    # the guard. A new one that forgets is the whole failure mode returning.
    unguarded = []
    for module_name, artifact in (
        ("night.pool_recall", "pool_recall.json"),
        ("night.backfill_premarket", "verify_intraday.json"),
        ("collect.collect_premarket", "premarket_snapshot.jsonl"),
    ):
        source = Path(importlib.import_module(module_name).__file__).read_text(encoding="utf-8")
        if "artifacts.resolve" not in source:
            unguarded.append(f"{module_name} writes {artifact} under runs/ but never "
                             "calls artifacts.resolve, so a hand run against a past "
                             "session would replace it")
    failures.extend(unguarded)
    if not unguarded:
        print("  operator     pool_recall, backfill and the collector all route "
              "their runs/ writes through the guard")


def claim_ok_codes_declared(failures: list[str]) -> None:
    """Every entrypoint declares OK_CODES at module level.

    The contract exists because a literal inside `if __name__ == "__main__":`
    is unreachable from a harness that imports the module and calls main()
    directly. market_today declared ok_codes only in that line, so _drive
    recorded its legitimate closed market exit as a failure, and the suite was
    green Monday to Friday and red on a Saturday.

    Asserted for all sixteen rather than for the one module that needs a non
    zero code today, because the next module to need one would otherwise
    reintroduce exactly the same split. Declaring (0,) explicitly is the point:
    it makes the value a property of the module that both callers read.
    """
    import importlib

    missing = []
    for step, module_name, _argv in SCHEDULED:
        module = importlib.import_module(module_name)
        codes = getattr(module, "OK_CODES", None)
        if codes is None:
            missing.append(f"{module_name} ({step}) does not declare OK_CODES")
        elif not isinstance(codes, tuple) or not codes or not all(
            isinstance(code, int) for code in codes
        ):
            missing.append(f"{module_name} ({step}) declares OK_CODES={codes!r}, "
                           "expected a non empty tuple of ints")
        elif 0 not in codes:
            missing.append(f"{module_name} ({step}) declares OK_CODES={codes!r}, "
                           "which excludes 0, so a clean run would record failed")
    failures.extend(missing)
    if not missing:
        non_default = [
            f"{step}={getattr(importlib.import_module(module_name), 'OK_CODES')}"
            for step, module_name, _argv in SCHEDULED
            if getattr(importlib.import_module(module_name), "OK_CODES") != (0,)
        ]
        print(f"  ok_codes     all {len(SCHEDULED)} entrypoints declare OK_CODES"
              + (f", non default: {', '.join(non_default)}" if non_default else ""))


def claim_calendar(failures: list[str]) -> None:
    outcome = _drive("calendar", "ops.market_today", [])
    # A trading day exits 0, a holiday exits 3, and both are successes.
    _check(outcome, failures, expect_code=outcome.code,
           expect_status=job_status.STATUS_OK)
    if outcome.code not in (0, 3):
        failures.append(f"calendar exited {outcome.code}, expected 0 or 3")


def claim_calendar_refresh_keeps_the_cache(failures: list[str]) -> None:
    """A failed nightly refresh leaves yesterday's holiday list on disk.

    market_today's whole failure direction is that an unknown calendar reads
    as OPEN, because a false closed silently loses a real morning. That is the
    right trade only while "unknown" is rare. The refresh deleted the cache
    and then fetched, so one 22:15 vendor outage produced no calendar at all,
    and every job the following morning ran on the assumption that the market
    was open. On the night before a holiday that assumption builds a watchlist
    from stale quotes, collects nothing, and emails a report about a session
    that does not exist, which is the exact failure the guard exists to
    prevent.

    Asserted on Christmas rather than on the file's presence alone, because
    the file existing is not the claim. The claim is that the guard can still
    answer.
    """
    from core import eodhd
    from ops import market_today

    holiday = dt.date(TODAY.year, 12, 25)
    _install(ROUTES + [("exchange-details/", {
        "Name": "USA Stocks", "Code": "US", "Timezone": "America/New_York",
        "ExchangeHolidays": {"1": {"Date": holiday.isoformat(),
                                   "Holiday": "Christmas Day"}},
        "TradingHours": {"Open": "09:30", "Close": "16:00",
                         "WorkingDays": "Mon,Tue,Wed,Thu,Fri"},
    })])
    try:
        market_today.reset_memo()
        market_today.main(["--refresh"])
    finally:
        _uninstall()

    if not market_today.CACHE_PATH.is_file():
        failures.append("the seeding refresh wrote no cache, so this claim has "
                        "nothing to protect")
        return

    saved = eodhd.EodhdClient.exchange_details
    eodhd.EodhdClient.exchange_details = lambda self, exchange: (
        None, "simulated vendor outage at 22:15")
    try:
        market_today.reset_memo()
        code = market_today.main(["--refresh"])
        market_today.reset_memo()
        trades, reason = market_today.is_trading_day(holiday)
    finally:
        eodhd.EodhdClient.exchange_details = saved
        market_today.reset_memo()

    if code != 0:
        failures.append(f"a failed refresh exited {code}; it must not fail the "
                        "nightly, the calendar is survivable")
    if not market_today.CACHE_PATH.is_file():
        failures.append("a failed refresh removed the cached calendar, so the "
                        "next morning has no holiday list at all")
    if trades:
        failures.append(f"after a failed refresh the guard called Christmas a "
                        f"trading day: {reason}")
    print("  calendar keep a failed refresh leaves the cache standing and the "
          "guard still names the holiday")


def claim_universe(failures: list[str]) -> None:
    """The rebuild, driven with no previous file on disk.

    The sandbox carries a restamped copy of the real universe, roughly 2,750
    names, while this claim's stubbed vendor serves a few. build() now asks
    check_admissible about its own payload before overwriting anything, so a
    previous count of 2,750 correctly refuses a rebuild that admits a
    thousand: that is a rebuild cut short, which is exactly what the gate is
    for. Comparing a stub against real production counts tests the fixture
    rather than the entrypoint.

    Removing it first is also the honest shape for this claim. With no
    previous file there is nothing to compare against, which is the first
    build case, and it is the only place the suite drives the branch of the
    first quota gate that cannot size the market cap sweep yet.
    """
    config.UNIVERSE_PATH.unlink(missing_ok=True)
    # Outcome carries the record and the session, not the printed lines, and
    # the branch under test is only visible in what the gate said. Captured
    # and replayed rather than swallowed, so the run still reads normally.
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        outcome = _drive("universe", "selection.universe", [])
    sys.stdout.write(printed.getvalue())
    _check(outcome, failures,
           expect_endpoints=["exchange-symbol-list", "eod-bulk-last-day"])
    if "bulk sweep alone" not in printed.getvalue():
        failures.append("with no previous universe on disk the first quota gate "
                        "should say it can only size the bulk sweep, and it did not")


def claim_universe_force(failures: list[str]) -> None:
    """The gate refuses by default, and --force writes while recording the verdict.

    Both halves are one claim because either alone is a defect. A gate with no
    escape hatch is the trap this fixed: the refusal is measured against
    previous_count, which _previous_count reads from the very file the refusal
    preserves, so a shrink that is REAL, the owner tightening a CRITERIA.md
    floor being the case BUILD_PLAN anticipates, is measured against the same
    frozen baseline every Sunday and refuses forever. Once max_age_days has
    passed, load_universe raises on the file nothing is allowed to replace and
    discover, scan and gap_stats refuse every morning after that. An escape
    hatch with no record is the opposite defect: a file that shrank past the
    floor and looks exactly like one that passed.

    So: the previous count is fabricated large enough that this rebuild lands
    below whatever the floor currently says, which is why the fraction is read
    rather than assumed. The refusal must leave the old file untouched and
    must name the flag, because a hatch nobody is told about is barely a
    hatch. The forced run must write, must carry the verdict text itself, and
    must be admitted downstream only for THAT verdict: a payload the override
    does not name is still refused, which is what makes it an override of one
    decision rather than a switch that turns the gate off.

    Which verdict the hatch reaches is the rest of the claim, and it is one
    verdict: the count fraction, the only one measured against the file the
    refusal preserves and therefore the only one that can refuse forever. A
    file carrying an override for the unswept ceiling is still refused here,
    and a --force run whose market cap sweep answered nothing is still refused
    at build time. Both are asserted below, because a hatch that widened to the
    lost batch case would be a hatch past the exact failure the gate was built
    for, and the refusal's own wording promises it is not.
    """
    from selection import universe

    fraction = _CRIT.number("universe", "min_count_fraction_of_previous")
    # Comfortably past the floor rather than a hair over it, so the claim is
    # about the gate and not about rounding.
    previous_count = int(len(BULK_SYMBOLS) / fraction) + 100
    config.UNIVERSE_PATH.write_text(json.dumps({
        "generated_at": ettime.stamp(ettime.now_et()),
        "count": previous_count,
        "cleared_price_and_liquidity": previous_count,
        "symbols": [{"symbol": f"OLD{n:05d}.US"} for n in range(previous_count)],
    }), encoding="utf-8")
    untouched = config.UNIVERSE_PATH.read_bytes()

    # The branch under test is only visible in what the gate said, and Outcome
    # carries the record rather than the printed lines. Captured and replayed
    # the way claim_universe does it, so the run still reads normally.
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        refused = _drive("universe", "selection.universe", [])
    sys.stdout.write(printed.getvalue())

    if refused.error:
        failures.append(f"universe raised out of main on a refusal: {refused.error}")
        return
    if refused.code != 1:
        failures.append(f"a rebuild below the count floor exited {refused.code}, "
                        "expected 1")
    if refused.status != job_status.STATUS_ERROR:
        failures.append(f"a refused rebuild recorded {refused.status!r}, so the "
                        "visible symptom would be a universe that did not change "
                        "with nothing saying why")
    if config.UNIVERSE_PATH.read_bytes() != untouched:
        failures.append("the refusal replaced the previous universe anyway, which "
                        "is the destructive overwrite the gate exists to prevent")
    if "--force" not in printed.getvalue():
        failures.append("the refusal never mentions --force, so an operator "
                        "holding a legitimately smaller universe is told to stop "
                        "and not told how to proceed")

    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        forced = _drive("universe", "selection.universe", ["--force"])
    sys.stdout.write(printed.getvalue())

    if forced.error:
        failures.append(f"universe raised out of main under --force: {forced.error}")
        return
    _check(forced, failures)
    if config.UNIVERSE_PATH.read_bytes() == untouched:
        failures.append("--force did not write the universe, so the gate still has "
                        "no way past it")
        return

    written = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    override = written.get("admissibility_override") or {}
    verdict = override.get("verdict") if isinstance(override, dict) else None
    if not verdict:
        failures.append("a forced universe carries no admissibility_override, so "
                        "nothing downstream or later can tell it from a build that "
                        f"passed cleanly: {sorted(written)}")
        return
    if str(previous_count) not in verdict:
        failures.append("the recorded override does not carry the gate's own "
                        f"verdict text, which named {previous_count}: {verdict!r}")
    if not any("--force" in str(value) for value in override.values()):
        failures.append("the override records what the gate said but not that a "
                        f"human overrode it: {override!r}")
    if "WARNING" not in printed.getvalue():
        failures.append("a forced write was not announced as a warning, so it "
                        "reads like an ordinary Sunday in the log")

    # Admitted downstream for the verdict a human accepted, and only that one.
    if universe.check_admissible(written) is not None:
        failures.append("the forced universe is still refused by check_admissible, "
                        "so discover would reject it every morning until the next "
                        "rebuild and --force would have bought nothing")

    # An override answers the verdict it names and leaves every other one
    # standing. That used to be asserted by mutating the count by one, which is
    # the one mutation that cannot detect the hole: the count floor is the LAST
    # check and the only one still reachable once a count override matches, so
    # the mutation moved the text of the check that was never at risk and passed
    # against the broken implementation as happily as against a sound one.
    #
    # The hole is a file whose override names a verdict from an EARLIER check.
    # Builds before the override was scoped could write one: --force recorded
    # whatever verdict came back first, and if that was the unswept ceiling then
    # check_admissible matched it, returned from inside that branch, and never
    # reached the count floor at all. The floor was off, in discover, every
    # morning until the next Sunday, on precisely the file that most needed it.
    # So the payload here carries an unswept override AND a count below the
    # floor, and the whole claim is that it is still refused.
    ceiling = _CRIT.number("universe", "max_unswept_fraction")
    starved = dict(written)
    starved.pop("admissibility_override", None)
    examined = int(written["count"])
    starved["market_cap_funnel"] = {
        "examined": examined,
        "in_an_unanswered_batch": int(examined * (ceiling + 0.05)) + 1,
    }
    unswept_verdict = universe.check_admissible(starved)
    if not unswept_verdict:
        failures.append("a funnel far above the max_unswept_fraction ceiling was "
                        "admitted, so this claim never built the payload it "
                        f"needs: {starved['market_cap_funnel']}")
    else:
        starved["admissibility_override"] = {"verdict": unswept_verdict}
        if universe.check_admissible(starved) is None:
            failures.append(
                "a universe carrying an unswept-batch override was admitted "
                f"whole, with {starved['count']} names against "
                f"{starved['previous_count']}. The override answered a verdict "
                "nobody applied it to and the count floor below it never ran, so "
                "discover would take that file every morning until the next "
                "rebuild")

    # The other half of the same design, at build time rather than read time:
    # --force reaches one verdict, and the refusal has said which since the day
    # it was written, that names in a batch which answered nothing are the case
    # the gate exists for. Driven with a vendor that answers no market cap batch
    # at all, which is what a quota starved sweep looks like from inside build().
    forced_bytes = config.UNIVERSE_PATH.read_bytes()
    starved_routes = [
        (needle, (lambda path, params: {"data": {}})
         if needle == "us-quote-delayed" else route)
        for needle, route in ROUTES
    ]
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        starved_run = _drive("universe", "selection.universe", ["--force"],
                             routes=starved_routes)
    sys.stdout.write(printed.getvalue())

    if starved_run.error:
        failures.append(f"universe raised out of main on a starved sweep: "
                        f"{starved_run.error}")
    else:
        if starved_run.code != 1 or starved_run.status != job_status.STATUS_ERROR:
            failures.append(
                f"a --force run whose market cap sweep answered nothing exited "
                f"{starved_run.code} and recorded {starved_run.status!r}, "
                "expected 1 and an error. --force is the answer to a shrink the "
                "gate cannot judge, not a way past a sweep that lost its batches")
        if config.UNIVERSE_PATH.read_bytes() != forced_bytes:
            failures.append(
                "--force wrote a universe whose market cap sweep answered "
                "nothing over the previous one. The sweep runs in dollar volume "
                "order, so that file is not a smaller universe, it is one with "
                "its illiquid tail amputated, and it is exactly what this gate "
                "exists to keep out of discover")
        if "--force does not apply" not in printed.getvalue():
            failures.append(
                "the refusal of a --force run never says that --force does not "
                "reach this verdict, so the operator reads it as a flag that "
                "failed rather than as one that does not apply here, and the "
                "next thing they reach for is deleting universe.json")

    print(f"  {'force':<12} the gate refused {written['count']} names against "
          f"{previous_count} and left the old file alone; --force wrote it and "
          "recorded the verdict, and did not reach the unswept verdict")


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

    The replay opens with one non fatal status frame as well, and the second
    half of this claim is that the frame reaches the stats file. run_websocket
    collects those frames for the reason stated where status_frames is
    declared: a morning that saw six odd frames and still worked is a
    different morning from a clean one, and the run stats are where that
    difference has to survive. It did not survive. The count and the frames
    were both computed, both printed, and then left out of the record appended
    to <day>-stats.jsonl, so the difference lived only in a log line that rolls.
    The printed line was never the problem, which is why this asserts the file
    the morning leaves behind and not the collector's output.
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

    stats_file = collect_premarket.stats_path()
    lines = ([line for line in stats_file.read_text(encoding="utf-8").splitlines()
              if line.strip()] if stats_file.is_file() else [])
    if not lines:
        failures.append(f"the collector appended no run stats record to "
                        f"{stats_file.name}, so nothing about this run outlives "
                        "the log")
        return
    # The last line is this run's: the file is append only and the sandbox may
    # carry a real morning's earlier records in the copied data directory.
    record = json.loads(lines[-1])
    if not record.get("status_frames"):
        failures.append(
            "the collector saw a non fatal status frame and its stats record "
            f"says status_frames={record.get('status_frames')!r}. A morning that "
            "saw odd frames and still worked is then indistinguishable from a "
            "clean one the moment the log rolls.")
    seen = record.get("status_frames_seen") or []
    wanted = REPLAY_STATUS_FRAME["status_code"]
    if not any(isinstance(frame, dict) and frame.get("status_code") == wanted
               for frame in seen):
        failures.append(
            f"the stats record does not carry the status {wanted} frame itself "
            f"in status_frames_seen: {seen!r}. The count says how many, only "
            "the frames say what the server actually objected to.")
    print(f"  {'collector':<12} {record.get('status_frames')} status frame(s) "
          f"reached {stats_file.name}, first {seen[0] if seen else None}")


# The non fatal frame the replay opens with. A 500 and not a 422 on purpose:
# 422 is the refusal that must end the run, claimed above, and this is the
# other kind, the odd frame a morning survives and must still be able to name
# afterwards.
REPLAY_STATUS_FRAME = {"status_code": 500, "message": "Server error"}


class _ReplaySocket:
    """A socket that yields one status frame, then canned trades for all but
    the last symbol."""

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.sent = 0
        # Deliberately silent, to exercise the coverage report.
        self.silent = symbols[-1] if symbols else None
        # Ahead of the trades, so the run both sees it and carries on. Real
        # mornings get these mid stream; first is simply where a replay can
        # guarantee it arrives before the socket is exhausted.
        self.status_sent = False

    def recv(self) -> str | None:
        import websocket

        if not self.status_sent:
            self.status_sent = True
            return json.dumps(REPLAY_STATUS_FRAME)

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

    claim_packet_names_its_build(failures)
    claim_scan_survives_an_empty_pool(failures)
    claim_scan_degrades_on_a_thin_meter(failures)


def claim_packet_names_its_build(failures: list[str]) -> None:
    """A packet that reached disk can say which commit wrote it.

    scan.py has built the `build` block into its payload since 2026-08-14, but
    nothing asserted that it survives to the file. The existing check tested
    config.build_identifier() in isolation, which passes even if the key is
    dropped from the payload or write_packet stops writing it.

    That gap is not academic. Neither runs/2026-08-13/packet.json nor
    runs/2026-08-14/packet.json carries the key, because both were written
    before the line existed, and 2026-08-14 is precisely the morning whose
    report could not be tied back to the code that produced it. The whole
    point of the block is to make that impossible a second time, and an
    untested guarantee is not one.

    A null commit is allowed and is not a failure: an export with no .git is a
    legitimate way to run this. What must not happen is the key being ABSENT,
    because then the packet cannot even say that it does not know.
    """
    from core import config
    from morning import scan

    day = ettime.today_str()
    path = config.run_dir(day) / "packet.json"
    if not path.is_file():
        # The vintage gate refused this run's canned data, which is the gate
        # working. Build a payload straight from the writer instead, so the
        # claim is still exercised rather than silently skipped.
        payload = {"session_date": day, "build": config.build_identifier()}
        path = scan.write_packet(payload)

    written = json.loads(path.read_text(encoding="utf-8"))
    if "build" not in written:
        failures.append(f"{path.name} has no build block, so the report it feeds "
                        "cannot be tied to a commit")
        return
    build = written["build"] or {}
    for key in ("commit", "dirty"):
        if key not in build:
            failures.append(f"{path.name} build block has no {key}: {build}")
    print(f"  {'packet':<12} names its build: commit "
          f"{str(build.get('commit'))[:12]} dirty={build.get('dirty')}")


def claim_scan_survives_an_empty_pool(failures: list[str]) -> None:
    """A morning with nothing subscribed writes a zero candidate packet.

    Both architecture pages describe this as the discover.py failure: the
    watchlist is absent or empty, the collector heard nothing, and the report
    still goes out with no candidates and the holes named. It did not. Every
    per candidate stage in build_packet lives inside one `if candidates:`
    block, and dropped_stale was bound there and read unconditionally in the
    payload, so an empty pool ended the scan with UnboundLocalError. The chain
    stops on the first non-zero exit, so the documented degrade path was in
    fact the total loss path: no packet, no report, no email.

    Driven both ways, because the two arrive by different routes and the
    payload is assembled once for both. A watchlist that is present and holds
    no subscribed row is what a quiet 07:15 leaves; a watchlist that is not on
    disk at all is what a discover that died leaves.
    """
    from morning import scan

    day = ettime.today_str()
    packet_path = config.run_dir(day) / "packet.json"
    # claim_analyst runs next and reads this file, so whatever the working
    # morning left is put back before returning.
    saved_packet = packet_path.read_bytes() if packet_path.is_file() else None
    saved_watchlist = (config.WATCHLIST_PATH.read_bytes()
                       if config.WATCHLIST_PATH.is_file() else None)

    cases = (
        ("empty", lambda: config.WATCHLIST_PATH.write_text(
            json.dumps({"generated_at": ettime.stamp(ettime.now_et()),
                        "pool_size": 0, "subscribed_count": 0, "symbols": []}),
            encoding="utf-8")),
        ("absent", lambda: config.WATCHLIST_PATH.unlink(missing_ok=True)),
    )
    try:
        for label, arrange in cases:
            arrange()
            _install(ROUTES)
            try:
                payload = scan.build_packet()
            except BaseException as exc:  # noqa: BLE001
                failures.append(
                    f"scan raised on an {label} watchlist: {type(exc).__name__}: "
                    f"{exc}. The degrade path both architecture pages describe "
                    "is a zero candidate packet, not a dead chain.")
                continue
            finally:
                _uninstall()

            if payload.get("candidates"):
                failures.append(f"an {label} watchlist produced "
                                f"{len(payload['candidates'])} candidates")
            for key in ("dropped_no_coverage", "dropped_stale_price"):
                if payload.get(key) != []:
                    failures.append(f"an {label} watchlist left {key} as "
                                    f"{payload.get(key)!r}, expected an empty list")
            if not payload.get("gaps_to_fill"):
                failures.append(f"an {label} watchlist wrote no gaps_to_fill, so "
                                "the report would not say why it is empty")
            written = scan.write_packet(payload)
            if not written.is_file():
                failures.append(f"an {label} watchlist wrote no packet to disk")
        print("  empty pool   an absent and an empty watchlist both write a zero "
              "candidate packet that names its own gaps")
    finally:
        if saved_watchlist is None:
            config.WATCHLIST_PATH.unlink(missing_ok=True)
        else:
            config.WATCHLIST_PATH.write_bytes(saved_watchlist)
        if saved_packet is None:
            packet_path.unlink(missing_ok=True)
        else:
            packet_path.write_bytes(saved_packet)


def claim_scan_degrades_on_a_thin_meter(failures: list[str]) -> None:
    """Three points around the degrade threshold, asserted on the OUTPUT.

    Claim 12 in test_pool covers the refuse floor, where the job does not run
    at all and the exit code is the whole story. The degrade threshold is the
    higher risk of the two and needs a different kind of assertion, because
    the job DOES run: it produces a packet, and the question is whether that
    packet tells the truth about being thin.

    That matters because thin mode is where the false reason defects lived. A
    packet whose catalyst reads "none" when the news feed was never called is
    not a thin packet, it is a wrong one, and it is wrong in the direction
    that looks fine. Checking the exit code cannot see any of that, so nothing
    here checks the exit code.

    Three assertions on a degraded run, all on what it wrote:
      a packet exists at all, rather than the run refusing;
      gaps_to_fill names the meter reading, so the thinness is attributable;
      catalyst is UNKNOWN rather than none, on every candidate.
    """
    from core import criteria, eodhd

    crit = criteria.load()
    threshold = crit.integer("quota", "degrade_below_remaining")
    floor = crit.integer("quota", "refuse_below_remaining")
    limit = conftest.HEALTHY_METER["dailyRateLimit"]

    cases = (
        ("just below the threshold", limit - (threshold - 1), True),
        ("exactly at the threshold", limit - threshold, False),
        ("comfortably above", limit - (threshold * 10), False),
    )

    for label, used, should_degrade in cases:
        remaining = limit - used
        if remaining < floor:
            failures.append(f"the {label} case sits below the refuse floor, so it "
                            "tests refusal rather than degradation")
            continue

        with conftest.meter_reading(apiRequests=used):
            record = eodhd.preflight("test")
            if record["degraded"] != should_degrade:
                failures.append(
                    f"a meter {label} ({remaining:,} remaining against a "
                    f"{threshold:,} threshold) set degraded={record['degraded']}, "
                    f"expected {should_degrade}")
                continue
            if record["refused"]:
                failures.append(f"a meter {label} refused, which is the wrong path")
                continue
            if not should_degrade:
                continue

            _write_universe()
            _write_watchlist()
            # Pinned to the scan's own run time. The pipeline this claim is
            # about only assembles candidates under morning conditions: prices
            # older than CRITERIA [price age] are dropped, and the collector
            # coverage window is the premarket. Run at 21:00 every candidate
            # is correctly discarded and the packet is empty, so the claim
            # would pass at 08:45 and fail all evening while testing nothing
            # either way.
            with _clock_pinned_to_scan_time():
                _write_collector_bars()
                outcome = _drive("scan", "morning.scan", [])
            if outcome.error:
                failures.append(f"a degraded scan raised out of main: {outcome.error}")
                continue

            # ---- the packet exists, which is the first claim
            #
            # Whichever packet the DEGRADED run wrote, which is not always
            # packet.json. A quota thinned rerun of a day that already has a
            # full width packet stands down and writes packet_degraded.json
            # beside it rather than overwriting better evidence with worse.
            # That is correct behaviour and the first version of this claim
            # walked straight past it, reading the fuller packet and reporting
            # three defects that were really one wrong filename.
            day = ettime.today_str()
            run_directory = config.run_dir(day)
            side = run_directory / "packet_degraded.json"
            packet_path = side if side.is_file() else run_directory / "packet.json"
            if not packet_path.is_file():
                # The vintage gate can legitimately refuse canned fixtures, and
                # that is a different outcome from a degraded run failing to
                # produce anything. Say which, rather than reporting a defect
                # that is not there.
                if outcome.code == 1:
                    print(f"  {'degrade':<12} {label}: scan exited 1 before writing a "
                          "packet, which the vintage gate does on canned data. The "
                          "preflight verdict was still asserted.")
                    continue
                failures.append(f"a degraded scan wrote no packet and exited "
                                f"{outcome.code}")
                continue

            payload = json.loads(packet_path.read_text(encoding="utf-8"))

            # ---- gaps_to_fill names the reading, which is the second
            gaps = " ".join(str(g) for g in (payload.get("gaps_to_fill") or []))
            if str(record["remaining"]) not in gaps.replace(",", ""):
                failures.append(
                    f"a degraded packet does not name the {record['remaining']:,} "
                    f"remaining reading in gaps_to_fill: {gaps[:200]}")
            if not (payload.get("quota_preflight") or {}).get("degraded"):
                failures.append("a degraded packet does not record degraded=true in "
                                "quota_preflight")

            # ---- catalyst is unknown, not none, which is the third and the
            # one the false reason defects would have slipped past
            candidates = payload.get("candidates") or []
            if not candidates:
                failures.append("a degraded packet carried no candidates, so the "
                                "catalyst claim could not be tested")
            for candidate in candidates:
                if candidate.get("catalyst_found") is not None:
                    failures.append(
                        f"{candidate['symbol']} records catalyst_found="
                        f"{candidate['catalyst_found']!r} on a degraded run, expected "
                        "null: the feed was never called")
                if candidate.get("catalyst_class") == "none":
                    failures.append(
                        f"{candidate['symbol']} records catalyst_class 'none' on a "
                        "degraded run. That says the window was checked and empty. "
                        "It was never checked.")
                why = str(candidate.get("catalyst_why") or "")
                if "unknown" not in why.lower():
                    failures.append(
                        f"{candidate['symbol']} catalyst_why does not say unknown: "
                        f"{why[:120]}")

            print(f"  {'degrade':<12} {label}: {remaining:,} remaining, "
                  f"{packet_path.name} written, {len(candidates)} candidate(s) with "
                  "catalyst unknown, reading named in gaps_to_fill")

    print(f"  claim degrade  threshold {threshold:,} exercised from fed readings on "
          "both sides, asserted on packet output rather than exit code")


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
    # The stubbed model returns both watchlist tables with the literal header
    # rows from REPORT_TEMPLATE.md. It used to return one improvised
    # "| Ticker | Gap |" table, which passed a guard that counted ticker
    # columns. The guard now requires these two tables BY NAME, because
    # counting columns stopped working the moment a third table could carry a
    # Ticker header, so a stub that would be rejected in production must be
    # rejected here.
    # Same skeleton as the report fixture, from the template.
    # Two parameters, because a flagged narrative is regenerated with the
    # rejected sentences appended to the piped document. A one parameter
    # stub would pass here and TypeError on the morning the guard fires.
    analyst.invoke_claude = lambda packet_text, correction=None: (
        "# Premarket\n\n"
        + conftest.watchlist_table("day watchlist",
                                   ["| AAPL | +3.1% | 100.00 | 1.8 | 101.00 | 100.50 | 6.0 | green |"])
        + "\n"
        + conftest.watchlist_table("swing watchlist")
        + "\nNothing here is advice.\n",
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
    claim_verification_is_not_gated_on_picks(failures)


def claim_verification_is_not_gated_on_picks(failures: list[str]) -> None:
    """The collector volume check runs on a day with no live picks rows.

    This is the instrument for BUILD_PLAN.md's top open question, and it used
    to sit at the tail of backfill(), after the early return that fires when a
    day has no live picks. Emptying picks on 2026-08-19 therefore also stopped
    the nightly writing runs/<date>/verify_intraday.json, on the night the
    question it measures got most urgent, and nothing said so. An instrument
    gated on the thing it measures is not an instrument.

    Driven with picks deliberately empty for the day under test, which is also
    the state of the real database today, so this asserts against the situation
    the machine is actually in rather than a hypothetical one.

    On YESTERDAY rather than today because the stubbed vendor serves yesterday's
    minutes from its intraday route, and the check compares identical minutes
    only: a collector file stamped today would intersect it on nothing and the
    claim would pass or fail for a reason that has nothing to do with the gate.
    """
    from collect import collect_premarket
    from core import store
    from night import backfill_premarket

    day = YESTERDAY.isoformat()
    verify_path = config.run_dir(day) / "verify_intraday.json"
    bars_path = collect_premarket.bar_path(day)
    saved_verify = verify_path.read_bytes() if verify_path.is_file() else None
    saved_bars = bars_path.read_bytes() if bars_path.is_file() else None

    # Bars on exactly the minutes the stub's intraday route serves, at a volume
    # that deliberately disagrees with it, so a real comparison happens and
    # produces a real disagreement rather than an empty intersection.
    rows = [
        json.dumps({
            "symbol": "AAPL.US", "minute_epoch": int(bar["timestamp"]),
            "minute_et": ettime.stamp(ettime.from_epoch_s(int(bar["timestamp"]))),
            "o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0,
            "v": 9_000.0, "pv": 900_000.0, "trades": 12,
        })
        for bar in _intraday_rows(YESTERDAY)
    ]
    bars_path.parent.mkdir(parents=True, exist_ok=True)
    bars_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    try:
        with store.session() as connection:
            store.init(connection)
            live = connection.execute(
                "SELECT COUNT(*) FROM picks WHERE date=? AND source='live'", (day,)
            ).fetchone()[0]
            connection.commit()
        if live:
            print(f"  verify gate  SKIPPED, the sandbox database holds {live} live "
                  f"pick(s) for {day}, so the ungated path is not the one under test")
            return

        verify_path.unlink(missing_ok=True)
        _install(ROUTES)
        try:
            code = backfill_premarket.backfill(day, overwrite=True)
        finally:
            _uninstall()

        if code != 0:
            failures.append(f"backfill exited {code} on a day with no live picks; "
                            "an empty table is not a failure")
        if not verify_path.is_file():
            failures.append(
                "backfill wrote no verify_intraday.json for a day with no live "
                "picks rows. The collector volume check reads the bar file, not "
                "the picks table, and must not be gated on it.")
            return

        summary = json.loads(verify_path.read_text(encoding="utf-8"))
        for key in ("day", "compared", "within_one_percent", "median_abs_pct"):
            if key not in summary:
                failures.append(f"the verification summary has no {key}: {summary}")
        if summary.get("compared", 0) < 1:
            failures.append(f"the verification compared nothing: {summary}")
        if summary.get("day") != day:
            failures.append(f"the summary is stamped {summary.get('day')}, not {day}")
        # The fixture disagrees by 10 percent on purpose, so a summary claiming
        # agreement would mean the comparison never ran on these bars.
        if summary.get("within_one_percent"):
            failures.append(
                f"the fixture's 9,000 shares a minute against the vendor's 10,000 "
                f"came back as {summary['within_one_percent']} symbol(s) within one "
                "percent, so the numbers being compared are not the ones written")
        print(f"  verify gate  written with picks empty for {day}, "
              f"{summary.get('compared')} symbol(s) compared, median absolute "
              f"difference {summary.get('median_abs_pct'):.1f}%")

        # And the sweep that finds a session nobody measured, which is the other
        # half: a day with no picks row is invisible to the true-column catch-up.
        found = backfill_premarket.unverified_sessions(
            ettime.today_str(), _CRIT.integer("backfill", "catchup_days"))
        if day in found:
            failures.append(f"{day} still reads as unverified after its summary "
                            "was written, so the sweep would measure it every night")
    finally:
        if saved_bars is None:
            bars_path.unlink(missing_ok=True)
        else:
            bars_path.write_bytes(saved_bars)
        if saved_verify is None:
            verify_path.unlink(missing_ok=True)
        else:
            verify_path.write_bytes(saved_verify)


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
    claim_ok_codes_declared(failures)
    claim_subscription_refusal_is_fatal(failures)
    claim_operator_tools_spare_artifacts(failures)
    claim_calendar(failures)
    claim_calendar_refresh_keeps_the_cache(failures)
    claim_universe(failures)
    claim_universe_force(failures)
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
