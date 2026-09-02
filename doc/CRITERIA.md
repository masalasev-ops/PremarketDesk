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
max_symbols_named_per_line    = 40         # a sweep that loses part of its list names
                                           # the symbols it lost, which is the whole
                                           # value of the line on a bad network day and
                                           # is worthless past a point: a fully starved
                                           # float cache sweep is 1,870 tickers on one
                                           # line. Past this it names the first few and
                                           # counts the rest, which the file it wrote
                                           # carries in full.

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
end of day: three at 07:15, two for discover's prior session movers source and
one for the universe closes sidecar discover writes for the notable movers
section, and two at 22:15 for the nightly pool recall, at a measured 100
credits each
[corrected 2026-08-17: was "98 counted calls each, about 392 a day". The
ledger counts calls and the meter bills credits, and the meter says a flat
100, reconciled exactly on two universe rebuilds], about 500 a day against a
shared 100,000. [corrected 2026-08-20: was "two at 07:15" and "about 400 a
day". write_universe_closes has bought a third bulk day since 2026-08-18 and
every discover log since counts three eod-bulk-last-day calls.] The weekly universe rebuild buys
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
quota_headroom_multiple       = 1.5        # SEED, not measured. A work sized
                                           # gate requires this multiple of what
                                           # the step will actually spend before
                                           # it starts. The margin is for the
                                           # other project on the key, which was
                                           # measured taking 15,910 credits in
                                           # thirty minutes on 2026-08-16, not
                                           # for error in the price table, which
                                           # reconciles exactly. Revisit when the
                                           # sampler has a few weeks of the
                                           # sibling's shape.

## Quota costs

What the shared counter charges, as against what the client side ledger counts.
These are different numbers and the gap is not small. The 2026-08-17 universe
rebuild reported 172 http calls and moved the meter 4,945, because
us-quote-delayed is billed per symbol while it is issued twenty at a time, and
one bulk day is a flat hundred. Any gate sized off eodhd.call_count() is
therefore sized off the wrong quantity, and for the universe rebuild it would
be set twenty eight times too low.

MEASURED, not seeded, and the arithmetic closes exactly on two independent
runs. On the 00:06:53 rebuild, 2 symbol lists + 1 eod + 20 bulk days + 2,942
staged names priced by this table gives 2 + 1 + 2,000 + 2,942, or 4,945, which is
the delta between the entry and exit readings in logs/meter-2026-08-17.log. The
20:30:01 run of the evening before staged 2,941 and read 4,944 at its exit. The
two runs also pin the user endpoint at zero: there is no slack in either sum for
the meter reads themselves.

The left side is the endpoint name as the call ledger reports it, except
us-quote-delayed-per-symbol, which is named for its unit because that unit is
the whole point. A call that is not priced here cannot be costed, and
eodhd.credit_cost raises rather than treating it as free.

cost = eod-bulk-last-day : 100
cost = us-quote-delayed-per-symbol : 1
cost = eod : 1
cost = exchange-symbol-list : 1
cost = news : 5
cost = news-feed : 5
cost = intraday-1m : 5
cost = user : 0

**The three added 2026-08-31, and the one that is a correction.** Measured the
same way as the rest, five calls of one kind between two user reads, and every
delta divided exactly: news 25 over 5, intraday-1m 25 over 5, news-feed 5 over
1. Nothing else was touching the key, and the six user reads interleaved
through the measurement re-pin that endpoint at zero for a third time.

intraday-1m is the correction. Nothing had ever priced it, and a reader
counting http calls would have costed it at one. It is FIVE, so the two
scheduled steps that use it cost five times what a call count suggests: the
07:15 baseline warm makes one call per stale subscribed ticker, up to 42, which
is about 210 credits and not 42, and the nightly verify_against_intraday makes
one per collected symbol, about 50, which is about 250 and not 50. Neither is
gated on a number sized off the old reading, so nothing was actually undersized
and nothing is being fixed here. What changes is that the next gate to be
written cannot be wrong by a factor of five, which is exactly the mistake this
section exists to have already made once.

## Notable

The briefing section of the report, and nothing else. Built on 2026-08-20 and
live from that morning; BUILD_PLAN.md Layer 4 holds the design and DECISIONS.md
carries the calls made while building it. All four keys below are read:
list_size, min_abs_gap_pct and min_return_stdev_pct by morning/scan.py, and
min_sessions_for_move_sigma by both selection/gap_stats.py, as the floor on
return_stdev_20d, and scan.py, which quotes it in the reason a null sigma
carries.

These names are chosen for the size and unusualness of their move, not for
tradeability. They are never screened against day_setup or swing_setup, never
scored, never given a conviction, and never written to picks. Nothing in this
section may be read by the trading path: picks is the record of what the screen
claimed, and mixing briefing names into it would destroy the recall
measurement.

Three legs, each measured over a different window, and every row states which
leg produced it and the session it is as of. A section that silently mixes an
overnight move with a two day old one is worse than no section, so the leg
label is fixed template text rather than something the model composes. Four
lists are ranked from those three legs, and no ranked list mixes two legs: a
list that orders a fresher window against an older one is not an ordering.

No leg can carry today's regular session move, because the report is written
before the open. The premarket leg exists only for names the collector
subscribed to, which is at most [Collector] max_subscriptions of the
universe, so for every
other name the most recent evidence is the previous session's close.

move_sigma is the move divided by the name's own daily volatility, scaled by
the square root of the number of sessions the move spans, so a quiet megacap
moving 2 percent overnight and a thin small cap moving 6 percent over two
sessions land at comparable numbers. That scaling assumes daily returns are
independent, which a sustained run in one name is not, so the number
understates how unusual a run is rather than overstating it. The denominator
floors below mirror the RVOL denominator floor note: a denominator too small
to divide by yields a null with the reason recorded, never a substituted
number and never a silent drop.

list_size                     = 5          # symbols per LIST, before deduplication.
                                           # Not per leg: the prior session leg
                                           # carries two of the four lists, so it
                                           # can publish up to ten rows and
                                           # deduplicates within itself
min_abs_gap_pct               = 1          # the floor for the market cap list only,
                                           # so a megacap barely moving does not
                                           # crowd out a real mover
min_sessions_for_move_sigma   = 20         # sessions of returns the denominator needs
min_return_stdev_pct          = 0.1        # SEED, not measured. Below this the daily
                                           # return stdev is too small to divide by
                                           # and move_sigma is null with the reason.
                                           # A name that has barely moved in twenty
                                           # sessions would otherwise report an
                                           # enormous sigma on any move at all.

## Composition

What the morning's list looks like TOGETHER, which is a different question from
what each name looks like. Read by morning/scan.py list_shape and by nothing
else. Nothing in this section reaches eligibility, the score or the picks table.

The report has always said a great deal about each candidate and nothing at all
about the twelve as a group. Three energy names on one morning is a fact about
the morning rather than about any of the three, and a name that has now been
picked on three of the last five sessions is a different object from a first
appearance. Neither is visible from a per candidate block, because neither is a
property of a candidate.

DESCRIBING IS NOT SCREENING and the boundary is the same one the notable movers
section holds. A sector concentration is something for a reader to weigh, not
evidence about any one name, and screening on it would mean refusing a good
setup for the company its peers keep. There is no threshold here and no
parameter that could become one: the counts are published and the reader
decides what they mean.

min_sessions_for_sector_history = 20       # SESSIONS, not rows, that must carry a sector
                                           # before the sector line prints its historical
                                           # median. picks gained its sector column on
                                           # 2026-09-02, so every earlier session carries
                                           # NULL and cannot contribute, and until this
                                           # many have accumulated the line states in words
                                           # that the comparison is unavailable. A median
                                           # over five sessions is a number computed
                                           # correctly over a sample too small to mean
                                           # anything, which is worse than no number
                                           # because it looks like one. Twenty matches
                                           # [Notable] min_sessions_for_move_sigma, the
                                           # other place this project refuses to divide by
                                           # too little history
repeat_lookback_sessions      = 5          # how many RECORDED SESSIONS back the repeat
                                           # appearance count reaches, counted as distinct
                                           # dates already in picks rather than as calendar
                                           # days. Five calendar days over a long weekend is
                                           # three sessions and over a holiday week is fewer,
                                           # so a calendar window would silently shrink in
                                           # exactly the weeks a reader is least able to
                                           # remember what ran last. SEED, not measured:
                                           # it is a reporting window, not a threshold, and
                                           # nothing branches on it

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

gap_pct                       = > 3        # absolute gap versus prior close, percent. ABSOLUTE: evaluate_eligibility takes abs(), so
                                           # this screen is direction blind too and require_above_prior_high is what makes it long in
                                           # practice. Measured over the live picks table on 2026-09-01: 0 of the 12 rows that reached
                                           # either watchlist gapped down, because
                                           # clearing the prior session high requires the premarket price above a level at or above
                                           # that session's close. That is arithmetic plus one assumption, that the vendor's daily high
                                           # and close come from one consistently adjusted row, which is the class of assumption the
                                           # 2026-08-20 review caught disagreeing by 1.67 percent. See [Score gap].
price                         = > 3        # dollars, latest premarket print
market_cap                    = > 1B
premarket_rvol                = > 1.5      # the CONSOLIDATED premarket volume estimate divided by the cached baseline median. Was the collector's socket volume until 2026-08-21; see the capture rate note
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
exchanges                     = NYSE, NASDAQ   # the venues the universe COVERS, not only the symbol lists fetched.
                                           # A row is admitted on its own Exchange field, so adding NYSE ARCA or
                                           # NYSE MKT here is what admits them. See the exchange coverage note.
session_calendar_symbol       = SPY.US   # its EOD history supplies the real session dates
expected_count_min            = 1000       # a smaller result means the build went wrong
expected_count_max            = 3000       # a larger result means the type filter went wrong
max_age_days                  = 10         # every later script refuses to run past this
closes_retention_days         = 7          # days; night.prune_data deletes universe-closes-<date>.json older than this. See the closes retention note
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
max_unswept_fraction          = 0.02       # SEED, not measured. Names the market
                                           # cap sweep got NO answer for, as a share
                                           # of those it examined. Above this the
                                           # build refuses to overwrite the previous
                                           # universe, because a truncated file that
                                           # looks fresh is worse than a stale one:
                                           # the monitor relaunches on age, so a bad
                                           # new file is never retried while a missing
                                           # one is. This is a different question from
                                           # the count fraction above. That one asks
                                           # whether the file is the right SIZE, this
                                           # asks whether its names were dropped on
                                           # evidence or on silence. A quota starved
                                           # sweep amputates the illiquid tail,
                                           # because staged is sorted by dollar volume
                                           # descending, and the count fraction cannot
                                           # see that until half the file is gone.
                                           # Names the vendor answered a batch WITHOUT
                                           # are excluded: that is its coverage, not
                                           # this run's failure, and it is structural
                                           # at 26 of 2,942 on 2026-08-17. So the
                                           # baseline here is zero and 0.02 of 2,942
                                           # is 58 names, which clears two lost
                                           # batches of twenty and trips on the third.

### The exchange coverage note

Added 2026-08-28, when this key was found to filter the REQUESTS and not the
rows. universe.py asked the vendor for the NYSE and NASDAQ symbol lists and
then admitted every Common Stock row either list returned, whatever venue the
row named. The vendor's NYSE list is not only NYSE: measured 2026-08-28, its
2,365 Common Stock rows split 2,322 NYSE, 27 NYSE ARCA and 16 NYSE MKT. So a
key reading "NYSE, NASDAQ" produced a file covering four exchanges.

Three of those 43 cleared the price, cap and volume floors into the 2,771 name
file: PHYS, PSLV and VZLA. Two of the three are the second half of the
argument. Sprott Physical Gold Trust and Sprott Physical Silver are closed end
commodity trusts, which is what allowed_security_type above exists to exclude,
and they are in the file because the vendor TYPES them Common Stock. A type
filter cannot catch a vendor mistyping and was never going to. The exchange key
catches both for nothing.

The row's own Exchange field is now matched against this key. A row whose field
is EMPTY is kept and attributed to the list it came from, because that list is
a configured exchange by construction and dropping it would empty the universe
on a vendor that stops populating the column. Every drop is counted per venue
into the build's notes, because the failure this could hide is the vendor
relabelling NYSE itself: every row would drop, and the count floors above would
refuse the build with nothing saying why.

To admit NYSE ARCA or NYSE MKT, add them to the key. That is the whole change,
and it is here rather than in the code because that is what this file is for.

The current universe.json predates this and still carries all three names. It
is rebuilt on the Sunday 21:00 pass.

### The closes retention note

This is the project's first retention window of any kind. Until 2026-08-21
nothing under data/ was ever deleted on a schedule, and a grep of the whole
tree for prune, retention or unlink returned one call, in probe_alpaca_live,
cleaning up after itself. data/ grew by about 900 KB a trading day with nothing
watching it.

**What the window is protecting against is not disk, it is a wrong deletion.**
universe-closes-<date>.json is written by discover at 07:15 and read by
scan.load_universe_closes at 08:45 for the SAME session_date, which scan.main
takes from the clock rather than from an argument. There is no second reader in
the tree, and no supported way to ask for a past one: --rescore reads the saved
packet and never reaches this file. The file is therefore dead to the CODE the
moment its own chain window closes at [Monitor] rerun_chain_until the same
morning, and every day kept after that is margin for a human reading it by
hand.

7 is that margin, not a measurement, and it is marked SEED for that reason. It
covers any weekday plus a long weekend, so "something looked wrong last
Tuesday" is still answerable on Monday. It holds about five files, near 1.2 MB,
in steady state, against 233 KB a trading day and no ceiling.

**What is NOT prunable is the more important half of this note.** night/
prune_data.py deletes only what its PRUNABLE whitelist names, which today is
this one file class. data/premarket/ is the collector's own socket capture and
is not reproducible at any price, being a recording of a tape that no longer
exists, as well as the only record of the 2026-08-14 over count. data/backtest/
eod is the population the shipped float rotation edges were fitted on and a
re-fit reads it. data/backtest/sessions is the replay behind the subscription
cap recall table, which is an open purchasing decision. runs/ is what
build_archive rebuilds site/ from, so pruning it would silently shorten the
archive. None of those is a candidate, and a sweeper that decided by age alone
would have reached all four.

The age is read from the FILENAME, never the mtime. The file describes the
session its name carries whoever copied it and whenever; an mtime rule would
spare a file a backup had touched and delete one it had not, which makes the
window a property of the filesystem rather than of the data.

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

These two are not seeds. They were chosen by src/research/backtest_pool.py over 60
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

Cost: two bulk end of day calls at a measured 100 credits each
[corrected 2026-08-17: was 98 counted calls each], plus one
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
return_stdev_sessions         = 20         # sessions in return_stdev_20d. See the stdev window note
max_unswept_fraction          = 0.02       # SEED, not measured. See the partial sweep note

### The partial sweep note

This is [Universe] max_unswept_fraction asked of the other half of the same
Sunday job, and it is set to the same number for the same reason rather than
because the two were measured together.

**What it protects against.** build() writes every name it reached under a NEW
as_of and main() only failed the step when NOTHING was written, while load_all()
took MAX(as_of) unconditionally. So a sweep that died 200 names into 2,745
exited 0, and the next 07:15 read served those 200 and could not see the
complete set behind them. gap_propensity is what discover ranks the whole pool
by inside each tier, so the pool changes shape for a reason that has nothing to
do with the market. build()'s own docstring already called a run that stops
partway "worse than not running"; nothing enforced it.
[Discovery] min_ranked_fraction_to_subscribe is not that enforcement. It asks
whether enough of the universe carries ANY ranking key, and
within_tier_fallback means atr_pct_20d answers for a name propensity cannot
score, so a sweep can lose most of its propensity column and still clear that
floor.

**What now happens above it.** Nothing is deleted: the rows a partial sweep
wrote are real measurements of the names they cover. load_all() skips that as_of
and reads the newest one below the floor, saying which it skipped and why, and
the step declares itself failed so the run is visible in the job trail rather
than only in what the next reader declines to use. gap_sweeps is the record it
reads, one row per as_of, and an as_of written before that table existed carries
no row and is trusted.

**Why 0.02 and not a measurement.** The same argument [Universe]
max_unswept_fraction makes: it sits far above the handful of names the vendor
structurally has no history for, and far below any run that ended early. On a
2,745 name universe it is 54 names. It is a SEED and the header of this file
applies.

### The stdev window note

return_stdev_20d is the denominator [Notable] move_sigma divides by, and until
2026-08-20 this key did not exist. gap_stats trimmed its CLOSES to
lookback_sessions and took the standard deviation over every return in that
list, so a column named for twenty sessions held a trailing one year figure.
[Notable] min_sessions_for_move_sigma was doing duty as the window and it is
not one: it is a floor on how many returns are needed before the answer may be
published, which is a different question from how many go into it.

The two are kept apart on purpose. A floor answers "is this measurable"; a
window answers "measurable over what". Reusing one for the other is how the
column ended up describing a different quantity from its own name, and
BUILD_PLAN.md, in the Layer 4 list of what is already built, recorded the
intended behaviour as already built the whole time.

What the year long version cost, since the section that reads it is not built
yet and no report has carried it: a name that was violent for a year and has
been quiet for a month keeps the violent denominator, so a genuinely unusual
move reads as ordinary and never reaches the list. The reverse overstates a
megacap that has just started moving. It also disarmed min_return_stdev_pct,
whose whole purpose is that "a name that has barely moved in twenty sessions
would otherwise report an enormous sigma on any move at all": over 250 sessions
almost nothing sits below 0.1, so the floor never fired.

20 matches the column name and the specification. It is not independently
measured, and the header of this file applies.

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
subscription_retry_wait_s     = 60         # measured 2026-08-19: a dropped connection's 50 slots were still held 1s later and free within 105s
max_subscription_retries      = 4          # four waits is four minutes, against a window that is two hours long
verify_warmup_minutes         = 25         # see the verification note below
verify_window_minutes         = 15
volume_check_agreement_pct    = 1.0        # SEED, not measured. How close either reading has to sit to the vendor to count as agreement. See the volume check note
volume_check_max_age_days     = 5          # how far back the 08:45 scan will read a written verify_intraday.json. See the volume check note
premarket_capture_rate        = 0.1172     # the share of the consolidated tape the socket carries for a symbol nothing has been measured for. MEASURED, see the capture rate note
min_capture_vendor_volume     = 2000       # shares; a per symbol capture share measured on less vendor volume than this is refused and the default is used instead. SEED, see the capture evidence note
min_capture_minutes           = 3          # common minutes; the same refusal on a share backed by fewer. SEED, see the capture evidence note
min_probe_messages_per_arm    = 20         # messages; probe_socket_cap leaves a symbol out of its B/A median unless BOTH arms carried this many for it. SEED, see the probe evidence note

### The capture rate note

This is the only number in this file that exists to correct another
measurement rather than to threshold one, so it is worth being exact about what
it is and is not.

**What it corrects.** premarket RVOL divides collector socket volume by a
baseline collect/baseline.py builds from the vendor's 1m intraday bars. Those
are two different tapes: the socket carries a fraction of the consolidated
volume. Premarket float rotation divides the same socket numerator by a float,
against bands fitted on Alpaca volume, which is consolidated. Both ratios
therefore understate by about the reciprocal of this number, and the day
screen's premarket_rvol floor of 1.5 was being applied to a value that could
not reach it: six mornings, 62 candidates, zero day eligible, [2026-08-21: still exactly true, and now also a measure of the cost: re-read against Alpaca full SIP, those six mornings would have held twenty four names instead of six. See DECISIONS 2026-08-21 eighth.] 19 of them
failing on that line alone.

**How it was measured.** verify_against_intraday compares collector volume
against vendor intraday volume over identical minutes and now keeps the pair
per symbol. All six collected sessions were re-measured on 2026-08-21 for 297
intraday calls: doc/research/collector-capture.json.

    session aggregate, collector over vendor
      2026-08-13   1.4926      a different regime, see below
      2026-08-14   3.8257      a different regime, see below
      2026-08-17   0.1028
      2026-08-18   0.0938
      2026-08-19   0.0862
      2026-08-20   0.0908

The first two sessions over report and are excluded: 2026-08-14 carried the
known vintage defect, and doc/research/COLLECTOR_VOLUME.md holds the replay
measurement. Everything from 2026-08-17 sits inside two percentage points.

**Why a single number is allowed to stand for a symbol.** Because the share is
a property of the symbol rather than noise, which is the whole reason this
correction is possible. Over symbols measured on three or more of the four
clean sessions, the median max/min spread is 1.48 times and 18 of 25 vary by
less than two. The liquid names are tighter: AXTI 1.2, TLT 1.2, NBIS 1.2,
MU 1.4, SPY 1.5. A 1.5 times dispersion inside a nine times correction is a
different order of error from the one being fixed.

**Why 0.1172 rather than 0.0923.** 0.0923 is the median of the session
aggregates, which are volume weighted and answer "what share of the total tape
did the socket hear". This number answers a different question, "what share
should be assumed for ONE symbol nothing has been measured for", and the right
estimator for that is the median of the per symbol rates, which is 0.1172 over
110 symbols. It is also the safer of the two: a higher assumed capture produces
a lower corrected ratio, and the safe direction on a long only screen is to
withhold rather than admit.

**It is a fallback, not the usual path.** scan prefers the symbol's OWN
collector over vendor ratio from the newest verify_intraday.json, and reaches
this number only for a symbol that check does not carry. Each candidate records
which of the two it used.

**How it is re-derived now.** Not by re-running the EODHD capture backfill.
The source is picks.capture_observed, written nightly from Alpaca SIP since
2026-08-21, and the instruments are research/measure_capture_rate.py, which
applies the guards and archives the raw rows, and research/sweep_capture_rate.py,
which scores candidate replacements off that archive with no database read and
no vendor call. Two things gate a change to the value, and both are open:
[Truth] baseline_sessions of GUARDED sessions, against six today, and
[Collector] start_time, because every row of that record was measured over a
window opening at 07:20 and a re-fit taken before that key moves is a fit to a
window about to be replaced. Measured 2026-09-01 and recorded rather than
acted on: the re-derived single number is 0.0968 by this file's own recipe,
0.1172 sits at quantile 0.61 of the record so the shipped key is already the
conservative one, and the two admit the same names on the day screen.

**What would retire it.** If the 2026-08-21 06:30 census shows the parser is
dropping volume the feed delivered, the numerator can be made whole and this
correction becomes unnecessary rather than merely smaller. If the stream
structurally omits off exchange volume, this is the permanent answer and this
number should be re-derived whenever the collector, its window, or its
subscription list changes materially. Re-derive by re-running the capture
backfill and reading the per symbol median.

### The capture evidence note

A capture share is a ratio of two volumes and it inherits the frailty of the
smaller one. These two floors decide when a measured share is trusted over the
file wide default, and they are SEEDS in the sense [Baseline]'s denominator
floor note uses: chosen to exclude degenerate measurements, with the effect
measured but the exact edge not read off an empty stretch, because the vendor
volume distribution has no empty stretch to read.

What they exclude, measured over the 202 symbol sessions on the four clean
sessions in doc/research/collector-capture.json:

| | |
| --- | ---: |
| UUP on 2026-08-20 | 10 vendor shares, 1 minute, share 1.0000 |
| MH on 2026-08-17 | 2 vendor shares, share 1.0000 |
| VNET on 2026-08-19 | 50 vendor shares, share 1.1800 |
| NBTX on 2026-08-18 | 931 vendor shares, share 0.9635 |

A share of 1.0 means no correction at all for a symbol that ordinarily
captures about a tenth, which is the whole defect back again for that one row.
A share of 1.18 is impossible: a socket carrying a subset of the tape cannot
report more than all of it. Every share above 0.9 in that population sat under
a thousand vendor shares, which is the corroboration that this is a thin
evidence problem rather than a real spread.

The effect of the volume floor on the surviving population, as the p95 over p05
ratio of the share:

| floor | excluded | kept | kept p95/p05 |
| ---: | ---: | ---: | ---: |
| none | 0 | 202 | 9.6 |
| 500 | 11 | 191 | 9.2 |
| 1,000 | 15 | 187 | 9.0 |
| **2,000** | **24** | **178** | **6.8** |
| 5,000 | 35 | 167 | 6.2 |
| 20,000 | 66 | 136 | 5.9 |

Most of the available improvement arrives by 2,000 and the curve flattens after
it, while the cost of a higher floor rises steadily: every excluded symbol falls
back to a file wide default instead of its own measurement. 3 common minutes
selects the same rows on this population, so it catches nothing extra today and
exists for the case where a symbol trades a large block in one minute and looks
well measured on volume alone.

The impossible value is refused separately from the floors and regardless of
volume, on the same reasoning as [Float rotation] max_float_to_shares_outstanding:
a value that cannot occur is refused for being impossible, not for being thin.

Below any of these the symbol uses premarket_capture_rate and the row records
which refusal sent it there, so a thin measurement is visible rather than
silently averaged in.

### The probe evidence note

src/research/probe_socket_cap.py answers one question: does the 50 symbol
socket cap starve delivery, so that the collector's volume shortfall is the
cap's doing rather than the tape's. It subscribes 8 symbols on arm A and 50 on
arm B, alternating, and compares the per symbol message rate. B over A near 1
means the cap is not the cause.

**The reading is only as good as the smaller of the two counts behind it, and
until 2026-08-21 nothing said so.** That morning's premarket run carried 123
trade messages across 8 symbols over 14 minutes of arm time. IWM's B/A of 0.14
was 49 messages against 9. UUP's 0.00 was one against none. The probe printed
"median B/A message rate across 6 watched symbols is 0.58" and the sentence
that reads a ratio well below 1 as the cap starving delivery, with nothing on
the page about the sample. The 2026-08-19 run, taken on a regular hours tape,
carried 8,056 messages and its median was 0.87. A reader with both would
conclude the cap bites in premarket and not in the session, when the whole
difference is 65 times less tape.

**Where 20 comes from.** Each symbol's B/A was recomputed per cycle on the
2026-08-19 payload, where four cycles of both arms ran on a rich tape. The
spread between a symbol's highest and lowest cycle ratio is how far the same
measurement moves with nothing about the cap changing:

| thinnest cycle, messages | that symbol's own B/A spread |
| ---: | ---: |
| 0 | undefined |
| 2 | 66.0 |
| 3 | 6.2 |
| 23 | 2.5 and 8.4 |
| 47 | 1.9 |
| 97 | 1.4 |
| 255 | 2.4 |

Below about 20 the ratio is not a measurement of anything. Above it the ratio
is still noisy, and that is the more important half: the best measured symbols
in the richest sample available still moved by 1.4 to 2.4 times, which is the
same size as the effect the probe is asked to detect. So the floor removes what
cannot be a reading, and the probe now also computes that spread from its own
cycles and prints it beside the median. A median inside the spread is reported
as separating nothing rather than as a number.

**Not capped, floored, for the reason [Baseline]'s denominator floor note
gives.** And unlike the capture floors this one guards a research instrument,
not the live screen: nothing under src/morning reads it, so a wrong value here
mismeasures a question and cannot mis-screen a candidate.

### The volume check note

verify_against_intraday compares the collector against the vendor's one minute
bars on identical minutes and is the definitive measure of what the socket
misses. The nightly writes it to runs/<date>/verify_intraday.json. Until
2026-08-20 nothing under src/morning read that file, so the number existed and
reached no reader, and the morning report described premarket RVOL as a lower
bound while naming only the smaller of the two reasons it is one.

The two reasons are different in kind. The WINDOW reason is arithmetic and
needs no measurement: the numerator starts at [Collector] start_time and the
denominator at [Baseline] session_start, so the ratio is bounded below by
construction. The FEED reason is empirical and is exactly what this file
measures: the numerator comes from the collector socket and the denominator
from the vendor intraday endpoint, so whatever those two disagree by passes
straight into the ratio. On the four sessions measured before this key existed
the median absolute disagreement was 90.0, 90.0, 88.4 and 71.0 percent, with
1 symbol out of 210 inside one percent.

The scan reads and never computes. Computing it costs one intraday call per
collected symbol, which is fifty of them, and the 08:45 window does not spend
that. A check older than volume_check_max_age_days is reported with its age
rather than used silently, and no check at all is itself written into the gaps
list: an unmeasured feed is not a clean one.

The check reports a DIRECTION, and it reports one only where its two readings
say the same thing. The signed median is the typical symbol and the aggregate
ratio is the whole tape, and doc/research/COLLECTOR_VOLUME.md records a session
where those two point opposite ways: 2026-08-14 came back at a signed median of
-33.77 percent beside an aggregate 3.83 times the vendor. Each reading is
placed against volume_check_agreement_pct rather than against zero, as a
distance from the vendor in percent, the aggregate ratio converted as
(ratio - 1) * 100. Both inside the band is agree, both below is under, both
above is over, and anything else is mixed with a phrase naming which reading
fell where.

Without the band there was no word for a collector that MATCHES the vendor,
which is the outcome this measurement exists to work towards: a signed median
of zero beside a ratio of one fell through to mixed and published as "the two
readings disagree, the typical symbol falling on one side of the vendor and the
aggregate tape on the other", which is false of a session where neither reading
is on a side. 1.0 percent is a seed fitted to nothing, chosen to match the
within one percent count this same function already reports so that the two
readings of "close enough" in one summary are the same number. The four
sessions measured so far sit at 90.0, 90.0, 88.4 and 71.0 percent median
absolute disagreement, so the band has never yet been reached and nothing has
tested it. The header of this file applies.

5 days covers a long weekend plus a session the vendor published late. It is
not independently validated and the header of this file applies.

### The symbols limit note

The socket cap is 50 concurrent symbols and it is ACCOUNT WIDE, not per
connection. A subscribe frame that would take the account past 50 is answered
with {"status_code":422,"message":"Symbols limit reached"} and no data.

Until 2026-08-19 that was treated as fatal, on the reasoning that a refusal
means another process holds the slots and retrying would be refused every time
until the window was gone. That reasoning was wrong, and the morning of
2026-08-19 is the counterexample. The collector had been streaming happily on
50 symbols since 08:16. At 08:34 the remote host closed the connection, the
reconnect went out about a second later, and the server refused it: the
account was still holding the dropped connection's 50 symbols. The process
competing for the slots was the collector itself, one second in its own past.
It exited, and the last 50 minutes of the window were lost. A hand restart at
08:37:13 subscribed without complaint, so the slots had been released
somewhere inside 105 seconds.

So a refusal is now retried, max_subscription_retries times, waiting
subscription_retry_wait_s between attempts. The asymmetry is the argument. If
the slots are ours, waiting gets them back and the morning continues. If they
genuinely belong to another process, four waits cost four minutes of a two
hour window and then the run fails exactly as it used to. The old behaviour
paid the whole window to avoid a four minute delay.

The original reasoning is kept above rather than deleted because it was not
silly, it was untested: nothing had ever observed a refusal, so the note was
written from the vendor's documentation of the cap rather than from a
refusal's behaviour.

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
thin_baseline_premarket_volume = 10000     # shares; at or above the floor but below this, pm_rvol is PUBLISHED and
                                           # SAID to rest on a thin denominator. Disclosure only: it refuses nothing,
                                           # changes no screen and moves nobody onto the float rotation path. Measured
                                           # 2026-08-28, see the note below.

### The denominator floor note

A seed value, chosen to exclude degenerate denominators, not a validated
threshold. [corrected 2026-08-28: this went on to say "Nothing has been
measured against it yet", which was true from 2026-08-14 until it was
measured. The measurement is below. The VALUE has not moved and is still a
seed; what is no longer true is that nothing is known about it.]

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

#### What 1000 actually buys, measured 2026-08-28

The floor's stated job is that a denominator must not max the RVOL scoring
band "by construction rather than by evidence". That is a testable claim and
nothing had tested it, so this is the test.

For each of the 241 names holding a cached 08:45 baseline, the same 20 prior
sessions over the same 04:00 window were refetched, and each session was
divided by the median of the set it belongs to. The question asked of every
name: what share of its own ORDINARY sessions would score above 3, the top
band, against its own median? Half of them sit above the median by
construction, so this measures the right tail, and a name whose premarket
volume is steady has almost nothing at 3x while a name that usually trades
nothing has most of it there. 241 intraday calls, 239 names with a non zero
median.

| baseline median | names | ordinary sessions above 3x their own median |
| --- | ---: | ---: |
| 0 to 1,000 | 46 | 30% |
| 1,000 to 2,000 | 13 | 20% |
| 2,000 to 5,000 | 30 | 20% |
| 5,000 to 10,000 | 19 | 15% |
| 10,000 to 25,000 | 25 | 15% |
| 25,000 to 100,000 | 37 | 10% |
| 100,000 and up | 69 | 5% |

Monotonic, and it says two things.

The floor is real and points the right way: it removes the 30% band, which is
the population ARX and MH came from. It is also set too low to do the job the
paragraph above claims for it. Just over the floor, one ordinary session in
five scores into the top band, against one in twenty for the largest names.
A name at 1,078 shares clearing the volume screen is not evidence of anything
in the way a name at 740,086 clearing it is.

It is not hypothetical either. 25 of the 80 premarket RVOLs ever published
stood on a median under 10,000 shares, 14 of them since the floor was added:
DKS at 514.0 on 1,085 shares, CHA at 316.1 on 1,078, KSS at 191.1 on 1,944,
PLAB at 70.7 on 4,135, DQ at 53.6 on 1,198, MNSO at 25.2 on 6,276.

#### Why the value did not move, and what it would take

The obvious answer, raise the floor to 10,000, is refused here because the
floor does not travel alone. A name refused by it is not dropped: it is
RESCUED onto [Score premarket float rotation], and those bands were set on
2026-08-16 by reading the rotation distribution of the rescued population
specifically, at the quantiles reproducing what the RVOL bands pay. Raising
the floor changes who is rescued: the names it would newly rescue have medians
between 1,000 and 10,000 and are materially more liquid than the sub 1,000
names the bands were fitted on. Their rotations sit higher, so the existing
edges would pay them MORE than the RVOL bands would have, which is the wrong
direction: the change meant to stop a thin name maxing a band would hand it
the band through the other door.

So moving this number is a TWO PART change, floor and rotation edges together,
refitted on whatever population the new floor rescues. That is a study, not an
edit, and it is owed one.

#### The study, run 2026-08-31, and it is a THREE part change

`research/sweep_baseline_floor.py` re-fits the rotation edges at every candidate
floor by the same arithmetic `research/float_rotation_study.py` uses, against
the RVOL payout recomputed on the population each floor produces. It takes no
vendor call: the study now records `sweep_rows`, four fields per scored row, so
a re-fit is arithmetic on a file. At the shipped floor the sweep reproduces the
study's own fit exactly, which is what makes the other rows worth reading.

Measured over 6,500 scored rows from 50 sessions, on the top-by-gap slice the
shipped edges are fitted to:

| floor | keeps an RVOL | rescued | 2pt target | 2pt edge | 1pt edge |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 (shipped) | 358 | 189 | 0.5335 | 0.00033 | 0.0002 |
| 2,000 | 326 | 221 | 0.4939 | 0.0004 | 0.00023 |
| 5,000 | 275 | 272 | 0.4509 | 0.00049 | 0.00029 |
| 10,000 | 244 | 303 | 0.4180 | 0.00056 | 0.00034 |
| 25,000 | 184 | 363 | 0.3696 | 0.00079 | 0.00042 |

**The paragraph above predicted the direction and the size is now known.** The
newly rescued names do sit higher, so the edges have to RISE to stop
overpaying them: 0.00033 becomes 0.00056 at a 10,000 floor, a 70 percent move,
against 48 percent at 5,000 and 21 percent at 2,000. Raising the floor without
that refit hands a thin name its band through the other door, exactly as
written.

**The part that was not named, and it is the one that decides the change.**
[Day setup] `premarket_rvol` is `> 1.5` and has NO rotation alternative, and
`Rule.test(None)` is false, so a name whose ratio the floor refuses is not
merely rescored: it leaves the day watchlist outright, however busy it was.
Over the live record, 11 sessions carrying 70 published ratios, a 10,000 floor
refuses 16 of them, and 2 of those were day_eligible: PLAB on 2026-08-26 at a
4,135 share median and SAIC on 2026-08-31 at 1,002. Both were green. Both have
a rotation far above the edge that would admit the same share the RVOL floor
admits, 0.007036 and 0.000703 against 0.00034. So they are not names the
evidence rejects; they are names the screen has no way to measure.

The score survives where membership does not, and that asymmetry is the whole
finding. Of the 16 refused rows, 14 are paid the same points by rotation under
the current edges, 2 are paid less, and none is paid more.

**So the change is floor, rotation edges, AND a rotation path on the day
screen, or the day watchlist shrinks for a reason no reader could see.** The
day screen edge is in the sweep output. Nothing here is a recommendation and no
value moved: this is the study the paragraph above says is owed, and what it
found is that the change is bigger than the paragraph thought. Until then the number stays and the report says when
a published ratio rests on a thin denominator, which is what
thin_baseline_premarket_volume above is for. 10,000 is where the table stops
improving: the bands below it run 15 to 30 percent and the bands above it run
5 to 15.

Disclosure was chosen over a cap for the reason the paragraph above gives
about caps, and over a refusal because a refusal is the two part change. It
costs nothing and hides nothing: the ratio is still published, still screened
on, still scored, and the reader is told what it rests on.

## Float rotation

Premarket volume divided by shares float, the second of the two volume
measures. Its whole reason for existing is that it needs no history: RVOL is
null on a name's first appearance because there is no cached baseline, and a
null RVOL used to make the entire score null. Float rotation is computable from
the first minute a name trades, so the two are scored as alternatives filling
one slot. See [Score premarket float rotation] for the bands and DECISIONS.md
2026-08-16 for how they were set.

The numerator is the collector's premarket volume, the same field RVOL uses,
so the same lower bound applies: the collector starts at 07:20 and the true
premarket opens at 04:00, so the rotation understates the full session. It can
therefore withhold a candidate from a band, never smuggle one into it.

The denominator is sharesFloat from us-quote-delayed, the same response the
scan already reads marketCap from, so this costs no extra call.

min_shares_float              = 500000     # absolute floor, used when shares outstanding is unavailable
min_float_to_shares_outstanding = 0.01     # a float below this share of outstanding is a vendor artifact, not a real free float
max_float_to_shares_outstanding = 1.01     # a float above outstanding is impossible; the 1 percent allowance is for rounding between the two fields

### The float floor note

Unlike the RVOL denominator floor above, these are measured rather than seeded.
Across the 1,785 addressable gappers carrying a float on 2026-08-16: the
smallest was 51,810 shares and the median 89,831,112, and exactly one name sat
below one percent of its own shares outstanding (YPF at 0.013 percent, which is
a vendor error rather than a small float). The next lowest was VG at 2.169
percent, so the one percent line falls in an empty stretch of the distribution,
which is where a threshold should sit. No name had a float above its shares
outstanding, so max_float_to_shares_outstanding caught nothing on the day it
was written and exists for the impossible value rather than the observed one.

The degeneracy that forced the RVOL floor does not arise here. A baseline
median can be ten shares; a float cannot, because a company with ten tradeable
shares is not in the universe.

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

## Truth

The nightly pass that measures what premarket volume ACTUALLY was, from
Alpaca's full SIP tape, once the session is over. It writes beside the
morning's numbers and never over them, on the [Backfill] precedent.

**Why this exists.** The morning divides the collector's socket volume by
[Collector] premarket_capture_rate, one number, 0.1172. The socket's real
share of the consolidated tape was measured at 2.1 to 12.1 percent over the
2026-08-19 probe window: a six fold spread. A single divisor cannot correct a
quantity that varies six fold. See DECISIONS.md 2026-08-21 on the record.

[corrected 2026-09-01: this went on to say the error is not random, that
"Thin names capture least and are therefore understated most, and thin names
are exactly the population premarket float rotation exists to rescue, so the
correction reinstates at a lower layer the bias the float rotation fallback
was built to remove". THE RECORD SAYS THE OPPOSITE, and it is the record this
section exists to accumulate. Over the 46 guarded rows in
data/research/capture_rate_study-2026-09-01.json, terciles of the morning's own
avg_volume_20d give a median capture share of 0.178 for the thinnest band,
0.087 for the middle and 0.084 for the thickest, with Spearman rho of share
against average volume at -0.405 over 46 rows and 6 sessions. Thin names
capture MORE than twice what the thickest band captures.

The spread is real and the DIRECTION was assumed. Both halves matter: a single
divisor still cannot correct a quantity that varies six fold, and the sign of
what it gets wrong is the reverse of what was written down. If it holds, the
single number understates thin names LESS than liquid ones, and the bias the
float rotation fallback was said to reinstate points the other way. Six
sessions is below [Truth] baseline_sessions and this is not yet a finding to
act on; it is a claim that was never measured and is now contradicted, which
is a different thing from a claim that is merely old. Re-ask it with
research/sweep_capture_rate.py, which costs nothing.]

**Alpaca, not EODHD, and only after the close.** The free plan serves the sip
feed for a session that is OVER and refuses it with HTTP 403 for one that is
running, measured in doc/ALPACA_PROBE.md section 1 and its 2026-08-20
correction. That is the whole reason this is a nightly pass and not a morning
one, and it is why the morning still ships an estimate.

**The numerator and the denominator come from the same tape.** pm_rvol_true
divides an Alpaca window by an Alpaca baseline over the same window. Dividing
an Alpaca numerator by the EODHD intraday baseline the morning uses would
repeat the defect this whole section is correcting, one vendor down. Both are
meant to be consolidated; this project has been wrong about "meant to be"
several times, so the two sides are held to one source rather than to an
intention.

source                        = alpaca     # the vendor, named so a reader never assumes _true means one thing everywhere. [Backfill]'s pm_high_true comes from EODHD intraday and this does not
feed                          = sip        # the full consolidated tape. iex returned 0 bars and 0 shares over the same premarket window while sip returned 1,410,664, measured in ALPACA_PROBE.md section 1
documented_lag_minutes        = 15         # MINUTES. The vendor's DOCUMENTED delay on the free tier sip feed. NOT a threshold anything screens on and not a measurement: it is the vendor's claim, and research/probe_alpaca_live.py exists to find out whether it holds. It is here rather than as a literal in that file because the probe now SUBTRACTS it from the wall clock to build a window the free tier can serve, so the number it subtracts and the number it prints the observed lag against have to be the same one. Until 2026-08-22 it was a literal and the window ended at the wall clock itself, which is inside the delay, so all 46 requests of the 2026-08-17 run were refused and the probe could never test this key at all. See DECISIONS.md 2026-08-22
baseline_sessions             = 20         # prior sessions the true baseline median is taken over. Matches [Backfill] gap_report_sessions and [Baseline] sessions so the three windows can be read against each other
min_true_bars                 = 1          # bars inside the window before a true volume is recorded at all. A window with no bars is null with a reason, never zero
symbols_per_request           = 100        # MEASURED: batch 100 returned 200 with a 444 character symbol list, ALPACA_PROBE.md section 3. Larger batches also worked and a morning's picks is about twelve names, so this is never the binding constraint
max_pages_per_request         = 20         # pages of 10,000 bars before the fetch is called incomplete and refused rather than silently truncated
max_calendar_days_back        = 40         # DERIVED: baseline_sessions of 20 trading days spans 28 calendar days at five a week, and the worst holiday stretch on this calendar adds two. 40 leaves a full week of margin and bounds the walk when a symbol simply has no history
fill_band_pct                 = 0.005      # SEED. Half width of the band around entry_ref_true that fill plausibility is measured in, as a fraction. See the fill plausibility note below
min_fill_band_notional        = 250000     # SEED, DOLLARS not shares. Band notional below this makes fill_plausible read 'implausible'. See the fill plausibility note below

### The fill plausibility note

A reference level is not a price anyone could have transacted at. On a name
whose entire premarket is a few hundred shares, entry_ref is a print rather
than a market, and every excursion in [Outcomes] measured from it is arithmetic
about a price that was never available. Nothing asked this question before
2026-08-29.

**The three counts, and where each already lived.** Two of them did.

  total premarket volume   pm_volume_true, from the same pass
  distinct minutes traded  true_bars. Alpaca publishes a one minute bar only
                           for a minute that carried a trade, so the bar count
                           IS the minute count
  volume near the level    fill_band_volume, which is new

**A minute counts when its range reaches the band**, high at or above the band
floor and low at or below its ceiling. The MINUTE COUNT IS THEN EXACT: that
many minutes traded somewhere inside the band.

**The volume is an UPPER BOUND and is not volume at the level.** A one minute
bar carries o, h, l, c and v and no distribution, so a minute that ran from
well below up into the band contributes all of its volume while only some of it
transacted inside. Stated as a bound rather than corrected, the way premarket
RVOL is, because correcting it needs trade level data this plan does not buy.

**Dollars, not shares.** fill_band_notional is fill_band_volume times the
level. The table holds prices from 5.64 to 1,585: ten thousand shares is 56,000
dollars of TIGR and 9,400,000 of MU, and one share floor cannot mean the same
thing at both ends.

**fill_plausible is three state and never a boolean:** 'plausible',
'implausible', 'unknown'. A boolean has no room for the third, and the third is
the one that matters, because a row the feed could not reach would otherwise
read as one that was checked and failed. Those are opposite facts. Every row
carries fill_plausible_reason with the numbers behind whichever verdict it got,
and fill_band_pct so a row says which band it was judged under rather than
inheriting whatever this file says today.

**Two rejected alternatives, both tried on the 2026-08-29 calibration.**

Counting a minute by its own volume weighted price rather than its range. It
measures the wrong thing: entry_ref is a session HIGH, an extreme no whole
minute averages near, so a wide ranging name scored near zero however much it
traded. BABA on 2026-08-20 has 2,986,339 premarket shares over 268 minutes and
came back with a band volume of 0. It called the most liquid names in the table
the least fillable.

Requiring a minute count as well as a notional. MSTR on 2026-08-20 traded
49,768 shares inside the band in a SINGLE minute, and KSS, TIGR, BBY and PLAB
are the same shape. Half a million dollars at the level in one minute is a
market, and a rule that called it a print because it lasted one bar would be
measuring duration. The minute count is recorded and reported, and it does not
gate.

**MEASURED 2026-08-29**, over the 54 live rows across the six sessions whose
packets carry an rvol_cutoff_hhmm. The sample unit is the session, so this is
six observations.

  band width   median band volume   median band minutes   median share of the
                                                          whole premarket
    0.10%             14,212                  1                  2.40%
    0.25%             25,108                  3                  3.59%
    0.50%             41,146                  7                  6.71%
    1.00%             79,768                 20                 15.29%
    2.00%            201,570                 81                 46.72%

0.005 is the band. 0.001 is too tight to separate anything: the median row has
one minute in it, which is the bar that made the high and nothing else. 0.02 is
too wide to mean anything: it holds 46.72 percent of the whole premarket at the
median and 100 percent at the p90, so it stops being a band and becomes the
session. 0.005 sits where the band is a small slice, 6.71 percent at the
median, and still separates: it is also a realistic slippage tolerance for a
breakout entry, which is what the level is for.

  band notional at 0.005, dollars    min 7,085   p10 111,033   p25 310,123
                                     median 1,967,202   p75 16,538,588
                                     p90 76,028,180   max 894,263,874

250,000 is the floor and it is a SEED. Five orders of magnitude separate the
thinnest row from the thickest, so no percentile of this distribution is a
natural cut. What picks the number is that it flags 10 rows of 54, and those
ten read as genuinely thin on inspection: eight of them had under 7,000 shares
in the band and three had the level touched in a single minute. Below the floor
the distribution falls away fast, p25 being 310,123 and p10 being 111,033.

  at    25,000    1 of 54 implausible   CSIQ
  at    50,000    3 of 54               CSIQ, DQ, SCSC
  at   100,000    5 of 54               + HMY, MNSO
  at   250,000   10 of 54               + AAP, BLSH, BWLP, CHA, TIGR
  at   500,000   16 of 54               + DLTR, DY, NSSC, PLAB, WOLF, WSM
  at 1,000,000   23 of 54

THE RIGHT FORM OF THIS THRESHOLD IS NOT A CONSTANT. It should be the intended
position size divided by the largest share of the band a fill may be, because
what makes a fill implausible is being too much of the volume at the level, and
that is a statement about an order rather than about a name. No rule in this
file names a position size yet. When one does, this becomes
size / max_participation and the constant goes, and 250,000 is a placeholder
that behaves like the right rule for an order of about 10,000 dollars at a
4 percent participation cap.

### The reference level note

The same pass measures the REFERENCE LEVELS, off the same bars, for the same
reason it measures the volume.

entry_ref and stop_ref are [Picks] entry_ref_field and stop_ref_field, which
are pm_high and pm_low, which are the collector's raw live levels: the extremes
of a socket sample over a window that starts at [Collector] start_time. A
sample understates a maximum and overstates a minimum, so entry_ref sits below
the true premarket high and stop_ref sits above the true premarket low, and
every excursion in [Outcomes] is measured from a level that is off by an amount
nobody had measured.

THE TWO BIASES DO NOT POINT THE SAME WAY, and the easy mistake here is to say
they do. mfe_pct measures UP from entry_ref, so too low an entry_ref makes the
favourable excursion look bigger. mae_pct measures DOWN from stop_ref, so too
high a stop_ref makes the adverse excursion look deeper. The record flatters
its upside and overstates its downside at once. Whether they cancel, and by how
much, is a measurement rather than an argument, and it is below.

entry_ref_true and stop_ref_true are the same two references over the same
window off the whole tape. Beside, never over: the sampled pair is what the
morning had and the gap between the pairs IS the measurement, so a corrected
column with the original discarded could not state it. The FIELD NAMES are read
from [Picks] rather than assumed, so a pair hard coded to high and low cannot
go on being written under a name it no longer has.

entry_ref_collector_window and stop_ref_collector_window are the same two
levels over the socket's OWN minutes, and they exist for the reason
capture_observed sits beside collector_window_share. There are two shortfalls
here with two different fixes, and one column cannot carry both:

  sampling   collector window against the live level. The socket missing
             trades inside minutes it was listening to. A FEED question.
  late start full window against the collector window. The socket not
             listening from 04:00. A START TIME question.

MEASURED 2026-08-29, over the 54 live rows of the six sessions whose packets
carry an rvol_cutoff_hhmm. 2026-08-21 is refused because its packet does not,
and a guessed window would mismeasure exactly the session that went wrong. Six
sessions, and the sample unit is the session, so this is six observations and
not fifty-four.

  entry_ref gap    p10 +0.046%  p25 +0.391%  MEDIAN +1.189%  p75 +4.076%
                   p90 +8.328%  max +20.936%
  stop_ref gap     p10 -4.922%  p25 -3.317%  MEDIAN -1.732%  p75 -0.370%
                   p90 +0.000%  max +0.065%
  of which sampling    median +0.095%  p90 +0.822%  max  +3.480%
  of which late start  median +0.984%  p90 +7.930%  max +20.373%

THE SAMPLING IS NOT WHERE THE BIAS IS. Ten to one, on the median, in favour of
the late start. The socket reproduces the extremes of the minutes it hears
almost exactly, and nearly the whole reference gap comes from 04:00 to 07:20
being unheard. That is the opposite of what this file assumed when the columns
were specified, and it points any fix at [Collector] start_time rather than at
the feed. It is NOT acted on here; see BUILD_PLAN.md for what a 04:00 start
would cost in socket hours and quota.

Neither sampled column is corrected and neither is deleted.

### The true window note

The window is 04:00 to THE SAME CLOCK CUTOFF THE MORNING USED, which the scan
records in the packet as rvol_cutoff_hhmm and which this pass copies onto every
row it writes as true_window. Not market open, and not a fixed 08:45.

A truth measured over a wider window than the estimate would make every
capture_observed too small by whatever the extra minutes carried, and that
error would look exactly like the socket missing more of the tape. The morning
cutoff snaps to [Scan] run_time only inside rvol_cutoff_snap_minutes, so on a
rerun it is a different clock, and a fixed window would silently mismeasure
precisely the sessions that went wrong.

If the packet for a session is unreadable the row is left null with the reason
recorded. Guessing the window is the one thing this pass must not do.

### The two ratios this writes note

capture_observed = pm_volume / true_volume_socket_window. What the socket
ACTUALLY carried of the consolidated tape over THE MINUTES IT WAS LISTENING TO,
per symbol per session. This is the quantity [Collector] premarket_capture_rate
asserts as 0.1172 for every name, and after baseline_sessions of it that key can
be re-derived per symbol, re-derived as a distribution, or discarded on evidence.

[corrected 2026-08-22: this said "pm_volume / pm_volume_true", which is not what
true_volume.py computes and is not what should be computed. pm_volume_true
covers 04:00 to the cutoff and the socket cannot see 04:00 to 07:20 at all, so
dividing by it folds the collector's late start into a number meant to measure
the FEED, and the two have different fixes. store.py's column comment has said
so since the columns shipped and this file disagreed with it. The number this
line tells a reader to re-derive premarket_capture_rate from was therefore the
wrong one, and it is the correction the whole day screen's volume floor rests
on. collector_window_share is the other half, true_volume_socket_window over
pm_volume_true, and is the measurement of the late start.]

estimate_error = pm_volume_estimated / pm_volume_true. How well the MORNING'S
correction did, where 1.0 is exactly right, above 1.0 overstated and below 1.0
understated. It is a different question from the first and it is the one that
says whether the shipped screen admitted the right names.

Both are recorded because they answer different questions and neither can be
derived from the other without pm_volume, which is why that column is now
written to picks as well. The morning's own estimate is never overwritten: a
row carries what was known at 08:45 and what was true that night, side by side,
and which one a query used is then visible rather than assumed.

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

max_adjustment_drift_pct      = 0.1        # SEED, not measured. See the price units note below.
horizon_sessions_short        = 1
horizon_sessions_long         = 5

### The measured excursion note

mfe_pct_true and mae_pct_true are the same two subtractions against
entry_ref_true and stop_ref_true, the reference levels [Truth] measures off the
full SIP tape rather than the ones the collector sampled. See the reference
level note there for why the sampled pair is biased and in which direction.

Filled by night/fill_outcomes.py in a pass of its OWN, not as a branch of the
end of day fill. It needs no vendor call, so it must not sit behind a query
that exists to ration requests, and that query selects on next_day_close being
null, so a row whose short leg filled before these columns existed would never
be re-selected and never measured. Every such row was in the table on the day
they were added.

NO FALLBACK TO THE SAMPLED PAIR. A row [Truth] could not reach keeps null true
excursions and refs_true_reason on the same row says why. Substituting
entry_ref would put the number this column exists to be compared against into
the column doing the comparing, and the gap would read as zero on exactly the
rows where it is unknown.

MEASURED 2026-08-29, over the 48 live rows across 5 sessions that carry both
an outcome and a measured reference. The sample unit is the session.

                     median sampled   median measured   median row difference
  favourable            +0.8132%          -2.1271%           -1.2336 points
  adverse               -1.9243%          +0.1465%           +1.7354 points

  reached entry_ref     sampled 29 of 48    measured 20 of 48
  undercut stop_ref     sampled 30 of 48    measured 22 of 48

BOTH MEDIANS CHANGE SIGN. On the sampled levels the median pick ran past its
entry reference and broke its stop reference. On the measured levels it did
neither: the median name never reached the true premarket high and never
undercut the true premarket low. That is not a small correction to a result, it
is the reverse of one, and it is the reason nothing in this file is calibrated
against mfe_pct.

Five sessions is five observations. This is a measurement of a bias in the
record, not a result about the screen, and it names no threshold.

### The price units note

The outcome fill measures mfe_pct, mae_pct and pm_high_broke_next_day by
subtracting entry_ref, stop_ref and pm_high, the collector's raw live premarket
levels from the pick date, from the high and low of the next session's end of
day bar. A split, reverse split or spinoff whose ex date falls on that session
leaves the two sides in different price units under either vendor adjustment
convention, because retro-adjustment rewrites only the bars dated BEFORE the ex
date and the next session's bar is post event either way. A 4-for-1 forward
split writes both excursions near -75 percent with pm_high_broke_next_day 0,
and a 1-for-10 reverse split near +900 percent, unflagged and indistinguishable
from a real excursion, into the table this file says its thresholds will one day
be recalibrated against. The screen's price floor is only "> 3", so a reverse
split candidate is not an exotic case.

The vendor's own record answers it. close divided by adjusted_close is flat
between corporate actions and steps at each one, so that ratio moving between
the pick date and the next session says an action has its ex date in between.
Past this many percent the row is refused with the reason recorded, the way the
module already refuses a pick the session calendar cannot date, rather than
rescaled: entry_ref, stop_ref and pm_high are raw collector levels with no
adjusted counterpart, and a rescaled excursion would be a computed number in a
table meant to hold measured ones.

0.1 percent is a seed fitted to nothing. It sits above the rounding noise of two
four decimal vendor prices, which is a few hundredths of a percent on the
smallest name the screen admits, and below any corporate action. An ordinary
dividend ex date also moves the ratio and is also refused, which costs roughly
one row in sixty for a dividend paying name and is the safe direction: a
dividend drop is a mechanical adjustment rather than the market moving against a
reference level. The header of this file applies.

## Scan

The 08:45 gathering pass that writes packet.json.

candidate_count               = 12         # top N by the absolute gap measured from the collector against the pool's prior close
news_lookback_hours           = 24
news_keep                     = 3
economic_country              = US
economic_days_ahead           = 1          # today plus this many days
earnings_days_ahead           = 1
run_time                      = 08:45
rvol_cutoff_snap_minutes      = 10         # see the cutoff snap note below
min_bars_for_full_window      = 10         # seed: below this many collected minutes the premarket window is called THIN, not merely partial. See the thin window note
prior_close_disagreement_pct  = 0.5        # seed: percent between the two vendor prior closes above which the packet says so. See the two prior closes note

### The thin window note

pm_window_starts_late already says a window opened after the collector's
start_time. It says nothing about how much of the window then carried trades,
and those are different facts that were reaching the reader as one word.

2026-08-20 is the case. SCSC's entire premarket record that morning was FOUR
one minute bars holding 1,487 shares, and its 16.34 percent gap, its 56.78
VWAP and its 59.82 high all rested on them. AAP's window also opened late and
carried fifty bars. Both were described as "partial", which is true of both
and useful about neither.

So a window is now THIN as well as late when it holds fewer than
min_bars_for_full_window minutes with prints. The two flags are independent on
purpose: a window can open on time and still be thin, which is a silent socket
rather than a late one, and the fixes differ.

10 of a roughly 85 minute window is a seed fitted to nothing. It is set where
it is because four bars is plainly not a price path and fifty plainly is, and
somewhere in between is a line nobody has measured. The header of this file
applies.

### The two prior closes note

Two vendor endpoints carry a prior close and they do not always agree. The end
of day record is authoritative here and attach_daily_history has read it from
one OHLC bar since 2026-08-14, for the reason that function's docstring gives.
The delayed quote carries previousClosePrice as well, and the packet holds both
without ever comparing them.

On 2026-08-20 they disagreed for SCSC by 1.67 percent, 51.42 against 52.2909.
The gap was measured from the first and published as 16.34 percent; from the
second it is 14.4. Every other candidate agreed to within rounding except BLSH
at 0.15 percent. Neither number was wrong and nothing said they differed.

So the disagreement is now recorded as a magnitude, the way
pm_source_disagreement already is for the premarket high, and gapped above
prior_close_disagreement_pct. The end of day record still wins: this is a
disclosure, not a tiebreak, and a packet that quietly switched sources on a
disagreement would be harder to explain than one that reports it.

0.5 percent is a seed. It sits above the rounding noise the other eleven
candidates showed that morning and below the one real disagreement.

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

## Midday

The 12:00 pass. It answers two questions the morning cannot: what the morning's
own picks did once the session opened, and what else moved that the morning
never named. Live from 2026-08-31. Every number below is a SEED.

**What it may read, and why the list is this short.** EODHD does not publish
today's intraday bars until overnight, measured 2026-08-31 and written up in
DECISIONS: today's completed session returned zero 1m rows two hours after the
close while the three sessions before it returned full days. So the endpoint
the night measures the morning with is unavailable to this pass at any hour of
the trading day. us-quote-delayed is what is left, and during REGULAR HOURS it
carries today's open, high, low, lastTradePrice and volume, with
lastTradeTime measured 2026-08-17 at 09:56:12 against a 09:57 fetch. Its
extended hours fields are NOT read here: they were stale at 08:45 on the same
morning they were needed, and this pass has no use for them. Neither is its
previousClosePrice, for the reason the denominator note gives, and that is the
most important line in this section.

run_time                      = 12:00      # ET. Deliberately well inside regular hours: the delayed quote's REGULAR hours behaviour is what was measured, and its premarket behaviour is untested
max_quote_age_seconds         = 1800       # SEED. lastTradeTime older than this against the run clock makes the row's prices null with a reason, never carried
require_prior_session_close   = true       # a symbol the prior session's bulk close payload does not carry is REFUSED and left unmeasured, never measured against the quote's own previousClosePrice. See the denominator note
open_tolerance_pct            = 0.5        # SEED, PERCENT. A carry through verdict decided by a smaller margin between the open and the entry is flagged, because the quote's open is the first consolidated print and not the opening auction. See the open note

### The carry through note

This grades every live picks row for today against THE LEVELS THE MORNING
PUBLISHED, entry_ref and stop_ref, and never against entry_ref_true or
stop_ref_true. Those do not exist until the night's truth pass writes them, so
the choice is between the morning's levels and no answer at all.

The consequence has to be stated wherever this is read: the night ledger books
the same trade against the corrected levels and WILL sometimes reach a
different verdict. That is not a defect in either pass. It is two measurements
of one question against two reference prices, and the midday pass is the one
built on numbers a reader actually saw at 08:45.

Nothing here is ever written to paper_trades. That table is the night's, it is
keyed on a rule version, and a second writer booking against uncorrected levels
would destroy exactly the comparison it exists for. The midday verdict lives in
its own packet and nowhere else.

**The rule, which is [Paper]'s rule run against what a daily quote can say.**

  NEVER TRIGGERED   high < entry_ref. No position, and the session low is NOT
                    read: a low with no trade under it stops nothing. This is
                    the case the first prototype got wrong on 2026-08-31, which
                    is why it is written down first.
  GAPPED THROUGH    open >= entry_ref. Fill is the open, exactly as [Paper]
                    fills a gap through at the open. The fill is the session's
                    FIRST print, so a low reaching stop_ref after it is
                    unambiguously a stop out and is booked as one. Order is
                    knowable here and only here.
  TRIGGERED         open < entry_ref <= high. Fill is entry_ref. Whether the
                    session low came before or after that fill is UNKNOWABLE
                    from a daily high and low, so a low at or under stop_ref is
                    reported as stop level reached with the sequence unknown,
                    and NEVER as a stop out. A quote carries no sequence and
                    this pass will not invent one.
  UNKNOWN           any level the quote did not carry. Null with a reason.

The third case is the whole argument for extending [Collector] stop_time past
the open: minute bars with timestamps turn it into the second case's certainty.
Until that is measured and shipped, the count of rows landing in it is reported
on every edition, because a pass that is silent about how often it cannot
answer reads exactly like a pass that always can.

**What it does not check.** [Paper]'s SKIP condition, fill_plausible, is
computed by the night from Alpaca band volume and does not exist at 12:00. So
this pass grades levels without asking whether they were transactable, and says
so. A midday verdict on an illiquid level is arithmetic, not a trade.

### The mover scan note

The second half, and it is a different question from [Notable]. That section
ranks the previous COMPLETED session's moves out of a file already on disk and
costs nothing. This ranks TODAY'S move, mid session, and costs one credit per
universe name because there is no cheaper honest way to ask.

**Why the whole universe and not a news feed.** The affordable design pulls the
global news feed since 08:45 and quotes only the names carrying a headline.
That answers which names had news and also moved, which is not the question: a
name that moved on no tagged headline would be invisible and the report would
have no way to say it was blind. The owner chose the sweep on 2026-08-31 with
the price stated. Selection is on PRICE, and news is fetched afterwards to
explain what price already found, never to decide membership.

**The bill.** One credit per symbol against a 2,751 name universe, priced by
[Quota costs] us-quote-delayed-per-symbol, so about 2,751 credits a session
against a shared 100,000 a day. The preflight is sized to the sweep and refuses
rather than truncating: half a universe is not a market wide scan and must not
be published as one.

min_move_pct                  = >= 5       # SEED. abs lastTradePrice against previousClosePrice, percent. Not a gap: this is the whole session's move so far
min_day_rvol                  = >= 3       # SEED. today's volume against averageVolume. Without it the list fills with high beta names doing what they always do
min_price                     = >= 3       # dollars, lastTradePrice. Matches [Universe] so the scan cannot admit what the population already excluded
list_size                     = 15         # how many ranked movers reach the report
news_lookups                  = 10         # how many of those get a news call, 5 credits each by [Quota costs], trivial against the sweep that found them
headlines_per_mover           = 3          # how many of a mover's stories are RENDERED. The packet keeps every one the lookup returned; this only bounds what a reader is asked to read, and the feed tags generic market roundups to most large movers
rank_by                       = move       # move or rvol. Which of the two floors above orders the list once both are cleared

### The denominator note

Every move this pass reports divides by the prior session's close. That close
comes from eod-bulk-last-day for an EXPLICITLY NAMED date, one call, 100
credits, the whole exchange. It is NOT the quote's own previousClosePrice, and
the first draft of this section said it was, which is the mistake this note now
exists to prevent anyone repeating.

**What previousClosePrice actually is, measured 2026-08-31.** Not one quantity.
Across the 2,391 universe names carrying both, it equalled the PRIOR session's
close for about 34 percent and TODAY'S close for about 29 percent, and nothing
in the payload says which a given row holds. SAIC.US matched neither: 125.74
against a 125.96 close on 2026-08-28 and a 128.22 close on 2026-08-31. A
further 359 names carried no previousClosePrice at all while carrying a
previousCloseDate, an open, a high, a low, a last and a volume.

**And previousCloseDate does not save it.** Every one of those 359 rows carried
a correct date. The field was RIGHT on rows whose price was wrong, so it is
evidence about the vendor and not a check on anything. It is recorded in the
packet and nothing branches on it. A vintage stamp that does not travel with
the number it stamps is worse than none, because it invites exactly the trust
the first draft of this section placed in it.

**Why the bulk day is safe where the quote is not.** The request NAMES a
session, so there is no roll time to be on the wrong side of. Verified
2026-08-31 against the single symbol eod endpoint that fill_outcomes and the
morning already trust: the two agreed exactly on every name checked while the
quote disagreed with both. It also covers all 359 the quote declined, because
it is keyed on the exchange rather than on a symbol list.

This is the 2026-08-14 defect wearing new clothes. That one published a report
priced off the last completed session from an endpoint whose name said live.
The lesson then was that a field's name is not its contract, and the lesson
holds for a field called previous which is sometimes current.

The prior trading session comes from the session calendar, never from weekday
arithmetic, for the reason [Outcomes] gives: a Monday holiday makes the prior
session Thursday and weekday math would compare against a day nobody traded.

### The open note

The carry through rule turns on whether the session open cleared entry_ref, and
us-quote-delayed's open is the FIRST CONSOLIDATED PRINT, not the opening
auction price. Measured 2026-08-31 across 2,750 names against
eod-bulk-last-day: it agreed for about 70 percent, and for the rest it differed
by a median 0.34 percent, worst among the least liquid, up to 5.8 percent on
MLR.US. SAIC.US and MNSO.US, the two names that mattered that day, agreed
exactly.

So the open is USED, because it is the only open available inside the session,
and a verdict decided by a margin smaller than open_tolerance_pct is FLAGGED
rather than presented as settled. A row that would read gapped through against
one open and triggered against the other is a row a reader should be told
about, not one to be quietly rounded into whichever state the arithmetic
reached first.

### Why this pass has no narrative

The morning runs the analyst because what should I make of this is an open
question. Midday asks closed ones: a pick triggered or it did not, a name moved
or it did not. Both are arithmetic on numbers already in the packet, so the
report is RENDERED, not written. No claude CLI call, no containment check, no
quantifier guard, because there is no prose for any of them to police.

## Traps

A gap up contradicted by the news underneath it. Decided in scan.py and
narrated by the report, never judged by the model.

negative_polarity             = -0.35      # seed: at or below this a headline counts as negative
positive_polarity             = 0.35       # seed: at or above this a headline counts as positive
min_headlines_for_balance     = 2          # below this there is no balance to read and trap is NULL
min_gap_pct                   = 3          # seed: a gap smaller than this is not the kind of move a trap describes

### The balance note

Until 2026-08-20 there was no rule here at all. REPORT_TEMPLATE.md told the
model "a positive gap on headlines whose sentiment is negative is a trap and is
said plainly", and the model read the WORST SINGLE headline. That is the wrong
reduction and 2026-08-20 is the case that proves it. MSTR was published as a
trap on "Bitcoin tops $71K as crypto rally gains momentum", which the vendor
scored -0.914; its other two headlines that morning scored +0.963 and +0.833.
FUTU was published as a trap on "Here are the major earnings before the open
Thursday", scored -0.422, against +0.836 and +0.691. Both calls were vendor
scoring errors on text that is plainly positive or plainly neutral, and both
reached the reader as statements about the market.

So the rule reads the BALANCE: a trap needs strictly more negative headlines
than positive ones among those the vendor scored. One mis-scored headline
inside a positive set can no longer carry a call on its own, which is the
specific failure above, and a name whose coverage really is negative still
trips it. Neither threshold is symmetric by accident: they are the same
magnitude because nothing yet justifies treating a -0.35 as different evidence
from a +0.35.

min_headlines_for_balance exists because two is the smallest set where "more
negative than positive" says anything. On a single headline the balance IS the
worst single headline, which is the failure being fixed, so trap is NULL there
with the reason recorded rather than decided on one item.

The vendor's polarity is the only sentiment source on this plan and it is
demonstrably unreliable at the item level. That is the argument for reading it
in aggregate and for the packet carrying the counts it was decided on, so a
reader can see the evidence rather than take the verdict. The magnitudes are
seed values fitted to nothing, and the header of this file applies.

## Analyst

The narrative pass. The claude CLI is invoked as a subprocess and
authenticates through the logged in subscription, never an API key. The model
narrates numbers already decided in Python, so these are operational knobs
like the Api section above, not screen criteria.

model                         = opus       # owner's standing choice, re-asserted 2026-08-13 evening
effort                        = medium     # compared against low on the 2026-08-13 packet (2026-08-14): medium covered all 12 candidates individually in Technical signals where low compressed six into one vague sentence, and its traps section gave actionable per-name instructions; ~25s slower, worth it. Default (high) effort remains measured at ~340s, not affordable.
timeout_s                     = 1007       # 3x the slowest morning on record, 335.7s on 2026-08-27. See the timeout note below.
                                           # [corrected 2026-08-29: was 537, itself 3x the 178.9s of 2026-08-19 when it was
                                           # set on 2026-08-20. Four scheduled mornings overtook that and the multiple had
                                           # decayed to 1.6, which the 2026-08-28 pass recorded and declined to act on
                                           # because the number does not travel alone. It travels with [monitor]
                                           # job_log_stale_after_s, which moved with it. The RULE is unchanged throughout;
                                           # only its evidence moved. See DECISIONS.md 2026-08-29.]
                                           # [corrected 2026-08-20: was 293, "3x the slowest of five measured opus
                                           # medium runs on 2026-08-14: 97.4, 86.5, 97.7, 91.1, 92.4 seconds". The
                                           # rule did not change, the evidence under it did.]
max_attempts                  = 2          # total CLI runs the narrative may spend in one morning, including the first, counting retries on a CLI failure AND the quantifier regeneration together. Enforced by analyst.RunBudget since 2026-09-02; before that each of the two calls retried this many times on its own, four runs at worst, and the arithmetic below never allowed for it. The gap explanation pass is a separate, short call and is outside this count.
quantifier_regenerations      = 1          # flagged narratives thrown away and asked for again before the plain table takes over
quantifier_guard              = enforcing  # warn: log and print flags, deliver the narrative anyway. enforcing: regenerate, then fall back. See the note below for the three things that had to be true, and were, on 2026-08-28.
                                           # [corrected 2026-08-28: was warn, from 2026-08-18. The three conditions below
                                           # are met. Flipping does not widen the clock budget: the worst case was already
                                           # computed at two CLI runs, 09:03:13, in the timeout note above.]
prose_token_stopwords         = ET, EST, EDT, UTC, GMT, AM, PM, US, USA, Q1, Q2, Q3, Q4, YOY, QOQ, EPS, ARR, GAAP, IPO, CEO, CFO, COO, CTO, FDA, SEC, FOMC, GDP, CPI, PPI, PCE, ISM, ADP, ETF, NYSE, USD, EUR, RVOL, VWAP, OHLCV, NOT, AND, THE, ALL, ON, SO, IT, AI, A, I

### The timeout note, and why the number moved

The rule has always been three times the slowest run on record. What changed on
2026-08-20 is that runs on record now means scheduled mornings rather than the
five dry runs of 2026-08-14, which the schedule has overtaken.

| session | analyst step | CLI duration | output tokens |
| --- | ---: | ---: | ---: |
| the five dry runs, 2026-08-14 | - | 86.5 to 97.7 | - |
| 2026-08-14 | - | 89.1 | 7,697 |
| 2026-08-17 | 54.4 | 48.4 | 4,000 |
| 2026-08-18 | 107.5 | 98.5 | 8,954 |
| 2026-08-19 | 185.3 | 178.9 | 16,005 |
| 2026-08-20 | 231.7 | 226.1 | 20,188 |
| 2026-08-24 | 270.8 | 262.8 | 22,936 |
| 2026-08-25 | 252.4 | 246.2 | 21,947 |
| 2026-08-26 | 272.2 | 265.7 | 23,488 |
| 2026-08-27 | 342.6 | 335.7 | 28,633 |
| 2026-08-28 | 213.3 | 206.3 | 18,264 |

[appended 2026-08-28] The five rows above are the scheduled mornings since the
number was set, read from each session's chain log for the step and from its
analyst_usage.json for the CLI duration and the output tokens. 2026-08-21 is
not among them: it produced no narrative and its usage file records no run.

The doubling has stopped. 226.1, 262.8, 246.2, 265.7, 335.7, 206.3 is a plateau
with one high session, not the trend the paragraph below was written against,
and output tokens plateau with it at 18k to 29k. What HAS moved is the slack:
the rule is three times the slowest run on record, the slowest is now 335.7s on
2026-08-27, and three times that is 1,007. 537 is 1.6 times it.

The number was not changed on 2026-08-28, because it does not travel alone, and
this paragraph listed the trade for the owner: a wider timeout, a lower
max_attempts, or an accepted 1.6x.

[resolved 2026-08-29] The owner chose the wider timeout, on the stated ground
that a slower report costs nothing and a report that is CORRECT AND DETAILED is
the whole point. That reading is right and it reverses the direction this note
was drifting in. The timeout is not a speed control: exceeding it does not make
the report late, it KILLS the narrative and hands the morning the deterministic
plain table. So the number being too SMALL is the risk to a detailed report,
and the pressure on it comes from the detail itself, output having grown from
18,264 tokens to 28,633 across the week.

max_attempts stays at 2 and quantifier_regenerations at 1. Lowering either
would have bought the same headroom by removing a retry, which is a smaller
report on a bad morning rather than a later one, and that is the trade the
owner declined.

Nothing has timed out. This is not a fault being fixed, it is a threshold being
kept faithful to the rule that defines it, and the direction is what forces it:
54.4, 107.5, 185.3 is close to a doubling per session, and it tracks output
length rather than the model being slow. One more session on that trend rides
the first attempt past 293, retries, rides the second, and hands the morning the
deterministic plain table for no reason at all. That is exactly the cost the
2026-08-18 regeneration work was built to stop paying.

What the new number costs, arithmetic rather than assertion. The chain starts at
08:45:00. Everything that is not the analyst measured 19.0, 20.6 and 19.1
seconds across the three mornings recorded when this was written, and 22.3 on
2026-08-20 since: the scan step is 13.9 to 20.5 of it and render,
verify, deliver and archive are about two seconds together. So the worst case is
08:45:00 plus 19s plus max_attempts times timeout_s.

  at 293:  two attempts exhaust at 08:55:05, 35 minutes before the open
  at 537:  two attempts exhaust at 09:03:13, 27 minutes before the open
  at 1007: two attempts exhaust at 09:18:53, 11 minutes before the open

All three clear the open, and all three clear the watchdog: [monitor] chain_due
is 09:00 but the watchdog only fires on its half hours, so the 08:55 pass reads
NOT DUE and the next is 09:25, by which time even the worst case has finished.
Nothing downstream of the chain has a deadline between those two numbers.

At 1007 the margin against the 09:25 pass is six minutes rather than
twenty-two, and that is the number to watch if this rises again. The margin
against the OPEN is eleven minutes and is not the binding one: a report that
lands at 09:19 is still a premarket report, where a chain still running at
09:25 is one the watchdog has to reason about.

The output length is the thing actually worth watching. 16,005 output tokens on
2026-08-19 was double the previous high on a template whose nine sections did
not change. Raising the timeout buys room for that trend, it does not explain
it, and a report that keeps doubling is its own question. 2026-08-20 answered
part of it: 231.7 seconds of analyst step and 20,188 output tokens, so the
growth from 185.3 was 25 percent rather than 72 and the doubling did not
continue. The number stays at 537 rather than moving to three times 226.1,
because 231.7 is 43 percent of it and that is room for another session like
this one. One session is not a trend broken, and the rule above is the one to
reapply if the next morning is slower again.

**The premise of every sentence above changed on 2026-08-20.** All four of those
readings were taken against a template of NINE sections. Layer 4 added a tenth,
the notable movers section, on the evening of that day, and it is a table of up
to fifteen rows with nine columns plus seven fixed sentences and one line per
lost leg or short list. The trend the paragraph above is watching therefore has
a step change in it that has nothing to do with the model getting wordier, and
the first reading after 2026-08-21's 08:45 chain is the one to compare, not the
one to be alarmed by. The timeout is not moved on a prediction: 537 leaves 305
seconds of headroom over the last measurement, the section adds text rather than
reasoning, and a number changed before the thing it measures has been measured
is a guess wearing a derivation.

### The prose stopword note

Containment reads ticker claims out of the report's prose as well as its
tables. Prose is ambiguous in a way a Ticker column is not: "06:37 ET" is a
time, and ET is also Energy Transfer, so a naive reader of prose would fail
every report ever written. Time expressions, ISO dates and punctuation joined
abbreviations are stripped before tokens are taken, and this list removes what
survives. The abbreviation pass was added on 2026-08-20, after "S&P 500 futures
are flat" came apart into P and S, which are both real listings, so containment
read two invented tickers and stopped the morning.

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

### The warn mode note, and what has to be true before it flips

quantifier_guard was `warn` from 2026-08-18, the day the regeneration and
fallback were built, until it was armed on 2026-08-28. It reads `enforcing`
now. [corrected 2026-09-01: this said "quantifier_guard is `warn`" in the
present tense, and went on saying it for four days after the flip that the
numbered list below already records. The rest of this section is history and is
left exactly as written, because it was true when it was written; a sentence
stating the CURRENT setting is not history, it is a reading a reader takes at
face value, and this one sent them to the opposite of the value in the block at
the top of this file.] The reason is measured rather than
feared. Running the guard over the three archived reports flags every one of
them: 2026-08-14 twelve times, 2026-08-17 eight times, 2026-08-18 ten times,
with `no` accounting for eighteen of the thirty. Enforcing today would mean the
plain table on most mornings, which is a working guard producing the wrong
outcome daily.

The cause is that the instructions still ASK for the sentences the guard
refuses. REPORT_TEMPLATE.md tells the model to name the candidates whose
pm_rvol is null and whose premarket window starts late, and on a morning with
none to name it writes a sentence about the whole set because that is the only
honest answer to the question it was asked. Those requests are the queued
derivations T2, T3, T15 and T16 and their prompt duplicates P1 and P2.

In warn mode every flag is written to data/quantifier-flags.jsonl with outcome
`warned`, printed with its sentence, and named on the report's disclaimer line
so the reader can judge it on the morning it fired. Nothing is regenerated and
nothing falls back. This is deliberately the more informative half of the
telemetry: a flag log filling under the template that provokes the flags says
which words and which instructions are responsible, where one filling after the
provocation is gone would only say the remainder is quiet.

Three things have to be true before this reads `enforcing`, and on 2026-08-28
all three do. What each one was, and what closed it:

  1. T2, T3, T15, T16, P1 and P2 are resolved, so the instructions no longer
     ask for a claim about the set that the model cannot compute.
     CLOSED. T16 and P2 went on 2026-08-20 with the trap work, which this
     list was never updated to say, so it named two resolved items as
     blockers for eight days. T2, T3, T15 and P1 went on 2026-08-28: the
     packet's evidence_roll carries the five membership lists and a quoted
     sentence for each, and the template and prompt read them instead of
     asking the model to filter. See TEMPLATE_DERIVATIONS.md fourth pass.
  2. A morning runs clean, meaning a real report with zero flags rather than a
     fixture with zero flags.
     CLOSED on 2026-08-19, and five more before the flip: 2026-08-24, 08-25,
     08-26, 08-27 and 08-28. The last flag of any kind was raised on
     2026-08-21.
     [corrected 2026-09-01: this said "seven more since". Five trading
     mornings ran between the last flag and the flip, not seven, and the two
     days between them were a weekend. A count that overstates the evidence
     for the very condition it is the evidence for is the wrong kind of number
     to leave standing.
     Separately, and NOT a correction to the verdict: runs/2026-08-19 was
     deleted on 2026-09-01 along with five other sessions, and the backup
     copies no rendered report, so that morning can no longer be inspected.
     The condition was met on evidence that existed when it was judged. The
     claim is simply no longer checkable, which is a different thing from a
     claim that was never supported, and it should be read as one.]
  3. The flags already logged have dispositions, since the word list was going
     to be tuned on them and flipping the switch first would mean tuning it on
     a sample that stopped growing.
     CLOSED on 2026-08-25. Both flags are judged, and both are false
     positives on the forward only `no`, six words ahead of a set word.

### What flipping this does and does not risk

Stated here rather than left to be rediscovered, because 2 of 2 judged flags
were false positives and that is the number a reader will reach for.

The clock does not move. The worst case under `enforcing` is one flagged
report plus one regeneration, which is two CLI runs, which is the same figure
the timeout note above already computes and accepts for two attempts.
`quantifier_regenerations` is 1, so a third run is not reachable. [corrected
2026-08-29: this read "1,074 seconds ... at 09:03:13", which was the worst case
against a 537 second timeout_s. timeout_s is 1007 and the worst case is 2,014
seconds ending 09:18:53. The ARGUMENT is unchanged, and it is the argument that
matters here: enforcing adds no CLI run that the two attempt budget did not
already allow for.]
[corrected 2026-09-02: the sentence "a third run is not reachable" was not
true of the code. invoke_claude retried max_attempts times on a CLI failure,
and write_report called it once more for the regeneration, which retried
max_attempts times again: a first call that timed out once and then answered
with a flagged report, followed by a regeneration that timed out once and then
answered, is FOUR runs of timeout_s, 4,028 seconds, ending 09:52 on a chain
that started 08:45. Nothing ever took that path. analyst.RunBudget now holds
the morning to max_attempts runs in total across both calls, so the two run
worst case this paragraph computes is what the code enforces rather than what
it hoped. The one trade: a first call that needed both of its runs to get an
answer has no run left for a regeneration, and a flag on that answer goes
straight to the plain table with the disclaimer saying why. The gap
explanation pass is a further short call outside the budget, about twenty
seconds measured, and is not in this arithmetic.]

The cost of a false positive is one regeneration, and the narrative is lost
only when the SECOND answer flags too. A false positive is cheap to clear:
the rejected sentence is appended to the piped document, and both flags on
record are ordinary sentences that reword in a clause.

The flag rate is 2 in 11 scheduled mornings, both of them in the first week,
and 0 in the last seven. Both were the model writing freehand about names
dropped for no coverage and about partial premarket windows, which is
precisely the prose evidence_roll now supplies pre worded and guard clean.
So the population that produced both flags is the one this pass removed.

What is NOT settled: the word list itself. The review scheduled for a month
after 2026-08-18 still stands, `no` and `each` are still the words most
likely to move, and a sample of two is not a rate. Enforcing changes what a
flag costs, not how often the guard is right, and if the plain table starts
appearing on mornings a reader disagrees with, the word list is the thing to
tune and this knob is the thing to put back to `warn` while that happens.

An unrecognised value here is treated as enforcing and says so, because a typo
must not be a silent way to switch the guard off.

### The quantifier regeneration note

The quantifier guard rejects a report that asserts a quantifier over the
candidate set. Until 2026-08-18 that rejection cost the whole morning: the
guard returned exit 2, the chain stops on the first non-zero code, and render,
deliver and archive never ran. No report at all, over one sentence, from a
guard whose own false positive rate is still being measured.

That is the wrong price, and the wrong price is what gets a guard switched off.
So a flag now buys a regeneration first. The rejected sentences are appended to
the piped document, the model writes the report again knowing what to avoid,
and only if the second answer flags too does the morning drop to the plain
table fallback, with the reason and the offending sentence stamped into the
disclaimer line. One regeneration rather than several: a second roll of the
dice that also fails is evidence about the report or the guard, not bad luck,
and each attempt costs another timeout_s of the morning's clock.

The worst a false positive can now do is remove the narrative from one
morning. That is exactly the trade the guard's own asymmetry argument assumed
it was making.

Note on the invocation: the narrative pass is one text generation, not an
agent loop. The CLI runs with --tools "" so there is nothing to loop on, a
one line --system-prompt so the piped document is the entire instruction,
and everything (prompt, template, packet) piped on stdin. num_turns is
recorded in analyst_usage.json and must be 1. The report is produced either
way: on any failure of the CLI call, timeout included, analyst.py renders the
plain table fallback straight from packet.json and the chain carries on to
email. The containment check is the one deliberate exception. An invented
ticker or a missing watchlist table returns exit 2, the chain stops on the
first non-zero code, and nothing is delivered, because a report naming a
company the packet never saw is the failure this whole file is written
against.

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

## Backup

A copy of the four artifacts that cannot be rebuilt, taken by the nightly and
read by nothing. night/backup_evidence.py.

[corrected 2026-09-01: this said TWO and named two, while _ARTIFACTS has copied
four since the collector's two sidecars joined it. This page is the authority
the others were echoing, so the count travelled from here into both architecture
pages, a docstring in morning/scan.py and the module's own headline. Those were
corrected first and this was not, which is backwards.]

**Why only four.** Everything else in this system has a route back. The universe
rebuilds weekly. The closes re-fetch. Reports render from packets. The database
refuses test code through store.guard_live_database. Four things have no route:

  data/premarket/<date>.jsonl   the collector's socket capture, a recording of
                                a tape that no longer exists
  runs/<date>/packet.json       the frozen evidence a morning was judged on
  data/premarket/<date>-stats.jsonl
                                one line per collector run: connections,
                                reconnects, the drops it survived. There is no
                                second copy of a connection that has closed
  data/premarket/<date>-subscriptions.json
                                what the collector asked the socket for, at
                                subscribe time. The stale watchlist note calls
                                this the ONLY evidence of what was listened to,
                                because the watchlist beside it can be rewritten
                                after the socket has already read it

All four live under gitignored directories, and on 2026-08-21 at 15:46 a sweep
that invoked every claim directly wrote fixture data over 29 files, including
258 fixture bars over roughly 3,200 real ones and 762 bytes over a 125 KB
packet. That session is gone, and runs/2026-08-21/packet.json is still that 762
byte stub today: one candidate where picks holds twelve, and `stub` where a
commit belongs. build_archive refuses to present it as a morning. A list that
grows past these four without remaking the argument above is a backup of
everything, which is a weaker promise that nobody checks.

root                          = %LOCALAPPDATA%\PremarketDesk\evidence   # expanded through the environment. OUTSIDE the working tree on purpose: a copy inside the directory that gets deleted is not a copy
catchup_sessions              = 10         # recent sessions checked each night, so a night the machine was off is caught up rather than lost. Ten covers a fortnight of weekdays

### The write once note

A dated backup is NEVER overwritten. When the working copy no longer matches a
backup already held, the run reports a DISAGREEMENT and changes neither file.

That is not caution for its own sake. A stale backup and a corrupted working
copy are the same observation from inside this module, and resolving it either
way automatically destroys the evidence needed to tell them apart. Copying the
working file over the backup would have erased the last good capture on
2026-08-21; copying the backup over the working file would silently discard a
legitimate re-run.

The tripwire is the second reason this exists. Had it been running, the 22:15
pass on 2026-08-21 would have said the morning's capture no longer matched the
copy taken the night before, on the same night rather than by inference from
three failing checks a day later.

### Restoring

    python -m night.backup_evidence --list
    python -m night.backup_evidence --restore YYYY-MM-DD

Restore refuses a working copy that already matches, and refuses one that
DIFFERS unless --force, because overwriting the newer of two disagreeing files
is the mistake this whole section exists to undo. It spends no vendor call: the
capture and the packet are files, and the point of holding them is that neither
can be asked for again.

## Job status

Every scheduled step appends one line to data/job-status.jsonl as it exits,
written in a finally block so a step that dies still records dying. This
exists because pool_recall raised NameError on every nightly run for a week
and nothing said so: its exit code is ignored by design, its main caught the
wrong exception type, and the watchdog then read only each job's final step
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

universe                      = 5          # Sunday 21:00, five sessions old by Friday
                                           # [corrected 2026-08-17: was 20:00, which
                                           # the schedule left on 2026-08-16]
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
prune                         = 1
truth                         = 1
paper                         = 1          # the [Paper] ledger, run in the nightly right after truth because it reads entry_ref_true, stop_ref_true and fill_plausible and every one of those is written by that step
midday                        = 1          # the 12:00 pass, see [Midday]
midday_render                 = 1          # rendered from the packet the step above wrote, no model and no vendor call
weekly                        = 1
backup                        = 1
monitor                       = 1
calendar                      = 1

## Monitor

The watchdog. It runs a few times each weekday, asks Task Scheduler whether
each PremarketDesk job fired and what it returned, reads the job's own dated
log for the final step marker, reads the job-status record every step inside
that job wrote, and reruns what is safe to rerun. Safe means
idempotent: the morning chain and the nightly can always be rerun, the
collector may only be restarted when no collector is alive (two live
collectors would write duplicate minutes), discover is rerun whenever it did
not finish and the collector has not yet written its subscription list, at
any hour, because that file is the only thing a rewritten watchlist could
desync and the clock was only ever a proxy for it, and the universe is
rebuilt on a weekday only when the Sunday build was missed. Each job gets at most
max_reruns_per_job_per_day so a hard failure cannot loop.

discover_due                  = 07:25      # discover plus baseline warm should be done by here
chain_due                     = 09:00      # a healthy chain is done by about 08:52; the worst case runs to 09:18:53, see the [Analyst] timeout note
                                           # [corrected 2026-08-29: the worst case read 09:03 against a 537s timeout_s.
                                           # 09:00 is unchanged and still correct: the only pass inside
                                           # [chain_due, rerun_chain_until] is 09:25, and the worst case now finishes six
                                           # minutes before it rather than twenty-two.]
midday_due                    = 12:20      # [Midday] run_time plus twenty. DERIVED, not chosen: the only recorded run of the
                                           # scan step took 20.5 seconds and the render makes no vendor and no model call, so a
                                           # healthy pass is over by about 12:01. The upper bound is the SCHEDULE and not the job:
                                           # a due time later than the first pass that can judge it slips the verdict by a whole
                                           # pass_interval_min, so due must land at or before 12:25. Thirty, matching nightly_due,
                                           # would have put it at 12:30 and cost the reader half an hour for nothing.
nightly_due                   = 22:45      # the 22:15 nightly is minutes long
rerun_chain_until             = 09:30      # after the open a premarket report is history, report only
collector_stale_after_s       = 180        # no bar file write for this long inside the window means dead
universe_rerun_after_days     = 8          # a fresh weekly build is 7 days old at most
max_reruns_per_job_per_day    = 1
flag_backlog_after_days       = 7          # an unjudged quantifier flag older than this is a backlog rather than a fresh flag
job_log_stale_after_s         = 2200       # no write to a job's dated log for this long means the job is not alive. See the liveness note below.
                                           # [corrected 2026-08-29: was 1200, two minutes over max_attempts times a 537s
                                           # timeout_s. [Analyst] timeout_s moved to 1007 and this is the number derived
                                           # from it, so it moved too: 2 x 1007 is 2,014 and 2,200 leaves three minutes
                                           # over it. Leaving it at 1200 would have made a HEALTHY long analyst step read
                                           # as a dead job, which is the double chain this gate exists to prevent.]
pass_interval_min             = 30         # register_tasks.ps1: the monitor task repeats on this interval
first_pass                    = 07:25      # register_tasks.ps1: the weekday monitor trigger, and what its repetition counts from
last_pass                     = 09:25      # first_pass plus the two hour repetition duration in register_tasks.ps1
night_pass                    = 22:45      # register_tasks.ps1: monitor-night, one firing with no repetition
midday_first_pass             = 12:25      # register_tasks.ps1: monitor-midday, and what its repetition counts from. The first slot
                                           # on the existing :25 and :55 grid at or after midday_due, so there is one fact about when
                                           # the watchdog fires rather than two.
midday_last_pass              = 13:25      # midday_first_pass plus the one hour repetition duration in register_tasks.ps1, so the
                                           # firings are 12:25, 12:55 and 13:25. MORE THAN ONE PASS IS ARITHMETIC, not caution:
                                           # job_log_stale_after_s is 2200, so a midday that hung after writing its log at 12:00 is
                                           # still warm at 12:25 and cannot be told from a live job, and is 3,300 seconds cold by
                                           # 12:55. One pass could only ever report UNRESOLVED on that state. The third is margin for
                                           # Task Scheduler's repetition endpoint, which the morning trigger's five firings imply is
                                           # inclusive and which nothing here has verified.

### The liveness note

The watchdog reruns what is idempotent, and idempotent is not the same as safe
to run twice at once. Until 2026-08-20 the morning chain and the nightly were
rerun on the absence of a finish marker in the dated log alone, and a job that
started seconds ago has not written that marker, so it read exactly like one
that died. A late machine wake is what fires it: every task carries
-StartWhenAvailable, and two catching up within 0.15 seconds of each other is
already on record from 2026-08-19.

_job_alive now asks the same two questions of every job that _collector_alive
already asked of the collector. Does Task Scheduler say the task is running,
which is Status Running or Last Result 267009, the code Scheduler returns while
a task is still going and which the watchdog used to read as a failure. And was
the job's dated log written to inside this many seconds. A third question was
added to it later the same day and is asked before the mtime one: what is the
last step marker in that log, because a job that exited says so there. The
correction below is why.

The number has to clear the longest silence a healthy job can produce, and that
is the analyst step: cmd writes a step marker at each boundary but nothing
touches the log while one python step runs, so the worst case is [Analyst]
max_attempts times timeout_s, 2,014 seconds. 2,200 leaves three minutes over it.
Measured within-run gaps to compare it against: the morning chain's worst is
342.6 seconds on 2026-08-27, 232.1 on 2026-08-20 and 398.4 on 2026-08-13,
discover's is 33.0 and the nightly's is 62.0.

[corrected 2026-08-29: the two figures above were 1,074 and 1,200, against a
537 second timeout_s. Both moved with it. This is the whole reason the timeout
could not be raised alone: this gate's job is to tell a hung job from a working
one, and a healthy analyst step is by far the longest silence in the tree.]

WHAT THE LARGER NUMBER COSTS, said rather than left to be discovered. The blind
band below widens with it, from twenty minutes to about thirty-seven. A job
that dies with NO finish marker, leaving only a warm log, now reads as
possibly-alive for that much longer. Two things bound it and neither is new:
the mtime is asked last, so any death where a step actually exited is caught by
its finish marker whatever the mtime says; and where the mtime is the only
evidence and no later pass falls inside the window, the job is reported
UNRESOLVED and counted as a problem rather than as RUNNING. For the morning
chain, whose only in-window pass is 09:25, that verdict is the same at 1,200 as
at 2,200. What actually changes is that the watchdog will no longer RERUN a
chain in that band, which is the safer direction: a second chain races the
first on packet.json and spends another CLI completion.

The first version of this note ended on a claim that is not true, kept here
because the shape of the error is worth more than the sentence was: "It does
not delay a rerun past its window. The monitor repeats every thirty minutes,
which is longer than this, so a job that really died at 08:46 reads as alive at
the 08:55 pass and as dead at 09:25, still inside rerun_chain_until." That
inference needs a LATER pass to exist, and for the two jobs the gate guards
there is none. register_tasks.ps1 fires the weekday monitor at first_pass and
repeats it every pass_interval_min through last_pass, which is 07:25, 07:55,
08:25, 08:55 and 09:25, fires monitor-midday at midday_first_pass and repeats
it through midday_last_pass, which is 12:25, 12:55 and 13:25, and fires
monitor-night once at night_pass. chain_due
is 09:00, so the 08:55 pass reads NOT DUE, exactly as the [Analyst] timeout
note already says, and the chain is judged by ONE pass inside
[chain_due, rerun_chain_until]: 09:25. The nightly is judged by one pass too,
monitor-night at 22:45, and nothing after it revisits that verdict. The next
morning's 07:25 is before nightly_due and prints NOT DUE, by the following
22:45 the dated log path has rolled, and job_status.overdue cannot surface it
either because backfill, outcomes and pool_recall each carry a one session
window.

So the real property is narrower. A log written inside job_log_stale_after_s is
the SAME reading for a job writing now as for a job that stopped writing up to
twenty minutes ago, and it costs nothing only where a later pass inside the
window reads it again. That leaves one blind band per job: a chain that dies in
(09:05, 09:25] and a nightly that dies in (22:25, 22:45] are both twenty
minutes fresh at their only pass, and until 2026-08-20 each printed a clean
RUNNING with nothing counted and the pass exiting 0.

Two things narrow those bands now, and neither pretends to close them on mtime.

The mtime is asked LAST. Every .bat echoes a finish marker naming the step and
its exit code once that step has returned, and exits on a non-zero one, so a
log whose last marker is a finish belongs to a job that is over whatever its
mtime says, and a non-zero code there is named in the report line. That covers
every death where a step exited, which is most of them. What is left is power
loss, a kill and a hang: no marker, a warm log, and nothing in the file that
tells them apart from work in progress.

And the pass with nobody after it stops pretending. Where the mtime is the only
evidence and no later pass falls inside the window, the job is reported
UNRESOLVED rather than RUNNING and counted as a problem, so the pass exits
non-zero and the morning report names it. It is not rerun: a second chain races
the first on packet.json and spends another claude CLI completion, and a second
nightly duplicates the backfill. For a SCHEDULED job the path is rare, because
Task Scheduler settles it with Status Running or 267009; the warm log is the
only evidence for a hand run or for a rerun the watchdog launched with Popen,
neither of which Scheduler can see. The nightly band is bounded further by the
07:00 nightly-catchup, which runs the backfill and the outcome fill again
regardless.

The same schedule values decide whether the collector may be HELD. The hold
waits one pass rather than starting a collector on a watchlist discover is in
the middle of rewriting, so it is a promise that a later pass starts it. At the
08:55 pass there is no later pass inside the collector window, because
[Collector] stop_time is 09:25 and the branch that starts a collector tests
now < stop_time. Held at 08:55, window over at 09:25, no collector all morning
and its rerun budget unspent. A hold now requires a next pass inside the
window, and past that point the collector is started on the names that are on
disk instead: half a window of the previous session's tape is worth more than
no tape. See the stale watchlist note below for what that costs and what now
pays for it.

### The stale watchlist note

The paragraph above stood on a second sentence that was withdrawn on
2026-08-24: "and scan records watchlist_generated_at, so the wrong names case
stays visible in the packet rather than becoming a silent hole." The field was
recorded and read by nothing. Recorded is not visible, and the morning that
proved it was collected before anyone noticed the difference.

**What happened.** A power cut ran 01:00 to 07:49 ET on 2026-08-24. Every
weekday task carries -StartWhenAvailable, so Task Scheduler caught the whole
set up at one instant, 07:54:58, which collapsed the 07:15 to 07:20 gap
between discover and the collector to nothing. The collector reads the
watchlist ONCE, at subscribe time. It read the file in the same second discover
was replacing it, got the previous session's, and select_symbols found no row
in it marked subscribed. An empty list is not an error, so it subscribed to the
eight [Collector] context_symbols and nothing else, wrote its subscription
list, and ran healthy. Nothing objected. The watchdog restarts a collector that
is DEAD and this one was alive, listening perfectly to the wrong thing, and
_collector_has_subscribed read the list it had written as proof discovery was
settled. All 42 of the day's candidates would have reached the 08:45 scan with
no coverage and been reported as "on the watchlist but the collector recorded
no bars for it", which reads like a quiet tape.

**Two changes, and they are deliberately in different places.**

collect_premarket REFUSES a watchlist that is not today's and exits non-zero.
That is the fourth hard rule applied to an empty list, and it is what the
2026-08-22 review found two thirds of its defects to be: a missing answer
presented as a measured one, leaking wherever the missing thing had a falsy
value. The refusal is also the repair, because it writes no subscription list,
which is what holds the watchdog's discover rerun gate open. --snapshot and
--verify-intraday return well before the check and are unaffected.

The branch above is the ONE exception, and it passes --stale-watchlist-ok
through job_collector.bat to say so. It is entitled to, because it is the only
caller that knows no later pass falls inside the window, which is exactly the
condition that makes wrong names better than no tape. Nothing else in this
project passes that flag and a claim holds that the 07:25 pass does not: at
07:25 a later pass still fits, so the right answer there is to let the
collector refuse and be restarted on a file discover has finished writing.

**And the withdrawn sentence is now true, on the second attempt.** scan raises
a gap on a watchlist that is not today's. That check alone would NOT have
caught 2026-08-24, and saying so matters more than the fix: the collector read
the previous session's file at 07:55:13 and discover replaced it with a today
stamped one in the same second, so by 08:45 the file on disk was today's and a
date test passes while the socket is still listening to eleven context tickers.
The file is not the evidence. What the collector asked the socket for is, and
it writes that down at subscribe time. scan therefore ALSO compares the
subscription list against the names this watchlist marks subscribed, and names
any that were never requested. Both land in gaps_to_fill, which the analyst
reads and the report prints, and both say the part a reader needs: a candidate
reported with no collector bars was never listened to, and that is not evidence
the tape was quiet.

### The flag backlog note

The watchdog also counts the quantifier guard flags nobody has judged yet.
It is not checking a job; it is checking that a measurement is still being
taken. The flag log exists so the guard's false positive rate is a counted
number rather than an impression, and a log that fills while nobody records
a verdict is a rate that never prints and a word list tuned on the same
intuition it was written with. This project has watched that happen once
already: pool_recall raised nightly and wrote nothing for a week while
DECISIONS cited its evidence as accumulating.

A flag raised this morning has not been ignored, so pending flags are named
and not counted as a problem. Past flag_backlog_after_days the oldest one
has survived a week of mornings, which is a backlog, and it joins the
problem count so it shows up on a morning somebody is already reading.

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
The labels are lowercased on the way in, because pair_map lowercases every key,
so the report table prints spy and 10y rather than SPY and 10Y.

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

Both are levels the COLLECTOR saw, which is a sample of a window that starts at
07:20. [Truth] measures the same two references off the whole tape over the
whole premarket and writes them beside these as entry_ref_true and
stop_ref_true; the reference level note there carries the measured gap and its
direction. These two field names are read by that pass rather than assumed, so
moving either key moves both ends of the comparison together.

Every picks row carries a source: 'live' for rows written by the scheduled
morning inside the window below, 'test' for rows from manual or off clock
runs, and 'reconstructed' reserved for any future row rebuilt after the
fact. The writer decides at write time: the --test flag forces 'test', and
so does a run clock outside the window, because a packet gathered at noon
describes a different market than the one the report is about. Every query
and every screen filters to source 'live' and says so in its header when
it does not; test rows must never leak into outcome or calibration math.
The migration on 2026-08-14 marked every earlier row 'test', which every
one of them was.

live_window_start             = 07:00      # rows written inside this ET window are source live
live_window_end               = 09:30

## Paper

ONE RULE, written down before any code, and a SEED like everything else here.
It is a measuring instrument and not advice: it exists so that "what would this
have done" has one answer instead of an argument, and so that mfe_pct becomes a
diagnostic rather than a result.

**Which session it trades, and why that is not the one [Outcomes] measures.**
The scan runs at [Scan] run_time, 08:45, on the pick's own date, and the report
is about the open that follows it ninety minutes later. So the rule trades THE
PICK'S OWN SESSION.

[Outcomes] measures the session AFTER that one. next_day_open, next_day_high,
next_day_low, next_day_close, pm_high_broke_next_day, mfe_pct, mae_pct,
mfe_pct_true and mae_pct_true all describe D+1, and the session the report was
actually about is not measured by any of them. AXTI on 2026-08-27 is the
clearest case on the record: entry_ref 70.94, and its own session opened 70.30
and reached 70.85, which is a miss by 0.13 percent. next_day_high is 65.4155,
from 2026-08-28, and mfe_pct reads -7.79. Those are different facts about
different days and only the first is about the report.

Nothing in [Outcomes] is changed here. Those columns are a real second horizon
and rewriting them would destroy the record rather than extend it. The ledger
fetches its own bars for its own session, and this paragraph is the standing
warning that the two horizons are not the same and must never be read as one.

**The rule.**

  UNIVERSE      every live picks row. Not only the eligible ones: day_eligible
                and swing_eligible travel onto the ledger row as GROUPING
                columns instead, so a later pass can ask whether the screen's
                verdict separated outcomes at all. Booking only what the screen
                admitted makes that question unaskable.
  SKIP          any row whose fill_plausible is not 'plausible'. The trigger
                level has to be a price somebody could have transacted at or
                the booked P&L is fiction. A skipped row is WRITTEN with its
                reason, never dropped.
  TRIGGER       the first minute of the regular session whose high reaches
                entry_ref_true. A stop order resting at that level.
  ENTRY PRICE   max(entry_ref_true, that minute's open). A session that gaps
                straight through the trigger fills at the open and not at the
                level, which is the honest treatment and the common case for a
                gap candidate.
  STOP          stop_ref_true. The first minute whose low reaches it exits at
                that level.
  SAME MINUTE   a minute that both triggers and reaches the stop is booked as
                STOPPED. One minute bar carries no sequence, so the order
                inside it is unknowable, and the losing reading is taken rather
                than the flattering one.
  EXIT          the close of the last minute of the session, if the stop was
                never reached.
  NEVER FIRED   no trade. exit_reason says so and pnl is NULL, never zero. A
                zero would read as a flat trade, and a trade that was not taken
                and a trade that made nothing are different facts.
  SIZE          set by the version's own sizing mode above, whole shares,
                floor divided. v1 uses a fixed notional; v2 uses a fixed dollar
                risk. Never fixed SHARES under either, because this table holds
                prices from 5.64 to 1,585. A version whose size works out below
                one whole share books no trade and records why.

**No target, and that is a choice.** Adding one would make this a family of
rules with a parameter to fit, and the instruction was one rule. Holding to the
close is the least fitted exit there is: it has nothing to tune, so a result
from it cannot be a result about a tuned number. What it costs is visible on
every row, because mfe_pct sits beside the booked P&L and the gap between them
is exactly what a target would have been trying to capture.

THE SIZING MAP IS THE VERSION REGISTRY. Every version named on a `sizing` line
is booked, side by side, on every session, and a new version NEVER replaces an
old one. There is deliberately no separate list of versions: a version with no
sizing mode cannot be booked, and a sizing mode for a version nobody lists
would be dead configuration, so the two are one line.

sizing = v1 : notional                     # the same dollar POSITION on every trade
sizing = v2 : risk                         # the same dollar RISK on every trade

account_notional              = 100000     # SEED, DOLLARS. The notional both sizings are expressed against, so a booked P&L can be read as a return on something rather than as a number
position_notional             = 10000      # SEED. v1's fixed position, 10 percent of the account. Also the base [Truth] min_fill_band_notional derives from
risk_notional                 = 750        # SEED. v2's fixed dollar risk, 0.75 percent of the account. CALIBRATED, and the calibration matters: see the v2 note below
max_position_notional         = 25000      # SEED. v2's cap, 25 percent of the account. Without it a two percent stop buys a 37,500 dollar position and the sizing rule quietly becomes a leverage rule
session_close                 = 16:00      # ET. The regular session end the hold-to-close exit uses. The open comes from [Backfill] market_open, which is the same fact and is not restated here
max_band_participation        = 0.04       # SEED. The largest share of [Truth] fill_band_volume's notional that one position may be. See the note below

### Rule v2, pre-registered 2026-08-29

**Written before the code and before any v2 result existed.** v1 had booked 16
trades at that point and its numbers are below; nothing about v2 was chosen by
trying variants and keeping the best.

**v2 CHANGES EXACTLY ONE THING: the position size.** Entry, entry price, stop,
same-minute tie break, exit, the skip rule and the universe are byte for byte
v1's. That is deliberate and it is the whole design. Two changes at once would
leave no way to say which of them moved the number.

  v1   the same DOLLAR POSITION on every trade: position_notional
  v2   the same DOLLAR RISK on every trade: risk_notional, where the risk is
       entry_price minus stop_ref_true, capped at max_position_notional

**What v1's numbers said, and why sizing is the one thing to change.** Measured
2026-08-29 over v1's 16 booked trades:

  every one of the 16 was in profit at some point while held
  median best price reached while held      +1.84 percent
  median given back by the hold-to-close    -3.91 points
  median risk taken per trade                5.89 percent of the position
  widest risk taken                         21.48 percent
  median distance reached, in units of the risk taken   0.46R
  reached 1R at any point                    4 of 16

A trade that risks 5.89 percent to reach 0.46 of that cannot work at any hit
rate, and the two largest losses were the two widest stops: PLAB risked 21.48
percent and reached 0.05R, NSSC risked 18.22 and reached 0.59R. Under a fixed
notional those two carried 2,141 and 1,943 dollars of risk while LITE carried
253. That is an eight fold spread in what each trade could lose, across trades
the rule treats as equals. It is a sizing defect, not an exit defect, and it is
the one this project can fix without inventing a number to tune.

**THE RISK BUDGET IS CALIBRATED TO HOLD TOTAL RISK CONSTANT, not to win.** v1's
16 trades carried 12,354 dollars of risk between them, a mean of 772 per trade.
risk_notional is 750, which is that mean rounded to a policy number. So v1 and
v2 put the SAME total money at risk across the same trades and differ only in
how it is distributed. If v2 comes out ahead it is because equal risk beats
arbitrary risk, and not because it risked less. Choosing a smaller number here
would have manufactured the result.

**THE SKIP RULE IS NOT CHANGED FOR v2**, and this is a known imperfection
written down rather than fixed. [Truth] min_fill_band_notional is derived from
position_notional, which is v1's size; v2's positions run up to
max_position_notional. A v2 specific floor would be more correct and would also
mean the two versions traded DIFFERENT NAMES, which would confound the only
comparison this section exists to make. Both versions trade the same
population. A per version floor is a question for whenever a third version
needs one.

**What would make v2 the better rule.** Judged at the same point [Score watch]
and doc/research/SCORE_INVERSION.md name for the primary, 200 booked trades
across 60 sessions, on the same trades under both versions:

  v2 IS BETTER    its total P&L exceeds v1's AND its worst single trade loss is
                  smaller. Both, because a sizing rule that only improves the
                  total by taking more risk somewhere has not done the thing it
                  was built to do.
  NO DIFFERENCE   the total P&Ls are within 10 percent of each other. Sizing is
                  then not where this system's problem is, and the search moves
                  to the entry or the exit.
  v2 IS WORSE     its total P&L is below v1's. Equal risk sizing is standard
                  practice, so this outcome is more likely to mean the trades
                  with wide stops are the ones carrying whatever edge exists,
                  which is a real finding and points at the screen rather than
                  at the sizing.

**No test and no p value**, for the reason SCORE_INVERSION.md gives.

**What v2 is NOT.** It is not an exit rule and it does not add a target. The
+3.91 point median give-back is real and a target would capture some of it, and
a target is also a dial with a free number on it that could be turned until 16
trades looked good. If sizing turns out not to be the answer, an exit rule is
the next pre-registration, written the same way and run beside these two.

### What ties this section to the fill band

[Truth] min_fill_band_notional was set on 2026-08-29 before any rule named a
position size, and it was written down as a placeholder that "behaves like the
right rule for an order of about 10,000 dollars at a 4 percent participation
cap". Those two numbers now exist here, and the placeholder is exactly their
quotient: 10,000 / 0.04 = 250,000.

It stays ONE shipped value, in [Truth], because that is the key the code reads
and a second key holding the same number is two things to keep right. It is
derived from position_notional, which is v1's size, and every version is judged
against the same floor so that they all trade the same population; see the v2
note above on why that imperfection is kept deliberately. The
coupling is machine checked instead, by
claim_the_fill_band_floor_is_the_position_over_the_participation_cap, so a
change to either number here that is not carried into [Truth] fails the suite
rather than quietly decoupling the two.

## Fill warning

The MORNING'S version of [Truth]'s fill plausibility check, computed at 08:45
from the collector's own bars, because the definitive one cannot be.

**Why the morning cannot just run the real check.** Alpaca serves its sip feed
for a session that is OVER and refuses it with HTTP 403 for one that is
running, which is why [Truth] is a nightly pass. So at 08:45 the only evidence
available is the socket sample the collector has been accumulating since 07:20.

**IT IS A WARNING AND IT IS NEVER AN APPROVAL**, and the asymmetry is the whole
design. A low number here means the collector saw very little trade at the
premarket high and the level is probably not a price anyone could transact at.
A high number means nothing of the kind: it means this weak instrument did not
fire.

**How weak, measured rather than asserted.** Over the 54 live rows across 6
sessions where both the morning band and the night's verdict exist, at the
floor below:

  it fires on                                        12 of 54 rows
  names the night called implausible that it MISSES   4 of 10
  names the night called plausible that it flags       6 of 44

Four in ten of the genuinely untradeable levels get past it. That is stated
here, printed in the report, and is the reason the field is a warning rather
than a verdict.

**Why it cannot be calibrated any better than this.** The morning centres its
band on `pm_high`, which is the collector's own level; the night centres on
`entry_ref_true`, the level off the whole tape. Those differ by a median 1.19
percent and by as much as 20.9, so on the names that matter most the two bands
do not even overlap. On top of that the socket's share of the band ran 0.017 to
1.158 of the true figure across those same rows, a 68 fold spread. No single
floor turns one into the other, and one that appeared to would be fitted to 54
rows.

**The band width is NOT restated here.** It is [Truth] fill_band_pct and the
morning reads that same key, so the two bands are the same width by
construction and can never drift apart.

min_morning_band_notional     = 40000      # SEED, DOLLARS. Socket-observed volume times the level, within [Truth] fill_band_pct of pm_high. Below this the candidate is flagged thin. Chosen from the sweep above as the point that catches the most known-thin names without flagging more than it catches; the two error counts are recorded above and in DECISIONS.md rather than left to be discovered

**Three states, never a boolean**, on the [Truth] fill_plausible precedent:

  thin        below the floor. The collector saw very little at this level
  not flagged at or above it. NOT an approval, see above
  unknown     the collector never covered this name, so there is no evidence
              either way and none is invented

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

max_tags_for_one_company      = 20         # SEED. See the article scope note below.
max_candidates_sharing_article = 2         # SEED. See the article scope note below.

### The article scope note

EODHD tags are ARTICLE scoped, not company scoped, so a tag on a multi company
roundup is a tag about the roundup and not about every name the feed returned
it for. Until 2026-08-20 classify_catalyst read them the other way, and the
CNBC piece "Stocks making the biggest moves premarket: Walmart, Coinbase,
Moderna, Alibaba and more" conferred class earnings, worth 3 of the score's 10
points, on MSTR, COIN and MARA, none of which was on that morning's calendar.
Removing those 3 points moves MSTR from 7.0 green to 4.0 yellow and COIN, MARA
and BLSH from 6.0 yellow to 3.0 red.

So an article's tags classify a name only when the article is about it, and
breadth is what decides that. Two counts measure breadth, because neither one
sees the whole thing, and an article has to sit inside both.

The first is the tag count, and it catches a roundup even when the feed handed
it to a single candidate: that CNBC piece carried 46 tags, 19 of them issuer
names covering 14 companies, against a maximum of 7 tags on the single company
releases the same morning.
20 sits in the empty stretch between those two figures.

The second catches what the tag count cannot, a roundup tagged by TOPIC rather
than by issuer. "Biggest stock movers Thursday: Crypto stocks, WOLF, and more"
carries seven purely topical tags, so nothing about its tag list gives it away,
and the feed returned it for three of that morning's twelve candidates, one of
which took class earnings off it. An article the feed hands to more than this
many of one morning's candidates is not about any one of them. 2 sits where it
does because two names sharing one genuine story is ordinary and three or more
is a wire roundup or a sector piece.

The cost of being wrong here is a class withheld rather than a class invented.
A name whose every article is a roundup comes out class none with
catalyst_found still true, which says the window was checked and paid nothing,
where null would say it was never checked. Both numbers are seeds and the
header of this file applies to them.

### The macro tag note

A THIRD breadth test, and it catches a shape neither count above can see. The
two counts measure how WIDE an article is: how many issuers it tags, how many
candidates the feed gave it to. Both are blind to the narrow market piece. "US
Stock Market Today: S&P 500 Futures Edge Lower As Inflation Concerns Resurface"
carries five tags and went to one candidate, so it sits well inside both limits
and its tags were read as tags about that candidate. It is not about any
company at all. It is about the session.

That is the shape that put "Palantir Leads Tech Stocks as Nasdaq Rebounds"
under MSTR on 2026-09-01: five tags, one candidate, invisible to both counts.

MEASURED FIRST, on every article any packet has carried: 195 articles over the
fourteen sessions 2026-08-13 to 2026-09-01, labelled wrap or company release by
TITLE ONLY so the labelling cannot be circular with the tag rule being tested.
71 labelled wrap, 40 labelled company release, 84 left unlabelled.

Macro tags carried, per article:

    macro tags   wrap   release   unlabelled   all
        0          50      40         83       173
        1          12       0          1        13
        2           8       0          0         8
        3           1       0          0         1

THE DISTRIBUTION HAS A GAP AND IT IS AT ZERO, so the threshold is presence and
not a number chosen inside a continuum. 173 articles carry none. The 22 that
carry any are 21 labelled wraps and one policy story, "Trump pushes Clarity Act
at White House crypto meeting", which is not a company release either. Across
the 124 articles NOT labelled a wrap, exactly one carries a macro tag, and it
is that policy story. No company release in the corpus carries one.

That is evidence and not proof. 40 labelled releases is a thin denominator: a
tag that truly sat on one release in twenty would be missed here about one time
in eight. The list below is a SEED for that reason and the header of this file
applies to it.

THIS TEST IS ORTHOGONAL TO THE OTHER TWO, which is the point of adding it. All
22 articles it catches are invisible to the tag count and the sharing count;
the overlap is zero. The reverse holds too: all eight of the big issuer
roundups, 33 to 50 tags, carry no macro tag at all, so this list would not have
caught the CNBC piece the other two were written for.

WHERE THE LIST CAME FROM. Every tag on it appears in the corpus, on at least
one labelled wrap and on no labelled release and no unlabelled article. Four
were the starting point and ten more were mined from the corpus by that test.
Six earned a catch nothing else makes; four are on the list on the strength of
never sitting on a release, and caught nothing new in these fourteen sessions.
Both kinds are marked below.

WHAT WAS MEASURED AND LEFT OFF, so the next reader does not re-propose it:

  Sector tags do not belong here. They sit on company releases, which is what
  disqualifies them: SEMICONDUCTORS on 2 releases, TECH on 3, AI on 3, RETAIL
  on 7, FINANCIALS on 2, ENERGY on 1, UTILITIES on 1. A sector tag says what a
  company does, not that an article is about the market.

  Desk section tags are a publisher's filing system, not a topic. STOCKS,
  MARKETS, STOCK MARKETS, US MARKETS, FINANCE and BUSINESS sit on 6 to 12
  wraps each and on no release, which looks strong until you notice they are
  CNBC section names. A list built on them is a rule about who published an
  article, and every catch they make here is already made by the tag count.

  ECONOMY, UNITED STATES, WALL STREET and TRADE-NEGOTIATIONS sit on no release
  either, and every article they catch is already caught by the tag count. They
  are also broad enough that 40 releases is too thin a denominator to trust
  them on. Left off, reconsider when the corpus is larger.

  GEOPOLITICS, CREDIT, DEBT, SELLOFF, EQUITIES, REGULATION and LEGISLATION each
  sit on a single company story in this corpus, so each one is disqualified by
  the same test that admitted the others. GEOPOLITICS is worth naming twice
  because GEOPOLITICAL-RISKS is on the list and reads like the same tag: the
  vendor uses them differently, and the corpus is the reason to trust that
  rather than the spelling.

An article carrying any tag below classifies no candidate. The cost of being
wrong is the same as for the other two counts, a class withheld rather than a
class invented, and catalyst_found stays true.

# Each earned a catch that neither of the counts above makes.
macro_tag = inflation : consumer price inflation, the session's subject
macro_tag = rates : the interest rate path, the session's subject
macro_tag = treasuries : government bond yields, the session's subject
macro_tag = geopolitical risks : conflict and sanctions moving the whole tape
macro_tag = cpi : the inflation print itself
macro_tag = ppi : the producer price print itself
macro_tag = labor market : the employment print itself
# On the list because it never sits on a release, but it caught nothing in
# these fourteen sessions that a tag above did not already catch.
macro_tag = fed : the central bank, whose decisions move every name
macro_tag = bonds : the bond market as a market
macro_tag = sovereign bonds : government debt as a market

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

## Score premarket float rotation

Premarket volume as a fraction of shares float. The alternative to
[Score premarket rvol], used when RVOL is unavailable. Only one of the two ever
contributes, so the two band sets must pay alike, or a name would score
differently for the mere fact of having no baseline.

The edges are not free choices. They are read off the rotation distribution at
the quantiles reproducing what the RVOL bands pay, and they are read off the
RESCUED population specifically: the names with no usable baseline, which are
the only names these bands ever touch. Names carrying both measures are scored
by RVOL and never reach this section, so calibrating against them would set the
rate for a population that never gets it.

That distinction was got wrong first time and is worth stating rather than
hiding. The first edges, 0.0006 for two points and 0.0003 for one, sat on the
overlap. The rescued names sit materially lower, at a median 0.61 of the
overlap's on the scored population, so those edges paid two points to only
45.87 percent of rescued names against a 53.87 percent target: the fallback
under-paid the very names it exists for. Corrected 2026-08-16 in the same
day's work. See DECISIONS.md for both distributions and the full comparison.

On the 303 rescued names among the top candidate_count by gap, over 61 cached
sessions, the edges below pay two points to 55.45 percent and one point to
12.21 percent, against an RVOL target of 53.87 and 12.43.

Re-derived 2026-08-17 by re-running that script after its float screen was
corrected to read all three [Float rotation] floors from this file instead of
one hardcoded copy. THE EDGES ARE UNCHANGED, 0.0004 and 0.0002 both times, and
the screen fix provably cannot move them: it changes one verdict across the
whole float cache, YPF, and YPF reaches the top candidate_count by gap on none
of the 61 sessions, so it never voted on these edges.

The percentages in the paragraph above are the 2026-08-16 measurement and are
kept as written. The 2026-08-17 re-run measured 300 rescued names paying 56.00
and 11.67 percent against a target of 53.72 and 12.40. The difference is not the
screen fix: data/universe.json was rebuilt between the two runs and the
addressable population differs on 29 of the 61 sessions before the float screen
is reached. Expect a re-run to reproduce the EDGES, which is what this section
sets, and not the surrounding percentages, which describe the population of the
day they were measured. See DECISIONS.md 2026-08-17 sixth.

**Re-fitted 2026-08-20, and this time the edges DID move: 0.0004 and 0.0002
became 0.00033 and 0.00014.** Everything above is kept as written, because it
was true when it was written. What changed is the population, not the method.

The `rescued` set both earlier fits were read off was 36 percent the script's
own cold start. For the first [Baseline] min_sessions_for_rvol sessions the
rolling history is too short for ANY name to carry an RVOL, so every
addressable name fell into `rescued` whether or not it had a baseline. Those
894 rows are ordinary established gappers, and this section's whole argument is
that such names sit materially higher than a genuine rescue, so they dragged
the fitted quantiles up and took the shipped edges with them. The study now
walks the warm up sessions to build the history and refuses to tally them.

Measured on the 190 rescued names among the top candidate_count by gap, over
the 51 tallied sessions of 61 walked:

| edges | two points | one point | miss against target |
| --- | ---: | ---: | ---: |
| the RVOL target | 53.72% | 12.40% | |
| 0.0004 / 0.0002, as shipped | 47.89% | 14.74% | 8.17 points |
| 0.00033 / 0.00014, re-derived | 54.21% | 13.68% | 1.77 points |

The direction is the one the 2026-08-16 correction found, for the same reason
in a second disguise: a rotation band fitted on names that carry an RVOL will
under-pay the names that do not. It was the overlap contaminating the fit the
first time and the script's own cold start the second.

**Two significant figures, not one.** The re-derivation is rounded DOWN, so the
rounding never makes a band stricter than the share it was matched to, and it
was rounded to one significant figure until this fit. One figure is lossy in
proportion to where a value sits inside its decade: it costs 2 percent at
0.00033763 and 30 percent at 0.00014266, where the next figure down is a third
of the value. At one figure the re-derived pair reads 0.0003 and 0.0001 and
pays 54.74 and 16.32, missing the target by 4.94 points against 1.77. A
rounding rule may cost a little readability. It may not cost more accuracy than
the re-derivation it is rounding was performed to gain.

**The next re-fit needs no vendor call.** The payload now carries
`rescued_rotation_values`, the rows behind the quantiles, for both slices.
Their absence is what made this correction expensive: when the contamination
was found, which way the edges would move could not be computed from either
archived payload, because a quantile of a contaminated set does not yield the
quantile of the clean one, so the study had to be re-run against Alpaca to
answer a question about numbers already measured. With those rows and
`rvol_band_payout`, a re-fit is arithmetic on a file.

**Re-fitted 2026-08-31. The two point edge reproduced; the one point edge did
not, and it moved 0.00014 to 0.0002.** Measured on the 189 rescued names among
the top candidate_count by gap, over 50 tallied sessions:

| edges | two points | one point | miss against target |
| --- | ---: | ---: | ---: |
| the RVOL target | 53.35% | 10.89% | |
| 0.00033 / 0.00014, as shipped | 53.44% | 15.34% | 4.54 points |
| 0.00033 / 0.0002, re-fitted | 53.44% | 10.58% | 0.40 points |

Nothing was wrong with the 2026-08-20 fit. The POPULATION moved: universe.json
has been rebuilt twice since and ten more sessions are cached, and the one
point edge sits low in its decade where a small shift in the distribution moves
the quantile a long way. The two point edge is unmoved at 0.00033, which is
what says this is drift in the data rather than a fault in the method.

**Why it was worth moving for 4.54 points.** This section exists so the two
band sets pay alike, because a name is scored by one or the other and never
both. At 15.34 against a 10.89 target, a name with no usable baseline was
getting the one point band half again as often as an equivalent name that had
one, which is the exact defect the matching prevents. It is also the same size
of miss that settled the rounding argument above: one significant figure was
refused at 4.94 points.

**No historical row was rescored.** picks rows keep the score they were
published with, on the no overwriting rule. Two rows in the record would have
scored differently: NSSC on 2026-08-24 from 7.0 green to 6.0 yellow, and WSM on
2026-08-26 from 6.0 to 5.0, still yellow.

**The open [Day setup] eligibility floor moved with it.** DECISIONS.md lists a
rotation floor for day eligibility as still open, at 0.00014. That number was
the rotation edge admitting the same share the RVOL floor admits, and on this
population it now reads 0.0002. The question stays open; its candidate value is
0.0002.

**These edges are conditional on [Scan] candidate_count.** The scored
population is the top N by gap, and rotation rises with gap size, so changing
candidate_count changes the population these were fitted to and they must be
re-derived. Run `python -m research.float_rotation_study` with src on
PYTHONPATH and read
`mapping_transfer.top_<candidate_count>_by_gap.rederived_on_rescued`, which is
`top_12_by_gap` at today's candidate_count.

Read these as small numbers because the window is small: 0.00033 is three
hundredths of one percent of the float changing hands between 07:20 and 08:45,
not over the whole premarket.

band = > 0.00033 : 2
band = >= 0.0002 : 1
band = else : 0

## Score gap

Tested against the absolute gap percent.

**THE SCORE IS THEREFORE UNSIGNED, and what that costs is stated here rather
than left to be rediscovered.** A name down 20 percent and a name up 20
percent earn the same points, while every outcome column in picks is
measured from entry_ref, which is pm_high, a LONG reference. So a bucket
holding more falling names is compared on a quantity it cannot win. That is
a confound in the score's own evaluation and it is written down as one, in
doc/research/SCORE_INVERSION.md, dated before either judging point.

The direction is carried rather than the sign being restored: per candidate
as gap_direction, which reads a gap of exactly 0.0 as UP, per packet as
score_roll.text.direction, which is written
to be quoted word for word, and the report is required to give it wherever a
score is named. Signing the component instead would change what the score IS
while the score is under a pre-registered evaluation, and changing the
instrument mid measurement destroys the measurement. That is an owner
decision and not a code change.

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

## Score watch

The score exists to order names by confidence, and over the first fifty filled
rows it ordered them BACKWARDS: yellow beat green, twenty-five rows each. At
that count it is noise. It is also exactly the thing that should be watched
rather than rediscovered, so night/weekly_page.py renders it every night and
doc/research/SCORE_INVERSION.md holds a pre-registration written before the
count is reached.

**The page reports and does not conclude.** No test, no p value, no verdict in
the code. It prints n, the session count and three medians per group, and the
judging is a separate act performed against a rule written down in advance.

**BOTH DENOMINATORS, EVERYWHERE.** Twelve names from one morning share a tape
and are one observation, so every group states rows and sessions. A group that
looks like twelve data points and is one is the single easiest way to be wrong
with this table.

**A group below either minimum is WITHHELD and says so**, rather than showing a
median nobody should read. Suppression is per METRIC, not per group: booked
P&L, favourable excursion and adverse excursion each have their own n, because
the ledger reaches fewer rows than the outcome fill does.

min_group_rows                = 10         # SEED. Below ten rows one name moves the median
min_group_sessions            = 3          # SEED. The sample unit is the session. Below three, the rows share at most two tapes and the group is one or two observations wearing a larger number

**The excursion columns on that page are D+1.** mfe_pct_true and mae_pct_true
come from [Outcomes], which measures the session AFTER the one the report was
about; the booked P&L comes from [Paper], which trades the pick's own session.
See the [Paper] section on which session it trades. They are shown together
because they are the numbers that exist, and the page says on every rendering
that they are not the same day.

