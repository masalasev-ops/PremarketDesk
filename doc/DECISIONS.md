# Decisions

Choices that could reasonably have gone the other way, with the reasoning that
settled them and the date it was settled. Appended to, never rewritten. When a
decision is reversed, the new entry says so and the old one stays where it is,
because the reasoning that turned out to be wrong is the part worth keeping.

Errors of fact are corrected in place and carry a `[corrected YYYY-MM-DD: was
X]` marker; superseded decisions keep their original text and are answered by
a later entry. The distinction is whether the statement was true when it was
written. A measurement that was misreported is a mistake and is fixed where it
stands, because a decision resting on a number nobody can reproduce is worse
than no record. A decision that was right and has since been overtaken keeps
its text, because that reasoning is the point of this file.

What changed and when is in CHANGELOG.md. Every threshold is in CRITERIA.md.

This file starts at 2026-08-14. Earlier reasoning is in doc/BUILD_PLAN.md and
in the commit messages.

## 2026-08-22, second: a step that already acted reports instead of failing, and a lost session is labelled instead of dropped

Three calls from the 2026-08-22 review that could reasonably have gone the other
way. All three are about what to do AFTER something irreversible has already
happened, which is a different question from what to do before it, and this tree
had been answering both the same way.

**A STEP THAT HAS ALREADY ACTED MUST NOT FAIL LOUDLY.** deliver.py sends the
email and then writes delivered.json to stop a rerun sending it again. The
obvious fix for a write that can be denied is to retry and then raise, which is
what every other write in this tree does and is correct for every other write in
this tree, because everywhere else the step can simply be run again.

Here it is exactly backwards. The chain stops at the first nonzero exit, the
finish marker is written by build_archive AFTER deliver, and the watchdog
relaunches a chain with no finish marker. So raising is not "the step failed",
it is "send the email a second time". Reproduced: two POSTs from one report.

deliver now returns 0 on a denied record, prints that the email went and the
record did not, and calls job_status.failed so the status trail carries the
fact. That combination is deliberate and it is unusual: job_status.run turns a
declared failure into STATUS_ERROR while still returning the code, so the chain
continues to its finish marker and the watchdog leaves it alone, while the
watchdog's own steps_ok check reports STEP FAILED for a human to read. A morning
that sent one email and could not say so is better served by a line in the log
than by a crash, and the crash was the thing summoning the duplicate.

The alternative was to write the record BEFORE the POST and delete it if the
send failed. Refused: that trades a duplicate email for a silently missing one,
and of the two mistakes only the duplicate is visible to the person it happens
to.

**FOUR ATTEMPTS AND HALF A SECOND ARE NOT CRITERIA KEYS.** deliver's
WRITE_ATTEMPTS and monitor_jobs' STATE_WRITE_ATTEMPTS are module constants, not
CRITERIA.md thresholds, and the rule they are being held against says every
SCREEN threshold lives in CRITERIA. These decide nothing about a market. Putting
them there would say the file is where numbers live rather than where DECISIONS
live, and the 263 keys already in it are hard enough to audit. Sized against the
documented antivirus denial, which has cleared within a second every time it has
been seen. If a real morning ever exhausts four attempts, that is evidence for a
key rather than an argument for one now.

**A LOST SESSION IS LABELLED, NOT DROPPED.** site/PremarketDesk.html has been
rendering 2026-08-21 as its seventh session since the sweep destroyed it: one
candidate, AAPL at 100.00, presented exactly like the six real mornings. The
cheap fix is to skip a session whose packet no build wrote, and it is the wrong
one. The rail is a list of dates, so a session removed from it leaves a gap, and
a gap in that list reads as a day the market was shut. This file is the record
of what this system did, and a record that quietly omits its worst day is the
failure it exists to prevent. So the session stays, and the page says on it, in
the rail, in the subtitle count and in the step's log that it is not a morning.

Matched on the SHAPE of the commit rather than on the string "stub", because a
guard that names one value catches that value and nothing else, and the next
fixture to reach a run directory will not be spelled the same way. The first
draft did the shape test and got the SILENCES wrong: it treated a packet with no
build key as a fixture, and accused 2026-08-13 and 2026-08-14, both real
mornings written before the field was added on 2026-08-14. A packet that cannot
be asked and a packet that answers wrongly are not the same observation, which
is the same distinction [Notable]'s four list states were drawn on this morning,
and it is worth noticing that the same mistake was available twice in one day.

## 2026-08-22, first: four states for an empty ranked list, not one, and what "considered" counts

Two calls inside the notable movers disclosure work that could have gone the
other way. Both are cheap to overrule and are named here rather than buried.

**FOUR STATES RATHER THAN A REASON STRING.** The section already had a reason on
every empty list. What it did not have was a state, and the difference is
whether a reader can compare four lists at a glance or has to parse four
sentences. The owner asked for at minimum three distinctions: an input that was
null so the list could not be computed, an input that was present with nothing
clearing the floor, and a leg with no eligible population. Those map onto
`uncomputable`, `below the floor` and `nothing to rank`, plus `ranked` for a list
holding names.

The fourth was not padding. `uncomputable` and `nothing to rank` both produce an
empty list off an unavailable leg, and telling them apart needed
`_leg_report` to carry `input_present`, because `available` alone cannot say
whether the file was missing or the file was read and held nothing. A lost
sidecar sends a reader to discover's 07:15 run; a sidecar that carried no pair
of closes sends them to the vendor. Collapsing the two would have kept the code
smaller and sent half of those readers to the wrong place.

`below the floor` is deliberately reachable by ONE of the four lists, because
only prior_session_by_market_cap applies a floor before it ranks. The other
three rank whatever their leg measured, so they cannot be below a floor by
construction rather than by accident, and the claim asserts the branch is
reached rather than assuming it.

**THE STATE WORDS ARE CHOSEN FOR THE QUANTIFIER GUARD, NOT FOR PROSE.** The
natural spelling of the third state is "none cleared the floor". REPORT_TEMPLATE
tells the model to quote these strings word for word, and
analyst.quantifier_violations flags `none` within six words of `name`,
`candidate` or `watchlist`. The guard is in warn mode today; on the day it flips
to enforcing, a quoted state would be regenerated twice and then fall back to the
Python report, every morning a list was empty, which today is every morning. So
the words are "below the floor" and "nothing to rank". This is the T17 lesson
applied before the fact rather than after it, and it is the second time the
section's own vocabulary has had to be written around this guard.

**CONSIDERED IS WHAT THE LEG MEASURED, NOT WHAT THE CLOSES FILE COUNTED.** The
leg already reports `examined`, which is the closes file's own denominator, 2,754
on an ordinary morning. A list's `considered` is a different number: the rows the
leg actually produced a move for, which is what the list could have ranked. The
alternative was to reuse `examined` and have one number mean one thing, and it
was refused because a list that ranked over 2,741 measured rows out of a 2,754
row file would have reported the 2,754, and the thirteen rows nobody could
measure would have vanished into a denominator that looked complete. The two
numbers are both published, one on the leg and one on the list, and they are
allowed to disagree.

`considered` is 0 and never null when a leg is lost, which is the opposite of the
convention the legs use: a leg reports `examined` null when it cannot look the
number up. Here the count is not unknown, it is zero, and the state beside it
already says the input is missing. A null would have taken the denominator away
from the exact case it was added for.

## 2026-08-21, eighth: the record re-read against true volume, and what it costs the watchlists

Every session with a packet was re-measured against Alpaca full SIP over the
window its own morning used, not examined. night/true_volume.py --reread does
it from the packet rather than picks, so it reaches the four sessions whose
rows were purged on 2026-08-19 and writes to nothing.

| session | candidates | day watchlist as published | would gain on true volume | would lose | swing | names that change side |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-08-13 | | | | | | not a morning: gathered 16:40, excluded |
| 2026-08-14 | 12 | 0 | 0 | 0 | 0 | none |
| 2026-08-17 | 2 | 0 | 2 | 0 | 0 | +HTHT, +KEEL |
| 2026-08-18 | 12 | 0 | 1 | 0 | 0 | +AS |
| 2026-08-19 | 12 | 0 | 4 | 2 | 0 | +KC, +MRVL, +EL, +DRD |
| 2026-08-20 | 12 | 0 | 7 | 0 | 0 | +SCSC, +FUTU, +MSTR, +ASST, +BLSH, +COIN, +MARA |
| 2026-08-21 | 12 | 6 | 4 | 0 | 0 | +BKE, +GLXY, +CLSK, +HUT |

**Six published day watchlists held six names between them. On the true volume
they hold twenty four.** Not one name moves the other way: no name the morning
admitted fails the floor on its true RVOL.

**The rule for changing side is narrow on purpose.** A name counts only when
premarket_rvol was the ONLY day condition it failed AND its true RVOL clears
the floor. Far more names clear the floor than change side: on 2026-08-14
eleven did and none is admitted, because all eleven also failed the prior day
high, which no volume number touches. Counting floor clearances instead would
have put 2026-08-20 at ten rather than seven, overstating the defect in the
same direction, and for the same reason, that the estimate understated it. The
weekly page counted it the wrong way for one afternoon and was corrected.

**Swing watchlists cannot move here and none does.** [Swing setup] carries no
volume condition at all. Stated because a reader would otherwise have to
reconstruct it.

**The first run of the re-read was itself wrong, in the way this project keeps
catching.** day_failed_conditions did not exist before 2026-08-19, and reading
the missing field as an empty list said "this name failed nothing" for every
candidate in the three older packets. It reported 2026-08-14, 08-17 and 08-18
as gaining zero names. That is an absence dressed as a measurement, the same
failure as the off exchange counter that printed a missing field as a measured
zero. day_failed carries the same fact as prose in every packet ever written,
and the single question here needs no lossy mapping: one entry beginning
"premarket_rvol" is exactly the case. Where neither field exists the answer is
UNRESOLVABLE and the report says so.

**2026-08-13 is excluded and that is a finding, not a gap.** Its packet was
gathered at 16:40 against a scheduled 08:45, so it describes a different market
and its watchlists are not a morning's. The re-read refuses any packet whose
run_time_et is not [Scan] run_time rather than quietly averaging it in.

### What this corrects in the documents

The 2026-08-18 float rotation entry argued the open eligibility question around
AS.US, on the grounds that its premarket RVOL was null and float rotation was
the only measure that could rescue it. **Its true RVOL is 606.85.** The name is
admitted by the volume screen itself once the volume is right, so the entry's
strongest example is no longer an example. Corrected in place. The eligibility
question survives, narrowed: the case for a float rotation floor now needs a
name whose RVOL is null AFTER the correction, and none has been observed.

The 2026-08-18 model-summary entry counted correctly and one word under it
changed meaning: AS.US's RVOL failure is now known to be an instrument reading.
Corrected in place.

**"Six mornings, 62 candidates, zero day eligible" is quoted in three places
and it is still exactly true.** It describes what the screen DID, and the
screen did that. What has changed is what it means: it was written as evidence
that the ratio could not reach its floor, and it is now also the measure of
what that cost. Each of the three is annotated rather than rewritten, because
the sentence is not wrong.

### The compounded shortfall, in one figure

The socket carried a median 0.0296 of the true premarket tape: about one share
in thirty four. Range 0.0087 to 0.3334 across 24 rows, a 38 fold spread. Feed
capture ran 0.0288 to 0.4231 on the socket's own window; window share ran
0.1562 to 0.9779. Multiplying the two medians gives 0.0337 where the rows give
0.0296, because the two fractions are not independent, which is why the product
is now published rather than left for a reader to compute. Table in
doc/research/COLLECTOR_VOLUME.md.

## 2026-08-21, seventh: the code is frozen except for defects that make published numbers wrong

**THE RULE.** From this entry forward a change is in scope if, and only if, it
does one of two things:

  1. It makes a number that gets PUBLISHED wrong, or stops one being wrong.
     Published means it reaches the report, the archive, the weekly page or the
     picks table.
  2. It makes the RECORD READABLE. Not richer, not better instrumented:
     readable, by a person who was not here when it was written.

Everything else waits for the outcome rows. Not "is deferred", not "is lower
priority": waits. There is no evidence yet that any of it is worth having,
because the thing this project exists to test, whether the screen picks names
that go on to do something, has zero settled outcomes behind it.

**WHY, IN NUMBERS THAT WERE COUNTED RATHER THAN REMEMBERED.**

| measured 2026-08-21, after this session's work | |
| --- | ---: |
| Python, src/ | 42,949 lines across 63 files |
| Documentation, tracked markdown | 14,869 lines |
| scan.py alone | 4,533 lines |
| CRITERIA thresholds | 260 |
| conditions in the day screen those thresholds serve | 5 |
| claims in test_regressions.py | 74 |
| test modules | 13 |

260 thresholds for a screen with five conditions. 4,533 lines in one module to
decide which of about twelve names to put on a list. Every finding that
produced that growth was real, and several of them were serious: the RVOL
numerator was measuring the wrong tape, the packet asked the model to apply a
correction twice, the socket cap probe published a reading its own noise
swallowed. Fixing each was right. The aggregate is still past what one person
can audit, and an unauditable safeguard is a liability wearing a safeguard's
clothes.

**WHAT THE FREEZE IS NOT.** It is not a claim the code is finished, or correct.
Today's own work found the shipped capture correction wrong by up to nineteen
times on live rows, and that fix landed under rule 1 above. There will be more
like it. The freeze says only that the ROUTE to more code now runs through a
published number being wrong, rather than through something being improvable.

**WHAT THE FREEZE IS PROTECTING.** Every hour spent making this tree larger is
an hour not spent accumulating the twenty sessions of outcomes that would say
whether any of it works. The project is nine days old and has 24 rows of true
premarket volume and zero settled outcomes. The next real decision, whether the
screen has any edge, cannot be brought forward by writing more of it.

**THE TEST, STATED SO IT CAN BE APPLIED WITHOUT ME.** Before writing anything,
answer: which published number is wrong today, and where would a reader see it?
If there is no answer, the change waits. "It would be more accurate", "it would
be more complete", "the docs should mention it" and "this ought to be measured"
are all out of scope. "The report prints an estimate as if it were measured" is
in scope, and is what today's truth pass was built under.

Three things are explicitly still open and are NOT unfrozen by being named
here. They wait for the same evidence as everything else: the float rotation
eligibility floor at 0.00014 in [Day setup], absolute against signed sigma on
notable lists 1 and 4, and whether premarket_capture_rate should become a per
symbol table now that capture_observed is being measured. The third has a date
attached: twenty sessions of truth rows, which at one a trading day is
2026-09-18 at the earliest.

## 2026-08-21, sixth: the record's volume comes from Alpaca, and the estimate is named as one

The morning divides the collector's socket volume by [Collector]
premarket_capture_rate, one number, 0.1172. The owner's objection was that a
divisor cannot correct a quantity measured varying six fold, and that the error
is not random: thin names capture least and are understated most, and thin
names are the population float rotation exists to rescue, so the correction
reinstates at a lower layer the bias the fallback removed.

**The first night of measurement says the objection understated the problem.**
night/true_volume.py fetches Alpaca full SIP one minute bars for every live
picks row over the same window the morning used, once the session is over, and
writes beside the morning's numbers on the pm_high_true precedent. Two sessions
measured, 24 rows:

| | 2026-08-20 | 2026-08-21 |
| --- | ---: | ---: |
| capture_observed, median | 0.1010 | 0.0928 |
| capture_observed, range | 0.0403 to 0.4231 | 0.0288 to 0.3187 |
| spread within the session | 10.5 fold | 11.1 fold |
| rows below the shipped 0.1172 | 7 of 12 | 8 of 12 |
| published volume over true volume | not applicable | 0.053 to 0.745 |

**Every row on 2026-08-21 was understated, by between 1.3 and 19 times.** The
morning published RVOL figures that had already been corrected once and were
still an order of magnitude short.

**[corrected 2026-08-21: THE TWO SESSIONS ABOVE ARE NOT EQUALLY SUPPORTED, and
this entry presented them as though they were.**

capture_observed is the collector's socket volume over what the tape actually
carried in the same minutes. The vendor side can be re-fetched from Alpaca for
either session. The SOCKET side comes from data/premarket/<date>.jsonl and the
packet, and for one of the two those files no longer exist: at 15:46 that day a
sweep invoking every claim directly wrote 258 fixture bars over roughly 3,200
real ones, and 762 bytes over a 125 KB packet.

| | raw inputs | status |
| --- | --- | --- |
| 2026-08-20 | capture 3,249 lines and packet 125,575 bytes, both intact | REPRODUCIBLE: every figure can be recomputed from disk |
| 2026-08-21 | capture and packet both overwritten with fixtures | RECORDED ONLY: the numbers stand and cannot be re-derived |

pm_volume is null in picks for both sessions, because those rows predate the
column, so the socket volume for 2026-08-21 survives nowhere at all. Its
capture_observed values are not wrong and they are not checkable, and those are
different things.

**What this does to the finding.** The eleven fold spread within a single
session is measured on 2026-08-20 alone and stands unaided: 0.0403 to 0.4231
over twelve names, all re-derivable. The claim that the spread REPEATS across
sessions rests on one reproducible session plus one recorded value, which is
weaker than the table above reads, and no later work should treat the pair as
equally checkable. The next session measured restores a second reproducible
one; until then the repeat is a single corroboration, not a replication.

night/backup_evidence.py now copies both artifacts outside the working tree on
every nightly, so a session cannot be ended this way again. It began on
2026-08-21 and holds 2026-08-13 through 2026-08-20 intact.]**

**The cost in names, which is the only unit that matters.** Against the day
screen's premarket_rvol floor of 1.5: on 2026-08-20 the morning published an
EMPTY day watchlist and ten of the twelve candidates cleared the floor on the
true numbers. On 2026-08-21 it published six and four more cleared. BKE, whose
RVOL the morning could not compute at all because its baseline median of 83
shares sat under the denominator floor, came in at 27.1.

**One thing the objection got wrong, stated because it was measured.** Thin
names are not reliably the worst captured. On 2026-08-21 the thinnest tape of
the twelve, BKE at 6,081 true shares, had the HIGHEST capture at 0.3187, and
the worst captured was HUT at 0.0288. Twelve names in one session settles
nothing either way, and the eleven fold spread disqualifies the single divisor
regardless of which direction it runs in.

**A defect in the first working version, found by running it.** capture_observed
was computed as socket volume over the whole 04:00 premarket. The socket does
not start until 07:20, so that number folded the collector's late start into a
figure meant to measure the feed, and it put ASST at 0.0254 where its real same
minutes capture was 0.0664. Two shortfalls with two different fixes, one a
subscription question and one a start time question. capture_observed now
divides by the socket's own window, and collector_window_share carries the
other: the 07:20 start saw a median 0.5228 of the premarket tape on 2026-08-20
and 0.2887 on 2026-08-21. **That is the lower bound this project has called
arithmetic since 2026-08-14 and never once measured.**

**A worse defect, in the claim rather than the code.** claim 73 rebound
config.DATA_DIR and config.RUNS_DIR for its fixtures and did NOT rebind
config.DB_PATH. Inside run_tests that changes nothing, because conftest rebinds
all three. Run directly, which is how it was being checked while it was
written, its two fixture rows landed in the LIVE picks table and its fake probe
overwrote a real session's truth columns with nulls. The morning's own columns
survived, which is the one property the claim asserts and the only reason this
was recoverable. The claim now rebinds DB_PATH itself, and the reason is in the
code: a claim that is only safe inside its harness is a trap for whoever
reaches for it next.

**What did not change.** The morning still ships the estimate, because Alpaca
refuses the sip feed for a running session with HTTP 403 and there is nothing
else to ship. What changed is that the report now has to SAY so: the disclaimer
names the volume as an estimate, gives the share used and whether it was the
symbol's own or the file wide default, and says the true figure lands that
night. REPORT_TEMPLATE, prompt_analyst rule 6 and the fallback report all carry
it, so which report a reader gets is no longer which caveat they get.

**Both sides of every ratio come from one tape.** pm_rvol_true divides an
Alpaca window by an Alpaca baseline over the same window across the prior
twenty sessions. Dividing the Alpaca numerator into the morning's EODHD
baseline would repeat this defect one vendor down. Both are meant to be
consolidated, and this project has been wrong about "meant to be" several
times.

**The trading calendar comes from the data.** The baseline walks back day by
day and a day the exchange was shut returns no bars for anybody, so it is
skipped without a holiday table having to be right. Bounded by
max_calendar_days_back so a symbol with no history cannot start a crawl.

## 2026-08-21, fifth: data/ gets a retention policy, and a closed study gives back 110 MB

Two things, and the second is the one worth reading.

**110 MB deleted, all of it one closed study's raw material.** data/backtest/
bars, vwap_gappers_trades.csv and alpaca_assets.json were the inputs and the
per trade output of the VWAP gappers study, whose pre-registered stop rule
fired: no rule cleared both conditions, and by the rule written before the
numbers were seen that work stopped. The 748 line report keeps every table,
both pre-registrations and the verdict.

What was given up is reproducibility, not results. `--cache-only` existed to
prove a rerun needs no network and cannot do that now. The module stays, on the
same principle that kept probe_alpaca_live and probe_live_v1 after their jobs
were deleted, and it prints what happened rather than letting the cache miss
surface as symbols that failed to fetch. **Nothing under data/ is in git**, so
this was not recoverable and was not a decision to take on the owner's behalf.

**The retention policy is the part that will matter next month.** Until today
this project had NO retention anywhere: a grep of the whole tree for prune,
retention or unlink returned one call, in probe_alpaca_live cleaning up after
itself. data/ grew by about 900 KB every trading day with nothing watching it,
and the only reason that had not become a problem is that the project is nine
days old.

night/prune_data.py runs in the nightly and deletes what CRITERIA [Universe]
closes_retention_days puts past its window. Three design choices, each because
the obvious alternative is worse:

**What may be deleted is a WHITELIST, not a rule about age.** It names one file
class. A sweeper that took anything older than a window would, on its first
run, have reached data/premarket, which is a recording of a tape that no longer
exists and cannot be refetched at any price; data/backtest/eod, the population
the shipped float rotation edges were fitted on; data/backtest/sessions, the
replay behind an open purchasing decision; and runs/, which build_archive
rebuilds the whole site from. Four only-copies, one careless glob. Claim 72
puts an ancient file of every one of those kinds in front of the prune and
requires it to survive.

**The age comes from the FILENAME.** universe-closes-2026-08-18.json describes
the session of the 18th whoever copied it and whenever. An mtime rule would
spare a file a backup had touched and take one it had not, which makes the
window a property of the filesystem rather than of the data. The claim sets the
mtimes to say the opposite of the names on both sides.

**Why universe-closes is the only entry.** discover writes it at 07:15 and
scan.load_universe_closes reads it at 08:45 for the SAME session_date, which
scan.main takes from the clock rather than an argument. There is no second
reader in the tree and no supported way to ask for a past one: --rescore reads
the saved packet and never reaches this file. It is dead to the code the moment
its own chain window closes. 7 days is margin for a human, not a measurement,
and it is marked SEED.

The step costs two EODHD calls a night, which is job_status.run recording the
meter at entry and exit. That is kept deliberately: the trail's value is that
it is continuous, and a step that skipped it would fold its own spending into
the next step's delta.

## 2026-08-21, fourth: the probe answered one question and was found to have never answered the other

The one off socket cap probe fired at 06:30, on the premarket tape it was armed
for, and both halves of what it produced are worth recording. The half that
worked closes a fork this project has carried since 2026-08-19. The half that
did not had been reported as an answer twice.

**The census: the feed omits off exchange volume, it does not mislabel it.**
All 123 trade messages carried `c=[]`, an empty condition list, and `dp=False`,
an explicit not a dark pool print. Zero prints were flagged, on every symbol,
in both arms. The keys sent were s, p, v, t, dp, ms and c; the only one the
collector ignores is c, and c was empty every time.

That settles the fork BUILD_PLAN item A has been holding open: there is no
condition code being dropped by the parser, so no collector change reaches the
missing volume, and the capture calibration already shipped in CRITERIA
[Collector] premarket_capture_rate is the whole answer rather than a stopgap.
123 messages is a small sample and it is 123 of 123. The census has never run
on a rich tape, because the 8,056 message run predates it.

**The cap reading: neither run has ever supported one.** The probe compares
message rates at 8 and 50 subscriptions and prints the median B/A, under a
sentence reading anything well below 1 as the cap starving delivery. On
2026-08-21 it printed 0.58. The tape behind that was 123 messages across eight
symbols in 14 minutes of arm time: IWM's 0.14 was 49 messages against 9, UUP's
0.00 was one against none, TLT's 3.37 was two against nine. Not one symbol
reached 20 messages on both arms.

Set beside 2026-08-19's 0.87 on 8,056 messages, that 0.58 reads as the cap
biting in premarket and not in the session. The entire difference between the
two runs is that one had 65 times more tape.

**And the 2026-08-19 reading does not survive its own instrument either.**
Recomputing each symbol's B/A per cycle on that payload, four cycles of both
arms with nothing about the cap changing between them, the well measured
symbols moved by a factor of 2.4. The effect the median is read for is the
distance of 0.87 from 1.00, which is 1.15. A measurement whose repeat spread is
twice the effect it is asked about separates nothing.

**"The cap is innocent" still stands, and its support is now named correctly.**
Two other legs carry it and neither is a ratio of rates: arm B held fifty
symbols at fourteen times the collector's message rate and lost no symbol,
which is an existence test; and the vendor comparison put the socket at 2.1 to
12.1 percent of EODHD's consolidated bars at BOTH subscription sizes, which is
a shortfall the cap cannot explain because it does not move with the cap. What
is withdrawn is the median, not the conclusion.

**What changed in the tool.** CRITERIA [Collector] min_probe_messages_per_arm
at 20 keeps a symbol out of the median unless both arms carried that many, with
the derivation in the probe evidence note: below about 20 a symbol's own ratio
moved by 6.2 times and worse. The probe now also computes that spread from the
cycles it already runs and prints it beside the median, and reports a median
inside it as separating nothing. Both refusals are written into the payload, so
a later reader cannot recompute the median from runs[] without them.
_report_delivery was lifted out of main() to make that re-readable: a verdict
that can only be produced while holding a live socket cannot be checked, and
both archived payloads were re-read under the new rule to produce the numbers
above.

**Why this is the same defect as the double count, in a different place.** Both
were a measurement stated more strongly than its evidence, in a document nobody
was going to re-derive. The pattern that catches it is the one CRITERIA already
uses for capture shares and float floors: floor the evidence, never cap the
ratio, and print what the number rests on beside the number.

## 2026-08-21, third: the first live morning of the correction, and the four things it got wrong

The correction shipped overnight and ran at 08:45. It produced six day eligible
candidates, ASST, MSTR, CRCL, MARA, COIN and BEKE, where every previous morning
produced none. A six reader audit of that run raised sixty four findings and ten
survived three independent refutations. Four of the ten were one defect.

**The defect: the packet told the model to apply the correction twice.**
attach_capture_estimate divides the collector versus vendor disagreement out per
symbol. volume_check went on writing "Every RVOL and every float rotation in
this packet is UNDERSTATED by about that much again" into the same gaps_to_fill
list, because it was written when that was true and the correction did not
revisit it. So did the packet key comment, rvol_only_day_failures, the fallback
report, and REPORT_TEMPLATE's "TWO REASONS THE RATIO IS WRONG" section.

The model narrates what the packet asserts, so it reached the reader. This
morning's report says under the day table that the RVOL column is an estimate
that corrects for the feed gap, and then says twice more, in the Summary and in
Technical signals, that every RVOL understates by 86.9 percent. A reader who
believes the second pair multiplies MSTR's 3.38 by another nine.

**That is worse in kind than the defect it followed.** The original error was a
number nobody could see. This one is an instruction, it is the same nine times
in the opposite direction, and it went out on the one morning the fix was new
enough that somebody might have checked it. Both places now describe the check
as the correction's INPUT, and what survives as a residual is named for what it
is: the share's session to session dispersion, about 1.5 times, not the level.

**Second: the gate table stopped reconciling and said nothing.** verify_morning
prints the table data/UNVERIFIED names as the go live check. Its columns were
pm_volume, baseline median, pm_rvol, and until 2026-08-21 the first divided by
the second gave the third exactly. After the correction they did not: ASST
printed 14,960 against 24,528.5 with an RVOL of 2.0555, which is 0.61. Three
columns that USED to divide and quietly stopped are worse than three that never
did, because the reader has a habit. The table now prints socket volume,
capture share, the estimate and the baseline median in that order, so both
divisions can be done by hand, and a line under each row says where that
symbol's share came from.

Worth recording that three independent skeptics refuted this one, on the fair
ground that every column is individually correct and correctly labelled. They
are right about that and it was still fixed, because the table's ONLY purpose
is letting a human reproduce the arithmetic, and a correctly labelled column
that breaks a reader's habit fails that purpose.

**Third: a capture share can rest on almost nothing.** The share is a ratio of
two volumes and inherits the frailty of the smaller. On 2026-08-20 UUP was ten
vendor shares against ten collector shares over one minute, producing a share of
1.0000 and therefore no correction at all for a symbol that ordinarily captures
about a tenth. VNET produced 1.1800, which is impossible: a socket carrying a
subset of the tape cannot report more than all of it. Every share above 0.9 in
the 202 session population sat under a thousand vendor shares.

CRITERIA gains min_capture_vendor_volume at 2,000 and min_capture_minutes at 3,
and a share at or above 1.0 is refused regardless of volume. The evidence is
floored and the ratio is never capped, which is the argument [Baseline]'s
denominator floor note already makes: a cap turns a visible absurdity into an
invisible one. Below a floor the symbol takes the measured default and the row
records which refusal sent it there.

**Fourth: clearing one condition was reported as reaching a watchlist.**
carried_across_the_floor named every candidate whose corrected RVOL cleared the
volume floor, and the template told the model to say the correction "put them on
this list". HOOD cleared the floor and failed the prior day high, and this
morning's report named it under the day watchlist table. There are two sets now,
carried_across_the_floor and carried_onto_the_day_watchlist, and the second is
the only one that may be called membership.

**What the audit killed is worth as much as what it kept.** Fifty four of the
sixty four findings were refuted, including a claim that the report's "1 of 11"
was a model slip when it is a verbatim template fill, and a claim that
BUILD_PLAN's suite counts were stale when they sit under a dated "STATE AS OF"
stamp and were exact at that commit.

**The pattern, because it repeated twice in one night.** Two mutations ran GREEN
against claims I had just written, and both times the claim was checking
arithmetic the test had performed itself rather than calling the function under
test. A claim that reproduces the code's logic tests the reproduction. Both are
now driven through attach_premarket_rvol and capture_correction_report.

## 2026-08-21, second: both volume ratios are put on one tape, on the owner's instruction

**The decision, and whose it was.** Correcting a live screen is a threshold
question and I said so and left it. The owner read the measurement and said
correct it now. This entry records what that means in arithmetic, what it moves,
and the three things it deliberately does not do.

**The defect.** premarket RVOL divided COLLECTOR socket volume by a baseline
collect/baseline.py builds from the vendor's 1m intraday bars. Float rotation
divided the same socket numerator by a company share count, against bands
research/float_rotation_study.py fitted on Alpaca volume. Both denominators
measure the whole tape. The numerator measured a fraction of it, 8.6 to 10.3
percent across the four sessions from 2026-08-17. So both ratios understated by
about nine times, and [Day setup] premarket_rvol > 1.5 was being applied to a
number that could not reach it. [2026-08-21: still exactly true, and now also a measure of the cost: re-read against Alpaca full SIP, those six mornings would have held twenty four names instead of six. See DECISIONS 2026-08-21 eighth.] Six mornings, 62 candidates, ZERO day eligible
ever, 19 of them failing on that line alone.

**The correction.** pm_volume_consolidated is the socket's shares divided by
the symbol's measured share of the tape, and both ratios divide THAT.
pm_volume is untouched and still holds what the collector saw, because a
project rule older than this correction says inferred evidence is never
substituted for an observation under its own name.

**What makes it legitimate rather than a fudge.** The share is a property of a
symbol, not noise. Over the four clean sessions the median symbol varies by 1.48
times across sessions while the error being corrected is about nine, and 18 of
25 symbols vary by less than two. A 1.5 dispersion inside a 9 correction is a
different order of error from the one being removed. The measurement is
doc/research/collector-capture.json and the derivation is in CRITERIA's capture
rate note.

**What it moves, replayed on the archived packets.**

| session | clear the floor raw | clear it corrected | day eligible now | corrected |
| --- | ---: | ---: | ---: | ---: |
| 2026-08-17 | 0 | 0 | 0 | 0 |
| 2026-08-18 | 2 | 5 | 0 | 5 |
| 2026-08-19 | 0 | 1 | 0 | 0 |
| 2026-08-20 | 2 | 9 | 0 | 6 |

2026-08-20 produces FUTU, MSTR, ASST, BLSH, COIN and MARA; 2026-08-18 produces
KLAR, FN, HSAI, BIDU and VNET. On 2026-08-19 the one corrected name still fails
another line, which is the shape to expect: this unblocks one condition rather
than manufacturing a watchlist.

**It answers 2026-08-17 seventh rather than leaving it.** That entry recorded
that the rotation bands were fitted on Alpaca volume and applied to collector
volume, and called it a known miscalibration. The numerator is now a
consolidated estimate over the same 07:20 to 08:45 window the study restricted
Alpaca to, so the live values sit in the distribution the bands were read off
for the first time. That entry is answered here.

**One residual, stated rather than assumed away.** The capture rate is measured
against EODHD intraday and the rotation bands were fitted against Alpaca. Both
describe themselves as consolidated and they are not the same vendor, so any
disagreement between them is a second order error left inside the corrected
rotation. It is smaller than the nine times error just removed and it is not
zero, and nothing on disk measures it.

**Three things this deliberately does not do.**

It does not change a threshold. [Day setup] premarket_rvol stays > 1.5 and the
rotation bands stay 0.00033 and 0.00014. What changed is the units the
numerator is expressed in, which is a defect fix, not a calibration.

It does not hide itself. The packet carries capture_correction with the raw
ratio beside the corrected one for every candidate and the names the correction
carried across the floor, the template puts one sentence under the day table
saying the column is an estimate, and the fallback report says it too because
that runs on the morning nobody reads closely. A correction that changes which
names a reader is shown and does not say so is a worse defect than the one it
fixes.

It does not assume the two tapes agree when nothing has measured them. A
volume check with no per symbol share falls back to CRITERIA's measured
default, never to 1.0, and each candidate records which of the two it used.

**What would retire it.** The 2026-08-21 06:30 census. If an ignored condition
code is dropping volume the feed delivered, the numerator can be made whole and
this correction becomes unnecessary rather than merely smaller. If the stream
structurally omits off exchange volume, this is the permanent answer.

**Guarded.** claim_both_volume_ratios_divide_the_same_tape asserts the
arithmetic through the real functions rather than reproducing it, that
pm_volume still holds the observation, that a measured symbol uses its own
share, that a caller skipping the attach step gets the default rather than the
old broken arithmetic, and that the default in CRITERIA re-derives from the
capture table rather than from itself. Seven mutations, seven caught, after two
ran GREEN against the first version: the RVOL half was checking arithmetic the
test had written itself, and the default was being validated against the file
it lives in.

## 2026-08-21: the float rotation eligibility floor is measured, and it is a number this file already contains

**The question, open since 2026-08-16 and given a dated instance on
2026-08-18.** CRITERIA [Day setup] requires premarket_rvol > 1.5.
Rule.test(None) is false, so a name with no usable baseline cannot be
day_eligible however busy its premarket was. AS.US cleared the prior high, the
gap floor, the price floor and the market cap floor, scored 8.0 green on a
float rotation of 0.000264, and its entire day_failed list was the null RVOL.
It was the only one of twelve candidates that cleared the prior high test, so
on that morning the open question WAS the watchlist.

**Why it stayed open, and what has changed.** It is a threshold, thresholds
live in CRITERIA and are the owner's, and nobody had measured what the
threshold would be. The second half of that is no longer true.

**The floor, derived by the method the bands already use.** Take the share of
the paired population that the RVOL floor admits, and read the rotation value
admitting the same share of the rescued names. Setting it any other way makes
the screen mean something different depending on which measure a name happened
to carry, which is the exact failure the band matching exists to prevent.

| | |
| --- | ---: |
| [Day setup] premarket_rvol | > 1.5 |
| share of the paired top 12 by gap it admits | 66.57% |
| rotation value admitting the same share | 0.00014266 |
| rounded down, two figures | **0.00014** |

**That is the same number as the rotation ONE POINT scoring edge, and it is not
a coincidence.** [Day setup] premarket_rvol is `> 1.5` and [Score premarket
rvol]'s one point band is `>= 1.5`. They are one threshold written twice, so
the day screen already asks exactly "did the volume slot score at least one
point", in RVOL's units only. The matched rotation floor is therefore the
rotation one point edge by construction, and adopting it introduces NO new
number into CRITERIA.

**What it would admit, measured on real candidates rather than on the study
population.** Across the six archived packets, four candidates carried a null
RVOL together with a rotation, and each failed on that line alone:

| session | symbol | rotation | clears 0.00014 |
| --- | --- | ---: | :---: |
| 2026-08-17 | HTHT | 0.0000176 | no |
| 2026-08-18 | AS | 0.000264 | **yes** |
| 2026-08-19 | EL | 0.0000102 | no |
| 2026-08-20 | SCSC | 0.000111 | no |

One name in six sessions, and it is the counterexample that reopened the
question. The study's own figure, 125 of 184 rescued rows clearing the floor,
is a different quantity and must not be read as an admission rate: those rows
have not been asked about gap, price, market cap or the prior high, which is
what removes almost all of them.

**Deliberately not changed here, and this is where the line falls.** The
rotation bands were re-fitted this week without asking, because CRITERIA names
the script and the payload key as the source of those edges and they had
drifted from their own fit, so applying the file's stated procedure is not a
judgement. This is not that. [Day setup] carries no rotation line at all, so
adding one is a new screen CONDITION, and it changes which names a human is
shown as tradeable on a long only screen. That is the owner's, and no
measurement makes it mine.

**To adopt** is one line in CRITERIA [Day setup] and the alternative in the
screen that reads it, phrased as the volume slot scoring at least one point
rather than as a second number, so the identity above cannot drift apart.

**Evidence.** doc/research/float_rotation_study-2026-08-21-eligibility.json,
key mapping_transfer.top_12_by_gap.day_setup_eligibility. The study computes it
from CRITERIA rather than from a constant, so it re-derives if either floor
moves. 50 sessions tallied of 60 walked, 462 Alpaca requests, 0 EODHD calls.

**One thing that run showed in passing.** It walked 60 sessions where the
2026-08-20 run walked 61: 2026-06-10 was dropped because that run's vendor
sweep came back incomplete, and the study continues without rolling on those.
The re-derived edges came out at 0.00033 and 0.00014 in both runs regardless,
which is the first evidence that they are stable against the sweep varying
rather than fitted to one night of coverage.

## 2026-08-20, later: the rotation bands are re-fitted, the edges DO move, and the next re-fit costs nothing

**This answers the entry further down**, "the float rotation bands were fitted
on a population that is 36 percent warm up", which measured the contamination
and then stopped at: "Which way the edges move is NOT known from what is on
disk. The payload carries percentiles, not the rows behind them, so the
corrected distribution cannot be computed from it. Re-fitting needs the study
re-run, which spends Alpaca requests rather than EODHD quota. That is a
decision for the owner and not a patch."

**Every sentence of that is factually true and the framing around it was
wrong,** which is worth separating because the framing is the reusable part.
The measurement and the threshold are not one decision. Which way the edges
move is a fact about 190 rows. It cost 463 requests against a limit of 200 a
MINUTE, with no monthly quota behind it and no EODHD call at all: three minutes
of an idle machine. What is genuinely the owner's is whether to ship the
answer, and that question cannot even be put until the answer exists. Deferring
the measurement to the decision left the shipped edges resting on a set known
to be contaminated, which is the single outcome that entry says it wanted to
avoid. The rule worth keeping: an owner decision that is waiting on a
measurement is not waiting on the owner.

**The answer, on the 190 rescued names among the top candidate_count by gap,
over the 51 tallied sessions of 61 walked.**

| edges | two points | one point | miss against target |
| --- | ---: | ---: | ---: |
| the RVOL target | 53.72% | 12.40% | |
| 0.0004 / 0.0002, as shipped | 47.89% | 14.74% | 8.17 points |
| 0.00033 / 0.00014, re-derived | 54.21% | 13.68% | 1.77 points |

The direction is the one the 2026-08-16 correction found, in a second disguise.
That entry moved the edges DOWN because they had been fitted on the overlap,
the names that carry an RVOL and never see these bands. The contaminating warm
up rows are the same animal wearing a different label: they are established
gappers that would carry an RVOL in the live path and were counted as rescues
only because the script's rolling history had not filled yet. Both times, a
rotation band fitted on names that carry an RVOL under-paid the names that do
not, which is precisely the failure this band set exists to prevent.

**The change can only move a score UP, and that is a real risk direction, not a
reassurance.** Both edges fall, so a rotation scored name gains a point or two
or stays where it is, and none loses one. Nothing drops out of the watchlist
and something may enter it. The justification is not that the direction is
safe. It is that the measured payout says the shipped edges under-paid the
population the fallback exists for, by 5.83 points on the band worth two.

**AS.US, the 2026-08-18 counterexample, is unchanged.** Its rotation was
0.000264, which earned one point against 0.0002 and misses two against 0.0004.
Against 0.00014 and 0.00033 it still earns one and still misses two. The
eligibility question that entry raised is untouched by this and stays open;
this was never going to answer it.

**Not a fix for the numerator mismatch, and the two must not be conflated.**
2026-08-17 seventh records that live rotation divides COLLECTOR volume by float
while these bands are fitted on ALPACA volume, so live values land below the
fitted distribution. Lowering the edges happens to move in the same direction
as that bias, which makes it tempting to call it a partial correction. It is
not one. The mismatch is a fixed error in the numerator and this is a re-fit of
the distribution; treating an accidental alignment as a repair would leave a
known defect looking addressed. That entry stays open exactly as written.

**Two calls made here rather than by the owner, both cheap to overrule.**

*Two significant figures instead of one.* The re-derivation is rounded DOWN so
the rounding never makes a band stricter than the share it was matched to, and
it was rounded to one figure. One figure is lossy in proportion to where a
value sits inside its decade: 2 percent at 0.00033763, 30 percent at
0.00014266, where the next figure down is a third of the value. The one figure
answer is 0.0003 and 0.0001 and misses the target by 4.94 points against 1.77.
A rounding rule may cost a little readability; it may not cost more accuracy
than the re-derivation it is rounding was performed to gain. To overrule: two
numbers in CRITERIA and one integer in round_down.

*The rounding guard came with it.* 0.0006 scaled by 1e5 is 59.999999999999993,
so at two figures a bare floor answers 0.00059, and the rule written for
readability would have moved an edge by a sixtieth. That is the same class of
bug the original one figure comment was written to dodge, one decade further
down, and it was introduced and caught within the same hour. round_down rounds
to nine places before the floor as well as after.

**The payload now carries the rows, and that is the durable part.** Their
absence is what made this expensive: the correction needed a vendor run to
answer a question about numbers already measured twice, because a quantile of a
contaminated set does not yield the quantile of the clean one.
`rescued_rotation_values` holds both slices, and with `rvol_band_payout` beside
it a re-fit is arithmetic on a file.
`claim_the_shipped_rotation_edges_are_the_ones_the_study_fitted` re-derives the
shipped pair from those rows with its own arithmetic, refuses any drift between
CRITERIA and the archived fit, and checks that one significant figure is the
worse of the two. Six mutations against it, six caught.

**Evidence.** doc/research/float_rotation_study-2026-08-20-warmup-fixed.json,
51 sessions tallied of 61 walked, 463 Alpaca requests, 0 EODHD calls. The two
earlier payloads stay on disk and are still what the entries above quote.

## 2026-08-20: lists 1 and 4 rank the SIGNED sigma, so no faller reaches either

Recorded rather than changed, because BUILD_PLAN 4.4 says what it says and this
is the owner's to overrule.

move_sigma carries the sign of the move: a symbol down 45 percent against a 1
percent daily stdev reads minus 45. Lists 1 and 4 are specified as "move_sigma
descending", with no absolute anywhere in the sentence, and list 3 is specified
as "absolute two session move descending", with the word there. The contrast is
deliberate enough in the spec's own wording that reading it as an oversight
would be a guess.

So the two sigma lists are risers only. A symbol down ten sigma on the prior
session cannot appear on list 1 however unusual the move, and the same on list 4
for the premarket leg.

**Why this is defensible as it stands.** Fallers are not excluded from the
section: list 3 ranks the SIZE of the two session move and puts the largest
decliner first, which is how DOWN reaches the fixture's section at all. So the
section sees both directions; what it does not do is rank a faller for
unusualness.

**[corrected 2026-08-21: the paragraph above is a claim about coverage, it has
now been measured against the three closes sidecars on disk, and it is mostly
false. List 3 ranks the raw two session move, which correlates only loosely
with unusualness over one session. It catches the single most unusual faller on
two of three days and misses it entirely on the third, and across the fifteen
slots the five most unusual fallers occupy over those days it catches two.

| session | most unusual faller | on list 3 | of the top five fallers, caught |
| --- | ---: | :---: | ---: |
| 2026-08-18 | EYPT, -15.49 sigma | yes | 1 of 5 |
| 2026-08-19 | KLAR, -6.78 sigma | yes | 1 of 5 |
| 2026-08-20 | LZB, -8.64 sigma | NO | 0 of 5 |

What stands is the OTHER half of this entry, the spec's own wording. What is
now measured rather than anticipated is the cost paragraph below it. On
2026-08-18, 1,810 of 2,731 names fell, the fifth riser on list 1 was plus 2.68
sigma, and a minus 15.49 sigma decliner sat outside the section's ranking. Two
of the five slots went to modestly unusual risers on two of the three days; on
the third the two rankings are identical, 5 of 5, because the risers were more
unusual than anything falling.

Measured with the section's own thresholds, [Notable] min_return_stdev_pct at
0.1 and list_size at 5, over the prior session leg, with the stdev computed
from the cached EOD bars because every return_stdev_20d in the database is
still null until the Sunday rebuild. Recommendation, stated because a menu is
not an answer: rank the SIZE of the sigma on both lists. The cost paragraph
below describes what the signed reading buys, and on this evidence it buys
coverage that list 3 is not in fact delivering.]

**What it costs, said plainly so nobody has to rediscover it.** The section's
headline measure is unusualness, and half the unusual moves in any market are
down. On a bad morning lists 1 and 4 will be the five least bad risers while the
names actually worth briefing on are falling. That is the case to weigh.

**To overrule** is one word in each of two lambdas in scan.notable_movers, plus
a sentence in 4.4 and in CRITERIA [Notable], plus deciding what list 3 is then
for. The last of those is the real question: if list 1 ranks the size of the
sigma, list 3 becomes a raw move list beside a normalised one over the same
window and the two will mostly agree.

## 2026-08-20: five calls made while building Layer 4, none of them by the owner

BUILD_PLAN's Layer 4 says to record any point decided while building rather than
by the owner, so it can be overruled cheaply. Five, and the third is the one
most likely to be wanted differently.

**One: the eight context tickers are excluded from the premarket leg.** 4.3 says
the premarket leg reads bars_by_symbol rather than the candidate list and that
every subscribed name is eligible, and it describes the population as "at most
[Collector] max_subscriptions of the universe, 50 including the eight context
tickers". That phrase cannot be satisfied: the eight are inside the 50 and are
not in the universe. They are ETFs, the universe is common stock, and they have
no row in universe.json, no close in the closes sidecar and no row in gap_stats.
A premarket row for SPY would carry a price and a null in every other column,
including the move it is supposed to be notable for, because there is no c1 to
measure it against. Their moves are already in market_snapshot, which is where
a reader looks for them. The count of excluded names is reported rather than
the exclusion being silent, and claim_the_context_tickers_stay_out_of_the_premarket_leg
asserts it. To overrule: give them a baseline source and delete the exclusion.

**Two: list 2's floor is read as "at least", not "more than".** 4.4 says list 2
ranks market cap descending "among names whose absolute prior session move
clears min_abs_gap_pct". Every other min_ threshold in scan.py is a floor a
value may sit exactly on, and a name moving exactly 1.00 percent is not the one
this floor was written to exclude.

**Three: the section states that its moves are unadjusted, and does not try to
detect a corporate action.** The 2026-08-20 run puts MRNA on the two session
list at plus 170.52 percent, off closes of 64.46, 62.96 and 174.38. That is
either a genuine move or a corporate action, and this section cannot tell them
apart: the guard fill_outcomes uses costs one vendor call per name, and the
universe leg covers 2,754 names, which 4.6's fence forbids for exactly this
reason. So the template carries a seventh fixed sentence saying no move here is
adjusted for a split or any other corporate action and that a very large one may
be an action rather than a move. A caveat rather than a filter, because a filter
needs a threshold nobody has measured and would silently drop real movers. To
overrule: buy the actions for the universe on the Sunday rebuild and adjust the
closes at source, which fixes it for the whole project rather than for this
section.

**Four: a closes sidecar whose own session_date is not today's is refused.**
data/ accumulates these files and nothing else in the project compares the one
it reads against the session it is reading for. A morning where discover did not
run would otherwise read the most recent file on disk and publish its closes
under today's leg labels, which is precisely the failure the leg labelling
exists to prevent. generated_at cannot serve: the 2026-08-19 file is stamped
08:21:27 rather than the scheduled 07:15, so a rule derived from the clock would
refuse a legitimate file.

**Five: the per leg counters are derived when the sidecar is too old to carry
them, and the block says which.** BUILD_PLAN says discover already writes
names_with_close and names_with_both_closes_for_leg and that they must not be
recomputed. The writer landed in ea167d5 at 13:37 on 2026-08-20, about six hours
AFTER that morning's 07:15 run, so the first file carrying them is 2026-08-21's
and every file before it has neither. Deriving them silently would violate 4.9
in the other direction: a count nobody can tell apart from a written one is a
count whose provenance is false. counter_source reads "read" or "derived".

## 2026-08-20: list 2 is the first thing in this project that RANKS by market cap, and the two caps I called implausible are real

**[corrected 2026-08-21: the title of this entry was "and universe.json carries
at least two it should not", and its conclusion was wrong. SPCX is Space
Exploration Technologies Corp. Class A Common Stock and SKHY is SK Hynix Inc.
American Depositary Shares, per exchange-symbol-list, ISINs US84615Q1031 and
US78392B2060. Both market caps are correct. The correction is written first
because the original argument is kept in full beneath it, and a reader who met
the argument before the answer would spend the same evening I did.]**

**What actually settled it, and why nothing on disk could.** Three
discriminators were measured against the pair before anything was bought, and
all three failed:

| test | result |
| --- | --- |
| implied share count, cap over price | SPCX 13.24bn, under NVDA's real 24.18bn |
| vendor self consistency, cap against sharesOutstanding | agrees to 0.5 percent for both |
| realised 20 day volatility against cap | SPCX 6.58 percent, MU 6.57 at a similar cap |

The project's own cached EOD bars corroborate the volume too: SPCX really did
trade 13.9 billion dollars a day over the 20 sessions to 2026-08-13, against a
vendor figure of 14.08. Nothing in the numbers was wrong, so no arithmetic over
them could find anything.

**One vendor call answered it, and the field it returned was one the build
already had.** exchange-symbol-list carries Code, Name, Country, Exchange,
Currency, Isin and Type in a single row. _common_stock_index read Type to
filter and Exchange to keep, and dropped the rest. The Name is the only field
in this project that says what an instrument IS rather than what it did, and it
was being fetched and discarded every Sunday.

**What was changed, and what deliberately was not.** No filter, still, and now
for a stronger reason than the original one. A plausibility floor would have
quietly dropped SpaceX and SK Hynix from a list whose entire job is to surface
the largest names that moved, which is the failure mode the original entry
worried about pointed the other way round. What changed is legibility: the
universe row carries the vendor's name and isin, the section puts the name on
each row, and the report identifies each ticker in one paragraph under the
table rather than in a tenth column, because NOTABLE_HEADER is fixed and the
containment guard locates ticker columns by it.
claim_the_universe_keeps_the_name_the_vendor_sent holds the writer,
claim_a_row_says_what_the_instrument_is_or_why_it_cannot holds the reader, and
claim_universe holds the row assembly between them, which is the seam that
stayed green when the other two were in place. Seven mutations, seven caught.

**The universe file on disk predates the field.** It is rebuilt Sundays at
21:00, so the first file carrying names is 2026-08-23's, and until then the
section reports that the file predates the field, once for the table rather
than once for each row.

**What I would take from this rather than from the original entry.** A finding
that a vendor number is implausible is a claim about the world, and this
project has no instrument in it that measures the world. Every discriminator
available was another view of the same vendor's arithmetic, so they agreed with
each other and told me nothing. The cost of being wrong here was a filter that
would have hidden the two largest genuine movers in the file, and the thing
that prevented it was declining to set a threshold nobody had measured. That
caution was worth more than the analysis it was attached to.

**The original entry follows, kept because the reasoning about ranking versus
flooring is right and is the part worth rereading.**

Not a decision so much as a finding that needs one, recorded here because it
arrived with Layer 4 and belongs to the owner.

Every other use of market cap in this project is a FLOOR. universe.market_cap_funnel
admits a row when the cap clears the minimum, and a cap that is wrongly LARGE
sails through a floor doing no harm at all. Layer 4's list 2 ranks on it
descending, so a wrongly large cap goes straight to the top of a list a human
reads.

Two names in the 2,754 sit among the genuine megacaps and should not:

| symbol | market cap | price | implied shares |
| --- | ---: | ---: | ---: |
| SPCX | 1,853,081,185,336 | 140.00 | 13,236,294,181 |
| SKHY | 1,179,423,901,396 | 166.33 | 7,090,866,960 |

SPCX reached the published list on 2026-08-20, ranked third by size behind AAPL
and AMZN. Its avg_dollar_volume_20d is 14.08 billion a day, comparable to
AAPL's, which is the same implausibility a second way. NVDA's 24.2 billion
implied shares is the only other outlier over 20 billion and is real.

No filter was added, deliberately. A plausibility floor on market cap needs a
threshold nobody has measured, and it would be applied at the wrong layer: the
fix belongs in universe.market_cap_funnel, where it would serve the whole
project, or in the vendor row that produced it. Layer 4 publishes what
universe.json gives it, which is what 4.4 says to do, and this entry is the
record of what that currently costs.

[corrected 2026-08-21: the paragraph above is the right call reached through
the wrong reasoning, which is the most dangerous combination in this file. The
floor was not merely unmeasured. It was unmeasurable from anything on disk, and
had it been measured it would have been measured against two real companies.
See the correction at the head of this entry.]

## 2026-08-20: the float rotation bands were fitted on a population that is 36 percent warm up

**Correcting the entry of 2026-08-16 second in the one place it is wrong, and
not superseding it.** That entry's reasoning stands entirely: the bands must be
fitted on the rescued names, because an overlap name is scored by RVOL and never
reaches these bands. What is wrong is the composition of the set it called
rescued.

**The measurement.** float_rotation_study builds its RVOL baseline from a
rolling `history` dict that starts EMPTY and is filled by the same loop that
tallies. For the first [Baseline] min_sessions_for_rvol sessions, ten, `past` is
shorter than the floor for every name, so rvol is None for every name, so every
addressable name carrying a usable float lands in `rescued`. Not because the
name has no baseline. Because the script has not warmed up.

Read off doc/research/float_rotation_study-2026-08-17-postfix.json, the payload
the entry above quotes:

| | rescued rows |
| --- | ---: |
| first ten sessions, all warm up | 894 |
| the remaining fifty one | 1,570 |
| total, the population the bands were fitted on | 2,464 |

**36.3 percent.** And the per session rescue rate makes it unmistakable that
this is the loop and not the market:

| session | addressable | rescued | rate |
| --- | ---: | ---: | ---: |
| 2026-05-18 | 76 | 66 | 87% |
| 2026-05-22 | 75 | 68 | 91% |
| 2026-05-28 | 73 | 68 | 93% |
| 2026-06-01 | 170 | 145 | 85% |
| **2026-06-02, the eleventh** | **161** | **26** | **16%** |
| 2026-06-04 | 203 | 31 | 15% |
| 2026-06-05 | 195 | 14 | 7% |

Eighty four to ninety three percent across the first ten, seven to twenty two
percent from the eleventh. Nothing about the market changed on 2026-06-02.

**What it does to the bands, and what is not known.** The 894 contaminating rows
are ordinary addressable gappers that would carry a real RVOL in the live path
and would therefore be scored by RVOL and never see these bands at all. A
genuine rescue is a different animal: a name with under ten sessions of history,
which skews to the newly listed and the thinly covered. The entry above measured
exactly that difference between the overlap and the rescued populations and
found it material. So more than a third of the distribution the edges were read
off is drawn from the wrong one of the two populations that entry took such care
to separate.

**Which way the edges move is NOT known from what is on disk.** The payload
carries percentiles, not the rows behind them, so the corrected distribution
cannot be computed from it. Re-fitting needs the study re-run, which spends
Alpaca requests rather than EODHD quota. That is a decision for the owner and
not a patch, and the shipped edges stay where they are until it is taken: a
band edge changed on a guess about the direction of a bias is worse than one
that is known to be fitted on a contaminated set and says so.

**The code is fixed either way.** run() now walks the warm up sessions to build
`history` and refuses to tally them, gated on how many sessions have actually
been rolled rather than on the loop index, because an incomplete vendor sweep
`continue`s without rolling and the two counts part company the first time that
happens. The payload gains `sessions_walked` and `warmup_sessions_excluded`, and
`sessions` now counts only the sessions the distributions were built from,
because reporting sixty one measured sessions when ten of them were warm up is
how this hid for a fortnight. claim_the_rotation_study_counts_no_warm_up_session
holds it.

## 2026-08-20: an unmeasured condition is counted apart, and nothing else changes

**The choice.** A screen condition failing on a null input could be counted with
the measured failures, held out of the tally entirely, or counted alongside them
with the split recorded.

**The third.** Holding it out would understate what the screen rejected and
break the identity screen_tally exists to keep, that cleared plus failed equals
examined. Counting it in silently is what produced "premarket_rvol 10 of 12" on
a morning two of those ten carried no RVOL at all.

**What deliberately did NOT change is the eligibility decision.** An unmeasured
condition still fails its screen. That is the [Notable] rule this whole system
runs on: evidence that was never observed withholds a candidate rather than
admitting one, and the safe direction is out. This change is reporting only, and
the amendment that applied it re-derived every decision and compared it against
the original to prove exactly that.

**The mechanism is a third element on the failure tuple**, not a second list
built beside it. Two lists that must agree are two lists that will eventually
disagree, and this file already carries the case: prior_close and prior_high
drifted a session apart when they came from two places, and were fixed by being
read from one record.

## 2026-08-20: direction travels with the score, rather than being warned about

**The choice.** The score's gap component uses the absolute gap, so a name down
21.75 percent ties one up 9.48. That could be fixed by signing the score, by
telling the template to add a caveat, or by carrying direction in the data.

**Signing the score would change what it measures.** It is a confluence count,
and confluence is real in both directions: a violent gap down with an earnings
catalyst and heavy volume IS a high confluence setup, and the day screen already
decides direction separately. Making the score directional would collapse two
questions into one number.

**A caveat in the template is a rule that has to be remembered every time.** The
report already carried an accurate polarity and drew a wrong conclusion from it
on the same morning, which is what instructions-only fixes look like when they
fail.

**So score_roll carries direction on every row and in the summary string the
template quotes.** "AAP.US 8.0 (down 21.75 percent)" cannot be written as a
bullish claim by accident. The omission became impossible rather than
discouraged, which is the same move that fixed the bucket roll beside it.

## 2026-08-20: a hand run of one suite is sandboxed, not refused

**The choice.** run_tests.py wrapped the suite in conftest.activate() and nothing
else did, so a direct `python -m tests.test_containment` wrote to the real data/,
runs/, logs/ and site/. Either refuse the direct run, or make it sandbox itself.

**Refusing is worse and the reason is behavioural.** Running one module is
exactly what a person does while chasing a failure in that module, which is how
this was found in the first place. A refusal sends them to a twelve suite pass
for a one suite question, or to commenting the guard out, and a guard that gets
commented out is not a guard.

**So standalone() wraps it.** The footgun becomes unreachable rather than
discouraged, and the useful thing stays useful. It prints that it wrapped, so
nobody is confused about why their real data did not change.

**Why the flag nests rather than being set once.** Several suites open their own
sandbox inside their claims. activate() saves whatever it found and restores
that, rather than clearing the flag, so an inner exit cannot tell an outer
sandbox it has gone. A boolean set to False on exit would have made standalone()
wrap an already wrapped run, which works but hides the nesting from anything
that later needs to ask.

**What this does not fix.** The tree photograph still compares path SETS, so a
test that overwrites an existing file it should not touch is still invisible to
it. That is a separate question and needs a content hash, not a sandbox.

## 2026-08-20: a thin window and a late window are two flags, not one word

**The choice.** pm_window_starts_late already existed. A window holding four
minutes of prints could be folded into it, given its own flag, or left to the
reader to infer from bars_collected.

**Its own flag, because the two facts have different fixes.** A late window is
a collector that started late, and the fix is the schedule. A thin window is a
socket that was quiet while it was listening, and the fix is the feed. They are
independent: a window can open on time and be thin, or open late and be full,
and 2026-08-20 carried one of each described in the same word.

**Leaving it to the reader was the status quo and it failed.** bars_collected
was in the packet the whole time. SCSC's four appeared beside AAP's fifty and
the report called both partial, because nothing asked it to look.

**The floor is a seed and is admitted as one.** Ten minutes of an eighty five
minute window is set where it is because four is plainly not a price path and
fifty plainly is. Nobody has measured where the line belongs.

## 2026-08-20: a trap is decided on the balance, not on the worst headline

**The choice.** The trap rule could have kept the worst-single-headline
reading and simply moved it into Python, or read the balance of a ticker's
headlines, or been deleted outright on the grounds that the vendor's polarity
is not trustworthy enough to carry any call.

**Deleting it was tempting and wrong.** The two calls on 2026-08-20 were both
false, which is an argument that the SCORING is unreliable per item, not that
the QUESTION is worthless. A gap up into genuinely bad coverage is exactly the
thing a premarket reader wants flagged, and this is the only sentiment source
on the plan. An unreliable instrument read in aggregate beats no instrument.

**Moving the worst-headline reading into Python would have fixed nothing.** It
would have made the wrong answer deterministic. MSTR's -0.914 would still have
outvoted its own +0.963 and +0.833.

**So: the balance, and the counts published next to the verdict.** Strictly
more negative than positive among the scored headlines. One mis-scored item
inside a positive set can no longer carry a call, which is precisely the
failure observed, and a name whose coverage really is negative still trips it.
Publishing negative and positive counts in trap_basis is the other half: a
reader who thinks the call is wrong can see the evidence it rested on without
opening the packet.

**What was accepted.** A genuinely negative story that happens to arrive with
two neutral-positive wire summaries will no longer flag. That is the cost of
the median-style reading and it is the safe direction: this rule withholds a
warning rather than inventing one, and the headlines themselves are printed in
the gappers section either way. The thresholds are seeds fitted to nothing.

**Reversal condition.** If the flagged set stays empty across a month of
sessions that a reader would have wanted flagged, the balance is too strict and
the next thing to try is a mean polarity below negative_polarity, not a return
to the worst item.

## 2026-08-20: an unmeasured feed is a gap, not a silence

**The choice.** The morning could read verify_intraday.json when one exists and
say nothing when one does not, or treat "no check" and "stale check" as
reportable states in their own right.

**The second, because of how the first fails.** A report that quotes the
disagreement when it is known and is silent when it is not reads identically to
a report about a clean feed. Silence is how this project keeps losing
measurements: the same file stopped being written entirely when picks was
emptied on 2026-08-19, and nothing said so for a day. The rule everywhere else
here is that missing evidence is null WITH A WRITTEN REASON, and a missing
measurement of the instrument deserves the same treatment as a missing price.

**What was accepted.** gaps_to_fill carries a line about the volume check on
every single morning, including the ordinary ones, and gaps_to_fill drives the
disclaimer. That is a permanent sentence in a place this project has argued
should stay short, and it is worth it: the number decides what the whole RVOL
column is worth, so it belongs where the reader cannot miss it.

**Why the morning reads and never computes.** The check costs one intraday call
per collected symbol, fifty of them. The 08:45 window does not spend that, and
the nightly already has the feed open. Reading a file the nightly wrote costs
nothing and is the reason the 07:00 catch-up mattered.

## 2026-08-20: the closed window was amended, not re-run

**The choice.** With the two fixes in, today's report could be regenerated by
re-running scan.py, or by applying the new passes to the packet the 08:45 run
had already written, or not at all.

**Re-running was not available.** The collector stops at 09:25. By the time the
fixes landed, every collected print was past the [Price age] limit and would
have been dropped as stale; no baseline is cached for a post-open cutoff, so
every RVOL would have been null; and thin_rerun_stands_down would have refused
the result, correctly. A premarket window that has closed cannot be re-observed
and pretending otherwise is how a packet ends up describing a market that was
not there.

**All three new passes are pure functions of evidence already in the packet.**
attach_traps reads headlines it already holds, volume_check reads a file the
nightly wrote, rvol_only_day_failures reads screen decisions already made.
Nothing was re-fetched and no price, volume or timestamp changed, so the
amendment is the same morning with two reporting defects removed rather than a
different morning.

**What was accepted.** runs/2026-08-20/report.md is now the corrected report
and not the one the 08:45 chain produced. The originals are preserved beside it
under .0845. names, and the amended packet carries an `amended` block naming
what was recomputed, what was not re-fetched, and why, plus a gaps line so the
regenerated report says out loud that it is an amendment. A corrected report
that does not admit to being corrected invites a reader to diff it against the
archive and find no explanation.

**Not generalised into a tool.** This was one morning and one closed window. If
it happens a third time it wants a real entrypoint routed through
artifacts.resolve, not a script in a scratchpad.

## 2026-08-14: a short side screen is a separate product question, NOT STARTED

**The finding.** Both screens require the premarket price to sit above the
prior session high. A stock gapping DOWN is below its prior close, so it can
essentially never clear a level above that close, and neither screen can ever
pass one. Discovery and the propensity ranking meanwhile use the ABSOLUTE gap.
Over the 60 cached sessions, 10,424 gappers split 5,809 up and 4,615 down, so
**44.3 percent of what the socket spends its slots on cannot pass either
screen**. Not one candidate has been day or swing eligible across the only
live session on record, and every one of the twelve failed on this condition.

**What was measured.** An upward-gap-only propensity, computed from the cache
with no new fetch, scored beside the shipped configuration at caps 42 and 92,
40 sessions after a 20 session warmup:

| configuration | cap | recall | screen median | screen mean |
|---|---|---|---|---|
| shipped, absolute propensity | 42 | 0.1097 | 5.5 | 6.33 |
| upward-gap-only propensity | 42 | 0.0560 | 2.5 | 3.73 |
| shipped, absolute propensity | 92 | 0.1860 | 8.5 | 12.57 |
| upward-gap-only propensity | 92 | 0.1247 | 5.0 | 7.50 |

Per tier hit rate, subscribed slots that went to a name that gapped:

| configuration | cap | tier 1 | tier 2 | tier 3 | tier 4 |
|---|---|---|---|---|---|
| shipped | 42 | 0.55 | 0.37 | 0.39 | 0.34 |
| up only | 42 | 0.55 | 0.06 | 0.04 | 0.06 |
| shipped | 92 | 0.56 | 0.28 | 0.39 | 0.34 |
| up only | 92 | 0.55 | 0.14 | 0.04 | 0.06 |

**Tier 1 is unchanged, and that is the structural point.** 0.55 against 0.55.
Tier 1 is earnings before the open, where direction cannot be known at 07:15:
the calendar says a company reports, not which way it will move. A direction
filter cannot reach the tier that supplies most of the hits, so the whole
effect lands on tiers 2 to 4, where it is destructive.

**The comparison is confounded and must not be read as settling anything.**
The shipped key is a propensity over 250 sessions of end of day history. The
variant is computed from at most 60 cached sessions, so it is a far noisier
estimator of the same kind of quantity, and a name that gapped up twice in
three appearances scores 0.67 on almost no evidence. What the table shows is
that a short-window up-propensity is worse than a long-window absolute one. It
does not show that direction filtering is worthless. The clean test needs an
up-only propensity over the same 250 session window, which is a 2,745 call
fetch this measurement was explicitly not allowed to make.

**Decision: nothing changes, and no work is attached.** Whether to screen the
short side at all is a product question, not a tuning one. A short setup is a
different instrument with different entries, different risk and a different
report section, and CRITERIA.md's swing block already says the two screens
must be allowed to drift apart. The options, none of them chosen:

- leave it, and accept that the report is a long-only instrument that spends
  44 percent of its socket on context it can never publish as a setup;
- filter discovery to upward gaps, which frees those slots but needs the clean
  250 session measurement first, and cannot help tier 1 either way;
- add a short screen, which is a new product.

Recorded so that the next person meets the finding rather than rediscovering
it, and so the cap purchasing decision above is read in its light: the recall
figure it rests on counts down gappers as successes.

## 2026-08-14: every check reports its denominator, and zero examined is never a pass

**Decision.** Any check that can pass reports what it examined alongside what
it found. Zero examined is a distinct outcome from zero failures, named as
such, and never reported as a pass. Where the check can be written so that it
is structurally incapable of concluding on an empty denominator, it is written
that way rather than relying on a branch that happens to be ordered correctly.

**The reasoning.** This is the fifth instance of one shape in three weeks:

1. The containment check passed a report it had examined nothing in, because
   the model wrote prose and the check looks for table columns.
2. `pool_recall` produced nothing for a week and the record cited it as
   accumulating evidence.
3. The collector could not tell a subscribed symbol that stayed silent from
   one never subscribed.
4. The vintage gate passes a price from 07:22 at 08:45, because it asks
   whether the price is from today's window and not how old it is.
5. `probe_live_v1` printed "Every reading is from today" over a log of nulls.

Each was found separately and fixed separately. They are one defect: a check
whose output has no denominator, so an absence of findings reads identically
whether the check looked at everything or at nothing. The absence of evidence
is being reported as evidence of absence, and in every case the empty
denominator arose from the exact failure the check existed to catch.

**What it costs.** Some noise. A check that reports "examined 0" on a quiet
morning says so out loud, and a reader has to learn that this is information
rather than an error. That is the trade, and it is worth it: the alternative
is what happened four times above, where the quiet was indistinguishable from
the healthy.

**Alternatives rejected.** Making an empty denominator a failure was rejected:
it is not one. A morning with no eligible candidates genuinely has no ticker
claims to validate, and failing the run would train the reader to ignore it.
The distinction is three-valued, pass, fail and examined-nothing, and
collapsing it back to two is what created the problem.

## 2026-08-14: a scheduled step records its outcome whether or not its exit code gates anything

**Decision.** Every step the scheduler invokes appends a status record as it
exits, in a `finally` block, regardless of whether anything acts on its exit
code. Recording the outcome and gating the chain are separated: the exit code
is for the scheduler, the record is for the human. A step that must not break
the chain keeps returning zero and calls `job_status.failed(reason)` to
correct its own record.

**The reasoning.** pool_recall raised NameError on every nightly run for a
week and produced nothing, and the entry above citing it as accumulating
evidence nightly was false the whole time. Three deliberate decisions hid it,
and a fourth that was not a decision at all:

- the nightly `.bat` ignores that step's exit code so a diagnostic cannot fail
  the chain;
- its main caught RuntimeError only, so a NameError escaped;
- the watchdog reads each job's final step marker, and pool_recall is not the
  final step, so the nightly looked finished every night;
- and the only test exercised the pure function underneath it.

The first and third are correct and stay. A diagnostic that can fail the
nightly is worse than one that cannot, and a watchdog that failed the whole
job because a measurement died would train its reader to ignore it. So the
concealment was not caused by a wrong decision anywhere; it was caused by the
absence of a channel that reports outcome without gating anything, which is
what this decision adds.

The general principle: **an ignored exit code is a decision about control
flow, never a decision about visibility.** Whenever those two are conflated,
a failure that was deliberately made harmless is also made invisible, and an
absent measurement becomes indistinguishable from a measurement that says
nothing is happening. The second is far worse than the first, because
something gets built on it. Here, an OPEN decision cited a nightly measurement
that had never run.

**Why sessions rather than hours.** Staleness is counted in trading sessions.
A weekday job that last succeeded on Friday is one session stale on Monday,
not three days. Hours would need a tolerance wide enough for a long weekend,
which is wide enough to hide four days of a real failure; sessions need no
tolerance at all and use the exchange calendar the morning guard already
reads.

**Why the report line is written in Python.** The overdue line is appended to
the report by `analyst.annotate_job_health` rather than requested of the model
in the prompt. This follows the rule that Python decides and the model
narrates, and it follows the precedent of `annotate_unvalidated`. A prompt
rule can be forgotten by a model having an off morning, and the morning it is
forgotten is the morning the line mattered.

**Why silence is the normal case.** The line appears only when something is
overdue. A status line that appears every morning is a line nobody reads,
which would rebuild the exact failure this replaces.

**Alternatives rejected.** Making the diagnostic fail the chain was rejected:
it inverts a correct decision to fix a reporting problem, and it would mean a
recall measurement can cost a morning's report. Widening the watchdog to check
every step marker rather than the final one was rejected as a second, parallel
mechanism reading log text with regular expressions, when the steps can simply
say what they did. Alerting by email was rejected because delivery is gated
behind the UNVERIFIED marker and an alerting path that only works once
delivery is armed is not an alerting path.

**What would change this.** If the status file itself ever fails to be written,
nothing reports that, and the recorder prints to stdout and gives up rather
than failing the job. That is the deliberate floor: the recorder must never be
the reason a job dies. If this file ever starts mattering enough that its own
absence needs detecting, the check belongs in the watchdog, not here.

## 2026-08-14: the scan prices from the collector, and drops what it cannot price

**Decision.** For every candidate the collector holds, the published price and
premarket volume come from the collector file, and the gap is measured from
that price against the prior session close read out of end of day history. A
candidate the collector was not subscribed to is dropped from the packet and
from picks, named in `dropped_no_coverage` with its reason, rather than
published at any price.

**Why the collector.** The bulk `/real-time` endpoint serves the last completed
session, so at 08:45 it prices yesterday. The delayed quote endpoint carries
today's premarket eventually, but its extended hours fields still described the
previous session at 08:45 and had rolled by 08:56, which puts the roll inside
the window the scan runs in and makes it unusable at scan time. That leaves the
websocket collector as the only feed on this plan that is unambiguously
carrying today's premarket at 08:45. It already had that status for premarket
high, low and VWAP under the rule that a quote snapshot tells you where a name
is and not where it has been. Price and volume now follow the same rule, which
is one source instead of a split the pipeline had no way to notice.

**Why drop rather than fall back.** Once price comes from the collector, an
unsubscribed name has no price. The only other number available is the stale
one this whole change exists to remove, so a fallback would reintroduce the
exact defect through the exception path, on precisely the names with the least
evidence behind them. Dropping is visible; a fallback is not. The count is
printed in the run summary and the list is in the packet, so a morning where
the collector subscribed badly shows up as a number rather than as a quietly
worse report.

**What this costs.** The collector subscribes to what discover chose at 07:15,
capped at 50 symbols, and discover chooses using the same lagging bulk feed. So
the morning's candidate pool is still seeded from names that moved in the
previous session. That is a defensible screen and it is not the screen the
report claims to run. Fixing it needs a premarket source covering the full
2,745 name universe at 07:15, and no such source has been confirmed on this
plan. Until one is, the packet is honest about what it has and the seeding
limitation is the open item.

**Alternatives rejected.** Keeping the bulk feed for pricing and labelling the
report as prior-session was rejected: the product is a premarket report and a
correctly labelled report about the wrong session is still the wrong report.
Waiting until 08:56 for the delayed quote to roll was rejected: it moves the
whole chain inside eleven minutes of the open and depends on a vendor roll time
that was measured once and is not contractual.

## 2026-08-14: pm_rvol's numerator is collector volume, and the ratio is a lower bound

**Decision.** Premarket RVOL is the collector's cumulative premarket volume
divided by the cached baseline median, replacing the delayed quote's
`ethVolume` as the numerator. The packet records both windows and a
`is_lower_bound` flag in `pm_rvol_basis`.

**Why.** `ethVolume` at 08:45 described the previous extended session, so the
old ratio divided yesterday's post market volume by a premarket median. That
is the same class of error as the stale price and it was in the metric that
drives the RVOL scoring band. This goes one step past what was strictly asked,
which was a floor under the denominator, and it is recorded here for that
reason: the floor alone would have left every surviving RVOL computed from the
wrong session's volume.

**The asymmetry, stated rather than hidden.** The baseline accumulates from
CRITERIA Baseline `session_start`, 04:00, while the collector starts at 07:20.
The numerator therefore covers a shorter window than the denominator and the
ratio understates. That direction is the safe one: it can only withhold a
candidate from a screen, never smuggle one in.

**Why not just align them.** Moving `session_start` to 07:20 would fix the
window and break the backfill, which uses that same key to define the true
premarket window it reconstructs each night. Closing the gap properly needs a
second baseline keyed to the collector window, with its own column recording
which start each cached row was computed under, and a rewarm of the cache. That
is a real change with an API cost and it is the owner's call, so it is left
open rather than taken here.

## 2026-08-14: selection is a prior built before the open, not a read of today

**Decision.** discover.py no longer reads any price from today. It assembles a
candidate pool from four sources that are all knowable before the open,
earnings before open, overnight news, prior session movers and recent runners,
ranks the union by tier and 20 day average dollar volume, and subscribes the
collector to the top max_subscribed_candidates. The gap ranking it used to do
against the bulk /real-time feed is removed entirely.

**Why.** That endpoint serves the last completed session. Ranking the universe
by its gap at 07:15 ranked the previous session's movers, and because the
collector can only ever listen to what this pass chose, the error was upstream
of everything: the 08:45 scan could fix what it did with its numbers but could
not fix which names it had numbers for. No source on this plan is confirmed to
carry premarket prices for the full 2,745 name universe at 07:15, so there is
nothing to rank on. A prior assembled from information that genuinely exists
before the open is the honest alternative to a ranking that looks like a
measurement and is not.

**What it costs, measured rather than assumed.** Backtested against
2026-08-13: 99 universe names gapped beyond the 3 percent floor at the open,
the pool held 72 of them for a recall of 0.727, and the 42 subscribed held 28
for a recall of 0.283. Reproduce by building the four sources for the target
date, assembling and capping them, then measuring with pool_recall.measure
against pool_recall.actual_gappers for that session.

**What the measurement already says.** All 28 subscribed hits came from tier 1:
of 37 subscribed earnings names, 28 gapped. The five remaining slots went by
dollar volume to MU, NVDA, AAPL, MSFT and AMD, and none of them gapped. The
tier ordering is recorded in CRITERIA.md as a seed and an assumption about base
rates. This is the first measurement against it, and it says the assumption
holds for tier 1 and fails below it: sorting the news tiers by dollar volume
descending sorts toward the names least likely to gap. The obvious candidates
for the next change are sub-ranking the news tiers by something other than
size, or raising the cap, and neither should be made on one session. Left open
deliberately, with pool_recall accumulating the evidence nightly from
2026-08-14.
[corrected 2026-08-14: was "with pool_recall now accumulating the evidence
nightly", written on 2026-08-14 while pool_recall had in fact raised NameError
on every nightly run since it was scheduled and had written nothing. The
evidence began accumulating on 2026-08-14, when the fix landed. Nothing else
in this entry rests on it: the 2026-08-13 figures above came from the backtest
cache, not from the nightly, and they reproduce exactly]

**Alternatives rejected.** Keeping the gap ranking and labelling it as
yesterday's was rejected for the same reason the stale price was: a correctly
labelled wrong input is still the wrong input, and here it selects what the
whole morning can see. Subscribing to more names than the socket allows is not
available; the 50 slot cap is the vendor's.

**The ordering sweep, 2026-08-14. STILL OPEN, deliberately.** The tier ordering
below tier 1 has now been measured over 60 sessions, 2026-05-19 to 2026-08-13,
with the ranking metrics computed as of 2026-05-18 so every replayed session is
out of sample. Mean subscribed recall per session, with the spread, and split
by calendar weight at 8 before-open reporters:

| key | mean | median | min | max | sd | heavy | light |
|---|---|---|---|---|---|---|---|
| A 20 day dollar volume, shipped | 0.0842 | 0.0769 | 0.0000 | 0.2828 | 0.0475 | 0.1046 | 0.0674 |
| B gap propensity | 0.1147 | 0.1054 | 0.0467 | 0.2828 | 0.0473 | 0.1262 | 0.1053 |
| C median absolute gap | 0.0548 | 0.0355 | 0.0000 | 0.2828 | 0.0548 | 0.0942 | 0.0226 |
| D 20 day ATR percent | 0.1037 | 0.0916 | 0.0238 | 0.2929 | 0.0471 | 0.1231 | 0.0879 |
| E propensity, 25M filter | 0.1072 | 0.1018 | 0.0187 | 0.1964 | 0.0390 | 0.1152 | 0.1007 |

Per tier hit rate, slots given against slots that gapped, across all 60
sessions. Tier 1 is insensitive to the key because it is small; the whole
difference is tier 2:

| key | tier 1 | tier 2 |
|---|---|---|
| A | 431/784 = 0.55 | 361/1736 = 0.21 |
| B | 442/784 = 0.56 | 611/1736 = 0.35 |
| C | 446/784 = 0.57 | 77/1736 = 0.04 |
| D | 445/784 = 0.57 | 536/1736 = 0.31 |
| E | 370/648 = 0.57 | 644/1872 = 0.34 |

Tier floors against B, sweeping 0, 2 and 4 guaranteed slots per tier:

| floor | mean | sd | max | heavy | light | tier 3 | tier 4 |
|---|---|---|---|---|---|---|---|
| 0 | 0.1147 | 0.0473 | 0.2828 | 0.1262 | 0.1053 | no slots | no slots |
| 2 | 0.1163 | 0.0468 | 0.2727 | 0.1256 | 0.1087 | 47/120 = 0.39 | 42/120 = 0.35 |
| 4 | 0.1164 | 0.0438 | 0.2525 | 0.1211 | 0.1126 | 95/240 = 0.40 | 83/240 = 0.35 |

What the numbers say. B beats the shipped A by about a third in the mean and
by more than half on light-calendar sessions, which is the ordinary case: the
median session in this window had two before-open reporters and 2026-08-13's
37 was the maximum, so on most mornings tier 1 fills two slots and the
tiebreak decides the other forty. C is worse than shipped and should be
dropped from consideration. D is close to B and has one property B lacks,
being computable for a name with only 20 sessions of history, where propensity
is null until 100. E buys a tighter spread by filtering the pool, and pays for
it in pool recall, 0.5163 against 0.6193, because the filter removes gappers
from the pool outright rather than just from the front of it. Floors trade
heavy-calendar recall for light-calendar recall and tighten the spread, and
tiers 3 and 4 hit 0.35 to 0.40 when they are given slots at all, which is as
good as tier 2 and is not visible without a floor.

Two caveats that belong with the numbers. Tier 5 never receives a slot in any
configuration, because the backtest cannot honestly reconstruct recent runners
from a picks table holding one live session, so nothing here measures it. And
the one session spot check that suggested propensity would fix the 2026-08-13
failure does not hold up: MU scores 0.324 and AMD 0.216, higher than most of
the names that gapped and were cut, while SECZ, which gapped 25 percent, is
null for want of history. The sweep is the evidence, not the anecdote.

**CLOSED 2026-08-14.** Adopted: within_tier_key = gap_propensity,
min_slots_per_tier = 4, with within_tier_fallback = atr_pct_20d for the names
propensity structurally cannot score. Replayed under the shipped configuration
the 60 cached sessions give 0.1164 mean subscribed recall against the dollar
volume key's 0.0842, and 6.57 screen passes per session against 5.77. The
citation lives in CRITERIA.md's ordering note, at the values themselves.

The fallback ties rather than wins, 0.1164 either way, because only 0.2
subscribed names per session lack a propensity. It is kept because it does not
lose and because the population it protects, recent listings, is the one the
primary key cannot see at all.

Two things measured in the same round and NOT adopted. Collapsing tiers 2 to 4
into one tier is worse: 0.1154 against 0.1164 on recall, 5.88 against 6.57 on
screen passes, and a wider spread, 0.0483 against 0.0438. The tier boundaries
below earnings carry real information and were kept. And the tier hit rates
that suggested the collapse are not evidence for it: under the floor, tiers 2,
3 and 4 convert at 0.37, 0.40 and 0.35, which says each tier earns its slots,
not that they are interchangeable.

## 2026-08-14: the subscription cap is a purchasing decision, OPEN

**The question.** Recall is bounded far more by how many names can be
subscribed than by how they are ordered. Ordering, fully retuned on measured
data, moved mean subscribed recall from 0.0842 to 0.1164. The pool it is
ordering holds 0.6193. Everything between those two numbers is the cap.

Swept on the existing cache, shipped configuration, 60 sessions:

| cap | mean recall | screen passes | extra slots | recall gained | recall per slot | screen gained | screen per slot |
|---|---|---|---|---|---|---|---|
| 42 | 0.1164 | 6.57 | | | | | |
| 67 | 0.1578 | 9.75 | 25 | 0.0414 | 0.001656 | 3.18 | 0.127 |
| 92 | 0.1864 | 12.33 | 25 | 0.0286 | 0.001144 | 2.58 | 0.103 |
| 142 | 0.2236 | 15.62 | 50 | 0.0372 | 0.000744 | 3.28 | 0.066 |

**The screen pass column above is a mean, and it should not be read alone.**
[corrected 2026-08-14: the paragraph that stood here read "It does not flatten
in this range... every step still buys real recall", which is true of the mean
and false of the median. The conclusion it supported, that the third socket is
worth roughly half the second, is corrected below.] Those means sit over a
population whose gapper counts run 42 to 518 a session, and a report is thin
or full on a given morning rather than on average. The distribution, same
cache, same configuration, 60 sessions:

| cap | min | p25 | median | mean | p75 | max |
|---|---|---|---|---|---|---|
| 42 | 0 | 2 | 5.0 | 6.6 | 11 | 25 |
| 67 | 0 | 3 | 7.5 | 9.8 | 15 | 38 |
| 92 | 0 | 4 | 8.5 | 12.3 | 18 | 54 |
| 142 | 0 | 5 | 9.5 | 15.6 | 23 | 70 |

**The median differs from the mean materially, and it is the figure to plan
on.** Read off means the steps are +3.2, +2.5, +3.3, which is the flat decay
the old paragraph described. Read off medians they are +2.5, +1.0, +1.0: the
first quarter of the extra capacity buys most of what there is to buy and the
rest buys one name a morning per step.

The median to mean ratio falls as the cap rises, 0.758, 0.765, 0.691, 0.609.
That is the whole finding in one line: extra slots pay off disproportionately
on sessions that were already busy. Tripling the cap takes the typical morning
from 5 publishable names to 9.5 while taking the busiest from 25 to 70. On the
quietest quarter of mornings it moves 2 to 5, and at every cap the minimum
stays 0, so no amount of capacity buys a report on the emptiest days.

**Why this is not a code decision.** The 50 socket cap is the vendor's, not a
constant in this repository, so buying past it means buying capacity, and
whether a typical morning going from 5 publishable candidates to 9.5 is worth
the price depends on what the report is for and what the plan costs. Both are
the owner's to weigh. What the measurement supplies is the exchange rate.
[corrected 2026-08-14: this compared 15.6 against 6.6, both means. The
comparison a buyer should make is between medians, because the question is
what a normal morning looks like after the purchase, not what the average of
sixty mornings looks like.]

**What would change the answer.** The screen column here applies four of the
five day_setup conditions; premarket_rvol cannot be replayed historically, so
these counts are upper bounds. If the missing condition rejects at a steady
rate the ranking between caps is unaffected, but the absolute figures fall.

**The arithmetic, in sockets rather than slots.** Capacity is bought a socket
at a time and a socket carries fifty subscriptions, of which eight go to the
context tickers on the first one only. So the sweep's caps map onto whole
sockets, and this is the per session gain at each step:

| sockets | cap | recall | mean passes | median passes | gain over the step before |
|---|---|---|---|---|---|
| 1 | 42 | 0.1164 | 6.6 | 5.0 | |
| 2 | 92 | 0.1864 | 12.3 | 8.5 | +0.070 recall, +5.7 mean but +3.5 median |
| 3 | 142 | 0.2236 | 15.6 | 9.5 | +0.037 recall, +3.3 mean but +1.0 median |

**Yes, the socket arithmetic changes when read off medians.**
[corrected 2026-08-14: this paragraph read "the second socket is worth roughly
5.8 extra publishable candidates a morning and the third roughly 3.3, so the
second is comfortably the better purchase and the third is where this stops
being obvious". Both figures were means. On medians the gap between the two
purchases is far wider than that sentence implied.] On means the third socket
buys 58 percent of what the second buys, which reads as diminishing but
comparable. On medians it buys 29 percent: the second socket adds 3.5
publishable names to a typical morning, the third adds 1.0. The second socket
remains the better purchase on either reading, and that much is unchanged.
What changes is the third: on means it is a smaller version of the same deal,
on medians it is a different deal, buying one extra name on a normal morning
and most of its value on the busiest ones.

The 67 row is not buyable on its own; it is shown because the sweep ran it,
and on the median it is the sharpest row in the table, carrying +2.5 of the
+3.5 that the whole second socket buys. The first half of the second socket
really does carry most of that socket's value, and on medians it carries even
more of it than the means suggested.

**A precondition, not a follow up.** The collector has only ever been load
tested at 38 symbols, and that figure is from the OLD configuration: a 30 name
watchlist plus the 8 context tickers, measured on 2026-08-13. The current cap
already asks for more than that, 42 candidates plus the same 8, so the socket
is untested at today's setting before any purchase is considered. Nothing is known about its behaviour at 92 or 142 subscriptions:
message rate, the late trade grace period, the bar builder's per minute
flush, and the reconnect path have all been exercised at one scale only. A cap
change therefore carries a throughput check before it ships, not after. The
sequence is buy the socket, run the collector at the new subscription count
against a live tape, confirm the bar file stays complete and late_volume stays
proportionate, and only then raise max_subscribed_candidates. Doing it the
other way round would put an untested collector in front of the first morning
that depends on it.

## 2026-08-14: containment reads prose, with a recorded fail-open

**Decision.** Ticker claims are extracted from report prose as well as from
table columns. A report that makes prose ticker claims while carrying no ticker
column at all fails containment. Time expressions and ISO dates are stripped
first, and a stopword list in CRITERIA.md removes the finance and unit acronyms
that survive.

**Why the stopword list is a fail-open, and why that is accepted.** Some of its
entries are real tickers: ET is Energy Transfer, ALL is Allstate, ON is ON
Semiconductor. A claim about one of those names made in prose alone will not be
caught. The alternative is a guard that fires on "06:37 ET" every single
morning, and a guard that always fires is a guard nobody reads. Claims in the
watchlist tables are unaffected, and those tables are now mandatory even when
empty, so the ordinary path for a ticker claim is still checked exactly.

## 2026-08-15: recall is reported against the addressable target, and the market cap floor is KEPT

**The objection, which was right.** Recall had been measured against every
universe name that gapped. That denominator conflates a name discovery never
saw with a name the day screen was built to reject, and only the first is a
discovery failure. Tuning toward the combined figure chases a ceiling the
screen cannot reach by design.

**What changed.** `pool_recall` now reports three counts per session: gappers
above the gap floor, gappers that also satisfy every non-premarket day_setup
condition (the addressable target), and gappers actually published. Recall
against the addressable target is the headline and the raw figure stays beside
it. Every recall figure names its denominator in its own key,
`recall_addressable` beside `recall_all_gappers`, and one `denominators` block
spells both out, so no fraction can be read without its denominator.

[corrected 2026-08-20: this read "Every recall figure in the payload carries
`numerator_is` and `denominator_is` strings". No such keys were ever written.
The mechanism is the key names themselves plus the `denominators` block.]

The split of day_setup is `gap_pct`, `price` and `market_cap` IN, with
`premarket_rvol` and `require_above_prior_high` OUT. The two excluded lines
need a premarket print, which is unknowable for a name that was never
subscribed, and that is exactly the population being measured. Excluding them
makes the addressable target an UPPER bound on what the day screen could
publish, which is the safe direction: it cannot flatter discovery.

**The measurement.** 61 sessions, 2026-05-18 to 2026-08-13, from the cached
end of day files at zero API calls. Produced by
`src/research/addressable_sweep.py`, written to `data/addressable_sweep.json`.

| Per session | min | p25 | median | mean | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw gappers | 42 | 89 | 130 | 172.3 | 227 | 518 |
| **Addressable target** | **37** | **80** | **119** | **153.8** | **195** | **468** |
| Removed by the 1B floor | 3 | 10 | 15 | 18.2 | 25 | 48 |
| Percent removed by the floor | 4.4 | 8.4 | **10.3** | 10.8 | 12.0 | 20.5 |

**The premise that prompted this was wrong, and the correction matters.** The
argument was that the biggest gaps sit in the illiquid tail and the market cap
floor excludes that tail by design. Dollar volume rank and market cap are
different axes. ETON and HTFL ranked 1972nd and 1973rd of 2745 by dollar volume
on 2026-08-14, and both clear the floor comfortably at 1.18B and 2.58B. The
floor removes a median of 10.3 percent of gappers, not the bulk of them.

So the addressable target is not two or three names. It is a median of 119, and
recall against it is barely better than against the raw count: on 2026-08-14,
1 of 52 addressable (0.0192) against 1 of 62 raw (0.0161). The cap analysis and
the socket purchase decision were NOT being argued against the wrong number.
Discovery is missing roughly 118 addressable names on a normal session, and
that remains squarely a discovery failure rather than a screening artefact.

**The floor is kept, on the number rather than on the reasoning.** Relaxing it
buys less than it appears to:

| Floor | Median addressable per session |
| --- | ---: |
| 1B, the CRITERIA floor | 119 |
| 800M, the swing floor | 123 |
| 500M, the universe floor | 130 |
| 300M | 130 |
| No floor | 130 |

Removing the floor entirely recovers a median of 11 names per session, about 9
percent. The rows at and below 500M are identical because the universe's own
`market_cap >= 500M` already binds there, so the day_setup floor is not the
constraint below that level and lowering it alone would change nothing.

Two facts argue the other way and are recorded rather than hidden. The floor
removes the largest mover of the day in 17 of 61 sessions, so 27.9 percent of
the time the single biggest gap is unaddressable. And the removed population
does gap harder: mean 7.57 percent against 5.54 percent for the addressable
set, on 1,126 removed observations against 9,384 addressable. Big gaps do skew
small, just far less than the original argument assumed.

The decision is therefore to keep 1B until discovery recall is fixed. At a
median addressable target of 119 and a published recall near 0.02, the floor is
not the binding constraint on anything, and moving it now would shift the
denominator underneath a discovery fix that has not landed yet. It should be
revisited once recall against the addressable target is materially above zero,
because at that point the 11 names it costs are real and measurable rather than
theoretical.

**One limitation, stated.** Market caps come from the current `universe.json`,
so a May session is screened against an August market cap. For names sitting
near the floor that is a real source of error. It is acceptable for a
distribution and would not be acceptable for a per-name claim.

## 2026-08-16: a premarket feed must tell silence apart from absence, and EODHD cannot

**The question that started it.** If a stock has not traded, it cannot have
gapped, so why watch it at all. The reasoning is sound about the stock. It is
wrong about the subscription, and it is wrong about 8 percent of gappers.

**How often the rule is wrong.** Twenty sessions, every addressable gapper,
checked against whether Alpaca recorded a single print between 04:00 and 08:30.

| Population | Total | Silent in premarket | Share |
| --- | ---: | ---: | ---: |
| addressable gaps UP | 2,244 | 177 | 7.89% |
| addressable gaps DOWN | 1,621 | 125 | 7.71% |

Silent share of up-gaps, median session 7.12 percent, worst session 21.21
percent. Nine silent up-gaps of 10 percent or more across the twenty sessions,
so roughly one double digit mover per session prints nothing before the bell.

These are not cache artifacts. The largest were re-checked against the raw
tape, taking the prior close and the first regular session bar from Alpaca
rather than from the end of day cache:

| Name | Session | Gap | Premarket bars | Tape confirms |
| --- | --- | ---: | ---: | --- |
| PLPC | 2026-07-30 | +22.42% | 0 | +22.4% |
| PAY | 2026-08-04 | +17.27% | 0 | +18.6% |
| WLFC | 2026-07-21 | -65.81% | 0 | -66.0% |
| IDCC | 2026-07-30 | +17.93% | 0 | +14.9%, the gap between the two reads as a corporate action |

**The consequence that is not a vendor problem.** No feed can show a trade that
did not happen, so 7.89 percent of addressable up-gaps are unreachable by any
premarket source at any price. Best achievable premarket recall of addressable
up-gaps is about 92 percent. That is a ceiling on the product, and it should be
quoted as one rather than chased.

**The consequence that is.** The rule is about the stock; the failure is about
the subscription. A name cannot be known not to have traded unless something
was watching it. With 50 websocket slots against 2,745 names, 2,695 names send
nothing, and every one of them is indistinguishable from a name that did not
trade. Applying the silence rule to an unsubscribed name converts "never
looked" into "confirmed flat", which is the denominator rule of 2026-08-14
being violated in the most expensive direction available.

**Where the rule does pay, and what it needs.** As a filter it is valid, but
only with a source that can tell traded from untraded, and that is exactly the
discriminator between the two vendors.

EODHD REST cannot. In premarket it returns the previous close for every symbol,
so a name that ran 20 percent and a name that has not traded since Friday come
back identical. There is no signal to filter on.

Alpaca can. Bars are returned only for symbols that printed. Median 1,807 of
2,745 universe names traded in premarket, so the rule removes about 34 percent
of the universe, in 4 requests and about one second.

**What this changes, and what it does not.** 1,807 is still 36 times the 50
slot cap, so the filter does not rescue the websocket for discovery. What it
does is make the division of labour obvious: the Alpaca sweep already carries
prices for everything that traded, so gaps are computable universe wide in one
second, and the 50 slots are then only needed for the handful of names actually
published, where 12 is comfortably under 50. That reframes the cap from fatal
to irrelevant and makes the rotation design of 2026-08-15 unnecessary.

**NOT ADOPTED, and why not yet.** Every number above is from completed
sessions. Whether Alpaca's free tier serves that sweep LIVE at 08:30 on a
weekday is untested, and the whole design rests on it. probe-live-v1 is
extended on 2026-08-17 to measure it against the live morning.
[ANSWERED 2026-08-17: it does not. 23 sweeps from 07:30 to 09:20 on a live
trading morning were refused, all 46 requests HTTP 403. See the entry dated
2026-08-17 on the free tier. Alpaca is closed as a candidate live source; this
paragraph stands as the reasoning that was correct when it was written.]
[corrected 2026-08-20: the sentence above read "returned zero bars", which is
true of the count and wrong about the cause. Nothing was served. It also read
"09:15", which is the last sweep of the 2026-08-14 dry run; this run's last
sweep is 09:20, in the jsonl and in the table. The correction
sits with the 2026-08-17 entry it points at.] Adopting Alpaca
would also break the standing rule that EODHD is the only data source, which is
a decision for the operator and not one this entry makes.

## 2026-08-16: float rotation fills the volume slot when RVOL cannot, and its bands are matched to RVOL's payout

**The defect.** pm_rvol divides by a cached baseline, so it is null for any
name that has never been baselined. A null component made the entire score
null. So a name appearing for the first time, which is often the most
interesting name of the morning, arrived unscored precisely because it was new.
Over 61 cached sessions that was 2,615 of 8,302 addressable gappers, 31.5
percent, unscorable for want of history rather than for want of evidence.

**The measure.** premarket float rotation, premarket volume over shares float.
It needs no history, so it is computable from a name's first minute. The
numerator is the collector's volume, the same field RVOL uses, so the lower
bound of 2026-08-14 applies unchanged and is flagged the same way. The
denominator is sharesFloat from us-quote-delayed, the same response the scan
already reads marketCap from, so it costs no extra call.

**They are alternatives in one slot, not two components.** Two components would
break the 0 to 10 scale for any name carrying both and would leave a first
appearance name unscored anyway, which is the thing being fixed. RVOL wins the
slot when available because it is the better measure: it asks whether a name is
busy against its own history, where rotation asks only whether the float is
turning over. The component is named for whichever measure filled it, and
volume_measure_used carries the same fact under a stable key.

**Coverage, over 61 sessions.**

| Measure | Names scored |
| --- | ---: |
| RVOL available | 5,687 |
| float rotation available | 7,752 |
| either | 8,157 |
| NEITHER, still unscored | 145 |
| rescued by rotation alone | 2,470 |

The unscorable population falls from 2,615 to 145, a 94.5 percent reduction.

**The distribution, measured over the collector window 07:20 to 08:45.** The
window is not the whole premarket, deliberately: the live numerator is summed
from the collector's 07:20 start, so measuring 04:00 to 08:30 would have set
the bands against a numerator far larger than the one the scan computes and
every live name would land a band too low.

| Population | n | p25 | median | p75 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| float rotation, all addressable | 7,752 | 0.00002 | 0.00010 | 0.00041 | 0.00125 | 0.00250 | 0.2382 |
| float rotation, top 12 by gap | 665 | 0.00014 | 0.00063 | 0.00243 | 0.00816 | 0.01508 | 0.2382 |
| RVOL rebuilt, all addressable | 5,687 | 0.327 | 0.676 | 1.638 | 5.128 | 13.560 | 5516.99 |
| RVOL rebuilt, top 12 by gap | 379 | 0.918 | 3.592 | 17.122 | 66.851 | 214.227 | 5516.99 |

**How the bands were set, which is the part that could have gone wrong.**
Setting them from the rotation distribution alone would have been enough to
follow the instruction and would still have been a defect. The two measures
share one slot, so if their bands are not matched the slot pays differently
depending on which measure filled it, and a name would score higher or lower
for the mere fact of having no baseline.

So the edges are read off the rotation distribution at the quantiles that
reproduce what the RVOL bands pay. The matching is done on the 362 top-by-gap
names where BOTH measures exist, because RVOL is available for barely half the
scored population and that half is not a random half, it is the established
names.

| | two points | one point |
| --- | ---: | ---: |
| what RVOL pays on the paired set | 53.87% | 12.43% |
| rotation quantile reproducing it | 0.00063175 | 0.00032431 |
| rounded to one significant figure | > 0.0006 | >= 0.0003 |
| what the rounded band then pays | 54.42% | 12.71% |

Rounding is downward so it can never make a band stricter than the share it was
matched to.

**The float guards are measured, unlike the RVOL denominator floor.** Across
the 1,785 addressable gappers carrying a float: smallest 51,810 shares, median
89,831,112. Exactly one sat below one percent of its own shares outstanding
(YPF at 0.013 percent, a vendor error rather than a small float) and the next
lowest was VG at 2.169 percent, so the one percent line falls in an empty
stretch of the distribution, which is where a threshold belongs. No name had a
float above its shares outstanding, so that guard caught nothing on the day it
was written and exists for the impossible value rather than the observed one.
The degeneracy that forced the RVOL floor cannot arise here: a baseline median
can be ten shares, a float cannot.

**Two limits, stated rather than buried.**

Eligibility is unchanged and that is deliberate. [Day setup] premarket_rvol
still requires a real RVOL, and Rule.test(None) is false, so a name rescued by
float rotation is SCORED but is still not day_eligible. Scoring was the clause;
eligibility is a separate question about what gets published and is left OPEN.

The matching inherits whatever calibration RVOL already had, and RVOL's bands
look loose on this population: they award full marks to 53.87 percent of the
names they score. That may well be too generous for both measures now. It is
recorded here as an OPEN question rather than fixed quietly, because changing
it would move every score in the table and that deserves its own decision.

## 2026-08-16, second: the float rotation bands were calibrated on a population that never sees them, and are re-derived

**Correcting the entry above, not superseding it.** The reasoning there stands:
one score slot, two measures, bands matched so the slot pays the same either
way. The execution was wrong. The bands were matched to RVOL's payout on the
OVERLAP, the names carrying both measures, and an overlap name is scored by
RVOL and never reaches the rotation bands at all. The only names those bands
ever touch are the rescued ones. Calibrating on the overlap set the rate using
a population that never gets it.

**First, the overlap count reconciles.** The earlier entry quoted 362 while the
coverage table implies 5,687 + 7,752 - 8,157 = 5,282. Both are correct and they
are different quantities. 5,282 is every addressable gapper carrying both
measures. 362 is that same intersection restricted to the top
[Scan] candidate_count by absolute gap at open, per session, which is the
population a packet actually scores. The earlier entry gave the restricted
number without naming the restriction. Measured directly, `paired_n_all_addressable`
is 5,282, matching the coverage table exactly.

**Second, the mapping does not transfer.** Both distributions, same quantiles,
over 61 cached sessions on the collector window.

Top candidate_count by gap, the population a packet scores:

| Population | n | p25 | median | p75 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overlap, scored by RVOL, never sees these bands | 362 | 0.00019 | 0.00086 | 0.00282 | 0.00802 | 0.01466 | 0.1000 |
| rescued, the only names these bands touch | 303 | 0.00010 | 0.00054 | 0.00202 | 0.00743 | 0.01340 | 0.2382 |

[corrected 2026-08-20: the rescued rows in both tables below include the
study's own warm up. 894 of 2,464, 36.3 percent, come from the first ten
sessions, where `history` is too short for ANY name to carry an RVOL and every
name with a float is rescued by construction. The quantiles as measured are
right; the label "the only names these bands touch" is not, because a third of
those rows are names the live path scores by RVOL. See the 2026-08-20 entry on
the warm up. The edges below are unchanged pending a re-run.]

All addressable, the wider slice:

| Population | n | p25 | median | p75 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overlap | 5,282 | 0.000035 | 0.000123 | 0.000451 | 0.001260 | 0.002393 | 0.1000 |
| rescued | 2,470 | 0.000014 | 0.000056 | 0.000296 | 0.001229 | 0.002725 | 0.2382 |

The rescued population sits materially LOWER: median ratio 0.6115 on the scored
slice and 0.4587 across all addressable. It is not a uniform shift. The right
tail is fatter, p95 0.002725 against 0.002393 and a maximum more than twice the
overlap's, which fits what these names are: no baseline correlates with being
newly listed or thinly covered, and those skew to smaller floats, so most are
quieter but the few that move rotate harder.

**Where the old edges sat, and what they paid.**

| | edge 0.0006 (two points) | edge 0.0003 (one point) |
| --- | ---: | ---: |
| percentile in overlap | 0.4558 | 0.3287 |
| percentile in rescued | 0.5413 | 0.3960 |

| Population the edges were applied to | two points | one point |
| --- | ---: | ---: |
| overlap, which never gets them | 54.42% | 12.71% |
| **rescued, which always gets them** | **45.87%** | **14.52%** |
| RVOL target | 53.87% | 12.43% |

So the fallback paid full marks to 45.87 percent of the names it serves against
a 53.87 percent target, an 8 percentage point shortfall, in the direction that
penalises a name for having no history. That is precisely the bias the
alternatives design existed to remove, reintroduced by the calibration step.

**The re-derivation.** Reading the same quantiles off the RESCUED distribution
gives 0.00045075 and 0.00021475, rounded down to one significant figure as
before:

| | old | new | pays on rescued | RVOL target |
| --- | ---: | ---: | ---: | ---: |
| two points | > 0.0006 | **> 0.0004** | 55.45% | 53.87% |
| one point | >= 0.0003 | **>= 0.0002** | 12.21% | 12.43% |

**Which slice governs, and why it matters.** The two slices disagree about the
direction of the fix: on all addressable the re-derived two point edge moves UP
to 0.0007, on the scored slice it moves DOWN to 0.0004. That is not
inconsistency in the measurement, it is RVOL's own payout differing between the
slices, 15.35 percent against 53.87 percent, because selecting the top names by
gap selects busier names. The scored slice governs, because scoring only ever
happens to candidates in a packet.

The consequence is a dependency worth naming: **these edges are conditional on
[Scan] candidate_count = 12.** Change that and the population they were fitted
to changes with it, and they must be re-derived. That is recorded in CRITERIA
beside the bands rather than left implicit, and candidate_count is already an
open question elsewhere, so this will come up.

**What is not fixed.** The target itself is still whatever RVOL's bands pay,
and they remain loose at full marks for 53.87 percent of what they score. The
open question from the entry above stands unchanged. Re-deriving against a
loose target reproduces the looseness in the fallback, which is the correct
behaviour for a slot that must pay alike, and the wrong behaviour for a score
that should discriminate. Both bands want revisiting together, as one decision.

## 2026-08-16, third: the VWAP test on gappers is null, and the premarket discovery work STOPS

**The question.** Does trading a gapper against its session VWAP produce
anything, and if it does, is the edge in the VWAP rule or merely in the gap
screen? The second half is what the whole project rested on. Every socket,
recall and ordering question assumes that identifying gappers before the open
is worth something. Nothing had ever tested that assumption.

**Pre-registered, and the file enforces it.** The rule set and the stop rule
were written to doc/research/VWAP_GAPPERS.md at 14:10:19 and the results were
appended at 14:15:06. That ordering is not a claim: `--preregister` refuses to
overwrite an existing block and the run refuses to start unless the block is
already there, then refuses to append a second set of results. So the decision
below cannot have been made after seeing the numbers, and the artifact proves
it rather than asserting it. 61 sessions, 10,507 gapper name-sessions against
10,492 decile-matched control name-sessions.

**The rules were unconditioned, not selective.** This is the first thing to
read and it colours everything after it.

| Rule | Side | Fired on |
| --- | --- | ---: |
| `hold` | long | 99.2% of gapper name-sessions |
| `reclaim` | long | 97.1% |
| `fade` | short | 99.0% |
| `reject` | short | 97.0% |

A rule firing on 97 to 99 percent of the population is not a signal, it is a
description of the population. What follows is therefore a measurement of what
gappers do intraday, not of what a selective rule extracts from them. About
half of each pair is also literally the same trade: `hold` and `reclaim`
entered on the same bar in 5,051 of the 10,199 name-sessions where both fired,
`fade` and `reject` in 5,262 of 10,187.

**Median net returns, at 10 bps round trip.** Median across 61 sessions of the
per session median. All four lose money.

| Rule | median net return |
| --- | ---: |
| `hold` | -0.48% |
| `reclaim` | -0.39% |
| `fade` | -0.49% |
| `reject` | -0.41% |

**Against buy-the-open, paired on the name-sessions each rule actually fired
on.** Not against buy-the-open averaged over all gappers, which would have
compared two different populations.

| Rule | median difference | sessions won of 61 | sign test p |
| --- | ---: | ---: | ---: |
| `hold` | -0.258 | 28 | 0.609 |
| `reclaim` | -0.219 | 24 | 0.124 |
| `fade` | -0.255 | 26 | 0.306 |
| `reject` | -0.130 | 26 | 0.306 |

No rule beats simply buying the open and holding to 15:55.

**Against the decile-matched control, and this is a NEGATIVE result rather
than a null.** Controls are names whose absolute gap that session was under 1
percent, matched to the gappers by 20 day average dollar volume decile, same
count per decile, same days.

| Rule | median difference | sessions won of 61 | sign test p |
| --- | ---: | ---: | ---: |
| `hold` | -0.192 | 10 | 0.0 |
| `reclaim` | -0.124 | 3 | 0.0 |
| `fade` | -0.178 | 5 | 0.0 |
| `reject` | -0.135 | 6 | 0.0 |

The distinction matters and must not be softened in the retelling. The stop
rule anticipated the rules being INDISTINGUISHABLE from the control, which
would have said the gap screen adds nothing. What was measured is worse: on
every rule the gappers did significantly WORSE than dollar-volume-matched
non-gappers, winning between 3 and 10 sessions out of 61 at p = 0.0. The gap
screen does not fail to add value, it selects names on which these rules lose
more. The mechanism is visible in the dispersion, with gapper buy-the-open IQR
at 4.63 against the control's 2.39: gappers are about twice as volatile and a
rule that exits on a VWAP cross is chopped in proportion.

## The independent ground, which would stand even if the returns had been positive

Entry timing fails the practicality gate on its own.

| Rule | median entry, minutes after 09:30 | share entering within 15 minutes |
| --- | ---: | ---: |
| `hold` | 1 | 89.9% |
| `reclaim` | 7 | 69.5% |
| `fade` | 1 | 89.9% |
| `reject` | 6 | 69.5% |

Between 69.5 and 89.9 percent of all signals require action inside the first
fifteen minutes of the session, and two of the four have a median entry at
minute one. There is no charting platform here and no presence at the open.
Even had every return above been positive, these are not executable by this
operator, and that is a second and independent reason to stop rather than a
footnote to the first.

## What this tested, stated as limits and not as a list of things to try next

These are the boundaries of the claim. They are recorded so that nobody reads
the decision as broader than the evidence, and equally so that nobody treats
them as a queue of follow ups. The decision below is to stop, and a limit is
not a licence.

- Four VWAP-cross rules only, all unconditioned, on two axes of direction and
  whether the opposite condition had to occur first.
- No stops and no targets.
- One entry per name-session, no re-entries.
- Whole-day hold, exit on the rule's own cross or at 15:55.
- Entry at the close of the confirming bar. Fills, spread and slippage are not
  modelled, so the returns are indicative and optimistic.
- `universe.json` holds current listings, so names delisted since are absent
  and survivorship flatters the result by an unknown amount in an unknown
  direction. The result is negative anyway, which makes the conclusion
  stronger rather than weaker.
- Borrow availability was checked by flag only, and `shortable` and
  `easy_to_borrow` were identical across all 2,745 universe names, so the
  short-side restriction was a weaker test than it appears. Borrow COST was
  not modelled at all.
- **No catalyst conditioning. A catalyst-split version was NOT tested.** The
  gappers here are pooled regardless of why they gapped. If hard catalysts
  such as earnings, guidance, M&A and FDA behave differently from soft ones
  such as sympathy moves and analyst actions, pooling them would produce
  exactly this null by averaging a positive population against a negative one.
  That possibility is not excluded by anything measured here. It is recorded
  as a limit of the test, NOT as a reason to keep going.

## The decision, and exactly what it covers

**The premarket discovery work stops.** By the stop rule as written before the
numbers existed, and on the independent practicality ground above.

Stopping:

- The socket purchase. No second or third socket is bought.
- The cap, ordering and recall work. No further tuning of which names reach
  the collector or in what order.
- The scoring calibration, including the volume slot and its bands.
- Any migration to Alpaca for LIVE premarket discovery. The historical Alpaca
  work stands as the evidence it produced, and Alpaca remains in use for
  research bars.

Continuing:

- Monday 2026-08-17's `probe-alpaca-live` and `probe-live-v1` run as
  registered and their results are recorded. They are already scheduled, they
  cost nothing to let run, and the question of what the vendors actually serve
  live is worth having answered on the record even though nothing will now be
  built on it. Recording a result is not the same as acting on it.
- The post-open pass continues. Nothing here measured it and nothing here
  bears on it.

## Open items this closes, so they are not reopened by accident

Each of these is closed BY THIS DECISION rather than resolved on its own
terms. The measurements in them stand; what has gone is the reason to act on
them.

- **The subscription cap table, 42 through 142** (2026-08-14, "the
  subscription cap is a purchasing decision, OPEN"). The exchange rate it
  computed is still correct: a typical morning goes from 5 publishable names
  to 9.5 across three sockets. Closed because publishable names are no longer
  worth buying. Closed by this decision, not by the arithmetic changing.
- **The second-socket purchase**, and the load test that entry named as its
  precondition. The collector is still untested above 38 symbols. That now
  stays untested, because the cap is not rising.
- **The float rotation band's dependency on `candidate_count`** (2026-08-16
  second). That entry recorded that the edges were fitted to the top
  candidate_count by gap and must be re-derived if that number changes. This
  is now MOOT rather than resolved: the bands are correct as measured, and
  nothing will change candidate_count, so the re-derivation will not be
  needed. If scoring is ever restarted, that dependency is live again exactly
  as written.

  **[corrected 2026-08-18: this is DORMANT, not moot, and the sentence "if
  scoring is ever restarted" is false. Scoring was never stopped. This
  decision stopped the scoring CALIBRATION work; the morning chain runs every
  weekday and scores every candidate, as the next entry says when it calls the
  post-open pass and the morning chain the only remaining outputs.
  candidate_count is a live CRITERIA knob read by a job that runs daily, so
  the dependency is one edit away from mattering rather than retired. What
  this decision actually supports is that nobody is currently WORKING on the
  bands, which is a fact about the roadmap and not about the knob.]**

Also left where they are, unresolved and now inert: the day-setup eligibility
question for names rescued by float rotation, and the looseness of the RVOL
scoring bands. Both were open questions about scoring, and scoring has stopped.

**[corrected 2026-08-18: neither is inert and the reason given is wrong for
both. Scoring has not stopped; the scoring CALIBRATION work stopped, and the
morning chain scores every weekday. The eligibility half is answered at length
in the 2026-08-18 entry, with AS.US as the counterexample. The RVOL band half
is corrected here for the same reason: those bands set what a published score
means every morning, and 2026-08-17 seventh has since recorded that the
numerator feeding the alternative measure is miscalibrated against the source
its bands were fitted on. A question that decides what today's report says
cannot be inert.]**

## 2026-08-16, fourth: the second SOCKET is closed, the second TOKEN is not, and they were never the same purchase

**Correcting a conflation in the entry above.** The VWAP stop closed "the
socket purchase" and listed the cap table with it. That is right about one
purchase and wrong about the other, and the two have been spoken of together
often enough that the distinction needs writing down before the shorthand
outlives the reasoning.

**The second websocket socket: CLOSED.** It was only ever worth buying to lift
subscribed recall against the 50 name cap, which bought a typical morning from
5 publishable names to 9.5. Publishable names are what the VWAP test found no
value in, so the thing that purchase buys is the thing that turned out not to
be worth having. Closed, and closed on the decision rather than on the
arithmetic, which still stands.

**A second API token: OPEN, and worth MORE than it was yesterday, not less.**
It is a different purchase entirely. It buys quota isolation, not subscription
capacity, and the case for it strengthened at the moment the rest of the work
stopped.

The reasoning. The key is shared with sibling projects this repository cannot
see or throttle. On 2026-08-16 a sibling took it from 96,098 used to 99,671
across an afternoon, which put the remaining balance below discover's refuse
floor of 500. Anything scheduled into that window does not degrade, it refuses
outright. Before the stop that was one failure mode among many in a system
with several moving parts. After the stop, the post-open pass and the morning
chain are the ONLY remaining outputs, and both die the same way for a reason
that has nothing to do with either of them. Narrowing the project did not
reduce this exposure, it concentrated it: the same accident now takes out
everything rather than one component of many.

Recorded as OPEN with its reason, and deliberately NOT as a plan. No price has
been checked, no vendor terms read, and nothing here says buy it. What this
entry fixes is that the case for a second token must not be quietly retired
alongside the socket, because a reader skimming for "purchases, closed" would
take both and would be wrong about one.

**The cheap half, taken now.** Attribution does not need a second token. Every
job now reads the shared meter at entry and at exit and appends both to
`logs/meter-<quota day>.log` with the delta since the previous reading, so a
day of consumption is attributable to a time of day and to a step. A job's own
spend is its entry-to-exit delta; whatever a sibling spent shows up as the gap
between one job's exit and the next job's entry. Two calls per job, about
eighteen a day against a shared 100,000, and the readings themselves are
visible in the trail rather than hidden, so a delta of two across a step that
made no other call is the instrument seeing itself.

That does not fix the exposure. It measures it, which is the precondition for
deciding whether the token is worth its price, and it works today.

## 2026-08-17: the bill is not the call count, so the gate is sized in credits and the funnel names its doors

**The measurement that forced this.** The 2026-08-16 Sunday rebuild started
with 329 credits on the shared meter and finished successfully, and the call
report said it made 172 http calls. Reading those two numbers together says the
job cleared with room to spare. It did not. The meter moved 4,945.

The prices reconcile exactly on two independent runs and are now recorded in
CRITERIA.md [quota costs] as MEASURED: us-quote-delayed bills one credit per
SYMBOL while being issued twenty at a time, eod-bulk-last-day is a flat hundred
per call, eod and exchange-symbol-list are one each, and user is free. On the
00:06:53 rebuild, 2 + 1 + 20x100 + 2,942 staged names gives 4,945, which is the
delta between the entry and exit readings in logs/meter-2026-08-17.log. The
20:30:01 run staged 2,941 and read 4,944 at its exit. There is no slack in
either sum for the meter reads themselves, which is what pins user at zero.

So the 2026-08-16 run did not clear with room to spare. It needed 4,945 and
held 329, seven percent of the bill, and it survived only because the vendor's
counter rolled within the first seconds of it. The bulk sweep alone would have
exhausted 329 on its fourth of twenty calls.

**Decision: quota gates are sized in credits against the work about to be done,
not against a flat floor.** refuse_below_remaining is 500 and stays 500, which
is right for a scan spending a few hundred. It is useless for the Sunday
rebuild: a meter reading 501 clears that floor and then strands the job a tenth
of the way in, having spent everything that was there. eodhd.require_quota
prices the step from the table and refuses below it times the headroom in
[quota] quota_headroom_multiple.

**Two gates, at the two points where nothing has to be estimated.** After
_session_dates returns, exactly three credits are spent and len(session_dates)
is exact, so the two thousand credit bulk sweep is priced rather than guessed;
refusing there costs three credits instead of two thousand. Before the market
cap sweep, len(staged) is final, so the largest block is priced exactly and the
meter read to check it is free. The second gate is the one that had to exist.
The first is cheap insurance and its sweep estimate comes from the previous
build's cleared_price_and_liquidity, which is a real number rather than a seed.

**An unknown meter still refuses nothing, and this is load bearing.** preflight
leaves remaining as None on three paths, and the third is a reading dated to
another quota day, which is exactly what the vendor serves for the half hour
after a reset it rolls thirty minutes late. Treating that as a zero would turn
a benign late roll into a skipped weekly rebuild, and would act on a number
nobody read. require_quota therefore refuses only when remaining is not None,
never recomputing it from api_requests, which the stale branch does populate.

**gap_stats gets the same gate rather than universe carrying its budget.** It
is the second step of the same .bat and cost a measured 2,753 credits against
the same 500 floor. Coupling the two would refuse a rebuild on Sundays when
only gap_stats was unaffordable, so each prices itself. gap_stats can price
itself exactly, one eod per universe name, before its first call.

**Refusing is the cheaper failure, which is why it is the choice.** A refused
Sunday leaves last week's file, and the monitor relaunches the job at
universe_rerun_after_days, so the recovery path already exists. That argument
holds ONLY while a refusal leaves the old file in place, which is why the
write time gate below exists: it is the same reasoning applied to the failure
the quota gates cannot see. Continuing: discover only
starts refusing on the fourth morning after a miss. Proceeding on a short meter
is the outcome with no recovery. staged is sorted by dollar volume descending,
so a sweep that runs out partway does not thin the file evenly, it amputates
the illiquid tail, and the result stays inside expected_count_range and above
min_count_fraction_of_previous until roughly half the names are gone. A missing
report is recoverable. A plausible one built on a truncated universe is not.

**Decision: the market cap funnel records every door, by name.** The note this
replaces said "46 names were dropped because no market cap came back" against
2,942 examined and 2,754 admitted. That arithmetic does not close: 142 names
failed the market cap floor with nothing recording that they had been
considered. Naming the 46 alone would have made the record worse, because a
reader would take the named list as the explanation for the whole 2,942 to
2,754 drop, and it explains a quarter of it.

Five doors now, and they are not the same kind of fact.
below_market_cap_floor is a decision made on evidence. The other three are
absences that differ in what is absent: the vendor answered and carried no
market cap, the vendor answered a batch without mentioning the name, or nothing
came back for the batch at all. Only the first is a fact about the market.

**What separating them immediately revealed.** The 46 were never one thing.
They are 20 and 26, and neither group is missing data. The 20 are alternate
share classes and warrants the vendor prices under the primary class: BRK-A,
BRK-B, HEI-A, LEN-B, MOG-A, GEF-B, BH-A, UHAL-B, BF-B. The 26 are preferreds
and warrants it does not quote at all: ALB-PA, ARES-P-B, BA-P-A, HPE-P-C,
KKR-P-D, NEE-P-T, PCG-P-X, JOBY-WS, and ZVZZT, which is NASDAQ's test symbol.
So the market cap gap was silently doing the filtering that
allowed_security_type was supposed to do, and that was invisible while all 46
shared one sentence. Whether the type filter should catch them upstream is a
separate question and is left open here.

**A silent hole closed on the way.** The old guard was `if error and not data`.
eodhd.quote_delayed returns ({}, None) when a chunk comes back 200 with a body
it does not recognise: no error, no rows. The guard was False, the loop ran
over an empty dict, and twenty names fell into the vendor gap counter with
nothing written anywhere. The test is now on the data rather than the error, so
a batch that answered nothing is recorded as unanswered whether or not it said
why. It did not fire on either run observed, which is why it went unnoticed.

**check_admissible acts on the distinction, at max_unswept_fraction = 0.02, and
the build asks it BEFORE overwriting anything.** Recording the difference
without acting on it would leave the same silent corruption in place with
better documentation. But where it is enforced matters more than the number.
check_admissible has always been called downstream, by discover, on a file
already on disk. That ordering is fine for a question about age and useless for
a question about completeness: os.replace is destructive, so by the time
discover can refuse the file, the good one it would have fallen back to is
gone. Worse, the monitor relaunches the rebuild on AGE, so a truncated file
with a fresh timestamp is never retried while a missing one is, and the
recovery argument two paragraphs above would not have applied to the very
failure this gate was added to catch. build() therefore asks the question of
its own payload and raises PartialBuildError rather than writing.

The numerator is the names nothing came back for at all. Names the vendor
answered a batch without mentioning are excluded, because that is its coverage
rather than this run's failure, and it is structural: 26 of 2,942, all
preferreds and warrants. Folding them in would spend a third of the ceiling on
a constant and leave real losses 1.6 batches of room. Excluded, the baseline is
zero, 0.02 of 2,942 is 58 names, and the gate clears two lost batches of twenty
and trips on the third. Payloads written before the funnel existed carry no
field and are skipped rather than failed.

**Errors of fact corrected in place today.** CRITERIA.md recorded
eod-bulk-last-day at "98 counted calls each" in two places. At 98 the rebuild
reconciles to 4,905 and leaves 40 credits unexplained; at 100 it closes
exactly. The 98 was read off the client side call ledger, which counts calls
and is not the bill. Both sites now carry the marker. The [job status steps]
comment still said Sunday 20:00 after the schedule moved to 21:00 on
2026-08-16, and is corrected the same way.

**What this does not close.** Whether eod-bulk-last-day costs 100 for every
caller or only for this one is untested; the price is measured from universe's
usage alone. The vendor's HTTP status on exhaustion is still unobserved, so the
refusal path is argued rather than demonstrated end to end. And the 21:00 slot
has never fired, so its clearance of the late roll is inferred from the
schedule rather than seen.

## 2026-08-17: Alpaca's free tier does not serve live premarket, measured across a whole morning

**The open question this closes.** The entry above, on reconstructing premarket
from Alpaca, ends NOT ADOPTED with one reason: every number in it came from
completed sessions, and whether the free tier serves that sweep LIVE on a
weekday morning was untested while the whole design rested on it. It is tested
now.

**The measurement. 23 sweeps, 07:30 to 09:20 ET on Monday 2026-08-17, every
one REFUSED.** All 46 requests, two per sweep, came back HTTP 403, across a
live trading morning on which this project's own collector folded 33,489
trades from 50 symbols into 3,102 minute bars. The sweep asks for the sip feed
over a window ending at the wall clock, and the free tier will not serve that,
so not one request was answered. The zero active names and zero bars in the
table are therefore the count of what an unanswered sweep returns, and not a
reading of what the premarket held. The denominator an emptiness claim needs
is requests SERVED, which was nought; symbols requested, which was 2,754, is
not that denominator. The table is
data/probe-alpaca-live-table-2026-08-17.md, regenerated on 2026-08-20 so that
it carries the served and refused counts, and the raw readings are beside it.

[corrected 2026-08-20: this read "every one empty", "Zero active names, zero
bars, no newest bar timestamp, on every sweep", and "The probe records its own
denominator, which is what makes the emptiness informative rather than
vacuous". data/probe-alpaca-live-2026-08-17.jsonl says otherwise: 23 sweeps,
23 with errors, 46 entries reading "status 403", and zero symbols with bars.
The probe did NOT record its own denominator. It recorded symbols requested,
and its table never read the errors key at all, so a refusal and an empty
premarket printed identically and this entry was written off the wrong one.
probe_alpaca_live.py carries the served and refused counts into the table from
2026-08-20, and the three stored tables are rebuilt from the same jsonl. The
contrast that proves the point is on disk beside them: the 2026-08-14 dry run,
which swept a COMPLETED session, has zero errors and 1,461 to 1,845 names with
bars, and it is the only one of the three where the sweep was answered. Two
numbers in the paragraph above were corrected with it. The window read "07:30
to 09:15", which is the 2026-08-14 dry run's last pinned time; this run's last
sweep is 09:20, in the jsonl and in the table, and is where 23 sweeps five
minutes apart from 07:30 have to end. Symbols requested read 2,745, which is
the 2026-08-14 and 2026-08-16 figure; every 2026-08-17 row says 2,754, matching
the universe.json rebuilt at 00:50 that morning.]

**The conclusion stands, on firmer ground than the reasoning it was written
on.** A blanket refusal of the sip feed for a window ending at the wall clock
IS evidence that the free tier does not serve it live, and it is the narrower
and stronger of the two claims. An empty feed admits other causes: a quiet
morning, a badly built window, a filter upstream. HTTP 403 on every request for
two hours is the vendor declining to answer the question at all, and no reading
of the active count is needed to see it.

It also sharpens what "not pending a better tier" below means. A 403 is an
entitlement refusal, so a paid tier is precisely what would lift it. That
reopens nothing, for the reason the stop paragraph below gives: the 2026-08-16
stop was about whether the names are worth having and not about what they cost
to find.

**It does not stand alone.** Two other measurements from the same morning point
the same way, and each closes a different candidate.

The per symbol real time endpoint was swept 125 times and not one reading was
dated to that day. It serves the last completed session, exactly as the bulk
form does, which had already been recorded.

The delayed quote's extended hours fields were stale at the moment they were
needed. At 08:45, KEEL.US carried ethTime dated the previous Friday at 16:29
while data/premarket/2026-08-17.jsonl already held 50 of its minute bars from
07:19 that morning. The same fields read correctly at 10:12, so they do update,
just not in time to be read at 08:45. A field that is right two hours after the
report is written is not a source for the report.

**Decision: Alpaca is closed as a candidate LIVE discovery source.** Not
deferred, not pending a better tier, closed on measurement. It remains what it
already was, a historical reconstruction source for completed sessions, and the
NOT ADOPTED entry above stands unchanged as the reasoning that was correct when
it was written.

**This corroborates the 2026-08-16 stop, it is not an input to it.** The order
matters and is worth stating so the record cannot later be read backwards. The
VWAP test stopped the premarket discovery work on 2026-08-16 on its own
evidence: four rules losing, none beating buy the open, and gappers doing
significantly worse than decile matched controls at p = 0.0, winning 3 to 10
sessions of 61. This probe ran the following morning and answers a different
question, which is whether a cheaper data path existed that would have changed
the economics. It did not. Had this probe come back positive the stop would
still stand, because the stop was about whether the names are worth having and
not about what they cost to find.

**Correction to a claim made earlier the same day.** A two credit probe at
09:57 confirmed that us-quote-delayed carries lastTradePrice and lastTradeTime,
and I described that as a live price. Precisely: it is live during REGULAR
HOURS, where it read 09:56:12 against a 09:57 fetch. Its behaviour during
premarket is UNTESTED and cannot be inferred from that reading, because the one
extended hours field this project does record was demonstrably stale at 08:45
on the same morning. Any design that assumes a universe wide premarket price
from that endpoint is assuming the untested half.

**What this does not close.** Whether lastTradePrice moves ahead of the prior
close during premarket, which a probe run between 07:30 and 09:00 would settle
for about 20 credits a day. That probe was considered and deferred: the
briefing section it would inform is built from completed sessions and needs no
premarket price, so the question is now optional rather than blocking.

## 2026-08-17, second: the briefing reads one file, scales its sigma by the span, and ranks inside one leg

Three rulings by the owner on the notable movers section, before a line of it
was built. The section is specified in BUILD_PLAN.md Layer 4; this is why each
of the three went the way it did. The design they amended was mine, written
down the same day, and each ruling replaced a worse answer.

**The universe legs read data/universe-closes-<date>.json, not
pool_recall.json.** My version had the universe wide leg reading the previous
session's true OPEN gap out of the prior day's pool_recall.json, on the
grounds that the 09:45 pass had already computed it for every name. Three
things are wrong with that and only the third was visible to me at the time.

It is not universe wide. pool_recall only records names above the discovery
gap_pct floor of 3 percent, so the leg would have covered the gappers and
called itself the universe. I had noticed this and disclosed it as a partial
view, which is the wrong repair: a section that reports a truncated
denominator and explains the truncation is worse than one that reports the
whole universe, because the explanation is what nobody reads.

It costs a vintage. The closes file exists precisely so that the section's
three closes share one vintage, bought with an extra 100 credit bulk call for
exactly that reason. Reading a fourth number out of a different module's
output on a different schedule reintroduces the mixing that call was spent to
avoid.

And close to close is the better measure for a briefing anyway. An open gap
carries only the discontinuity. Close to close carries the whole session, the
gap and the drift after it, and the question this section asks is what
happened to the name, not what the screen could have traded. The open gap
belongs to pool_recall because recall is measured against what the screen
could have caught at the open; the briefing is not that.

**Decision: no leg reads pool_recall.json.** The scope fence around the recall
measurement then holds with nothing to enforce it, because there is no
connection to sever, and the examined count is the universe rather than the
gapper count.

**move_sigma scales by the square root of the span.** I had ruled sigma
inapplicable to the multi session legs, correctly identifying that a two
session move over a one day standard deviation is dimensionally wrong, and
then stopped at the diagnosis. The standard repair is to divide an n session
move by sigma times the square root of n, which is what the section now does:
1 for premarket and prior_session, the square root of 2 for two_session.
Every leg carries a sigma, and the four labelled lists can be read as one
section.

The assumption is stated in the docstring where the scaling is computed,
because it is not free. Square root of time scaling assumes daily returns are
INDEPENDENT, and consecutive moves in one name frequently are not: momentum
and a multi day catalyst both produce runs, and dependent returns accumulate
faster than the square root allows. So the scaled sigma UNDERSTATES how
unusual a sustained run is. That is the safe direction here. It cannot inflate
a name into a briefing, it can only keep one out.

**Every ranked list stays inside one leg.** My version ranked the whole
section on each name's newest available move, premarket where the collector
heard it and the completed session otherwise. That is a ranking that cannot
mean anything. The 50 collector names were selected in advance for gap
propensity and news, and they are measured on a fresher and wider window than
the 2,704 names nothing selected. They would take the top of every list
systematically, and a section that exists so the report says something the
watchlist does not would have spent itself restating the watchlist.

**Decision: four lists, each ranked within one leg.** move_sigma and market
cap on the prior session leg universe wide, absolute move on the two session
leg universe wide, and move_sigma on the premarket leg over the collector
names alone. Like for like inside each list, and the premarket names get their
own five slots instead of taking everyone else's.

**What this cost, stated rather than buried.** Under the naming these rulings
settle, where a leg is named for the number of sessions its move SPANS, the
three session leg has no source: it needs a fourth close and the file holds
three. It is not emitted. Restoring it is one more 100 credit bulk call in
discover, 500 credits a week against a 4,945 credit universe build, and that
is the owner's call rather than the builder's. The leg name stays in
_LEG_NEWEST_SESSION_BACK, where it costs nothing and would validate correctly
if a row ever carried it.

## 2026-08-17, third: the three session leg is DROPPED, not left defined and unemitted

The notable movers section was specified with four legs and shipped with
three. The fourth, three_session, had no source: under the naming settled
earlier the same day a leg is named for the sessions its move SPANS, and a
three session move universe wide needs a fourth close where
data/universe-closes-<date>.json holds three. I left the key in
_LEG_NEWEST_SESSION_BACK anyway, with a note that it cost nothing and would
validate correctly if a row ever carried it. The owner removed it.

**The cost of restoring it, so the number is on the record and not
recomputed.** One more bulk end of day call in discover, a flat 100 credits in
CRITERIA [quota costs], every weekday morning. About 500 credits a week
against a shared 100,000 a day key that a sibling project already drains
unpredictably, and against the 4,945 credits the Sunday universe build spends.
Small, and not zero.

**What it would buy, which is less than it looks.** The two session leg
already carries most of it. A three session window and a two session window
over the same name are highly correlated, because the second contains the
first, so the marginal name that a three session leg surfaces and a two
session leg misses is rare. And the question a three session move answers is
what this name has been doing this WEEK, which is a trend question. This
report is written at 08:45 to answer what is worth watching in the next few
hours. A leg whose window outruns the report's own horizon is a different
product.

**Decision: three_session is removed from the table, not deprecated in it.**
The reasoning matters more than the deletion. This project has been bitten
repeatedly by the same shape: something is defined, looks reachable, and never
runs. The bulk feed that served the last completed session while the gate
compared it against its own high. The live v1 cumulative volume that was
available and unsound. The Alpaca free tier that served a completed session in
a second and refused every request for a live one. [corrected 2026-08-20: this
read "that answered every request and returned no bars". It answered none of
them: all 46 requests on 2026-08-17 came back 403.] In each case the thing
existed, and its existing was read as its working. An enum key that no code
path emits is that shape in miniature: a
future reader finds it, assumes a producer somewhere, and either writes a row
that no list can populate or spends an afternoon looking for the writer.

A recorded decision is strictly more useful to that reader than a silent enum
entry. The entry says a leg exists. This entry says what it would cost, what
it would buy, why the answer was no, and that re-adding one key to
_LEG_NEWEST_SESSION_BACK plus one bulk call in discover is the whole job if
the answer changes.

**What this does not touch.** The extra 100 credit bulk call discover already
makes for c3 STAYS. c3 is the two session leg's baseline, so that call is
still doing the work it was bought for; dropping the leg named "three" does
not make the third close unnecessary. The per candidate gap_3session field
also stays, because it is emitted: it is measured to today's premarket price
over the twelve candidates and is a report field beside gap_pct, not a section
leg. Nothing here is defined and unemitted after this change.

## 2026-08-17, fourth: the universe escape hatch reaches ONE verdict, and the reason is which number it is measured against

The pre-write admissibility gate refuses to overwrite a good universe with a
partial one. Moving that check before the write was right and is not in
question here. What was missing is that the gate had no way out: the count
fraction verdict measures this build against previous_count, which is read from
the very file the refusal prevents replacing, so a legitimate shrink refuses
again every Sunday against the same frozen baseline, and past max_age_days
every morning job refuses too. A --force flag now exists.

**The decision that could have gone another way is its SCOPE.** The obvious
implementation is "--force writes anyway", and that is what the first fix did.
It is wrong, and the code was already saying so. check_admissible can return
three verdicts, and they are not the same kind of thing:

| verdict | measured against | clears by itself? |
|---|---|---|
| count fraction | previous_count, from the file on disk | NO, the baseline is frozen |
| unswept fraction | this build's own market cap funnel | YES, rerun when the vendor answers |
| no count | a malformed payload | not a shrink at all |

Only the first can refuse forever, because only the first is measured against
something the refusal itself prevents changing. The other two are measured
against this run, so a rerun settles them and no human has to decide anything.
An escape hatch for those buys nothing and costs the gate.

**And the refusal message had already committed to this.** Its own wording
said names in a batch that answered nothing "are the case this gate exists for
and must never be forced past", while `if verdict and not force` cheerfully
forced past exactly that. The code contradicted its own message, which is the
tell that the scope was never thought through rather than deliberately wide.
Forcing the unswept verdict writes the quota starved, illiquid tail amputated
universe the gate was built for: the sweep runs in dollar volume order, so a
run that lost batches has not thinned the universe evenly, and the result still
lands inside its expected count range while the names it is missing are the
ones a gap screen is looking for.

**Scoping it also closed a blocking defect for free, and that is the part
worth keeping.** The override matches on the verdict TEXT rather than on a
boolean, deliberately: tighten the floor afterwards and the sentence changes,
the override stops applying, and the gate speaks again, which a flag could
never do. But the first implementation applied that match at all three return
sites, each written "return answer(...)", so a matched override returned None
immediately and every check BELOW it never ran. An override recorded for the
unswept verdict admitted a file whose count was far under the floor, in
discover, every morning until the next rebuild. Narrowing the override to the
count fraction verdict, which is the LAST check in the function, means there is
no check below it left to skip. The design is now safe by construction rather
than correct by inspection, and that is why the scoping decision is recorded
here rather than treated as a tidy-up.

**Cost accepted.** An operator whose Sunday rebuild is refused on the unswept
verdict has no override and must rerun, possibly waiting on the shared quota.
That is the intended answer: the thing they would be forcing is the thing the
gate exists to stop.

## 2026-08-17, fifth: an absent, a zero and a negative sharesOutstanding are three facts, not one

Float rotation divides premarket volume by sharesFloat, and the vendor figure
needs a cross check, because a float far below shares outstanding is an
artifact and a float above it is impossible. Both checks need a usable
sharesOutstanding. The guards asked for one in two different ways, "if
outstanding" and "if outstanding is None", and between them they covered falsy
and None while covering zero NEITHER time, so a sharesOutstanding of exactly
0.0 skipped both ratio checks AND the absolute floor and a fabricated float
became the divisor unchecked.

**Decision: three states, three answers, each named in the recorded reason.**
An ABSENT sharesOutstanding and a ZERO one are both a share count the vendor
never supplied, so the float faces the absolute share floor in place of the
ratios. A NEGATIVE one is a share count that cannot exist, so the quote is
corrupt rather than incomplete and the float in it is refused outright. The
reason string says which case fired, because a human reads it and "the vendor
sent nothing" and "the vendor sent zero" call for different follow ups.

**The negative case is here because the first fix broke it, and the reasoning
is worth preserving.** The review that found the zero hole asserted negatives
were unguarded too. They were not: "if outstanding and share_float > outstanding
* max_ratio" is truthy for a negative outstanding, and every positive float
exceeds a negative product, so negatives were already refused, with a gap
raised, by accident. The fix replaced the falsy test with an explicit "present
and positive" test, which is correct in intent, and in doing so it stopped
refusing negatives and began publishing a rotation for them with an impossible
share count recorded beside it. A guard that was holding for a reason nobody
had written down was removed by a change aimed at a different hole. That is the
argument for making all three states explicit rather than leaning on which
comparisons happen to be true for which signs.

**Known and accepted, recorded so it is not mistaken for an oversight.** The
absolute share floor is weak protection at this scale. A fabricated float at or
above min_shares_float with a few hundred shares of premarket volume still
lands in the top rotation band, which starts three orders of magnitude below
where such a name computes. The floor keeps out only the most obviously bogus
denominators. Closing that properly needs either a second independent share
count to check against or a band structure that does not reward an unverifiable
denominator, and both are threshold and design questions for the owner rather
than guard placement. What changed here is that no name reaches the divisor
without facing SOME check, and that every null says why.

## 2026-08-17, sixth: the rotation bands are re-derived after the screen fix, and they do not move

**Why this was owed.** The 2026-08-17 review fixed float_rotation_study.py: it
carried a private copy of one CRITERIA floor with the ratio written into the
Python as 1.01, was missing the other two floors entirely, and refused nothing
for the corrupt records the live path will not divide by. CRITERIA
[Score premarket float rotation] names that script as the way to re-derive the
bands, and the bands scoring live names every morning were produced by the rule
that had just been corrected. Fixing the instrument and leaving its output
standing is not a fix, it is a fix and an unmeasured claim. The edges are read
off rotation quantiles at the points reproducing RVOL's payout on a specific
population, and the hole changed WHICH NAMES were in that population, so the
payout match the edges exist to preserve could no longer be assumed.

**[corrected 2026-08-17: was "the edges do not move, and they reproduce
exactly rather than approximately", with a table asserting the counts and
payout shares reproduced too. The EDGES do reproduce, and that is the claim
this entry exists to make. The surrounding percentages do NOT, because
data/universe.json was rebuilt between the two runs. The original table is
replaced rather than kept because it was wrong when written: it was built from
a proof about the screen fix and presented as though it described a re-run.]**

**The result first: the edges do not move.** Confirmed twice over, by proof and
then by an actual re-run of the script on 2026-08-17.

**Both sides of this table are committed evidence, because neither run can be
produced again.** The columns below are read from:

- 2026-08-16: doc/research/float_rotation_study-2026-08-16-prefix.json
- 2026-08-17: doc/research/float_rotation_study-2026-08-17-postfix.json

Each carries a `_provenance` header naming the commit that produced it and why
it is unrepeatable, above the script's verbatim output. The first is
unrepeatable because the script is gone: its float screen was replaced in
405c9ac. The second is unrepeatable because its INPUT is gone, since it read
data/universe.json as generated at 2026-08-17T00:50 and the Sunday rebuild
overwrites that file weekly. They live under doc/ rather than data/ because
data/ is gitignored and stays that way. This is one comparison preserved for one
entry, not a change of policy about study outputs.

| | 2026-08-16, in CRITERIA | 2026-08-17 re-run |
| --- | ---: | ---: |
| **two point edge** | **0.0004** | **0.0004** |
| **one point edge** | **0.0002** | **0.0002** |
| unrounded two point quantile | 0.00045075 | 0.00045409 |
| unrounded one point quantile | 0.00021475 | 0.00021511 |
| rescued names fitted on | 303 | 300 |
| overlap names | 362 | 363 |
| pays two points | 55.45% | 56.00% |
| pays one point | 12.21% | 11.67% |
| RVOL target | 53.87% / 12.43% | 53.72% / 12.40% |

**The edges survive because the rounding absorbs the drift.** Both quantiles
moved in the fourth significant figure and both still round to the same one
significant figure edge. That is not luck, it is what reading an edge off a
quantile at this precision is for, but it is worth stating that the margin is
real rather than infinite: the two point quantile would have to reach 0.00050
to move the edge, and it sits at 0.00045.

**None of the drift is the screen fix, and that part IS exact.** The screen
change is a pure function of data/float_cache.json and the three CRITERIA
[Float rotation] floors. Running both screens over all 1,870 cached symbols:

| | names |
| --- | ---: |
| admitted by the old screen, refused by the new | 1 |
| admitted by the new screen, refused by the old | 0 |

The single name is YPF, float 51,810 against 392,075,056 shares outstanding,
0.013 percent, refused by min_float_to_shares_outstanding. It is the same name
CRITERIA's float floor note already records as the only one under that line,
which cross checks both implementations. Replaying all 61 session pairs through
the study's own gap ranking, which reads data/backtest/eod/ and not the network,
puts YPF in the top [Scan] candidate_count by gap on ZERO of them. The edges are
fitted on the rescued subset of that population, so a name contributing no rows
to it cannot move a quantile of it. Under one fixed universe the two screens
give bit identical top-N numbers.

**What the drift IS.** data/universe.json was rebuilt at 2026-08-17T00:50, after
the 2026-08-16 study run. The addressable population is computed from the
universe and the EOD cache BEFORE the float screen is consulted, and it differs
on 29 of the 61 sessions, 9,384 rows against 9,390. That is the universe
rebuild, not the fix, and it is measurable precisely because addressable sits
upstream of everything this entry changed. Revised Alpaca history may contribute
on top of it and is not separated here; it does not need to be, because neither
cause is the screen fix and the edges hold under both.

**On the method, and a claim to retire.** An earlier draft of this entry argued
a re-run was impractical, on the grounds that it needs Alpaca volume for the
whole universe over 61 sessions. That was wrong and the project's own probe
already said so. ALPACA_PROBE.md measured the free tier serving a complete
2,745 name 1Min universe sweep in 4 requests and 1.04 seconds, and the
2026-08-17 entry closing Alpaca as a LIVE source is explicit that it "remains
what it already was, a historical reconstruction source for completed sessions".
The re-run cost 463 requests, 567 seconds and ZERO EODHD calls. It should simply
have been run, and was. The population identity proof is kept above because it
is strictly stronger for the question it answers, attributing the drift, which
a re-run alone cannot do.

The screen change is a pure function of data/float_cache.json and the three
CRITERIA [Float rotation] floors. Both screens, the pre-fix one and the
corrected one, were run over all 1,870 cached symbols:

| | names |
| --- | ---: |
| admitted by the old screen, refused by the new | 1 |
| admitted by the new screen, refused by the old | 0 |

The single name is YPF, float 51,810 against 392,075,056 shares outstanding,
0.013 percent, refused by min_float_to_shares_outstanding. That is not a new
discovery: it is the same name CRITERIA's float floor note already records as
the only one below the one percent line, which is a useful cross check that
both screens were implemented as described.

Then the only remaining question is whether YPF is in the population the edges
are fitted to. It is not, and that is decidable offline because the gap ranking
reads data/backtest/eod/ rather than Alpaca. Replaying all 61 session pairs
through the same pool_recall.actual_gappers and addressable_target the study
uses:

| YPF over the 61 cached sessions | sessions |
| --- | ---: |
| raw gapper | 2 |
| addressable | 2 |
| in the top [Scan] candidate_count by gap | 0 |

The edges are fitted on the RESCUED subset of the top candidate_count by gap,
per the 2026-08-16 entry above. YPF contributes zero rows to that population on
every one of the 61 sessions, so removing it cannot move a quantile of it, and
the 303 count, both unrounded quantiles and both payout shares are unchanged
bit for bit. The replay made zero HTTP calls, which the run's own call report
confirms.

**What DOES move, recorded so it is not discovered later and mistaken for a
contradiction.** The study's all_addressable block is a wider slice, n 7,752
rotation rows, and YPF is addressable on 2 sessions, so that block loses at most
2 rows of 7,752 and its numbers shift in the fourth decimal. Those are not the
live bands. The all_addressable re-derived edges are 0.0007 and 0.0002, which
already differ from the committed 0.0004 and 0.0002 precisely because CRITERIA
is fitted on the scored population rather than the wide one, exactly as the
2026-08-16 entry decided. Nothing in CRITERIA reads the all_addressable block.

**The earlier claim that was wrong when written, corrected in place.** The
docstring added to float_rotation_study.py earlier on 2026-08-17 said the counts
in CRITERIA [Score premarket float rotation] "were measured before that was
fixed, so a re-run will not reproduce them to the name". That was written before
anyone checked and it is false: they reproduce exactly, for the reason above.
The docstring is corrected in place rather than answered by this entry, under
the wrong-when-written rule, because a reader who found it would conclude the
committed numbers are stale and would either re-fetch for nothing or distrust
edges that are sound.

**What would make this owed again.** These edges are conditional on [Scan]
candidate_count, as CRITERIA already says: change it and the fitted population
changes and a real re-run is required. A re-run is also required if the float
cache is re-swept, since a new sweep can change more than one verdict, or if any
of the three CRITERIA [Float rotation] floors moves. The cheap proof used here
works only because the population delta was one name and that name was outside
the fitted set. It is a proof about this change, not a standing exemption.

## 2026-08-17, seventh: the rotation bands are fitted on one volume source and applied to another

**The mismatch, stated plainly.** The float rotation score bands in CRITERIA
[Score premarket float rotation] were derived by research/float_rotation_study.py,
whose numerator is ALPACA premarket volume, read from the SIP feed for completed
sessions. The live path that those bands score is
morning/scan.attach_float_rotation, whose numerator is COLLECTOR premarket
volume, folded from the EODHD websocket tape. Two different sources measuring
the same quantity, one setting the edges and the other being measured against
them. The study's own docstring is careful that the two use the same WINDOW,
07:20 to 08:45, and says nothing about them being different SOURCES, which is
how this went unnoticed while the windows were being matched.

**The direction, which is what makes it actionable.** The scoring numerator is
smaller than the fitted one, so live rotation values land below the distribution
the edges were read off, and the bands therefore admit FEWER names than intended.
The fallback under-pays the population it exists for, which is the same failure
recorded on 2026-08-16 second and corrected there by re-fitting on the rescued
population. That entry fixed which POPULATION the edges were read from. This one
is about which SOURCE the numerator comes from, and it is still open.

**How big, and why that is not answered here.** Measured on 2026-08-17 against
EODHD's own 1m bars over identical minutes, collector volume ran at a median of
-88.49 percent, about an eighth of the vendor's figure. If that were the whole
story the gap would be roughly an order of magnitude and the correction
mechanical. It is not the whole story. The same check on 2026-08-14 came back
mixed, with the collector 3.83 times the vendor in aggregate and individual ETFs
up to 50,188 percent high, and the collector's own numbers for one symbol swing
by up to 181x between the two mornings while the vendor's move by 1.1x. The
collector is not merely low, it is not reproducible session to session. The full
diagnosis is doc/research/COLLECTOR_VOLUME.md.

**Decision: record the miscalibration, do NOT re-fit yet.** A re-fit needs a
stable ratio between the two sources and there is no evidence one exists. Fitting
the bands to a numerator that moves by two orders of magnitude between sessions
would bake one morning's accident into a threshold and would be harder to detect
afterwards than the mismatch it replaced. The order is: settle what the collector
is actually doing, then decide whether the honest fix is to re-fit the bands on
collector volume, to correct the collector, or to stop scoring on a number two
sources cannot agree about.

**What this does not change.** The edges themselves stay where they are. Nothing
here says 0.0004 and 0.0002 are the wrong numbers for the distribution they were
read off, and the 2026-08-17 sixth entry establishes that the float screen fix
did not move them. The claim is narrower and worse: the distribution they were
read off is not the distribution they are applied to.

**Where this is visible to a reader who does not open this file.** The study's
docstring names Alpaca as its volume source, scan.attach_float_rotation names the
collector as its numerator source and marks the value a lower bound, and
CRITERIA [Float rotation] describes the numerator as the collector's. None of the
three says the other two disagree. That is why this entry exists.

## 2026-08-18: the report's screen summary is computed by the model, and it was wrong the first morning it mattered

**What happened.** The 2026-08-18 report explained an empty day watchlist with
"the most common failed condition was price not above the prior day high, which
every candidate missed". Every candidate did not miss it. AS.US priced at 34.71
against a prior day high of 33.4194 and cleared that condition; its day_failed
list carries exactly one line, the null premarket RVOL. Counted from the packet,
11 of 12 candidates failed the price condition and 10 of 12 failed the RVOL one.
The mode is right and the universal is false.

**[2026-08-21: the counting above is still exact and one word under it has
changed meaning. AS.US failed on RVOL, and that failure is now known to be an
instrument reading rather than a market one: its true premarket RVOL is 606.85
against a published null. So the 2026-08-18 day watchlist was empty by one
name, and that name was kept off it by the volume defect. Re-read in the
2026-08-21 eighth entry.]**

**Why the model was in a position to get it wrong.** REPORT_TEMPLATE.md asks for
"one sentence below it saying the day screen produced nothing today and the most
common failed condition". That is a COMPUTED STATISTIC, and the packet does not
carry it. Nothing aggregates day_failed or swing_failed. The model is handed
twelve per candidate lists and asked to report their mode, so it is doing
arithmetic by eye in prose, which is the one thing this project has consistently
refused to let it do everywhere else: membership, eligibility, scores and
conviction are all computed in Python before the model runs.

**Why nothing caught it.** The containment checker validates that every ticker
named in the report exists in the packet. vintage validates that the data is the
session it claims. Neither looks at a numeric or logical claim about the screen's
own output, and there is no third guard that does. So the sentence went out
unchecked.

**Why it matters more than a normal wording slip.** On an empty morning that
sentence IS the report. It is the entire explanation of why nothing was
published, and it pointed at the wrong cause. A reader would conclude that no
name came close, when in fact one name cleared the published gate, scored 8.0
green on an earnings catalyst, and was stopped by a baseline too thin to divide
by. Those two mornings look identical in the report and are completely different
mornings.

**Decision: recorded OPEN with the fix named, not built in this pass.** The fix
is deterministic and small: scan.py counts the failed conditions across
candidates and writes the tally into the packet, and REPORT_TEMPLATE.md tells the
model to QUOTE that tally rather than derive it. That follows the precedent
already set for the watchlist table headers, which were made literal in the
template with a prompt rule pinning them character for character precisely so a
guard would stop depending on the model's word choice. This is the same move
applied to the same class of problem, and it is left for the owner to schedule
rather than slipped into a diagnosis pass.

## 2026-08-18: the float rotation eligibility question is NOT inert, and this morning is the counterexample

**[corrected 2026-08-18: the 2026-08-16 third entry closed by listing the
day-setup eligibility question for names rescued by float rotation as
"unresolved and now inert", on the grounds that "scoring has stopped". That was
wrong when it was written and is corrected here rather than superseded. What it
stopped was the scoring CALIBRATION work, not the publication of scores: the
2026-08-16 fourth entry, written the same day, calls the post-open pass and THE
MORNING CHAIN "the ONLY remaining outputs" after the stop. [corrected
2026-08-18, later the same day: this paragraph first cited the stop's own
"Continuing" list as the thing that keeps the daily report running. That list
names the two probes and the post-open pass, not the morning chain. The morning
chain is named in the next entry, cited above. The conclusion is unchanged and
the citation was wrong.] A
question about which names reach a watchlist that is published every weekday
morning cannot be inert while that publication continues.]**

**The question, as it already stood.** The 2026-08-16 first entry recorded it
deliberately: [Day setup] premarket_rvol still requires a real RVOL, Rule.test(None)
is false, so a name rescued by float rotation is SCORED but is still not
day_eligible. Scoring was the clause being fixed; eligibility was left OPEN.

**The counterexample, 2026-08-18.** AS.US, Amer Sports, reporting earnings before
the open, gapped up 6.57 percent to 34.71 against a prior day high of 33.4194.
It cleared the prior high condition, the gap floor, the price floor and the
market cap floor. It scored 8.0, conviction green, with
volume_measure_used = premarket_float_rotation. Its entire day_failed list is:

    ["premarket_rvol None fails > 1.5"]

and pm_rvol is null because its baseline median premarket volume is 383.5 shares,
under the 1,000 share floor, so the denominator was refused as too thin. The name
traded 37,169 premarket shares, roughly 97 times that median.

**Why this instance is the one that settles the priority.** It was the ONLY one
of the twelve candidates that cleared the prior high test; the other eleven
gapped down and cannot pass a long only screen. So on 2026-08-18 the open
eligibility question was not a marginal case at the edge of the watchlist, it
WAS the watchlist. The published day list is empty rather than holding one green
earnings name, and the difference is entirely this unresolved question.

**[corrected 2026-08-21: THE LAST SENTENCE IS WRONG, and it was wrong when it
was written. The difference is NOT entirely the eligibility question. AS.US's
premarket RVOL was null because the collector saw 37,169 shares against a
baseline median of 383.5, and the true premarket tape measured from Alpaca full
SIP over the same window carried 818,638 shares against a true baseline median
of 1,349. Its pm_rvol_true is 606.85. It clears [Day setup] premarket_rvol of
> 1.5 by a factor of four hundred.

So AS.US did not need float rotation to reach the day watchlist. It needed the
RVOL to be computed on the tape the baseline is measured on, which is the
defect corrected on 2026-08-21 and measured that night. The entry is kept
because everything else in it is true and the question it raises is still open,
but its strongest example is no longer an example: the name it was built around
is admitted by the volume screen itself once the volume is right.

What this does to the eligibility question is narrow it rather than settle it.
The case for a float rotation floor in [Day setup] now has to rest on a name
whose RVOL is null AFTER the correction, and no such name has yet been
observed. That is a reason to wait for evidence, not a reason to decide.

The baseline behind 606.85 rests on 13 prior sessions rather than the 20
[Truth] baseline_sessions asks for, because Alpaca returned no bars for AS.US
on seven of the days walked. Recorded rather than rounded up.]**

**Compounding, recorded so the two are not treated separately.** AS.US's float
rotation came out at 0.000264, which earns one point against the 0.0002 edge and
misses two against 0.0004. DECISIONS 2026-08-17 seventh records that the
numerator feeding that number is collector volume, systematically smaller than
the Alpaca volume the bands were fitted on. So the measure that rescued this name
for scoring also under-rewarded it, for a reason already on the record.

**Still not resolved here, and deliberately.** Whether a float rotation floor
belongs in [Day setup] is a threshold question, and thresholds live in CRITERIA.md
and are the owner's. Nothing in this entry changes a screen. What has changed is
that the question now has a dated, concrete instance behind it instead of being
theoretical, and it is no longer described as inert.

## 2026-08-18, third: everything parked on the stop decision, re-checked against its actual scope

**Why.** The 2026-08-16 third entry's own text was wrong about what it stopped,
saying "scoring has stopped" when the morning chain scores every weekday and
what stopped was the scoring CALIBRATION work. That entry has been cited to
close or defer several things, so each citation was checked against what the
decision actually says rather than against the sentence that summarised it.
This is the record of that check, so it is not repeated.

**The decision's actual scope, quoted.** Stopping: the socket purchase; the cap,
ordering and recall work; the scoring calibration including the volume slot and
its bands; any migration to Alpaca for LIVE premarket discovery. Continuing: the
two probes already scheduled, and the post-open pass. The 2026-08-16 fourth
entry adds the morning chain, calling it and the post-open pass "the ONLY
remaining outputs".

| Item parked on the stop | Scope supports it? | Outcome |
| --- | --- | --- |
| The subscription cap table, 42 through 142 | YES, "the cap, ordering and recall work" | stands |
| The second socket purchase and its load test precondition | YES, "the socket purchase" | stands |
| Alpaca as a live discovery source | YES, named explicitly | stands, and 2026-08-17 corroborates it independently |
| The float rotation bands' dependency on candidate_count, called MOOT | PARTLY | corrected in place: dormant, not moot |
| The day-setup eligibility question, called inert | NO | corrected 2026-08-18, with a counterexample |
| The looseness of the RVOL scoring bands, called inert | NO | corrected in place |

**The two that failed, and the single mistake behind both.** Each rested on
reading "the scoring calibration work stops" as "scoring stops". The first is a
statement about what nobody is working on. The second would be a statement about
what the system does, and it is false: the morning chain computes a score and a
conviction for every candidate every weekday and publishes them. So a question
that decides what a published score MEANS is live whatever the roadmap says, and
only a question about what to TUNE NEXT is genuinely parked.

candidate_count is the clearest case. The entry closed its dependency on the
grounds that "nothing will change candidate_count", which the stop does not
guarantee and cannot: it is a CRITERIA knob read every morning by a job that
runs on a schedule. Stopping work on the bands does not freeze the input they
were fitted to. The dependency is one edit away from mattering.

**What this does NOT change.** The three items that survive the check are
untouched, and the stop itself stands entirely. The VWAP measurement that
produced it is unaffected by any of this: four rules losing money, gappers doing
worse than decile matched controls at p = 0.0, pre-registered before the numbers
existed. Nothing here reopens that.

**The rule this suggests, recorded rather than applied.** An entry that closes
other items should say which of them it closes by SCOPE and which by
CONSEQUENCE. All six above were listed the same way, and the two that were wrong
were wrong because a consequence was asserted ("scoring has stopped") that the
scope did not deliver. That is a convention for future entries, not a change to
any existing one.


## 2026-08-18, fifth: what a rejected narrative costs, and who notices

**The decision.** A quantifier flag costs one regeneration, then the narrative,
and never the report. It used to cost the whole morning, and that was set
without ever being chosen: the guard returned exit 2 because every other
containment failure does, and the morning chain stops on the first non-zero
code, so the price was inherited from a check that guards against a different
kind of failure.

**Why the two are not alike.** An invented ticker is fabricated evidence. A
reader acting on it is acting on something that does not exist, and no partial
version of that report is safe to send, so exit 2 with nothing delivered is
right and stays. A quantifier over the candidate set is an UNCHECKABLE claim,
which is a smaller thing: the numbers around it are still true, the tables are
still correct, and the only unsafe part is one sentence. Withholding the
narrative removes that sentence and keeps everything else. Withholding the
report removes everything and keeps nothing, to protect a reader from a sentence
they were never going to see.

**Why one regeneration and not three.** The rejected sentences go back with the
request, so the second attempt is told what to avoid rather than asked to differ
by luck. An attempt that fails after being told is evidence about the report or
about the guard, and a third would be spending the morning's remaining clock on
the hope that a deterministic failure is stochastic. timeout_s is 293 seconds
and the chain starts at 08:45.

**Why the guard does not read the fallback.** Two reasons, and the first is the
one that decided it. The withheld disclaimer quotes the sentence that caused the
withholding, because a reader told the narrative was withheld and not told what
for has been handed a mystery instead of a report, and the person best placed to
say the guard was wrong is the one reading the morning it fired. That quote
necessarily carries the banned pattern. A guard reading it would reject the
fallback and leave the morning with nothing, which is the exact failure this
path exists to prevent. The second reason is that the fallback's claims are
computed in Python from the packet and are true by construction, which is
precisely what the guard exists to establish about the model's.

The fallback's own prose was rewritten into counts anyway, so the exemption
covers only the quoted evidence and never the report's ordinary sentences. That
also fixed a live defect: until today the fallback's own wording tripped the
guard, so an analyst timeout on a morning with an empty screen produced no
report at all. Both halves are kept because either alone would have left the
morning depending on the other.

**Why the watchdog counts the unjudged flags.** The flag log exists so the
guard's false positive rate is counted rather than recalled, and it fills only
if somebody records verdicts by hand. This project has already run the
experiment where a diagnostic raises on schedule and nobody reads what it wrote:
pool_recall did it nightly for a week while DECISIONS cited its evidence as
accumulating. The backlog is therefore surfaced where the jobs are, on the
mornings somebody is already reading, rather than waiting to be asked for. A
flag raised today is named and not called a problem; one that has survived
flag_backlog_after_days of mornings is a backlog and joins the problem count.

**What is deliberately not recorded as a failure.** A morning the regeneration
rescued. The report went out and the narrative is the model's, so job_status
stays ok. Marking it failed would fire the watchdog's STEP FAILED line on a good
morning, and a line that fires on good mornings stops being read, which is the
same decay this whole apparatus is built against. The event is in the flag log
with an outcome of regenerated, in analyst_usage.json, and in the unjudged
count.

**What this does not settle.** Whether the word list is right. That still waits
on judged dispositions, and the outcome split added here is the second input to
it: a word that regenerates away costs a retry, a word that reaches the fallback
costs the narrative, and the two should not be tuned as though they were the
same. `each` and `no` remain the two most likely to move.


## 2026-08-18, sixth: a guard that fires every morning is a guard nobody keeps

**The decision.** The quantifier guard runs in warn mode, logging and printing
and publishing, until the instructions stop asking for the sentences it
refuses. CRITERIA carries the switch and the three conditions for flipping it.

**Why this is not a retreat.** The fifth entry today argued that a flag should
cost the narrative rather than the morning, and made it so. It never asked how
often a flag would fire, and the answer, measured rather than guessed, is every
morning: all three archived reports flag, thirty times between them. A guard
that removes the narrative from every morning is not a guard being strict, it
is a guard that has been mispriced twice, and the second mispricing is the one
that gets it deleted. Warn mode is the price the evidence supports until the
provocation is gone.

**Why warn is the better half of the telemetry, not just the cheaper one.**
The flag log exists so the word list is tuned on data. A log filling under the
current template records which words fire, on which instructions, and how
often. A log filling after T2, T3, T15 and T16 are resolved would record only
that the remainder is quiet, which answers a question nobody asked. Running the
guard loudly while the documents still provoke it is the more informative
experiment, and it happens to be the one that keeps the narrative.

**Why the disclaimer says so.** Warn mode publishes a claim the guard calls
uncheckable. Saying that on the disclaimer line follows the rule the fallback
already follows, that a report which degraded quietly is a report lying about
its own provenance. A published flagged sentence is a quieter degradation than
the plain table, not a smaller one. It also puts the flag in front of the
person best placed to judge it on the morning it fired, which is the standing
difficulty with a log that has to be opened deliberately.

**Why the word list gets one definition rather than four.** Three times in
three commits the instructions asked for what the guard forbids, and each time
the guard was right, the instruction was wrong, and nothing said so until a
report was already written. The watchlist headers had this exact failure and it
was closed by a claim asserting every source agrees, not by anyone resolving to
be careful. So the tuples in analyst.py are the definition and rule 13's
enumeration, the template's wording and the fallback's prose are all checked
against them. The claim carries no copy of the list, because a fixture with its
own copy is a fourth place to drift, which is how three of the four watchlist
header fixtures came to be wrong for as long as they existed.

**Why backticks are the exemption and nothing else is.** These documents have
to teach a phrasing by exhibiting it. An exemption by line number would rot,
one by keyword would be argued about, and one by judgment would not be
mechanical. Backticks already mean "this is text I am showing you, not text I
am saying", they are visible to a reader and to a scanner alike, and a specimen
that will not fit on one line is a specimen that wants shortening.

**Why the instruction scan reads paragraphs where the report scan reads lines.**
Not a difference of principle. The instruction files are hand wrapped, so a
banned word and its set word land on different lines routinely and a
line-at-a-time scan reads past the pair; prompt_analyst.md had exactly that in
its own text. Model output wraps nowhere, so the report scan does not need it,
and changing a live guard's behaviour in the same commit that changes its
enforcement setting would have made tomorrow's flag count uninterpretable. That
asymmetry is recorded rather than defended: if a model ever hand wraps its
prose, the report scan needs the same treatment.

**What was not decided.** T2, T3, T15, T16, P1 and P2. The rewording removed
the banned words from those instructions without answering whether the
instructions should exist. "name the candidates whose pm_rvol is null" asks for
precisely the list "name every candidate whose pm_rvol is null" asked for, and
the empty case still invites a sentence about the whole set, which is why warn
mode is needed and why resolving them is the first condition on the switch.


## 2026-08-19: exempt what a process does, not where it writes

**The decision.** The suite's tree check exempts the meter sampler's behaviour
and not the directory it writes to. Three conditions together: the path is one
of the two files the sampler writes by name, the change is a pure append with
every previous byte unchanged, and the appended bytes parse as what that file
holds.

**Why not exempt logs/.** It is one line of code and it would have worked. It
would also have stopped the check watching the neighbourhood where the meter
trail and the quantifier flag log live, and the flag log is about to become the
evidence the guard's word list is tuned on. An isolation check that stops
watching the file a measurement depends on, in the week that measurement
starts, has been turned off in the only place it currently matters. The cost of
the narrower fix is about a hundred lines and a test module; the cost of the
wider one is a class of contamination nobody would see.

**Why a digest rather than a size.** Because a same length rewrite is the case
that matters. This check's own docstring already carries a correction about
mistaking an internally caused change for an external toucher, and size alone
cannot tell a file that grew by a tick from a file that was rewritten to the
same length. The digest is taken for two paths only, because hashing the whole
tree twice a run would cost more than the check is worth.

**Why the midnight case goes through the same three conditions.** A new dated
trail at 00:00 UTC is a creation rather than an append, and the obvious fix is
a second rule that allows a created file matching the trail pattern. Two rules
about the same thing can disagree, and the second one would be exercised once a
month by a person running the suite late, which is the worst possible test
schedule. It is the same predicate with a zero length previous file, so there
is nothing to disagree with.

**What the claims are for, given the exemption is small.** An exemption nobody
tests is a hole nobody sees. Each claim removes exactly one of the three
conditions and asserts the change is refused, so the exemption cannot quietly
become a filename convention or a directory allowance through a later edit that
looks harmless. Writing them found two intermittents in the new code, both of
which would have presented as the original symptom and been blamed on the
sampler.

**The report scan, recorded and not changed.** Whether the report scan has the
line-wrap hole the instruction scan had is now measured rather than assumed:
zero split sentences across 21 adjacent prose pairs in three reports, with the
model writing prose lines of 207 to 933 characters and wrapping at no width.
The paragraph scan finds exactly the hits the line scan finds on all three. The
hole is real in principle and has not fired. It stays unchanged until the first
week of warn-mode counts is in, because changing a guard's scan in the same
week its enforcement setting changed would make those counts uninterpretable,
and the counts are the reason the setting changed.


**The second toucher, recorded and not fixed.** `.git/FETCH_HEAD` is rewritten
by a timer outside this repository about every ten minutes, as a truncate
followed by a write of byte-identical content, and it failed one of 194
consecutive suite runs. It is the likely identity of the path that could not be
named on 2026-08-18. It is not exempted here, because the obvious exemption,
that unchanged content is not a change, does not cover the zero length window
the rewrite passes through, and covering that means letting an empty file stand
in for its own contents. That is a wider hole than the sampler's and it is the
owner's to open or refuse. Recorded so the next intermittent is compared
against it rather than investigated from scratch.


## 2026-08-19, second: fix what the data proves, measure what it only suggests

**The decision.** Two findings from the same investigation are treated
differently on purpose. The replayed out of window trade is fixed, because the
archived files prove it happens and prove what it costs. The subscription size
is NOT acted on, because the archive only correlates it, and a collector changed
on a correlation is how a measurement problem becomes two.

**What the archive proves.** The subscription replays a last trade per symbol
with its original timestamp. Forty-eight such trades on 2026-08-18, two of them
from the previous session, every one carrying exactly one trade. The damage is
not the 0.27 percent of volume, it is that pm_window_starts_late reads the first
bar present, so a replayed 07:00 print silences the flag that exists to say the
collector only reached 07:20. That is a vintage defect and this project has a
standing rule about those.

**What the archive only suggests.** Every other mechanism for the tenfold
volume gap is dead: sizes are ordinary, messages equal trades folded, no
reconnects, and the rate is flat across the window rather than collapsing. What
is left is that 38 subscriptions produced 171 SPY trades a minute and 50
produced 5.8, with the vendor's own bars moving 1.3x across the same two
mornings. Fifty is the cap. That is two sessions each side and a plausible
mechanism, which is exactly the evidence that feels like enough and is not.

**Why the probe alternates its arms.** Premarket trade rates climb through the
morning. Two consecutive blocks, small then capped, would confound the
subscription size with the clock and produce a number that looked decisive and
meant nothing. Alternating costs nothing and removes the confound.

**Why the probe refuses to run after 07:10.** The fifty symbol pool is account
wide. A probe still holding slots at 07:20 would starve the collector, and the
morning it corrupted would be the morning it was measuring. The refusal is in
the tool rather than in the operator's memory.

**Why the window guard is opt in.** A builder constructed without a window
refuses nothing. The ad hoc evening runs, measure_socket_cost.py among them,
collect outside any configured premarket window, and a guard that applied
itself by default would silently empty their output. The scheduled collector
passes its window explicitly; anything else gets the old behaviour.

**The one that nearly shipped.** The window's open edge was computed to the
microsecond while trade timestamps arrive as whole seconds, so every trade in
the run's first second read as early. The suite's replayed socket refused all
thirty and wrote no minutes. A guard against a defect that costs 0.27 percent
of volume would have discarded the first second of every morning. It floors to
the minute now, which is the granularity bars have anyway.


## 2026-08-19, third: a guard that costs more than what it guards against

**The decision.** A refused subscription is retried on a wait rather than
ending the run. The reasoning that made it fatal was not overtaken by events,
it was wrong when it was written, and it is corrected in place.

**What made it wrong.** It reasoned from the vendor's documentation of the cap
to the conclusion that a refusal must mean another process holds the slots, and
therefore that retrying is futile. Both steps were sound and the conclusion was
false, because the other process it could not imagine was the collector itself.
The cap is account wide and a closed connection keeps its symbols for a while,
so a reconnect one second after a drop competes with its own corpse. Nothing
had ever seen a refusal, so nothing had ever tested the reasoning.

**Why the retry is bounded rather than patient.** Four waits of a minute
against a window of two hours. If the slots are ours they come back inside
about that, measured at 105 seconds this morning. If they are not, the run
fails four minutes later than it used to and nothing else is different. The old
behaviour spent fifty minutes of window to save four.

**Why the collector was restarted by hand.** The window had 48 minutes left,
the watchdog's rerun budget for the day was unused, and a restart is what the
watchdog would have done on its next pass. It also tested the diagnosis: the
restart subscribing cleanly is what proves the slots were the collector's own
rather than a competitor's. A failed restart would have been equally
informative and cost nothing.

**Why the probe's guard moved from an hour to a window.** It was written to run
before the morning and 07:10 was the only free slot, so the hour and the
constraint agreed by accident. When the power took the 06:20 run, the accident
came apart: the hour refused a whole day in which the socket was free from
09:25. The constraint is that the probe must not hold slots the collector
wants, and the collector's configured window is where that is written down.

**Why the probe settles between arms.** Its two arms are two subscriptions on
one account, so arm B asking for 50 while arm A's 8 are still held is the same
collision that killed the collector this morning, and it would have produced a
refused arm measuring zero. A zero from a refusal reads exactly like a zero
from starvation, which is the answer the probe exists to find, so it has to be
impossible rather than unlikely. Refused arms are marked and excluded.

**What today did not settle.** Whether 50 subscriptions starve the feed. Today
is a third session at 50 and SPY still gets about 11 trades a minute against
171 at 38, so the correlation holds at three sessions to one. It is still a
correlation, and the probe still has to run.


## 2026-08-19, fourth: a probe that answers its question and unmakes its premise

**The decision.** The subscription cap is ruled out as the cause of the volume
gap on the strength of a measurement, and the search moves to whether the trades
websocket carries a venue subset while the intraday bars are consolidated. The
correlation with subscription count is withdrawn rather than weakened.

**Why the correlation is withdrawn rather than weakened.** It rested on two
sessions each side and on SPY being right at thirty eight subscriptions. SPY was
not right at thirty eight. It was 373.88% over the vendor's own bars, and TLT
was thirteen times over and DIA ninety five times over on the same morning. A
reading that is an order of magnitude high on one session and an order of
magnitude low on another is not a reading with a cause to find in the
subscription count. Both of those sessions failed the same check that failed the
fifty symbol ones, at 70.95% median absolute difference, and nobody had run the
check across every session at once until today.

[corrected 2026-08-19: this read "Both of those sessions failed the same check
... at 69.77% and 70.95%" and "all four sessions". The 69.77% belonged to
2026-08-13, which is not a premarket session and has since been removed from
every comparison, so the plural was wrong when written. The argument does not
depend on it: 2026-08-14 alone is the session that looked right, and it failed
the same check at 70.95%.]

**Why the probe's negative is trusted this far and no further.** It is trusted
because the mechanism it tested is a throughput mechanism and it was tested
harder than the collector tests it: fifty symbols drawn from the morning's own
list, at fourteen times the collector's message rate, on the densest tape of the
day. A starvation effect should be easier to provoke there, not harder. It is
not trusted past that because the arms are two minutes and the tape is not the
premarket tape, and the collector's own hourly counts, while they show no decay,
are not a controlled pair.

**Why the premarket re run is the next measurement rather than a longer hold.**
The hourly trade counts already argue against a hold length effect: the fifty
symbol mornings are down by about the same factor in their first hour as their
last, so a slow squeeze is not what a two minute arm would be missing. Tape type
has no such evidence against it. Re running the identical script premarket
changes one variable; lengthening the arms at the same time would change two,
and the cheaper discriminator goes first.

**What the answer no longer decides.** The choice this document was holding open
between subscribing to fewer names and splitting across connections is closed on
the first option. Fewer names buys nothing, on the measurement.

**What is still not known.** Why 2026-08-14 over reported. A venue subset
explains a collector that is short and cannot explain one that is long, so the
leading hypothesis for the fifty symbol sessions does not cover the thirty eight
symbol ones, and a single explanation for both has not been found.


## 2026-08-19, fifth: the containment guard cannot see this class, and that is why it needs claims

**The decision.** The five defects found by reading the report against its
packet are fixed at their sources rather than by widening the containment
check, and each is pinned by a claim in the suite rather than by the template
alone.

**Why containment could not have caught any of them.** It checks that every
ticker and number in the report exists in the packet, and all five reports
passed it: 42 claims checked, nothing invented, both tables present. Every
figure in the RVOL sentence was quoted correctly. What was wrong was the
DESCRIPTION around the figures, and a checker built to catch fabricated values
is structurally blind to a true value with a false account of what it measures.
That is not a gap to close in the checker. A general purpose reader of English
claims against JSON is the analyst, which is the thing being checked.

**Why three of the five are fixed in the template and two in Python.** The
split is whether the packet already carried the truth. It did for the funnel
count, the nowhere-else clause and the absent-component sentence, so the model
was narrating past evidence it had and the instructions are what changes. It
did not for is_lower_bound, job_health or the refused run's counters: those
were Python telling the packet something false or nothing at all, and no
instruction to the model could have recovered them.

**Why the drift guard is a literal string check.** It scans the template for
the two sentences the packet contradicts. That is crude, and it fired on the
template's own prohibitions, which quoted the strings they were banning. The
prohibitions were reworded rather than the check loosened, because a check with
an exception is a check that grows exceptions, and the one thing this guard has
to do is fail when somebody writes the sentence again.

**Why a recovered failure is still reported.** A step that failed at 08:16 and
succeeded at 08:37 is a working morning by every measure the packet had, which
is exactly why it was invisible. The reader is not being told the morning is
broken; they are being told what happened to it, and a rerun that fixed it is
the part they would otherwise have to infer from twelve late premarket windows.
The cost of the wrong choice here is asymmetric: a line too many is read and
dismissed in a second, and a line missing is a morning that quietly lies about
the machine.

**What is still not covered.** The report scan for banned words is still per
line rather than per paragraph, deliberately, and still deferred to its own
commit after the first week of warn mode counts. Nothing in this pass touched
it. And no check exists for the general class these five belong to, which is a
correct number with a wrong account of itself. Every one of them was found by
reading, and the next one will be too.


## 2026-08-19, sixth: read the history before spending another morning

**The decision.** The collector's run history is read before the probe runs
again, and the probe's first measurement becomes the off exchange question
rather than a repeat of the cap question.

**Why the history came first.** It costs nothing and it changes what the probe
is for. Had either morning been refused or restarted, the volume disagreement
would have had a mundane explanation already in hand and tomorrow's probe would
have been confirming rather than discovering. Both were single unbroken runs, so
the probe carries the whole question, and that is worth knowing before spending a
premarket window on it rather than after.

**Why the answer is trusted despite half the records not existing.** job_status
cannot speak for 2026-08-14: it was born that afternoon. The collector's own
sidecar can, it is a different file written by different code, and the two
defects fixed earlier today cannot have touched it here because neither morning
was refused. Where the two sources overlap, on 2026-08-17, they agree. Saying
"no record exists" is the honest answer to half the question and the sidecar is
the honest answer to the other half; neither is a guess.

**Why the vendor comparison is a separate command.** The probe runs premarket
and the vendor does not publish a session until it is over, so a fetch from
inside the probe would return zero rows every time and quietly print a shortfall
of one hundred percent. The same thing already happened by hand at 10:05 today.
A command that must be run the following session is a worse workflow and a
correct measurement.

**Why the census records values rather than judging them.** The obvious
alternative was a list of off exchange condition codes and a count of messages
matching it. That list would have been written from the vendor's documentation
rather than from the feed, which is exactly how the refusal guard was written
and exactly why it was wrong for a fortnight. Every code-like value the feed
sends is counted and printed with whether the parser reads it, and the judgement
is left to a reader who can see the codes.

**What has not been decided.** Whether dark_pool_volume is a parser bug or a
column for something the feed never sends. That is the measurement, and it is one
premarket run away.


## 2026-08-19, seventh: a hypothesis measured and refused, and a row deleted rather than footnoted

**The decision.** Replay is recorded as its own tagged row in the bar file
rather than discarded, the observed window and the intended one are carried as
separate packet fields, and 2026-08-13 is deleted from every comparison rather
than annotated in place.

**Why the two mechanism verdict is not stated.** The audit was set up to test
whether replay owns the over counting while the off exchange question owns the
under counting. It does not. Excluding every pre subscription bar moves
2026-08-14 by nothing and the other two sessions by about half a point. Stating
a two mechanism verdict anyway would have been fitting the frame to the data,
and the frame was worth testing precisely because it was checkable.

**Why the 2026-08-14 zero is reported as a limit rather than a result.** That
session predates both the job_status collector record and the subscriptions
file, so the only subscription time available is the configured one, and its
first bar falls in exactly that minute. The audit cannot see replay there. A
zero in that cell means the measurement was blind, and writing it as a finding
would be the same error as reading a missing counter as a count of none, which
this project made twice today already.

**Why replay is written to the bar file rather than to a sidecar of its own.**
The rows belong with the minutes they were mistaken for, and a separate file is
one more thing to remember to read. The protection is the tag plus a single
filter in read_bars_file, which every consumer already goes through, so a new
consumer gets the filtering by default and has to ask for replay by name. A
sidecar would invert that: safe by default only for readers who know it exists.

**Why the intended start is kept rather than replaced.** pm_window_start was
always derived from the bars. What was missing was anything beside it saying
what it was being judged against, so a reader could not see the two disagree
without knowing CRITERIA by heart, and the fields that DID quote the schedule,
the RVOL basis and the provenance membership line, asserted it as though it were
an observation. Both are needed and neither may stand in for the other.

**Why 2026-08-13 is deleted and not footnoted.** A row in a comparison table
gets counted whatever the note beside it says. It survives in the run history
and tape window tables, labelled, because those are the evidence for the
deletion and neither is a comparison.

**What is now unexplained.** The 2026-08-14 over count. It is 3.8x in aggregate
and 12.7x on TLT against the vendor's own bars, replay does not account for it,
no collector code change landed between that session and the next, and the
subscription cap was measured innocent. It has no candidate mechanism, and it
should not be quietly dropped for that reason.


## 2026-08-19, eighth: empty one table rather than start again

**The decision.** The picks table is emptied and nothing else is. The owner
chose this over quarantining the contaminated rows in place, having been shown
what each option costs.

**Why a wider purge was argued against.** The question asked was whether the
revisions of the last week had left the stored data untrustworthy. Measured
rather than assumed, the answer was that they had not, except in one table. The
baseline denominators come from EODHD intraday calls and gap_stats is end of day
data, so neither can carry a collector defect. The prices in picks are
corroborated: pm_source_disagreement is 0.0 on every backfilled row. Only volume
was ever wrong, and only picks stores it.

**Why the contamination was real anyway.** pm_rvol reached 882,728 on
2026-08-14, with eleven of twelve rows above 10 and outcomes already filled
against them. An earlier reading in this session that the volume component had
never fired was true of 2026-08-19 alone and wrong about the table, and it is
corrected here rather than left standing.

**Why the rows were exported before deletion.** They are the evidence for an
over count that has no explanation, and a file cannot be fitted against while a
table can. The export lives in data/, which is gitignored, and deleting it is
one command. This is not a hedge against the decision: the table is empty, which
is what was asked for.

**What this costs, stated rather than discovered later.** discover.py seeds a
pool tier from prior picks. It now returns its designed empty state with
sessions_considered 0, and the recent runner tier will be thin for
recent_runner_lookback sessions. That is a real thinning of tomorrow's
watchlist, it is visible in the packet, and it repairs itself.

**What was not purged and why.** The bar files, packets, reports, archive and
job-status.jsonl. Each is currently load bearing evidence in an open
investigation, and none of them feeds a threshold fit. Tidiness is not a reason
to delete the only record of a defect nobody has explained.

## 2026-08-20: three failures the pages described and the code did not do

A full read of the pipeline against doc/ArchitecturePremarketdesk.html and
doc/Premarketdesk_ADayRunArc.html, looking for places the two disagree. Three
of the disagreements were not documentation drift. The pages were right and the
code was wrong.

**The documented degrade path was the total loss path.** Both pages describe a
morning where discover produced nothing as a report that still goes out with no
candidates and the holes named: "Yes, no candidates" in the architecture page's
failure table. It did not. Every per candidate stage in `build_packet` sits
inside one `if candidates:` branch, and three of that branch's outputs are read
unconditionally in the payload at the bottom of the function. Two of the three
were bound before the branch. `dropped_stale` was not, so an empty pool ended
the scan with `UnboundLocalError` before it wrote anything. The morning chain
stops on the first non-zero exit, so a quiet 07:15 cost the packet, the report,
the picks rows and the email, on precisely the morning the degrade path exists
for. Reproduced under the sandbox before fixing, both ways in: a watchlist that
is present with nothing subscribed, and no watchlist at all.

The bug is small and the reason it survived is not. `write_picks`, the
`for candidate in payload["candidates"]` loops in `main`, the archive, the
report: every one of them handles zero candidates correctly. It is only the
literal that assembles the payload that reads a name the branch may not have
bound, and no test had ever driven the scan with an empty pool, because every
fixture writes a working watchlist. A static pass over the whole tree for
locals that may be read before they are certainly bound found exactly one other
site of this shape and it was a false positive, which is the reassuring half of
the finding.

**A watchlist that subscribes nobody said nothing.** Related and separately
wrong. `pool_candidates` gaps when `watchlist.json` is MISSING and says nothing
when it is present and holds no subscribed row. That produced a packet with
zero candidates and an empty `gaps_to_fill`, so the report's tables would have
been empty with no sentence anywhere explaining why, which is the one thing this
project's rule about missing evidence forbids. An empty pool and an absent file
are different failures with different fixes and both now name themselves.

**The calendar refresh destroyed the fallback it depends on.** market_today's
failure direction is deliberate and stated in its own docstring: an unknown
calendar reads as OPEN, because a false closed silently loses a real morning
where a false open produces one honestly thin report that says its numbers are
stale. The same docstring promises "a fetch failure falls back to the stale
cache". The `--refresh` path, which the nightly runs every weeknight, did
`CACHE_PATH.unlink(missing_ok=True)` and then fetched. One vendor outage at
22:15 therefore left no holiday list at all, and every job the next morning ran
on the assumption that the market was open. Reproduced: with the cache deleted
by a failed refresh, `is_trading_day(2026-12-25)` returns
`(True, 'calendar unavailable, assuming the market is open')`.

The unlink existed for a real reason, which is why it was not simply removed.
`get_details` short-circuits on a cache younger than `refresh_after_days`, so a
refresh that honoured the age check would decline on six days out of seven, and
deleting the file was the cheapest way to force the fetch. The fix keeps the
force and moves it into the function: `get_details(force=True)` skips the memo
and the age check, goes to the vendor, and falls through to the existing
"refresh failed, using the cache from X" branch when the vendor does not
answer. The old file now stands until a new one is in hand.

**Why these three and not a rewrite.** Each is a case where the design was
already written down, already correct, and the code diverged from it silently.
The architecture pages have been carrying the right answer for these three for
a week. That is an argument for reading the pages against the code on a
schedule, not for trusting either one alone.

## 2026-08-20: a test that stubs a module attribute must restore it

`test_vintage.main()` replaced `market_today.is_trading_day` with a weekday
rule and never put it back. run_tests imports every suite into ONE process and
runs them in a fixed order, so from test_vintage onward every suite in the
sweep, test_repricing, test_pool, test_backtest, test_txn_guard,
test_entrypoints, test_sandbox and test_evidence_gaps, has been running against
a calendar with no holidays in it. test_entrypoints' `claim_calendar` drives
the real guard as a scheduled entrypoint, and it has been driving that stub.

The stub itself is right and stays. What was wrong is its lifetime. It is now
taken in `main` and restored in a `finally`, with the body moved to `_run`.

This is the same failure conftest's `block_network` was built to remove, one
layer up. That docstring already argues the principle: a claim whose outcome
depends on state another claim left behind is not a test, and the fix belongs
at the boundary rather than in whichever claim happens to trip over it first.
The boundary here is the suite's own process, and nothing was watching it.
A cheap guard would be for run_tests to photograph the stubbed-out module
attributes the way it already photographs the working tree; not built, because
the tree check took several iterations to get right and the same care is owed
here.

## 2026-08-20, second: an instrument must not be gated on the thing it measures

`verify_against_intraday` is the check BUILD_PLAN names as definitive for
collector volume, which is the project's top open question. It ran at the tail
of `backfill()`, after `if not picks: return 0`. That coupling was invisible
while picks had rows in it and became total the moment the table was emptied on
2026-08-19 over the very defect the check exists to measure.

The shape is worth naming because it will recur. The check was PUT there for a
good reason: the comment said "while it is here with the intraday feed open",
and it is genuinely cheaper to make those calls in a pass that is already
talking to that endpoint. What was not noticed is that sharing a function with
the picks fill also inherits the picks fill's preconditions. Co-location for
convenience becomes coupling the first time one of them fails.

The rule this leaves: a measurement's preconditions must be the preconditions
of what it reads, and nothing else. This one reads the collector bar file and
the intraday feed. It now runs first, before any path that can return early,
and its catch-up sweep asks its own question, which sessions were collected and
never measured, rather than borrowing the fill's question about which picks
rows lack a column.

**What bounds the sweep, and why it is not a date.** Only sessions the collector
wrote a subscription list for. 2026-08-13's bar file holds an afternoon
shakedown, 13:32 to 20:00 ET, and BUILD_PLAN already records that no
verification is owed for it. A date floor would have worked today and rotted;
the subscription sidecar is the actual definition of "this was a scheduled
premarket run" and it is written before the socket opens, so a collector that
died early is still correctly included.

**What this does not fix.** The reading it produces is not expected to be good.
2026-08-19 will come back with the same disagreement the other sessions show,
because the defect is real and undiagnosed. The point is that the disagreement
is measured every night rather than not at all.

## 2026-08-20, third: the timeout rule kept, its evidence replaced

CRITERIA [analyst] timeout_s moves 293 to 537. The rule that defines it, three
times the slowest run on record, is untouched. What changed is that "on record"
now means scheduled mornings rather than the five dry runs of 2026-08-14, which
the schedule has overtaken.

This is deliberately not a new policy, and the distinction matters for a file
whose header says every number in it is an unvalidated seed. A seed threshold
moved on a hunch is a worse number than the one it replaced. A derived
threshold recomputed on better evidence, by the same derivation, is the same
number better measured, and that is the only kind of change this file should
accept without a study behind it.

**Why not leave it.** Nothing has timed out, so the case for acting is entirely
the trend: the analyst step measured 54.4, then 107.5, then 185.3 seconds on
consecutive mornings, close to a doubling each time, and it tracks output
length rather than model speed. At 293 the next session on that trend rides
both attempts into the deterministic fallback. That is not a lost morning, but
it is a lost narrative on a morning that had nothing wrong with it, and the
2026-08-18 work established that the guard-shaped version of exactly that trade
was the wrong price to pay.

**Why not more.** 537 is what the rule yields. Two exhausted attempts end at
09:03, which clears the open by 27 minutes and clears the watchdog's next pass
at 09:25. Rounding up further would buy nothing measurable and would be a
choice rather than a derivation.

**The question this leaves with the owner.** Raising the timeout accommodates
the trend and explains none of it. 16,005 output tokens on 2026-08-19 is double
the previous high, against a template whose nine sections did not change and a
packet that carried the usual twelve candidates. If the next morning lands near
350 seconds the question is what the model is being asked for, not what the
timeout is, and no threshold edit answers it.

## 2026-08-20, fourth: what twenty verified defects had in common

Six readers over six packages raised forty findings; independent verifiers told
to refute them killed twenty. The twenty that survived are in CHANGELOG the same
date. What is worth keeping is the shape, because almost none of them was a
wrong algorithm.

**They were seams.** A UTC clock relabelled instead of converted. An instrument
sharing a function with the thing it measures. A write that marked its work done
before doing it. A guard whose docstring described a stricter test than the code
made. A count that reported its request instead of its result. Every one looked
correct read on its own and was wrong read against its neighbour.

That is an argument about where to look, not about writing more careful code.
The defects did not live in the hard parts. scan.py's scoring, vintage's five
checks, the transaction guard, the containment checker, the quota preflight,
the places this project spent its thinking, all came back clean. What came back
dirty was the plumbing between them, and plumbing is exactly what a reader
skims because each piece is obvious.

**The strongest single signal was a docstring making a claim.** Four of the
twenty were found by reading a docstring's promise and then checking whether the
code kept it: thin_rerun_stands_down said "a rerun is only idempotent when it
carries at least as much evidence" and tested one narrow case; monitor_jobs said
"the morning chain can always be rerun" while deliver had no send-once record;
fill_outcomes said "a second run straight after the first changes nothing" and
rewrote null-close rows forever; query_task's return shape said it absorbed
failures and it absorbed one of three. This project writes unusually long
docstrings, and that turns out to be a testing asset rather than only
documentation: a promise written down is a promise that can be checked.

**The refuted twenty were not noise either.** Several were mechanically accurate
and stopped at reachability: real behaviour, no scheduled path to it. Keeping
the verify step adversarial and separate from the finding step is what made that
distinction cheap, and it is why the fixed list is twenty rather than forty. A
list of forty would have meant changing twenty pieces of working code.

## 2026-08-20, fifth: the watchdog's exit code and its status record answer different questions

monitor_jobs.check_all returns 1 when it FINDS a problem. job_monitor.bat
documents that as "something needs a human eye", which is right, and OK_CODES
was (0,), which made every such pass record STATUS_FAILED in the job trail.

Those are two different questions and they had one answer between them. The exit
code is for Task Scheduler's last result column and for a person looking at it.
The status record feeds job_status.overdue and report_line, which put a sentence
on the next morning's report, and there it has to mean "the watchdog ran".

The reason it matters is that several conditions setting `problems` are designed
to persist. CRITERIA's own note on the quantifier flag backlog says the word
list should be tuned on about a month of flags, and flag_backlog_after_days is
7, so an unjudged flag makes every pass from day eight onward report a problem.
Under the old pairing that meant no monitor record was ever STATUS_OK again, and
two sessions later the morning report would carry "monitor has never recorded a
success", with max_steps_named_in_report at 4, crowding out the real overdue
steps the line exists to surface. The watchdog would have been reporting itself
broken for doing its job.

OK_CODES is (0, 1) and the produced count is `problems found`. A pass that
genuinely fails still raises, and job_status.run records the exception whatever
the tuple says, so nothing is lost by admitting 1.

What this costs, stated rather than discovered later: the trail no longer
carries `jobs checked` as its count, so the denominator moved to the printed
line. That is a constant, four, and a constant in a trail is not a measurement.

## 2026-08-20, sixth: an economic calendar is not a news feed, and both are the vendor's

scan parsed the EODHD economic events feed with
`fromisoformat(raw).replace(tzinfo=ET)`. attach_catalysts, forty lines away,
parsed the news feed with `ettime.to_et`. One of those keeps the digits and
changes their meaning; the other converts. The feeds are both UTC, so the news
timestamps in every archived report are right and the macro ones are four hours
late in daylight time and five in standard.

The wrong one shipped because a re-label is invisible in a code review the way a
missing conversion is not. `.replace(tzinfo=ET)` reads as "this is Eastern", and
it is, after the sentence has finished being false. There is no error, no
warning, and the output is a plausible time on the right day. Every packet on
disk carries it and nobody reading four reports noticed, because 12:30 for
jobless claims is not absurd on its face: it is only wrong.

Two things follow. The packet now carries a `time_source` line saying these
times are a conversion, so the pre-2026-08-20 packets are distinguishable from
the ones after rather than silently comparable. And the fetch window is widened
a day past the ET window, because the vendor is asked in dates and answers in
UTC, so membership has to be decided after the conversion rather than by the
query.

The general rule, which this project already followed everywhere except here:
`.replace(tzinfo=...)` is only ever correct on a value that is ALREADY in that
zone and merely naive. On anything from a vendor it is a bug with no symptom.
