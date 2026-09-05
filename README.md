# PremarketDesk

A single machine, single user premarket desk for US equities. Every weekday
morning it builds a watchlist, listens to the live premarket tape, scores the
candidates, and puts the morning in front of you two ways before the open: as
nine screens you look at, and as one report you read. Every evening it goes
back and checks itself against what the vendors published.

The design has one brain and one voice: **Python decides, the model narrates.**
Membership, scores and conviction come from code reading explicit thresholds.
The model only fills marked prose slots in a report Python has already written,
and a checker verifies the prose invented nothing.

## The hard rules

These are load bearing. The code enforces them; changing them means changing
the design, not a config value.

1. **One data source in the published path.** Every market number the morning
   publishes comes from EODHD All-In-One (REST and the US trades websocket).
   Exactly one scheduled step reads a second vendor, and it runs after the
   session is over: `night/true_volume.py`, inside the 22:15 nightly, measures
   what premarket volume actually was from Alpaca's full SIP tape. It writes
   its own columns beside the morning's and never over them, nothing the
   morning reads comes from it, and it spends no EODHD quota. See rule 5,
   `doc/CRITERIA.md [Truth]`, and `doc/ALPACA_PROBE.md` for why that vendor and
   why only at night.
2. **Every threshold lives in `doc/CRITERIA.md`.** The strict reader in
   `src/core/criteria.py` raises on a missing key, and no decision literal is
   allowed in Python. To retune the system you edit a markdown file.
3. **The narrative pass uses the claude CLI as a subprocess**, authenticated
   by a logged in Claude subscription. There is no Anthropic SDK anywhere,
   and `src/core/config.py` actively refuses to read or pass `ANTHROPIC_API_KEY`.
4. **Missing evidence stays missing.** A field the pipeline could not get is
   null with a recorded reason. It is never filled from another day, another
   source, or a guess. This is the rule most often broken by accident, because
   a boolean that could not be answered has a falsy value that reads as an
   answer: `trap` is true, false or null and null is not false.
5. **Premarket high, low, VWAP and volume come from the project's own
   collector.** The socket carries a fraction of the consolidated tape, so the
   morning's premarket volume is an estimate: the socket's count divided by
   `[Collector] premarket_capture_rate`. The night audits both halves and uses
   a different vendor for each. EODHD's published intraday bars fill
   `pm_high_true`, `pm_low_true` and `pm_vwap_true`; Alpaca's SIP tape fills
   the volume truth columns. All of it is written beside the morning's values,
   never over them, and `_true` is not a provenance: `truth_source` carries the
   vendor on every row. Their disagreement is itself a recorded measurement.
6. **Nothing on a screen is computed by the page.** The desk reads and renders.
   Every figure on it was written into that morning's packet by `scan.py` and
   copied by `desk/compact.py`, so a wrong number on a screen is a wrong number
   in the packet and the fix is upstream. The same is true of the report, the
   midday pass and the weekly page: one measurement, four surfaces.

## A day in the life

All times are US Eastern, which the machine is expected to keep locally.

| Time | Job | What it does |
| --- | --- | --- |
| 03:55 and 07:15 | discover | Builds today's candidate pool from four priors (earnings between the prior close and this open, overnight news, prior session movers, recent runners), ranks it, subscribes the collector to the top of it, warms the volume baseline. Twice: 03:55 gives the 04:00 collector a pool to open on, 07:15 is the one the morning screens, over a news window that reaches the hours most earnings land in |
| 04:00 to 09:25 | collector | Websocket trades to one minute bars on disk, one file per day. Starts on the provisional pool the 03:55 discover wrote and moves onto the 07:15 pool at 07:20, keeping the tape of every name on both. See the two phase note in CRITERIA |
| 07:25 every 30 min to 09:25; 12:25, 12:55, 13:25; 22:45 | monitor | The watchdog, one task with three triggers: checks each job fired and finished, reruns what is safe. The morning trigger covers the collector, discover and the chain. The three midday passes watch the midday job, and there are three and not one because `job_log_stale_after_s` is 2,200 seconds: a midday that hung after writing its log at 12:00 is still warm at 12:25 and cannot be told from a live one, and is cold by 12:55. The midday job is the one job the watchdog reports and never reruns: the 12:00 sweep spends about 2,900 credits on the shared key, and a relaunch would replace the packet it may already have written. The 22:45 pass is over the nightly. Which pass a firing is comes from the clock, decided in `ops/monitor_jobs.py` from CRITERIA [Monitor] |
| 08:45 | morning chain | scan, analyst, render, verify, deliver, desk, stopping at the first failure. verify is the exception: it prints the gate table for a human and never stops the chain, because the gate is enforced by deliver |
| 12:00 | midday | The two questions the morning cannot answer, because at 08:45 the session had not opened: what every one of today's picks did against the levels the morning published, and what else moved that the morning never named. Then a second report, rendered straight from the packet. No model and no narrative pass, because midday asks closed questions: a pick triggered or it did not. 12:00 and not another hour because us-quote-delayed's regular hours behaviour is what was measured, and it never writes to picks or paper_trades, which are records of what an earlier pass claimed |
| 22:15; 07:00; Sun 21:00 | nightly | One task with three triggers, and the .bat reads the clock to tell them apart (a hand run may pass `full`, `catchup` or `universe` instead). 22:15 on weekdays is the full night, twelve steps, in this order and the list is closed: the trading day guard; a calendar refresh so the 08:45 chain never fetches it; the backup of the six artifacts that cannot be rebuilt (the collector's capture, its stats and subscriptions sidecars, the packet, and the report in markdown and HTML) plus a dated snapshot of the quantifier flag log, to a root outside the working tree; the true premarket backfill; the trade outcome fill; the Alpaca SIP measurement of what premarket volume actually was; the paper ledger, which books one written rule against the levels that measurement wrote; what the morning's pool missed, into `runs/YYYY-MM-DD/pool_recall.json`; the compaction, which freezes each session's payload to `runs/YYYY-MM-DD/desk.json.gz` and must run BEFORE the prune, because the prune refuses to drop a session's duplicate snapshot until that session's bars are frozen; the prune, which is the only scheduled step in the project that deletes anything and deletes only what its whitelist names; the weekly page; then the desk rebuild, so a morning that failed after the scan still reaches a screen the same evening. `tasks/README.md` carries the same list with the reasoning under each. 07:00 on weekdays is the catch-up, the vendor lag half: guard, calendar refresh, backup, backfill, outcomes, then stop. The vendor usually publishes yesterday's intraday overnight, so this fills anything the 22:15 run could not. Everything after the outcome fill is skipped, because those steps measure a session that at 07:00 has not opened. pool_recall is the one that made the case: it measures the session it is invoked on, and until 2026-08-20 this firing wrote recall 0.0 over the evening's real measurement. Sunday 21:00 is the weekly rebuild of the discovery universe, then the gap propensity sweep over every name in it, one counted call per name, measured at 2,745 calls and 421 seconds on the 2026-08-13 universe, run under `PMD_JOB` universe and writing `logs/universe-<date>.log` exactly as the retired `job_universe.bat` did. That propensity is what discovery ranks the pool by inside each tier. 21:00 and not 20:00: 20:00 ET is the instant of the 00:00 UTC quota reset in daylight time, so the largest job in the schedule billed to whichever quota day it happened to land on; and not 20:30, because the vendor's counter rolled 30 to 32 minutes late on 2026-08-16 |
| Every 30 min, all day, every day | meter-sampler | One reading of the shared EODHD quota counter into `logs/meter-<quota day>.log`, 48 a day, weekends included. Not a pipeline step: an instrument. The job trail says which step spent what and cannot say when, and nothing at all runs between 22:45 and 07:00, which is exactly where a sibling project draining the shared key would hide |

```mermaid
flowchart LR
    U[universe.py<br>weekly] --> G[gap_stats.py<br>gap propensity]
    G --> D[discover.py<br>ranked candidate pool]
    U --> D
    D --> C[collect_premarket.py<br>live 1m bars]
    C --> S[scan.py<br>prices from the collector]
    S --> X{vintage.py<br>is this today?}
    X -->|no| STOP[run refused,<br>gate re-armed]
    X -->|yes| A[analyst.py<br>claude CLI, one completion]
    A --> R[render_report.py<br>HTML report]
    R --> V[deliver.py<br>email, gated]
    R --> W[desk/render.py<br>the desk, one document]
    S -. picks .-> B[(SQLite)]
    N[backfill_premarket.py<br>+ fill_outcomes.py<br>EODHD intraday] --> B
    T[true_volume.py<br>Alpaca SIP tape] --> B
    P[pool_recall.py<br>what the pool missed] -. reads .-> B
    B -. reads .-> WK[weekly_page.py<br>did the week work]
    S -. picks .-> MD[scan_midday.py<br>12:00 carry through]
    MD --> MR[render_midday.py<br>midday report, no model]
    J[(job-status.jsonl)]
    S -. records .-> J
    C -. records .-> J
    P -. records .-> J
    J -. overdue steps .-> A
```

Every step in that diagram, and every other step a `.bat` runs, appends its
outcome to `data/job-status.jsonl` as it exits. The analyst reads it back and
names anything overdue in the morning report, which is the one channel a human
reads every day. It exists because `pool_recall.py` raised NameError on every
nightly run for a week: its exit code is ignored by design so a diagnostic
cannot break the chain, and nothing recorded that it had failed.

Every weekday job first runs `src/ops/market_today.py`, a trading day guard built
on the cached EODHD exchange calendar. It exits 3 on a weekend or an official
holiday and the calling `.bat` logs one line and stops cleanly, so the tasks
stay registered plain Monday to Friday and holidays take care of themselves.
Two firings run no guard. The nightly's Sunday 21:00 universe rebuild does not,
because that guard counts Sunday as a non trading day, so wiring it in would
skip the weekly rebuild every week, and the rebuild is what keeps the following
week alive. The meter sampler does not either, because the counter it reads is shared with
everything else using the token and rolls at midnight UTC, so a day this market
is closed is exactly a day a drain would otherwise go unrecorded.

That table is the whole recurring schedule. One off measurement tasks are
registered separately and on purpose, by `tasks/register_tasks.ps1 -Probe`,
`-Capture` or `-SocketCost` with a date, because they are meant to be deleted
once the question they were armed for has an answer in `doc/DECISIONS.md`. A
plain run of the register script never resurrects them, and `-Unregister`
removes all three. `tasks/README.md` says what each one measures.

## What it puts in front of you

Four surfaces, and every number on all four comes out of the same packet. They
are not four answers to reconcile; they are one answer in four shapes, and the
shapes are good at different things.

| | The desk | The morning report | The midday report | The weekly page |
| --- | --- | --- | --- | --- |
| File | `site/PremarketDesk.html` | `runs/YYYY-MM-DD/report.html` | `runs/YYYY-MM-DD/report_midday.html` | `site/Weekly.html` |
| Written | End of the morning chain, the midday chain and the nightly | 08:46 to 08:49 | 12:00 | 22:15 |
| Covers | Every session on file | This morning, except one section | Today's session so far | A rolling trailing 7 days |
| It answers | Which name is worth your next forty five minutes, and what the evidence behind it is worth | What the setup is on a name, and what would prove it wrong. Two thirds of it is a copy of the screens; the prose is the third that is not | What the open did to the levels the morning published | Whether the machine itself is working, over a week rather than a morning |
| Written by | Nothing. It is rendered | Python, with a handful of prose slots filled by the claude CLI | Nothing. It is rendered | Nothing. It is rendered |

A screen puts twelve names on one axis, and a level, a tape and a score side by
side, so you can see which one to look at. Prose can say what a setup is and
what would prove it wrong, which no picture does. The report is also the only
one an email can carry, so it is a complete document on its own, and being
complete is why most of it repeats the screens. See
`## The morning report, and what is only in it` for what does not.

Every ticker and number in the examples below is INVENTED. `runs/` and `site/`
are gitignored so no real morning is ever committed to a public repository. The
one place real figures appear is the paper ledger's aggregate counts, which are
labelled where they are used.

### The desk

One HTML file. No framework, no library, no build step, no network. Each
session is compacted by `desk/compact.py`, gzipped and base64 encoded into the
document, and inflated in the page, because Chrome blocks `fetch` on `file://`.
Every screen is a hash route, so it can be linked, bookmarked and sent to
another machine, and the browser's back button works.
`#/session/2026-09-04/morning` is a whole address.

The navigation carries seven of the nine; Session and Name are reached from
the screens that name them.

**Morning** `#/session/<date>/morning`, and the desk opens here on today.
The tape and stat strips, then eight sections, in this order:

- the **tape strip**, nine index, volatility, rate, oil and dollar proxies
- a **stat strip**: candidates kept, day eligible, swing eligible, green
  conviction, and the largest gap with its catalyst
- **the gap spine**, every candidate on one axis. Distance from the centre is
  the premarket gap against the prior close, the side is direction, the stripe
  and the word are conviction, and the reason column carries each name's
  catalyst class and story count, so "why did this gap" is answered for the
  whole list at once. Filters for day eligible, swing eligible, green, up, down
- **the selected name**, which is the deck, below
- **How the list was cut**, the funnel drawn stage by stage from the pool to
  the names that cleared a screen, with each stage's share of its own
  predecessor, and both screens broken down condition by condition
- **What the evidence is worth**, which is the report's Skips and traps: every
  sentence the packet resolved about its own evidence, quoted as written, each
  printed whether or not it names anybody, with the per name reasons under it
  and the evidence gaps the scan recorded beneath
- **What kind of morning this is**, the list by sector, catalyst class and gap
  direction, because concentration is what a list of names hides
- **What else moved**, the names that are not candidates, ranked within one leg
  at a time, each of the four ranked lists printing its own state and
  denominator
- **On the calendar** and **Coming up**, today's high importance releases and
  who reports tomorrow

**The deck** is the unit and it is what the spine loads. One name: the level
ladder with prior close, prior high, premarket low, VWAP, last and premarket
high on one price axis, the gap bracketed beside it; the premarket tape with
its volume underneath and a crosshair; the score component by component with
the points each earned; the evidence facts; the catalyst and every headline
behind it with its polarity; and, once noon has run, what that name actually
did. Its badges are the warnings: conviction and score, Day and Swing
eligibility with the failed conditions in the tooltip, Trap flagged, Trap
undecided, Thin at the level, Partial window, No collector coverage.

**Precedent** `#/session/<date>/precedent`. What happened the last time a name
looked like each of the ones on that morning's list. One row a candidate: the
rule it was matched on, how many past candidates matched and over how many
DISTINCT sessions, how many of those reached the entry the report named, the
middle result of the ones that did, the spread of them, and how long the middle
one took to reach its high. Under it, the whole replayed population split by
time to the high, on the same buckets the Record screen uses.

It is a separate screen and not a section of Morning on purpose. The score is
what the desk thinks about a name; a base rate is a count of what lookalikes
did. Folding one into the other hides the case where they disagree, and that
case is the only one either of them ever gets corrected by.

Everything on it comes from RECONSTRUCTED sessions, which are sessions the desk
did not run, replayed over a real tape by `research/replay_session.py` and
graded by `research/replay_outcomes.py`. The live record is the Record screen's
and the two are never added together. A group under `[Precedent] min_rows` or
`min_sessions` prints that it is too few rather than a number, and a group that
only qualified after a condition was dropped says which one. Until the replay
has been run the screen says so and names the command, and still prints the
rule each name would be matched on.

**Midday** `#/session/<date>/midday`. What the open did to the levels the
morning published, name by name, with the packet's own reason under each; what
moved that the morning never named; and what the floors turned down. Before
12:00 it counts down to the pass and shows the levels it is going to grade,
because a screen that answers "not yet" and nothing else wastes the click.

**Report** `#/session/<date>/report`. The words delivered that morning, and the
midday one where the 12:00 pass wrote it, with a toggle where both exist. The
same markdown the email carried under the same stylesheet.

**Session** `#/session/<date>`. One session's shape: the tape, the counts, a
card into each of the three above, what the record says, and the health
verdict. Reached from the Sessions calendar.

**Sessions** `#/sessions`. Every session on file. A calendar where each lifted
day carries that morning's largest gap as a bar on one scale across every
month, so two mornings compare by eye, and a faint day is a day the machine did
not run rather than a quiet one. Or a list, newest first.

**Record** `#/record`. Across every session: candidates a morning with the day
eligible share inside each bar, the totals, and where the median pick ends up.

**Name** `#/name/<ticker>`. Every session that ticker has appeared in, its gap,
score, conviction, catalyst and what noon made of it, then its deck for each.
Reached by clicking a ticker anywhere.

**Health** `#/health/<date>`. Was the machine right that morning. Every check
as a sentence with a verdict chip: the scheduled steps, the vendor budget, what
the collector heard, the listening window it actually ran, the standing caveat
that premarket volume is scaled rather than measured, which names cleared a
floor only because of that scaling, and which tape the pictures were drawn
from. The packet's own figures are folded underneath, because the working
should be checkable and should not be the first thing read.

### Reading a morning at 08:50

1. **What the evidence is worth**, and the verdict at the foot. Before anything
   the morning concluded, find out what its evidence is worth. Anything not
   green is one click to Health.
2. **The stat strip and How the list was cut.** A morning where the cap cut six
   names is a different morning from one where it cut none.
3. **The gap spine.** Which name to look at, with why it gapped already beside
   it.
4. **Its deck.** Levels, tape, score, headlines, warnings.
5. **The report**, for the names you are still weighing, and only for its
   prose. Two things in it are nowhere else: one write up per day eligible
   name saying what the setup is and what would prove it wrong, and one
   sentence under each quoted headline saying who the story is actually
   about. The rest of the document is the screens again in words. Report in
   the navigation opens it for the session you are on.

The Record screen once, as context. It does not change between 08:50 and 09:30
and it is not about any name in front of you.

**If email is all you have**, the report alone is the whole morning, read in
this order: Skips and traps, Summary, the two watchlists, the record. That is
not the order it is written in, and that is deliberate: you find out what the
evidence is worth before you read what it concluded.

**What none of it can do.** Gap setups resolve inside the first fifteen minutes
and you are reading this at 09:00. It replaces the hour of scanning between
07:00 and 09:30. It is not a signal and the design does not allow it to become
one.

### Nothing has been emailed, and why

`data/UNVERIFIED` is on disk, so `deliver.py` refuses to send regardless of
what keys are configured. No email has ever gone out from this system. Until
you delete that file you read a morning by opening `site/PremarketDesk.html`,
or `runs/YYYY-MM-DD/report.html` for that morning's report alone. Both open by
double clicking.

That gate is the one thing in the project a person has to clear by hand.
Deleting it is a statement that you have taken one live morning's numbers,
checked them against an independent source, and found them right. See
`## When things go wrong`.

Each `report.html` ends with links to the previous session, that day's midday
report, that session's route on the desk and the weekly page. Those are paths
on this machine, so the emailed copy has them stripped: a path is not a URL.

## What the numbers mean, and what they are worth

Read this once. It is about the packet fields themselves, so it is true of
every surface: the screens and the report are rendering the same values.

### The entry, the stop, and the table the guard reads

The day watchlist table has a fixed header, character for character, because
the containment guard locates the ticker column by it:

```
| Ticker | Gap % | Price | Premarket RVOL | Premarket high | Premarket VWAP | Entry | Stop | Score | Conviction |
| ------ | -----:| -----:| --------------:| --------------:| --------------:| -----:| -----:| -----:| ---------- |
| ACME   | +14.2 | 18.44 |            6.1 |          18.90 |          17.95 | 18.90 | 17.60 |   7.0 | green      |
| BOLT   |  +9.8 | 42.10 |            2.3 |          43.05 |          41.60 | 43.05 | 40.90 |   5.0 | yellow     |
| CRUX   |  +7.1 |  6.22 |           null |           6.40 |           6.05 |  6.40 |  5.98 |  null | unscored   |
```

Entry and Stop are the two numbers the paper ledger books against, read from
`CRITERIA [Picks]` through one function: the entry is the premarket high and
the stop is the premarket low, so a name has to carry on past its premarket
high rather than merely hold. On the desk they are the two marked lines on the
level ladder, one arrow each.

### Premarket RVOL is an estimate, not a measurement

The collector's socket carries a measured fraction of the consolidated tape, so
the numerator is the socket's count divided by
`[Collector] premarket_capture_rate` while the denominator measures the whole
tape. The report says so in a sentence directly under the table every time, and
Health says it as a standing note. Both name how many rows would have cleared
the volume floor on the raw socket count against how many clear on the
estimate, so you can see how much work the correction is doing; and where the
correction is what put a name on the list, both name that name. It is the one
place a name is present because of a scaling factor rather than a measurement.

### `unscored` is not a bucket

A row whose score could not be computed says `unscored` and never a colour.
CRUX above has a null RVOL, so the volume component could not be scored, so no
total exists. It is on the list because `day_eligible` is true, which the
screens decide and the score does not.

### Being on the list is not a recommendation

Membership means a name passed a set of thresholds copied from a third party
and not yet validated on this data. See `## What the scope is today, plainly`.

### What the evidence is worth

The evidence roll is the packet resolving sentences about its own evidence. It
is section 11 of the report and the "What the evidence is worth" block on the
Morning screen, from the same rows. On a real morning it reads like this:

```
Moving on no found catalyst, a skip: BOLT, CRUX, DELTA.

Catalyst status is unknown for ECHO: the news feed was never checked this
run, so no catalyst judgment exists for them.

Traps: 0 of 12 candidates gap up against the balance of their own headlines.

The trap question was not asked of 7 of 12 candidates: a trap is a gap up
contradicted by its news, and those gaps are below the 3 percent the
question is asked above, or were never computed.

2 of 12 candidates carry a premarket RVOL built on a THIN denominator: at or
above the 1,000 share floor and below 10,000 shares, measured 2026-08-28 as
where 15 to 30 percent of a name's own ordinary premarket sessions reach the
top RVOL band by construction, against 5 percent above 100,000: CRUX, FOXO.

2 of 12 candidates traded so little near their own premarket high that the
level may be a print rather than a price anyone could transact at: ACME, BOLT.

4 of 12 candidates opened their premarket window late, so their premarket
path evidence is partial: SWBI, MAMA, IOT, PL.

Cleared selection and dropped before pricing, the collector having no bars
for them: HALO (subscribed, no bars recorded).
```

Four things about it are worth knowing.

**A `0 of 12` line is printed as readily as one that names somebody.** An
absent line is indistinguishable from a section that was forgotten. The same
rule governs every ranked list on every screen: each prints its own state and
denominator, so a short list cannot read as a quiet market.

**The thin band line is the fill warning and it fires in one direction only.**
A name it does NOT mention has not passed anything. Measured over the 54 past
rows where the night reached a verdict at all, it caught 6 of the 10 levels it
went on to call untradeable and flagged 6 of the 44 that were fine. Four in ten
untradeable levels get past it. The population is 66 rows; the other 12 are the
ones the night could not judge either, counted apart rather than folded in.
Nothing in this system may ever write that a level looks liquid or should fill,
because the definitive answer is computed that night from a complete tape and
is not available at 08:45.

**A trap is a packet field with three states, not two.** True is a gap up
contradicted by the balance of its own headlines. False is asked and cleared.
Null is could not be answered, and the report says in as many words that
undecided is not a verdict of safe: the deck draws a Trap undecided badge for
it. Until 2026-08-20 the model judged this from headline polarity and published
names as traps on a single mis-scored headline; it is computed in Python now
and the counts behind it are quoted so you can disagree with the call.

**Names dropped before pricing appear here and nowhere else.** They cleared
selection and the collector recorded no bars for them, so they carry no
premarket price at all and are absent from every table and every screen.

### What the record says, and what it is not

The one part of a morning that is not about that morning: the Record screen,
and section 10 of the report, from the paper ledger, which is what one written
rule in `doc/CRITERIA.md [Paper]` would have done with every past pick.

```
The ledger holds 66 picks across 7 sessions, of which 16 were traded across 6.
The sample unit is the session and not the pick, so this rests on six
observations rather than sixteen.

14 of 16 trades reached their trigger within thirty minutes of the open, at a
median of 1 minute.
28 picks never reached their trigger at all, across 6 sessions.
10 of 10 trades that made their best price within ten minutes of entry closed
below their entry.
4 of 4 trades that made their best price more than a hundred minutes after
entry closed above it.

The best a position was worth while open was a median +1.84 percent, against
a median -1.38 percent booked at the exit. Rule version v1.
```

Those are the real current figures and they are also in `doc/CHANGELOG.md`.

**What you take from it is shape, not instruction.** A name that made its high
in the first ten minutes and faded has not recovered once in ten tries, and the
four that worked were still making highs an hour or more in. Ten and four are
not sample sizes.

`doc/REPORT_TEMPLATE.md` FORBIDS turning any of this into advice: three
specimens of the phrasing it may not use are written into it verbatim, and so
is a ban on the words pattern, signal, edge and tendency. If you ever see one,
that is a defect worth chasing, because a description of six sessions written
as an instruction is a strategy nobody validated wearing the authority of a
generated document.

## The morning report, and what is only in it

MOST OF IT IS A COPY OF THE SCREENS. Measured on `runs/2026-09-04/report.md`,
47,000 characters: Python wrote 30,343 of them and the model 16,657. Every one
of Python's 30,343 is a table, a count, a level or a quoted figure that the
Morning, Record and Health screens now draw, usually better, because a bar
compares and a number does not.

The 16,657 are the reason to open it. They are 32 marked slots the model fills,
and none of them is on any screen:

| Slot | How many that morning | What it is |
| --- | ---: | --- |
| `{{SETUP:<ticker>}}` | 2 | One write up per day eligible name: what the setup is, and the line saying what would prove it wrong |
| `{{HEADLINE:<ticker>:N}}` | 27 | One sentence under each quoted headline, saying who the story is actually about |
| `{{MOOD}}` | 1 | The phrase in the title |
| `{{TONE}}` | 1 | The market tone sentence |
| `{{RATES}}` | 1 | One sentence on the rate picture |

The difference is easiest to see on one headline. The deck draws the title, the
publisher, the time, the polarity and an "about this name" pill. The report
adds the model's sentence under it:

> Headline: "Samsara outlines FY 2027 revenue of $2.043B-$2.047B while
> targeting 21% non-GAAP operating margin" (seekingalpha.com, 22:19)
>
> This is about the company itself, its outline of FY 2027 revenue and a 21
> percent non-GAAP operating margin target.

That is the whole case for the document. Open it for the two setup write ups
and the headline sentences on the names you are still weighing; everything else
in it you have already seen.

The eleven sections, in the fixed order they always appear in, because a
section that goes missing is a defect rather than an empty morning: Summary,
Premarket gappers, Day watchlist, Swing watchlist, Notable movers, Market
trends, Technical signals, Economic data and rates, Coming up, What the record
says so far, Skips and traps. The slots are not spread evenly through them:
the setups are in Technical signals, the headline sentences in Premarket
gappers, the mood in the title, the tone in Summary and the rates sentence in
Economic data and rates. The other six sections carry no prose at all, which
is another way of saying they are the screens in words.

**How the two halves are kept apart.** Python writes the whole report from the
packet with the slots marked, pipes that skeleton and `doc/prompt_slots.md` to
the CLI, and takes back only what the model put in the slots: the fixed text
that ships is Python's copy, byte for byte, and a model answer that altered
anything outside a slot is refused and kept beside the report as
`report.slots-rejected-N.md`. The containment and quantifier guards then read
the slot prose. Before 2026-09-02 the model wrote the whole page from a 68 KB
instruction set and at least 60 percent of what survived the guard was packet
text copied under instruction, which is what the slots exist to stop.
`CRITERIA [Analyst] mode` switches between the two.

## The midday pass

Live from 2026-08-31. It exists because the morning report is written ninety
minutes before the session it is about, so at 08:45 nothing in it has happened
yet. It asks closed questions, a pick triggered or it did not, so it is laid
out directly from arithmetic: no model, no containment check, nothing that
could hallucinate.

**What the morning's picks did.** Every pick from today, graded against the
levels the morning published:

| Ticker | Score | Morning entry | Stop | What happened | Now vs fill | Best vs fill | Stop state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MNSO.US | 7.0 green | 9.69 | 9.46 | never triggered | n/a | n/a | not applicable |
| SAIC.US | 10.0 green | 137.40 | 134.00 | gapped through at the open | -8.87% | +1.62% | stopped out |

Read the second row first, because it is the case the morning cannot show you.
SAIC was the highest scoring name of the day, green, eligible on both screens.
It opened above its entry, so a resting order filled at the open. It then ran
1.6 percent, gave it all back, broke its stop and sat nearly 9 percent below
the fill. The 08:45 report could not know any of that.

Four verdicts, and the difference between two of them is the whole design:

- **never triggered.** The session high never reached the entry. The stop is
  NOT read, because a low with no trade under it stops nothing. MNSO's low was
  under its stop all day and that fact is meaningless: there was no position.
- **gapped through at the open.** The open was already past the entry, so the
  fill is the session's first print. Everything after it is after it, which
  makes a later low through the stop unambiguously a stop out.
- **triggered after the open.** The fill happened mid session, where a daily
  high and a daily low carry no order. If the low went through the stop it says
  **stop level reached, sequence unknown** and refuses to call it a stop out.
- **unknown.** A level the quote did not carry. Null with a written reason.

The third case is the one thing this pass cannot answer and it says so every
edition, with a count. Fixing it means running the collector past the open for
timestamped minute bars instead of one daily bar, and that is gated on a
measurement not yet taken.

**What else moved.** The whole 2,751 name universe is quoted and ranked on
today's move, excluding anything the morning named, and the headlines are
fetched AFTER the ranking. **That order is the whole argument.** The cheap way
is to pull the news feed and quote only names carrying a headline, which
answers "which names had news and also moved" and makes a name that moved on no
tagged headline invisible with nothing saying so. Here price selects and news
only explains, so a name with no story stays on the list and the pass can tell
you it does not know why it moved.

The right hand column is a live recall measurement with three states that are
not the same fact: **subscribed** means the collector was listening and the
08:45 screen declined it; **pooled not subscribed** means discover ranked it
and the 50 symbol cap cut it, so no premarket tape exists for it at all; **not
pooled** means discover never had it. On the first real run the two largest
moves of the day were both in the middle group.

**What it costs**: about 2,900 credits a session against a shared 100,000 a
day, almost all the per symbol universe sweep. There is no cheaper honest way
to ask what moved: the vendor's bulk endpoints serve the previous session,
which is the trap that published a wrong report on 2026-08-14. The preflight is
sized to the sweep and refuses rather than truncating, because half a universe
is not a market wide scan.

**One thing it does not check.** The night's ledger skips any level that was
not transactable, judged from a second vendor's tape. That measurement does not
exist at midday, so these grades are arithmetic on levels without asking
whether anyone could have traded them. It says so every day.

## The weekly page

Five sections, in the order a person actually asks them. It reads and renders
only: no vendor call, no measurement of its own, and if a number is not already
on disk it does not appear. It is not weekly in cadence, only in span: rebuilt
from scratch every night, always covering the last seven days ending yesterday.

| Section | What it answers | What a bad answer looks like |
| --- | --- | --- |
| Did it run | Jobs fired, non zero exits, mornings that produced a report at all | A step with no record inside its window. That is the silent failure mode the job trail exists to catch |
| Is the data trustworthy | The collector against vendor comparison as a SERIES rather than one reading, and what the truth pass measured the capture share actually to be | A capture share that moves a lot session to session, which is what the single divisor in `premarket_capture_rate` cannot correct |
| What did it publish | Candidates a morning, how many reached each watchlist, how many went unscored and why | A rising unscored count, which means evidence is going missing upstream |
| What did it cost | This project's spend against the shared key's siblings, and the closest any morning came to the preflight floor | A morning that came close to the floor. The jobs that spend before the open refuse rather than discover the limit through errors |
| Does the score order anything | Filled outcomes grouped by conviction bucket AND by each score component separately, with both denominators everywhere | Nothing yet. See below |

**The score watch is the long game and it currently reads backwards.** Green
n=20 at a median -7.44 percent favourable excursion against yellow n=21 at
+1.36. Red is withheld at n=8 because it is below the stated minimum, and the
page refuses to print any group below that minimum rather than printing a
number with a caveat.

That direction survived correcting the reference levels from the collector's
sampled ones to measured ones, which is the correction that flipped the sign on
both excursion medians for everything else. It is six sessions and it is not a
result. `doc/research/SCORE_INVERSION.md` holds the pre-registered judging
point and what would count as no relationship, written while the record was too
small to judge, on purpose, so the verdict cannot be chosen once the counts
arrive.

## A worked example: one morning, end to end

03:55. Discovery runs for the first time and writes a provisional pool, so the
collector has something to subscribe to when the extended session opens.

04:00. The collector opens the socket on that pool and starts writing minute
bars. This is the only source of today's premarket tape, and it is now listening
from the first print of the session rather than from 07:20.

07:15. Discovery runs again, over a news window that reaches the hours most
earnings land in, and ranks 38 names from the four priors, subscribing the
collector to 34 of them, four short of the cap because the pool did not fill it.
Everything below the cut is written to `watchlist.json` marked
`not_subscribed`, so the cut is auditable.

07:20. The collector notices the new `generated_at`, reconnects on that pool and
logs what was added, dropped and kept. A name on both pools keeps its tape
unbroken from 04:00; a name added here starts at 07:20, which `window_open_at`
records. A name discovery did not subscribe cannot be priced at 08:45 no matter
what it does.

08:45. The scan prices all 34 from the collector file, measures each gap against
the prior session close, and keeps the top 12, gaps up first and then gaps down
by size, because both screens are long in practice. It enriches those 12, computes
RVOL against the cached baseline, reads catalysts, computes the eligibility
booleans and the score. It writes `packet.json` and 12 picks rows.

08:46. `vintage.py` has already passed, so `analyst.py` writes the whole report
from the packet, every table, count and quoted sentence, with marked slots
where prose is wanted, and pipes `doc/prompt_slots.md`, that skeleton and a
projected packet to the CLI. The model returns the report with the slots
filled; the fixed text that ships is Python's, and the model's copy is used
only to find what it wrote. A containment check fails the run if the prose
names a ticker the packet does not carry, and the quantifier guard reads the
slot prose.

08:49. `deliver.py` refuses because `data/UNVERIFIED` exists, and says so.
`desk/render.py` rebuilds `site/PremarketDesk.html` with this morning in it.

You open the desk at 08:50. The verdict at the foot of the Morning screen says
one thing is worth a look, and Health names it: ACME cleared the volume floor
only once the capture correction was applied. ACME is also the widest bar on
the gap spine at a score of 7.0 green, so you click it, and its deck carries a
Thin at the level badge beside that score with the sentence underneath. **On
the desk those two facts sit together; in the report they are eight sections
apart and it will not join them for you**, which is the whole reason the
screens exist. Neither surface decides for you: the fill test's silence is not
an approval and its warning is not a verdict. What you now know is that the
18.90 on that ladder is a level the collector saw very little trade near.

22:15 that night. The backfill writes what the premarket really was from EODHD
intraday. The truth pass measures it again from Alpaca's complete tape and
writes the measured reference levels beside the sampled ones, then decides
whether ACME's level was transactable at all: `fill_plausible` comes back
`implausible`. The ledger then SKIPS ACME with that reason recorded rather than
booking a trade against a level nobody could have got.

Tomorrow morning, ACME's skip is one row inside the ledger counts, on the
Record screen and in section 10 of the report.

## What the scope is today, plainly

**The machine is complete and runs.** Seven scheduled tasks [corrected 2026-09-02: was eleven; the same seven jobs, each task now carrying every trigger its job has], every weekday since
2026-08-13, with a watchdog over them and a job trail under them. The midday
pass is the newest and joined on 2026-08-31.

**The record is 66 picks across 7 sessions.** That is enough to have found real
defects and nowhere near enough to validate anything.

**Every threshold in `doc/CRITERIA.md` is a seed value copied from a third
party.** Until a few dozen more sessions of outcomes exist, the report is a well
formatted list of names that met a stranger's rules. That is not modesty, it is
the actual epistemic state, and the pre-registered judging points exist so the
moment it changes is not a matter of opinion.

**The one thing the record has already earned.** Rule v1 lost money over its
first 16 trades, and every one of those 16 was in profit at some point while it
was held. A trigger producing random entries could not do that. So the first
result indicts the exit and the risk carried per trade, not the screen behind
it, and that is a more useful thing to know than a profitable sixteen trades
would have been.

## What you need

- **Windows 10 or 11.** Scheduling is Windows Task Scheduler plus the `.bat`
  files in `tasks/`. The pipeline itself is portable Python, but the provided
  automation is Windows.
- **Python 3.11 or newer** (developed on 3.14.7). Dependencies are deliberately
  tiny: `requests`, `websocket-client`, `markdown`.
- **An EODHD All-In-One subscription** and its API token. Lower EODHD tiers
  do not include the trades websocket that the collector needs.
- **The claude CLI, signed in to a Claude subscription** (Pro or Max). Install
  with `npm install -g @anthropic-ai/claude-code`, run `claude` once to log
  in. The analyst step shells out to it for exactly one completion per
  market day. No API key is used or wanted.
- **Optional: an Alpaca account** for the free market data plan, if you want
  the night to measure what premarket volume actually was rather than leave it
  estimated. Without it the morning is unaffected and the nightly truth pass
  records that it could not reach the vendor, leaving every column it owns null
  with the reason. The research probes under `src/research/` read the same two
  keys.
- **Optional: a Resend account** if you want the report emailed. Without it,
  delivery skips cleanly and the report still lands on disk.
- The machine must be **awake and on US Eastern time** during the premarket
  window. Task Scheduler triggers are machine local time; if your machine
  keeps another zone, re-derive the times in `tasks/register_tasks.ps1` from
  the clocks in `doc/CRITERIA.md` before registering. The Python code itself
  computes Eastern time internally (`src/core/ettime.py`) regardless of the
  machine zone.

## Setup

1. **Clone and create the venv at the project root.** The `.bat` jobs
   hardcode `.venv\Scripts\python.exe`, so the name and place matter:

   ```
   git clone https://github.com/masalasev-ops/PremarketDesk.git
   cd PremarketDesk
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

   `requirements-dev.txt` adds pyflakes, which the tree is kept clean under;
   nothing in the pipeline or the suite needs it.

2. **Configure.** Copy `.env.example` to `.env` and fill in
   `EODHD_API_TOKEN`, which is the only one the pipeline requires.
   `ALPACA_KEY_ID` and `ALPACA_SECRET_KEY` are optional and read by one
   scheduled step and the research probes; see the note in `.env.example` for
   what leaving them blank costs. Leave the Resend keys blank for now; you want
   the verification gate (below) to pass before any email goes out.

3. **Self check.** This creates the working directories and prints the project
   root, whether `ANTHROPIC_API_KEY` is set anywhere (it must not be), the
   masked EODHD token, whether the Resend keys are set, and the dependency
   versions:

   ```
   set PYTHONPATH=%CD%\src
   .venv\Scripts\python.exe -m core.config
   ```

4. **Arm the delivery gate.** This creates `data\UNVERIFIED`, and
   `deliver.py` refuses to email while that file exists:

   ```
   .venv\Scripts\python.exe -m morning.verify_morning --arm
   ```

5. **Build the first universe, and the gap statistics that rank it.** Normally
   the Sunday firing of `job_nightly.bat`, and it is both halves: that firing
   runs the rebuild and then the propensity sweep over every name in it. Discovery ranks
   the pool inside each tier by `gap_propensity`, so a universe with no gap
   statistics behind it leaves discover with nothing to order by, and
   `[Discovery] min_ranked_fraction_to_subscribe` makes it write no watchlist
   and exit non zero rather than subscribe an arbitrary 42 names. The second
   command is the larger of the two: one counted call per universe name,
   measured at 2,745 calls and 421 seconds.

   ```
   .venv\Scripts\python.exe -m selection.universe
   .venv\Scripts\python.exe -m selection.gap_stats
   ```

6. **Register the scheduled jobs:**

   ```
   powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1
   ```

   They appear in the Task Scheduler GUI under Task Scheduler Library >
   PremarketDesk, seven tasks, one per job, each carrying every trigger its job
   has. A plain run also removes the four names the schedule carried until
   2026-09-02 (nightly-catchup, universe, monitor-midday, monitor-night), whose
   triggers now live on the nightly and monitor tasks, so a machine registered
   from an older copy of the script ends up matching the current one rather
   than firing the nightly twice at 22:15. `-Unregister` removes them all. Do not register these by
   hand with `schtasks /Create`; its string quoting silently stores a spaced
   path unquoted and the task dies at fire time with 0x80070002. The script
   uses the PowerShell ScheduledTasks module, which stores the path
   structurally. Details and caveats are in `tasks/README.md`.

7. **Let a real morning run**, then read the gate table that
   `src/morning/verify_morning.py` prints into `logs\morning-chain-YYYY-MM-DD.log`.
   For the first three candidates it lays the evidence out on one line: the
   price and the minute it printed, the collector's premarket volume, the
   cached baseline median, the RVOL those two produce, and the bar count
   behind it, plus any candidate dropped for having no collector coverage.
   A price with no clock beside it cannot be checked by eye, which is the
   lesson of the first live morning. You can also run any step by hand in
   pipeline order; every script is idempotent and safe to rerun.

8. **Go live.** When a morning looks right: delete `data\UNVERIFIED`, put
   `RESEND_API_KEY` and `EMAIL_TO` into `.env`. The next morning's report
   arrives by email. Everything before this point is guaranteed to send
   nothing.

## Where things land

Everything generated at runtime is git ignored and created on demand. One
destination is not in the tree at all, and is the last row for that reason:

| Path | What |
| --- | --- |
| `data/premarketdesk.db` | SQLite (WAL), seven tables. picks, one row per (date, ticker), carrying the pool source and tier that put each name in front of the collector; baseline, the premarket volume denominator; gap_stats, one row per (ticker, as_of), and gap_sweeps, one row per sweep recording what that as_of covered; paper_trades, one row per live pick per rule version, holding the trade the `[Paper]` rule took or the reason it declined; sessions, one summary row per session written by `desk/compact.py`, which is what lets the Sessions, Record and Name screens ask a question across every session without opening every packet; and research_outcomes, what a RECONSTRUCTED pick did on its own session, written only by `research/replay_outcomes.py` and read only by the Precedent screen, never pooled with paper_trades under any question |
| `data/premarket/` | The collector's one minute bar files, its per run stats, and the subscription list it wrote at subscribe time so the 08:45 packet can tell a silent symbol from one that was never subscribed |
| `data/job-status.jsonl` | One line per scheduled step per run: job, step, start and end in ET, status, exception type, and one count of what it produced. Written in a `finally` block, so a step killed mid run records dying. The next morning's report names any step that has not succeeded inside its window |
| `data/universe.json`, `data/watchlist.json` | The weekly universe, and the day's whole ranked candidate pool rather than only the names being listened to. Up to `max_subscribed_candidates` rows are marked `subscribed`, and that is not simply the top 42: each populated tier takes `min_slots_per_tier` first. Everything below the cut stays in the file marked `not_subscribed`, so the cut is auditable |
| `runs/YYYY-MM-DD/` | The day's evidence packet, model transcript, rendered report, verification results |
| `logs/` | One log per job per day, every step ending in a `rc=N` marker line. Two files here are not that: `meter-<quota day>.log` is the shared quota trail, keyed by the vendor's quota day rather than the ET date because that is the day the counter actually resets on, and `meter-sampler.log` is the sampler's own undated stdout |
| `site/PremarketDesk.html` | The desk: every session on file in one self contained document, nine screens on hash routes, each session's payload inlined gzipped and base64 encoded. Opens from disk, no server, no network. Rebuilt whole every time, never appended |
| `runs/YYYY-MM-DD/desk.json.gz` | That session's compacted payload, frozen by `desk/compact.py` in the nightly. It is what the desk inlines, and the file `prune_data.py` requires before it will drop the duplicate premarket snapshot, because the run copy is the only exact record of the tape the morning saw |
| `site/Weekly.html` | One page saying whether the week worked, rendered by the nightly from what the steps before it have just written. It reads and renders: no vendor call, no measurement of its own |
| `%LOCALAPPDATA%\PremarketDesk\evidence` | Outside the working tree on purpose, because a copy inside the directory that gets deleted is not a copy. The nightly's backup of the six artifacts with no route back: the collector's socket capture, which is a recording of a tape that no longer exists, its stats and subscriptions sidecars, the frozen 08:45 packet a morning was judged on, and the report in markdown and HTML, because the same input does not produce the same words twice. A dated snapshot of `data/quantifier-flags.jsonl` sits beside them. See `doc/CRITERIA.md [Backup]` |

## Configuration reference

`doc/CRITERIA.md` is the single place every tunable number lives: scoring
weights, gap and RVOL thresholds, session clocks, the analyst model and its
measured timeout, watchdog rerun policy, how many sessions the desk inlines.
Each value carries
its reasoning in prose next to it. Edit it and the next run picks it up; get
a key wrong and the strict reader fails loudly rather than defaulting.

Other documents:

- `doc/CHANGELOG.md` records what changed and when, newest first, and
  `doc/DECISIONS.md` records why the choices that could have gone another
  way went the way they did. Both start at 2026-08-14.
- `doc/BUILD_PLAN.md` records how the system was built and verified,
  checkpoint by checkpoint, including the environment traps that were
  actually hit. Paths in it refer to the original build machine.
- `doc/MIGRATION.md` is what moving to another machine takes, what cannot be
  fetched again once it is left behind, and the two ways to start the record
  over. Written for a Windows to macOS move.
- `doc/ArchitecturePremarketdesk.html` and `doc/Premarketdesk_ADayRunArc.html`
  are the architecture pages; open them in a browser.
- `doc/REPORT_TEMPLATE.md` and `doc/prompt_analyst.md` are the report shape
  and the narrative instructions, the specification of every sentence the
  skeleton renders and the documents piped to the CLI when `CRITERIA
  [Analyst] mode` is `freeform`. `doc/prompt_slots.md` is what is piped under
  `slots`, the setting since 2026-09-02, and `doc/IMPROVEMENT_PLAN.md` is the
  2026-09-02 review written as work packages, with each tier's status.
- `doc/SCREENS.md` is the specification of the desk's screens, with a BUILT
  note recording where what shipped differs from it, and `doc/RETENTION.md`
  is what is kept, for how long, and what may never be deleted.
- `doc/ALPACA_PROBE.md` is what the Alpaca free plan was measured to serve and
  to refuse, which is what puts the truth pass at night rather than in the
  morning. `doc/research/` holds the other measurement write ups and the raw
  outputs behind them.
- `doc/sample_report.html` is a hand built mock with invented data, kept
  because `runs/` and `site/` are gitignored and no real report is in the
  repository. It predates the settled template: its watchlist headers are the
  old ones, so a report shaped like it would be reported by the containment
  check as omitting both watchlist tables, and its footer records sonnet where
  `doc/CRITERIA.md` sets opus. The shape the code actually produces is
  `doc/REPORT_TEMPLATE.md`, rendered by `analyst.fallback_report`.

## What it costs to run

- **EODHD:** the websocket collector was measured at zero against the
  vendor's own API counter (connections, subscribes, and reconnects
  included; `src/research/measure_socket_cost.py` reproduces the measurement). REST
  usage is a few hundred counted calls a day. Discovery spends up to three
  bulk end of day calls at a measured 100 credits each, two for the prior
  session movers source and one more for the third session close the
  briefing's two session leg is measured from, plus one earnings calendar
  call and up to five news calls; the baseline warm spends one
  intraday call per stale name; the 08:45 scan spends a few dozen across
  quotes, history and news; the nightly spends one intraday call per pick
  plus two bulk end of day calls for the pool recall measurement, today's
  session and the prior one. The Alpaca truth pass in the same nightly spends
  none of it, and neither do the backup, the prune or the weekly page. The
  weekly job is the largest single spend: the universe rebuild plus one call
  per name for gap propensity, measured at 2,745 on the 2026-08-13 universe.
  The jobs that spend before the open read the shared counter once on entry
  and act on
  what it says rather than discovering the limit through 429s: discover, the
  baseline warm that follows it, the 08:45 scan, and the Sunday universe and
  gap propensity sweeps, which refuse outright rather than start a sweep they
  cannot afford. The nightly does not preflight. The counter is account wide
  across everything using your token and resets at midnight UTC.
- **Claude:** one non agentic completion per market day (plus at most one
  retry, two CLI runs in total), on the subscription, and a second short call
  for the "Why these gapped" section. Under the freeform mode that ran until
  2026-09-02 the narrative was measured at 48.4, 98.5, 178.9 and 226.1 seconds
  of CLI time on the four scheduled mornings of 2026-08-17 to 2026-08-20, and
  at 335.7 seconds on 2026-08-27, which is the slowest on record, at opus and
  medium effort. Under slots mode, opus at low effort, hand runs of the
  2026-09-01 and 2026-08-31 packets took 134 and 97 seconds and wrote 13k and
  9k output tokens against 31k and 18k before; CRITERIA's slots note carries
  the table. The first scheduled morning to actually run in slots mode is
  2026-09-03: from the flip on 2026-09-02 until that afternoon a sentence in
  CRITERIA shadowed the mode key and every morning ran freeform, which
  CHANGELOG 2026-09-02 thirty ninth records. The 2026-09-02 packet regenerated
  in slots mode took 138 seconds and 13,236 output tokens at $0.68, against
  209 seconds and 17,989 at $1.27 for the freeform report the chain shipped
  that morning. Nothing has timed out. The rule behind the timeout
  in `doc/CRITERIA.md` has always been three times the slowest run on record,
  and the evidence under it has moved twice while the rule has not: from the
  five dry runs of 2026-08-14 to the scheduled mornings that overtook them,
  and again on 2026-08-29. It is 1007 seconds, three times 335.7. The
  watchdog's `job_log_stale_after_s` is derived from it and moved with it, to
  2200, because a healthy analyst step is the longest silence in the tree and
  raising one without the other makes a working job read as a dead one. If the
  CLI fails or times out, the morning still ships:
  `analyst.py` falls back to a plain table report built from the packet and
  says so in the report itself.

## When things go wrong

- **A morning titled "numbers only, narrative unavailable" or "numbers only,
  narrative withheld" is the fallback, and its disclaimer says why.** The two
  titles name two different causes. "Narrative unavailable" means the CLI
  failed or timed out on both runs. "Narrative withheld" means an answer came
  back and was refused: the quantifier guard refused the model's prose on both
  attempts, in which case the flag is in `data/quantifier-flags.jsonl` and
  `ops.quantifier_flags` is how you judge it; or, under slots mode, the model
  altered the report outside its slots or left one unfilled on both attempts,
  in which case the rejected answers are beside the report as
  `report.slots-rejected-N.md`. Read `analyst_usage.json` for `status`, `mode`
  and `slots_filled` before debugging anything else.

- **The watchdog usually acts first.** `src/ops/monitor_jobs.py` reruns anything
  idempotent at most once per day, restarts a dead collector only while the
  premarket window is open and no collector is alive, and never reruns
  discovery while a subscription list exists that the collector will not read
  again. Since the collector rereads the watchlist until its 09:25 stop time,
  a discovery rerun is free all morning; it is refused only once the socket
  has closed on a pool it will never revisit. Its reasoning is in
  `logs\monitor-YYYY-MM-DD.log`.
- **Antivirus TLS interception** (Norton and similar re-sign HTTPS with
  their own root): `src/core/config.py` detects the local root and widens the
  trust store instead of turning verification off. The same suites
  occasionally deny a first file write; scripts retry, and a one line
  permission error in a log that still ends `rc=0` was a survived retry.
- **The vendor publishes intraday late.** EODHD's one minute bars for a day
  often appear only overnight, so the 22:15 backfill may find nothing. That
  is what the 07:00 catch-up run is for, and unfilled days are swept up for
  several sessions after. A day is only ever filled with its own data.
- **A failed morning is visible, not silent.** The chain stops at the first
  nonzero exit, the report falls back rather than fabricates, and the
  evening desk rebuild still captures whatever the day produced.

## Disclaimer

This is personal research tooling that summarizes market data. It is not
investment advice, and nothing it prints is a recommendation to trade.
