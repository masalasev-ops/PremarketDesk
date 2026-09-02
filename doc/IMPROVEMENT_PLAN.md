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
the gap (Spearman 0.627 between absolute gap and premarket range). The gap
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

Most of this tier ends in a written proposal for the owner, because the
project's own rule is that a threshold moves only on a pre-registered
measurement and the score is under a pre-registered evaluation. The work a
model can do is to build the instruments and write the amendments.

### 5.1 Amend SCORE_INVERSION.md before the judging point

File: doc/research/SCORE_INVERSION.md register block.

Add, dated: the premarket range confound (Spearman 0.627 between absolute gap
and premarket range as a share of entry; range against best excursion -0.343);
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

1. Move [Collector] start_time toward 04:00. The socket was measured free on
   2026-09-01 (21,306 messages, zero counter movement). Consequences to name:
   the float rotation edges and the capture rate were fitted on 07:20
   numerators (CRITERIA [Score premarket float rotation]); the RVOL floor of
   1.5 then means something different; the re-fit study exists offline.
   Acceptance if adopted: median `pm_rvol_true / pm_rvol` falls from about
   4.6 toward about 1.4 over ten sessions, and day eligible counts are
   published before and after.
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
5. `data/UNVERIFIED`. The gate is blocked on a decision, not a measurement:
   the 68 row RVOL study is done. Either decision 1 above lands and one real
   morning is reviewed, or the owner accepts the lower bound and reviews a
   morning as is.

---

## Suggested order and what it buys

| Order | Packages | Buys |
| --- | --- | --- |
| Day 1 | 0.1, 0.2, 0.3, 0.4, 0.5 | The next empty morning renders its watchlist; the glossary says the right thing; the fallback is complete; no tracking pixel; the clock arithmetic is honest |
| Week 1 | 1.1, 1.2, 1.3, 1.4, 2.3, 2.4 steps 1 and 2, 2.6, 3.2, 3.3 | A report that leads with the decision, half the repetition, a guard that stops eating mornings, a third off the input tokens, an email with a text part |
| Week 2 | 2.1 or 2.2, 2.5, 1.5, 3.1, 3.4, 3.5 | Output tokens down by two thirds, CLI time under two minutes, the guards scanning a few hundred words, one page shell, midday reachable |
| Week 3 | 4.1 to 4.7, 4.9, 5.1, 5.2, 5.3 | Nine floats become one, six writers become one, CRITERIA checked at test time, the suite cannot hide a raising claim, the record page answers the questions a trader asks |
| Week 4 | 5.4, 5.5 | The 60 session replay and the fifth prior test, both free, both pre-registered, both ending in a table the owner can decide on |
| Owner | 5.6 | The five decisions the measurements are waiting on |
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
