"""EODHD All-In-One client.

The only market data provider in this project. There is no second source, no
yfinance, no fallback vendor. If a number is not in here it does not exist.

Two rules shape the whole module.

One, every single HTTP call goes through _request. That is where the retry on
429 lives, that is where the per run counter is incremented, and that is where
failures are turned into a returned value instead of an exception. Nothing in
this file calls requests directly anywhere else.

Two, no endpoint method ever raises at the caller. Each returns an ApiResult,
which is a (data, error) pair. On success error is None. On failure data is
None and error carries a human readable note that is good enough to paste into
the gaps_to_fill list of a packet. A morning run that loses one endpoint must
still produce a report saying which endpoint it lost.

The call counter prints at the end of every run whether or not the script
remembers to ask for it.

Endpoints wrapped, and only these:
    bulk live OHLCV for US exchanges   /real-time/{any}.US?ex=US
    delayed US quotes                  /us-quote-delayed?s=...
    intraday 1 minute bars             /intraday/{symbol}?interval=1m
    end of day historical              /eod/{symbol}
    exchange symbol list               /exchange-symbol-list/{exchange}
    financial news                     /news?s=...
    economic events                    /economic-events
    earnings calendar                  /calendar/earnings
    the account meter                  /user
"""

from __future__ import annotations

import atexit
import datetime as dt
import json
import time
from collections import Counter
from typing import Any, Iterable, NamedTuple

import requests

import config
import criteria
import ettime

_CRIT = criteria.load()

MAX_ATTEMPTS = _CRIT.integer("api", "max_attempts")
BACKOFF_START_S = _CRIT.number("api", "retry_backoff_start_s")
BACKOFF_MAX_S = _CRIT.number("api", "retry_backoff_max_s")
CONSECUTIVE_429_TRIP = _CRIT.integer("quota", "consecutive_429_trip")
RETRY_BUDGET_PER_RUN = _CRIT.integer("quota", "retry_budget_per_run")
TIMEOUT_S = _CRIT.number("api", "timeout_s")
BULK_TIMEOUT_S = _CRIT.number("api", "bulk_timeout_s")
QUOTE_BATCH_SIZE = _CRIT.integer("api", "quote_batch_size")
NEWS_LIMIT = _CRIT.integer("api", "news_limit")

# Status codes worth another try. 429 is the one the brief names, the 5xx
# family is added because a gateway blip should not cost us the morning.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class _TlsAdapter(requests.adapters.HTTPAdapter):
    """Carries our SSLContext into urllib3 so the trust decision actually applies."""

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
    session.headers.update({"User-Agent": "PremarketDesk/1.0"})
    session.verify = config.ca_bundle()
    session.mount("https://", _TlsAdapter(config.tls_context()))
    return session


class ApiResult(NamedTuple):
    """(data, error). Exactly one of the two is set."""

    data: Any | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None

    def or_empty(self, fallback: Any) -> Any:
        return self.data if self.ok and self.data is not None else fallback


class CallLedger:
    """Per run accounting for every HTTP call the process makes."""

    def __init__(self) -> None:
        self.calls = 0
        self.failures = 0
        self.retries = 0
        self.by_endpoint: Counter[str] = Counter()
        self.errors: list[str] = []
        self.started = ettime.now_et()
        self.first_call_quota_day: str | None = None
        # Circuit breaker state, per run. Consecutive 429s prove the shared
        # quota is gone; once tripped, every later call in this process fails
        # fast with the reason recorded instead of rediscovering the limit
        # through its own backoff. See CRITERIA.md [quota].
        self.consecutive_429 = 0
        self.circuit_open_reason: str | None = None
        self.suppressed = 0
        self._reported = False

    def record(self, endpoint: str, attempts: int, error: str | None) -> None:
        if self.first_call_quota_day is None:
            self.first_call_quota_day = quota_day()
        self.calls += attempts
        self.retries += attempts - 1
        self.by_endpoint[endpoint] += attempts
        if error:
            self.failures += 1
            self.errors.append(f"{endpoint}: {error}")

    def summary(self) -> str:
        elapsed = (ettime.now_et() - self.started).total_seconds()
        lines = [
            "",
            "EODHD call report",
            f"  total http calls   {self.calls}",
            f"  of which retries   {self.retries}",
            f"  failed endpoints   {self.failures}",
            f"  wall clock         {elapsed:.1f}s",
        ]
        if self.suppressed:
            lines.append(f"  suppressed calls   {self.suppressed} "
                         "(quota circuit open, failed fast without HTTP)")
        # The day is captured at the first recorded call, because a run that
        # straddles the 00:00 UTC reset would otherwise label all of its spend
        # with the post boundary day, defeating the line's whole purpose.
        exit_day = quota_day()
        billed_day = self.first_call_quota_day or exit_day
        if billed_day != exit_day:
            lines.append(f"  quota day          {billed_day} at the first call, "
                         f"{exit_day} at exit; the run straddled the 00:00 UTC reset")
        else:
            lines.append(f"  quota day          {billed_day} "
                         "(the shared counter resets 00:00 UTC)")
        for endpoint, count in self.by_endpoint.most_common():
            lines.append(f"    {count:>5}  {endpoint}")
        for note in self.errors:
            lines.append(f"    error  {note}")
        return "\n".join(lines)

    def report(self) -> None:
        if self._reported:
            return
        self._reported = True
        print(self.summary())


LEDGER = CallLedger()
atexit.register(LEDGER.report)


def quota_day(when: dt.datetime | None = None) -> str:
    """The vendor quota day a moment bills to: the UTC calendar date.

    The daily counter resets at midnight UTC, which is 20:00 ET in daylight
    time and 19:00 in standard time. One ET weekday therefore spans two quota
    days: the morning jobs bill to the day that opened the previous evening,
    and the 22:15 nightly bills to the next one. A sibling project running in
    the evening competes with the following morning, not with the day it
    feels like it belongs to.
    """
    return (when or ettime.now_et()).astimezone(ettime.UTC).date().isoformat()


class QuotaRefusal(RuntimeError):
    """Raised when the preflight reading is below the refuse floor."""


def print_call_report() -> None:
    """Print the call count. Safe to call more than once, prints only once."""
    LEDGER.report()


def call_count() -> int:
    return LEDGER.calls


def _sleep_for(attempt: int, retry_after: str | None) -> float:
    """Exponential backoff, but honour a Retry-After header when the server sends one."""
    if retry_after:
        try:
            return min(float(retry_after), BACKOFF_MAX_S)
        except ValueError:
            pass
    return min(BACKOFF_START_S * (2 ** (attempt - 1)), BACKOFF_MAX_S)


class EodhdClient:
    """Thin wrapper. One session, one chokepoint, one counter."""

    def __init__(self, token: str | None = None, ledger: CallLedger | None = None) -> None:
        self._token = token or config.eodhd_token()
        # Certificate verification stays on. build_session widens the trust
        # store when a local security suite is re-signing TLS.
        self._session = build_session()
        self.ledger = ledger or LEDGER

    # ---- the one and only chokepoint --------------------------------------

    def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        endpoint: str | None = None,
        timeout: float | None = None,
    ) -> ApiResult:
        """Every HTTP call in this project goes through here. It never raises.

        Two run wide bounds live here, both from CRITERIA.md [quota]. Once
        consecutive 429s reach the trip count the circuit opens: this call and
        every later one in the process fails fast with the reason recorded,
        because each call rediscovering an exhausted quota through its own
        backoff is how a morning grinds past the open. And once the run has
        spent its total retry budget, every remaining call gets one attempt.
        """
        label = endpoint or path
        if self.ledger.circuit_open_reason:
            self.ledger.suppressed += 1
            return ApiResult(None, f"{label} failed: {self.ledger.circuit_open_reason}")

        query: dict[str, Any] = {"api_token": self._token, "fmt": "json"}
        query.update(params or {})
        url = f"{config.EODHD_BASE_URL}/{path.lstrip('/')}"
        attempts = 0
        last_error = "no attempt was made"

        def may_retry(current_attempts: int) -> bool:
            if current_attempts >= MAX_ATTEMPTS:
                return False
            if self.ledger.retries + (current_attempts - 1) >= RETRY_BUDGET_PER_RUN:
                print(f"eodhd: {label} not retried, the run's retry budget of "
                      f"{RETRY_BUDGET_PER_RUN} is spent (CRITERIA.md [quota])")
                return False
            return True

        while attempts < MAX_ATTEMPTS:
            attempts += 1
            try:
                response = self._session.get(
                    url, params=query, timeout=timeout or TIMEOUT_S
                )
            except requests.RequestException as exc:
                # Exception text can quote the full URL, token included.
                # Scrubbed here, at the one chokepoint every HTTP call goes
                # through, so no error string leaving this function can carry
                # a credential regardless of which caller records it.
                last_error = config.scrub_secrets(f"{type(exc).__name__}: {exc}")
                if may_retry(attempts):
                    time.sleep(_sleep_for(attempts, None))
                    continue
                break

            if response.status_code == 429:
                self.ledger.consecutive_429 += 1
                last_error = f"HTTP 429 after {attempts} attempts"
                if self.ledger.consecutive_429 >= CONSECUTIVE_429_TRIP:
                    self.ledger.circuit_open_reason = (
                        f"quota circuit open: {self.ledger.consecutive_429} consecutive "
                        "429s say the shared key is exhausted; failing fast for the "
                        "rest of this run (CRITERIA.md [quota] consecutive_429_trip)"
                    )
                    print(f"eodhd: {self.ledger.circuit_open_reason}")
                    last_error = self.ledger.circuit_open_reason
                    break
                if may_retry(attempts):
                    wait = _sleep_for(attempts, response.headers.get("Retry-After"))
                    print(f"eodhd: {label} returned 429, retrying in {wait:.0f}s "
                          f"(attempt {attempts} of {MAX_ATTEMPTS})")
                    time.sleep(wait)
                    continue
                break

            self.ledger.consecutive_429 = 0
            if response.status_code in _RETRY_STATUSES:
                last_error = f"HTTP {response.status_code} after {attempts} attempts"
                if may_retry(attempts):
                    wait = _sleep_for(attempts, response.headers.get("Retry-After"))
                    print(
                        f"eodhd: {label} returned {response.status_code}, "
                        f"retrying in {wait:.0f}s (attempt {attempts} of {MAX_ATTEMPTS})"
                    )
                    time.sleep(wait)
                    continue
                break

            if response.status_code != 200:
                # A vendor error body can echo the request, so it is scrubbed
                # like exception text.
                body = config.scrub_secrets((response.text or "")[:200].replace("\n", " "))
                last_error = f"HTTP {response.status_code}: {body}"
                break

            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                body = config.scrub_secrets((response.text or "")[:200].replace("\n", " "))
                last_error = f"response was not JSON ({exc}): {body}"
                break

            self.ledger.record(label, attempts, None)
            return ApiResult(payload, None)

        # Belt over the branch level scrubs: nothing recorded, printed or
        # returned from the chokepoint may carry a credential.
        last_error = config.scrub_secrets(last_error)
        self.ledger.record(label, attempts, last_error)
        print(f"eodhd: {label} failed, {last_error}")
        return ApiResult(None, f"{label} failed: {last_error}")

    # ---- endpoints --------------------------------------------------------

    def bulk_live_us(self) -> ApiResult:
        """Latest live OHLCV for every US listed ticker, in one call.

        The ticker in the path is a placeholder. ex=US is what makes it bulk.
        Returns a list of dicts carrying code, timestamp, open, high, low,
        close, volume, previousClose, change and change_p.
        """
        result = self._request(
            "real-time/AAPL.US",
            params={"ex": "US"},
            endpoint="bulk-live-us",
            timeout=BULK_TIMEOUT_S,
        )
        if not result.ok:
            return result
        rows = result.data
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return ApiResult(None, "bulk-live-us failed: payload was not a list")
        return ApiResult(rows, None)

    def eod_bulk_last_day(
        self,
        exchange: str = "US",
        day: dt.date | None = None,
        symbols: Iterable[str] | None = None,
        extended: bool = False,
    ) -> ApiResult:
        """One session of end of day bars for a whole exchange, in one call.

        This is how the weekly universe build gets twenty sessions of history
        for every US listing in twenty calls rather than five thousand. Note
        that the extended filter adds company name, EMA 50, EMA 200 and average
        volumes, but not market capitalisation. Market cap comes from
        us-quote-delayed so that the universe and the morning scan are reading
        the same field.
        """
        params: dict[str, Any] = {}
        if day:
            params["date"] = day.isoformat()
        if extended:
            params["filter"] = "extended"
        symbol_list = [s for s in (symbols or []) if s]
        if symbol_list:
            params["symbols"] = ",".join(symbol_list)
        result = self._request(
            f"eod-bulk-last-day/{exchange}",
            params=params,
            endpoint="eod-bulk-last-day",
            timeout=BULK_TIMEOUT_S,
        )
        if not result.ok:
            return result
        rows = result.data
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return ApiResult(None, "eod-bulk-last-day: payload was not a list")
        return ApiResult(rows, None)

    def quote_delayed(self, symbols: Iterable[str]) -> ApiResult:
        """Delayed US quotes keyed by symbol.

        This is where ethVolume, ethTime, marketCap, sharesFloat,
        averageVolume, twoHundredDayAveragePrice and previousClosePrice come
        from. Requests are chunked, and a chunk that fails leaves its symbols
        out of the result rather than losing the whole batch.
        """
        wanted = [s.strip().upper() for s in symbols if s and s.strip()]
        if not wanted:
            return ApiResult({}, None)

        merged: dict[str, Any] = {}
        failed_chunks: list[str] = []
        for start in range(0, len(wanted), QUOTE_BATCH_SIZE):
            chunk = wanted[start:start + QUOTE_BATCH_SIZE]
            result = self._request(
                "us-quote-delayed",
                params={"s": ",".join(chunk)},
                endpoint="us-quote-delayed",
            )
            if not result.ok:
                failed_chunks.append(result.error or "unknown error")
                continue
            payload = result.data
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                merged.update(data)
            elif isinstance(payload, dict) and "symbol" in payload:
                merged[str(payload["symbol"]).upper()] = payload
            elif isinstance(payload, list):
                for row in payload:
                    if isinstance(row, dict) and row.get("symbol"):
                        merged[str(row["symbol"]).upper()] = row

        if not merged and failed_chunks:
            return ApiResult(None, "; ".join(failed_chunks))
        if failed_chunks:
            missing = sorted(set(wanted) - set(merged))
            return ApiResult(
                merged,
                f"us-quote-delayed partially failed, missing {len(missing)} symbols "
                f"({', '.join(missing[:10])}): {failed_chunks[0]}",
            )
        return ApiResult(merged, None)

    def live_quotes(self, symbols: Iterable[str]) -> ApiResult:
        """Live v1 for a handful of named symbols, keyed by symbol.

        Only the collector's --poll fallback and its verification mode use
        this. The normal websocket path spends no REST calls at all.
        """
        wanted = [s.strip().upper() for s in symbols if s and s.strip()]
        if not wanted:
            return ApiResult({}, None)

        merged: dict[str, Any] = {}
        errors: list[str] = []
        for start in range(0, len(wanted), QUOTE_BATCH_SIZE):
            chunk = wanted[start:start + QUOTE_BATCH_SIZE]
            params: dict[str, Any] = {}
            if len(chunk) > 1:
                params["s"] = ",".join(chunk[1:])
            result = self._request(
                f"real-time/{chunk[0]}", params=params, endpoint="real-time-live"
            )
            if not result.ok:
                errors.append(result.error or "unknown error")
                continue
            rows = result.data
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows or []:
                code = str(row.get("code") or "").strip().upper()
                if code:
                    merged[code] = row

        if not merged and errors:
            return ApiResult(None, "; ".join(errors))
        if errors:
            return ApiResult(merged, f"real-time-live partially failed: {errors[0]}")
        return ApiResult(merged, None)

    def intraday(
        self,
        symbol: str,
        start: dt.datetime,
        end: dt.datetime,
        interval: str = "1m",
    ) -> ApiResult:
        """One minute bars. Timestamps come back as UTC unix seconds."""
        return self._request(
            f"intraday/{symbol}",
            params={
                "interval": interval,
                "from": ettime.epoch_s(start),
                "to": ettime.epoch_s(end),
            },
            endpoint=f"intraday-{interval}",
        )

    def eod(
        self,
        symbol: str,
        start: dt.date | None = None,
        end: dt.date | None = None,
        period: str = "d",
    ) -> ApiResult:
        """Daily bars: date, open, high, low, close, adjusted_close, volume."""
        params: dict[str, Any] = {"period": period, "order": "a"}
        if start:
            params["from"] = start.isoformat()
        if end:
            params["to"] = end.isoformat()
        result = self._request(f"eod/{symbol}", params=params, endpoint="eod")
        if not result.ok:
            return result
        rows = result.data
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return ApiResult(None, f"eod {symbol} failed: payload was not a list")
        return ApiResult(rows, None)

    def user_status(self) -> ApiResult:
        """The account meter: apiRequests used today against dailyRateLimit.

        The counter is account wide, shared by every consumer of the key, and
        resets at midnight UTC. Reading it is itself one API call.
        """
        result = self._request("user", endpoint="user")
        if not result.ok:
            return result
        if not isinstance(result.data, dict):
            return ApiResult(None, "user: payload was not an object")
        return result

    def exchange_details(self, exchange: str) -> ApiResult:
        """Exchange metadata: official holidays, early closes, trading hours."""
        result = self._request(
            f"exchange-details/{exchange}",
            endpoint="exchange-details",
        )
        if not result.ok:
            return result
        if not isinstance(result.data, dict):
            return ApiResult(None, f"exchange-details {exchange}: payload was not an object")
        return result

    def exchange_symbol_list(self, exchange: str) -> ApiResult:
        """Every listed symbol on an exchange, with its security Type."""
        result = self._request(
            f"exchange-symbol-list/{exchange}",
            endpoint="exchange-symbol-list",
            timeout=BULK_TIMEOUT_S,
        )
        if not result.ok:
            return result
        if not isinstance(result.data, list):
            return ApiResult(None, f"exchange-symbol-list {exchange}: payload was not a list")
        return result

    def news(
        self,
        symbol: str,
        start: dt.date | None = None,
        end: dt.date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ApiResult:
        """News carrying the EODHD symbol tag.

        The symbol tag is the whole filter. There is no keyword matching, no
        company name regex and no stopword list anywhere in this project.
        """
        params: dict[str, Any] = {"s": symbol, "limit": limit or NEWS_LIMIT, "offset": offset}
        if start:
            params["from"] = start.isoformat()
        if end:
            params["to"] = end.isoformat()
        result = self._request("news", params=params, endpoint="news")
        if not result.ok:
            return result
        if not isinstance(result.data, list):
            return ApiResult(None, f"news {symbol}: payload was not a list")
        return result

    def news_feed(
        self,
        start: dt.date,
        end: dt.date,
        limit: int = 1000,
        offset: int = 0,
    ) -> ApiResult:
        """The whole news feed for a window, with no symbol filter.

        news() answers "what was said about this name". This answers "what was
        said", which is the question the 07:15 pool has to ask: it does not yet
        know which names to care about, and asking per symbol across a 2,745
        name universe is not a thing anyone can afford.

        The feed is global and carries crypto and non US listings, so the
        caller intersects the symbols array against universe.json. Verified on
        2026-08-14 that omitting the s parameter returns a general feed rather
        than an error.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        params["from"] = start.isoformat()
        params["to"] = end.isoformat()
        result = self._request("news", params=params, endpoint="news-feed")
        if not result.ok:
            return result
        if not isinstance(result.data, list):
            return ApiResult(None, "news feed: payload was not a list")
        return result

    def economic_events(
        self,
        country: str,
        start: dt.date,
        end: dt.date,
        limit: int = 1000,
    ) -> ApiResult:
        result = self._request(
            "economic-events",
            params={
                "country": country,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "limit": limit,
            },
            endpoint="economic-events",
        )
        if not result.ok:
            return result
        if not isinstance(result.data, list):
            return ApiResult(None, "economic-events: payload was not a list")
        return result

    def earnings_calendar(
        self,
        start: dt.date,
        end: dt.date,
        symbols: Iterable[str] | None = None,
    ) -> ApiResult:
        """Returns the earnings array, already unwrapped from its envelope."""
        params: dict[str, Any] = {"from": start.isoformat(), "to": end.isoformat()}
        symbol_list = [s for s in (symbols or []) if s]
        if symbol_list:
            params["symbols"] = ",".join(symbol_list)
        result = self._request(
            "calendar/earnings", params=params, endpoint="calendar-earnings"
        )
        if not result.ok:
            return result
        payload = result.data
        if isinstance(payload, dict):
            rows = payload.get("earnings")
            if isinstance(rows, list):
                return ApiResult(rows, None)
            return ApiResult(None, "calendar/earnings: no earnings array in the payload")
        if isinstance(payload, list):
            return ApiResult(payload, None)
        return ApiResult(None, "calendar/earnings: unexpected payload shape")


_default_client: EodhdClient | None = None


def client() -> EodhdClient:
    """Process wide client so the counter counts the whole run."""
    global _default_client
    if _default_client is None:
        _default_client = EodhdClient()
    return _default_client


def preflight(job: str) -> dict[str, Any]:
    """Read the shared account meter before a job spends anything.

    The key is shared across projects, so the quota remaining to this project
    is not a function of its own usage and cannot be inferred from the client
    side ledger. One call to /api/user answers what no local accounting can,
    and answers it before the retry budget is burned discovering it via 429s.

    Returns a record for the packet. Two thresholds from CRITERIA.md [quota]
    shape the verdict: below degrade_below_remaining the job should skip every
    call it can and say why, below refuse_below_remaining it should not run at
    all. The caller owns acting on the verdict; this function only reads,
    prints and records. A failed reading is an unknown meter, not a zero, so
    it degrades nothing.
    """
    threshold = _CRIT.integer("quota", "degrade_below_remaining")
    floor = _CRIT.integer("quota", "refuse_below_remaining")
    record: dict[str, Any] = {
        "quota_day": quota_day(),
        "meter_day": None,
        "read_at": ettime.stamp(ettime.now_et()),
        "api_requests": None,
        "daily_limit": None,
        "remaining": None,
        "degrade_below": threshold,
        "refuse_below": floor,
        "degraded": False,
        "refused": False,
        "error": None,
    }
    data, error = client().user_status()
    if error:
        record["error"] = error
        print(f"{job}: quota preflight could not read the meter ({error}). "
              "Proceeding at full width: an unknown meter is not a zero meter.")
        return record

    # A 200 payload is still untrusted input. A missing or null field must not
    # collapse into limit 0 and a fabricated "0 remaining": that would refuse
    # the morning on evidence that was never read, the exact substitution this
    # project forbids. Unreadable fields mean an unknown meter, full width.
    try:
        used = int(data.get("apiRequests"))
        limit = int(data.get("dailyRateLimit"))
    except (TypeError, ValueError):
        used = limit = -1
    if used < 0 or limit <= 0:
        record["error"] = (
            f"the meter payload was unreadable: apiRequests="
            f"{data.get('apiRequests')!r}, dailyRateLimit={data.get('dailyRateLimit')!r}"
        )
        print(f"{job}: quota preflight got an unreadable meter payload "
              f"({record['error']}). Proceeding at full width: an unknown meter "
              "is not a zero meter.")
        return record

    # The payload dates its own counter. A reading dated before the current
    # quota day is the prior day's spend still waiting to roll over, and acting
    # on it would thin or kill a morning whose budget is actually full.
    meter_day = str(data.get("apiRequestsDate") or "").strip() or None
    record["meter_day"] = meter_day
    if meter_day is not None and meter_day != record["quota_day"]:
        record["error"] = (
            f"the meter reading is dated {meter_day}, not the current quota day "
            f"{record['quota_day']}, so it describes another day's spend"
        )
        record.update({"api_requests": used, "daily_limit": limit})
        print(f"{job}: quota preflight read {used:,} of {limit:,}, but the reading "
              f"is dated {meter_day} while the current quota day is "
              f"{record['quota_day']}. A stale reading is another day's spend. "
              "Proceeding at full width and recording the reading as dated.")
        return record

    remaining = max(0, limit - used)
    record.update({"api_requests": used, "daily_limit": limit, "remaining": remaining})
    print(f"{job}: quota preflight reads {used:,} of {limit:,} daily calls used "
          f"on the shared key, {remaining:,} remaining, "
          f"billing to quota day {record['quota_day']}")

    if remaining < floor:
        record["refused"] = True
        record["degraded"] = True
        print(f"{job}: quota exhausted by another consumer on the shared key: "
              f"{remaining:,} of {limit:,} remain, below the refuse floor of {floor:,} "
              "in CRITERIA.md [quota]. Running would spend the retry budget "
              "against 429s, so the job refuses outright.")
    elif remaining < threshold:
        record["degraded"] = True
        print(f"{job}: quota exhausted by another consumer on the shared key: "
              f"{remaining:,} of {limit:,} remain, below the {threshold:,} threshold "
              "in CRITERIA.md [quota]. Proceeding only with the calls this job "
              "cannot skip.")
    return record


def describe_preflight(record: dict[str, Any]) -> str:
    """The quota reading as one clause, for gaps_to_fill and disclaimers."""
    if record.get("remaining") is None:
        return "the quota preflight could not read the shared meter"
    return (f"the shared API key had {record['remaining']:,} of "
            f"{record['daily_limit']:,} daily calls remaining at preflight "
            f"(quota day {record['quota_day']})")


def _smoke() -> int:
    """Checkpoint 3 done condition.

    Hit us-quote-delayed for AAPL.US, print ethVolume and ethTime, and report
    the call count.
    """
    api = client()
    symbol = "AAPL.US"
    print(f"smoke test: us-quote-delayed for {symbol}")

    data, error = api.quote_delayed([symbol])
    if error:
        print(f"FAIL  {error}")
        print_call_report()
        return 1

    quote = data.get(symbol) or data.get(symbol.upper())
    if not quote:
        print(f"FAIL  no row for {symbol} in {sorted(data)}")
        print_call_report()
        return 1

    eth_volume = quote.get("ethVolume")
    eth_time_ms = quote.get("ethTime")
    eth_time_et = ettime.from_epoch_ms(eth_time_ms)

    print(f"  symbol                     {quote.get('symbol', symbol)}")
    print(f"  ethVolume                  {eth_volume}")
    print(f"  ethTime                    {eth_time_ms}")
    print(f"  ethTime as ET              {ettime.stamp(eth_time_et) if eth_time_et else 'null'}")
    print(f"  lastTradePrice             {quote.get('lastTradePrice')}")
    print(f"  previousClosePrice         {quote.get('previousClosePrice')}")
    print(f"  marketCap                  {quote.get('marketCap')}")
    print(f"  sharesFloat                {quote.get('sharesFloat')}")
    print(f"  averageVolume              {quote.get('averageVolume')}")
    print(f"  twoHundredDayAveragePrice  {quote.get('twoHundredDayAveragePrice')}")
    print(f"  fields returned            {len(quote)}")

    missing = [
        field
        for field in (
            "ethVolume",
            "ethTime",
            "marketCap",
            "sharesFloat",
            "averageVolume",
            "twoHundredDayAveragePrice",
            "previousClosePrice",
        )
        if field not in quote
    ]
    if missing:
        print(f"  WARNING fields absent from the payload: {', '.join(missing)}")

    print("OK")
    print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(_smoke())
