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

The redesign line is the cost of one bulk call at which the day's bulk calls
would dominate the shared account and force a design change. Nothing in the
pipeline calls the bulk live endpoint any more, so the day's bulk calls are all
end of day: two at 07:15 for discover's prior session movers source, and two at
22:15 for the nightly pool recall, at a measured 98 counted calls each, about
392 a day against a shared 100,000. The weekly universe rebuild buys
lookback_sessions more of the same call in one Sunday run.
measure_bulk_cost.py still judges its verdict against this number using the
bulk live endpoint, because that is the call whose price would force the
redesign if selection ever needed it back; the measured fact on 2026-08-13 was
a flat 100 per call.

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

## Price age

How old the last collector print behind a published price may be, measured
against the scan clock rather than against the premarket window.

The vintage check answers a different question. It asks whether a price is
from today's premarket session, which a print from 07:22 satisfies perfectly
while being 83 minutes stale at 08:45. A collector interrupted at 08:10 leaves
exactly that: prints inside today's window, correctly dated, and describing a
market that has moved on. The gap computed from one is not this morning's gap,
and nothing in the packet said so.

max_price_age_seconds         = 900        # SEED, not measured. Fifteen minutes,
                                           # chosen because it is short enough that
                                           # a gap is still recognisably the same
                                           # gap and long enough that a thinly
                                           # traded name with sparse prints is not
                                           # dropped for being quiet. No measurement
                                           # supports it yet. Widen it if real
                                           # mornings show liquid names being cut.

## Day setup

Applies to the intraday gap and go screen. A candidate is day_eligible only
when every line here passes.

gap_pct                       = > 3        # absolute gap versus prior close, percent
price                         = > 3        # dollars, latest premarket print
market_cap                    = > 1B
premarket_rvol                = > 1.5      # collector premarket volume divided by the cached baseline median
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
min_count_fraction_of_previous = 0.5       # SEED, not measured. A rebuild that
                                           # admits less than this share of the
                                           # previous run's names is treated as a
                                           # partial run rather than as a market
                                           # that halved overnight, and discover
                                           # refuses it. 0.5 is a guess chosen to
                                           # sit far below any plausible real
                                           # weekly change and far above a
                                           # truncated file. Revisit once a few
                                           # real rebuilds have been observed.

## Discovery

The 07:15 pass that builds the candidate pool and writes watchlist.json.

It used to rank the whole universe by gap off one bulk /real-time call and keep
the top 30. That feed serves the last completed session, so the ranking was of
yesterday's movers, and since the collector only ever subscribes to what this
pass chose, the error propagated into every morning downstream of it. Nothing
here reads a price from today any more, because at 07:15 no source on this plan
has one for the whole universe. See the pool note below and DECISIONS.md.

price                         = > 3        # applied by the 08:45 scan, not here, matches the day setup price floor
gap_pct                       = > 3        # applied by the 08:45 scan to the measured gap, matches the day setup gap floor
run_time                      = 07:15
max_subscribed_candidates     = 42         # seed: the collector's 50 subscription cap less the 8 context tickers
within_tier_key               = gap_propensity   # MEASURED, see the ordering note below
within_tier_fallback          = atr_pct_20d      # for names propensity cannot score: it needs 100 sessions, this needs 20
min_slots_per_tier            = 4          # MEASURED, see the ordering note below
min_ranked_fraction_to_subscribe = 0.5     # SEED, not measured. Below this share
                                           # of the universe carrying a ranking
                                           # key, discover writes no watchlist and
                                           # exits non zero rather than cutting an
                                           # unranked pool to the cap. An arbitrary
                                           # 42 names looks exactly like a real 42
                                           # downstream, and a missing report is
                                           # recoverable where a plausible wrong
                                           # one is not. 0.5 is a guess; the
                                           # observed value is above 0.98.

### The ordering note

These two are not seeds. They were chosen by src/backtest_pool.py over 60
cached trading sessions, 2026-05-19 to 2026-08-13, a full quarterly earnings
cycle, with the ranking metric computed as of 2026-05-18 so every replayed
session is strictly out of sample.

Mean subscribed recall per session, gap propensity descending against the 20
day average dollar volume it replaces:

  gap propensity, 4 slots per tier   0.1164      the shipped configuration
  gap propensity, no floor           0.1147
  20 day dollar volume, no floor     0.0842      what this replaces

The margin is wider where it matters. Splitting the sixty sessions at eight
before-open reporters, the no-floor propensity run gives 0.1053 on the light
ones against dollar volume's 0.0674, and light is the ordinary case: the median
session in the window carried two before-open reporters against 2026-08-13's
37. On such a morning tier 1 fills a couple of slots and this key decides the
rest, which is why a key pointed the wrong way costs most on the commonest kind
of day.

Dollar volume was not merely worse, it was pointed the wrong way. It measures
how much a name trades, and the largest names are the steadiest, so inside the
news tiers it sorted toward the least likely to gap: 361 of 1,736 subscribed
tier 2 slots gapped under dollar volume against 611 of 1,736 under propensity.

min_slots_per_tier exists because strict priority never gave tiers 3 and 4 a
single slot in 60 sessions, and when a floor of 4 gives them some they convert
at 0.40 and 0.35, which is at or above tier 2's 0.37. The floor costs
heavy-calendar recall, 0.1262 down to 0.1211, and buys light-calendar recall,
0.1053 up to 0.1126, which is the trade worth making on a window whose median
session is light.
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

## Gap stats

Per name gap propensity, written by gap_stats.py on the universe rebuild
schedule and read at 07:15 at no cost. It measures the thing the pool ordering
is trying to predict, rather than dollar volume, which measures how much a name
trades and runs against gap propensity because the largest names are the
steadiest.

The gap threshold is not repeated here. Propensity counts sessions whose open
sat beyond the Discovery gap_pct floor from the prior close, so the two can
never drift apart.

lookback_sessions             = 250        # about one trading year
min_sessions                  = 100        # seed: below this the propensity is NULL, never a computed zero
atr_sessions                  = 20         # sessions in the average true range

### The null note

A name with fewer than min_sessions of history stores a null propensity and its
real sessions_used. Null and measured zero are different facts: one is a name
nobody has measured, the other is a name that has not gapped in a year, and a
ranking that collapsed them would promote every recent listing above every
genuinely quiet name. Everything reading these fields sorts nulls last within
their tier rather than treating them as zero.

## Pool tiers

The order the pool is ranked in, best tier first, with the Discovery
within_tier_key descending as the tiebreak inside a tier, the fallback below it
and names carrying neither last. A name qualifying under several sources takes
its best tier and records all of them.

This ordering is a seed. It is an assumption about which priors most often
precede a premarket gap, not a measured base rate. pool_recall.json in the
nightly pass is what will eventually replace the assumption with a measurement.

tier = earnings_before_open : 1
tier = news_fresh : 2
tier = news_stale : 3
tier = prior_session_mover : 4
tier = recent_runner : 5

### The ghost row note, history rather than current behaviour

The bulk live feed returns some tickers twice. One row is current, the other is
a frozen snapshot from an old session that never aged out. On 2026-08-13 it
carried AZN twice: the live row was 157.90 against a 158.50 prior close, a
quiet -0.4 percent, and the ghost row was 188.41 against a 92.77 prior close, a
fabricated +103 percent that sorted straight to the top of the watchlist. The
ADT ghost was timestamped February 2023.

That deduplication is history, not current behaviour. The feed was normalised
by taking the newest timestamp per ticker, and any row older than 96 hours was
dropped outright, 96 chosen because a holiday Monday puts about 87 hours
between Friday's close and Tuesday's premarket. No code does that now.
Discovery builds the pool from the earnings calendar, the overnight news sweep,
two bulk end of day calls and the picks table, and the scan prices every
candidate from the collector file, so no scheduled job reads the bulk live feed
and a ghost row cannot reach a watchlist. The threshold it used,
max_quote_age_hours, has been removed from the block above along with its last
reader.

This note is kept as the reason the live feed is not trusted for selection, not
as a description of anything that runs. If bulk live is ever consumed for
selection again, the dedup and the age drop have to come back with it.

## Collector

The 07:20 to 09:25 websocket run that is the only source of today's premarket
price path.

start_time                    = 07:20
stop_time                     = 09:25
context_symbols               = SPY, QQQ, IWM, DIA, TLT, USO, UUP, VIXY
max_subscriptions             = 50         # hard socket cap including the 8 context tickers, so 42 candidate slots. Overflow comes off the tail of discover's ranked list, the collector does not reorder
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
gap_report_sessions           = 20
catchup_days                  = 5          # prior days with unfilled true columns retried each night, because the vendor usually publishes after the 22:15 run

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

candidate_count               = 12         # top N by the absolute gap measured from the collector against the pool's prior close
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
run_time cutoff. The numerator, the collector's premarket volume, is
still summed over every bar in the snapshot taken at the actual scan moment, so
a snapped run compares up to that many extra minutes of volume against the
run_time baseline. That skew is bounded and recorded: the packet
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
prose_token_stopwords         = ET, EST, EDT, UTC, GMT, AM, PM, US, USA, Q1, Q2, Q3, Q4, YOY, QOQ, EPS, ARR, GAAP, IPO, CEO, CFO, COO, CTO, FDA, SEC, FOMC, GDP, CPI, PPI, PCE, ISM, ADP, ETF, NYSE, USD, EUR, RVOL, VWAP, OHLCV, NOT, AND, THE, ALL, ON, SO, IT, AI, A, I

### The prose stopword note

Containment reads ticker claims out of the report's prose as well as its
tables. Prose is ambiguous in a way a Ticker column is not: "06:37 ET" is a
time, and ET is also Energy Transfer, so a naive reader of prose would fail
every report ever written. Time expressions and ISO dates are stripped before
tokens are taken, and this list removes what survives.

A and I joined the list on 2026-08-14, when the token pattern widened from two
characters to one so that single letter listings stop being invisible to the
check. A is Agilent and it is also the English article; I is not a listing at
all. Both are stopped in PROSE only. A Ticker column cell reading A is
unambiguous and is still checked, which is the case that matters: the guard
exists to catch a fabricated single letter row, and F, T and the other
nineteen remain checked everywhere.

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

## Job status

Every scheduled step appends one line to data/job-status.jsonl as it exits,
written in a finally block so a step that dies still records dying. This
exists because pool_recall raised NameError on every nightly run for a week
and nothing said so: its exit code is ignored by design, its main caught the
wrong exception type, and the watchdog only reads each job's final step
marker, which pool_recall does not write. An ignored exit code stays ignored
and the chain still does not break on a diagnostic. What changed is that the
failure now appears in the next morning's report.

Staleness is counted in trading sessions rather than hours, so a long weekend
or a holiday cannot raise a false alarm and cannot hide a real one either.
The value is the largest number of sessions that may pass between successes:
a weekday job is 1, and the Sunday jobs are 5 because a Sunday build is five
sessions old by the following Friday. A step with no success record at all is
reported only once the recorder itself has existed longer than that window,
since nothing can be overdue before there was anywhere to record it.

Past max_steps_named_in_report overdue steps the report stops listing them
and says the machine or the schedule has stopped instead, naming only the
worst few. Sixteen named steps is not a list of problems, it is one problem,
and a line that long is a line nobody finishes reading.

max_steps_named_in_report      = 4

## Job status steps

Every key in this section is a scheduled step, and its value is the largest
number of trading sessions that may pass between successes. Nothing else
belongs here: job_status.py treats the whole section as the list of steps, so
a knob parked here would become a phantom step that has never succeeded. That
is why the one knob above lives in its own section.

A step is added here when the scheduler starts invoking it, and removed when
it stops. A step the scheduler runs that is missing from this list is never
reported as overdue, which is the one failure this list can have, so
test_entrypoints.py checks the two lists against each other.

universe                      = 5          # Sunday 20:00, five sessions old by Friday
gap_stats                     = 5          # rides the universe schedule
discover                      = 1
baseline                      = 1
collector                     = 1
scan                          = 1
analyst                       = 1
render                        = 1
verify                        = 1
deliver                       = 1
archive                       = 1
backfill                      = 1
outcomes                      = 1
pool_recall                   = 1
monitor                       = 1
calendar                      = 1

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

Resolution takes the collector's premarket price first and falls back to end of
day. The end of day call is made for every label regardless, because the prior
close comes from it; the collector only ever supplies the last price.

Five of the nine are also on the collector's context list, so those rows are
priced from this morning's tape and record source collector with
prior_session_only false. The index, bond and dollar symbols are not subscribed
and have no premarket tape on this plan, so they report the last completed
session and say so: source eod, prior_session_only true. Every row records
which path answered, which is what lets the vintage check tell a row that is
honestly labelled stale from one silently claiming to be current.

The live endpoint is not read here at all. The /real-time family serves the
last completed session, so at 08:45 it published yesterday's move as today's.

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
