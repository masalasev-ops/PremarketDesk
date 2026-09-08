"""The market data seam: what a vendor has to serve for this project to run.

WHY THIS FILE EXISTS AND WHAT IT IS NOT. It is not an abstraction layer and it
adds no indirection: nothing imports it at runtime and no call passes through
it. It is a written statement of the interface `core/eodhd.EodhdClient`
already satisfies, so that "could this run on another vendor" has an answer
that is checked rather than argued about. Hard rule 1 is untouched: exactly one
provider is active in the published path at a time, and every row still records
its `truth_source`.

THE SEAM WAS ALREADY THERE, which is the only reason this is cheap. Every
module in the published path obtains its client from one factory,
`eodhd.client()`, and not one of them constructs a client of its own. Every
call returns the same `(data, error)` pair, so no caller raises on a vendor
failure or knows what a vendor failure looks like. The vendor's URLs live in
`core/config.py` because a URL is not a criterion. A second provider is
therefore a second class with these twelve methods, not a refactor of the
twenty two modules that call them.

WHAT IS DELIBERATELY NOT IN HERE, and each omission is the interesting part.

  THE WEBSOCKET. `collect/collect_premarket.py` opens a trades socket directly
  against `config.EODHD_WS_TRADES_URL` and it is not a client method, so this
  protocol cannot describe it. That is not an oversight to tidy up: the socket
  is the single hardest thing to replace and it deserves to be conspicuous
  rather than folded into a list of twelve. Without a premarket trades feed
  there is no premarket tape, and without that tape there is no pm_high,
  pm_low, pm_vwap, pm_rvol, no entry_ref, no stop_ref and no gap spine. Every
  screen this project draws rests on it. doc/PROVIDERS.md carries what a
  replacement has to do.

  THE CREDIT MODEL. `preflight`, `require_quota`, `cost_table` and
  `credit_cost` are denominated in EODHD credits, priced per endpoint in
  CRITERIA [Quota costs], and read a counter shaped like EODHD's `/user`. A
  vendor that meters differently, by request count or by symbol month or not
  at all, needs those rewritten rather than reimplemented. Only the meter READ
  is in this protocol, as `user_status`, because that is the one call the
  preflight makes.

  bulk_live_us. It exists on the client and NOTHING in the published path
  calls it. It serves the last COMPLETED session, which published a wrong
  report on 2026-08-14, and every prior close is fetched by naming the session
  instead. A second provider does not have to offer it, and a reader deciding
  what to implement should not be misled into thinking it does.

HOW THIS STAYS TRUE. tests/test_regressions.py checks two things, and the
second is the one that matters. First, that `EodhdClient` still satisfies
every method here with a matching signature. Second, that the published path
calls NO client method this protocol omits, so the moment production starts
using a thirteenth endpoint, this file has to gain it or the suite fails. A
protocol nobody checks is a comment.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    """Every vendor call the published path makes.

    Each returns the project's `(data, error)` pair: exactly one of the two is
    set, an error is a human readable string with secrets already scrubbed,
    and NOTHING RAISES. A provider that raises on a bad response breaks the
    contract every caller in this project is written against, because missing
    evidence here has to arrive as a null with a reason rather than as an
    exception that ends a morning.
    """

    # ---- the universe -------------------------------------------------
    def exchange_symbol_list(self, exchange: str) -> Any:
        """Every tradeable symbol on an exchange, with type and name.

        Feeds the Sunday universe rebuild. Without it there is no population
        to screen and every later step refuses.
        """

    def exchange_details(self, exchange: str) -> Any:
        """Exchange metadata carrying the official holiday list.

        Feeds ops/market_today.py, the trading day guard every weekday job
        runs first. Without it the guard assumes the market is open, which is
        its deliberate failure direction.
        """

    # ---- prices -------------------------------------------------------
    def eod(self, symbol: str, start: dt.date | None = None,
            end: dt.date | None = None, period: str = "d") -> Any:
        """Daily bars for one symbol.

        Feeds the outcome fill, the market snapshot, the 200 day average and
        the gap propensity sweep. The most load bearing single endpoint here.
        """

    def eod_bulk_last_day(self, exchange: str = "US", day: dt.date | None = None,
                          symbols: Iterable[str] | None = None,
                          extended: bool = False) -> Any:
        """Every symbol's bar for ONE NAMED SESSION.

        Naming the session is the whole point and is not optional: the vendor
        field that means "previous close" was measured on 2026-08-31 to be the
        prior session for about a third of names and TODAY'S close for another
        third, with a correct date beside it either way. A provider that
        cannot be asked for a specific session by date cannot supply a prior
        close this project will publish.
        """

    def quote_delayed(self, symbols: Iterable[str]) -> Any:
        """Batched delayed quotes, the midday sweep's whole instrument.

        Called for the entire universe once a session, so a provider whose
        equivalent is per symbol and unbatched turns one job into 2,751 calls.
        """

    def fundamentals(self, symbol: str) -> Any:
        """One symbol's fundamentals record, the universe's SECOND cap source.

        Called only by the weekly rebuild, and only for names quote_delayed
        answered with a null market cap, which is the hyphenated share classes
        and the ADRs: eighteen of 2,928 on the 2026-09-06 build. A provider
        with no per symbol fundamentals record can still serve this project.
        The backfill then recovers nothing and those names stay out of the
        universe, which is exactly where they were before it existed.
        """

    def live_quotes(self, symbols: Iterable[str]) -> Any:
        """Batched live quotes. The collector's fallback when the socket is
        silent for a name."""

    def intraday(self, symbol: str, start: dt.datetime, end: dt.datetime,
                 interval: str = "1m") -> Any:
        """ONE MINUTE bars over an explicit instant range.

        Feeds the volume baseline and the night's premarket backfill. One
        minute is the floor: the paper rule reads its minutes in order and a
        five minute bar cannot say whether a trigger or a stop came first.
        """

    # ---- what moved things -------------------------------------------
    def news(self, symbol: str, start: dt.date | None = None,
             end: dt.date | None = None, limit: int | None = None,
             offset: int = 0) -> Any:
        """Stories for ONE symbol, with sentiment.

        Feeds the catalyst on a candidate and the midday explanation. The
        sentiment is used, so a headline only feed is not a substitute.
        """

    def news_feed(self, start: dt.date, end: dt.date, limit: int = 1000,
                  offset: int = 0) -> Any:
        """Every tagged story across the market in a window.

        Feeds the overnight news prior, one of the four discovery priors. The
        SYMBOL TAGS are what make it a prior rather than a reading list.
        """

    def earnings_calendar(self, start: dt.date, end: dt.date,
                          symbols: Iterable[str] | None = None) -> Any:
        """Who reports, and whether before the open or after the close.

        Feeds the earnings prior. The before/after marking is load bearing:
        an after close report is the gap the next morning screens for.
        """

    def economic_events(self, country: str, start: dt.date, end: dt.date,
                        limit: int = 1000) -> Any:
        """Macro releases with an importance ranking.

        Feeds the report's economic section only. THE ONLY ENDPOINT HERE
        WHOSE LOSS COSTS A SECTION RATHER THAN A MORNING, so a provider
        missing it is a degraded desk and not a dead one.
        """

    # ---- the account --------------------------------------------------
    def user_status(self) -> Any:
        """The account's own usage counter.

        The single call the quota preflight makes, so that jobs spending
        before the open stand down on a budget they read rather than discover
        through errors. A provider with no readable counter means the
        preflight cannot exist and the CRITERIA [Quota] floors become
        unenforceable.
        """
