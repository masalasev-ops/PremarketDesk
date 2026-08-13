# CRITERIA

## Read this before you trust a single number below

These seed values come from a third-party article. They have not been
validated on my own data, on my own fills, or on any sample I collected
myself. They are a starting point for gathering evidence, not an edge. Treat
every number here as a hypothesis with no track record behind it.

Once picks(...) has a few hundred filled outcome rows, come back and move
these numbers because the data said so, not because the article did.

Nothing in this file is advice and nothing in this file has been backtested.

## How this file is read

Every screen threshold in PremarketDesk lives here and nowhere else. No Python
file in this project is allowed to contain a threshold literal. criteria.py
parses this file, and `python criteria.py` prints everything it found.

Syntax, kept deliberately small:

    ## Section name          starts a section
    key = value              one parameter
    # anything               a comment, whole line or trailing
    blank lines              ignored

Value shapes:

    > 3          a rule, exclusive greater than
    >= 8         a rule, inclusive greater than
    1B           a number, suffix B for billion, M for million, K for thousand
    1.5          a number
    true / false a flag
    07:20        a clock time, always US Eastern
    A, B, C      a list
    > 3 : 2      a band, "when the test passes award the value after the colon"
    else : 0     the fallback band, always last in its section

Repeated keys inside one section keep their order, which is what makes the
banded scoring blocks readable. First matching band wins.

## Api

Operational knobs for the EODHD client. Endpoint addresses live in config.py
because a URL is not a criterion. Everything here is a number you may want to
turn on a bad network day.

max_attempts                  = 4          # total tries per call, including the first
retry_backoff_start_s         = 2
retry_backoff_max_s           = 30
timeout_s                     = 30         # per request, normal endpoints
bulk_timeout_s                = 180        # the bulk feed returns every US ticker
quote_batch_size              = 20         # symbols per us-quote-delayed call
news_limit                    = 50

## Day setup

Applies to the intraday gap and go screen. A candidate is day_eligible only
when every line here passes.

gap_pct                       = > 3        # absolute gap versus prior close, percent
price                         = > 3        # dollars, latest premarket print
market_cap                    = > 1B
premarket_rvol                = > 1.5      # ethVolume divided by the cached baseline median
require_above_prior_high      = true       # latest premarket print above prior regular session high

## Swing setup

Its own block on purpose. A swing candidate is a different animal from a day
candidate and the two screens must be allowed to drift apart.

Note on the two "open" conditions: the scan runs at 08:45 ET, before there is
an opening print. The latest premarket price is used as the proxy for the open
and the report says so. Do not read these as confirmed opening range facts.

gap_pct                       = >= 8       # absolute gap versus prior close, percent
price                         = > 3        # dollars, latest premarket print
market_cap                    = >= 800M
require_open_above_prior_high = true       # premarket price above prior regular session high
require_open_above_200sma     = true       # premarket price above twoHundredDayAveragePrice
require_catalyst              = true       # catalyst_found must be true

## Universe

The weekly discovery population written by universe.py. The market cap floor
here is deliberately below the day setup floor above. A name that gaps hard
crosses the day line during the gap, so it has to already be in the population
the night before or the morning pass can never see it.

price                         = >= 3
avg_dollar_volume_20d         = >= 5M
market_cap                    = >= 500M
min_sessions                  = 20         # sessions of history required to admit a symbol
lookback_sessions             = 20         # sessions pulled to compute the averages
allowed_security_type         = Common Stock
exchanges                     = NYSE, NASDAQ
session_calendar_symbol       = SPY.US   # its EOD history supplies the real session dates
expected_count_min            = 1000       # a smaller result means the build went wrong
expected_count_max            = 3000       # a larger result means the type filter went wrong
max_age_days                  = 10         # every later script refuses to run past this

## Discovery

The 07:15 pass that writes watchlist.json off one bulk call.

price                         = > 3        # matches the day setup price floor
gap_pct                       = > 3        # matches the day setup gap floor
watchlist_size                = 30         # top N by absolute gap
run_time                      = 07:15
max_quote_age_hours           = 96         # see the ghost row note below

### The ghost row note

The bulk live feed returns some tickers twice. One row is current, the other is
a frozen snapshot from an old session that never aged out. On 2026-08-13 it
carried AZN twice: the live row was 157.90 against a 158.50 prior close, a
quiet -0.4 percent, and the ghost row was 188.41 against a 92.77 prior close, a
fabricated +103 percent that sorted straight to the top of the watchlist. The
ADT ghost was timestamped February 2023.

So the feed is deduplicated by taking the newest timestamp per ticker, and any
row older than max_quote_age_hours is dropped outright. A long weekend with a
holiday Monday is about 87 hours from Friday's close to Tuesday's premarket,
which is what 96 leaves room for. Every run reports how many rows it dropped.
Watch that number. If it moves a lot, the feed changed.

## Collector

The 07:20 to 09:25 websocket run that is the only source of today's premarket
price path.

start_time                    = 07:20
stop_time                     = 09:25
context_symbols               = SPY, QQQ, IWM, DIA, TLT, USO, UUP, VIXY
max_subscriptions             = 50         # hard cap, lowest absolute gap dropped first
bar_seconds                   = 60
reconnect_backoff_start_s     = 1
reconnect_backoff_max_s       = 60
poll_interval_s               = 60         # only used by the --poll fallback
auth_wait_s                   = 10         # see the handshake note below
late_trade_grace_s            = 45         # see the late trade note below
verify_warmup_minutes         = 25         # see the verification note below
verify_window_minutes         = 15

### The handshake note

The trades socket sends {"status_code":200,"message":"Authorized"} a moment
after it opens. A subscribe frame sent before that arrives is answered with
{"status":500,"message":"Server error"} and the connection is dropped. The
first build of the collector did exactly that and ran a clean looking fifteen
minutes on thirty eight liquid symbols, including SPY at midday, and folded
zero trades. So the collector now waits for the authorization frame, and fails
loudly if it never comes, rather than sitting on a socket that will never
deliver anything.

### The late trade note

Trades do not arrive in timestamp order. A trade stamped 12:10:59 can land at
12:11:07. The first build closed a minute the instant the clock passed it, so
every late print was thrown away: a fifteen minute run folded 88,632 trades and
discarded 11,144 of them, which is twelve percent of the volume, silently.

So a minute is not written until late_trade_grace_s has passed since it ended.
Anything that still arrives after its minute is on disk cannot be merged in,
because rows are append only and are never revised, which is what makes a
restart safe. Those stragglers are counted and reported as late_trades and
late_volume instead. Watch those numbers. If late_volume is a material share of
the total, raise the grace period.

### The verification note

Two references were tried and one of them is unsound.

Live v1 polling was measured twice against the websocket, with per symbol
windows taken from the feed's own timestamps and a warmup covering its fifteen
to sixteen minute delay. It disagreed with the trade stream by orders of
magnitude in both directions on the most liquid ETFs in the market: IWM +804
percent, DIA +1113 percent, small caps -50 to -90 percent. Whatever Live v1's
cumulative volume field measures over a short window, it is not the
consolidated tape that the websocket delivers, so a within one percent test
against it is a test against a broken ruler. The --verify mode still prints
this comparison, labelled as directional only.

The sound reference is EODHD's own one minute intraday bars, which cover
04:00 to 20:00 ET and match the collector minute for minute. They are
published with a lag of a few hours, so the definitive check runs in the
evening: --verify-intraday compares every collected minute against the
intraday bar for that exact minute, and the nightly backfill runs the same
comparison for the record. Same window, same units, per minute.

## Baseline

The cached premarket volume baseline. Never fetched during the morning run.

lookback_sessions             = 20         # prior sessions summed per cutoff
session_start                 = 04:00      # premarket volume accumulates from here
refresh_after_days            = 7
min_sessions_for_rvol         = 10         # below this pm_rvol is null with a recorded reason

## Scan

The 08:45 gathering pass that writes packet.json.

candidate_count               = 12         # top N by absolute gap, recomputed on a fresh bulk call
news_lookback_hours           = 24
news_keep                     = 3
economic_country              = US
economic_importance           = high
economic_days_ahead           = 1          # today plus this many days
earnings_days_ahead           = 1
run_time                      = 08:45
rvol_cutoff_snap_minutes      = 10         # see the cutoff snap note below

### The cutoff snap note

The RVOL denominator is the cached baseline median for a clock cutoff, and the
cache is warmed for run_time. The scan stamps its cutoff from the wall clock,
so a scheduler that fires at 08:46 instead of 08:45 would miss the cache on an
exact match and null out every RVOL over sixty seconds of jitter. So when the
wall clock is within rvol_cutoff_snap_minutes of run_time, the scan uses the
run_time cutoff. The numerator, ethVolume, is still read at the actual scan
moment, so a snapped run compares up to that many extra minutes of volume
against the run_time baseline. That skew is bounded and recorded: the packet
carries both run_time_et and rvol_cutoff_hhmm, and they differ when snapped.
Outside the snap window nothing is snapped, which is why an off hours test run
honestly reports no cached baseline.

## Scan snapshot

The market snapshot line, as report label to EODHD symbol. Order is preserved.

Resolution is tried live first, then end of day. Indices, government bonds and
the dollar index return NA on the live endpoint but are current in the end of
day feed, so both paths are needed and the packet records which one answered.

snapshot = SPY : SPY.US
snapshot = QQQ : QQQ.US
snapshot = IWM : IWM.US
snapshot = DIA : DIA.US
snapshot = VIX : VIX.INDX
snapshot = 10Y : US10Y.GBOND
snapshot = 3M : US3M.GBOND
snapshot = WTI : USO.US
snapshot = DXY : DXY.INDX

EODHD commodity symbols are not on this plan. CL.COMM, WTI.COMM, CL1.COMM,
BRENT.COMM and OIL.COMM all return 404 on both the live and the end of day
endpoints. USO is an oil ETF standing in for WTI and it is labelled as a proxy
everywhere it appears, including in the report.

proxy = WTI : USO is an oil ETF standing in for WTI, EODHD commodities are not on this plan

## Economic importance

EODHD economic events carry no importance field. The response has type,
country, date, actual, estimate, previous and change, and nothing else. So high
importance is a list you own, matched case insensitively against the event
type. Anything not matched is dropped from the report rather than shown at an
importance we invented for it.

This is substring matching, and it is the only option here because there is no
structured field. It is not the same thing as the ban on keyword matching for
news catalysts, which exists because news carries a proper symbol tag that
should be used instead.

high = Fed Interest Rate Decision
high = FOMC
high = Fed Press Conference
high = Fed Chair
high = Inflation Rate
high = Core Inflation Rate
high = CPI
high = PPI
high = Producer Prices
high = Non Farm Payrolls
high = Unemployment Rate
high = Average Hourly Earnings
high = GDP Growth Rate
high = Retail Sales
high = ISM Manufacturing PMI
high = ISM Services PMI
high = Initial Jobless Claims
high = PCE Price Index
high = Core PCE Price Index
high = Consumer Confidence
high = Michigan Consumer Sentiment
high = Durable Goods Orders
high = Building Permits
high = Existing Home Sales

## Score catalyst class

Points awarded for the strongest catalyst class found on a name. Classes are
assigned from EODHD structured news tags and the earnings calendar, never from
regex over a headline.

class = earnings : 3
class = guidance : 3
class = m_and_a : 3
class = fda : 3
class = index_inclusion : 2
class = analyst_action : 2
class = sympathy : 1
class = none : 0

## Score catalyst tags

Maps an EODHD news tag, lowercased, onto one of the classes above. Add lines
here as you see which tags actually turn up in the feed. A tag that is not
listed contributes nothing, and a name whose only news carries unlisted tags
still counts as catalyst_found true with class none.

tag = earnings : earnings
tag = earnings report : earnings
tag = earnings call : earnings
tag = quarterly results : earnings
tag = guidance : guidance
tag = outlook : guidance
tag = forecast : guidance
tag = mergers and acquisitions : m_and_a
tag = m&a : m_and_a
tag = acquisition : m_and_a
tag = merger : m_and_a
tag = takeover : m_and_a
tag = buyout : m_and_a
tag = fda : fda
tag = clinical trials : fda
tag = drug approval : fda
tag = health : fda
tag = index inclusion : index_inclusion
tag = indices : index_inclusion
tag = s&p 500 : index_inclusion
tag = analyst ratings : analyst_action
tag = price target : analyst_action
tag = upgrade : analyst_action
tag = downgrade : analyst_action
tag = initiated coverage : analyst_action

## Score premarket rvol

band = > 3 : 2
band = >= 1.5 : 1
band = else : 0

## Score gap

Tested against the absolute gap percent.

band = > 8 : 2
band = >= 4 : 1
band = else : 0

## Score booleans

Flat points added when the named condition is true. Missing data scores zero,
it never scores a point by default.

above_prior_high              = 1
above_premarket_vwap          = 1
market_cap_above              = >= 2B     # the test
market_cap_above_points       = 1         # the points it is worth

## Score buckets

Ordered. First match wins. The total runs 0 to 10.

band = >= 7 : green
band = >= 4 : yellow
band = else : red
