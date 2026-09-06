# What another market data vendor would have to serve

Written 2026-09-06, because the owner asked whether this project could run on a
different subscription. The answer is that the CODE is ready and the MARKET is
the problem: the seam has been there since the first checkpoint, and the list
below is what a replacement has to sell before any of it matters.

Nothing here changes hard rule 1. Exactly one provider is active in the
published path at a time, and every row still records its `truth_source`. A
second provider means swapping which one, never running both.

## The seam already exists, which is why this is cheap

Three properties, none of them added for this document:

- **One factory.** Every module in the published path calls `eodhd.client()`
  and not one of them constructs a client of its own. Fifteen call sites,
  fifteen identical lines.
- **One return shape.** Every call returns `ApiResult`, a `(data, error)` pair
  where exactly one side is set and NOTHING RAISES. No caller anywhere knows
  what a vendor failure looks like, because a vendor failure arrives as a null
  with a reason, which is hard rule 4 and is why the code survives a dead
  token without a single try block being written for it.
- **URLs are not criteria.** `EODHD_BASE_URL` and `EODHD_WS_TRADES_URL` are in
  `core/config.py`, not scattered through twenty two modules.

So a second provider is a second class with the twelve methods in
`core/provider.py`, not a refactor. `claim_the_provider_protocol_covers_what_production_calls`
holds that file to the shipped client and, more usefully, fails the moment the
published path starts calling a thirteenth endpoint this document does not
mention.

## The twelve calls, and what each one costs to lose

Ordered by what its absence does, worst first.

| Call | Feeds | Without it |
| --- | --- | --- |
| `intraday` | the volume baseline, the night's premarket backfill | RVOL has no denominator and the night cannot correct a single level. ONE MINUTE resolution is a floor, not a preference: the paper rule reads minutes in order and a five minute bar cannot say whether the trigger or the stop came first |
| `eod` | outcome fill, market snapshot, 200 day average, gap propensity | no record, no ranking, no swing screen |
| `eod_bulk_last_day` | prior closes, prior session movers, pool recall | no gap can be computed at all |
| `exchange_symbol_list` | the weekly universe | there is no population to screen and every later step refuses by design |
| `quote_delayed` | the midday sweep, universe market caps | no midday pass, and it must be BATCHED: it is called for 2,751 symbols a session |
| `news_feed` | the overnight news prior | one of four discovery priors dies. Needs SYMBOL TAGS; an untagged feed is a reading list, not a prior |
| `earnings_calendar` | the earnings prior | a second prior dies. The before-open / after-close marking is load bearing, since an after close report is the gap the next morning screens for |
| `news` | per candidate catalysts, midday explanations | every name reads "no catalyst found", and the trap test cannot run. Needs SENTIMENT, which the trap balance is computed from |
| `exchange_details` | the trading day guard's holiday list | the guard assumes open, which is its deliberate failure direction, and the machine runs on Thanksgiving |
| `live_quotes` | the collector's fallback for a silent name | thin coverage degrades quietly instead of being patched |
| `user_status` | the quota preflight | the CRITERIA [Quota] floors become unenforceable and jobs discover the limit through errors instead of standing down |
| `economic_events` | the report's rates and calendar section | ONE SECTION of one document. The only entry here whose loss is a degraded desk rather than a dead one |

`bulk_live_us` is on the client and **nothing in the published path calls it**.
It serves the last COMPLETED session, which published a wrong report on
2026-08-14, and every prior close is now fetched by naming the session instead.
A replacement does not have to offer it.

## The websocket is the real blocker

`collect/collect_premarket.py` opens a trades socket directly against
`config.EODHD_WS_TRADES_URL`. It is not a client method and it is not in the
protocol, because folding the hardest thing to replace into a list of twelve
would understate it.

**Without a premarket trades feed this project has no premarket tape**, and
therefore no `pm_high`, `pm_low`, `pm_vwap`, `pm_rvol`, no `entry_ref`, no
`stop_ref`, no gap spine and no deck. The screens are drawings of that tape.

What a replacement has to do:

- carry **US equity trades before 09:30 ET**, live, on the session in progress
- accept **subscribe and unsubscribe on a live connection**, because the two
  phase collector hands over from the 03:55 pool to the 07:15 one at 07:20
  without dropping the names on both
- carry at least **50 concurrent symbols**. That number is CRITERIA
  `[Collector] max_subscriptions` and everything above it, the candidate cap of
  45 and the five context tickers, is arithmetic on it
- deliver a **price, a size and a timestamp** per trade

This is where most vendors fail at a hobby price, and it is exactly why Alpaca
is confined to the night: its free plan serves the SIP feed for a session that
is OVER and returns 403 for one that is running, measured across all 46
requests of the August probe and re-checked 2026-09-06. See `ALPACA_PROBE.md`.

## The credit model is not portable, it is rewritable

`preflight`, `require_quota`, `cost_table` and `credit_cost` are denominated in
EODHD credits, priced per endpoint in CRITERIA `[Quota costs]`, and read a
counter shaped like EODHD's `/user`. A vendor metering by request count, by
symbol month, or not at all does not need these translated. It needs them
rewritten, and `[Quota costs]` repriced against whatever it actually bills.

That is a real cost and it is smaller than it looks, because the thing those
functions protect is one behaviour: jobs that spend before the open must stand
down on a budget they READ rather than discover through errors. Any vendor with
a readable usage figure can support that. A vendor with none means the
preflight is deleted and the morning finds its ceiling the hard way.

## So what would a swap actually take

Assuming a vendor that serves all twelve calls and a conforming websocket:

1. A `SomeVendorClient` with the twelve methods, returning `ApiResult` and
   never raising. This is the bulk of the work and it is mechanical.
2. A socket client with the four properties above, and the handover behaviour
   the two phase collector needs.
3. `[Quota costs]` repriced, or the preflight removed with that recorded as a
   decision rather than an omission.
4. `config` gaining the new URLs, and `eodhd.client()` becoming a factory that
   returns the configured provider. One function.
5. Every threshold in CRITERIA re-examined, because several were measured
   against EODHD's data and not against the market: `premarket_capture_rate` is
   the share of the consolidated tape THIS SOCKET carries, and it means nothing
   about another one.

Item 5 is the one that gets forgotten. The code would run on day one and the
numbers would be wrong until the measurements behind them were retaken.

## What is deliberately not built

**No second implementation, and no adapter layer.** `core/provider.py` adds no
indirection and nothing imports it at runtime. Building an abstraction for a
vendor nobody has chosen would mean carrying an interface shaped by guesses
about an API that has not been read, plus a second code path the suite cannot
exercise. The seam is written down and checked; the implementation waits for a
real vendor, and the first thing to do when one is proposed is read its API
against the table above.
