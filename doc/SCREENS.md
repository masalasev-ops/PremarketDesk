# SCREENS

Written 2026-09-04. The screen design in this file was approved by the owner
on 2026-09-04, from a working prototype built over runs/2026-09-03 and read in
a browser before approval.

[BUILT 2026-09-04, later the same day. All seven screens ship in src/desk/,
an eighth was added that afternoon and is section 8 below, and
site/PremarketDesk.html carries every session. THE FILENAME IN THIS FILE IS
THE ONE IT WAS SPECIFIED UNDER, Desk.html, and it is left standing wherever
the specification uses it: the owner retired build_archive that afternoon and
the desk took site/PremarketDesk.html from it, which is recorded in section 8
and in CHANGELOG 2026-09-04 sixty first. Read Desk.html below as that file.
 What actually landed differs from the
specification below in two places and both are recorded where they belong: the
marks are drawn in the page from an inlined payload rather than by a
core/charts.py returning SVG from Python, because the desk needed one payload
per session and the emailed report is a separate surface that has not been
changed at all; and desk/compact.py freezes each session's payload to
runs/<date>/desk.json.gz, which was not in this file and which doc/RETENTION.md
explains, because a tape path cannot be redrawn exactly from the collector file
alone. core/charts.py is therefore NOT built and the emailed report is exactly
as it was. See CHANGELOG 2026-09-04 sixtieth.]

This is a specification, not a proposal. Where a screen below was drawn and
approved it says so; where it is specified in the same shape but has not been
drawn it says that too, because a reader six weeks from now must not have to
guess which parts were seen and which were reasoned about.

## What this file is for

The morning report is a document. It is read at 08:45 by one person deciding
which of twelve names is worth the next forty five minutes, and on 2026-09-03
it was 55,076 characters of markdown and 72,405 of HTML. Nothing in it is
wrong. The problem is that the decision has to be found.

Every screen below replaces reading with looking. None of them replaces the
prose: the analyst's words are kept, in full, one disclosure down, because the
screen answers WHICH NAME and the prose answers WHY, and the second question
is the one this project is actually good at.

## The rule that governs every screen here

READS AND RENDERS, NOTHING ELSE. No new measurement, no new vendor call, no
new threshold, no new scheduled job that fetches. Every number on every screen
below is already in packet.json, midday_packet.json, the picks table,
job-status.jsonl or the meter trail today. A screen that wants a number the
packet does not carry is not in this file; it is a change to scan.py, and it
goes through the freeze like anything else.

This is night/weekly_page.py's constraint, in its own words, and the reason it
is worth having is the one its docstring gives: a reporting layer that fetches
is a second pipeline to keep right.

## The freeze

BUILD_PLAN's "What remains" has carried a code freeze since 2026-08-21, and
its test is: which published number is wrong today, and where would a reader
see it. This work does not pass that test. No number here is wrong.

It proceeds anyway, on the owner's approval of 2026-09-04, in the same way the
2026-09-02 tiers did. That is recorded here rather than left implicit, because
the freeze is a good rule and the next person to want past it should have to
get the same answer from the same person rather than cite this file as
precedent.

## One document, no pages

The owner's instruction on 2026-09-04 was that the result must not be a set of
HTML pages clicked between, it must behave as a single application.

TODAY there are four documents and the reader navigates between them by
loading a new file. render_report.py writes a footer of relative links, at
line 298 a literal `<a href="../../site/PremarketDesk.html#{date}">`, pointing
at the archive, the weekly page, the midday page and the previous session.
Four documents, four loads, no shared state, and deliver.py strips the whole
footer before mailing because every one of those links is dead in an inbox.

TOMORROW there is one document, `site/Desk.html`, and the reader never loads a
second one. Views are hash routes resolved by client side JavaScript. Back and
forward work, a route is a link that can be sent to another machine, and the
selected name is part of the route so a screenshot is reproducible. That is a
single page application in every sense that matters here.

The one thing that cannot be escaped is that a browser opens a FILE, and that
file is HTML. There will be exactly one of them and it is the shell, not a
page. What goes away is the clicking between documents, which is what was
asked for.

### Why the data is inlined and not fetched

build_archive.py already established this and its docstring is the authority:
"Chrome blocks fetch on file://, so every byte the page needs is inlined at
build time." site/PremarketDesk.html is 349,737 bytes today for exactly that
reason. Desk.html inherits the finding. Python writes the shell and the data
into one file, and the page reads its data out of a `<script
type="application/json">` block rather than over the network.

That has a size ceiling and the ceiling is measurable. The prototype's
compaction of one session, which drops headlines_all and the provenance prose
and keeps every figure any screen draws, took runs/2026-09-03 from a 254,252
byte packet to 63,913 bytes, including the 216 minute bars of the tape path.
Thirty sessions inlined whole is about 1.9MB, which is five times today's
archive and still opens instantly from disk. One hundred and twenty, which is
what CRITERIA [Archive] embed_sessions is set to, is about 7.7MB, and that is
the point at which this needs measuring rather than estimating.

[measured 2026-09-04: the estimate above assumed the compacted session was
inlined as plain text. Gzipped and base64 encoded it is 19,808 bytes, not
63,913, so a year is 4.8MB and two years 9.5MB. The retention tiers and the
per screen consequences are in doc/RETENTION.md, which this file's storage
paragraphs defer to.]

THE ESCAPE HATCH, IF IT IS EVER NEEDED, IS THE STANDARD LIBRARY. `python -m
http.server` costs nothing, adds no dependency to requirements.txt, and turns
fetch back on, at which point sessions load on demand and the ceiling goes
away. It is not the default because a file that opens by double clicking is
worth more than lazy loading is, and because the moment there is a server
there is a server to remember to start. Reach for it when a measured file size
says to, not before.

## The three surfaces, and which is which

| Surface | What it is | Built how |
| --- | --- | --- |
| The 08:45 email | A flat document, no scripting | Python, static HTML and inline SVG, flattened by page.flatten_variables |
| The desk | The single page application | Python writes the shell, the data and the marks; the browser routes |
| The PDF | The printed desk | Headless Chrome against the desk, print stylesheet |

The email is the surface that constrains everything, and it is not negotiable.
page.flatten_variables exists because CSS custom properties reach under half
the clients caniemail tracks and classic Outlook has none; a mail client that
cannot read `var()` certainly cannot run a router. So the emailed copy is
rendered by the same Python that renders the desk, from the same packet,
through the same marks, and then flattened. One source of numbers, two
documents, which is the property core/page.py was written to protect and the
property that four drifting renderers cost this project once already.

## The chart vocabulary

Seven marks. They are defined once, in `core/charts.py`, and every screen
draws from this list. Nothing on any screen is a one off drawing, for the same
reason REPORT_CSS is one string with three users: parity by construction, not
by remembering.

Each mark is a function that takes packet values and returns an SVG string. No
JavaScript is required to render any of them, which is what lets the emailed
copy carry the same pictures as the desk.

### 1. Gap spine

Every candidate on one horizontal axis. Distance from the centre rule is the
premarket gap against the prior close, the side is direction, the scale is
fixed and symmetric so two mornings can be compared by eye. Conviction is a
stripe at the row edge and the word in the row, never the bar.

Used by: Morning, Session, Sessions.

### 2. Level ladder

A vertical price axis carrying prior close, premarket low, VWAP, last,
premarket high, prior high, with the entry and stop marked and the gap itself
drawn as a bracket to the same scale. Labels are pushed apart on collision and
joined to their tick by a leader.

This is the mark that earns the redesign. Six numbers in a table do not say
that SNOW's entire premarket range on 2026-09-03 was a sliver sitting 24
percent above a prior close that falls off the bottom of the frame. The ladder
says it without a word.

Used by: Morning, Session, Name.

### 3. Tape path

The collector's minute closes as an area, the premarket VWAP as a dashed rule
across it, and the minute volume as a strip beneath, on one shared time axis.
The last bar carries an emphasised endpoint.

It degrades honestly. On 2026-09-03 the collector recorded 216 minutes for
SNOW and 8 for PVH; under two bars the mark returns a sentence saying how many
minutes there were, rather than a line drawn through one point. The count of
minutes with a print, against the minutes in the window, is printed on the
axis so a sparse tape is never mistaken for a quiet one.

Used by: Morning, Session, Name.

### 4. Component bars

One row per score component, the points as a bar on a shared scale, the
component named in words. Replaces the score as a single number that says
nothing about what made it.

Used by: Morning, Record.

### 5. Stage strip

A count per stage with the share carried forward drawn beneath it, and the
reason for the drop written under that. The 2026-09-03 pipeline reads: pool
681, subscribed 42, ranked 41, cleared floors 17, kept 12, day eligible 3,
swing eligible 2, with 5 of the 17 cut by the cap of 12 rather than by any
screen. That last fact is in candidate_provenance today and no reader has ever
seen it.

The stages are NOT drawn to one shared scale. 681 and 2 on one axis makes the
2 invisible, and a funnel drawn on a square root scale is a lie told for
looks. Every stage prints its own count and its own share of its own
predecessor.

Used by: Morning, Record.

### 6. Condition track

Per screen condition, out of one denominator: cleared, measured and failed,
never measured. The third state is drawn as a dashed outline and not as a
third colour, because never measured is not a smaller amount of failing and
must not read as one. On 2026-09-03 premarket_rvol shows 4 failed of 12 with 3
of those never measured, and that distinction is the difference between a
screen doing its job and a screen with no evidence.

Used by: Morning, Record.

### 7. Diverging row

A signed value against a zero rule, sized for a table cell. The mark that
turns a column of percentages into a shape.

Used by: Midday, Sessions, Record, Name.

## Colour

### Conviction owns the status hues, and never works alone

Green, amber and red mean conviction and nothing else on any screen. Direction
does not get them, because the score is unsigned: score_roll.direction_note
says so in the packet, and on 2026-09-03 VSXY was green conviction and down
16.11 percent. A page that colours both by the same pair cannot be read.
Direction is carried by which side of the axis the bar sits on and by the sign
on the number.

Every conviction also carries its word. Hue is never the only channel.

### A defect in the current conviction colours

core/page.py lines 169 to 171 set `td.conv-green` to `#10704A`,
`td.conv-yellow` to `#8A5300` and `td.conv-red` to `#A61B1B`. Run through a
palette validator against the white surface they sit on, the yellow and the
red measure 2.3 apart under deuteranopia and 11.6 in normal vision. Both are
below the floor. For a reader with the commonest form of colour blindness
those two convictions are the same colour, and the table gives no second cue.

`#B07800` for yellow and `#B02020` for red clear every check, stay inside the
same warm family, and hold their contrast against the surface. THIS IS A
DEFECT IN A PUBLISHED PAGE AND NOT PART OF THE SCREEN WORK. It passes the
freeze test on its own, it is a two line change to page.py, and it should go
in ahead of any of this.

### Magnitude is one hue

Four steps of one amber ramp, stepped for each surface and validated against
it. Light: `#D9A870`, `#C48744`, `#AC6820`, `#8C460B`. Dark: `#6E4C22`,
`#996834`, `#C08A46`, `#E8A254`. More is darker in light, more is lighter in
dark. Never a rainbow, never a second hue introduced to tell two bars apart:
if a chart needs more than one hue to be readable it is the wrong chart.

## The seven screens

Every screen below names what it answers, its route, what is on it, and what
it reads. Where a screen reads a file it reads what is already written there.

### 1. Morning

APPROVED AS DRAWN, 2026-09-04.

Route: `#/session/<date>/morning`, and `#/` resolves to the newest session's
morning.

Answers: which of this morning's candidates is worth the next forty five
minutes, and what would make me wrong.

Reads: `runs/<date>/packet.json`, and `runs/<date>/midday_packet.json` where
the 12:00 pass has already run, for the outcome strip only.

Regions, in order:

  Session tape        market_snapshot, one chip per proxy, with the prior
                      session only ones marked as such rather than shown as
                      though they were live
  Decision counters   candidates kept, day eligible, swing eligible, green
                      conviction, largest gap, each naming its members
  Gap spine           mark 1, over all candidates, filterable by eligibility,
                      conviction and direction, and selectable
  Candidate deck      for the selected name: the level ladder, the tape path,
                      the component bars, the evidence grid, the catalyst and
                      its headlines with polarity, and the trap verdict in the
                      packet's own words
  Pipeline            mark 5, from candidate_provenance
  Composition         sectors, catalyst classes and direction from list_shape,
                      because concentration is what a list of twelve hides
  Record digest       the two findings from record_so_far, linking to Record
  Calendar            the economic events, today and tomorrow, from economic
  Prose               the analyst's summary and the standing disclaimer, in
                      disclosures, verbatim

The evidence grid prints premarket RVOL, move in sigma, premarket volume,
float rotation, market cap, twenty day dollar volume, news in window and pool
rank with its tier reason, plus the earnings actual against estimate where the
calendar carries one. Every one of those is a packet field today.

### 2. Midday

PARTLY DRAWN. The carry through table and the per name outcome strip were
built into the prototype; the floor buckets were not.

[AMENDED 2026-09-04. A midday screen whose pass has not run no longer sits
there saying nothing. It counts down in Eastern to the minute the 12:00 pass
fires, and under the countdown it prints the levels that pass will grade: the
entry and the stop the morning published, per name, in rank order. Four states,
because they are four different facts and a reader must be able to tell them
apart. Before 12:00 on today's session it counts down to the pass. Between
12:00 and the watchdog's due time it counts down to that. Past the due time
with a page built before it, it says the PAGE is behind the machine and to
rebuild the desk. Past the due time with a page built after it, that is a
fault and it says so. A session that is not today keeps the old sentence: the
pass never ran, which is not the same as a session where nothing triggered.
The two times come from CRITERIA [Midday] run_time and [Monitor] midday_due,
read by render.py and passed in, so neither is restated under [Screens].]

Route: `#/session/<date>/midday`.

Answers: did the levels the morning published survive contact with the open,
and what moved that the morning never named.

Reads: `runs/<date>/midday_packet.json`.

Regions:

  Carry through       one row per pick: the entry state at noon in words, the
                      move from the prior close as mark 7, the day RVOL, and
                      the packet's own state_reason, which already says things
                      like "the session high 427.27 came up -5.47 percent
                      short of the 452 entry"
  Movers              what moved that the morning never carried
  The floors          what each floor turned down, largest mover first, which
                      the 2026-09-03 fifty sixth change added to the packet
                      and which nothing has ever displayed

The four entry states get words and not codes: triggered reads "entry
reached", gapped_through reads "opened past the entry", never_triggered reads
"entry never reached". REPORT_TEMPLATE's rule that no field name is printed as
English applies to screens exactly as it applies to prose.

### 3. Session

SPECIFIED, NOT DRAWN.

Route: `#/session/<date>`.

Answers: what happened on this day, whole.

Reads: `packet.json`, `midday_packet.json`, `verify_intraday.json`, and the
picks rows the night filled.

This is the only screen where the morning's estimate and the night's
measurement appear together, and the rule from CRITERIA [Truth] governs it:
the night writes BESIDE the morning's values and never over them, so the
screen shows both columns and never one. A premarket volume of 57,031 scaled
by a capture share of 0.1172 and the consolidated figure the truth pass wrote
that night are two different numbers, and a screen that shows one of them and
calls it the volume is worse than the report is now.

### 4. Sessions

SPECIFIED, NOT DRAWN. Replaces the day rail in site/PremarketDesk.html.

[AMENDED 2026-09-04. It leads with a CALENDAR and not with the row per session
below, which the owner read as a wall of line items. Every month on file is
laid out at once, the day the desk holds a morning for is lifted and clickable
and carries that morning's largest gap as a ticker and a bar on one scale
across every month, and every other day is hazed. Two levels of hazing, because
a weekday the machine did not run and a date before the history the desk
carries are different facts. The row per session is still there behind a
Calendar and List toggle; nothing described below was deleted, it stopped being
the first thing seen.]

Route: `#/sessions`.

Answers: what have the mornings looked like, and which one do I want.

Reads: the compacted per session summaries inlined at build time, plus
job-status.jsonl for whether each chain ran clean.

One row per session: the date, candidates kept, day and swing eligible, the
conviction split, the largest gap with its name, and a health mark. The gap
spine appears here at row scale, so a morning's shape is legible before it is
opened.

### 5. Record

SPECIFIED, NOT DRAWN. Replaces site/Weekly.html.

Route: `#/record`.

Answers: is any of this working.

Reads: exactly what weekly_page.py reads today, which is job-status.jsonl, the
meter trail, quantifier-flags.jsonl, verify_intraday.json and picks.

Its five regions are weekly_page's five questions, unchanged, because they
were already the right five and they are already written down in its
docstring: did it run, is it trustworthy, what did it publish, what did it
cost, does the score order anything.

The finding that leads this screen is the one already in record_so_far and
never displayed: of 87 picks over 10 sessions, all 12 that peaked within ten
minutes closed red, and all 5 that peaked after a hundred minutes closed
green. On 17 picks that is a hint and not a rule, and the screen must say so
where it says the rest.

### 6. Name

SPECIFIED, NOT DRAWN. Exists in no form today.

Route: `#/name/<ticker>`.

Answers: has this name done this before.

Reads: every inlined session's candidate rows for that symbol, plus its picks
history.

list_shape.repeat_appearances already computes this over a five session
lookback and read 0 of 12 on 2026-09-03. The screen widens the lookback to
whatever is inlined and gives it somewhere to be seen: the ladder and the tape
path for each appearance, side by side, and what followed each one.

### 7. Health

SPECIFIED, NOT DRAWN.

[AMENDED 2026-09-04. The first build printed five blocks of the packet's raw
JSON, which is the packet talking to itself, and the owner said so. It now
answers its question in sentences: a verdict line, then one check at a time
with a state and an English paragraph carrying the figures. Six or seven
checks depending on the session, and the one that earns the screen its place
is the last: the names that cleared the volume floor only once the capture
estimate was applied and do not clear it on what the socket actually heard.
That is the one place on any screen where a name is present because of a
scaling factor and not because of a measurement, and nothing else displays it.
The JSON is still here, folded, because the working should be checkable and
should not be the first thing read. The route takes an optional date, so any
morning on file can be checked and not only the newest.]

Route: `#/health`, or `#/health/<date>`.

Answers: is the machine right.

Reads: job_health, quota_preflight, collector_coverage,
collector_window_observed and capture_correction, all of which are in the
packet already, plus job-status.jsonl and data/monitor-reruns.json.

Today this is four lines appended to the report's disclaimer and an email from
the watchdog. It is the least glamorous screen in this file and it is the one
that would have shown, on the morning after the outage, that the catch up had
subscribed the collector to proxies only while the watchdog read healthy.

### 8. The report, as written

[ADDED 2026-09-04. Route `#/session/<date>/report`. Not in the original seven,
because when this file was written site/PremarketDesk.html was build_archive's
page and that page's whole job was reading old mornings' prose. The owner
retired it that afternoon and the desk took its filename, so the desk took its
job: desk/compact inlines each session's report.md and report_midday.md,
rendered through render_report.to_html and never markdown.markdown, and this
screen shows them with a toggle where both exist. REPORT_CSS ships with the
desk for it, which is safe beside DECK_CSS because all 46 of its selectors are
scoped under .report. A session whose morning stopped before the render step
carries None and the screen says so, which is a different fact from a morning
that found nothing.]

### The catalyst, and where it is answered

[ADDED 2026-09-04, after the owner asked whether the screens say why a stock
gapped. They did, and only in the third column of the SELECTED name's deck, so
answering it for twelve names took twelve clicks. Two changes: the gap spine
grew a reason column carrying the catalyst class and the story count, with the
sentence in the row's own tooltip, so the question is answered for the whole
list at a glance; and the deck grew a Why it gapped line under its head, above
the three columns.

A name the packet found nothing for reads "nothing found" and its deck says
the move is unexplained by anything this project reads, which is itself a
finding. It must never read "none", which is how the packet spells it: a
screen that prints a field's sentinel at a reader is the report prose rule
applied to a screen.]

### 9. What else moved, and Coming up

[ADDED 2026-09-04, in the review that evening. Not in the original seven and
not an oversight of design so much as of accounting: the eleven report
sections were never checked off against the screens, and two of them had no
screen at all. Section 5, notable movers, was compacted into every payload
from the first build and drawn nowhere, which is the worse of the two: the
bytes were in the file and the reader could not see them. It is the one
section about names that are NOT candidates, so a Morning screen without it
answers "what should I look at" with the pool only.

Both are on the Morning screen. Notable movers is one table over all three
legs with the leg in words in its own column, ranked within a leg exactly as
the packet ranked it, and each of the four lists prints its own state and
denominator underneath, because BUILD_PLAN 4.4 and 4.9 already settled that
a short list with nothing beside it reads as a quiet market. A row routes to
the Name screen, since a mover is often a candidate on another session.

Coming up says which of the three states it is in: not checked, checked and
empty, or a table. The first two are different facts and the screen must not
let them look alike, which is the same rule as the midday pass that never
ran.]

### 10. What the evidence is worth

[ADDED 2026-09-04, after the owner asked where Skips and traps was. Section 11
of the report is the one that says what the morning's evidence is worth, and it
was one ninth drawn: the evidence roll writes nine sentences and only band_thin
reached a screen, on Health, with the scan's eighteen evidence gaps carried
nowhere at all. It is on the Morning screen now, above the composition block,
because the reading order puts it first and a section read first cannot be
three screens away.

Every sentence is quoted as the packet wrote it and printed whether or not it
names anybody, on the rule BUILD_PLAN 4.4 and 4.9 already settled: an absent
line and a clean one look identical and only one of them is good news. The
drawing ITERATES the roll rather than naming its keys, so a sentence the scan
learns to write next year appears with no change here, which is the property
that failed for the eight sentences nobody had thought to name.

The deck gained the third trap state in the same pass. trap is true, false or
null and the badge drew only the true case, so the eight names on that morning
whose question could not be answered looked like the four that were asked and
cleared.]

### 11. Precedent

[ADDED 2026-09-04, at the owner's request, after four rounds on a drawn design.
It is the ninth route and the seventh entry in the navigation.

Route: `#/session/<date>/precedent`.

Answers: what happened the last time a name looked like each of the ones on
this morning's list.

Reads: the compacted payload's `precedent` block, which desk/precedent.py
computes at compact time from `research_outcomes`. It reads no database at
render time, like every other screen here.

THE DESIGN ARGUMENT, because it was made three times before it was accepted
and the wrong version of this screen is easy to build.

  Not on the Morning screen. The first draft put a base rate under each name
  in the ranked list and the owner refused it twice. The refusals were right.
  The score is what the desk THINKS about a name and the base rate is a COUNT
  of what lookalikes did, and folding the second into the first hides the case
  where they disagree, which is the only case either of them ever gets
  corrected by. claim_the_precedent_screen_cannot_borrow_the_record pins the
  separation: screenMorning may not read this payload at all.

  Not a retrospective. The owner's question that killed the first design was
  "the event is over already when they see it", asked of a screen that
  reported on a finished replay. It is the right question and it is why this
  screen is about THIS morning and is read at the same hour as the Morning
  screen. The replay is the engine; the retrospective is a document under
  doc/research/ and not a tab.

  Every section mirrors a Morning section, and says which one. The names on
  this list against the gap spine, and when a winner stopped going up against
  the Record screen's own timing split. Those two splits are NOT the same and
  a finding does not carry between them: Record computes two buckets, minutes
  to the peak at most 10 and at least 100, and this screen cuts five with a
  120 line and no 100 line, and even the shared 10 differs because Record's is
  inclusive and this one is strictly less than. This paragraph said they were
  the same buckets until 2026-09-05, which would have had a reader compare two
  populations as one.

  ALL NINE SECTIONS ARE BUILT, three on 2026-09-04 and six on 2026-09-05.
  The paragraph here used to say the other six needed data the engine does not
  produce, and that was wrong on five of them: the rejects were already being
  graded with their verdict thrown away, the reconstructible evidence lines
  were already columns, the historical calendar was already in every session
  cache, and the session shape was a group by over bands already on the row.
  Only what the desk missed was really blocked, and only because a name nobody
  subscribed has no premarket tape and therefore no entry and no stop, so no
  paper rule can be run on it. Its outcome is the daily bar and it comes from
  research_daily, a separate table for the reason given below.

Regions, in order:

  What history says   one row a candidate: the rule it was matched on, rows
                      AND distinct sessions, how many reached the buy, the
                      middle result, the spread on mark 8, and the median
                      minutes to the high
  When a winner       the whole replayed population split on time to the high,
    stopped going up  drawn only when there is a population to split
  What each floor     every day condition, what it refused across the whole
    turned down       replay, and what those refusals went on to do. The
                      counts OVERLAP: a name can fail two conditions
  Whether thin        three splits, each drawn as a pair so neither side is a
    evidence has      number without a scale. The roll's other six sentences
    cost anything     cannot be rebuilt and are named rather than dropped
  What the desk       every name that cleared a session's gap floor, by band:
    missed            how many the pool had, and what the rest did
  How these events    every overnight reporter, by tier and by whether it beat
    have resolved     the vendor's own estimate
    before
  What kind of        four measures, today's share against the median and the
    morning this is   tenth to ninetieth of every replayed morning
  What noon has       the noon pass's own grade folded from the cached tape,
    graded before     against what the same name did by the close
  What these counts   four things the numbers are not, printed on the screen
    are not           rather than left in a document nobody opens

  TWO TABLES AND TWO INSTRUMENTS. The trade sections measure a simulated entry
  to a simulated exit and read research_outcomes. What the desk missed and how
  these events have resolved read research_daily, which is the DAILY BAR: open
  to close and open to high, for names that were never priced and have no entry
  under any rule. The two must never be compared and every daily bar figure on
  the screen carries that sentence beside it. research_daily is a separate
  table because precedent's own selector excludes only on skip_reason, so such
  a row would otherwise join the denominator of every count above it.

  Mark 8, the spread bar, is new and is the only chart this screen adds: a
  thin line from worst to best, a thick box over the middle half, a dot on the
  median, on ONE scale fixed in CRITERIA [Screens] precedent_strip_domain_pct
  and drawn once in the column heading rather than under every row. A result
  outside the domain is clamped and the clamp is drawn as a dashed notch,
  which is a visible lie rather than an invisible one.

THE EMPTY STATE IS A STATE THIS SCREEN DRAWS, and it was the shipping state on
2026-09-04 because no backtest cache existed on this machine. The pool was
fetched on 2026-09-05, 240 sessions, and the replay filled the table. The empty
state stays and is not decoration: research_outcomes is empty on any machine
that has not run the replay, and the screen then says so, names the command
that fills it, and still prints the rule each name WOULD be matched on, which
is the part worth checking before any number exists. The two daily bar sections
carry their own coverage and can answer while the trade table is still empty,
because they fill from the session caches alone.]

### The navigation, and a screen with no route into it

[CORRECTED 2026-09-04. The navigation shipped as Morning, Midday, Sessions,
Record, Health, and section 8's Report screen was in none of it. Its only
inbound link was a card on the Session screen, which is not in the navigation
either, so the route was Sessions, then a day, then the card. The owner opened
the desk and asked where the morning report was, which is the right question to
ask of a screen that cannot be found. Report is in the navigation now and
resolves against the selected session, like Morning, Midday and Health.

The navigation is the reachability guarantee and it is worth stating as one: a
screen not in it must be linked from a screen that is, or it cannot be opened
without typing a route. Session is the one screen that relies on that, from the
Sessions calendar, and it is a hub rather than a destination.
claim_every_screen_can_be_reached measures the distance rather than looking for
a link, because a link on a screen nobody can find is not a route.]

## Routing and state

  Hash routes only. No server, no history API, no build step. `#/sessions`,
  `#/session/2026-09-03/morning`, `#/name/SNOW`, `#/record`, `#/health`.

  A route is a link. The selected candidate is in the route, so what one
  person is looking at can be sent to another machine and be the same thing.

  Back and forward work, because the router listens to hashchange and does
  not push state the browser did not ask for.

  Filters live in the hash after the route. A filtered spine is a link too.

  Theme is a `data-theme` stamp on the root, remembered in localStorage,
  with the system preference as the default and both themes designed rather
  than one inverted. page.py's TOKENS_CSS already has this exact three state
  shape and the desk uses it unchanged.

  No framework. The prototype is 567 lines of JavaScript and 304 of CSS with
  no library, no CDN and no build step, and it does everything on the Morning
  screen. Angular was considered on 2026-09-04 and declined: it cannot reach
  the email at all, it would put a second source of formatted numbers into a
  project that has already paid for renderer drift once, and it would add npm
  to a scheduled chain that today runs seven python -m steps off one venv.

## PDF

Two paths, and they are for two different people.

FOR A READER AT THE DESK: a button that calls the browser's print dialog. The
print stylesheet forces the light tokens, opens every disclosure, and, before
printing, renders EVERY candidate's deck rather than the selected one, so the
printed file is the whole morning and not the one name that happened to be
open. Ctrl+P gives the same result without the button.

FOR THE MAIL: a `morning/print_pdf.py` step after render_report in the morning
chain. Headless Chrome print to PDF against the local file, no vendor, no new
dependency in requirements.txt, writing `runs/<date>/report.pdf`. deliver.py
attaches it beside the HTML and the plain text part it already sends. The
2026-09-02 run has a report.pdf on disk from a hand run at 330,603 bytes, so
the output shape is already known.

Both stay behind data/UNVERIFIED like everything else that leaves the machine.

## What does not change

  EODHD stays the only vendor in the published path. No screen fetches.
  Every threshold stays in CRITERIA.md. No literal in charts.py.
  The analyst pass, slots mode and the containment checker are untouched.
  The emailed report stays a flat document with a plain text part beside it.
  data/UNVERIFIED still gates delivery.
  The night still writes beside the morning's numbers and never over them.
  scan.py, discover.py and the collector are not opened by this work.

## Build order

  1. `core/charts.py`, the seven marks, returning SVG strings. Tests assert
     every drawn value is present in the packet that was passed in, which is
     the containment property the analyst pass already has, applied to
     pictures.
  2. `site/Desk.html` from a new `render_deck.py`: the shell, the router, the
     Morning screen, the inlined data, wrapped by page.shell like everything
     else. render_report.py keeps writing today's report unchanged.
  3. `morning/print_pdf.py` and the deliver attachment.
  4. Midday, Session, Sessions, Record, Name, Health, in that order, which is
     the order of how often they would be opened.

The conviction colour fix in page.py goes in before any of it, on its own,
because it is a defect and not a feature.

## The knobs this will add to CRITERIA.md

Listed here rather than added there, because criteria.py is a strict reader
and a key with no reader is clutter. They move to a `## Screens` section when
Phase 1 lands.

  inline_sessions        how many sessions the desk inlines whole
  spine_scale_pct        the fixed symmetric scale on the gap spine
  path_min_bars          below which the tape path degrades to a sentence

[appended 2026-09-04] They moved, and four more went with them:
ladder_label_gap_px, name_decks, sessions_page_size and
precedent_strip_domain_pct, all under `## Screens`. The Precedent screen also
added a `## Precedent` section of its own, which is not display bounds but the
match rule: band edges, the two floors and the widening order. It is a section
rather than four more keys under Screens because a band edge is a measurement
rule and a strip domain is a drawing bound, and the two would read as one list.

WHEN THEY MOVE, MIND THE SHADOW TRAP. A note in CRITERIA.md that begins in
column zero with `key = value` is parsed as a second parameter and the last
one wins; that is what disabled slots mode for a day. Never open a sentence in
that file with the name of a key.

## Open questions

  [answered 2026-09-04, see doc/RETENTION.md] How large the inlined file
  actually gets. Measured: a compacted session gzips to 14,856 bytes and
  inlines as 19,808 base64, so a year of sessions is 4.8MB and two years is
  9.5MB, inflated in the page by DecompressionStream with no library. Every
  session the project ever runs fits in one file, so inline_sessions is a
  ceiling and not a window.

  Whether site/PremarketDesk.html and site/Weekly.html are deleted when
  Sessions and Record land, or kept until a month of desk use says the
  screens cover what the pages did. Default is keep, and revisit.

  Whether the emailed copy carries the marks at all, or stays as it is. The
  argument for carrying them is that inline SVG is well supported in mail and
  the pictures are the point. The argument against is that caniemail is not
  the same thing as a real inbox, and the report is currently readable
  everywhere. Decide by sending one to the real inbox before deciding for
  everyone.
