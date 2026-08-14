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

## Quota

The EODHD key is shared across projects and the daily counter is account
wide, so the quota remaining to this project is not a function of its own
usage and cannot be inferred from the client side call ledger. discover.py
and scan.py read /api/user once on entry, before spending anything, and act
on what the meter actually says rather than discovering the limit through
429s. The counter resets at midnight UTC, which is 20:00 ET in daylight time
and 19:00 in standard time, so one ET weekday spans two quota days: the
morning jobs bill to the quota day that opened the previous evening, and the
22:15 nightly bills to the next one.

Below the degrade threshold the job proceeds only with the calls it cannot
skip and writes the reading into gaps_to_fill. Below the refuse floor it
does not run at all: with almost nothing left, every call is a likely 429
and the retry backoff would burn minutes learning what one meter read
already said. 5000 covers roughly two full mornings of headroom; 500 is
less than one degraded scan can need. The baseline warm that follows
discover in the same scheduled job reads its own preflight and stands down
on a degraded meter, because the warm is skippable spend and the scan
records null RVOL with the reason when the cache is cold.

The redesign line is the measured cost of one bulk live call at which the
two bulk calls a day would dominate the shared account and force a design
change. measure_bulk_cost.py judges its verdict against this number; the
measured fact on 2026-08-13 was a flat 100 per call.

The circuit breaker bounds the grind when the meter is unreadable and the
quota is also genuinely gone. Without it, every call discovers the limit
independently: four attempts with backoff each, which across a morning's
worth of calls plus the analyst timeout can push the chain past the open.
Consecutive 429s open the circuit; every later call in the run fails fast
with the reason recorded, and the packet completes thin instead of late.
The retry budget is the total number of retry attempts one run may spend
across all its calls before every remaining call gets a single attempt.

degrade_below_remaining       = 5000       # skip skippable calls below this, record why
refuse_below_remaining        = 500        # refuse to run outright below this
bulk_redesign_line            = 1000       # one bulk live call at or above this forces a redesign
consecutive_429_trip          = 5          # this many 429s in a row opens the circuit for the run
retry_budget_per_run          = 10         # total retries one run may spend across all calls

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

The 07:15 pass that builds the candidate pool and writes watchlist.json.

It used to rank the whole universe by gap off one bulk /real-time call and keep
the top 30. That feed serves the last completed session, so the ranking was of
yesterday's movers, and since the collector only ever subscribes to what this
pass chose, the error propagated into every morning downstream of it. Nothing
here reads a price from today any more, because at 07:15 no source on this plan
has one for the whole universe. See the pool note below and DECISIONS.md.

price                         = > 3        # matches the day setup price floor
gap_pct                       = > 3        # matches the day setup gap floor
run_time                      = 07:15
max_quote_age_hours           = 96         # see the ghost row note below
max_subscribed_candidates     = 42         # seed: the collector's 50 subscription cap less the 8 context tickers
prior_session_move_pct        = 5          # seed, not validated: absolute close to close percent that makes a name a continuation candidate
prior_session_dollar_multiple = 3          # seed, not validated: prior session dollar volume this many times its 20 day average counts as unusual
recent_runner_lookback        = 10         # seed, not validated: sessions of picks history a recent runner can come from
recent_runner_decay           = 0.85       # seed, not validated: per session weight decay, so 3 days ago outranks 3 weeks ago
news_window_start             = 16:00      # prior day ET, the close after which overnight news starts counting
news_fresh_hours              = 6          # seed: news newer than this is tier 2, older but inside the window is tier 3
news_sweep_page_size          = 1000       # rows per news call
news_sweep_max_pages          = 5          # hard bound on the sweep, truncation is recorded rather than silent

### The pool note

Selection is now a prior assembled from information that exists before the
open, not a reading of today's tape. Four sources, unioned, deduplicated, and
intersected with universe.json:

  earnings before open today, from the calendar API
  overnight news, from a symbol-less news sweep over the window above
  prior session movers, from two bulk end of day calls
  recent runners, from the picks table

Every name records which sources put it there. A source that fails is recorded
as not-fetched and a source that succeeds with nothing is recorded as
fetched-and-empty, the same distinction catalyst_why already draws, so a pool
missing its earnings names is never mistaken for a morning with no earnings.

Cost: two bulk end of day calls at a measured 98 counted calls each, plus one
calendar call and up to five news calls, against the one bulk live call at 100
that this replaces. Roughly 100 counted calls a morning more than before, far
below the bulk_redesign_line in the Quota section.

## Pool tiers

The order the pool is ranked in, best tier first, with 20 day average dollar
volume descending as the tiebreak inside a tier. A name qualifying under
several sources takes its best tier and records all of them.

This ordering is a seed. It is an assumption about which priors most often
precede a premarket gap, not a measured base rate. pool_recall.json in the
nightly pass is what will eventually replace the assumption with a measurement.

tier = earnings_before_open : 1
tier = news_fresh : 2
tier = news_stale : 3
tier = prior_session_mover : 4
tier = recent_runner : 5

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
min_baseline_premarket_volume = 1000       # shares; below this the denominator is degenerate and pm_rvol is null

### The denominator floor note

A seed value, chosen to exclude degenerate denominators, not a validated
threshold. Nothing has been measured against it yet.

It exists because a baseline median can be small enough that the ratio built
on it stops meaning anything. On 2026-08-14 ARX had a median premarket volume
of 23.5 shares and MH had 10, so any ordinary morning divided by them produces
a number in the thousands, which then maxes the RVOL scoring band by
construction rather than by evidence. Six of that morning's twelve candidates
sat below this floor.

The fix is a floor on the denominator, not a cap on the ratio. A cap would
turn 882,728 into a plausible looking number and hide the fact that the
denominator was never usable, which is the same class of error as substituting
a stale price: it replaces a visible absurdity with an invisible one. Below
the floor, pm_rvol is null with the reason recorded, the RVOL score component
is unavailable, and the total score is null rather than partial credit.

## Backfill

The nightly job that writes the true premarket window into picks, from EODHD
one minute intraday bars, which are published a few hours behind live. The
premarket window opens at the baseline session start and closes at market
open. The gap report compares the morning's live collector high against the
true high over recent sessions, which is the standing measurement of how much
premarket the 07:20 collector start actually misses.

market_open                   = 09:30
run_after                     = 22:00      # ET, the day's intraday is usually complete by then
gap_report_sessions           = 20
catchup_days                  = 5          # prior days with unfilled true columns retried each night, because the vendor sometimes publishes later than run_after

## Outcomes

The nightly outcome fill for picks old enough to have them. Horizons are
trading sessions counted on the session calendar symbol's end of day history,
never weekday arithmetic, because holidays are not sessions.

The excursion definitions, for the record: favourable excursion is how far
the next session's high ran past entry_ref, as a percent of entry_ref.
Adverse excursion is how far the next session's low undercut stop_ref, as a
percent of stop_ref, so a negative adverse excursion means the stop reference
was breached by that much. Both are measurements of what happened near the
reference levels, not a simulation of any trade.

horizon_sessions_short        = 1
horizon_sessions_long         = 5

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

## Analyst

The narrative pass. The claude CLI is invoked as a subprocess and
authenticates through the logged in subscription, never an API key. The model
narrates numbers already decided in Python, so these are operational knobs
like the Api section above, not screen criteria.

model                         = opus       # owner's standing choice, re-asserted 2026-08-13 evening
effort                        = medium     # compared against low on the 2026-08-13 packet (2026-08-14): medium covered all 12 candidates individually in Technical signals where low compressed six into one vague sentence, and its traps section gave actionable per-name instructions; ~25s slower, worth it. Default (high) effort remains measured at ~340s, not affordable.
timeout_s                     = 293        # 3x the slowest of five measured opus medium runs on 2026-08-14: 97.4, 86.5, 97.7, 91.1, 92.4 seconds
max_attempts                  = 2          # total tries, including the first
prose_token_stopwords         = ET, EST, EDT, UTC, GMT, AM, PM, US, USA, Q1, Q2, Q3, Q4, YOY, QOQ, EPS, ARR, GAAP, IPO, CEO, CFO, COO, CTO, FDA, SEC, FOMC, GDP, CPI, PPI, PCE, ISM, ADP, ETF, NYSE, USD, EUR, RVOL, VWAP, OHLCV, NOT, AND, THE, ALL, ON, SO, IT, AI

### The prose stopword note

Containment reads ticker claims out of the report's prose as well as its
tables. Prose is ambiguous in a way a Ticker column is not: "06:37 ET" is a
time, and ET is also Energy Transfer, so a naive reader of prose would fail
every report ever written. Time expressions and ISO dates are stripped before
tokens are taken, and this list removes what survives.

Some entries here are real tickers, ALL, ON, SO, IT, AI and ET among them.
That is a deliberate, recorded fail-open: a claim about one of those names in
prose alone will not be caught. The alternative is a guard that cries wolf
every morning, and a guard that always fires is a guard nobody reads. Claims
in the watchlist tables are unaffected, and those tables are now mandatory
even when empty.

Note on the invocation: the narrative pass is one text generation, not an
agent loop. The CLI runs with --tools "" so there is nothing to loop on, a
one line --system-prompt so the piped document is the entire instruction,
and everything (prompt, template, packet) piped on stdin. num_turns is
recorded in analyst_usage.json and must be 1. The report is produced either
way: on any analyst failure, timeout included, analyst.py renders the plain
table fallback straight from packet.json and the chain carries on to email.

## Calendar

The is it a trading day guard. Every weekday job runs market_today.py first
and exits cleanly when the market is closed, because a full pipeline run on
Thanksgiving would build a watchlist from stale quotes, collect zero trades,
and email a report about a session that does not exist. The holiday list is
the EODHD exchange-details endpoint, cached to data/exchange-details.json and
refreshed when the cache is older than refresh_after_days. On any fetch error
with no usable cache the guard assumes the market is OPEN: a false closed
silently loses a real morning, a false open produces one honestly thin
report.

exchange                      = US
refresh_after_days            = 7

## Monitor

The watchdog. It runs a few times each weekday, asks Task Scheduler whether
each PremarketDesk job fired and what it returned, reads the job's own dated
log for the final step marker, and reruns what is safe to rerun. Safe means
idempotent: the morning chain and the nightly can always be rerun, the
collector may only be restarted when no collector is alive (two live
collectors would write duplicate minutes), discover is only rerun before the
collector window opens (a later rewrite would desync the watchlist from what
the collector actually subscribed to), and the universe is rebuilt on a
weekday only when the Sunday build was missed. Each job gets at most
max_reruns_per_job_per_day so a hard failure cannot loop.

discover_due                  = 07:25      # discover plus baseline warm should be done by here
chain_due                     = 09:00      # the 08:45 chain worst case ends about 08:53
nightly_due                   = 22:45      # the 22:15 nightly is minutes long
rerun_chain_until             = 09:30      # after the open a premarket report is history, report only
collector_stale_after_s       = 180        # no bar file write for this long inside the window means dead
universe_rerun_after_days     = 8          # a fresh weekly build is 7 days old at most
max_reruns_per_job_per_day    = 1

## Archive

The single file report archive at site/PremarketDesk.html, rebuilt from
runs/ at the end of every morning chain and every nightly run. Always a full
rebuild, never an append, so it is idempotent by construction. The newest
sessions are inlined in full; older ones stay in the rail but link out to
their own runs/<date>/report.html so the file stays small and nothing is
ever dropped.

embed_sessions                = 120

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

## Picks

The picks table row written for every candidate after each scan. entry_ref
and stop_ref are references for outcome measurement in later nightly jobs,
never advice. The entry reference is the premarket high, the natural breakout
trigger level for a gap candidate. The stop reference is the premarket low
rather than the VWAP: the low is a level that actually traded, an extreme of
the observed premarket path, where a VWAP is an average that one large print
can drag. Excursion math against a traded extreme stays interpretable.

entry_ref_field               = pm_high
stop_ref_field                = pm_low

Every picks row carries a source: 'live' for rows written by the scheduled
morning inside the window below, 'test' for rows from manual or off clock
runs, and 'reconstructed' reserved for any future row rebuilt after the
fact. The writer decides at write time: the --test flag forces 'test', and
so does a run clock outside the window, because a packet gathered at noon
describes a different market than the one the report is about. Every query
and every screen filters to source = 'live' and says so in its header when
it does not; test rows must never leak into outcome or calibration math.
The migration on 2026-08-14 marked every earlier row 'test', which every
one of them was.

live_window_start             = 07:00      # rows written inside this ET window are source live
live_window_end               = 09:30

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

A null score is unscored, not low. It means at least one component input was
never observed (the unavailable components are listed next to the partial
total in the packet and the row), and the conviction bucket is null,
rendered as unscored. Calibration and threshold queries must exclude
unscored rows, never fold them into red.

band = >= 7 : green
band = >= 4 : yellow
band = else : red
