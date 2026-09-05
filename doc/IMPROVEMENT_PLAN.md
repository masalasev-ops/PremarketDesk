# PremarketDesk improvement plan

Written 2026-09-02 against HEAD bb685e7, from a whole tree review: four
independent reading passes (analyst and prompt, rendering, code structure,
scoring and feedback loop) plus the owner's own records in CRITERIA.md,
DECISIONS.md and CHANGELOG.md. Every number below was measured on this machine
against runs/, data/premarketdesk.db and the archived reports, not carried over
from a document. Where a claim comes from a document it says so.

This file is a handoff. Each work package is written so that a less capable
coding model can build it from the package alone, with the acceptance test
stated before the work. Read "Rules for whoever builds this" first and do not
skip it.

## Rules for whoever builds this

These are the project's standing rules and they are enforced by the suite.
Breaking one is a failed package, not a style note.

1. No em dashes anywhere: code, comments, strings, docs, commit messages. Use
   a comma, a colon, or the word "to".
2. Every threshold lives in doc/CRITERIA.md and is read through
   src/core/criteria.py. No decision literal in Python. A new knob is a new
   CRITERIA key with a reasoning note beside it.
3. EODHD is the only vendor in the published path. Alpaca is allowed in
   night/true_volume.py and under src/research/ only. Nothing a morning
   report prints may come from Alpaca. Package 5.4 asks the owner to decide
   whether this rule bends for selection at 07:15; do not pre-empt that.
4. Missing evidence is null with a reason beside it, never a zero, an empty
   list or a False that reads as a measurement. Two thirds of every defect
   this project has ever closed was a falsy value read as an answer.
5. The narrative model is the claude CLI as a subprocess. Never the Anthropic
   SDK, never ANTHROPIC_API_KEY.
6. Do not run any scheduled job by hand to test a change. discover, scan and
   the midday sweep spend quota on a key shared with another project. Test
   through the suite and through the hand runnable paths the suite already
   stubs (analyst is stubbed at invoke_claude; render_report and
   render_midday run end to end on fixtures).
7. Run the suite before and after: `set PYTHONPATH=%CD%\src` then
   `.venv\Scripts\python.exe -m tests.run_tests`. It takes about 40 seconds.
   If the tree photograph fails on a mtime only change to `.git/gk/config` or
   a `.db-shm` sidecar, run it again; two clean runs mean it was an external
   toucher. Package 4.6 fixes the sidecar case.
8. Line endings are mixed per file and git has no autocrlf. Edit with the
   Edit tool, not with a Python script using write_text. Check
   `git diff --stat` before committing: a line count far larger than the
   change means endings were rewritten.
9. Every package that changes behaviour gets a CHANGELOG.md entry saying what
   changed and a DECISIONS.md entry saying why, both dated. Every package
   that changes a template, prompt or CRITERIA key updates the matching
   README.md and BUILD_PLAN.md sentence in the same commit. The suite has
   claims that read the documents and will catch some drift, not all.
10. Commit with the noreply identity already configured
    (`git config user.email` returns the GitHub noreply address). One commit
    per package. Retry `git add` and `git commit` in a loop if Norton denies
    a loose object write; it makes progress every time.
11. Where a package says "owner decision", write the proposal into
    DECISIONS.md and stop. Do not implement the decision.

## What the review found, in one page

The engineering is sound. The suite is green and hermetic, the guards work,
and the record of why every number is what it is has no equal in a project of
this size. The problems are in what the machine spends its effort on and in
what the reader is shown.

**The report.** The model writes a 3,000 to 5,700 word document every morning,
of which roughly 60 percent is packet text copied word for word under
instruction, a further large share is fixed boilerplate (seven notable movers
sentences, four list report lines, column legends under every table, a 30 term
glossary), and the candidate specific content a trader actually reads is
around 6,000 characters. The disclaimer that opens the page is 1,100 to 1,400
characters long and is followed by the Summary. Entry and Stop, the two
numbers the paper ledger books against, became table columns on 2026-09-01
and have no emphasis in the rendered page. The morning HTML has no table
wrapper, no right aligned numbers, no colour on the conviction cell, no links
to the midday report, the archive or the weekly page, and is emailed with no
plain text alternative.

**The analyst.** The instruction set is 68 KB (prompt 16.6 KB, template 51.2
KB), about 15,000 tokens, of which roughly 40 percent is incident history the
model cannot act on. The packet is 66 KB to 167 KB (28,000 to 71,000 tokens)
and carries fields the report never uses. Output runs 18,000 to 29,000 tokens
a morning against a visible report of about 4,000 tokens, so three quarters of
the paid output and of the 200 to 340 second wall clock is reasoning about 28
lettered rules and their prose restatements. Each run costs 0.92 to 1.57
dollars of API equivalent. The quantifier guard has fired seven times; the
owner judged six of the seven false positives, and on 2026-09-01 the scheduled
morning lost its narrative to two of them, both later judged wrong.

**Three live defects.** The template's own "exactly like this" example of an
empty day watchlist (REPORT_TEMPLATE.md:360-362) has a ten cell header over an
eight cell separator; the markdown library renders that as a paragraph of
pipes, not a table, and the containment guard cannot tell. The glossary has
the key "Stop" twice (glossary.py:186 and :198) so the watchlist definition is
dead. The fallback report has no "What the record says so far" section.

**The score.** Refreshed on 55 rows with true excursions: green median best
excursion is -6.88 percent, yellow +1.36, red +1.91, and the inversion holds
inside gap up names and inside gap down names separately, so the direction
confound SCORE_INVERSION.md lists does not explain it. What does explain most
of it, and is written nowhere: the outcome is measured against the premarket
high, and the premarket high sits further from the next open in proportion to
the gap (Spearman 0.695 between absolute gap and the measured premarket range
as a share of the entry, re-measured 2026-09-02 on 55 rows). The gap
component pays two points to exactly the names whose reference level is
furthest away. A reference free outcome, next day open to close, is nearly flat
across buckets. The pre-registered judgement is therefore at risk of returning
"inverted" for a reason about the yardstick, not about the names.

**The screen.** The day screen's volume floor, premarket RVOL above 1.5, is the
binding condition (failed 51 of 68 candidates) and it is applied to a number
the project's own night measures as a median five times too small, because the
collector starts at 07:20 and the baseline accumulates from 04:00. On the
measured number 54 of 80 picks clear it instead of 24. The socket was measured
free on 2026-09-01, so the collector may start at 04:00; the consequence has
not been drawn.

**Discovery.** Published recall of addressable gappers runs 0.05 to 0.15. The
pool holds 0.38 to 0.67 and the 42 slot cap throws the rest away. A free
Alpaca sweep of the completed premarket tape, measured on 2026-08-24 as serving
a live session up to fifteen minutes behind the clock in five requests, would
give the whole universe's measured premarket gap at 07:15. It was dismissed
because of a price age rule that applies to pricing at 08:45, not to selection
at 07:15. This is an owner decision because it puts a second vendor in the
selection path.

**Code.** scan.py is 6,427 lines with a clean eight way split available.
`_as_float` exists nine times with three different NaN behaviours. Atomic
write exists six times. The criteria parser has already swallowed a prose line
as a key. A test claim that raises aborts the rest of its module silently. The
conftest copies 43 MB of data per activation, 59 times a run.

## How the packages are tiered

Tier 0 is bugs: do today, in any order, each under an hour. Tier 1 makes the
report better for its reader without touching the model. Tier 2 restructures
the analyst call so the model does less and the guards see less. Tier 3 is
rendering and delivery. Tier 4 is code health. Tier 5 is the scoring and
feedback loop, and most of it ends in an owner decision rather than a code
change. Tiers 1 to 4 can proceed in parallel. Tier 2 should land before tier 3
package 3.3, because it changes what the renderer receives.

Every package carries: files, steps, acceptance, suite claims to add, effort
(S under two hours, M half a day to a day, L several days), risk, and whether
a less capable model can build it from this text alone.

---

## Tier 0: defects, fix today

Done 2026-09-02, all five, in the commit that follows ae0230d. CHANGELOG
2026-09-02 thirty second records what changed and DECISIONS 2026-09-02 records
the two choices. The packages are kept below as written so the acceptance
tests can be read against the claims that now hold them.

Package 0.6 was added later the same day at the owner's word, as the top
priority on this plan, after GTLB opened about 25 percent higher and was not
on the list. It is also done; CHANGELOG thirty eighth and DECISIONS seventh.

Packages 0.7 to 0.9 were added after the owner said the report looked
unprofessional. All three are done; CHANGELOG thirty ninth, DECISIONS
eighth.

### 0.7 Slots mode has never run (the reason the page looks the way it does)

Files: doc/CRITERIA.md the slots note, src/core/criteria.py `check`.

CRITERIA [Analyst] says `mode = slots`. Four lines below it a sentence began
`mode = slots since 2026-09-02. Under it the narrative pass does not write
the` at column zero. The parser reads a column zero line with an equals sign
under a `##` heading as a parameter, so that is a second [Analyst] mode, and
`_raw` takes the last pair. `report_mode()` saw a value it did not recognise,
printed so into the log, and fell back to freeform. Every morning since the
restructure ran freeform.

Cost, measured on the same packet: freeform 209 seconds, 17,989 output
tokens, $1.27, one 344 word Summary paragraph and a 374 word disclaimer
paragraph. Slots 138 seconds, 13,236 output tokens, $0.68, 20 slots filled
first attempt, 5 Summary paragraphs and a separated disclaimer.

Steps: reword the note so it does not open with the key name; add a
`shadowed` question to `check()` for any key a literal SCALAR accessor reads
that its section defines more than once, counted as a defect by `--check`;
add a claim asserting CRITERIA's mode is one `report_mode()` recognises.
Repeated keys are how pair_map and bands are written, so ask the question
only of scalar reads.

### 0.8 Markdown lists render as prose

Files: src/morning/analyst.py `fallback_report`.

Python-Markdown needs a blank line between a paragraph and a list after it.
Without one the items are a lazy continuation of the paragraph. The
2026-09-02 report shipped eight lists that way, every quoted headline block
among them, which is most of what "words not aligned" describes.

Steps: `open_lists_with_a_blank_line` over the finished document, separating
the OPENING item only. A blank line between items makes the list loose and
wraps each item in a paragraph. Applied at the one return rather than at the
dozen sites that emit a list.

### 0.9 The page is designed to fit rather than to be read

Files: src/core/page.py, src/morning/render_report.py, src/morning/deliver.py.

Prose measure capped at 68 characters with the container left wide; heading
space asymmetric, two lines above and half below; tables with horizontal
rules only, no verticals, no zebra, headers quieter than the data, padding
where the borders were; lining and tabular figures; the sideways scroll box
made keyboard reachable per WCAG 2.1.1; colours re-picked to WCAG AA on both
themes. `page.flatten_variables` resolves every var() and calc() to its light
literal for the emailed copy, because custom properties reach under half the
clients caniemail tracks and classic Outlook has none.

Also fixed here: `_late_hits` compared line text by equality, and a slot's
text is a fragment of the line it lands in, so a flagged mood slot was logged
twice, warned and annotated. Containment on the same quantifier and matched
word makes it one fault.

### 0.6 Names that reported after the prior close have no tier (top priority)

Files: src/selection/discover.py `earnings_before_open` and `assemble`,
doc/CRITERIA.md [Pool tiers], src/research/backtest_pool.py line 144,
src/tests/test_pool.py claim two and three.

What is wrong: the earnings source asks EODHD's calendar for today only and
keeps `BeforeMarket` rows. A name that reported `AfterMarket` on the prior
session, which gaps on this morning's tape, earns no tier. It reaches the pool
only if the overnight news sweep finds it, at tier 2, and is then ordered by
gap propensity like any headline. GTLB on 2026-09-02: 14 fresh items, newest
headline "GitLab Stock Soars 21% After Earnings", propensity 0.108, pool rank
41, tier 2 cut at rank 30, never subscribed, so no artifact of the morning
carries a premarket print for it.

Measured before fixing: one calendar call (2026-08-19 to 2026-09-01) crossed
with the eight `runs/*/pool_recall.json` files. 26 prior day after close
reporters gapped past 3 percent, 23 were in the pool, 2 were subscribed. OKTA
+23.6 (rank 41), ESTC +24.1 (rank 46), GAP +18.7, VEEV +12.4, CRM +11.9, CRWD
+10.1 and QFIN -15.9 were all cut. Today's five (CRDO, DELL, GTLB, MDB, PANW):
one subscribed, on other priors.

Steps:

1. Replace `earnings_before_open` with `earnings_reporters(api, universe,
   today, prior_session=None)`. Prior session from
   `vintage.previous_trading_session(today)`; one call
   `earnings_calendar(prior_session, today)`. Keep `BeforeMarket` rows dated
   today as `tier_key = earnings_before_open` and `AfterMarket` rows dated the
   prior session as `tier_key = earnings_after_close`. Drop the other two
   combinations. Record `window`, `prior_session`, the vendor's `actual`, and
   `prior_session_error` when the calendar could not name the prior session
   and today alone was read.
2. `assemble` claims each earnings name with `evidence.get("tier_key") or
   "earnings_before_open"`, so the replay cache from before the change still
   tiers as it did.
3. CRITERIA [Pool tiers]: `tier = earnings_after_close : 1` and a note with
   the measurement above. Tier 1, not a new tier, so `pool_tier` integers stay
   comparable across old `pool_recall.json` files.
4. Keep `earnings_before_open` as the before open half, for
   `backtest_pool.py`'s cached inputs, and point the fetch at the new source.

Acceptance: a fake calendar with the four timing and date combinations yields
exactly the two reporters, keyed and tiered 1 by `assemble`; the window read
is the prior session to today; a missing prior session is recorded, not
silent. `python -m tests.test_pool` passes; `python -m core.criteria --check`
reads the new key.

Effort S. Risk: on an earnings heavy morning tier 1 now holds both rows and
they compete on gap propensity, an ordering measured on before open reporters
only. The 60 session replay should be refetched through the new source and
re-run; that is the follow up, not a blocker.

### 0.1 The empty table example does not render

Files: doc/REPORT_TEMPLATE.md:321-323 and :360-362, doc/prompt_analyst.md:132,
src/morning/analyst.py `fallback_report` (the empty row it writes), and
src/tests/test_containment.py `claim_headers_cannot_diverge`.

The day header has ten cells since commit 0c89145 added Entry and Stop. The
separator and the none row in both "exactly like this" blocks still have eight.
Python-Markdown's tables extension requires the separator to match the header
width and otherwise emits a paragraph. Verified on this machine with the
venv's markdown 3.10.3.

Steps:
1. Make both separator rows and both none rows ten cells in the template and
   the prompt. The swing table is eight and is already correct.
2. Check `fallback_report` writes the same ten cell rows for the day table.
3. Extend the containment claim to render each required header block (header,
   separator, none row) through `render_report.to_html` and assert `<table`
   is in the output.

Acceptance: the claim fails on the current tree and passes after. Effort S.
Risk none. Delegable: yes.

### 0.2 Duplicate glossary key

File: src/core/glossary.py:186 and :198. Two entries named "Stop". The first
(the watchlist column definition) is dead; the second (midday) wins for both
tables. Rename the midday one to the exact header cell the midday table uses
for its second Stop column, or rename the midday column so the two words
differ. Check render_midday's header and the glossary's table walker agree.
Add a claim that the glossary dict literal has no duplicate keys (parse the
module with `ast` and count `Dict` keys). Effort S. Risk none. Delegable: yes.

### 0.3 Fallback report omissions and leaks

File: src/morning/analyst.py `fallback_report` (lines 350 to 803).

Four fixes:
1. Add the section `## What the record says so far` built from
   `packet["record_so_far"]` in the template's order (REPORT_TEMPLATE.md:704
   onward), including the zero count lines.
2. Economic events: print "actual pending" where `actual` is None. Today it
   prints the Python repr `actual None`.
3. Skips and traps: the line "Trap undecided for A, B, C, ..." listed all
   twelve names on 2026-09-01 because every `trap_why` was the direction
   reason (a gap down cannot be a trap). Where every undecided row carries the
   same `trap_why`, print the reason once with the count and no names.
4. The disclaimer currently embeds the operator's shell command
   (`set PYTHONPATH=%CD%\src && .venv\Scripts\python.exe -m
   ops.quantifier_flags`). Move it to `analyst_usage.json` only. The reader
   facing sentence keeps the flag id and the quoted sentence.

Acceptance: a claim renders the fallback from the 2026-09-01 packet fixture
and asserts the record section exists, no `None` token appears, the trap line
carries no ticker when all reasons match, and no `PYTHONPATH` appears in
report text. Effort S. Risk none. Delegable: yes.

### 0.4 Markdown links and images pass through to the email

File: src/morning/render_report.py:53-68 and test_regressions.py:9688-9709.

`_TAG_OPENER_RE` stops raw HTML tags but `[x](javascript:...)` and
`![p](http://host/pixel.gif)` render as a live anchor and an image. A vendor
headline containing markdown image syntax becomes a tracking pixel in the
emailed report and a network fetch in the archive, which build_archive.py:4
promises never happens.

Steps: register a Python-Markdown Treeprocessor in `to_html` that removes
every `img` element and every `a` whose href does not start with `http://` or
`https://`; extend the existing claim with both payloads.

Effort S. Risk none (no archived report carries a link). Delegable: yes.

### 0.5 The worst case clock is four CLI runs, not two

Files: src/morning/analyst.py:161-182 and :1993-2005, doc/CRITERIA.md
[Analyst] timeout note.

`invoke_claude` retries `max_attempts` (2) times on CLI failure. `write_report`
calls it `quantifier_regenerations + 1` (2) times. CRITERIA's arithmetic
assumes two runs at 1,007 seconds each, ending 09:18:53. The true worst case is
four runs plus the second CLI call for gap_reasons (also 1,007 seconds), which
passes the open. Nothing has hit it. Either cap total CLI runs per morning at
two in code (a shared budget counter passed into `invoke_claude`), or correct
the CRITERIA note and accept the risk in writing. Add a claim that counts CLI
invocations in the stubbed path with a failing first attempt and a flagged
second, and asserts the cap. Effort S. Risk low. Delegable: yes, with the
budget approach.

---

## Tier 1: report content, no model change

Done 2026-09-02, all five packages, with one departure: package 1.4 kept
prompt rule 17 rather than replacing it with article_scope.why, for the reason
DECISIONS 2026-09-02 second gives. Acceptance was a hand run on the 2026-09-01
packet: one attempt, zero quantifier flags, the strip above the disclaimer,
Technical signals as a table with the "Write ups: 0 of 12" sentence, the lower
bound arithmetic once and the collector check once. The report was 6,347 words
against 5,725 for the previous hand run of the same packet, the strip and the
table accounting for about 230 of the difference and the rest being run to
run variance in the gappers blocks; output tokens were 30,951 against 20,013,
which is the thinking cost tier 2 exists to remove. CHANGELOG 2026-09-02
thirty third.

### 1.1 Lead with the decision, not the disclaimer

Files: src/morning/render_report.py (a Treeprocessor or a pre-render pass on
the markdown), doc/REPORT_TEMPLATE.md for the wording of a new strip.

The page currently opens with a 1,100 to 1,400 character disclaimer, then a
one sentence Summary, then the gappers table. The reader at 08:50 wants: how
many names are day eligible, which, at what entry and stop, and what the
market tone is.

Steps:
1. Render a summary strip directly under the title from the packet, not from
   the model text: day eligible N of M, swing eligible N of M, gap direction
   count (from `list_shape.text.gap_direction` once it ships), the strongest
   bucket names with direction (from `score_roll.summary`), and the four index
   proxies with change. Build it in Python in analyst.py's annotation stage,
   the same way `annotate_score_bands` and `annotate_job_health` already
   insert deterministic text.
2. Move the "Nothing here is advice" paragraph to directly under the strip
   and give it a `disclaimer` class the renderer styles small and muted. The
   analyst still finds the line by its opening words; nothing about the guard
   changes because the guard reads the markdown before annotation.
3. Where day eligible is zero, the strip says so in one line with the top
   failed condition quoted from `screen_tally.day.failed_summary`.

Acceptance: a claim renders the 2026-08-31 fixture and asserts the strip
precedes the disclaimer, the counts equal the packet's, and every ticker in
the strip is in the packet. Effort M. Risk low. Delegable: yes.

### 1.2 Repetition budget

Files: doc/REPORT_TEMPLATE.md, doc/prompt_analyst.md.

The phrase explaining why RVOL is a lower bound appears four times in the
2026-09-01 hand run (disclaimer, Summary, Technical signals, Skips). The
estimate sentence appears twice. The collector check numbers appear twice.
MMED's null RVOL reason appears five times. Each repetition was instructed.

Steps: decide one home for each fact and remove the other instructions.
Proposed homes: lower bound and estimate go in the disclaimer only (they are
already there as `evidence_missing_shared.text` and rule 6c); the collector
check goes in Technical signals only; a per name null reason appears in that
name's gappers block (`evidence_missing.text`, rule 19) and nowhere else.
Delete the sentences in Technical signals (template lines under "WHEN A RATIO
IS A LOWER BOUND" and the collector check paragraph's duplicate) and Skips
that restate them.

Acceptance: hand run one packet through the CLI (one run, about 1.40 dollars)
and count occurrences of "lower bound", "estimate" and the collector
percentage; each at most once outside the disclaimer. Effort S. Risk low.
Delegable: yes, the edits are deletions.

### 1.3 The Technical signals section gets a table and loses the essay

Files: doc/REPORT_TEMPLATE.md Technical signals block, src/morning/analyst.py
`fallback_report` (which already renders this as a table).

The model writes twelve paragraphs restating levels the tables above already
carry, and this is where both 2026-09-01 quantifier flags fired (line 117 in
both attempts), because a section describing twelve rows without a table
invites a sentence about the set. The fallback's table version is the better
document.

Steps: make the fallback's table (ticker, premarket high with partial marker,
low, VWAP, prior high, 200 day, score, conviction) the required shape in the
template, with a fixed header so the containment guard reads it. Keep one
prose paragraph per day eligible name only, ending with the invalidation line
(rule 16), which is then always instantiable because those names are in the
watchlist table. Delete the instruction to write up ineligible names.

Acceptance: a claim asserts the fixed header is in `_REQUIRED_TABLES` or in
the claims checked set; a hand run shows the section under 400 words on a
twelve name morning. Effort S for the template, S for the guard header. Risk
low. Delegable: yes.

### 1.4 Rule 16 and rule 17 are asked of the wrong population

Files: doc/prompt_analyst.md rules 16, 17a to 17c, doc/REPORT_TEMPLATE.md
Technical signals and Premarket gappers blocks, src/morning/scan.py
`_scope_articles` (line 2122).

Rule 16 restricts the invalidation level to levels "printed for that ticker in
the watchlist table above" but asks for the line on every candidate; on an
empty morning eleven of twelve have no such row. No archived report carries
the lead in, so `invalidation_violations` has never fired on real output.
Rule 17a asks the model to classify each headline as company, sector or peer,
which is a judgement the packet already computes: `article_scope` with
`about_this_name` and a `why` is in the 2026-08-31 packet.

Steps: scope rule 16 to day and swing eligible names (package 1.3 does this).
Replace 17a with "quote `article_scope.why` under each headline where it is
not null" and keep 17c (what the headline says happened) as the one remaining
judgement, or drop 17c too and let the gap_reasons pass carry it. Remove the
retracted trap instruction block at prompt lines 55 to 72; the correct rule is
one sentence and the specimen is a distractor.

Acceptance: `instruction_violations` still green; a hand run carries the
invalidation line for every eligible name and none for ineligible ones.
Effort S. Risk low. Delegable: yes.

### 1.5 Midday report reaches the reader

Files: src/night/build_archive.py `collect_runs` (:297-320), tasks/job_midday.bat,
src/morning/render_report.py footer.

report_midday.html is written at 12:00 and nothing links to it or archives it.
The morning report has zero anchor tags.

Steps: add a footer to report.html with relative links to the previous
session's report, this day's report_midday.html, the archive with the day's
hash, and Weekly.html, inside a `local-only` div. `deliver.py` strips that div
before emailing (relative links are dead in mail). `collect_runs` reads
report_midday.md as a second block per day, rendered under the morning report
in the archive pane behind a heading.

Acceptance: a claim builds the archive from two fixture days and asserts the
midday heading appears once per day that has one and the footer links resolve
to files that exist in the fixture tree. Effort M. Risk low. Delegable: yes.

---

## Tier 2: the analyst call does less

Done 2026-09-02: 2.1 as slots (2.2 not taken, DECISIONS 2026-09-02 third
says why), 2.3, 2.4 steps 1 and 2 with the guard left enforcing rather than
step 4, 2.5 with effort moved to low, and 2.6. CRITERIA [Analyst] mode is
slots. Acceptance was three hand runs on two archived packets, first attempt
clean each time, the table in CRITERIA's slots note: the 2026-09-01 packet
fell from 227 to 359 seconds to 134, output tokens from 20k to 31k to 13k, the
2026-08-31 packet with a SETUP slot from 207 seconds to 97. Two of the plan's
acceptance figures were not met and are recorded as such: output tokens are
13k to 15k rather than under 6k, because the model thinks before it writes,
and the CLI took 97 to 156 seconds rather than under 90. CHANGELOG 2026-09-02
thirty fourth.

This is the structural change. Everything the report quotes word for word is
already rendered by `fallback_report`. The model is paid to copy it and a
guard then checks it did not paraphrase. The 2026-08-31 report that survived
the guard is at least 60 percent verbatim packet text.

### 2.1 Python renders the skeleton, the model fills prose slots

Files: src/morning/analyst.py (new `render_skeleton` built from the
`fallback_report` helpers), doc/REPORT_TEMPLATE.md (shrinks to the prose
slots), doc/prompt_analyst.md (drops rules that no longer apply), doc/CRITERIA.md
[Analyst] (new knob naming the mode, so the old path stays selectable while
the new one is measured).

Rendered deterministically: title date line, disclaimer (all six
`evidence_roll.text` items, `evidence_missing_shared.text`,
`score_roll.unscored`, dropped stale, capture share sentence, quota line,
silent symbols), the Summary counts sentence and bucket roll and the four
`list_shape.text` lines, all five tables including the notable movers table
and its seven fixed sentences and four `list_reports` lines, market snapshot
table, Skips and traps (evidence_roll with the per symbol why lines), the
record section, Coming up, economic events, column legends, glossary, score
band legend, job health.

Asked of the model, as bounded prose slots with a fixed marker each:
1. `{{MOOD}}`: the two to six word title phrase.
2. `{{TONE}}`: two or three sentences on the market snapshot mix.
3. `{{GAPPER:<TICKER>}}`: per candidate, the headline list with publisher and
   time (quoted), the `catalyst_why`, the `article_scope.why` lines, and the
   `evidence_missing.text` line. This can also be rendered; leaving it to the
   model keeps one place where headlines are read in prose.
4. `{{SETUP:<TICKER>}}` for each day or swing eligible name only: levels in
   words, what fired, and the invalidation line.
5. `{{RATES}}`: one sentence on what the rate picture does to the gap trade.

The model receives: the prompt (shortened), the skeleton with markers, and a
projected packet (package 2.3). It returns the skeleton with markers replaced.
analyst.py verifies every marker was replaced exactly once and nothing outside
a marker changed (diff the non slot text against the skeleton it sent; any
change is a failed attempt, same cost as a quantifier flag today). Containment
and the quantifier guard then run over the assembled page exactly as now, but
the prose they scan is a few hundred words.

Steps for the builder:
1. Extract every section builder in `fallback_report` into functions returning
   markdown strings; `fallback_report` becomes a composition of them with the
   slots filled by fixed "narrative withheld" sentences.
2. `render_skeleton(packet)` composes the same functions with markers.
3. `_compose_stdin` sends prompt, skeleton, projected packet.
4. After the CLI returns, `_check_slots(sent, received)` enforces the marker
   contract and returns the list of slot texts for the guards.
5. New CRITERIA key `analyst.mode = slots | freeform`, default freeform until
   five mornings of hand runs on archived packets pass.
6. Prompt rules that go: 6a, 6b, 6c, 9, 10 (numbers are rendered), 12, 13's
   rationale (the rule stays one line), 14 becomes "return the document with
   every marker replaced", 15, 18a to 18d. Rules that stay: 1, 2, 3, 4, 5 (one
   sentence), 7, 8, 11, 13 (one line), 16, 17c or its replacement, 19.

Acceptance: five archived packets hand run through the CLI in slots mode with
zero structural failures and zero guard flags; output tokens under 6,000 a
morning; CLI time under 90 seconds; containment `claims_checked` at least as
high as the freeform run of the same packet. Effort L. Risk medium, mitigated
because the fallback already renders every section and the guards still run.
Delegable: the extraction (step 1) and skeleton (step 2) yes, with this
section as spec; the slot contract (step 4) and prompt rewrite (step 6) should
be reviewed by a stronger model before the mode flips.

### 2.2 Structured output instead of markdown slots (alternative to 2.1)

Same skeleton, but the model returns JSON keyed by slot name and ticker, and
the renderer places the values. gap_reasons.py already works this way and its
`validate` (line 148) is the pattern: a cited headline must be one that was
supplied or the row is refused with a reason. Advantages: containment can
validate keys against packet symbols before any prose is placed; the
invalidation sentence can be checked per ticker for digits; a malformed field
costs one slot, not the morning, if parsing salvages per key. Disadvantage: a
second parser to harden. Pick 2.1 or 2.2, not both. 2.2 is preferred if
gap_reasons' cite or refuse behaviour has been reliable in production; check
`analyst_usage.json` `gap_reasons` blocks across the archived runs first.

### 2.3 Project the packet before piping it

File: src/morning/analyst.py `_compose_stdin` (line 106).

Per candidate the packet carries `pm_rvol_basis`, `pm_float_rotation_basis`,
`trap_basis` (only quoted when trap is true, which has not happened since the
balance rule), `headline_polarity`, `pool_evidence`, `pool_tier_reason`,
`prior_close_quoted`, `provisional_gap_pct`, `gap_2session`, `gap_3session`,
`avg_dollar_volume_20d`, and every headline's `url`. `notable_movers` is 11.5
KB of which the report uses six keys. `capture_correction.rows` is never
quoted per row. None of it reaches the report.

Steps: build a projection function that deep copies the packet and deletes a
named list of paths; pipe the projection; keep packet.json on disk unchanged
and keep `_packet_uppercase_tokens` reading the full packet (it takes
`packet_text` separately, so this is already true). The path list lives in
analyst.py as a constant with a comment per entry saying which template line
would have needed it.

Acceptance: a claim asserts the projected 2026-09-01 packet is at most two
thirds the size of the original and that every field the template names
(grep the template for backticked packet paths) survives the projection.
Effort S. Risk low. Delegable: yes.

### 2.4 Quantifier guard: judge it on its own record

Files: src/morning/analyst.py:866-880 and `_scan_prose` (:1089-1113),
doc/CRITERIA.md [Analyst] the warn mode note, data/quantifier-flags.jsonl.

Seven flags judged, six false positives, per DECISIONS 2026-09-01 ninth. The
owner's own analysis found two shapes: misgovernment (the determiner governs
another noun, `no bars`, `no trade`) and true and checkable universals. The
word `name` as a set word collides with ordinary "that name" prose every
morning.

Steps, in order and each measured against the seven logged flags and the
eight archived reports before and after:
1. Remove `name` and `names` from `_SET_WORDS`. Re-run the guard over the
   archived reports and count.
2. For `no`, require the set word within two words forward instead of six.
3. Add a checkability pass: a universal is allowed when its predicate is a
   printed count in the same report (screen_tally failed_summary lines). This
   is the "shape B" instrument DECISIONS names as the harder half; build it
   only if steps 1 and 2 leave the rate above one flag in ten mornings.
4. While tuning, set `quantifier_guard = warn` per CRITERIA's own instruction
   for exactly this case, and put it back once the word list has ten more
   mornings on record.

Acceptance: the guard over the eight archived narratives flags only id 4
after steps 1 and 2. The suite's claim that the prompt's banned and set word
lists match the code's must be updated in the same commit. Effort S for steps
1, 2 and 4; M for 3. Risk: a real overclaim slips through, which is the same
trade CRITERIA accepted for the prose stopwords. Delegable: steps 1, 2, 4 yes;
step 3 no.

### 2.5 Re-measure effort low against today's template

File: doc/CRITERIA.md [Analyst] `effort`.

The medium versus low comparison dates from 2026-08-14 and predates every
quoted text field that removed the model's need to reason. Output tokens are
three quarters thinking. Hand run the same archived packet at low and medium
once each (about 3 dollars) and compare section completeness, guard flags,
containment coverage and duration. Record the table in CRITERIA beside the
existing one. If 2.1 lands first, run the comparison in slots mode, where low
is very likely enough. Effort S. Risk none (it is a measurement). Delegable:
yes.

### 2.6 gap_reasons parse is all or nothing

File: src/morning/gap_reasons.py `_parse` (line 131).

`find("{")` to `rfind("}")` fails on a brace inside a model `why` string and
loses the whole section. Salvage per ticker: try the whole document, and on
failure split on the top level ticker keys with a tolerant regex and validate
each record independently; a refused record prints its refusal reason under
the ticker as `validate` already does for a bad citation. Also `headlines_all`
(added 2026-09-01) is empty in every archived packet, so the pass has only
ever read three headlines per name; confirm scan populates it on the next live
morning and add a claim on the fixture. Effort S. Risk low. Delegable: yes.

---

## Tier 3: rendering and delivery

Done 2026-09-02: 3.1 (core/page.py, all four renderers through it), 3.2, 3.3
(landed in tier 1), 3.4 and 3.5 (the midday hand parser removed in favour of
render_report.to_html). 3.6, the sparklines, is not done. CHANGELOG
2026-09-02 thirty fifth, DECISIONS 2026-09-02 fourth.

### 3.1 One page shell shared by four renderers

Files: new src/core/page.py; src/morning/render_report.py:70-102,
src/midday/render_midday.py:40-87, src/night/build_archive.py:40-198,
src/night/weekly_page.py:373-414 and :975-1193.

Four unrelated stylesheets: Georgia at 720 px, Georgia at 940 px, Segoe UI
with dark mode variables, and a Weekly page with no doctype, no charset and no
viewport meta (it opens in quirks mode from disk and would mis-decode a non
ASCII string on Windows). build_archive.py:12-13 claims an archived day and a
fresh one look identical; they do not.

`core/page.py` provides: `shell(title, body_html, extra_css="")` returning a
full document with doctype, charset, viewport, one token set with a
`prefers-color-scheme` dark block, `.tablewrap {overflow-x:auto}`, `.num`
right aligned with `font-variant-numeric: tabular-nums`, conviction cell
classes, a print block; `escape(text)`; `num(value, digits)` and `pct(value)`
with one null spelling. The four renderers import it. The archive embeds the
same report CSS block so parity is true by construction.

Constraints: test_regressions.py:9711-9734 reads render_report.py and
build_archive.py source for specific strings, and :9119 reads weekly_page.py
source to assert it "reads and renders and nothing else". Read those claims
first and keep the strings they pin, or update the claims in the same commit
with a DECISIONS entry.

Acceptance: all four outputs validate as full documents (doctype, charset,
viewport present); the suite is green; a claim asserts the four modules import
`core.page` and contain no `<style` literal of their own. Effort M. Risk
medium because of the source reading claims. Delegable: yes if the pinned
strings are listed in the package handed over.

### 3.2 The morning HTML reads like a table page

File: src/morning/render_report.py (a Treeprocessor after the markdown pass).

Steps: wrap every table in `.tablewrap`; add `class="num"` to cells that parse
as a number; colour the Conviction cell by its word (green, yellow, red,
unscored muted); add `border="1" cellpadding="6"` attributes to every table as
the fallback for mail clients that strip `<style>`; collapse a watchlist table
whose only body row is `none` to nothing, since the sentence beneath says the
same. Acceptance: a claim renders the 2026-09-01 fixture and asserts each
transformation with an HTML parser. Effort M. Risk low, additive markup.
Delegable: yes; the Treeprocessor API is small and 0.4 introduces it.

### 3.3 Email: text alternative, subject, no operator text

File: src/morning/deliver.py:157-162.

Send `"text": report.md` beside the HTML (it is on disk already). Subject
carries the title line and the day eligible count. Strip the `local-only`
footer (package 1.5). Acceptance: a claim on the stubbed send asserts the
payload has both parts and the subject matches the title. Effort S. Risk low.
Delegable: yes.

### 3.4 Archive on a phone and on paper

File: src/night/build_archive.py:46-132.

`.rail` is fixed at 250 px inside a 100vh flex shell with no media query, so a
phone gets a 140 px report pane, and printing yields one viewport because the
pane scrolls. Add `@media (max-width:720px)` turning the shell into a column
with a horizontally scrolling rail, and `@media print` that hides the rail and
hint and lets the pane flow. Effort S. Risk low. Delegable: yes.

### 3.5 Midday renderer promises it breaks

File: src/midday/render_midday.py:149, :406, :443.

`_cell` escapes `|` as `\|` and `to_html` splits on bare `|`, so an escaped
pipe becomes an extra column. `_inline` splits on `**`, so a headline
containing two asterisks opens bold for the rest of the line. Either honour
the escapes in the parser or stop promising them: replace `|` with `/` in
cells and escape `*` in inline text. After 3.1 the better fix is to render
midday through the markdown library like the morning report, removing the hand
parser entirely. Effort S. Risk low. Delegable: yes.

### 3.6 Sparklines from the collector file (later, and not for a junior model)

premarket_snapshot.jsonl carries about 80 one minute bars per symbol. An
inline SVG polyline per gapper row in report.html and the archive would show
the shape of the premarket path beside its numbers. Mail clients strip SVG so
it is HTML only. It aligns a rendered artefact with collector evidence for the
first time and needs judgement about window boundaries, replay bars and thin
symbols. Effort M. Risk medium. Delegable: no.

---

## Tier 4: code health

Done 2026-09-02: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.9. Not done, and left to the
owner to schedule for the reasons DECISIONS 2026-09-02 fifth gives: 4.5, 4.8,
4.10. CHANGELOG 2026-09-02 thirty sixth.

### 4.1 One `as_float`

Files: src/morning/scan.py:59, src/selection/discover.py:62,
src/night/pool_recall.py:40, src/selection/gap_stats.py:145,
src/selection/universe.py:83, src/midday/scan_midday.py:157,
src/night/fill_outcomes.py:102, src/night/paper_ledger.py:215,
src/night/true_volume.py:300.

Nine copies, three behaviours: one also rejects the string "NA", five reject
"" and NaN, three accept NaN as a float. A vendor NaN reaches paper_ledger and
fill_outcomes today. Write `core/numbers.as_float` that rejects "", "NA", NaN
and infinities, returns None otherwise, and replace all nine. Add a claim with
the table of inputs. Effort S. Risk low. Delegable: yes.

### 4.2 One atomic write

Files: src/core/config.py:403-410, src/morning/deliver.py:62,
src/morning/scan.py:6048, :6069, :6190, src/ops/market_today.py:105,
src/ops/monitor_jobs.py:352, src/selection/universe.py:947.

Six implementations of temp sibling plus `os.replace`. config.py's own
docstring explains it cannot import universe's version because core cannot
import selection. Write `core/files.write_text_atomically(path, text)` and
`write_json_atomically(path, obj)` and replace all six. Effort S. Risk low.
Delegable: yes.

### 4.3 CRITERIA check command

Files: src/core/criteria.py, new claim in test_regressions.

The parser treats any column zero line containing `=` under a `##` heading as
a pair and has already swallowed prose: section [paper] carries the key
`quotient: 10,000 / 0.04`. `###` headings are not section boundaries. A typo
in a key read inside `score_candidate` or `evaluate_eligibility` surfaces at
08:45 on the first candidate.

Build `python -m core.criteria --check` that: rejects keys containing spaces
or colons unless the section is a declared pair map section; walks src/ with
`ast` for literal `_CRIT.<accessor>("section", "key")` calls and asserts each
resolves; lists pairs with zero references. Wire it as a claim. Effort M. Risk
low. Delegable: yes, with the accessor list from criteria.py handed over.

### 4.4 Test runner: a raising claim must not hide its siblings

Files: every src/tests/test_*.py `main()`, src/tests/run_tests.py:227-231.

A claim that raises is caught at module level, so the remaining claims of that
module never run and the report says the module failed once. Wrap each claim
call so the traceback is appended to `failures` and the loop continues.
test_regressions already does this in six places; make it uniform. Effort S.
Risk low. Delegable: yes.

### 4.5 Conftest copies 43 MB fifty nine times

File: src/tests/conftest.py `activate` (line 659).

Copy data/ once per module, or take an explicit list of files a claim needs.
Some claims rely on the copied universe.json and database, so this needs a
run per module while changing. Effort M. Risk medium. Delegable: partly; do it
after 4.6 and one module at a time.

### 4.6 Tree photograph exemption for SQLite sidecars

File: src/tests/conftest.py `differences` (line 402), `snapshot_tree` (:342).

A `.db-shm` or `.db-wal` mtime only change with size unchanged fails the suite
on a run where every claim passed. It is the same intermittent the FETCH_HEAD
and sampler exemptions were written for. Add the exemption with the same three
condition rigour (named path pattern, mtime only, size unchanged) or exclude
the sidecars from the copy. Effort S. Risk low. Delegable: yes, with the
existing exemption as the pattern.

### 4.7 Schema ownership and a version table

Files: src/core/store.py:142, src/night/fill_outcomes.py:179 and :446,
src/night/backfill_premarket.py:451.

picks has about 85 columns declared across four files. Move the two night
owned column tuples into store.py beside `_PICKS_LATER_COLUMNS`, add a
`schema_version` table written by `init()`, and stop running the
`UPDATE picks SET source='test' WHERE source IS NULL` backfill on every
connection (store.py:517) once a version stamp says it has run. Effort S.
Risk low. Delegable: yes.

### 4.8 Split scan.py

File: src/morning/scan.py into a package src/morning/scan/ with a re-exporting
`__init__.py`.

Proposed modules and their functions by current line: collector.py (111 to
1035 and 1215), pool.py (391 to 1011), volume.py (1079 to 1834 and the volume
check helpers), catalysts.py (2094 to 2755), screen.py (2895 to 4134),
shape.py (3140 to 3324), notable.py (4306 to 5460), packet.py (97, 5466 to
end). The suite pins private names (`scan._promote_snapshot`,
`scan.write_packet` and others): grep `scan\.[a-z_]+\(` in src/tests and
re-export every hit. Watch the lazy import cycles: analyst and
quantifier_flags, analyst and gap_reasons, scan importing night.paper_ledger.
Effort L. Risk medium. Delegable: no; the private name pins and the import
graph need judgement.

### 4.9 Small cleanups

pyflakes reports 47 lines: unused `sys` in render_midday.py:23,
scan_midday.py:41, replay_session.py:83; unused imports in
float_rotation_study.py:96, replay_session.py:88, test_containment.py:629,
test_regressions.py:1409, :7589, :9141; `baseline_row` unused at scan.py:3578.
Add requirements-dev.txt with pyflakes. Move src/probe_alpaca.py into a
package (it is imported by night/true_volume.py, so `collect/` fits). Effort S.
Risk none. Delegable: yes.

### 4.10 A single job entrypoint (later)

Ten .bat files repeat a twenty line preamble and spawn a Python interpreter to
compute the date; monitor_jobs.JOBS pins the echo markers as regexes, so the
marker text is one contract in two places. `python -m ops.run <job>
[--catchup]` would hold the preamble once and write the markers from the same
constant the monitor reads. test_entrypoints pins the 23 module entrypoints
and register_tasks.ps1 would change its `-Argument`. Effort M. Risk medium.
Delegable: no, until the marker contract is written down as a spec.

---

## Tier 5: scoring, screens and the feedback loop

Done 2026-09-02: 5.1, 5.2, 5.3, and 5.6 written into DECISIONS 2026-09-02
sixth as five proposals and stopped at. Not built: 5.4 and 5.5, the two
research instruments, because each needs a pre-registration note written
before its first run and an afternoon of Alpaca fetches. CHANGELOG 2026-09-02
thirty seventh.

Most of this tier ends in a written proposal for the owner, because the
project's own rule is that a threshold moves only on a pre-registered
measurement and the score is under a pre-registered evaluation. The work a
model can do is to build the instruments and write the amendments.

### 5.1 Amend SCORE_INVERSION.md before the judging point

File: doc/research/SCORE_INVERSION.md register block.

Add, dated: the premarket range confound (Spearman 0.695 between absolute gap
and the measured premarket range as a share of entry_ref_true; range against
best excursion -0.351, both re-measured 2026-09-02 on 55 rows);
the finding that the inversion holds within each gap sign (gap up green n=12
median -5.28 against yellow n=12 -0.54; gap down green -8.39 against yellow
+2.93); a reference free co-secondary outcome, next day open to close, which
is already a picks column; and a commitment to report medians by gap band
beside buckets. CRITERIA's amendment convention allows this before a judging
point. No rule moves. Effort S. Risk none. Delegable: yes.

### 5.2 Weekly page: the record a trader would ask for

File: src/night/weekly_page.py:634-973.

All reads of existing columns, same withholding rule (`min_group_rows`,
`min_group_sessions`) per cell: medians by gap band (3 to 5, 5 to 8, over 8),
by direction, by catalyst class, by day eligible versus not; own session
premarket high break rate (booked plus unsized over evaluated, currently 17 of
55) and next day break rate (31 of 55); stop hit rate among booked (5 of 17,
median -7.72) against held to close (12, median -0.56); v1 and v2 side by
side; and the size of the record in words at the top of every table. Effort
M. Risk low. Delegable: yes.

### 5.3 Store pick day open and close for every pick

Files: src/night/paper_ledger.py and src/night/fill_outcomes.py, new picks
columns via store.py.

A reference free outcome exists only for booked trades. The 2026-08-29
DECISIONS entry quotes open to close for never triggered picks, so it was
computed once and stored nowhere. Add the two columns, fill them nightly for
every live pick, null for rows before the change, never overwritten. Effort S.
Risk low. Delegable: yes.

### 5.4 Offline replay of screen, proxy score and outcomes over 60 sessions

Files: new src/research/replay_outcomes.py beside replay_session.py; a
pre-registration note under doc/research/ written before the first evaluate.

replay_session.py already fetches 42 name premarket tapes and baselines from
Alpaca for a completed session at zero EODHD cost and fences its writes three
ways. backtest_pool has 60 cached sessions with earnings names, news titles,
prior closes and end of day bars. DECISIONS twelfth says the score cannot be
rebuilt because news tags are absent; earnings versus none, the component that
determines the bucket on the live record, is reconstructible from the session
cache's earnings list.

Design: extend fetch with a `--universe` mode (five requests per session for
the whole universe 04:00 to 08:45); evaluate the day screen and a proxy score
with `score_unavailable` naming the tags gap; write outcomes to a new table
(`research_outcomes`), never to picks outcome columns and never to
paper_trades; simulate the v1 paper rule by importing `paper_ledger.simulate`
as a function. Questions to pre-register: does the proxy score order pick day
open to close; does the gap band; how often is RVOL the binding condition on a
true tape; what recall does a full universe sweep have against the screen.
Must not: move a CRITERIA key, run from a scheduled job, spend EODHD quota,
write a date holding live rows, or be re-run with a changed question after
results exist.

Acceptance: a claim greps the module for any write to `paper_trades` or to
picks outcome columns and fails if one exists; the note carries a date earlier
than the first payload. Effort M. Risk: forking paths, held by the
pre-registration. Delegable: yes; the two stage pattern and the fences exist.

### 5.5 Test the Alpaca premarket sweep as a fifth discovery prior, offline

File: new src/research/premarket_prior_test.py.

For the nine live sessions: sweep 04:00 to 07:00 of the completed tape, rank
the universe by absolute gap against the cached prior close with a volume
floor, take 42, and score `subscribed_recall_addressable` against each
session's pool_recall.json `actual_gappers`. Pre-register the ranking rule and
the bar (beats the shipped recall on at least seven of nine sessions) before
running. Zero EODHD quota, nothing live, nothing written under picks. Effort
S to M. Risk none. Delegable: yes.

### 5.6 Owner decisions, written up and stopped at

Write each of these into DECISIONS.md as a proposal with the measurement that
motivates it, and stop.

1. TAKEN 2026-09-02. Move [Collector] start_time toward 04:00. Done as a
   two phase collector: discover at 03:55 and 07:15, the socket opening at
   04:00 on the provisional pool and moving onto the real one at the
   handover. DECISIONS 2026-09-02 ninth says what it was chosen over and
   CHANGELOG forty third what changed. The acceptance test stands and is
   owed: median pm_rvol_true over pm_rvol from about 4.6 toward about 1.4
   over ten sessions, day eligible counts published before and after.
   Neither the RVOL floor nor the float rotation edges is retuned yet, on
   purpose.

2. Sign aware candidate selection. Top twelve by absolute gap on 2026-09-01
   yielded twelve gap down names on a long only screen, so nothing could pass
   by arithmetic. Options: top six up and six down, or top twelve by signed
   gap. Changes the population the rotation edges were fitted on.
3. Drop gap size from the score sum into a size label beside the name, and
   publish the components as a checklist without the word conviction, per the
   freeze's clause 2. Rows before the change keep their score and the watch
   restarts after. This changes the instrument under evaluation and is the
   owner's call under CRITERIA [Score gap]'s own note.
4. A second vendor in the selection path, if 5.5 passes. This bends hard rule
   1 at 07:15 while leaving the published path EODHD only. Needs its own
   DECISIONS entry and a CRITERIA [Pool tiers] source with 403 recorded as
   not_fetched.

A fifth item, the disposition of `data/UNVERIFIED`, stood here until
2026-09-02 and was dropped from the plan at the owner's word (DECISIONS
2026-09-02, seventh). The gate itself is unchanged.

### 5.7 Precedent: what happened the last time a name looked like this

Added 2026-09-04 at the owner's request, after four rounds on a drawn design.
This package is the REASON to build 5.4 rather than a screen bolted onto it,
and 5.4's evaluate half is folded into it here. Build 5.4's fetch first; it is
unchanged and its fences hold for this too.

Files: new `src/research/replay_outcomes.py` (the engine), new
`src/desk/precedent.py` (the matcher), a new `research_outcomes` table via
store.py, a new Precedent route in `src/desk/assets.py` and
`src/desk/render.py`, a new `[Precedent]` CRITERIA section, and
`doc/research/PRECEDENT_PREREGISTRATION.md` written BEFORE the first evaluate.

WHAT IT IS. A separate screen, reached from its own tab, whose every section
is the historical mirror of a section the Morning screen already carries. The
Morning screen is not changed, and that is a requirement and not an accident:
the score is the desk's opinion, the base rate is a count of what lookalikes
did, and folding one into the other hides the case where they disagree, which
is the only case either of them gets corrected by. Section for section:

| On Precedent | Mirrors on Morning | State |
| --- | --- | --- |
| The names on today's list | The gap spine | BUILT |
| When a winner stopped going up | Record's timing split | BUILT |
| What these counts are not | nothing; it is new | BUILT |
| What the desk missed | What else moved | BUILT 2026-09-05, from research_daily |
| What each floor turned down | How the list was cut | BUILT 2026-09-05 |
| Whether thin evidence has cost anything | What the evidence is worth | BUILT 2026-09-05, three of the roll's nine lines, the other six named |
| How these events have resolved before | Coming up | BUILT 2026-09-05, from research_daily |
| What kind of morning this is | What kind of morning this is | BUILT 2026-09-05, narrower than the Morning section and says so |
| What noon has graded before | What noon will grade | BUILT 2026-09-05, scan_midday.grade folded over the cached tape |

ALL NINE ARE BUILT. Three shipped 2026-09-04 and six on 2026-09-05, and the
"needs" column this table carried until then was wrong on five rows and half
wrong on the sixth. Not one of the six needed a new network call. The rejects
were already being graded and their verdict discarded; the evidence roll's
reconstructible lines were already columns replay_session writes; the
historical calendar was already in every session cache with timing, estimate
and actual on it; the session level shape was a GROUP BY over bands already
frozen onto the row; and the noon target needed a fold of minutes the engine
already fetches, handed to the shipped grade function. What the desk missed was
the only genuinely blocked one, and only because "graded" was the wrong verb: a
name nobody subscribed has no premarket tape, so no entry and no stop, and no
paper rule can be run on it. Its outcome is the daily bar, which is why
research_daily exists as a table of its own.

WHY IT IS NOT THE REPLAY SCREEN. A retrospective page is opened once and then
never again, because the event it describes is over. The owner said so and it
is right. The replay is the ENGINE; what reaches a reader daily is this screen,
which uses the engine's output before the open. The engine's own system level
findings (the score's ordering, the component lift, the threshold sweeps) are a
generated document under doc/research/ and NOT a tab, for the same reason.

THE MATCHER, which is where this package can go wrong. "Looked like this" is
the whole design. Too loose and the count is meaningless, too tight and it is
noise. The rule is a CRITERIA table of bands, applied as a conjunction, with a
widening ladder that drops named conditions in a fixed order when the count
falls under the floor. Three things are compulsory:

1. Every printed count carries BOTH rows and distinct sessions. Twelve names
   from one morning share that morning's market and are one observation.
2. A group under `[Precedent] min_sessions` prints "too few to say anything"
   rather than a number. A widened group is labelled widened, every time,
   with the dropped condition named.
3. The bands are fixed in the pre-registration BEFORE any outcome is read. A
   matcher tuned after the results are visible is a matcher tuned to flatter
   the desk, and this is the failure mode the whole package exists to avoid.

Must not: change the Morning screen, change the ranking, write to `picks`
outcome columns or `paper_trades`, spend EODHD quota at render time, or read
any row whose `source` is not `reconstructed` when computing a base rate. The
live record is 43 picks over four sessions and must never be pooled into a
figure that claims to describe a year.

Acceptance: with `research_outcomes` empty the screen renders and says the
replay has not been run, naming the command; a claim fails if `desk/precedent`
reads picks without a source fence; a claim fails if any base rate is printed
over fewer sessions than `[Precedent] min_sessions`; a claim fails if the
Morning screen's section list changed; the pre-registration file carries a date
earlier than the first `research_outcomes` row. Effort L. Risk: the matcher,
held by the pre-registration. Delegable: no, not the matcher.

---

## Tier 6: what the 2026-09-02 evening review left open

Added 2026-09-02 evening, after a second whole tree review in six areas
(selection, collector and watchdog, scan, analyst and midday, nightly and
core, research and documentation). Everything that review found and could
fix the same evening is fixed and recorded in CHANGELOG forty fifth to
fiftieth. What follows is what it found and deliberately did NOT change,
because each is a threshold, a design, or a measurement the project's rules
say must be measured before it moves. Numbers are from runs/*/pool_recall.json
and runs/*/packet.json over the seven sessions 2026-08-24 to 2026-09-01
unless a line says otherwise.

The one page version, for the owner's standing complaint that the report
misses big gaps up of good companies. Of 46 universe names that opened up 8
percent or more in those seven sessions: 8 were subscribed (7 of them tier 1
earnings with news), 21 were in the pool and cut by the 42 slot cap, 17
were never in the pool. Of the 21 cut, at least 7 are after close reporters
that the earnings_after_close tier now lifts (OKTA, ESTC, GAP, VEEV, CRM,
CRWD, QFIN), 9 were tier 3 by the six hour freshness split (6.2), and the
rest sorted by gap propensity below the cut (6.1). Of the 17 never in the
pool, the four priors cannot see them at 07:15 and no premarket price
source exists for the universe on this plan: the delayed quote's ethPrice
was re-measured 2026-09-02 at 19:53 ET reading 16:28 for NVDA, three and a
half hours stale, so DECISIONS 2026-08-22 stands. The scan side is fixed:
the rank cut keeps gaps up first (forty fifth) and a stale print no longer
removes a name (forty seventh).

### 6.1 Measure the tier floors and the propensity ordering on size weighted recall

`min_slots_per_tier = 4` was measured on a +0.0017 mean recall margin for
gaps above 3 percent with no size weighting, before earnings_after_close
existed, and with tier 5 absent from the replay (the cache carries no
runners source, so the floor was measured across four tiers while shipped
mornings run five, 38 slots for tiers 1 to 4 rather than 42). Across the
seven live sessions the 28 floored slots in tiers 3, 4 and 5 subscribed 7,
10 and 9 names that gapped past 3 percent and none that gapped 8 or more;
the tier 2 cut region held 12 that did. Large caps sort to the bottom of
tier 2 by construction: OKTA propensity 0.056 (universe rank 679), VEEV
0.036 (1054).

Do: re-run src/research/backtest_pool.py with the after close tier, with
recall measured at 8 percent as well as 3, sweeping min_slots_per_tier over
0, 2 and 4, and with tier 2 ordered by news item count then propensity
(the cache holds `items` per news name). Four repairs to the replay first,
all found by the review: snapshot avg_dollar_volume_20d and market_cap per
name into inputs.json at fetch time and read them in load_metrics, because
the evaluate stage reads today's universe.json and the ordering note's
figures cannot be regenerated (re-run today gives 0.1171 against the
recorded 0.1164); cache adjusted_close and refuse corporate actions the way
pool_recall does; add a `--refresh-earnings` that replaces only
inputs["earnings"] so the after close re-measurement changes one input;
count the heavy and light split on earnings_before_open only. Then move
CRITERIA or leave it, with the table in the ordering note. Do not change
the floor or the key before this runs.

### 6.2 The six hour freshness split puts after close corporate news in tier 3

`news_fresh_hours = 6` makes "fresh" mean published after 01:15 ET, so the
16:00 to 20:00 window where earnings and guidance land is news_stale, tier
3, four floored slots against 235 to 556 names. On 2026-09-02 the 16:00
hour was the largest bucket, 82 names, all tier 3, 30 of them with an
earnings worded newest title. CRITERIA's own ordering note has tier 3
converting at 0.40 against tier 2's 0.37. At 03:55 the boundary is 21:55,
so the provisional pool carries the same skew and the 04:00 to 07:20 tape
is lost for exactly these names.

Do: in the replay cache, compare the shipped split against one tier for
everything since the prior close, and against a split by window position
rather than age. The after close tier already lifts the reporters; this is
about the non reporter names with real evening news (SOLS, SMMT, OOMA,
NTNX, WEN, HLF, BNTX in the seven sessions).

### 6.3 There is no discovery pass after 07:15

17 of 46 big gappers were never in the pool. Which prior would have caught
them was unknowable from the artifacts because pool_recall wrote
sources_that_would_have_caught_it as never computed; nothing retained the
four source lists past the run. Two cheap things and one decision.

Cheap one, DONE 2026-09-05: discover keeps each prior's name list in the
watchlist under pool_sources.<source>.found, names only and sorted, so the
payloads and the universe's closes stay out of it. About 11 KB a session.
pool_recall reads them and answers the question, and build() already refuses
to measure at all unless data/watchlist.json is provably the file the morning
read, so no new guard was needed. Worth doing on the numbers: across the 240
cached sessions, 3,649 of the 4,326 gappers past 8 percent at the open were
in at least one prior's list, so 84 in 100 get a real answer. The other 16
get an empty list, which now means all four looked and none found it, and
that sentence is only honest because the lists are present. The claim pins
both branches and the null one is unchanged for sessions written earlier.

Cheap two, still open: the provisional pool is not retained as
data/watchlist-provisional.json, so pool_recall cannot report
provisional_held or dropped_at_handover and still scores a name the 03:55
pass held and the 07:15 pass dropped as "missed".

Decision: an 08:15 pass. The collector rereads until its stop,
so a third pass lands mechanically; it costs 306 credits and a shorter
news window, and it would catch catalysts landing 07:15 to 08:15. Measure
what it would have caught from the news feed's timestamps before arming
it.

### 6.4 Tier 5 spends four slots on names already published

recent_runners reads picks WHERE source='live', which holds only the
twelve or fewer published names per day, so the four floored tier 5 slots
go to names the report already carried. ASST was subscribed as a runner
and left unpublished in five of seven sessions. The recent_runner_decay
weight is computed, recorded and orders nothing (CRITERIA now says so).
Measure tier 5's conversion in the replay (6.1 adds the source) and either
give it a real population (the subscribed set, or names that cleared the
floors) or drop its floor.

### 6.5 The day screen has no rotation alternative when the baseline is degenerate

Across ten archived sessions, 31 gap up candidates, 5 day eligible, 24
blocked on premarket_rvol alone, 4 of those never measured because the
baseline median sat under the 1,000 share floor: DG (+5.88, 27 billion)
on a 928 share median, DLTR 281, BBY 941 on 2026-08-27, DAKT (+6.97) on 18
shares on 2026-09-02. Those are not illiquid names; the vendor's intraday
premarket volume is near empty for them. CRITERIA [Baseline] already
records that the day screen "has NO rotation alternative". Build it: when
pm_rvol is null for a degenerate baseline and float rotation is measured,
let [Day setup] accept the rotation band the score already uses, as a
CRITERIA line, and surface day_failed unmeasured names as "not screened"
rather than as failures. The 20 measured and low cases were the window
mismatch and are addressed from 2026-09-03 except for handover names.

### 6.6 The 08:45 gap is not the open gap

Six of the eight subscribed 2026-09-01 names that gapped past 3 percent at
the open and were not published sat between -1.4 and -2.9 percent at
08:45 (ARM, ASST, NBIS, NIO, OPEN, MDT) and crossed the floor only at the
open. The rank floor and the screen floor are the same number applied to
different quantities. A lower ranking floor with the day screen floor kept
where it is would put them in the briefing; measure what the packets say
first (every packet carries below_floor and the snapshot).

### 6.7 Three scan failure modes left as designed, named

A candidate whose prior EOD row the vendor has not published makes the
vintage gate raise and the whole morning exits with no packet
(attach_daily_history takes completed[-1]); the blast radius is one symbol
to the whole report and the design intent is "no degrade path". A split
with today as the ex date mis-gaps by the ratio and clears every floor;
the nightly refuses it, the scan does not, and
prior_close_disagreement_pct only gaps. market_snapshot's collector path
takes completed[-1] as the prior close with no session check. Each is a
CRITERIA decision about how loud a single bad row should be.

### 6.8 The watchdog is blind from 04:00 to 07:25

No monitor pass exists between the collector's start and 07:25. The
collector now waits for today's file until the handover, which covers the
file race, and not a socket that never authenticates or a run that exits
on refusals at 04:10. Owner decision, because it registers tasks: monitor
firings at 04:05 and hourly to 07:25, with the collector's single rerun
budget in mind (an early restart on a stale file burns it). The -Probe arm
at 06:30 in tasks/register_tasks.ps1 now falls inside the collector window
and probe_socket_cap refuses inside it; re-time it or retire it.

### 6.9 Smaller items with a measured cost, unfixed

- backup_evidence never holds a power cut morning: an open collector row
  is refused and after catchup_sessions the session leaves the window
  uncopied unless someone runs --date.
- In slots mode a containment failure (a peer's ticker in a headline
  slot) still exits 2 and costs the chain, where the offending text is one
  located slot the guard could blank; and subprocess timeouts on Windows
  can block on a grandchild's inherited pipe, so the 1,007 second bound
  rests on the CLI not spawning one.
- universe.py: min_sessions equals lookback_sessions, so one missing bar
  excludes a name for the week; gap_stats counts a split session as a gap
  where pool_recall refuses it.
- CRITERIA prose lines that the parser reads as keys inside [Analyst].
  DONE 2026-09-05. One was still live, a backticked key from the slots note
  demonstrating its own shape at column zero, and the note is reflowed so it
  no longer is one. The unread report stays section wide, because a section
  read by a variable key cannot be resolved to the keys it touches and
  listing all of them would be noise. What closed the hole instead is
  question 1, which now asks TWO things: the key must be an identifier, true
  of all 349 real pairs and false of that one, and the value must not run on
  into a sentence, true of no real value and true of the [Analyst] mode that
  cost the 2026-09-02 morning. That shape was previously invisible to every
  question: spelled right for 1, defined once for 3, in a read section for 4.
- The after close measurement (26 gappers, 23 in pool, 2 subscribed) is
  quoted in CHANGELOG thirty eighth and DECISIONS seventh and is not on
  disk; write the crossing as data/research/after_close_reporters-<date>.json
  the next time it is run.

---

## Suggested order and what it buys

| Order | Packages | Buys |
| --- | --- | --- |
| First | 0.6 | A name that reported after yesterday's close is a tier 1 candidate this morning, not a headline ranked by history; GTLB's miss cannot recur by that route |
| First | 0.7, 0.8, 0.9 | Slots mode actually runs, at two thirds the tokens and time; lists render as lists; the page is laid out for reading and the emailed copy survives a mail client |
| Day 1 | 0.1, 0.2, 0.3, 0.4, 0.5 | The next empty morning renders its watchlist; the glossary says the right thing; the fallback is complete; no tracking pixel; the clock arithmetic is honest |
| Week 1 | 1.1, 1.2, 1.3, 1.4, 2.3, 2.4 steps 1 and 2, 2.6, 3.2, 3.3 | A report that leads with the decision, half the repetition, a guard that stops eating mornings, a third off the input tokens, an email with a text part |
| Week 2 | 2.1 or 2.2, 2.5, 1.5, 3.1, 3.4, 3.5 | Output tokens down by two thirds, CLI time under two minutes, the guards scanning a few hundred words, one page shell, midday reachable |
| Week 3 | 4.1 to 4.7, 4.9, 5.1, 5.2, 5.3 | Nine floats become one, six writers become one, CRITERIA checked at test time, the suite cannot hide a raising claim, the record page answers the questions a trader asks |
| Week 4 | 5.4, 5.5 | The 60 session replay and the fifth prior test, both free, both pre-registered, both ending in a table the owner can decide on |
| Week 4 | 5.7 | The Precedent screen: what happened the last time a name looked like this, printed before the open rather than after the event |
| Owner | 5.6 | The four decisions the measurements are waiting on |
| Later | 3.6, 4.8, 4.10 | Sparklines, the scan split, the single entrypoint |

## What was read and found sound

Named so the next reader does not spend a pass on them. The containment
check's coverage recording and its structural failure on a missing table. The
store's transaction guard, session context manager and identifier validation.
The vintage gate. The quota preflight's fail open on an unknown meter. The
midday pass's refusal to read `previousClosePrice`. The three fences on the
Alpaca replay. discover.py's two broad excepts, both deliberate and both
carrying the consequence. The prose stopword list's recorded fail open. The
guard on gap_reasons text, which DECISIONS thirteenth found missing and commit
8fae33d closed the same day.
