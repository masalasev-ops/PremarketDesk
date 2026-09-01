# Changelog

Dated entries, newest first. Appended to, never rewritten. What belongs here is
what changed and why it had to; the reasoning behind a choice that could have
gone another way belongs in DECISIONS.md, and every threshold belongs in
CRITERIA.md.

Errors of fact are corrected in place and carry a `[corrected YYYY-MM-DD: was
X]` marker; superseded decisions keep their original text and are answered by
a later entry. A number that was wrong when it was written is not history, it
is a mistake, and leaving it standing means the next reader measures against
it. A number that was right when it was written and has since been overtaken
is history, and rewriting it destroys the reasoning.

This file starts at 2026-08-14. Everything before it is in doc/BUILD_PLAN.md
and in the git history.

## 2026-09-01, fourteenth: the midday report is typeset, and stops shouting

Raised by the owner on reading the 12:00 edition: "so badly formatted. Small
and caps all wrongly done". Both halves were real, and neither was cosmetic in
the sense of being arbitrary.

### The type size was never decided

The HTML shell set no font-size on body at all. Every size under it was an em
multiple, so the whole report rendered against whatever default the reader's
browser happened to apply, and the eight column carry through table, at 0.92em
of that unknown, was the first thing to suffer. It sat in a 760px column, which
eight columns of grades and their prose do not fit.

Now an explicit 17px base, a 940px measure, tables at 0.97em with real padding,
a zebra on the body rows and the ticker column held on one line. Each table is
wrapped in a scrolling box, so a narrow screen scrolls the table rather than
the whole page sideways.

### Capitals doing two different jobs, and one of them badly

Two separate defects sat under "caps wrong".

Packet notes are written to sit wherever a reader needs them, so many begin
with a small letter, and the renderer was dropping them straight into sentence
position. "selection is on price across every universe name" opened its own
paragraph that way, and so did "every move divides by". _sentence now
capitalises a note that OPENS a sentence, and only where the first word is a
plain lowercase word. us-quote-delayed's and ethPrice keep the spelling the
vendor and the code give them, because "Us-quote-delayed" misnames a field a
reader has to go and look up, which is a worse error than a small letter.

Separately, this project argues in capitals. That is right in a comment and it
is shouting in a report, and NOT, PRICE and HERE reached the reader that way.
_prose lowercases a CLOSED LIST of emphasis words, matching maximal runs of
capitals and looking each run up, so CRITERIA, EODHD, DECISIONS, SKIP, RVOL and
every ticker are untouched and NOTE stays NOTE. Fixed at the source in
scan_midday too, but the list stays: every packet already on disk carries the
old wording, and a re-render of an archived session has to read right as well.

THE LINE IS BETWEEN PROSE AND AN ALARM, and the suite drew it. A close call and
an unjudged bucket appear in a perfectly healthy report, so capitals there
shout at a reader for whom nothing is wrong; both are sentence case now. THE
COUNTS ABOVE DO NOT ADD UP and PARTIAL fire only when the report cannot be
trusted as it stands. test_midday pins the first in both directions and was
right to, the de-shouting of it turned the suite red, and both keep their
capitals. The rule is now written beside the list that implements the other
half of it.

Today's 12:00 edition was re-rendered from its own packet. The packet was not
touched and no vendor call was made: it is the evidence, and the report is
derived from it.

Suite green, 1,741 paths, no drift.

## 2026-09-01, thirteenth: two readers that could not fail safely

A review pass over the tree, taken against the 12:00 job's dependency closure
first because that job was about to fire. Two defects, both the shape this
project keeps finding: a reader that answers confidently about a file it did
not manage to read.

### 1. The midday pass could die after paying for itself

morning_context reads three files. subscriptions.json goes through
collect_premarket.read_subscriptions, and the comment above that call already
says why: a bare json.loads there "would take the whole 12:00 pass down with a
traceback AFTER the universe sweep and the bulk day have been paid for,
roughly 2,900 shared credits".

packet.json and watchlist.json are read in the same function, after the same
spend, and used a bare json.loads. The argument was written once and applied
to one of the three readers it covers.

Reproduced rather than argued: today's real packet truncated at half its
length raises JSONDecodeError straight out of build_packet. scan_midday.main
catches QuotaRefusal, PriorSessionUnknown and PriorClosesUnusable and nothing
else, so it reaches the .bat as a traceback with the sweep already bought.
This session's preflight priced that sweep at 2,892 credits.

Both now go through _read_json_dict, the same shape as read_subscriptions. An
unreadable file becomes a written reason and never an empty answer, on the
rule this project has been burned by before: an empty named_this_morning would
report every mover as new, and an empty pool would caption every one of them
not_pooled. Reading intact files is unchanged, checked against today's
runs/2026-09-01/packet.json, which still reads 28 named, 499 pooled and 50
subscribed.

### 2. A restarted morning's capture was never backed up

collector_finished returned False on the FIRST unended collector row it saw
and did not look at the rest of the day. A morning the watchdog restarts
leaves the killed run's row open forever and records the completed run after
it, so that day was refused on every nightly until it fell out of the ten
session catch up window, after which the capture this module's own docstring
calls irreplaceable had never been copied at all.

Not hypothetical in shape. 2026-08-18 and 2026-08-19 are both restarted
mornings in data/job-status.jsonl, and they survive only because their failed
first runs recorded an end. A process killed by the power cut this module
keeps citing records none, and that is the row that was fatal.

An open row is now read IN ORDER against the completed runs beside it. Only a
run that started after the last completed one can still be appending to the
capture, so only that one refuses, which keeps the 2026-08-24 defect closed. A
run that started before it is a corpse and says nothing about a session that
went on to finish.

The claim gains both orders and went from four unfinished shapes to five: a
restarted morning whose second run finished is accepted, and a run still open
after a completed one is still refused. The four original shapes are unchanged.

### What was checked and found sound

Named here so they are not re-reported. The November fold in ettime, which
_USEasternFallback.fromutc already decides on the UTC instant rather than on a
standard clock. The rate division in weekly_page, guarded by its own "nothing
to divide is not a group that is nearly there" branch. float(row.get("gap_pct")
or 0) in the collector, removed at d224837, which now prints tier and rank. And
the SQL identifier guards in store.

The standing review's "the watchdog does not watch the midday job" was already
closed before this pass: monitor_jobs.JOBS carries five entries and midday is
keyed on the render marker.

Not touched, because neither is a code defect. The RVOL window mismatch and the
score inversion are threshold and pre-registration questions, and thresholds
live in CRITERIA.

Suite green on both fixes, 1,720 paths, no drift.

## 2026-09-01, twelfth: the child is tested too, and an unfinished session is not backed up

Both of these were raised as things to VERIFY before acting. Both hold, and the
verification moved two details.

### 1. The claim tested the parent and trusted the child

Confirmed by reading it. `claim_the_socket_probe_cannot_write_the_session_capture`
inspects the launched command for `--premarket-dir` and stops there. It never
calls `bar_path`, `stats_path` or `subscriptions_path`, so nothing asserted that
`collect_premarket` honours the flag it is handed.

Confirmed load bearing: the comment above the rebind states, as the reason it is
safe, that all three helpers read `config.PREMARKET_DIR` at CALL time. A
property named as the reason something is safe, with nothing enforcing it.

**The precedent is bigger than cited.** `conftest._DERIVED` carries SEVEN module
constants that captured a root at import and cannot be redirected without being
named one at a time: two backtest directories and a third for sessions, the job
status trail, the market calendar cache, the monitor's rerun state and the
UNVERIFIED marker. Not six.

`claim_the_collector_writes_where_premarket_dir_points` calls `main` with the
flag against a temporary directory. It returns 1 on the missing watchlist, which
is the first gate past the rebind and long before any socket, so the real parser
and the real rebind are exercised rather than a stand in. Then each of the three
helpers is checked SEPARATELY, because a set that fails as one says a redirect
broke and naming the helper says which line to open.

Verified by breaking it rather than by reasoning: `stats_path` rewritten to
capture `PREMARKET_DIR` at import turns the suite red with
"stats_path, the run stats sidecar returned ... which is not under the
--premarket-dir it was given".

### 2. The nightly backed up a session still being written

Confirmed in the .bat, not from the story. `tasks/job_nightly.bat` runs
`backup_evidence` at **line 56**, and the catchup gate is at **line 71** and only
skips pool recall and the archive. So the 07:00 firing backs up, and on
2026-08-24 the machine was late and that firing landed at 07:55 with five bars
on disk.

Confirmed in the code: the day list came from
`PREMARKET_DIR.glob("*.jsonl")`, which is file PRESENCE. A capture file exists
from the socket's first written minute, so it says a run started and nothing
about whether it ended.

`collector_finished(day)` now asks `job_status` instead, and three answers are
all False with distinct reasons: no row, a row that is not a scheduled collector
run, and a row that never ended. An instrument does not count. Today's socket
cost probe recorded step `collector` under job `manual` and wrote 932 minutes at
10:00 beside the morning's 3,289 at 07:20; a probe finishing is not a session
finishing.

**A detail the verification turned up.** 2026-08-13 and 2026-08-14 have NO
collector rows at all, because they predate job_status. Both are outside the ten
session window and both are already held, so the gate costs nothing there, and
the SKIPPED line says which case it is: a day whose artifacts are all held reads
"nothing is at risk" rather than being reported as a loss.

Verified against a FRESH backup root, simulating 07:55 with today's completion
removed: 35 files copied for the nine finished sessions, today skipped with
"Nothing was copied: a partial copy held is worse than none, because write once
makes it permanent. Force it with --date 2026-09-01 once the session is over."

`--date` stays the explicit override and announces itself, because after an
arbitration somebody has to be able to re-take a copy on purpose, and that is a
different act from the nightly sweeping up whatever it finds.

The word list in the self counting claim was extended to 134, which its own
failure message asks for rather than deleting the check.

Suite green, 134 claims, 1,699 paths, no drift.

## 2026-09-01, eleventh: monitor-midday registered by hand, and the blind spot it came from closed

### 1. The task, created singly

`register_tasks.ps1` was NOT re-run. It rewrites every trigger, and today is a
trading day with a 12:00 job already scheduled. `monitor-midday` was created on
its own, built from the same calls the `$jobs` loop makes rather than retyped:

    New-ScheduledTaskAction -Execute job_monitor.bat -WorkingDirectory <root>
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek <weekdays> -At 12:25
    repetition borrowed from a -Once trigger, 30 minutes for 1 hour
    New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit 4h

**Verified by querying it back, not by trusting the exit code.** Against the
live `monitor`, which runs the same .bat from the same `$jobs` loop, twelve
fields were compared and ten are identical: Execute, Arguments, WorkingDirectory,
DaysOfWeek 62, repeat interval PT30M, StartWhenAvailable, WakeToRun,
DisallowStartIfOnBatteries, StopIfGoingOnBatteries and ExecutionTimeLimit PT4H.
The two that differ are the two `$jobs` says differ: StartBoundary at 12:25
against 07:25, and repeat duration PT1H against PT2H, from `Start = "12:25"` and
`RepeatHours = 1`.

**One correction to the instruction.** `-WakeToRun` was asked for and is NOT
set, because the `$jobs` loop does not set it. That flag appears only in the one
off probe blocks. Matching the array means WakeToRun false, which is what every
other recurring task carries, and setting it here would have created the
divergence a later full re-registration is meant not to find.

**Nothing else moved.** Every trigger was snapshotted before and after: eleven
tasks now, exactly one line added, none removed, no other StartBoundary changed.

`register_tasks.ps1` should still be run in full at the next window after the
close, or at a weekend. This entry is a repair, not a substitute for it.

### 2. The class it belongs to, closed

Every guard in this project reads the tree. **Task Scheduler is state outside
the tree**, and this was the second gap to live there. The first was
`-WakeToRun`, set in the script and absent from the live tasks. The second was
`monitor-midday`, in `$jobs` since 2026-08-31 and never registered, so the three
pass midday window existed in `monitor_jobs.py`, in CRITERIA, in both
architecture pages and in a claim, and never fired once. Both were found by
hand, by someone happening to count.

`ops/monitor_jobs.reconcile_schedule` now reads the `$jobs` array out of the
script and queries `schtasks` for the folder, and reports four things: a name in
`$jobs` and not on the machine, a name on the machine and not in `$jobs`, a
start or repetition that disagrees, and a row whose repetition it could not
parse. It runs in `check_all`, which already fires several times a day and
already reports problems.

**It degrades honestly.** If either side cannot be read the result is
`checked=False` with the reason and the pass prints NOT CHECKED, which counts as
a problem. It never reports agreement it did not establish, and the failure
result carries no comparison keys at all, so there is nothing an empty answer
could be mistaken for. That was checked by making the query fail rather than by
reading the code.

**It is a monitor check and not a claim, and the code says so where it is
written.** No test can see the scheduler: the suite runs in a sandbox with none
in it. A claim that passes because it cannot see the machine is worse than no
claim.

Exercised in all four states before shipping: a dropped task reported MISSING, an
unknown task reported UNKNOWN, a bent start time reported DIFFERS with both
values, and a failed query reported NOT CHECKED. Against the real machine it
reports eleven matching eleven.

### 3. The probe cannot reach the session capture

`research/measure_socket_cost.py` still writes through `collect_premarket`, and
with the scheduled task gone a hand run was the only path left to the hazard,
which is exactly the path a header warning does not block.

It now refuses unless given `--out-dir`, and refuses again if that path is the
session capture or inside it. Both refusals name the directory they would not
write to and both happen before the counter is read, so a refusal costs nothing.
Refused rather than defaulted: a default output path is a decision the next
reader cannot see, and being made to name it is the point.

The redirect is real rather than advisory. `collect_premarket` gained
`--premarket-dir`, which rebinds `config.PREMARKET_DIR` after parse_args, and
that moves the capture, the stats sidecar and the subscription list together
because all three path helpers read the attribute at call time. Threading a
parameter through each would have been three chances to miss one.

The script is NOT deleted: `measure_bulk_cost` imports `read_counter` from it,
verified importing cleanly after the change, and README names it as what
reproduces the shipped measurement. The header warning stays and now explains
the refusal rather than standing in for one.

`claim_the_socket_probe_cannot_write_the_session_capture` drives all three
refusals and then asserts the accepted run actually points the collector at the
directory it was given, because a guard that refuses loudly while the child
writes where it always did would read as fixed and not be.

Suite green, 132 claims, 1,675 paths, no drift.

## 2026-09-01, tenth: the socket cost probe is deleted, and the midday watchdog was never registered

**The probe is gone, on its own instruction.** `tasks/job_probe_socket_cost.bat`
opened with "Delete the task and this file once the number is written down."
The number is written down, in DECISIONS 2026-09-01 eighth: 21,306 messages on
a live regular hours tape moved the vendor counter by zero. The scheduled task
is unregistered and the .bat is deleted. Ten job .bat files now, from eleven,
and the two documents that state that count were corrected with it.

Its trigger was one time and had already fired, so nothing was going to run
again on a schedule. What is removed is the hand run route and the standing
invitation of a .bat sitting in tasks/ looking armable.

**The module stays**, and that is deliberate rather than an oversight.
`research/measure_bulk_cost.py` imports `read_counter` from it, README names it
as what reproduces the measurement, and deleting it would take a working
instrument down with a spent one. It gains a warning instead, saying in its own
header what it does to the session capture, because after today only a hand run
can reach that hazard and the person doing it should meet the warning first.

**register_tasks.ps1 is untouched**, also deliberately. Its `-SocketCost` block
already prints "MISSING ... which is what was meant to happen once the number
was written down" when the .bat is absent, and its `-Unregister` tail still
names the task. Both behaviours are correct after this deletion, and editing
either would erase the script's own account of what happened.

### Found while checking the counts: the midday watchdog has no trigger

The arc page says eight .bat files register as **eleven** scheduled tasks. The
machine has **ten**. `register_tasks.ps1`'s `$jobs` array names eleven. The one
that is missing is `monitor-midday`.

    registered   collector, discover, meter-sampler, midday, monitor,
                 monitor-night, morning-chain, nightly, nightly-catchup,
                 universe
    in $jobs     the same ten, plus monitor-midday at 12:25 repeating every
                 30 minutes for an hour

So the three pass midday window, 12:25, 12:55 and 13:25, exists in
`ops/monitor_jobs.py`, is argued for in CRITERIA `[Monitor]`, is described in
both architecture pages, and is driven by
`claim_the_midday_watchdog_tells_a_hung_job_from_a_live_one`. **It has never
fired**, because the line that registers it was added to the script on
2026-08-31 and the script has not been run since. Every registered task still
carries a StartBoundary of 2026-08-31.

The consequence is the exact gap that window was built to close: the 12:00
midday job runs, and if it hangs or dies nothing looks at it until
`monitor-night` at 22:45. The changelog entry that added the window said a
midday failure was first named by the NEXT morning's watchdog, and that is
still true today.

Nothing is registered by this entry. Re-running the script would fix it in one
command and it also rewrites every other trigger, which is a live schedule
change on a trading day and belongs to an owner rather than to a cleanup.

**A claim would not have caught this and still would not.**
`claim_the_watchdog_reads_every_job_that_writes_a_log` compares the JOBS list
against the .bat files, and `claim_a_hold_needs_a_pass_that_can_act` walks the
pass grid, both from the tree. Neither can see Task Scheduler, and the gap is
entirely between the script and the machine. That is a real blind spot in the
suite and naming it is the honest half of finding it.

## 2026-09-01, ninth: three files, one incident, two verdicts each way

**Answers the entry below, which said the 2026-09-01 disagreement was not
arbitrated. It was, on the owner's word, once the probe had stopped writing and
the separation had been checked rather than assumed.**

One incident left three files disagreeing with their backups and they did not
all resolve the same way. That is the whole reason the door takes a verdict and
sources instead of a preference for the newer file or the older one.

| file | verdict | why |
| --- | --- | --- |
| `2026-09-01/premarket` | **backup** | the probe interleaved 932 open market bars into the session's evidence |
| `2026-09-01/subscriptions` | **backup** | the probe rewrote it in place, dating the morning's subscription at 10:00:04 |
| `2026-09-01/premarket-stats` | **working** | the probe APPENDED. The morning's line is byte identical to the backup and the second line is the only record of the probe's run |

**The capture.** `data/job-status.jsonl` holds two collector runs today: the
scheduled one 07:20:02 to 09:25:00 producing 3,289 minutes, and one under job
`manual` 10:00:02 to 10:20:05 producing **932** minutes. The working copy was
the backup byte for byte plus exactly **932** bars. An independent record and a
file difference agreeing on the same number is what made this decidable. By
`market_status`, written per bar, the backup held 3,338 bars every one of them
extended-hours and the 932 extra were every one of them **open**, earliest
09:53, after the bell. Restored: 3,338 bars, hours 07, 08 and 09 only, no open
bar left.

**The subscriptions.** Both files carried the identical fifty symbols, the same
requested count and the same cap. Only `subscribed_at` differed: 07:20:02 in
the backup against 10:00:04 in the working copy. CRITERIA calls this sidecar
the only evidence of what the socket was listening to, and the working copy had
come to date the morning's subscription at an hour the morning was over.
Restored to 07:20:02, and no symbol information was in dispute at any point.

**The stats sidecar went the other way, and the difference is the file's
shape.** Its contract is one line per collector run. Two runs happened, so two
lines is the complete record and one is the incomplete one. The morning's line
is byte identical to the backup, so nothing was overwritten, and the second
line carries the 21,306 messages and 932 minutes that ARE the socket cost
measurement reported today. Keeping the backup there would have destroyed the
record of a measurement rather than protected one.

**Zero disagreements outstanding**, 39 files held, and the suite is green again
at 1,650 paths with no drift. The two suites that were red were red because the
vintage guard refused a packet built from the contaminated capture, which was
the guard working, and they went green when the capture stopped being
contaminated rather than when anything was relaxed.

**The defect itself is untouched.** `research/measure_socket_cost.py` still
launches `collect_premarket`, which still writes to
`PREMARKET_DIR/<today>.jsonl`. Today's contamination is cleaned; the next run of
that probe would do it again. The probe is a one off whose .bat says to delete
it once the number is written down, and the number is now written down, so the
cheapest correct action is deleting the task rather than teaching the collector
a second output path. That is an owner's call and is not taken here.

## 2026-09-01, eighth: the freeze is amended rather than withdrawn

**Eighty commits have been judged against a rule that did not describe them.**
DECISIONS 2026-08-21 seventh said a change is in scope only if it makes a
published number wrong or makes the record readable. Since that entry the tree
has grown by 19,446 lines of Python and a second daily report pass was added,
and a recorded discipline nobody applies is worse than none, because it gets
cited against the wrong changes.

**Amended in place, not withdrawn**, because the route to more code genuinely
does still run through a published number being wrong, and most of the work has
gone that way. What was wrong when written is narrower and more useful than
"nobody follows it": the rule described the pipeline and nothing else, while
the two things that would inevitably grow, the claims that pin a fix and the
instruments that find one, match neither clause. A reader would have had to
break the rule to do the work correctly.

**The counts are in the entry**, measured from 5867e6e, whose subject is
"freeze the tree", rather than remembered.

  Python src/            42,949 -> 62,395   +19,446
    src/tests/           16,624 -> 24,259   +7,635
    src/research/         5,634 -> 10,427   +4,793
    src/night/            2,936 ->  6,211   +3,275
    src/morning/          7,269 ->  8,754   +1,485
    src/midday/               0 ->  1,365   +1,365
    core, ops, collect    7,174 ->  7,911     +737
  Tracked markdown       15,075 -> 22,063   +6,988
  doc/ all files         24,941 -> 27,140   +2,199
  claims                     74 ->    131      +57
  CRITERIA thresholds       260 ->    299      +39

**The headline is the smallest row.** The midday pass is 7 percent of the
growth. Two thirds is tests and research instruments. Blaming the second report
pass for the size of this tree would be reading the smallest number on the page,
and that is exactly what an unamended entry invited a reader to do.

**Two clauses added, describing what was already happening.** A claim that pins
a fix travels with that fix and is not separate work, because a fix nothing
holds in place comes back and this project has watched it: the artifact count
travelled through five documents after the module was corrected. And an
instrument that measures whether a published number is wrong is in scope,
which is the clause research/ needed while growing 4,793 lines without one.

**The midday pass is named as the one accepted exception, with its reason.** It
is out of scope under every clause and was built anyway, because the morning
cannot answer what the picks did and the outcome rows the whole freeze waits
for are what it grades. It buys the evidence the freeze exists to accumulate.
Named as an exception and explicitly not a precedent: a second needs its own
entry first.

**And what stays out**, so this reads as a rule and not a permission slip: a
refactor, a feature nobody asked for, a second vendor in the published path,
widening the socket cap, an instrument whose question is not whether a
published number is wrong, and a third report pass.

The heading carries an amendment marker, because a reader scanning headings
would otherwise take the two clause rule and never open the entry.

## 2026-09-01, seventh: the 2026-08-24 backup is the partial file, arbitrated

**Verdict: the working copies are intact and the backups captured a partial
file.** Neither of the two files could settle it, because each was the thing in
question. Three records that predate both and were written by different code
all describe the same session, and it is not the one the backup holds.

**Source one, the collector's own stats sidecar**, written at 09:25 by the
collector and not by either file: `minutes_written` 2003, `messages` 19576,
`trades_folded` 19576, `connections` 1, `reconnects` 0, `write_failures` 0.
One connection, one session, no losses.

**Source two, data/job-status.jsonl**, written by the job_status wrapper around
every step. The collector step ran **08:09:34 to 09:25:00**, status ok, exit 0,
producing 2003 minutes written. The rest of that day's timeline is the finding:
every job fired at **07:55** rather than at 07:00, 07:15 and 07:20. The machine
was late. `discover` ran 07:55:12 to 07:55:25 producing 42 names subscribed,
and warmed 50 tickers by 07:55:43.

**Source three, runs/2026-08-24/packet.json**, written by scan at 08:45:
`collector_snapshot.bars_total` 991 with `last_complete_bar_et` 08:43. A mid
session reading, consistent with 2,089 bars by 09:25 and consistent with
nothing near 5.

**What the two files hold.** The working capture has 2,089 bars across 53
symbols; the backup has 5 bars across 5. The working subscription list has 50
screened names; the backup has 11, and those 11 are exactly the context
proxies.

**What happened.** The nightly's own catch up ran at **07:55:13** and copied
the two files that existed at that moment: a proxies only capture and a proxies
only subscription list, left by a collector attempt that started before
discover had produced a watchlist. That is the same discover to collector gap
the outage note describes. The real collector then ran 08:09:34 to 09:25:00 and
resubscribed once, which the stats sidecar records as `resubscriptions` 1 on a
single connection. At 22:15 the nightly found both working copies had grown,
correctly refused to overwrite, and reported it.

**Which record is now believed wrong: the backup.** It is a partial file, not a
stale one, and it was partial the moment it was taken.

**This is NOT a second incident of the 2026-08-21 class.** Nothing overwrote a
working copy. That distinction is the whole reason the disagreement was
arbitrated rather than resolved by preference, and it is why the entry says
what happened rather than which file was chosen.

**The alarm fired the same night.** Line 115 of logs/nightly-2026-08-24.log,
22:15, naming both files and their byte counts. It has fired every night since
and nobody read it for eight days. The tripwire worked; the reading of it did
not.

### Write once had no door, and now has a narrow one

Write once protects a good backup from a corrupted working copy and protects a
corrupted backup from a good working copy exactly as firmly. A truncated
capture was therefore held permanently with no route in for the intact one.

`--arbitrate DAY/LABEL` is that route and it is not a relaxation. The default
path is unchanged: it still refuses and reports, and no scheduled step calls
this. The door opens only on `--verdict`, at least `[Backup] MIN_SOURCES` of
two `--source` citations, and a `--why`, and it refuses separately when the
artifact is not one this module backs up, when either copy is missing, and when
the two agree. Each refusal keeps its own message, because "refused" alone
sends a reader to the wrong file at the wrong hour.

The verdict is appended to `arbitrations.jsonl` in the BACKUP root, not under
data/, so it travels with the evidence it describes; a verdict kept beside the
working tree is lost by the same event that makes a working tree doubtful. It
carries both digests, both byte counts, the sources and the reason, and it is
written BEFORE the replacement. A recorded verdict with no replacement is a
readable state somebody can finish. A replacement with no record is what this
module exists to prevent.

`claim_a_held_backup_yields_only_to_a_recorded_verdict` drives five refusals,
asserts none of them writes the ledger, and asserts the recorded verdict exists
with its sources before the one replacement it permits.

### The same alarm on 2026-09-01, pointing the other way, and it is my defect

Tonight's disagreement on 2026-09-01 has the opposite verdict, and finding out
why turned up a defect in the socket cost probe that this entry has to name.

**The probe writes into the premarket session capture.**
`research/measure_socket_cost.py` launches `collect/collect_premarket.py` as a
subprocess, and that module writes to `PREMARKET_DIR/<today>.jsonl` with no
argument saying otherwise. It is the same file the 07:20 collector fills. The
probe was scheduled for 10:00 on the reasoning written into its own .bat, that
10:00 is past the 09:25 stop so the 50 symbol account wide cap is free and it
cannot starve the morning. That reasoning is correct about the cap and silent
about the file.

Measured at 10:06 while the probe was still running,
`data/premarket/2026-09-01.jsonl` held 3,670 bars: 978 in the 07 hour, 1,628 in
the 08, 742 in the 09, and **322 in the 10**. By `market_status`, 3,338
extended-hours and **332 open**. The collector's window is 07:20 to 09:25 and
every bar it writes is extended-hours. The 10 hour bars are the probe's, and
they are regular session trading written into the file CRITERIA calls not
reproducible at any price and that `_ARTIFACTS` backs up as one of four with no
route back.

**The vintage guard caught it.** Two suites went red on
`StaleDataError: 17 vintage violation(s) in the 2026-09-01 packet`, from a claim
that builds a packet against the live capture. That is the guard doing exactly
its job: the file no longer describes only today's premarket.

**Which inverts the backup question.** `backup_evidence` was run by hand at
09:44, after the collector stopped at 09:25 and before the probe started at
10:00, so the backup holds the CLEAN premarket only capture at 837,907 bytes
and the working copy is the contaminated one. On 2026-08-24 the working copy
was right; here it is the backup. That is the whole reason the door built above
takes a verdict and sources rather than a preference for one side.

**The two are perfectly separable, which the remedy depends on.** The backup
taken at 09:44 holds 3,338 bars and every one is extended-hours. The working
copy is that file byte for byte plus 932 more, and every one of those is
market_status open, earliest 09:53. Restoring the backup would discard the
probe run and not one premarket bar. That is checked rather than assumed,
because a remedy that loses real evidence to tidy up an instrument is worse
than the contamination.

**Not arbitrated and nothing changed.** The probe is still running, a verdict
taken against a moving file is worth nothing, and the remedy discards data,
which is a decision for an owner rather than a defect to be quietly repaired.
The probe's own measurement, which is a vendor counter delta and not these
bars, is unaffected. Recorded here so the next reader of that capture knows the
10 hour bars are an instrument's and not a session's.

## 2026-09-01, sixth: study payloads leave doc/, and the finding stays

**doc/ held 91,132 committed lines and 67,470 of them were nine machine written
JSON payloads.** A one line edit to CRITERIA arrived in the same review as
41,482 lines of per row study output. Reading diffs is the only review
mechanism this project has, and three quarters of the surface being generated
bulk is that mechanism not working.

**After: 26,953 lines across 21 files.** 64,179 lines left the repository.

**What moved and what did not.** Six regenerable payloads moved under
data/research, which config.STUDY_DIR names and .gitignore already covered.
Three stayed, each for a reason it states itself.

  float_rotation_study-2026-08-16-prefix.json    the script that produced it is
                                                 gone, replaced in 405c9ac
  float_rotation_study-2026-08-17-postfix.json   the input is gone: it read a
                                                 universe.json the Sunday job
                                                 overwrites weekly
  collector-capture.json                         no script produces it at all.
                                                 297 intraday calls against a
                                                 shared quota, and the
                                                 provenance a claim traces the
                                                 shipped capture rate to

The first two carry that argument in their own _provenance headers, written
when they were preserved on 2026-08-18. That commit ended "this is one
comparison kept for one entry, not a change of policy about study outputs",
which is the policy this entry finally applies to the other seven.

**Three findings written, so the payload is not the record.** CAPTURE_RATE.md,
BASELINE_FLOOR.md and FLOAT_ROTATION_FITS.md each carry the question, the
headline numbers, the date, the commit and the path. The counterfactual note
already existed and had its payload path repointed. Each is between 44 and 53
lines against payloads of 3,180 to 41,482.

**Two rules keep it this way**, in
claim_doc_carries_findings_and_not_payloads. A 1,500 line cap on any committed
file under doc/ not named in a list with its reason, and no committed JSON
under doc/ beyond the three above. Either rule alone has a hole: a cap admits a
1,400 line payload, and a no-JSON rule lets a prose file balloon. The cap was
chosen against the tree rather than picked, clearing the largest hand written
note at 1,148 and the arc pages near 1,350. Verified by planting a 2,000 line
JSON under doc/research, which raised both failures, rather than by trusting
that it would.

**The payloads are in the backup root**, under evidence/studies/ and
deliberately NOT in backup_evidence._ARTIFACTS. That tuple's argument is that
exactly four things have no route back, and a study payload has one: its
instrument can be re-run. They are held because re-running costs quota or reads
a universe and a set of packets that have since moved, which is prudence rather
than irreplaceability, and folding them into the four would make that sentence
mean nothing. Same write once discipline, its own weaker promise, stated.

**Two claims caught this work as it was written.** The new claim shelled out to
git without --no-optional-locks, which refreshes and rewrites .git/index and
then fails the whole tree photograph on a file the suite itself changed; there
is a claim watching for exactly that, and its message says it cost a day on
2026-08-14. And the self counting claim caught the module docstring still
saying one hundred and twenty nine.

**Raised while running the backup, and not from this work.** The 2026-08-24
premarket capture and its subscriptions sidecar DISAGREE with their backups:
520,756 bytes against 1,233, and 932 against 318. Neither file was changed,
which is the write once rule behaving correctly. A person has to say which side
is right. It is recorded here rather than fixed because only one of the two
readings is recoverable and choosing wrong destroys the evidence for telling
them apart.

## 2026-09-01, fifth: conviction is defined, and today's report was rebuilt

**Two defects in the same document, both raised by a reader looking at it.**

**The bands were published with the meaning stated nowhere.** green, yellow and
red appear in three tables, the day watchlist, the swing watchlist and technical
signals, and the report never said what any of them meant. A reader could see
that a row was red and had no way to learn that red is a score under 4 on a
scale that runs to 10, or that unscored is a fourth state and not a low one.

`analyst.annotate_score_bands` now places the definition under the first table
that carries the word. Three choices in it are load bearing.

It reads `criteria_summary.score_buckets`, the packet's own frozen copy of the
bands that scored THAT run, and not CRITERIA at render time. A threshold edited
next week would otherwise rewrite the meaning of a number already published.

It sits beside `annotate_job_health` and runs on BOTH paths, so the definition
cannot be present on the mornings the model behaved and missing on the mornings
it did not. REPORT_TEMPLATE.md now tells the model not to write its own, on that
module's existing argument: the model narrates, it does not define, and a
definition a model writes is one that can be forgotten on an off morning.

It says the ordering is open rather than settled. CRITERIA's score watch note
records that over the first fifty filled rows these bands ordered outcomes
BACKWARDS, yellow beating green at twenty five rows each. A legend implying
green means confidence would be the report overclaiming its own instrument.

A packet carrying no bands gets no legend rather than an invented one.

**And the table the fallback opened and never closed.** A markdown table runs
until a blank line. `fallback_report` wrote the notable movers rows and then,
with nothing between them, the sentence naming each instrument, so every
renderer parsed that paragraph as one more row: eighteen "TICKER is Company."
sentences collapsed into a single first column cell beside nine empty ones.
Latent since names began being carried on 2026-08-24 and first rendered today,
because only a rejected analyst reaches that function and this was the first
morning one was. The renderer that runs when something has already gone wrong
was the one emitting malformed markdown.

**Today's report was rebuilt rather than left standing.** Nothing was
re-fetched and packet.json was not touched: the same deterministic fallback was
rebuilt from it through the same two annotators, with the disclaimer reason
lifted out of the shipped document rather than reconstructed, so the two differ
only where the fixes land. Three added lines, no deletions, containment
re-examined at 45 claims with nothing invented and nothing missing. The
originals are preserved as runs/2026-09-01/report.0845.md and report.0845.html,
on the precedent of the 2026-08-20 amendment.

The 08:49 email carries the version that shipped. That cannot be recalled, and
tonight's build_archive will rebuild the site from the corrected file.

Two claims, both in test_containment. One states the placement rule
structurally, that any line after a table row is another row or is blank,
anywhere in the document, so a section added later cannot reintroduce the
shape. The other pins the legend: defined once, under the first table that uses
the words, carrying every band the packet scored against, passing the
quantifier guard it ships beside, and absent entirely when the packet has no
bands. The fixture gained the bands by the same criteria call scan makes, since
a fixture stating them on its own authority can disagree with the file the run
reads and then the claim passes while the page is wrong.

## 2026-09-01, fourth: the 2026-08-20 packet is back, and 08-21 never had one

**Answers the entry below, which said the restore was worth considering and
was not taken.** It was taken about an hour later, on the operator's word, and
that entry keeps its original text because it was true when written.

`night.backup_evidence --restore 2026-08-20` returned exactly one artifact.
The three premarket files were skipped as already matching, which is restore
refusing to overwrite a working copy that agrees with the backup, and no
rendered report came back because the backup never held one. So
runs/2026-08-20/ now holds packet.json and nothing else: twelve candidates,
all twelve carrying score_components, byte identical to the backup, and still
stamped 10:27 on 2026-08-20 because copy2 preserves the mtime. The restore
spent no quota. The meter read 1,148 before and after.

Both readers behave as their own docstrings promised. build_archive logs
"skipped 2026-08-20, no report.md" and moves on, so the published archive
still shows seven mornings and the deleted report stays deleted.
weekly_page._score_components_by_row now recovers all twelve rows, taking the
component table from 44 rows to 56.

**What the verification turned up, which is older than any of this.**
runs/2026-08-21/packet.json is a 762 byte stub. It carries one candidate, no
score components, and `stub` in its build commit field, while picks holds
twelve rows for that session. The backup holds the identical stub, so the
stub was already in place when the 22:15 backup ran that night.

[corrected 2026-09-01: this ended "and the real packet of 2026-08-21 was
never captured by anything", which reads as an open question and is not one.
CRITERIA [Backup] and backup_evidence.py both record the cause on their own
pages: on 2026-08-21 at 15:46 a sweep that invoked every claim directly wrote
fixture data over 29 files, including that morning's capture and its packet,
and both are gone permanently. The 762 bytes over a 125 KB packet that
CRITERIA names is this exact file. That incident is why backup_evidence.py
exists, so reporting its casualty as a mystery while reading its own
docstring is the reverse of the point.]

No number is published wrong by it and nothing is being changed. build_archive
already refuses to present it as a morning: _fixture_reason returns "its packet
was built by 'stub', which is not a commit" and the archive labels the day
rather than publishing its count of one. The weekly page contributes nothing
for those twelve rows, which is the same rule that governed 2026-08-20 while
its packet was gone, and a component nobody scored is still not a component
that scored zero. It is recorded here because a reader who finds one candidate
where picks says twelve deserves to know the answer is a stub and not a
morning.

## 2026-09-01, third: six run directories deleted by hand, and what that costs

**Not a code change. An operator action, recorded here because the tree no
longer matches what a dozen entries below describe.** On 2026-09-01 the run
directories for 2026-08-13, 08-14, 08-17, 08-18, 08-19 and 08-20 were deleted,
leaving 08-21 onward. The reason given was that those mornings published
reports written before the corrections of the following fortnight, and an
archive of reports now known to be wrong is its own kind of dishonesty. That
argument is accepted and the deletion stands.

There is precedent for recording rather than repairing. The entry of
2026-08-21 records runs/2026-08-15 and runs/2026-08-16 deleted as weekend
sweeps, and the citations written before it were left alone.

**The boundary is cleaner than it looks.** picks holds no row before
2026-08-20, so five of the six deleted sessions fed nothing downstream at all.
Only 2026-08-20 carries picks, twelve of them, and it is the session the
counterfactual watchlist study names as screened under an arithmetic retired
2026-08-21. The deletion therefore cuts almost exactly at the freeze.

**What survived.** night.backup_evidence holds all thirteen sessions at its
root outside the tree, and for each one it holds the four artifacts its
_ARTIFACTS tuple names: packet.json, the premarket capture, the stats sidecar
and the subscriptions sidecar. Nothing irreplaceable was lost. The capture in
particular, which CRITERIA calls not reproducible at any price, was never in
runs/ and was never touched.

**What did not.** The backup copies no rendered report, which is precisely what
made the deletion safe to want: report.md and report.html for those six days
are gone for good, as are pool_recall.json, verify_intraday.json,
analyst_usage.json and premarket_snapshot.jsonl, none of which _ARTIFACTS
names. Gone with them is the deliberately preserved pair
runs/2026-08-20/packet.0845.json and report.0845.md, which the entry of
2026-08-21 records as the before state of an amended packet. That entry now
cites two files that do not exist. It is left standing as history, because the
files did exist when it was written.

**Three consequences, none of them a failure.**

night.build_archive iterates runs/ and rebuilds site/ from what it finds, so
the published archive shortens from thirteen mornings to seven. That is the
intent of the deletion rather than a side effect of it.

night.weekly_page reads runs/*/packet.json for the points the morning actually
awarded, and its own docstring already answers this: a packet that is missing
contributes nothing rather than zeros, because a component nobody scored is not
a component that scored zero. The twelve picks of 2026-08-20 keep their row and
lose their component breakdown. Every median and trigger rate on that page is
computed from picks and paper_trades, which are in the database and untouched,
so no published number moves.

night.backup_evidence surveys the last ten sessions by [backup]
catchup_sessions, which still reaches 2026-08-19 and 2026-08-20, so from
tonight it reports two missing packets. That is the module telling the truth:
the working copies are gone and the backup still holds them. It resolves
itself once those dates fall out of the window, around mid September, and it
is worth naming because the same report carries the DISAGREES alarm, and noise
that gets ignored is how a real alarm gets missed.

**One restore is worth considering and is not taken here.** Restoring
2026-08-20 would return only packet.json, since the three premarket files
already match and restore refuses to overwrite a working copy that agrees with
the backup. It would give twelve live picks back the record of how they were
scored, without resurrecting a single rendered report. That is a judgment for
the operator and not a defect to be fixed.

## 2026-09-01, second: the score is unsigned wherever the score is printed

**Missed from the entry above and recorded here rather than folded into it.**
The change shipped in its own commit and the 2026-09-01 entry, written about the
three instruments, did not mention it. Every other commit of that night has an
entry.

[Score gap] weighs the ABSOLUTE gap, so a name down 20 percent and one up 20
percent earn the same points, while every outcome column is measured from
`entry_ref`, which is `pm_high` and therefore a long reference. The 2026-08-20
finding recorded this as closed and half of it was: `score_roll` has carried a
per row direction since, and REPORT_TEMPLATE has ordered the model to give it.

Three things were left. The caveat was a PARAPHRASE, because the template said
`direction_note` "says it in words" and that note cannot be quoted verbatim,
writing ABSOLUTE in capitals against prompt rule 8: six mornings produced six
different sentences. No candidate carried a direction at all, the sign being
discarded in `score_candidate` with nothing near the score recording it. And
`fallback_report` said nothing anywhere, while its Technical signals table
publishes a score for every candidate with no gap column.

`score_roll.text.direction` is the quotable form, on the `evidence_roll.text`
precedent, and every constraint on its wording is load bearing: it says rows and
never name or candidate so the quantifier guard cannot fire on it, it carries no
capitals so it can be reproduced, it carries its own denominator, and it counts a
never computed gap apart from up. `gap_direction` is one rule read by both the
roll and the candidate stamp, and it reads exactly 0.0 as up, which CRITERIA now
states because it is a decision about how a market fact is published.

The weekly page says its buckets mix directions. It does not render the split:
that belongs to the pre-registration, which commits to reporting it when either
point is judged, and a standing table invites eyeballing it at n=11.

No threshold moved and the screen is unchanged. Signing the component would
change what the score IS while it is under a pre-registered evaluation, which is
an owner decision, and CRITERIA says so where the value is set.

## 2026-09-01: the gate's question answered three ways, and an assumption the record contradicts

Three instruments and no threshold moved. The point of all three is that the
question `data/UNVERIFIED` has been gated on since 2026-08-18 is now blocked on a
DECISION rather than on a measurement, and a decision needs the number split in
the ways that change what it means.

**The counterfactual.** `research/counterfactual_watchlist.py` replays the
SHIPPED `evaluate_eligibility` and `score_candidate` over each archived packet
with `pm_rvol` swapped for `pm_rvol_true`, so it cannot drift from the screen it
is about. It refuses 2026-08-21 whole on `reread()`'s own run time guard, twelve
rows unresolvable rather than passed or failed, and it runs a BASELINE pass
first: two rows no longer replay their stored verdict, both on
`[Score premarket float rotation]`'s one point edge moving to 0.0002 on
2026-08-31, and both are excluded from the counts rather than being read as the
counterfactual lowering a score.

Eleven rows over four sessions would have gained the day watchlist. None would
have lost it. The swing screen cannot move at all, having no volume condition.

**And the three leads matter more than the eleven.**

The substitution swaps a WINDOW and not only a tape. Decomposed per row into
window, feed and baseline, an identity that closes on 37 of 37 rows carrying
all four terms, worst relative residual 2.5e-06.

THE FOUR MEDIANS DO NOT MULTIPLY, and they are not one group. Each carries its
own row and session count because each is taken over the rows that have that
term: window 2.5252 over 44 rows and 6 sessions, feed 1.3869 over 44 and 6,
baseline 1.0146 over 37 and 6, pooled total 5.0076 over 47 and 7. Over the 37
rows that carry all four they are 2.743, 1.367, 1.015 and 4.588.
doc/research/COUNTERFACTUAL_WATCHLIST.md states this and names the pooled total
as the figure not to quote; the sentence here originally gave the four under
one denominator, which invited exactly the multiplication that does not close.
The late start is most of it either way.
The baseline factor near 1.0 says the two vendors' denominators agree, so the gap
is not a denominator artefact. The window factor's minimum is exactly 1.0000, a
construction bound made visible. And "the true number is always bigger" is FALSE:
three rows measure lower than they published.

Seven of the eleven gains come from 2026-08-20, the one pre-correction session
that survives the run time guard. Split on `pm_volume_estimated`, the median
total ratio is 35.91 before the capture correction shipped and 4.59 after it, an
eight fold difference. Only four gained names over three sessions speak to the
screen that runs today.

No split of the outcomes can be published. `[Score watch]`'s minimums withhold
every one, including the `fill_plausible` split, and the pooled group is seven
parts one session to four parts three others.

**The capture rate, re-derived and left alone.**
`research/measure_capture_rate.py` guards the record and archives the raw rows;
`research/sweep_capture_rate.py` scores replacements off that archive with no
database read and no vendor call, so the question can be re-asked forever for
nothing. Both session guards fired once each: the 2026-08-21 stub, and
2026-08-24 for `started_late_minutes` 9.0, whose rows measure a start time
failure rather than the feed. The guarded set is 46 rows over six sessions.

The re-derived single number is 0.0968 by this file's own recipe, which the
sweep reproduces exactly against the 2026-08-21 payload at 0.117227. It is NOT
shipped, for three reasons that each stand alone. Every row was measured over a
window opening at 07:20 and that key is likely to move. `[Truth]`
baseline_sessions is twenty and the guarded set is six. And the move is in the
unsafe direction on a long only screen while buying nothing: 0.0968 admits the
same 21 names and the same 9 watchlist rows as 0.1172. The shipped key already
sits at quantile 0.61 of the record, so it is the conservative one.

**The residual no divisor closes.** The socket carries about a tenth of the
minutes it is awake for, and those minutes are about 41 percent of the premarket
tape. Composite socket share of the FULL window: 0.039. The capture rate corrects
the first factor. The 07:20 start is the second and no value of that key reaches
it.

**An assumption the record contradicts, in two documents.** `[Truth]` and
`night/true_volume.py` both said thin names capture least and are therefore
understated most, and that the correction reinstates the bias float rotation
exists to remove. Over the 46 guarded rows, terciles of the morning's own
`avg_volume_20d` give median capture shares of 0.178 thin, 0.087 mid and 0.084
thick, with Spearman rho of share against average volume at -0.405. Thin names
capture MORE than twice what the thickest band captures. The SPREAD was measured
and the DIRECTION was assumed. Six sessions is below `baseline_sessions`, so this
is a contradicted assumption rather than a finding to act on, and both documents
now say so where they said the opposite.

**The trigger rate per bucket, which the pre-registration promised.**
`weekly_page` renders it beside the medians, on the rows the rule was actually
applied to, with skipped and not-in-ledger counted apart and never folded in.
Green triggers on 6 of 18 evaluated rows, 33.3 percent; yellow on 10 of 18, 55.6
percent; red is withheld at 8 rows across 3 sessions. The page cross checks its
own three way split against `paper_ledger.record_so_far` on every rendering and
prints the agreement, because two copies of one split is how they come to
disagree.

The survivor set is now visible, which is the whole point: green's booked median
is withheld at n=6 while yellow's publishes at n=10, and green's smaller n is in
large part that it triggers at two thirds of yellow's rate.

**And building it found the phrase both confounds rest on is ambiguous.** "A
bucket whose trigger rate differs by more than half from another's" does not say
relative or absolute, and the two readings disagree on this record: relative puts
red past the line against both, absolute puts nothing past it. The same phrase
carries the gap direction confound. `SCORE_INVERSION.md` now pins it to the
RELATIVE reading, with the reasoning and today's measurement, dated before either
judging point, because after one, choosing between two readings is choosing a
result. It is deliberately not a CRITERIA key and the page does not render the
verdict: nothing computes off it, it is a rule for the person judging, and a page
that rendered it would conclude.

## 2026-08-31, seventh: the watchdog watches the midday job, and the suite counts itself

**The 12:00 job had been running watched by nothing.** `ops/monitor_jobs.JOBS`
held four entries and midday was not one of them. The weekday monitor stops at
`[Monitor] last_pass`, 09:25, and monitor-night is at 22:45, so a midday failure
was first named by `job_status.overdue` in the NEXT morning's packet, about
eighteen hours later, and was never rerun. CRITERIA [Job status steps] already
carried `midday` and `midday_render`, so the overdue path worked and only the
watchdog was blind.

**Three new clocks, and each is derived rather than chosen.** `midday_due` is
12:20, `[Midday] run_time` plus twenty: the only recorded run of the scan step
took 20.5 seconds and the render makes no vendor and no model call, so a healthy
pass is over by about 12:01. The upper bound is the SCHEDULE and not the job, a
due time later than the first pass that can judge it slips the verdict by a
whole `pass_interval_min`, so due had to land at or before 12:25. Thirty,
matching `nightly_due`, would have put it at 12:30 and cost the reader half an
hour for nothing.

`midday_first_pass` is 12:25, the first slot on the existing :25 and :55 grid at
or after due, so there is one fact about when the watchdog fires rather than
two. `midday_last_pass` is 13:25, giving three firings.

**More than one pass is arithmetic, not caution.** `job_log_stale_after_s` is
2,200, so a midday that hung after writing its log at 12:00 is still warm at
12:25 and cannot be told from a live job. One pass could only ever report
UNRESOLVED on that state. By 12:55 the log is 3,300 seconds cold and the verdict
is decidable. The third is margin for Task Scheduler's repetition endpoint,
which the morning trigger's five firings imply is inclusive and which nothing
here has verified.

**Midday is the one job the watchdog reports and never reruns.** Two reasons,
pointing the same way. The 12:00 sweep spends a measured 2,902 credits on a key
shared with another project. And `job_midday.bat` sets `PMD_JOB`, so a relaunch
resolves through `core/artifacts.py` as the owner of today and REPLACES the
12:00 packet with a later measurement. That is worst in the case most likely to
bring the watchdog here: a scan that wrote its packet and a render that failed,
where a rerun spends the whole sweep again to redo a step that makes no vendor
call and overwrites the good half on the way. CRITERIA [Midday] asks closed
questions about a session already open, so a named failure a human can act on
beats an automatic second attempt.

**What the new passes cost, said rather than left to be found.** They inherit
every other branch, including the discover rerun, which fires whenever discover
did not finish and no subscription list exists, at any hour by design. That is
not new: monitor-night at 22:45 already has it and the comment in
`monitor_jobs.py` says so. It is bounded by `max_reruns_per_job_per_day`, and in
practice the 07:25 pass has already spent that budget on any morning where
discover failed.

**The pass grid moved and one claim had to move with it.**
`_next_pass_minute(09:25)` is 12:25 now rather than 22:45, and
`claim_a_hold_needs_a_pass_that_can_act` walked the old grid. The BEHAVIOUR is
unchanged and that is the point: `hold_is_answerable` tests
`next_pass < collector_stop` and not merely that a next pass exists, so a pass
three hours after the collector window closed still cannot answer a hold. That
property is now asserted directly beside the walk, because a grid a claim only
reads is a grid it stops defending the moment the schedule changes again.

**Nothing compared the watchdog's list against the schedule, so now something
does.** `claim_the_watchdog_reads_every_job_that_writes_a_log` reads the .bat
files: a job that stamps `PMD_JOB` and writes a dated log is a job the watchdog
can read, and it must be in `JOBS` or in a named exemption. Two are exempt and
each carries its reason: the watchdog cannot watch itself, and the Sunday
universe rebuild is judged by AGE against `universe_rerun_after_days` rather
than by a dated log, which is what lets it survive a week of logs rolling over.
The next scheduled job is covered the day it is written.

**And the suite miscounted itself, in the sentence about not doing that.**
`test_regressions`'s docstring said it carried ninety six claims against one
hundred and twenty six defined and one hundred and twenty six called. The
sentence around the number argues that it "must be read off the file rather than
remembered, because it said forty four for a while after it held fifty seven and
a suite that miscounts itself is the first thing a reader stops trusting".

A sentence that argues for a discipline is not the discipline.
`claim_the_suite_can_count_itself` parses the file and compares the docstring
against the definitions and the call sites in `main()`. It caught itself on its
first run, since adding it moved the count. It also catches the two failures a
bare count cannot: a claim defined and never wired in, which passes silently
forever, and a claim called twice, which inflates the count without adding
coverage.

**One number nothing checks, stated because leaving it silent is how the last
one got here.** The monitor's trigger times live in `register_tasks.ps1` and in
CRITERIA [Monitor] and no test compares them. The job list is machine checked
now; the clocks are still held by hand.

## 2026-08-31, sixth: five falsy values that were reading as answers

One shape, five places, and the newest module carries four of them. A missing
answer leaks wherever the missing thing has a falsy value rather than a null,
which is what two thirds of the 2026-08-22 review turned out to be. These were
found by going looking for it again in the code written since.

**The paper ledger counted a refused SIZING as a trigger that never fired.**
`record_so_far` defined `never_triggered` as `booked=0` with no `skip_reason`.
`simulate` has a second path to `booked=0`: the trigger FIRES, `position_size`
refuses to buy anything, and the row returns with `exit_reason` set to the
refusal, `booked` still 0 and `skip_reason` still unset. Both landed in one
count, and REPORT_TEMPLATE quotes it verbatim as "picks never reached their
trigger at all", in the one section of the report whose whole argument is that
every figure arrives with its denominator.

No live row has been mislabelled: the sizing refusals need a zero or near zero
stop distance and the smallest on record is 0.33. The count was wrong by
construction and the first row to hit it would have been silent.

`triggered_but_unsized` is its own count now, named on every pass whether or
not there are any, with the refusals that produced it listed beside it. It is
identified POSITIVELY, by an `exit_reason` that is present and is not
`EXIT_NEVER`, so a row carrying no `exit_reason` at all still counts where it
always did: reading a null as a refusal would be the same mistake one level
down. The four states now partition the table and a claim holds that they do.

**A vendor reported ZERO is a measurement, and midday was filing it under
"never measured".** `rank_movers` tested `volume` and `average_volume` with
`not q.get(...)`, so a halted name, or one that printed premarket and has not
traded since, landed in the buckets the report describes as "the pass could not
price them ... these names were never measured". The tests are `is None` now. A
zero AVERAGE volume is a third state again, measured and with nothing to divide
by, and it is counted apart from both the missing field and the floors.

**`day_rvol` was the one null in the midday packet with no reason beside it.**
Every other null this pass writes carries one. A reader of a carry through row
could not tell a name the vendor never carried a volume for from one it measured
at zero, in the record another pass will compare against.

**A quote that was never sent was described as a quote missing a field.** A
picks ticker absent from the payload fell through to `read_quote({})`, which
took the branch for a quote carrying no `lastTradeTime` and published "the quote
carried no lastTradeTime, so how old its prices are is unknown rather than
merely large". The vendor sent nothing at all. It is reachable on any morning:
`quote_delayed` chunks its requests and returns partial data when a chunk fails.

**Midday's "subscribed" read discover's intent where the collector keeps the
record.** `morning_reach` decided it from `watchlist.json`'s subscribed flag,
which is what discover MEANT to subscribe at 07:15. CRITERIA [Monitor]'s stale
watchlist note already settles this in one line: "The file is not the evidence.
What the collector asked the socket for is."

2026-08-24 is the morning that made the distinction and it is exactly the shape
this would have misreported. A power cut collapsed the gap between the two jobs,
the collector read the previous session's watchlist and subscribed to the eight
context symbols alone, and by 12:00 the file on disk was today's and marked 42
names subscribed. Every one of them would have been captioned "the collector was
subscribed to this name and the 08:45 screen still did not publish it", for
names no premarket tape was ever collected for.

It reads `data/premarket/<date>-subscriptions.json` now, says which file it
read, and names any name the watchlist marks subscribed that the socket was
never asked for.

**And a market cap of zero rendered as n/a**, which is that table's word for a
field the vendor did not carry.

Four claims in `test_midday`, one in `test_regressions`, and the midday suite is
eighteen.

## 2026-08-31, fifth: a published median, a count nobody took, and a confound written early

Three changes, and the first is publishing wrong numbers on the live page
tonight.

**The score watch counted every booked pick once per paper rule version.**
`night/weekly_page.py`'s `how_did_the_score_do` joins picks to paper_trades,
which is keyed `(date, ticker, rule_version)`, and the predicate named only the
first two. That was harmless for exactly as long as one version existed.
`[Paper]` gained v2 on 2026-08-29 and the population went to 85 joined rows for
68 picks the same night, with only the BOOKED rows duplicating, so it
re-weighted toward the liquid subset rather than merely inflating.

What `site/Weekly.html` has been publishing since: yellow median adverse D+1
+1.98 percent against a true +0.19, yellow favourable +2.64 against +1.36, green
favourable -6.32 against -6.88. `README.md` still carries the pre-v2 readings and
its yellow +1.36 matches the corrected figure exactly, which dates the
regression to the v2 commit.

The worst of it is not a median. Green's booked P&L printed at n=12 when six
trades exist. Six is below `[Score watch] min_group_rows`, so that group should
have been WITHHELD and said so. A defect that inflates a count past a minimum
turns a guard into a publisher, and this one defeated the single rule on that
page whose job is to stop a median nobody should read from being read. It reads
withheld now, with its six rows and five sessions named.

The version comes from `sorted(paper_ledger.rule_versions())[0]`, the same
expression `record_so_far` already uses, so the page and the morning report
cannot come to rest on different rules.
`doc/research/SCORE_INVERSION.md` names v1 as the primary and that is what it
returns today.

**`sources_that_would_have_caught_it` was a literal empty list.**
`night/pool_recall.py` wrote `[]` on every missed row from the day it shipped and
never computed it, so 803 rows across 13 sessions published "not one of
discover's four priors would have found this name" as a measured finding. It is
the same defect the comment eleven lines below it in the same function describes
for `published`, and it survived a review that found that one because NOTHING
READS THE FIELD: a write only answer has no consumer to notice it is constant.

It is null with a reason now, and not computed, because the answer is not
available at 22:15. It needs discover's four source lists as they stood at
07:15, and production retains none of them: the watchlist carries `pool_source`
only for names that made the pool, and a missed name is by definition not in it.
Answering it properly costs a re-fetch of the prior session movers, the news
window and the earnings calendar, which is a design decision and a vendor spend
rather than a fix.

**`doc/research/SCORE_INVERSION.md` gains a fourth confound: gap direction.**
The score is unsigned, its gap component scores the ABSOLUTE gap, and every
quantity that file measures is taken from a long, so a bucket holding more
falling names is losing a race it was never entered in. Measured the same night
over the live rows carrying an excursion: green gapping up n=11 across 4
sessions, median favourable -4.24 percent; green gapping down n=11 across 6
sessions, median -8.69.

The mechanism was true on 2026-08-29 when that file was written and was simply
not written down. Adding it now, with both judging points still 200 rows away,
keeps it a pre-registration; adding it after either point is reached would make
it a rationalisation, and the date on the amendment line against the commit that
carries it is the only thing that separates the two. No judging rule moved and
no threshold moved.

`[Score watch]` does NOT move and the new paragraph says so explicitly, because
the obvious next argument is that a split halves every group under the minimum
and it does not: both halves of green clear at 11 and 11 across 4 and 6, both
halves of yellow at 12 and 11 across 4 and 5. Red's halves are withheld at 4 and
4, which is the withholding rule working. Those two minimums govern every group
on the weekly page, and lowering them so one new split publishes would change
numbers already published in order to serve it, on the one page built to watch
for a threshold turned until the output looks the way somebody wanted.

`night/weekly_page.py` does not render the split. The confound directly above
the new one commits to being reported when the primary is judged and is rendered
nowhere either, and `gap_pct` is a picks column outside `prune_data.py`'s
whitelist, so the split is recomputable on the day it is judged from evidence
already kept.

## 2026-08-31, fourth: the two files with no route back were the two nothing guarded

**What was wrong.** `morning/scan.py` wrote both of the artifacts
`night/backup_evidence.py` names as unrebuildable, and routed neither through
`core/artifacts.py`. Nine call sites in the tree resolve through that guard. The
one module that could destroy a morning outright was not among them.

**How it hid.** Two ways, and the second is the more interesting.

`write_packet` looked guarded because it is careful: it writes through a temp
sibling and `os.replace`, and its docstring explains at length why. That is a
real guarantee and it is a different one. It stops a run interrupted mid write
from leaving a packet that parses as nothing. It has never stopped a COMPLETE
run from replacing a frozen one.

The snapshot half is subtler. `snapshot_bars` DOES resolve through the guard, so
`collect_premarket` reads as protected and the source grep in
`test_entrypoints.claim_operator_tools_spare_artifacts` passes it. What that
call guards is `premarket_snapshot.pending.jsonl`, a name only that run writes
and which therefore has nothing to spare; scan passes `overwrite=True` there and
is right to. The frozen artifact is the name `_promote_snapshot` moves the
pending file INTO, and that was a bare `os.replace`. A guard on the wrong name
reads exactly like a guard.

`thin_rerun_stands_down` is not this either. It refuses a rerun carrying LESS
evidence. A hand run on a live tape hours after the open carries MORE, the whole
session against the premarket window, so it stands down on the harmless case and
waves through the one that destroys the record.

**It has already happened, and the evidence is still on disk.**
`runs/2026-08-21/packet.json` is stamped 15:46:38 and holds one candidate,
AAPL.US, beside twelve picks rows written that morning naming none of it. That
session's 08:45 evidence is gone. The nightly backup exists because of that
morning and says so in its own docstring, and a backup reports a loss rather
than preventing one.

**What changed.** Both writes resolve against `overwrite or scheduled_run()`, on
the precedent every other writer already follows, and `scan` gains
`--overwrite`. Production is unaffected: `job_morning_chain.bat` sets `PMD_JOB`,
so a scheduled scan and a watchdog rerun own today's artifacts and replace them
exactly as before. Only the operator path changes, and it now says what it
spared and where it wrote instead.

**Two claims, because a source grep was what missed this.**
`claim_a_hand_run_of_scan_spares_the_morning_it_would_replace` drives the
BEHAVIOUR in both directions: a hand run spares the packet and the collector
copy and writes beside them, and a scheduled run still replaces both, because a
rule that spared them would break the schedule rather than protect it. And
`morning.scan` joins the hand maintained list in
`claim_operator_tools_spare_artifacts`, which never asked about it.

**Four existing claims now say which path they exercise.** The 09:25 rerun claim
and the interrupted write claim both pass `overwrite=True`, because both are
about the scheduled path and neither was explicit about it.

**A note for whoever writes the next comment in this module.** `scan.py`
deliberately does not spell the recall filename or the backup module's name. The
notable movers scope fence and the backup reader check both grep this file for
them, and both are blunt on purpose. Naming either in prose fails the suite. The
wording in place says so where it matters.

## 2026-08-31, third: three things that were counted and not said

**What this was.** A read of the whole tree against what it claims, prompted by
nothing breaking. The suite was green before it and is green after it. Three
findings, and what they have in common is the shape rather than the subject:
each one was a fact the system already held and did not put in front of a
reader.

**One. `-Unregister` left `probe-socket-cost` armed.** The three one off probes
are deliberately kept out of `$jobs`, which is what stops a plain run of
`register_tasks.ps1` resurrecting a probe meant to be deleted. It costs each
probe its name written out twice, once in its own block and once in the
`-Unregister` tail, and `probe-socket-cost` was added on 2026-08-31 with only
the first. A full removal would have taken away the ten recurring tasks and the
two older probes and left it registered, in a folder the script had just
reported as emptied. The script's own comment on that tail says why that is
worse than removing nothing.

Fixed, and the second copy of the name is no longer what holds it:
`claim_unregister_removes_every_probe_register_can_create` reads both verbs off
the file and fails on any task name the script can create and cannot remove, so
a fourth probe is covered the moment it is written.

**Two. The midday movers breakdown named five of its ten buckets.** The one it
left out is `refused`, which counts the quotes `read_quote` declined for a
stale price, an absent `lastTradeTime` or a prior session carrying no close.
It was also the only bucket in the tally with no example list, so a refused
name could not be chased to a symbol.

Both holes were invisible on 2026-08-31 because that session refused nothing:
the five printed numbers added to 2,751 and the line reconciled by luck. On a
session where the vendor serves stale prices `refused` is the LARGEST bucket
here, and a reader would have been handed a population that does not add up
with nothing naming where the difference went. That is the defect this pass was
written to avoid, reached through the one bucket that was not a missing field.

The breakdown now names every bucket, `refused` carries examples like the four
beside it, and the renderer states the arithmetic rather than leaving it to be
attempted: a tally that does not cover the quoted count says so in the report
and sends the reader to the packet. `claim_the_breakdown_names_every_name_it_counted`
holds all three directions, including that the guard stays quiet on a healthy
session.

**Three. README drift, on three facts a reader uses to check the rest.** The
schedule table omitted the 12:00 midday job while the sentence under it said
"that table is the whole recurring schedule", and the flowchart omitted it too.
The one off probes were given as `-Probe` and `-Capture`, two of three. And the
analyst timeout was still reported as 537 seconds with the derivation that
produced it, when CRITERIA has read 1007 since 2026-08-29 and the slowest
morning on record is the 335.7 seconds of 2026-08-27, not the 226.1 the file
named. All three corrected, and the timeout paragraph now also carries
`job_log_stale_after_s`, because that number is derived from the timeout and
moving one without the other makes a healthy analyst step read as a dead job.

**What none of this touches.** No published number changes. The midday packet
already carried the refused count; what changed is that the report prints it.
`data/UNVERIFIED` is still in place and delivery is still gated.

## 2026-08-31, second: a midday pass, and the field it must never divide by

**What changed.** A tenth scheduled task at 12:00, two new modules under
`src/midday/`, and CRITERIA gains [Midday]. It answers the two questions the
08:45 report cannot, because the session it describes has not opened yet: what
the morning's own picks did, and what else moved that the morning never named.

**Why it reads quotes and not bars.** EODHD does not publish today's intraday
bars until overnight. Measured: today's completed session returned zero 1m rows
two hours after the close while the three sessions before it returned full
days. That is the same vendor lag the 07:00 catch-up exists to absorb, seen
from the other side, and it rules out every design that reads bars at any hour
of the trading day.

**The rule, and the case it refuses to answer.** [Paper]'s rule run against
what a daily quote can say. A name whose high never reached the entry never
filled, so its low is not read against the stop: the first prototype got that
wrong and booked a loss on a position nobody held. A name whose OPEN cleared
the entry filled at the session's first print, so a later low through the stop
is unambiguously a stop out. A name that filled intraday cannot be resolved at
all, because a daily high and low carry no order, and that count is published
on every edition rather than rounded into whichever verdict the arithmetic
reached first.

**What that gap is worth fixing with.** Moving [Collector] stop_time past the
open, which turns one daily bar into timestamped minute bars. Gated on a
measurement: `tasks\job_probe_socket_cost.bat` is written and NOT yet run.
Connecting, subscribing and reconnecting were measured at zero on 2026-08-13,
twice, but on the quiet evening tape; the per message cost on a heavy live tape
has never been readable, because the one window that streamed 1,574 messages
straddled the counter's daily reset.

**The defect this nearly shipped with.** The denominator. See DECISIONS
2026-08-31, second, in full: previousClosePrice is not one quantity, it was the
prior session for about a third of names and TODAY for about another third, and
previousCloseDate was correct on both so the vintage check written into the
first draft of [Midday] would have passed on every bad row. The prior close now
comes from eod-bulk-last-day for an explicitly named date. Corrected before it
ever ran scheduled, and the measured difference is not cosmetic: on 2026-08-31
the broken denominator found three movers and the corrected one finds eight,
the two largest being EIX.US at -22.69 percent and PCG.US at -19.22 percent.

**Three endpoint prices added to [Quota costs], and one is a correction.**
Measured the same way as the rest, five calls between two user reads, every
delta dividing exactly: news 5, news-feed 5, intraday-1m 5. intraday had never
been priced and a reader counting http calls would have costed it at one, so
the 07:15 baseline warm is about 210 credits rather than 42 and the nightly
verify about 250 rather than 50. Nothing was undersized, because no gate is
sized off either; what changes is that the next gate cannot be wrong by five.

**No model runs in it.** The morning uses the analyst because what to make of a
premarket is open. Midday asks closed questions, so the report is rendered from
the packet: no claude CLI call, no containment check, no quantifier guard,
because no prose is written for any of them to police. The renderer builds its
own markdown and escapes on the way out, which the claims exercise against a
headline carrying a pipe, a newline, a forged heading, a forged table row and a
script tag.

**Held to sixteen mutations, all caught.** Including both boundary flips on the
entry, the one on the stop, an intraday fill booking a stop out it cannot know,
the never triggered branch falling through to read a stop, and a missing bulk
close falling back to the quote's own field. Two claims were rewritten during
that pass because they survived their own defect: one asserted against a table
row the headline never reaches, and one described a mutation that turned out to
be behaviourally equivalent.

## 2026-08-31: the drifted rotation edge is fixed, 0.00014 becomes 0.0002

**What changed.** [Score premarket float rotation]'s one point edge moved from
0.00014 to 0.0002. The two point edge is unmoved at 0.00033. The claim that
traces the shipped edges to an archived fit now reads the NEWEST payload rather
than a named one, so a later measurement that disagrees with what is shipped
fails instead of being ignored.

**Why it had to.** That section exists so the rotation bands pay what the RVOL
bands pay, because a name is scored by one or the other and never both. On
today's population the shipped edges paid the one point band to 15.34 percent
against a 10.89 percent target, so a name with no usable baseline was getting
that point half again as often as an equivalent name that had one. The re-fit
pays 10.58. The miss falls from 4.54 points to 0.40.

**It is drift in the data, not a fault in the method.** The two point edge
reproduces exactly. universe.json has been rebuilt twice since the 2026-08-20
fit and ten more sessions are cached, and the one point edge sits low in its
decade where a small shift moves the quantile a long way. That is the same
sensitivity the rounding argument turned on: one significant figure was refused
at a 4.94 point miss, and this was 4.54.

**No historical row was rescored**, on the no overwriting rule. Two rows in the
record would have scored differently: NSSC on 2026-08-24 from 7.0 green to 6.0
yellow, and WSM on 2026-08-26 from 6.0 to 5.0, still yellow.

**The claim caught this by hand-editing CRITERIA, which is what it is for.**
Moving the edge failed the suite immediately, because
claim_the_shipped_rotation_edges_are_the_ones_the_study_fitted pinned the value
to float_rotation_study-2026-08-20-warmup-fixed.json by name. Pinning one named
file is one file too specific: it would have passed forever against an elder
payload while a newer fit disagreed. It now globs and takes the newest, and is
mutation tested both ways.

**Not fixed, and deliberately: the score is still ordering outcomes backwards.**
Green 25 rows, best price reached -7.44 percent; yellow 31 rows, +2.64. That is
six sessions, it is pre-registered in doc/research/SCORE_INVERSION.md, and
acting on it now would be fitting the score to six mornings. The rotation edge
is drift from a measurement that exists. The score inversion is a question whose
measurement is not in yet. They are different things and only one of them is
fixable today.

## 2026-08-31: the denominator floor study the CRITERIA note said was owed

**What changed.** research/sweep_baseline_floor.py, a new instrument, re-fits
the float rotation edges at every candidate denominator floor by the same
arithmetic float_rotation_study uses. That study now records sweep_rows, four
fields per scored row, so the re-fit is arithmetic on a file and takes no vendor
call. round_down and edge_at were lifted out of run() to module scope so a claim
can hold the sweep's copies to them. No threshold moved.

**The answer, over 6,500 scored rows from 50 sessions.** Raising the floor to
10,000 moves the two point rotation edge from 0.00033 to 0.00056, a 70 percent
move, with 48 percent at 5,000 and 21 percent at 2,000. The floor note predicted
that direction and the size is now measured.

**What the note did not name, and it is the part that decides the change.**
[Day setup] premarket_rvol is > 1.5 with NO rotation alternative, and
Rule.test(None) is false, so a name the floor refuses does not get rescored, it
leaves the day watchlist. Over 11 live sessions and 70 published ratios a 10,000
floor refuses 16, two of them day_eligible and both green: PLAB on 2026-08-26 at
a 4,135 share median, SAIC on 2026-08-31 at 1,002. Both carry rotations far
above the edge admitting the same share the RVOL floor admits. The change is
three parts, not two.

**The score survives where membership does not.** Of the 16 refused rows, 14 are
paid the same points by rotation under the current edges, 2 less, none more.

**Held in place by** one claim mutation tested against four edits: the sweep
rounds to one significant figure, a median exactly on the floor is refused, the
one point edge is read at the wrong cumulative share, and the RVOL target is
read over every row rather than the ones the floor admits. Its first draft
missed two of those, because the real file has no median sitting exactly on a
floor and one mutation was a no-op at the shipped value; the claim now carries
synthetic boundary rows and asserts the target moves with the floor.

**Also recorded:** a re-run of float_rotation_study on today's population
reproduces the shipped two point edge, 0.00033, and does NOT reproduce the one
point edge, giving 0.0002 against the shipped 0.00014. The population moved. The
edges are not changed here; the divergence is written down where the next
re-derivation will find it.

## 2026-08-31: two things today's report should have said and did not

**Found by reading the 2026-08-31 report against its own packet.** Both are
disclosure defects rather than wrong numbers, and both are the shape this
project calls worst: something the machine already knew, not reaching the page.

**1. A thin RVOL denominator never reached the reader.** scan.py has computed
this since 2026-08-28 and put it in gaps_to_fill, and gaps_to_fill reaches the
report only through the Summary's "anything that materially weakens this
morning's evidence", which is the model's judgement. Today that judgement went
the other way. Both of the morning's two candidates rested on a denominator
under the threshold, the top scored name of the day drew 2 of its 10 points from
an RVOL of 27.01 built on a 1,002 share median, two shares above the floor, and
the report said neither. CRITERIA's own measurement is that below 10,000 shares
15 to 30 percent of a name's ordinary sessions reach the top RVOL band by
construction, against 5 percent above 100,000.

evidence_roll gains a thin_baseline list and a required sentence, and
REPORT_TEMPLATE.md quotes it word for word in Skips and traps with the per row
median attached. The gap entry stays: it feeds the Summary and the roll feeds
the section, and a claim holds that the two name the same rows. Nothing is
refused, capped or rescored; this is disclosure, and refusing here is the two
part change the floor note declines to make.

**2. The notable movers market cap carried no vintage, and disagreed with the
same document.** Its caps come from universe.json, rebuilt on Sundays. The
candidate blocks' market_cap is the live 08:45 quote. Today's report published
SAIC at 5.43 billion in one section and 5.84 in the other, and MNSO at 3.07
against 2.84, with nothing anywhere to say they were measured at different
moments. Every other quantity in that section is vintage stamped: as_of_session
for the move, price_time and price_age_seconds for the price.

Neither number is wrong and neither is fixable: one of those lists ranks by cap
over the whole universe and that many live quotes is not something the morning
can buy. The block gains market_cap_as_of, and market_cap_as_of_reason where the
file carries no stamp, which is a different fact from an old one. Spelled
market_cap_as_of_reason and not market_cap_reason because the ROWS already use
that name for a cap missing on one symbol.

**Held in place by** two claims mutation tested against seven edits: the roll
stops carrying the list, a name exactly on the line is called thin, the per row
why stops naming its own median, the template stops quoting the line, the cap
stamp is dropped, the block reuses the rows' spelling, and the stamp is repeated
per row where it can disagree with the block. The cap claim also refuses to pass
on an empty section, which is how its first draft passed while broken.

**Also corrected:** README said the fill warning's 6 of 10 and 6 of 44 were
measured over 66 rows. They are over the 54 where the night reached a verdict;
the other 12 it could not judge either. The code and CRITERIA were right and the
README was the thing that was wrong.

## 2026-08-29: the README says what you see, not only how it works

**What changed.** A new section, "What you actually see, and how to read it",
sits between the schedule and the setup instructions. It names the two documents
the system produces, says where they are and why the report is not in an inbox,
walks all eleven report sections and all five weekly ones, gives the reading
order at 08:50, and follows one invented morning end to end from the 07:15
ranking to the next day's ledger skip.

**Why it had to.** Every document in this project described the machine. None
described the output. A reader could learn what backfill_premarket.py does and
still not know which section of the report to read first, that the RVOL column
is an estimate, or that the fill warning's silence is not an approval. That is
the gap that produced "I really dont know what I am looking at" on 2026-08-29,
and it was a documentation failure rather than a reporting one.

**Every ticker and number in the worked examples is invented, and the section
says so at the top.** runs/ and site/ are gitignored so no real morning reaches
a public repository, and a usage guide is not a reason to break that. The one
exception is the paper ledger's aggregate counts, which are already public in
this file, and they are labelled where they are used.

**One figure was wrong in the first draft and was caught by reading it back off
the code.** The never-triggered count was written as 28 picks across 7 sessions.
paper_ledger.record_so_far reports 6. Every other figure in the section was
verified the same way rather than carried over from a note.

## 2026-08-29: the architecture page has no standing state at all

**What changed.** The masthead block is gone, not shortened and not rewritten.
The page now runs from the lede straight into the table of contents.

**Why.** The previous entry replaced two stacked blocks with one and called that
the fix. It was not. A standing state on this page is the wrong artifact at any
length, because it goes stale the next weekday and a reader has no way to tell
whether it did. Every fact it carried has a home that stays right on its own:
the gate is a load bearing rule in section 11 and a row in section 10, the
counts are CHANGELOG.md, the reasoning is DECISIONS.md, the readings are
doc/research/, and the pre-registration is SCORE_INVERSION.md. The page
describes the machine. Nothing else.

**Nothing was lost to the deletion.** The one fact that had lived only in that
block, the 2026-08-19 collector against vendor reading of 0 of 73 symbols within
one percent at a median absolute difference of 90.0 percent, was moved into
doc/research/COLLECTOR_VOLUME.md's session table in the preceding commit.

## 2026-08-29: one standing state, rewritten, not a stack of corrections

**What changed.** The architecture page's masthead carried two stacked blocks:
a "Standing state, 2026-08-20" and, above it, a "read the standing state below
as of 2026-08-20, six things have moved" correction added the same day the arc
page's equivalent was being removed for exactly that fault. Both are replaced by
one block dated today, and a line under it says the block is REWRITTEN rather
than appended to and names where a dated log belongs instead.

**Why it had to.** The correction was the mistake. Appending to a status block
is the right instinct in the record, where a corrected value must sit beside the
original, and it is the wrong one on a page whose whole job is to describe the
machine as it stands: a reader hit fifty lines of qualifications and errata
before reaching the table of contents. The two rules are not in tension. A
MEASUREMENT is never overwritten. A DESCRIPTION is never accreted.

**One fact was rescued before the old block went.** The 2026-08-19 collector
against vendor verification, 0 of 73 symbols within one percent at a median
absolute difference of 90.0 percent, existed nowhere but that masthead. It is
now a row in doc/research/COLLECTOR_VOLUME.md's session table, which is where a
reading belongs. Everything else in the block was already in CHANGELOG.md,
DECISIONS.md or that same document.

**What the new block says**, in four facts that qualify the page and are not
visible from its figures: no email has ever been sent; the record has started
and decides nothing yet, at 66 rows over 7 sessions; the ledger separated the
screen from the rule, because all 16 booked trades were in profit at some point
while held; and the conviction score orders outcomes backwards so far, which is
six sessions and not a result.

## 2026-08-29: the arc page goes back to being about the arc

**What changed.** doc/Premarketdesk_ADayRunArc.html had grown a standing state
board at the top and three sections headed "Added 2026-08-29". The board is
gone, the dated headings are gone, and the sections are reordered so the page
follows one day once, in order: the timeline, the morning, the night, the
measurement chain, why there is one rule, what a finished row looks like, the
fill warning, what the record is worth to a reader, failure, rules, file map.
A navigation list was added, and every section carries an anchor.

**Why it had to.** The page has one job, which is to show the arc of a day and
what each stage of it achieves. A reader hitting a status board and a changelog
before reaching the first stage cannot use it for that, and the material was
already held properly in CHANGELOG.md and DECISIONS.md, so the page was
carrying a third copy that would go stale on its own schedule.

**What was cut, and where it lives instead.** The "Where this actually stands,
2026-08-20" block with its nested corrections; the "What the measurements said"
table of current readings; the v1 against v2 dollar totals. All of it is a
dated observation rather than a description of a stage, and all of it is in
CHANGELOG.md and DECISIONS.md already.

**What was kept and re-framed.** Every finding that explains why a stage
exists: both excursion medians changing sign on measured references, the ten to
one inversion of the premise that specified the work, every trade being in
profit at some point while held, and the ten of ten that peaked early and
closed red. Those are what the stages achieve, which is what the page is for.

**Also corrected here:** the same one vendor rule the architecture page was
carrying, which said nothing in night imports Alpaca; a lede that named which
morning a one off probe was armed for; and both file maps, which still had
job_probe_capture armed for 2026-08-24 after it was retired on 2026-08-26.

## 2026-08-29: the architecture page catches up, and two of its statements were wrong

**What changed.** doc/ArchitecturePremarketdesk.html had not been touched since
2026-08-20 and described a night pipeline of four steps against the ten that
actually run. Eight components were added (C59 true_volume, C60 paper_ledger,
C61 weekly_page, C62 backup_evidence, C63 prune_data, C64 the paper_trades
table, C65 site/Weekly.html, C66 the Alpaca REST feed), the picks row figure
went from three passes to four with the ledger row beside it, the store matrix
gained five rows, the failure table gained five, and sections 05, 06, 07, 11
and 12 were reconciled to the tree. The arc page gained the record section and
backup_evidence, which its nightly step list had never named.

**Two statements were not merely stale, they were false, and both are the kind
this project calls the worst kind.** The load bearing rule "EODHD is the only
market data source in the pipeline" carried its own exception clause: "nothing
in selection, collect, morning or night imports them". Since 2026-08-29 two
scheduled night steps import Alpaca. The rule is rewritten to what it actually
protects, which is that no vendor but EODHD reaches a published number, and the
change is stated in the rule rather than quietly absorbed. Separately, the
store matrix marked C63 as a WRITER of the collector capture. prune_data has
never touched that file and its own docstring says it is never a candidate at
any age. A reader checking whether the only irreplaceable artifact in the tree
is safe would have got the wrong answer from the page.

**Also corrected:** the analyst timeout read 537 in two places against 1007;
the report template was called nine sections in two places and eleven is right;
the tasks directory was called seven .bat files against nine, two of which are
unscheduled probes; the standing state block still said the picks table held one
morning and the long goal was at zero, against 66 rows over 7 sessions with 60
outcomes filled; and the quantifier guard was still called warn against
enforcing since 2026-08-28.

**Nothing was overwritten.** The 2026-08-20 standing state stays where it is
with a dated correction block above it, and the analyst timeout figcaption keeps
the four mornings it was written about. That is the same rule the night columns
follow: a correction sits beside the original, because the reasoning that turned
out to be wrong is the part worth keeping.

## 2026-08-29: the morning report starts carrying what the record has observed

**What changed.** paper_trades gains minutes_to_trigger, minutes_to_peak and
mfe_pct_held. night/paper_ledger.py gains record_so_far, which turns the ledger
into counts with their own denominators; morning/scan.py puts it in the packet;
REPORT_TEMPLATE.md gains a "What the record says so far" section that quotes it.
paper_ledger's probe_alpaca and true_volume imports moved inside book() so the
08:45 scan can read the record without loading a research HTTP client. No screen
threshold moved and no vendor call was added to the morning.

**Why it had to.** Everything built earlier today was a measurement apparatus
and none of it changed what a reader does at 08:50. Individual past outcomes
never will: PLAB losing 19 percent last Wednesday predicts nothing about today.
The shape of what those trades did is a different quantity and it was being
thrown away.

**MEASURED over v1's 16 trades across 6 sessions:**

  triggered within 30 minutes of the open   14 of 16, median 1 minute
  triggered at 291 and 337 minutes           2, making +0.60 and +0.36 percent
  never triggered                           28 picks, median -1.97 percent open
                                            to close, 7 of 28 above their open
  peaked within 10 minutes of entry         10, of which 10 closed BELOW entry
  peaked over 100 minutes after entry        4, of which  4 closed ABOVE it
  median best while a position was open     +1.84 percent
  median booked at the exit                 -1.38 percent

**It is a record and not a rule, and the template enforces that.** Ten and four
are not sample sizes. The section must quote every count with its denominator,
must name the rule version, must say the ledger is as of last night, and is
forbidden from writing any of it as an instruction or calling it a pattern, a
signal, an edge or a tendency. Three specimens of the forbidden phrasing are
listed in the template.

**Two timings because they answer different questions.** minutes_to_trigger
runs from the open, minutes_to_peak from the ENTRY. Measured from the open the
second would fold the wait into the hold and a name that triggered at 09:31
would look like one that triggered at 14:20.

**Held in place by** two claims, mutation tested against eight edits: every
count arrives over its own row AND session denominator, a pick skipped on
evidence is never counted as one that never triggered, the record names its
rule version, the trigger is timed from the open and the peak from the entry,
the best price while held is the highest rather than the first, a trade that
never fired times nothing rather than zero, and paper_ledger keeps a research
client out of its module scope.

## 2026-08-29: rule v2 books beside v1, and the morning gets a fill warning

**What changed.** CRITERIA [Paper] now registers TWO rule versions through its
sizing map, which is also the registry: v1 sizes by a fixed notional and v2 by
a fixed dollar risk. Everything else about the two is identical. New keys, all
SEED: account_notional 100000, risk_notional 750, max_position_notional 25000.
night/paper_ledger.py books every registered version over one fetch and prints
a head to head. New CRITERIA section [Fill warning] and a morning band warning
written by scan at 08:45, carried in the packet, on the picks row and in the
report's Skips and traps section. No screen threshold moved.

**Why v2 is a sizing rule and not an exit rule.** Every one of v1's 16 trades
was in profit at some point while held, median best +1.84 percent, median given
back -3.91 points. The entries are not random. But the median trade reached
only 0.46 of the risk it was taking and just 4 of 16 ever reached 1R, and the
two largest losses were the two widest stops. That is a sizing defect with a
standard fix, where an exit rule would have been a free parameter to tune
against 16 trades. See DECISIONS.md.

**The risk budget is calibrated to hold total risk CONSTANT**, at v1's own mean
of 772 dollars rounded to 750, so the versions differ in distribution and not
in amount. A smaller number would have manufactured the result.

**HEAD TO HEAD, over the same 16 trades across 6 sessions:**

  rule  mode        trades    total P&L     deployed    at risk   worst trade
  v1    notional        16    -3,487.81      158,512     12,354     -1,912.54
  v2    risk            16    -2,713.74      229,430     11,814       -748.90

Every per trade percent return is identical under both; sizing cannot change
what a trade did. Median -1.38 percent, win rate 5 of 16, under either. What
changes is the portfolio's shape. [Paper] pre-registers the verdict and its
judging point at 200 booked trades across 60 sessions, and 16 is not it.

**The morning fill warning, and its measured error rate.**

                  night: plausible   implausible   unknown
  morning thin                   6             6         0
  not flagged                   38             4         0
  unknown                        0             0        12

It catches 6 of the 10 untradeable levels, misses 4, and over-flags 6 of 44.
Those counts are printed in the report sentence itself. It uses its own words,
'thin' and 'not flagged', never the night's 'plausible', and the template is
told in the section never to write that a level is tradeable.

**Backfilled** onto all 66 existing rows from runs/&lt;date&gt;/premarket_snapshot.jsonl,
which is the same file the scan reads, so the comparison above rests on every
row rather than on the ones written from today.

**Held in place by** two new claims, mutation tested against eight edits: the
two sizings agree on entry, exit, reason and percent return and differ only in
share count, risk is constant under v2 and variable under v1, the cap stops
risk sizing becoming leverage, and a stop at the entry is refused rather than
sized off a fabricated risk; and the morning band reads [Truth]'s width, counts
a minute by its range, is null without evidence, keeps its own vocabulary, and
says on the row that its silence is not an approval.

## 2026-08-29: the weekly page starts watching whether the score orders anything

**What changed.** night/weekly_page.py gains a section grouping every live pick
that carries an outcome or a booked trade, by conviction bucket and by each
score component separately, reporting n, the session count, median booked P&L,
median mfe_pct_true and median mae_pct_true. New CRITERIA section [Score watch]
with min_group_rows 10 and min_group_sessions 3, both SEED. New
doc/research/SCORE_INVERSION.md holding the pre-registration. Nothing in the
morning path or the screen moved.

**Why it had to.** The score exists to order names by confidence and over the
first fifty filled rows it ordered them backwards, and nothing was watching.

**The section reports and concludes nothing.** No test, no p value, no verdict
in the code. The judging point, the three possible outcomes and the stop rule
are pre-registered, written today at 66 picks and 16 booked trades, which is
far below every threshold in that file. The primary is judged at 200 booked
trades across 60 sessions; the secondary, the two excursions, at 200 rows
across 40. Outcome 2 is "no relationship", defined in advance as the three
bucket medians spanning under one percentage point or not being monotone.
Outcome 3 is a confirmed inversion, and re-deriving the bands by inverting
them is explicitly not permitted.

**Both denominators everywhere, and a group too small is withheld with the
shortfall named.** Suppression is per METRIC: the ledger reaches 16 rows where
the outcome fill reaches 48, and one verdict over a group would either publish
a median resting on two trades or throw away twenty excursions to protect them.

**Component points are read from the packets**, which carry score_components
with the points the morning actually awarded. A component whose input was never
observed is null there and is ABSENT from its grouping rather than counted as
zero.

**WHAT IT SHOWS TODAY, and none of it is a result.**

  bucket    rows  sessions  booked P&L   favourable D+1   adverse D+1
  green       20         6    withheld           -7.44%        +0.10%
  yellow      21         5     -1.00%            +1.36%        +0.19%
  red          8         3    withheld         withheld      withheld

Green's booked P&L is withheld at 5 trades across 4 sessions. The direction of
the inversion survived the correction from the sampled reference levels to the
measured ones, which is the only new fact here and is still six sessions of
evidence.

**A schema fix fell out of it.** mfe_pct_true and mae_pct_true were declared
only in fill_outcomes' widening tuple, so store.init never created them and a
database that had never run the outcome fill lacked the columns; the new
section raised OperationalError on that path in the test sandbox. They are in
store.py now beside every other _true column and out of the widening tuple.

**Held in place by** three claims in test_regressions.py, mutation tested
against five edits: a group states rows AND sessions and is withheld on either,
each metric is judged on its own count, a withheld cell says how far short it
is, a component the morning could not score is absent rather than zero, and an
unscored row is its own group and never joins red.

## 2026-08-29: the paper ledger, one written rule, and a horizon that was off by one

**What changed.** New CRITERIA section [Paper] holding ONE rule, written before
any code as specified: trigger, entry price, stop, same minute tie break, exit,
size, and what happens when the trigger never fires. New module
src/night/paper_ledger.py applying it, new paper_trades table keyed on (date,
ticker, rule_version), and a nightly step after truth. New keys, all SEED:
rule_version v1, session_close 16:00, position_notional 10000,
max_band_participation 0.04. Nothing in the morning path moved and no screen
threshold changed.

**THE OFF BY ONE.** Writing the rule forced the question of which session it
trades, and [Outcomes] turns out to measure the wrong one. The scan runs 08:45
on the pick date and the report is about the open ninety minutes later, but
next_day_open through mae_pct_true all describe the session AFTER that. The
session the report was about is measured by nothing.

AXTI on 2026-08-27: entry_ref 70.94, its own session opened 70.30 and reached
70.85, a miss by 0.13 percent. next_day_high is 65.4155 from 2026-08-28 and
mfe_pct reads -7.79. Nothing in [Outcomes] is changed, because repointing those
columns would rewrite the meaning of every row already in the table. The ledger
fetches its own bars for its own session and the mismatch is written into
CRITERIA [Paper], the module docstring and the ledger's own summary line.

Every mfe and mae figure quoted in this file on 2026-08-28 and 2026-08-29
therefore describes D+1. The reference gap measurement is unaffected: both of
its halves are premarket levels from the same morning.

**FIRST RESULT, rule v1, 66 picks across 7 sessions.**

  booked          16 trades across 6 sessions
  median          -1.38 percent, which is -132.74 dollars on a 10,000 position
  win rate        5 of 16
  worst drawdown  -20.33 percent
  exits           4 stopped, 12 held to the close
  not traded      22 skipped because fill_plausible was not 'plausible',
                  28 never reached the trigger

  beside it, mfe_pct_true over the same picks: median +2.64 percent, n=15.

That last pair is the point of the whole exercise and it is a four point gap.
The BOUND says the tape ran 2.64 percent past the reference at its best moment;
the RULE captured -1.38. They are also measured over different sessions, which
the summary line says every time it prints.

Grouped, and every group is far too small to act on:

  day_eligible      n=3   3 sessions   median +2.52%   wins 2/3
  not day eligible  n=13  6 sessions   median -1.70%   wins 3/13
  conviction green  n=5   4 sessions   median -2.75%   wins 2/5
  conviction yellow n=10  5 sessions   median -1.00%   wins 3/10
  conviction red    n=1   1 session    median -4.11%   wins 0/1

**Held in place by** three claims in test_regressions.py, mutation tested
against nine edits. The rule reads its minutes in order, which is the whole
reason it fetches one minute data: a gap through the trigger fills at the open,
a minute that both triggers and stops is a loss, a low that undercuts the stop
BEFORE the trigger fires is not a stop, and an untaken trade is null rather
than zero. Every live pick gets a ledger row, a declined one carries the
evidence, an unmeasured level is never borrowed from the sampled pair, and a
re-run of one rule version replaces its own rows. And [Truth]
min_fill_band_notional equals [Paper] position_notional over
max_band_participation, so the placeholder set yesterday is now derived rather
than asserted.

## 2026-08-29: whether the reference level was a price anyone could have got

**What changed.** night/true_volume.py measures, off the bars it already
fetches, how much traded within [Truth] fill_band_pct of entry_ref_true and
over how many minutes, and writes fill_band_volume, fill_band_minutes,
fill_band_notional, fill_band_pct, fill_plausible and fill_plausible_reason
into picks. Two new SEED keys in CRITERIA [Truth]: fill_band_pct 0.005 and
min_fill_band_notional 250000. Nothing screens on any of it and no threshold in
the morning path moved.

**Why it had to.** entry_ref is the level every mfe_pct and mae_pct is measured
from, and on a thin name it is one print. The record could not tell a level a
market was standing at from one a single trade produced, and both were feeding
the table this project says its seed thresholds will be calibrated against.

**fill_plausible is three state and never a boolean:** plausible, implausible,
unknown. A boolean has no room for the third, and a row the feed could not
reach reading as one that was checked and failed is the failure this project
keeps finding under other names.

**The counts.** Two of the three the design asked for already existed:
pm_volume_true is the window total and true_bars is the count of minutes
carrying a trade, since Alpaca publishes a one minute bar only for a minute
that traded. fill_band_volume is the new one. It is an UPPER BOUND and is
labelled one: a one minute bar carries no distribution, so a minute running
from below up into the band counts whole.

**Two definitions were built and thrown away first**, both caught by the
calibration rather than by review. Counting a minute by its own mean scored
BABA's 2,986,339 premarket shares as 0 at the level, because a session high is
an extreme no minute averages near. Requiring a minute count as well as a
volume rejected MSTR's 49,768 shares in one minute, which is 1.4 million
dollars and plainly a market. The verdict rests on notional alone; the minute
count is recorded because it says how loose the volume bound is. See
DECISIONS.md.

**MEASURED 2026-08-29**, 66 live rows across 7 sessions: 44 plausible, 10
implausible across 4 sessions, 12 unknown. The twelve unknown are all of
2026-08-21, whose packet records no rvol_cutoff_hhmm; they are marked rather
than left null, because a null verdict is a fourth state.

The ten implausible, thinnest first, all within 0.5 percent of the level:
CSIQ 500 shares over 2 minutes for 7,085 dollars, DQ 2,010 over 3 for 28,421,
SCSC 714 over 1 for 42,840, MNSO 6,030 over 2 for 69,466, HMY 3,845 over 1 for
87,205, AAP 1,898 over 1 for 108,755, CHA 10,577 over 5 for 116,347, BWLP 6,748
over 7 for 158,173, BLSH 6,518 over 8 for 188,370, TIGR 39,761 over 1 for
224,252.

**Worth flagging rather than concluding.** Six of the nine day_eligible rows
are unknown, all six being 2026-08-21. Any reading of that group rests on three
rows with measured references, not nine.

**Held in place by** three claims in test_regressions.py, mutation tested
against eight edits: a minute counts when its range reaches the band and not
when its mean does, and an absent level measures nothing rather than zero; the
verdict has three states with the numbers behind each, the floor is the least
that counts rather than the least that fails, and one liquid minute is still a
market; and a refused session marks its rows unknown with the reason, never
over a verdict already taken and never on a test row.

## 2026-08-29: the reference levels get measured, beside the ones that were sampled

**What changed.** night/true_volume.py now reads the high, the low and a volume
weighted price off the Alpaca bars it was already fetching, and writes
entry_ref_true, stop_ref_true, entry_ref_collector_window,
stop_ref_collector_window and refs_true_reason into picks beside entry_ref and
stop_ref. night/fill_outcomes.py gains mfe_pct_true and mae_pct_true, filled by
a separate pass that spends no vendor call. Both passes report the distribution
of the gap they open up. No sampled column is corrected, replaced or removed,
and no threshold moved.

**Why it had to.** entry_ref and stop_ref are the collector's raw live levels,
which are the extremes of a socket sample. A sample understates a maximum and
overstates a minimum, so mfe_pct was overstated and mae_pct was overstated in
depth, both by construction and neither by a measured amount. CRITERIA.md and
BUILD_PLAN.md both designate the picks table as the record the seed thresholds
will one day be recalibrated against, and it was carrying a biased excursion in
every row with nothing beside it to say so.

**What the measurement found.** Over 54 live rows across the six sessions whose
packets carry an rvol_cutoff_hhmm, the median entry reference gap is +1.189
percent and the median stop reference gap is -1.732 percent. Split into its
two causes, the median sampling effect is +0.095 percent and the median late
start effect is +0.984, which is ten to one against the premise that specified
the work: the socket reproduces the extremes of the minutes it hears, and
nearly all of the gap is 04:00 to 07:20 going unheard.

Over the 48 rows across five sessions carrying both an outcome and a measured
reference, the favourable excursion median moves +0.8132 to -2.1271 percent and
the adverse median moves -1.9243 to +0.1465. Both change sign. The count of
picks whose next session reached the entry reference falls from 29 of 48 to 20,
and the count that undercut the stop reference falls from 30 to 22.

Five sessions is five observations, the sample unit is the session, and this
measures the record rather than the screen.

**Held in place by** three claims in test_regressions.py, each mutation tested.
reference_level reads the field [Picks] names rather than assuming high and low,
and returns null rather than a fabricated zero on an empty window; the full
window pair and the collector window pair stay in separate columns, the sampled
pair survives the write, and a refused float cannot become the recorded reason a
reference level is missing; and the true excursion is null wherever the true
reference is, refuses a row repriced by a corporate action, never reads a
source='test' row, and writes nothing on a second run.

**2026-08-21 is refused** and says so. Its packet carries no rvol_cutoff_hhmm,
so the window the morning used is unknown, and this pass will not guess a
window: a guessed one mismeasures precisely the sessions that went wrong.

## 2026-08-29: the analyst timeout is raised, and the number derived from it moves with it

[Analyst] timeout_s 537 to 1007, and [Monitor] job_log_stale_after_s 1200 to
2200. The RULE behind the first is unchanged and has been since it was written:
three times the slowest morning on record. Its evidence moved. The slowest is
335.7 seconds on 2026-08-27, and three times that is 1,007.

The 2026-08-28 pass measured this and declined to act on it, listing the trade
for the owner. The owner chose the wider timeout, on the ground that a slower
report costs nothing and a correct, detailed report is the whole point.

That reading corrects the direction the note was drifting in, and it is worth
writing down plainly. THE TIMEOUT IS NOT A SPEED CONTROL. Exceeding it does not
make the report late; it kills the narrative and hands the morning the
deterministic plain table. So the number being too SMALL is the risk to a
detailed report, and the pressure on it comes from the detail itself: output
grew from 18,264 tokens to 28,633 across the week, and duration grew with it.
Headroom over the slowest morning was 201 seconds. It is now 671.

max_attempts stays at 2 and quantifier_regenerations at 1. Lowering either
would have bought the same headroom by removing a retry, which is a smaller
report on a bad morning rather than a later one, and that is the trade the
owner declined.

**The coupled number, which is why this could not be one edit.** cmd writes a
step marker at each boundary and nothing touches the log while a python step
runs, so the longest silence a HEALTHY morning can produce is the analyst at
max_attempts times timeout_s. job_log_stale_after_s is what the watchdog uses
to tell a hung job from a working one. At 1200 against a 2,014 second silence
it would have declared a working chain dead and launched a second one onto the
same packet.json and another CLI completion. 2 x 1007 is 2,014 and 2,200 leaves
three minutes over it.

**What the larger watchdog number costs**, recorded rather than left to be
found. The blind band widens from twenty minutes to about thirty-seven: a job
that dies with NO finish marker, leaving only a warm log, reads as
possibly-alive for that much longer. Two existing bounds are unchanged. The
mtime is asked last, so any death where a step exited is caught by its finish
marker whatever the mtime says. And where the mtime is the only evidence and no
later pass falls inside the window, the job is reported UNRESOLVED and counted
as a problem rather than as RUNNING, which for the morning chain is the same
verdict at 1200 as at 2200. What actually changes is that the watchdog will no
longer RERUN a chain in that band, which is the safer direction.

**The arithmetic, checked rather than asserted.** Two attempts exhaust at
09:18:53, eleven minutes before the open and six minutes before the 09:25
watchdog pass. The margin against the OPEN is not the binding one: a report
landing at 09:19 is still a premarket report, where a chain still running at
09:25 is one the watchdog has to reason about. Six minutes is the number to
watch if this rises again.

**And the coupling is now machine checked**, which is the part that should have
existed before any of this. It lived in prose in two files and in arithmetic in
neither, so a pass that raised timeout_s alone would have been green everywhere
and wrong on every slow morning.
claim_the_watchdog_outlasts_the_longest_healthy_analyst holds three
inequalities: the watchdog outlasts the silence, the worst case finishes before
the last monitor pass that judges the chain, and it finishes before the open.
Mutation tested both ways: reverting job_log_stale_after_s to 1200 fails it, and
a timeout long enough to push the chain past 09:25 fails it.

Sites corrected in place with markers: the two values, the timeout note's
arithmetic block and its 2026-08-28 paragraph, the liveness note's derivation,
chain_due's inline comment, the enforcing section's worst case, and two places
in BUILD_PLAN.


## 2026-08-28: the three writers artifacts.py named as unprotected, and the loop that proved it

core/artifacts.py exists because a hand run against a past session destroyed
the 2026-08-14 collector snapshot on 2026-08-15, and it was only noticed
because a test happened to read that file. Its docstring then named three
writers still going straight to write_text: analyst.write_report for report.md
and analyst_usage.json, and render_report.render for report.html.

The gap fired during this review. Checking that the markup escaping change had
not altered any archived report, a loop called render_report.render over every
report.md on disk and rewrote twelve past mornings' report.html on the way. The
bodies were identical so nothing was lost. That was luck: the same loop a week
earlier, before the shell last changed, would have replaced twelve frozen
artifacts with output from a different template, and said nothing.

Both writers now resolve through artifacts.resolve against
`overwrite or scheduled_run()`, the pattern snapshot_bars, verify_intraday and
pool_recall already use, and both gain --overwrite. The scheduled path is
unchanged by construction: a .bat sets PMD_JOB, so the morning chain and the
watchdog's rerun still own today's artifacts and replace them, which they have
to, because a rule that spared them would break the schedule rather than
protect it.

analyst.write_report resolves ONCE, up front, and reuses the destination for
every write. It writes report.md twice on the path where containment examined
nothing, and resolving per write would spare the original on the first write
and then spare the SPARED FILE on the second, leaving the real output two
infixes deep. analyst_usage.json is resolved separately rather than derived
from the report's name: they are two artifacts and either can exist without the
other, since a morning whose analyst died between them leaves exactly that.

claim_the_narrative_writers_spare_artifacts_too holds all three states: a hand
run spares the frozen file and lands beside it, --overwrite replaces it, and a
run with PMD_JOB set replaces it. Mutation tested.

## 2026-08-28: the universe covered four exchanges while the file named two

[Universe] exchanges reads "NYSE, NASDAQ". universe.py used it to choose which
symbol lists to REQUEST and then admitted every Common Stock row either list
returned, whatever venue the row itself named.

The vendor's NYSE list is not only NYSE. Measured 2026-08-28 across both lists:
2,365 Common Stock rows on NYSE splitting 2,322 NYSE, 27 NYSE ARCA and 16 NYSE
MKT, and 3,693 clean rows on NASDAQ. Three of the 43 off venue rows cleared the
price, cap and volume floors into the 2,771 name file: PHYS, PSLV and VZLA.

Two of the three are the second half of the finding. Sprott Physical Gold Trust
and Sprott Physical Silver are closed end commodity trusts, which is exactly
what allowed_security_type exists to exclude, and they are in the universe
because the vendor TYPES them Common Stock. A type filter cannot catch a vendor
mistyping and was never going to; the exchange key catches both for nothing.
The third, VZLA, is a real mining company on NYSE MKT and is dropped because
the key does not name that venue, which is the key's job rather than a defect.

The row's own Exchange field is now matched against the key. A row whose field
is EMPTY is kept and attributed to the list it came from: that list is a
configured exchange by construction, and dropping it would empty the universe
on a vendor that stops populating the column. Every drop is counted PER VENUE
into the build notes and printed, because the failure this could hide is the
vendor relabelling NYSE itself, which would drop every row and leave
min_count_fraction_of_previous and expected_count_min refusing the build with
nothing saying why.

CRITERIA gains an exchange coverage note saying that adding NYSE ARCA or NYSE
MKT to the key is what admits them, which is the whole change and belongs
there rather than in code.

Not retroactive. universe.json is rebuilt on the Sunday 21:00 pass, so the
current file still carries all three names until then.

Found while reviewing what the last pass had not read, by checking the built
file against every rule in [Universe] rather than by reading universe.py. The
price, market cap and dollar volume rules all held on all 2,771 rows, no
duplicate codes, no missing names or caps, and nothing ETF shaped survived the
type filter. The exchange key was the only one the file disagreed with.

## 2026-08-28: a vendor headline could write markup into the archive

Python-Markdown passes raw HTML through by design and dropped safe_mode in
3.0, so every character of report.md reached the page as markup. The report is
not all first party text: vendor news headlines are quoted into it verbatim,
from a feed nobody here controls, and they land in Premarket gappers and in
Skips and traps.

The consequence that matters is the archive rather than the single report.
build_archive wraps each morning in `<section class="day" id="day-DATE"
hidden>` and switches days with a script, so a headline carrying a section
close ends that day early and takes the other eleven mornings on the page with
it. A headline carrying a script tag runs when the file is opened, and the
archive is a double click file rather than a served page, so there is no origin
to constrain it.

Neither is likely from a real newswire. Both are the ordinary consequence of
putting third party text into a document with passthrough on, which is the
same reasoning that made the collector scrub its token out of exception text
before printing it into a log that sits on disk for months.

render_report gains to_html, THE one place markdown is rendered, which
neutralises a `<` that begins something tag shaped before handing the text to
markdown. Only the tag shaped one: "guidance < consensus" is left for markdown
to escape as it already did, and `>` is not matched at all so blockquotes are
untouched. The title is html.escape'd separately, because it goes into an
element that does not parse markup and a bare `<` there ends the element and
turns the rest of the line into body.

build_archive was calling markdown.markdown itself with render_report's
extension list. The two therefore agreed on extensions and would not have
agreed on this, and the archive is the last file that should have had its own
renderer. It now calls to_html, and a claim refuses a second markdown.markdown
in that module.

Nothing legitimate is taken away, checked rather than assumed: no archived
report contains a raw tag, an autolink or a fenced block, and neither
REPORT_TEMPLATE.md nor prompt_analyst.md asks for HTML. All twelve report
bodies render byte identical under the old and the new path.

One wart, recorded rather than hidden: inside an inline code span, `<b>` now
renders as &lt;b> because markdown escapes the ampersand this produces. No
report uses a code span at all, and the alternative is passthrough.

## 2026-08-28: a 10-Q would have cost the whole morning

The containment tokenizer's third false ticker of the same family, found by
firing ordinary financial prose at it rather than by reading it.

_ABBREVIATION_RE was written on 2026-08-20 for "S&P", "P/E", "U.S." and "R&D",
after those took apart into P, S, U, E, D, every one of them a real listing.
That fix requires every piece of an abbreviation to START WITH A LETTER, so it
never saw a designator whose pieces are digits and whose separator is a hyphen.
_TOKEN_RE then took the bare capital out of each:

  "A 10-Q is due next week."                   -> Q
  "A Form S-1 was filed for the IPO."          -> S
  "The Fed's H.4.1 release is out Thursday."   -> H

Q, S and H are all in universe.json. Measured by injecting one sentence at a
time into the real 2026-08-28 report and checking it against the real
2026-08-28 packet: the 10-Q sentence invented Q and the H.4.1 sentence invented
H. The S-1 sentence claimed S and escaped only because that packet happens to
carry a bare S somewhere, which is luck rather than safety and is exactly how
2026-08-18 escaped the S&P case.

The consequence is the whole morning, not one bad claim. check_report exits 2
on an invented ticker, and the chain's "if %RC% neq 0 exit /b %RC%" then skips
render, verify, deliver and archive. A report saying "a 10-Q is due next week",
which is ordinary prose for a catalyst note, would have produced no HTML, no
gate table and no archive entry.

_DESIGNATOR_RE blanks letters bound to digits by a hyphen or a dot, in either
order, before the abbreviation pass. The letter run is capped at TWO for the
letter led form on purpose: that covers every real designator, S-1, F-1, A-1,
H.4.1, and leaves a three letter ticker followed by a hyphen and a digit alone,
so "SPY-1" is still a claim about SPY. The digit led form needs no such cap
because nothing in the universe starts with a digit.

Checked in both directions and against the record. Six designator sentences now
produce no ticker claim and six ordinary sentences keep theirs, including the
three letter hyphen digit case. All twelve archived reports were re-checked
against their own packets under the new tokenizer: no invented tickers and the
prose claim counts unchanged on every one, 33 of 33 identical on today's.
Blanking too much would be a ticker claim silently unchecked, which is the
failure this guard exists to prevent, so the claim asserts that half too.

## 2026-08-28: the true premarket gap was three causes reported as one

backfill_premarket writes pm_high_true, pm_low_true and pm_vwap_true over
04:00 to [backfill] market_open, 09:30, beside the morning's collector values.
Its docstring called the difference "the standing measurement of what a 07:20
collector start misses". It is not one thing. It is three:

  1. the collector's late start, 04:00 to 07:20, the cause the sentence named
  2. the vendor's bars and the trades socket disagreeing over minutes BOTH of
     them watched
  3. the stretch after the scan cutoff, 08:45 to 09:30, which no report
     written at 08:45 could ever have contained and which is therefore not
     something the collector missed at all

Measured on 2026-08-20 by splitting the same bars three ways, four names and
three different dominant causes. AAP's true high of 58.00 against a live 48.34
is 17.25 percent feed and 2.33 percent window. WMT's 116.695 against 108.00 is
8.05 percent feed and 0.00 window: the whole of it came from minutes the
collector was listening to. SCSC's 64.85 against 59.82 is 0.30 feed and 8.08
window, entirely the stretch after the cutoff. BABA's is 2.55 and 1.99. The
cause the sentence named is the smaller half on three of the four.

night/true_volume.py had already reasoned this out for volume, and ends its
window at the packet's own rvol_cutoff_hhmm precisely because "a truth measured
over a wider window than the estimate is too large by whatever the extra
minutes carried, and that error looks exactly like the socket missing more of
the tape, which is the thing being measured". This module predates that and
never got it.

_true_path now computes the path TWICE over the same fetched bars, once over
the full premarket session and once over the collector's own window, at no
extra call because the second is a subset of the first. picks gains
pm_high_collector_window, pm_low_collector_window, pm_vwap_collector_window,
pm_collector_window_bars and pm_collector_window, the last carrying the window
actually compared rather than leaving a reader to assume 08:45. The end comes
from the packet's rvol_cutoff_hhmm where the packet survives, falling back to
the scheduled [Scan] run_time where it does not, unlike true_volume which
refuses outright: there the comparison IS the output, here the full session
columns do not need the packet at all.

The nightly's gap report now prints the split, and prints it only over rows
that carry the new column, saying how many that is. Rows written before today
have no collector window and are not refilled, and reporting the split over
them with the missing half read as zero would be the absence dressed as a
measurement this project keeps finding. On the 61 rows currently on disk it
correctly reports 0 of 61 splittable.

A collector window that carried no bar reports a null high with a zero bar
count, never a zero high. claim_the_true_premarket_gap_separates_the_feed_from_the_window
pins the bounds, the single fetch, the recorded window text and the empty
window case; mutation tested by widening the window filter.

What this does NOT settle: which of the two halves the collector's feed gap
belongs to in cause terms. A median feed half above zero says the socket
reports a lower high than the vendor over shared minutes, which is the same
direction as the known volume under capture in COLLECTOR_VOLUME.md, and
whether it is one phenomenon or two is not answered here.

## 2026-08-28: the night divided by floats the morning refuses

night/true_volume.py exists to write what was TRUE beside what the morning
ESTIMATED, so a reader can compare the two columns. It computed
pm_float_rotation_true as `if share_float: true_volume / float(share_float)`,
with none of the four refusals scan.attach_float_rotation applies to the same
vendor field: no float, a negative sharesOutstanding, a float above its
outstanding, a float implausibly small against it, and the absolute share
floor where there is no usable cross check.

So a float the morning refused as a vendor artifact came back from the night
with a rotation sitting beside the morning's null. The comparison then reads
as the night measuring something the morning could not, when both had the same
bad denominator and only one of them noticed. Rotation is volume over float, so
an unchecked fabricated float of a few thousand shares does not produce a
slightly wrong number: it produces a very large one, in the column a reader is
being invited to trust over the estimate.

UNFIRED ON THE RECORD, and said plainly rather than dressed up. All 100
candidate floats in the packets on disk are valid under both rules, so no
published pm_float_rotation_true is wrong today. It is fixed because the checks
exist for a reason, YPF at 0.013 percent of its own outstanding having been
found in the 1,785 name sweep of 2026-08-16, and because a latent disagreement
between two renderers of one quantity is the same class of defect the sweep
earlier the same day found between the narrative and the plain table.

true_volume gains usable_float, carrying the four refusals and a reason for
each, plus the _as_float coercion the rule needs so a malformed quote field
cannot raise inside a night job. A refused float now writes a null rotation
WITH its reason into truth_reason on the module's existing first wins
convention, rather than a null nobody can tell from a pass that never reached
the row. sharesOutstanding is read from the packet alongside sharesFloat,
which it was not before: three of the four refusals are cross checks against
it, so reading the float alone was not a shortcut, it was most of the rule
missing.

Not imported from scan. Importing it would pull discover, universe, vintage,
baseline and the collector into a night job that needs none of them, so the
rule is spelled out the way measure_baseline_floor spells out
baseline.compute's window. claim_the_night_refuses_the_floats_the_morning_refuses
drives scan's REAL function over ten quote shapes, one per branch plus the two
that pass, and holds that the two agree on every one and that each refusal
carries a reason on both sides. Mutation tested: disabling any single refusal
in the night fails it.

## 2026-08-28: the two report renderers disagreed about whose evidence was partial

Found sweeping the modules the morning review had not read. Not a defect in
what shipped this morning, but one that arming the quantifier guard the same
day made reachable.

analyst.fallback_report, the deterministic plain table, marks a candidate's
premarket levels "(partial)" on `pm_window_starts_late OR NOT
collector_covered`. evidence_roll, added earlier today for the narrative to
quote, carried only the first half. Two renderers of one morning would then
name different sets of names as the ones a reader should distrust, and the
plain table stopped being a theoretical path this morning: it is what a twice
flagged narrative degrades to under enforcing.

The second half is not dead code. drop_uncovered splits on
`price is not None` and NOT on collector_covered, while collector_covered is
`bool(bars) and on_watchlist`. So a name the collector HEARD that is not on
today's watchlist keeps its price, survives the drop, and reaches the report
with collector_covered false. Checked against every packet on disk: WDAY did
it on 2026-08-13 and AAPL on 2026-08-21, 2 of the 12 mornings. A subscription
list that does not match the watchlist is the ordinary way to produce it, and
that is a failure this project has already had after a power outage.

evidence_roll gains coverage_absent, kept as its own list rather than folded
into window_starts_late because the two are different facts and the sentences
differ: a late window is partial path evidence, and no coverage at all is
ABSENT path evidence, where any level published rests on something other than
this morning's tape. The template quotes it as a fifth line in Skips and traps.

claim_the_roll_and_the_fallback_agree_on_partial_evidence holds that the union
of the two lists is exactly what the fallback marks, and spells the fallback's
predicate out rather than importing it: re-deriving it from the function under
test would make the claim agree with itself instead of with the report. Both
new claims mutation tested.

Also in this pass, and all cosmetic: a try/except in scan.main that caught
StaleUniverseError only to re-raise it, which read as though something was
handled; an f-string with nothing to interpolate in discover; an unused
ettime import in backup_evidence; and a `\s` in a test_regressions docstring
that raised a SyntaxWarning on every suite run and is now a raw string.

What the sweep did NOT find, recorded so the next reader does not repeat it:
no mutable default arguments anywhere, no bare except, no swallowed exception
on a scheduled path, and no CRITERIA key read by any module that the file does
not define, checked by walking every _CRIT reader call in the tree against the
parsed sections. The hand rolled ET fallback was verified against the real
transition instants for 2025 to 2028: both boundaries land on the right UTC
instant, the offsets flip correctly either side, and the November repeated
hour produces 01:00, 01:30, 01:00 fold=1, 01:30 fold=1, 02:00 rather than
02:00 twice.

## 2026-08-28: the RVOL denominator floor is measured for the first time, and says 1000 is low

Prompted by CHA publishing a premarket RVOL of 316.1 on a baseline median of
1,077.5 shares, which cleared [Baseline] min_baseline_premarket_volume by 77
shares and took the maximum 2 points from [Score premarket rvol], the same 2
that BWLP took at 3.36.

The floor note has said since 2026-08-14 that the floor exists so a denominator
cannot max the RVOL band "by construction rather than by evidence", and in the
same paragraph that it is a seed and nothing has been measured against it. Both
were true. The second is no longer.

**The measurement.** src/research/measure_baseline_floor.py, new. For each of
the 241 names holding a cached 08:45 baseline, refetch the same 20 sessions
over the same 04:00 window the baseline is built from, and divide every one of
those ORDINARY sessions by the median of the set it belongs to. What share of a
name's own ordinary mornings would score above 3, the top band, against its own
median? Half of any set is above its own median by construction, so this reads
the right tail. 241 intraday calls, 239 names with a non zero median, payload
in doc/research/baseline_floor_study-2026-08-28.json with the raw per session
volumes so it reruns offline.

| baseline median | names | ordinary sessions above 3x their own median |
| --- | ---: | ---: |
| 0 to 1,000 | 46 | 30% |
| 1,000 to 2,000 | 13 | 20% |
| 2,000 to 5,000 | 30 | 20% |
| 5,000 to 10,000 | 19 | 15% |
| 10,000 to 25,000 | 25 | 15% |
| 25,000 to 100,000 | 37 | 10% |
| 100,000 and up | 69 | 5% |

Monotonic. The floor is real and points the right way: it removes the 30
percent band, which is where ARX at 23.5 shares and MH at 10 came from. It is
also too low for the claim made about it. Just over it, one ordinary session in
five reaches the top band, against one in twenty for the largest names.

Not hypothetical: 25 of the 80 premarket RVOLs ever published stood on a median
under 10,000 shares, 14 of them since the floor was added. DKS 514.0 on 1,085.
CHA 316.1 on 1,078. KSS 191.1 on 1,944. PLAB 70.7 on 4,135. DQ 53.6 on 1,198.

**The floor did not move.** Reasoning in DECISIONS.md. In short: a name the
floor refuses is not dropped, it is rescued onto [Score premarket float
rotation], and those edges were fitted on 2026-08-16 against the population the
CURRENT floor rescues. Raising the floor rescues more liquid names whose
rotations sit higher, so the existing edges would pay them MORE than the RVOL
bands would have. The change meant to stop a thin name maxing a band would hand
it the band through the other door. Floor and edges move together or not at
all, and that is a study rather than an edit.

**What did change**, and it costs nothing: [Baseline]
thin_baseline_premarket_volume = 10000, disclosure only. It refuses nothing,
screens nothing out and moves nobody onto the rotation path. A published RVOL
resting between the floor and this line is NAMED in gaps_to_fill with the
median it rests on, the way _gap_for_stale_baselines already names a
denominator that was not computed this morning, and for the identical reason:
the report was setting a 1,078 share denominator beside a 740,086 share one
with nothing to tell them apart. 10,000 is where the table stops improving.

On this morning's packet the new gap names CHA on a 1,078 share median, BWLP on
4,876 and MNSO on 6,276.

## 2026-08-28: the two unusualness lists were ranking on the sign, and published the quietest names on a morning of decliners

Found reviewing the 2026-08-28 morning. The report ran clean end to end: nine
steps green, 0 problems from the watchdog, 25 EODHD calls, containment passed
on 33 ticker claims, and every number in it reconciles against packet.json.
The defect is not in what the report SAID, it is in what reached it.

The notable movers section ranks four lists. List 3 takes the size of the two
session move, `abs(...)`, and has since mutation testing found it ranking on
the signed value and losing every large decliner. Lists 1 and 4 rank on
move_sigma and were still taking the SIGNED sigma, so they published the five
largest risers and no faller could reach either of them however unusual it
was. BUILD_PLAN 4.4 said "move_sigma descending" for both and "absolute" only
for list 3; the sign was never considered for the other two.

What it cost, measured rather than asserted:

- 2026-08-28 premarket list: published FRO 0.26, BTQ 0.09, ORCL 0.09, NOK
  -0.02, SOUN -0.05, while MNSO sat on the same leg at -2.51, CHA at -2.10,
  BWLP at -1.84 and MRVL at -1.19. The section whose first sentence is "these
  names were selected for the size and unusualness of their move" published
  the five quietest names on the leg.
- 2026-08-28 prior session list: dropped HRL at -8.00 sigma, the second most
  unusual move in the whole 2,769 name universe, to publish VEEV at +6.04.
- Across the five mornings the premarket list has run, it lost the leg's
  largest move on three of them: 2026-08-25 published 0.77 against a 6.82 on
  the leg, 2026-08-27 published 3.01 against 4.60, 2026-08-28 published 0.26
  against 2.51. The two it got right, 2026-08-24 and 2026-08-26, were mornings
  whose largest premarket move happened to be UP.

A second symptom had been visible for a week and was read as normal. The
`also_on_watchlist` column has been "not screened" on every row of every
morning, while _watchlist_mark's own docstring says "expect most premarket
rows to carry a mark, since that leg draws from the pool the watchlist came
from". The mark was empty because the ranking could not reach the candidates,
not because the two sections disagree.

Fixed by taking `abs()` on both keys, which is what list 3 already does. The
rows keep the signed sigma, so the direction stays on the page and only the
ordering changed. BUILD_PLAN 4.4 points 1 and 4 are corrected in place with
markers.

Why no claim caught it: the fixture's only faller, DOWN, sits on the universe
legs and is not subscribed, so both subscribed names moved up and the signed
and size orderings agreed on list 4 on every run. On list 1 the fixture DID
carry the discriminating case, DOWN at -45 sigma, and the claim asserted the
buggy answer, that list 1 leads with QUIET at +2.0. That claim now asserts
DOWN and a second one holds that QUIET is on the list while LOUD at 0.8 is
not, so the sigma key is still told apart from the raw move. List 4 gets a new
claim with its own two name leg where the two orderings disagree. Both were
mutation tested: reverting either `abs()` fails the suite.

Not regenerated. runs/2026-08-28/ is the record of what ran this morning and
the archive is built from it; the fix applies from the next morning.

## 2026-08-26: the capture spread was mostly a late collector, and the probe is retired

probe_capture_live's second sweep, armed because the first ran against a
collector that started at 08:09 instead of 07:20. Both questions answered, no
code changed, no threshold moved.

The free tier serves a live premarket session behind the documented lag and
refuses the same window at the wall clock: served on both sessions, control 403
on both. Two independent confirmations.

The capture share measured 0.1298 median over 37 symbols on the clean session,
range 0.0195 to 0.4317, against 0.1172 assumed. The 2026-08-24 reading of
0.0072 to 0.8480 was mostly the missing forty nine minutes, and calling that a
118 fold spread in the tape overstated it. Corrected here rather than left
standing, because it was cited as the finding with consequences. Three
measurements from two methods now bracket the assumed rate at 0.73, 0.83 and
1.11 times, so [Collector] premarket_capture_rate stays where it is. The
remaining 22 fold spread and its direction are unchanged and still unfixed; see
DECISIONS.md for what that does and does not license.

The scheduled task is deleted, its one time trigger having fired. The .bat and
the module are KEPT, unlike the two probes retired on 2026-08-17, because the
capture half of the question improves with sessions while the served or refused
half is closed. tasks/README says so where it lists the probe.

## 2026-08-24, second: five test fixtures were being counted as measurements

data/quantifier-flags.jsonl held seven rows. Five of them were written by the
2026-08-21 15:46 sweep that invoked every claim directly, the same sweep already
on record here for putting 258 fixture bars over roughly 3,200 real ones and 762
bytes over a 125 KB packet. All five carry recorded_at 2026-08-21T15:46:33-04:00,
all five say "Every candidate missed the prior day high.", one carries
disposition_note "test disposition", and one is id 90001 back dated to
2026-08-12, before this project raised its first flag.

**What they cost, which is more than tidiness.** [Monitor]
flag_backlog_after_days is 7 and id 90001 could never age out of it, so the
watchdog reported BACKLOG and exited 1 on EVERY pass, for ever. monitor-night
rc=1 on 2026-08-21 is that, and so is every weekday pass since. A permanent red
is how a real one stops being read.

The second cost is worse in kind. The false positive rate printed "100.0% of 1
judged", and that one judged row was the fixture whose note says it is a test.
A fabricated measurement was being published on the one number the guard's word
list is meant to be tuned on, which is the exact failure the 2026-08-22 review
closed twenty three of.

The five rows were moved to data/purged-quantifier-flags-2026-08-24.jsonl
first, the way the 2026-08-19 picks purge was, and the live file rewritten with
the two real flags: 2026-08-20 08:49:13 and 2026-08-21 08:49:36, both raised by
a scheduled morning chain. The watchdog now reports PENDING with 0 problems, and
the rate line reads "NOT MEASURABLE, nothing judged yet", which is true.

Both surviving flags are still unjudged and the 7 day window puts them past
patience on 2026-08-27. Judging them is a reading of the morning's own prose
against its packet and is deliberately left to a human.

## 2026-08-24: a collector that looked healthy and was listening to the wrong session

A power cut ran 01:00 to 07:49 ET. Nothing was lost to it: every weekday task
carries -StartWhenAvailable and Task Scheduler caught the whole set up at
07:54:58, discover finished clean on 871 pool rows, the 07:00 catch-up ran, and
Sunday's universe rebuild had already succeeded. The morning chain returned 0.

What the catch-up did do is fire discover and the collector in the SAME SECOND,
collapsing the 07:15 to 07:20 gap that normally separates them. The collector
reads the watchlist once, at subscribe time. It read the file discover was in
the middle of replacing, got the previous session's, and select_symbols found
no row in it marked subscribed. An empty list is not an error, so it subscribed
to the eight context tickers and nothing else and ran healthy for fourteen
minutes: `requested_count: 11`, zero of the day's 42 candidates.

**Nothing in the system could see it.** The watchdog restarts a collector that
is DEAD, and this one was alive. `_collector_has_subscribed` read the
subscription list it had written as proof discovery was settled, which closed
the discover rerun gate. Every candidate would have reached the 08:45 scan with
no coverage and been printed as "on the watchlist but the collector recorded no
bars for it", a sentence that reads like a quiet tape. It was caught by hand
and the collector was restarted at 08:09:32 onto the right 50 names, so the
published morning is sound; the sixteen minutes 07:53 to 08:09 are proxies
only, and there is no candidate bar before 08:00.

**Three changes, in three places, because they answer three different
questions.**

`collect_premarket` refuses a watchlist that is not today's and exits
non-zero. This is the fourth hard rule applied to an empty list, which is the
shape two thirds of the 2026-08-22 review turned out to have. The refusal is
also the repair: it writes no subscription list, and that absence is what holds
the watchdog's rerun gate open, so the next pass rebuilds the file and starts
the collector on it. `--snapshot` and `--verify-intraday` return well above the
check and are untouched.

`monitor_jobs` may overrule it, in exactly one branch. Past the last pass that
could rerun discover inside the collector window, CRITERIA already decided that
possibly wrong names beat no tape at all, and an unconditional refusal would
have stranded that window the way the 2026-08-20 hold once did. `launch_bat`
and `maybe_rerun` gained an args passthrough and the branch passes
`stale-watchlist-ok` through `job_collector.bat`. Nothing else passes it, and a
claim holds that the 07:25 pass does not.

`scan` raises a gap when the watchlist is not today's. CRITERIA rested on the
sentence "scan records watchlist_generated_at, so the wrong names case stays
visible in the packet rather than becoming a silent hole". The field was
written at two places in scan.py and read by nothing. Recorded is not visible.
It now goes into gaps_to_fill, which the analyst reads and the report prints,
and it says the part that matters: a candidate with no collector bars is NOT
evidence the tape was quiet.

One claim covers all three and fails against each pre-fix file separately.
CRITERIA gains the stale watchlist note, and the withdrawn sentence is quoted
there rather than deleted.

## 2026-08-22, third: twenty three defects from a twelve reader review, and what they had in common

A twelve reader adversarial review of the whole tree, every finding put to two
independent verifiers, one arguing statically and one driving the code. Sixty
seven filed, twenty nine survived both, twenty three are closed here and each
carries a claim checked against the pre-fix code before it was kept. The suite
is ninety six claims in test_regressions plus twelve other modules, green, tree
photograph clean.

**WHAT THEY HAD IN COMMON, because it is more useful than the list.** Almost
none was a wrong calculation. Two thirds were a MISSING ANSWER PRESENTED AS A
MEASURED ONE: a call that failed reported as a call that came back empty, an
unreadable packet reported as a name that failed a screen, a refused close
reported as a file with nothing in it, a partial sweep reported as this week's
figures. This project's fourth hard rule is that missing evidence stays null
with a recorded reason, and it holds everywhere the evidence is a NUMBER. It
was leaking wherever the missing thing was a BOOLEAN or an EMPTY LIST, because
those have a falsy value that reads as an answer. `earnings_symbols` empty,
`_volume_was_the_only_failure` False, `capture_observed` absent, `rank_stats`
{}: four different modules, one shape.

The rest were writes and reads whose failure mode nobody had asked about, which
is the same pattern the 2026-08-22 second entry closed six of.

**The critical three.**

The collector wrote a settle batch one line at a time and, on a fault partway,
put the WHOLE batch back and said "nothing has been marked written". True of the
bookkeeping, false of the disk. Reproduced at six minutes, nine lines, three
doubled, and read_bars_file does not deduplicate on (symbol, minute), so a
doubled minute doubles that minute in pm_volume, the numerator of both premarket
RVOL and float rotation.

classify_catalyst consults the earnings calendar first and treats it as a fact.
stamp_all built the symbol set from a list that earnings() left empty when the
CALL FAILED, so a name reporting this morning came out as a name not on the
calendar: a different catalyst class, a different score, a different conviction,
a different swing watchlist through require_catalyst.

The truth pass nulled its own measurements. Every record carries the full column
set with the true columns None when Alpaca errored, and store.upsert writes every
key it is handed, so a second pass over a measured session replaced real SIP
volume with NULL and left a truth_reason beside it, which store.py's convention
reads back as "reached this row and could not measure it". A second pass is the
ORDINARY case: the nightly sweeps unmeasured sessions, the catch-up runs the
same step, and --reread walks every session on purpose.

**The rest, in one line each.**

- A restart after a run that died mid write glued the first new bar onto the
  torn fragment, losing both. A newline is written first now.
- One trade timestamp in the wrong unit raised OSError out of the message
  handler into `except (ConnectionError, WebSocketException, OSError)`, so a
  malformed message tore down a healthy socket and resubscribed into a 50 slot
  pool the server is known to refuse.
- _TIME_RE's meridiem and zone had no trailing word boundary: "07:15 AMD" left
  "D" and "16:00 ETSY" left "SY". One sentence hid a real ticker claim from
  containment AND invented one, which analyst.py exits 2 on, stopping the chain.
- A CLI answer that is valid JSON but not an object raised AttributeError past
  both the retry and the fallback report.
- pool_recall measured a dated session against the single undated
  data/watchlist.json. runs/2026-08-21/pool_recall.json is that: recall 0.0
  against 92 addressable gappers, off a three symbol afternoon hand run.
- actual_gappers counted every corporate action as the day's biggest gap,
  inflating the denominators of discovery_recall.
- A gap statistics sweep that died partway wrote a newer as_of that load_all
  then preferred, so 200 names could become the propensity column discover
  orders the whole pool by. [Gap stats] max_unswept_fraction is the new key.
- The weekly cost table subtracted two readings from OPPOSITE SIDES of the
  00:00 UTC quota reset: 11,761 published for a day whose counter moved 66,761.
- rescued_by_truth counted an unreadable packet as a name that failed something
  else. 2026-08-21 published 0 where five rows could not be read at all.
- The malformed line count _read_jsonl computes was filtered out by its only
  consumer, exactly as its docstring promised it would not be.
- An outcome refused for a corporate action left next_day_close null with no
  reason, and the candidate query selects on that null, so the row was
  re-fetched every night forever. picks gains next_day_refused_reason.
- day_blocked_on_rvol_alone asserted a capture correction over candidates whose
  RVOL was never measured.
- A c2 or c3 the vendor stamped with the wrong session lost its leg with the
  sentence for an empty sidecar, sending a reader to the vendor for data that
  arrived and was refused. c1 has named this since the section shipped.
- candidate_provenance.ranking was {} on the zero candidate morning the degrade
  path exists for, while the Summary quotes five of its keys by name.
- mark_notable_watchlist counted "screened, neither", which means the screens
  refused the name for both lists, as a name on a watchlist.
- The stand-down replaced the snapshot the KEPT packet describes, because
  build_packet copied it at the start and main decides at the end.
- The economic block's fallback read only `skipped` while a failed call sets
  `error`.

**Six documents corrected.** .env.example named EODHD as the only provider and
did not mention ALPACA_KEY_ID or ALPACA_SECRET_KEY, which a scheduled step
requires. CRITERIA [Truth] gave capture_observed as pm_volume / pm_volume_true,
which is neither what the code computes nor what should be computed, on the one
number the whole volume floor rests on. README's setup step built the universe
and not the gap statistics that rank it, leaving discovery unable to run.
BUILD_PLAN said probe_alpaca.py is imported by no pipeline module nine lines
after saying the nightly truth pass imports it. tasks/README listed the nightly
as five steps where it runs nine, naming neither the backup nor the only
scheduled deletion in the project. eodhd.py's docstring said "and only these"
over nine of thirteen endpoints, omitting the most expensive one in the tree.

## 2026-08-22, second: six writes and reads that could undo a closed defect

A full review of the tree. Six defects, and five of the six are one shape: a
write that could not complete leaving the file it was protecting worse than it
found it, in a tree that already has the fix written down twice, in
universe.write_atomically and in config.ca_bundle, and applied where each was
noticed rather than where the shape occurs. Every one is pinned by a claim, and
every claim was checked against the pre-fix code before it was kept. The suite
is 81 claims in test_regressions plus twelve other modules, green, tree
photograph clean.

**THE MORNING COULD BE EMAILED TWICE.** deliver.py writes delivered.json after
the send, and already_delivered reads it to refuse a second copy. The write was
a plain write_text, so a denial raised straight out of deliver(): the chain then
stopped before build_archive wrote its finish marker, the watchdog read an
unfinished chain and relaunched it, and the recipients got the morning again.
Reproduced end to end, two POSTs from one report. That needs no exotic failure,
because README already records this machine's antivirus intermittently denying a
first file write. The write now goes through a temp sibling and os.replace,
retries four times, and NEVER raises: it prints that the email went and the
record did not, and declares the step failed so the status trail carries it. The
exit code stays zero on purpose, because a nonzero one is what summons the
second copy. claim_delivery_happens_once gained the case; it had covered a
record present, absent and corrupt, and not a record that could not be written.

**A HALF WRITTEN CALENDAR READS AS AN OPEN MARKET.** get_details' docstring
promises "the old file now stands until a new one is actually in hand", which is
what closed the 2026-08-20 defect where the nightly deleted the cache before
fetching. The write beside it was still a plain write_text, which truncates
before it writes, and _load_cache answers a truncated file and a missing one
identically. So a refresh interrupted between the open and the flush reopened
the closed defect by a shorter route: with no calendar, is_trading_day returns
True for Christmas Day and every weekday job runs against a closed market.
Measured both ways, before and after.
claim_a_half_written_calendar_is_not_a_missing_one.

**THE MORNING'S ONLY EVIDENCE COULD BE LOST TO ONE INTERRUPTED WRITE.**
scan.write_packet wrote packet.json, one of the two files CRITERIA [Backup] says
has no route back, with a plain write_text. An interrupted write left a packet
that parses as nothing; every later step reads it, and thin_rerun_stands_down
reads an unparsable one as "not thinner", so a rerun replaces the 08:45 evidence
with a packet gathered off a different clock. The nightly backup answers this an
hour too late. claim_an_interrupted_packet_write_leaves_no_half_packet.

**A RELAUNCH THE STATE FILE REFUSED TOOK THE WATCHDOG DOWN WITH IT.**
monitor_jobs._record_rerun runs AFTER launch_bat, so its write is the one thing
in the watchdog that cannot be answered by running the pass again. _load_state
already treats an unreadable state file as worth declaring the step failed, on
the stated reasoning that a lost count stops max_reruns_per_job_per_day being
enforced; a failed write left the same state while also raising through the rest
of the pass. Now atomic, retried, reported, and the pass continues.
claim_an_unrecorded_relaunch_is_reported_rather_than_raised.

**THE ARCHIVE HAS BEEN PUBLISHING A FIXTURE AS A MORNING SINCE 2026-08-21.**
site/PremarketDesk.html rendered 2026-08-21 as its seventh session, identical in
the rail and in the pane to the six real ones: one candidate, AAPL at 100.00,
gap +3.1 percent, RVOL 1.8, score 6.0 green, none of it measured from a market.
That the session was destroyed is recorded in three documents; nothing stopped
the page from presenting it. The packet already carried the tell.
config.build_identifier writes a resolved HEAD or null with a commit_reason and
has no third answer, so the "stub" the fixture wrote is a value no version of
this code produces. build_archive now reports it, on the session, in the rail as
"not a morning", in the subtitle count and in the step's log. Matched on the
SHAPE of the commit rather than on the string, because the next fixture will not
be spelled the same. The session is LABELLED, NOT DROPPED: a gap in the rail
reads as a day the market was shut, and this file is the record. The first draft
of the rule accused 2026-08-13 and 2026-08-14, both real mornings written before
the build field existed, and the corrected rule leaves both silences alone.
claim_the_archive_does_not_publish_a_fixture_as_a_morning.

**READING A RUN DIRECTORY CREATED ONE.** config.run_dir mkdirs, which is right
for a caller about to write and wrong for the thirteen that asked it for a path
only to call .is_file() on something inside it. runs/2026-08-15 and
runs/2026-08-16 are a Saturday and a Sunday, deleted on 2026-08-21 as sweep
fixtures and back within hours carrying the 22:15 nightly's mtime, because
weekly_page walks a calendar week and asks each day for its report. So was
runs/2026-05-04, a date this project has never run a morning on. The archive
logged a skip for each, every night, and the deletion looked like it had not
held. A directory under runs/ is what build_archive walks to decide which
mornings exist, so a read that creates one destroys the meaning of what it is
reading. config.run_path is the read only accessor and twelve sites now use it;
backfill_premarket had already worked around this locally, which is the same fix
made once where it was noticed. The three empty directories are removed.
claim_reading_a_run_directory_does_not_create_one.

## 2026-08-22, first: every ranked list says which empty it is, and a surviving price says how old it is

Two changes to Layer 4, the notable movers section. Both are disclosures on
numbers the section already had in hand and was discarding.

**THE RANKED LISTS.** 4.9 makes each LEG tell a quiet market apart from a lost
input, and the four ranked lists inside those legs had been exempt from it since
the section shipped on 2026-08-20. An empty list published one sentence saying
it was "short", with no state and no denominator, and prior_session_by_sigma and
premarket_by_sigma have been empty on every run the section has ever made,
because return_stdev_20d is null on all 10,997 rows of the gap statistics
database until the Sunday 21:00 rebuild computes it. Nothing in the report said
whether that meant the market was quiet or the denominator does not exist yet.

Every list now publishes one of four fixed states with three counts beside it.

| state | what it means | the fix |
| --- | --- | --- |
| `ranked` | the list holds at least one name | none |
| `uncomputable` | an input nobody has produced: the leg's own file was lost, or the column the list ranks on is null on every row the leg carries | compute the input |
| `nothing to rank` | the input arrived and carried nothing for that leg to measure | look at the file |
| `below the floor` | the leg measured rows, the ranking key exists, and not one row reached this list's own floor | none: this is the quiet market |

considered is what the leg measured, qualified is what cleared the list's floor
and carried its ranking key, and selected is what it published, so an empty list
carries its own denominator the way the Summary counts do. On a morning with
return_stdev_20d null the two sigma lists now read, word for word: "The
premarket_by_sigma list is uncomputable: 0 selected of 0 qualified of 39
considered on the premarket leg. 0 of 39 on the premarket leg carry a
move_sigma, which is the key this list ranks on, so it could not be computed. 39
of 39 report: return_stdev_20d is null on a row covering 250 sessions, which is
enough for it, so the column was written before it was computed. The Sunday
21:00 universe rebuild fills it."

Three supporting changes made that possible. `_leg_report` gained
`input_present`, because a leg comes back unavailable both when its file was
missing and when its file was read and held nothing for it, and until now those
two collapsed into one empty. Each list's funnel is measured in two stages
rather than one, so "0 cleared the floor" and "0 carry the ranking key" are
separate answers. And the whole sentence is assembled once, in
`scan._list_report_text`, then quoted word for word by REPORT_TEMPLATE.md and by
fallback_report, so the two renderers cannot say different things about one
list. `list_reasons` stays in the packet and is DERIVED from the new reports,
because the template and the archive have read it since the section shipped.

**THE PRICE AGE.** The premarket leg computes each print's age against the scan
clock to apply the [price age] floor, dropped the rows past it, and then threw
the number away. That floor is a CEILING of 900 seconds, so a row that survives
it can still be fifteen minutes behind the scan clock, and the scan clock is not
printed anywhere in the report. A reader holding the bare `price_time` stamp
could not compute the one number that says how stale the published price is.
`price_age_seconds` now travels on the row beside `price_time` and renders as a
`Price age s` column, null on both universe legs where a close has no intraday
age. The notable table header is ten columns, was nine, and is pinned in
REPORT_TEMPLATE.md and analyst.NOTABLE_HEADER as before.

Every new string was run through the drift walk before it shipped, per the T17
lesson: the template tells the model to quote these word for word and
analyst.quantifier_violations then scans the model's output, so a state spelled
"none cleared the floor" would have put a set quantifier into the model's mouth
on every morning a list was empty. That is why the states read "below the floor"
and "nothing to rank". claim_the_sections_own_words_pass_the_quantifier_guard
gained two fixtures so all four states reach it, and now walks 48 distinct
strings against the 18 it walked yesterday.

Two claims added, so test_notable holds twenty six:
claim_an_empty_list_says_which_empty_it_is reaches all four states across six
fixtures and holds that list_reasons stays derived, and
claim_a_premarket_row_carries_the_age_of_its_price holds the 300 second age on
the row, the null on both universe legs, and the column in the rendered
fallback. The hand written notable block in test_containment now builds its
list reports through scan._list_report_text and asserts the fallback renders
them, because that fixture carried only list_reasons and would have gone on
walking a section whose loudest four sentences had silently stopped being
emitted.

BUILD_PLAN.md corrected in the same pass. Its Layer 4 heading read "specified"
while "What remains" item B in the same file recorded the section as built on
2026-08-20; it now reads BUILT 2026-08-20 and carries a pointer to that item.
Item B said thirteen claims, which was the count on the day it shipped and had
not moved since.

## 2026-08-21, ninth: the two artifacts that cannot be rebuilt are held twice

night/backup_evidence.py copies data/premarket/<date>.jsonl and
runs/<date>/packet.json to CRITERIA [Backup] root, outside the working tree,
dated and write once. It runs FIRST in the nightly, before anything else
touches the tree. It computes nothing, and claim 76 asserts that no module
outside itself reads the backup root: a copy anything depends on is a second
input with a second way to be wrong.

A dated backup is never overwritten. A working copy that no longer matches is
reported as a DISAGREEMENT and neither file is touched, because a stale backup
and a corrupted working copy are the same observation from inside the module.
Had it been running, the 22:15 pass on 2026-08-21 would have named that
morning's destroyed capture the same night rather than it surfacing a day later
through three unrelated failing checks.

**WHICH SESSIONS ARE HELD, so the gap is a known range rather than a
discovery.**

| sessions | held | note |
| --- | --- | --- |
| before 2026-08-13 | NO | predates the project's own history; no capture exists |
| 2026-08-13 to 2026-08-20 | YES | six sessions, captures and packets intact, first copy taken 2026-08-21 |
| 2026-08-21 | copy held, CONTENTS DESTROYED | the capture is 258 fixture bars over roughly 3,200 real ones and the packet is 762 bytes over 125 KB. Backed up because it is what exists, not because it is the tape |
| 2026-08-22 onward | YES, automatically | the nightly takes it |

So the gap is exactly one session, 2026-08-21, and it is not a gap in coverage
but a loss that predates coverage by one day. catchup_sessions is 10, so a
night the machine is off is caught up rather than lost.

Restore is `python -m night.backup_evidence --restore YYYY-MM-DD`. It refuses a
working copy that already matches and refuses one that differs unless forced,
and it spends no vendor call. Verified by deleting a working file and restoring
it byte identical.

## 2026-08-21, eighth: the true volume, the weekly page, and the freeze

night/true_volume.py writes pm_volume_true, pm_rvol_true,
pm_float_rotation_true, capture_observed, estimate_error and
collector_window_share into picks from Alpaca full SIP, over the same window
the morning used, beside the morning's numbers and never over them. Two
sessions measured: the capture share ran 0.0288 to 0.4231, a spread of over ten
fold in each session, against the single 0.1172 the morning divides by, and
every 2026-08-21 row was understated by between 1.3 and 19 times. Ten of twelve
candidates on 2026-08-20 cleared the day screen's volume floor on the true
numbers against an empty published watchlist.

capture_observed divides by the COLLECTOR'S window, not the premarket window:
the first version folded the 07:20 start into a number meant to measure the
feed. collector_window_share carries that second shortfall and measures it for
the first time at a median 0.2887 to 0.5228 of the tape.

The report now names the estimate as an estimate. REPORT_TEMPLATE,
prompt_analyst rule 6 and fallback_report all require the disclaimer to give
the capture share used, whether it was the symbol's own or the file wide
default, and that the true figure lands that night.

night/weekly_page.py renders site/Weekly.html from job-status.jsonl, the meter
trail, quantifier-flags.jsonl, verify_intraday and picks. Four sections: did it
run, is the data trustworthy, what did it publish, what did it cost. It reads
and renders, takes no vendor call, adds no table and no measurement.

CRITERIA gains a [Truth] section with six keys and three notes, plus truth and
weekly under [Job status steps]. picks gains eighteen columns. Claims 73 and 74
hold the truth pass and the page; claim 73 also rebinds DB_PATH after an
earlier version, run outside run_tests, wrote fixture rows into the live table
and nulled a real session's truth columns. Eleven mutations, eleven caught,
after the harness itself was corrected for scoring a suite crash as a pass.

DECISIONS carries the freeze: 42,949 lines of Python, 14,869 of documentation,
4,533 in scan.py, 260 thresholds for a five condition screen. A change is in
scope if it makes a published number wrong or the record readable. Everything
else waits for the outcome rows.

## 2026-08-21, seventh: data/ is 35 MB instead of 145, and stops growing unwatched

data/backtest/bars, vwap_gappers_trades.csv and alpaca_assets.json deleted on
the owner's instruction: 109.9 MB, every byte of it input or output of the VWAP
gappers study, whose pre-registered stop rule fired. doc/research/
VWAP_GAPPERS.md keeps all 748 lines of results and now records the deletion and
its cost, which is that the study can no longer be rerun offline.
vwap_gappers.py stays and prints what happened to its cache instead of
reporting it as symbols that failed to fetch.

night/prune_data.py is new and is the first thing in this project that deletes
on a schedule. It runs in the nightly after pool recall, and it deletes only
what its PRUNABLE whitelist names, which is universe-closes-<date>.json past
CRITERIA [Universe] closes_retention_days, 7. The age is read from the filename
rather than the mtime. It reports what it kept as well as what it took, and
names the directories it never examined.

CRITERIA gains closes_retention_days, the closes retention note explaining why
premarket/, backtest/eod, backtest/sessions and runs/ are deliberately not
prunable, and a prune entry under [Job status steps] so the monitor can report
it overdue. job_nightly.bat runs the step; test_entrypoints drives it.

Claim 72 puts an ancient file of every non whitelisted kind in front of the
prune and requires it to survive, sets the mtimes to contradict the filenames
on both sides, and asserts a second run is a no-op because the monitor reruns
the nightly. Suite 2,441 paths.

## 2026-08-21, sixth: the probe's off exchange answer, and the cap reading it never had

The 06:30 socket cap probe ran on a premarket tape. Its census came back
unanimous: all 123 trade messages carried c=[], an empty condition list, and
dp=False. There is no condition code for the parser to be missing, so the
trades stream omits off exchange volume rather than mislabelling it, no
collector change reaches the shortfall, and the capture calibration is the
whole answer. BUILD_PLAN item A's fork closes on the structural side.

Its cap reading is withdrawn, and so is 2026-08-19's. The premarket run printed
a median B/A of 0.58 off 123 messages, where no symbol reached 20 messages on
both arms and IWM's 0.14 was 49 against 9. The 2026-08-19 run printed 0.87 off
8,056 messages, and recomputing each symbol per cycle on that same payload the
well measured symbols moved by a factor of 2.4 with nothing about the cap
changing, against an effect of 1.15. "The cap is innocent" is unchanged: it
rests on fifty symbols at fourteen times the collector's rate losing none, and
on the vendor comparison holding at both subscription sizes.

CRITERIA [Collector] gains min_probe_messages_per_arm at 20 with the derivation
in a new probe evidence note. probe_socket_cap prints raw message counts beside
every rate, computes its own noise from the cycles it already runs, refuses a
median inside that noise, and writes both refusals into the payload.
_report_delivery is lifted out of main() so an archived payload can be re-read
with no socket, which is how both runs above were re-read.

Three stale definitions of the RVOL numerator are corrected: CRITERIA
[Day setup] premarket_rvol, attach_premarket_rvol and attach_float_rotation all
still called it collector premarket volume a day after both functions began
dividing the consolidated estimate. Claim 68 now holds all three.

Claim 71 holds the probe refusals, with fixtures taken from the two runs that
actually happened rather than derived from the floor, after the first version
ran GREEN under a floor set to zero because the fixture moved with it. Nine
mutations, nine caught. Suite 2,424 paths.

## 2026-08-21, fifth: the first live morning audited, and four defects in the correction closed

The correction ran at 08:45 and produced six day eligible candidates where every
previous morning produced none. A six reader audit of that run raised sixty four
findings; ten survived three independent refutations each.

The packet told the model to apply the correction a second time. volume_check,
the packet key comment, rvol_only_day_failures, the fallback report and
REPORT_TEMPLATE all still said the ratios understate by the feed gap that
attach_capture_estimate divides out, and this morning's report published that
twice beside a table of already corrected values. All five now describe the
check as the correction's input, and name the residual as the share's session to
session dispersion rather than its level.

The gate table stopped reconciling. verify_morning printed pm_volume, baseline
median and pm_rvol, which used to divide exactly and stopped when the numerator
became an estimate. It prints socket volume, capture share, estimate and
baseline median now, plus the basis for each share, so both divisions can be
done by hand on the page.

A capture share could rest on ten shares over one minute. CRITERIA gains
[Collector] min_capture_vendor_volume at 2,000 and min_capture_minutes at 3, and
a share at or above 1.0 is refused as impossible at any volume. Below a floor
the symbol takes the measured default and records which refusal sent it there.

carried_across_the_floor was reported as day watchlist membership; HOOD cleared
the volume floor, failed the prior day high, and was named under the day table.
There are two sets now and only the second is membership.

Claims 69 and 70 hold the thin share refusals and the no double count property.
Eleven mutations, eleven caught, after one ran green because the claim built the
packet by hand instead of calling capture_correction_report. Suite 2,407 paths.

## 2026-08-21, fourth: both volume ratios are corrected onto one tape

On the owner's instruction, after the measurement in the entry below.

premarket RVOL and premarket float rotation now divide pm_volume_consolidated,
the socket's shares divided by the symbol's measured share of the consolidated
tape, rather than the socket's shares themselves. Both denominators are whole
tape measurements, so both ratios were understating by about nine times and
[Day setup] premarket_rvol > 1.5 was being applied to a number that could not
reach it.

pm_volume is unchanged and still holds what the collector saw. The estimate is
a separate field and every candidate records the share used and whether it came
from its own measurement or from CRITERIA [Collector] premarket_capture_rate,
a new key at 0.1172 with its derivation in the capture rate note.

Replayed on the archived packets: 2026-08-20 produces six day eligible
candidates where it published none, FUTU, MSTR, ASST, BLSH, COIN and MARA, and
2026-08-18 produces five, KLAR, FN, HSAI, BIDU and VNET.

No threshold moved. The floor is still 1.5 and the rotation bands are still
0.00033 and 0.00014. What changed is the units of the numerator.

This answers DECISIONS 2026-08-17 seventh, which recorded the rotation bands
being fitted on Alpaca volume and applied to collector volume: the numerator is
consolidated now, over the same window the study used.

The packet carries capture_correction with the raw ratio beside the corrected
one and the names the correction carried across the floor, the template puts a
sentence under the day table saying the column is an estimate, and the fallback
report says it too. Seven mutations, seven caught, after two ran green against
the first version of the claim: one checked arithmetic the test had written
itself, and one validated CRITERIA against CRITERIA. Suite 2,374 paths.

## 2026-08-21, third: the per symbol capture rate is kept, and the RVOL numerator is named as a second tape

verify_against_intraday computed a per symbol collector volume and vendor
volume on every session it ever ran and persisted neither. It keeps
volume_by_symbol now, at no vendor cost, and the six collected sessions were
re-measured to backfill it: 297 intraday calls, doc/research/collector-capture.json.

What that answers, which no reading before it could. Not why the socket
disagrees with the vendor, but whether it disagrees by a STABLE amount, because
only a stable share can be divided back out of a numerator. Over the four
sessions from 2026-08-17 the aggregate sits between 0.086 and 0.103, and per
symbol the median spread across sessions is 1.48 times with 18 of 25 symbols
inside two. The two earlier sessions are a different regime, 1.49 and 3.83
times the vendor, and averaging them with the rest is what made the instrument
look chaotic.

What it costs. pm_rvol divides collector socket volume by a baseline built from
the vendor's intraday bars. Six mornings, 62 candidates, zero day eligible ever,
19 failing on the RVOL line alone. Corrected per symbol, 2026-08-20 produces six
names that clear every line of the day screen: FUTU, MSTR, ASST, BLSH, COIN,
MARA.

scan.rvol_capture_adjusted publishes the adjusted number and those names into
the packet and the gaps and CHANGES NO DECISION. day_eligible is untouched, and
claim 68 fails if an edit makes it touch one: correcting a live screen is a
threshold question and is the owner's. What this changes is that the gate table
data/UNVERIFIED asks a human to read now says whether an empty day watchlist is
an instrument reading or a quiet market.

Six mutations against claim 68, six caught, after the first fixture gave a
symbol the same capture rate as the session aggregate and could not tell the
two code paths apart. Suite 2,359 paths.

## 2026-08-21, second: the study measures the eligibility floor it was never asked to

float_rotation_study now reports mapping_transfer.<slice>.day_setup_eligibility:
the share of the paired population that CRITERIA [Day setup] premarket_rvol
admits, and the rotation value admitting the same share of the rescued names.
It reads both floors from CRITERIA rather than from constants, so it re-derives
if either moves.

Why it is there. The eligibility question has been open since 2026-08-16 and
had a dated counterexample from 2026-08-18, AS.US, which cleared every other
line of the day screen and failed on a null RVOL alone. It stayed open because
it is a threshold and nobody had measured what the threshold would be. The
answer on the top 12 by gap is 0.00014, which is the rotation one point scoring
edge, because [Day setup]'s `> 1.5` and [Score premarket rvol]'s `>= 1.5` are
one threshold written twice. Adopting the floor would introduce no new number.

Nothing in the screens changed. Re-fitting the bands was applying a procedure
CRITERIA names; adding a rotation line to [Day setup] is a new screen condition
that changes which names a human is shown as tradeable, and that is the
owner's. DECISIONS 2026-08-21 carries the measurement, what it would have
admitted across the six archived packets, which is one name, and the one line
that adopts it.

Also recorded there: the section's defence of ranking the signed sigma on lists
1 and 4 was that list 3 catches the fallers. Measured against the three closes
sidecars on disk, list 3 catches the single most unusual faller on two of three
days and two of fifteen top faller slots overall. That entry is corrected in
place and carries a recommendation.

## 2026-08-21: the universe keeps the name the vendor sends, and the two implausible caps were real

The universe build read Type off each exchange-symbol-list row to filter and
Exchange to keep, and discarded the rest of the row. Name and Isin are kept
now, the notable section puts the name on each row, and the report identifies
each ticker in one paragraph under the table.

Why. DECISIONS recorded SPCX at 1.85 trillion and SKHY at 1.18 as implausible
caps wanting a plausibility floor. Three discriminators were measured against
them and all three failed to separate the pair from real megacaps: implied
share count, where SPCX's 13.24 billion sits under NVDA's real 24.18; vendor
self consistency, where cap and sharesOutstanding agree to half a percent; and
realised volatility against cap, where SPCX at 6.58 percent sits beside MU at
6.57. The project's own cached bars corroborate the volume as well. One
exchange-symbol-list call returned Space Exploration Technologies Corp. Class A
Common Stock and SK Hynix Inc. American Depositary Shares. Both caps are right
and the finding was wrong. That entry is corrected in place with the original
argument kept beneath it.

No filter was added, and now for a better reason: a plausibility floor would
have dropped SpaceX and SK Hynix from a list whose job is to surface the
largest names that moved.

Not visible until Sunday. The universe file is rebuilt at 21:00 on 2026-08-23,
so it is the first one carrying names. Until then the section reports that the
file predates the field, once for the table rather than once per row, which is
the distinction instrument_name_reason exists to keep.

Three claims hold it, one per seam: the vendor index, the row assembly, and the
reader. The middle one earned its place. With the other two in place, mutating
the row literal so the name never reached the file left every suite green.
Seven mutations, seven caught. Suite at 2,316 paths.

## 2026-08-20, thirteenth: the rotation bands are re-fitted on the clean population and the edges move

CRITERIA [Score premarket float rotation] goes from 0.0004 and 0.0002 to
0.00033 and 0.00014. The bands are read from that file at runtime, so this is
the whole behaviour change.

Why now. The entry above records that the population both earlier fits were
read off was 36 percent the study's own cold start, and it left the direction
unknown because the archived payloads carry quantiles rather than rows. It
called the re-fit a decision for the owner. That conflated the measurement with
the threshold: the measurement is 463 Alpaca requests against a limit of 200 a
minute, no EODHD quota, three minutes. It was run, and the answer is that the
shipped edges pay two points to 47.89 percent of the rescued names against a
target of 53.72, while the re-derived pair pays 54.21.

What this does to a score. Both edges fall, so a rotation scored name gains a
point or keeps the one it had, and none loses one. The watchlist can grow and
cannot shrink from this.

What else changed with it. round_down answers two significant figures rather
than one, because at 0.00014266 the next figure down is a third of the value
and one figure costs three points of payout accuracy; it also rounds to nine
places before the floor, because 0.0006 scaled by 1e5 is 59.999999999999993 and
a bare floor answered 0.00059. The payload carries rescued_rotation_values, the
rows behind the quantiles, so the next re-fit needs no vendor call at all.
claim_the_shipped_rotation_edges_are_the_ones_the_study_fitted holds the lot:
it re-derives the pair from those rows with its own arithmetic and refuses any
drift between CRITERIA and the archived fit. Suite at 2,302 paths.

Not fixed by this, and named so it is not assumed: DECISIONS 2026-08-17 seventh,
the live numerator being collector volume where the bands are fitted on Alpaca
volume. Lowering the edges moves the same way that bias does. It is not a
correction for it.

## 2026-08-20, twelfth: the closes sidecar records what the vendor sent, and my reason for it was wrong

[corrected 2026-08-20: this entry was titled "check (e) was comparing the
calendar against itself, and now reads a datum" and the whole of its first half
argued that. It is FALSE, it was refuted the same evening by a reviewer whose
grounds I then checked myself, and the text below is rewritten rather than
marked up because almost every sentence of it rested on the error. The change
to the code is kept and is described honestly at the foot of the entry. What I
got wrong is recorded first, because a wrong reason for a right change is how
the next reader talks themselves into the wrong follow up.]

**What I claimed.** That both sides of check (e)'s comparison for the two
universe legs are the same calendar: discover writes sessions.c1 as
previous_trading_session(today), vintage computes sessions_back(today, 1), so no
packet the scan builds could ever fail it.

**Why that is wrong.** They are not the same cached calendar.
ops/market_today.ALLOW_NETWORK is True by default and the only place in the
repository that turns it off is scan.build_packet. Both tasks/job_discover.bat
at 07:15 and tasks/job_morning_chain.bat at 08:45 run `python -m
ops.market_today` as their own network allowed process BEFORE the Python that
matters, and get_details refetches and rewrites data/exchange-details.json
whenever the cache is older than [Calendar] refresh_after_days. So between the
stamp being written and the gate reading it there are two independent refresh
points in two processes ninety minutes apart. Check (e) is a live cross process
comparison.

It kills the trigger twice over. The scenario needed a calendar "a few weeks
old", which is exactly the condition that makes those two guard runs fetch; for
the mis-stamped sidecar to exist at all the 07:15 refresh must have failed, and
if the 08:45 one then succeeds, check (e) fires on every universe row and
enforce stops the chain. That is the opposite of certification. And check (c)
would refuse the same packet in the same call anyway, off prior_session_date,
which the entry never noticed.

**What the change is actually worth, stated without the story.** discover threw
the vendor's own date away and kept only the number, so nothing anywhere in the
chain could say which session the vendor believed it was sending. The sidecar
now records it: vendor_dates, the distinct session dates the ROWS carried, per
session and as a list rather than one value, because a bulk response carrying
two dates is itself the finding. The section refuses to stamp a leg the vendor
contradicts and names both dates. A sidecar written before today carries no such
field and reads as UNKNOWN rather than as agreement.

That is a cross check on the DATA, not on the calendar, and it is narrower than
the entry originally sold. The repository's own observed record is that
eod-bulk-last-day answers a session the calendar says was open with an EMPTY
ARRAY rather than with another session's bars, and discover already returns
before writing on that branch. So this guard may never fire. It is kept because
it costs a set comprehension over rows already in memory, because it also
catches a response mixing two session dates, which nothing else would see, and
because both halves are claimed and mutation tested:
claim_a_close_from_another_session_is_not_stamped_with_this_one holds the reader
and claim_seventeen in test_pool holds the writer. It is not kept because check
(e) needed rescuing. It did not.

## 2026-08-20, twelfth, as originally written, with its first argument now known to be wrong

Kept whole rather than deleted, because the reasoning that turned out to be
wrong is the part worth keeping and because only its FIRST argument is. From
"Everything else in this pass" onward every sentence still stands and is the
record of what the three passes closed; the entry above replaces the paragraphs
before it.

Six adversarial reviewers attacked the Layer 4 build across disjoint
dimensions. This entry is the one finding among their forty five that is about
the GATE rather than about the section, and it is the one worth reading.

**Both universe legs are stamped with sessions.c1, and sessions.c1 is the
calendar.** discover writes it as previous_trading_session(today). vintage
check (e) then validates the stamp by computing sessions_back(today, 1), which
is the same walk over the same cached calendar in the same process. Both sides
of the comparison are the calendar's opinion, so no packet this scan can build
was ever able to fail check (e) on a universe leg, whatever the vendor had
actually sent.

The trigger is ordinary rather than exotic. data/exchange-details.json is a
cache the nightly refreshes and the morning deliberately never fetches, so it
can be weeks old and missing a closure announced since. On the morning after
one: the calendar names Monday, discover buys the end of day bulk for Monday,
the vendor returns Friday's bars, write_universe_closes' close_of kept the
number and threw the row's own date away, and the sidecar recorded Friday's
closes under sessions.c1 = Monday. At 08:45 the section publishes both universe
legs stamped Monday, and every gate in the project is satisfied. vintage.py's
own comment asserts the opposite: "reading the oldest from gap_stats would be
free and wrong, its closes being five sessions old by Friday. Under this one it
fails immediately." It would not have.

**So the sidecar records what the vendor said, beside what the calendar asked
for.** write_universe_closes gains vendor_dates, the distinct session dates the
rows themselves carried, per session and as a list rather than one value,
because a bulk response carrying two dates is itself the finding. The section
refuses to stamp a leg the vendor contradicts, names both dates in the reason,
and treats a sidecar written before today as UNKNOWN rather than as agreement,
which is the honest reading of a file that never recorded it. A c2 or a c3 the
vendor contradicts costs the leg that reads it and not the other one, because a
wrong far end makes the MOVE wrong even where the stamp is right.

It takes effect from the 2026-08-21 07:15 run. Every sidecar on disk today
predates the field.

**Everything else in this pass and the two before it.** Twenty of the forty five
findings survived my own verification and are closed: the critical one, where
the notable_rows evidence axis let a rerun that lost every price, every RVOL and
every score overwrite a full packet because it had gained ten briefing rows;
also_on_watchlist null on every row of every run, because the mark reads
eligibility flags that stamp_all sets after the section is assembled; the
premarket leg republishing collector prints drop_stale_prices had already
refused; five reason strings that would have tripped the quantifier guard the
template tells the model to quote them past; a null move_sigma reason that
asserted "fewer than 20 sessions of returns" for 10,997 rows that are null
because the column was added after the last rebuild; an unreadable gap
statistics table written per row as a fact about each symbol; malformed sidecar
and bar shapes that raised straight out of build_packet; a third session the
vendor never answered for reported as a quiet market; a state name landing in
the Catalyst column; and two comments that were the reason a reader would trust
the code and were wrong.

**And the claims themselves were weak in ways only mutation testing shows.**
claim_no_ranked_list_mixes_two_legs re-derived each list's leg from the same
table the code stamps rows with, so a list that ranked one leg and labelled
another stayed green. Three of the four ranking keys were asserted by nothing,
because every close in the fixture rose and one subscribed symbol made list 4 a
one element list. The counter fixture wrote exactly what deriving would produce,
so read and derived were indistinguishable. Eighteen mutations now run against
the tree and eighteen are caught.

## 2026-08-20, eleventh: Layer 4 ships, and the spec was wrong in four places

The notable movers section is built. Three legs, four ranked lists, universe
wide for two of them, 2,754 names examined against the twelve the screen
publishes. BUILD_PLAN.md Layer 4 is the design and it was followed; where it
was wrong the code follows the tree and this entry says so.

**The section.** scan.notable_movers assembles it and attaches 4.2's three
report fields to every candidate off the same two reads, so the section and the
candidate rows cannot disagree about a name's sigma. It costs NO EODHD call:
universe.json, universe-closes-<date>.json, the collector bars the scan already
holds and one SQLite read are all local, which is why a quota degraded morning
loses this section no leg at all. Every row is keyed "symbol" and uppercase,
deliberately: vintage accepts either spelling, and analyst._packet_uppercase_tokens
builds the allowed set only from values under keys named symbol or label, so a
row keyed "ticker" would pass the vintage gate and then be reported as an
invented ticker by containment, which stops the chain before render, verify,
deliver and archive.

**Where the spec was wrong.**

FIRST, and it is the one that mattered most: 4.10 said a mis-stamped row failing
vintage.enforce was "already proven by claim_notable_legs". It was not.
claim_notable_legs calls check() and check_packet() and never enforce(), and a
full inventory of enforce calls in the suite found none exercising a check (e)
violation at all. Worse, and this is the part nobody would have noticed:
vintage.enforce runs in build_packet against a HAND BUILT dict carrying
candidates, market_snapshot and session_date, so check (e) walked ZERO ROWS on
every run this project has ever made. The whole check was dead.

Doubly so, and the second reason is the one that would have outlived the first:
no packet carried a notable_movers key either, because the section did not
exist. Building the section fixes that half on its own. It does NOT fix the
hand built dict, which would have gone on hiding the rows from the gate however
full the packet was, and which is the half nothing would have noticed. Adding
notable_movers to that dict is the line that armed it, and
claim_a_mis_stamped_notable_row_stops_the_run now exercises enforce raising,
rewriting data/UNVERIFIED and re-gating delivery, over a mis-stamped leg, a
missing leg and an unrecognised one.

SECOND, 4.9 says the per leg counters are already in the closes sidecar and must
not be recomputed. The writer landed in ea167d5 at 13:37 on 2026-08-20, about
six hours after that morning's 07:15 run, so no file on disk carries them and
"do not recompute" was not executable on the day it was written. They are read
when present, counted from the closes map when not, and counter_source says
which, because a count nobody can tell apart from a written one is a count whose
provenance is false.

THIRD, CRITERIA.md named a threshold key that does not exist. Its [Notable]
prose said the premarket leg covers "at most subscribe_cap of the universe";
there is no subscribe_cap anywhere in the project. The key is [Collector]
max_subscriptions, which BUILD_PLAN had right. CRITERIA is the one document that
must not name a key it does not define.

FOURTH, 4.3 describes the premarket population as "at most max_subscriptions of
the universe, 50 including the eight context tickers", which cannot be
satisfied: the eight are inside the 50 and are not in the universe. They are
ETFs and have no row in universe.json, no close in the sidecar and no row in
gap_stats, so a premarket row for SPY would carry a price and a null in every
other column including the move. They are excluded and the count is reported.
See DECISIONS.md for that and four other calls made here rather than by the
owner.

**Three defects beside the section, all in code the section touches.**
evidence_width counted candidates, priced, with_rvol and scored and nothing
else, so a rerun that produced the full watchlist and lost the whole notable
section was thinner on no axis at all and thin_rerun_stands_down would have let
it overwrite a fuller packet. It has a notable_rows axis now.
analyst.fallback_report writes its own headings in Python and would have shipped
a report with no notable section on any morning the model call failed, which is
exactly the morning nobody reads closely; it emits the section now, with the
header pinned to the template by claim_headers_cannot_diverge like the two
watchlists. And the one skip on the quota degraded path that recorded nothing,
the end of day buy for unpriced names, now records it: those names came out
unrankable and rank_stats attributed it to the collector or the pool, neither of
which was true.

**And a fixture that had been decoupled since the day it was written.**
test_containment carried the notable movers header as a hand written literal
with seven columns, against the nine the section publishes. conftest.watchlist_headers
pins the two watchlists to REPORT_TEMPLATE.md and pinned nothing else, so that
literal was pinned by nothing at all. template_headers() now covers all three,
the literal scan covers all three, and the notable header is checked against
analyst.NOTABLE_HEADER and asserted to be ABSENT from _REQUIRED_TABLES: the
vacuum detector requires the two watchlists BY NAME precisely so a briefing
table cannot satisfy it, and a report with no watchlist and a full notable
section must not pass the structure gate.

**What the first shipped section actually produces, so nobody hunts it.** Lists
1 and 4 are empty. Every return_stdev_20d in the database is null and stays null
until the Sunday 21:00 rebuild, so no name carries a move_sigma, and both sigma
lists come back with no ranking key while their legs are perfectly available.
list_reasons says exactly that, one level down from 4.9's leg rule, because "the
ranking key is null for every name on this leg" and "the market was quiet" are
different facts and an empty list cannot tell them apart. The two remaining
lists filled: five names by market cap over the 1 percent floor, five by the
size of their two session move.

**Thirteen claims in a new tests/test_notable.py**, wired into run_tests.SUITE,
which does not discover modules. They cover the fence, the square root of time
scaling with a name up 2 percent on each of two sessions against one up 2
percent on a single session, the four null sigma outcomes and the fact that they
are four, a 2 percent move at 2.0 sigma outranking an 8 percent move at 0.8, the
leg labelling, enforce, the context tickers, and the four degrades of 4.9.

**One finding handed over rather than fixed.** List 2 is the first thing in this
project that RANKS by market cap; every other use is a floor, and a wrongly
LARGE cap sails through a floor doing no harm. universe.json carries at least
two that are not: SPCX at 1.85 trillion on a 140 dollar price, and SKHY at 1.18
trillion on 166. SPCX reached the published list on 2026-08-20, third by size
behind AAPL and AMZN. No filter was added: a plausibility floor needs a
threshold nobody has measured and belongs in universe.market_cap_funnel where it
would serve the whole project. DECISIONS.md carries the numbers.

## 2026-08-20, tenth: the three unverified findings were all real, and the suite stops failing on the editor

The 2026-08-20 review filed 186 findings and adversarially verified only the
top 26. Three of the unverified nine bore on numbers already relied on and were
left standing as "filed, not confirmed". All three have now been verified and
all three were real. That is worth recording plainly, because the six still
unexamined inherit it: unverified is not a synonym for wrong.

**The float rotation bands were fitted on a population that is 36 percent the
study's own cold start.** float_rotation_study builds its RVOL baseline from a
`history` dict that starts EMPTY and is filled by the same loop that tallies, so
for the first [Baseline] min_sessions_for_rvol sessions, ten, nothing can clear
the floor, rvol is None for every name, and every addressable name carrying a
usable float lands in `rescued`. `rescued` is the population the CRITERIA
[Float rotation] band edges are read off, and DECISIONS.md 2026-08-16 second
went to considerable trouble to establish that it must be, because an overlap
name is scored by RVOL and never reaches these bands at all. Measured on the
archived payload that entry quotes: 894 of 2,464 rescued rows come from those
first ten sessions, and the per session rescue rate runs 84 to 93 percent across
them against 7 to 22 percent from the eleventh onward. Nothing about the market
changed on 2026-06-02. run() now walks the warm up for history and refuses to
tally it, gated on sessions actually rolled rather than on the loop index,
because an incomplete vendor sweep continues without rolling and the two counts
would part company the first time that happened. The payload gains
sessions_walked and warmup_sessions_excluded and `sessions` now counts only what
the distributions were built from, because reporting sixty one measured sessions
when ten of them were warm up is how this hid for a fortnight. WHICH WAY THE
EDGES MOVE IS NOT KNOWN and the shipped ones are unchanged: the payload holds
percentiles rather than rows, so the corrected distribution cannot be computed
from it, and a re-run spends Alpaca requests. A band edge changed on a guess
about the direction of a bias is worse than one known to be fitted on a
contaminated set and saying so.

**The merged trust store could be served half written, forever.**
config.ca_bundle() merges certifi with the local TLS inspection root and hands
the result to requests as verify=. It wrote that file with a plain write_text
and re-serves it on MTIME alone, so a truncated write carried a FRESH mtime and
would then be served until certifi itself changed. The local root is appended
LAST, which is what makes the consequence specific: a truncation loses exactly
the root that makes an intercepted connection verify, so every EODHD call fails
TLS afterwards, at 07:15 on a weekday, for a reason nothing in the trace would
name. tasks/README.md already records that Norton here occasionally denies the
first write of a file, so the interruption was never hypothetical. Now a temp
sibling and os.replace on universe.write_atomically's precedent, which is not
reused directly because it serialises a dict and because core must not import
selection. A second hole beside it is closed at the same time: read_text with
errors="replace" turns an unreadable byte into a character rather than raising,
so a source that came back empty would have contributed a header comment and
nothing else and the merged file would have looked healthy at every size check.
A source carrying no certificate now refuses the merge and returns certifi
alone, which fails verification loudly rather than serving a trust store missing
the one root it exists to add.

**And the suite was failing about one run in six on the editor.** The tree
photograph reported .git/FETCH_HEAD modified, mtime only, size unchanged at 106
bytes. The internal explanations were exhausted first, because the 2026-08-14
correction on differences() is exactly the record of not doing that: every git
invocation in this repository is `git --no-optional-locks status --porcelain` in
core/config.py and `git --no-optional-locks ls-files` in tests, and none of them
writes FETCH_HEAD. Only a fetch or a pull does. This machine carries
"git.autofetch": true in its VSCode user settings and the default 180 second
period, measured directly: FETCH_HEAD rewritten at 20:33:30 and again at
20:36:31, 181 seconds apart. A suite run takes about thirty seconds. That one
path is now exempt, narrowly, on the sampler exemption's model, and
claim_no_python_here_runs_a_git_fetch keeps the exemption honest by failing the
day anything here starts fetching, rather than the day somebody notices. It also
checks every git invocation still carries --no-optional-locks, which is the
2026-08-14 lesson written as a check rather than as a comment.

**62 claims**, and the three new ones were each proved to fail with their fix
removed rather than assumed to: reverting the atomic write produced "a refused
rename did not raise" and "a refused rename changed the bundle on disk", and
deleting the warm up gate produced "run() no longer calls warmup_over". A guard
that has never been seen to fail is not known to be a guard, which this pass
learned the hard way when conftest.redirect_captured_paths turned out to be
asserted by nothing.

## 2026-08-20, ninth: the socket cap probe is armed, and the number it prints was wrong by half

The probe that answers the delivery gate had no scheduled task and no supported
way to get one. It has both now, and reading its existing output first turned up
an arithmetic error in the instrument itself.

**Registered: `\PremarketDesk\probe-socket-cap`, once, 2026-08-21 06:30.** That
brings the folder to nine scheduled steps plus one one off. 06:30 is derived
rather than chosen: four cycles of two arms at 120s with 90s to settle is 28
minutes, the probe adds a 60s buffer before checking itself against CRITERIA
[Collector] start_time, and 06:30 finishes at 06:59 with 21 minutes of slack.
The task's execution time limit is 45 minutes so Task Scheduler's own kill also
lands before 07:20 if the probe hangs rather than exits, because the fifty
symbol pool is account wide and a probe still holding slots would starve the
morning it is meant to explain. WakeToRun is set: the 2026-08-19 run was lost to
a power outage at 06:20.

**register_tasks.ps1 gained `-Probe YYYY-MM-DD` and this is the point of the
entry.** The 2026-08-19 re-arm improvised with `schtasks /Change` against a task
that had never been created, so it failed silently and the document that waits
on the probe went on saying it was armed. A probe that is meant to be deleted
still needs a supported way to be created, or it gets created wrong. `-Probe`
registers exactly one task with one trigger and exits; it refuses a date in the
past, a weekend and anything that is not yyyy-MM-dd, all three verified. It is
deliberately NOT in the $jobs array, because everything there comes back on
every refresh of the schedule and this task must not outlive its question, and
`-Unregister` now removes it, because a removal that leaves one task behind in a
folder people read as empty is worse than none. The one time cleanup loop that
deleted five flat root level task names from the first week is gone; those names
have not existed for a fortnight and a full sweep of the machine's task list
confirms it.

**Nothing else in Task Scheduler was removed, because nothing else is
redundant.** All nine registered tasks map one to one onto register_tasks.ps1
and every one of them is a live step. A sweep of every task on the machine whose
action or arguments name this project found those nine and nothing else: no
orphan from the flat naming, no leftover from job_probe_alpaca_live or
job_probe_live_v1, whose .bat files were deleted on 2026-08-20.

**The instrument was inflating its denominator by exactly half.** The 2026-08-20
review filed this at high severity and never verified it; it was real and worse
than "about 1.5x". compare_to_vendor selected every one minute bar that
overlapped an arm at all and counted each one whole, so a 120 second arm that
did not start on a minute boundary charged 180 seconds of tape against 120
seconds of socket. All eight arms in the only run that exists started between
one and thirty four seconds into a minute, so it was exactly 1.5x on every one
of them. Each bar now contributes only the fraction of itself the arm covered.
The table is also split by arm, because the probe is an A/B and a single blended
percentage cannot answer one. Pro rating spreads a bar's volume evenly across
its minute, which is an assumption and is written down as one; only the two end
bars of an arm are ever partial, and starting the arms on a minute boundary
would remove it.

**Then the reading nobody had taken was taken.** Eight intraday calls against
data/socket-cap-probe-2026-08-19.json, 09:35 to 10:01 ET, no collector in the
path. Both arms delivered a few percent of EODHD's own consolidated bars for the
same minutes: weighted 4.68 percent at eight subscriptions and 5.78 percent at
fifty, median per symbol 3.33 and 3.39, all sixteen readings between 2.06 and
12.05 percent, and the per symbol B/A ratio has a median of 1.05. The capped arm
delivered marginally MORE of the tape than the small one. The cap is innocent
against the vendor's own bars and not merely against itself, and "subscribe to
fewer names" is closed as a fix. Every one of those percentages would have read
two thirds of itself before the denominator was corrected, under a printed
guidance that reads "far below 100%" as evidence of a defect.

**And the reading turned up a second defect, of the family this project keeps
finding: a fact and an absence written identically.** The flagged column was
read as `run.get("off_exchange", {}).get(symbol, 0)`, which returns 0 for a run
that HAD the off exchange counter and saw nothing and for a run that never had
it. The 2026-08-19 runs never had it. They carry arm, counts, cycle,
messages_total, refused, replayed, seconds, started_at, status, subscribed and
volume, and nothing else: `off_exchange`, `off_exchange_volume`, `census` and
`keys_seen` were all added to the probe afterwards. So the comparison printed a
flagged column of zero for every symbol in both arms, and zero flagged prints is
exactly the reading that would close the question below. It prints `not rec`
now, with a paragraph under the table saying that an absence of evidence about
off exchange prints is not evidence that there were none.

What the reading does NOT settle is that fork: a small share with no flagged
prints and no IGNORED condition code means the trades stream omits off exchange
volume, which no collector change reaches, while the same share with an ignored
code means the parser is dropping volume the feed delivered. This payload holds
no evidence on either side. The fork is open on the evidence rather than closed
by it, and the 2026-08-21 firing records off_exchange, off_exchange_volume,
census and keys_seen on a PREMARKET tape, which is the tape the defect appears
in rather than the regular hours tape all of the above was taken on. Both open
questions land on that one run.

**59 claims.** claim_a_partial_minute_counts_only_the_seconds_it_covered holds
the denominator: a misaligned arm and an aligned one both charge exactly the
seconds they listened, and a bar the arm never reached contributes nothing.
claim_a_flag_the_run_never_recorded_is_not_a_zero holds the other half, over a
run with no counter, a run with a counter reading zero, and an arm where only
some legs recorded it. The
file's own header said it carried forty four when it held fifty seven, which is
corrected and read off the file from here on, because a suite that miscounts
itself is the first thing a reader stops trusting.

Documents: BUILD_PLAN's open item A said NO SCHEDULED TASK EXISTS FOR IT in
capitals and is rewritten around the measurement; its item D loses the finding
that is now closed. tasks/README told the reader to read the probe back with
`--report`, a flag the tool has never had, and gives the two real commands
instead. Both architecture pages and the day arc page said no task was
registered for it today. COLLECTOR_VOLUME.md's own new section had the flagged
column as sixteen zeroes for the two hours between the comparison and the fix,
which is written down here rather than quietly overwritten. COLLECTOR_VOLUME.md keeps "The one clean reading nobody
has taken" as its section title, because that was true when it was written, and
carries the reading as its last section with a forward pointer from the old one.

## 2026-08-20, eighth: what the nineteen fixes broke, and 173 corrections to the documents

Two passes over the entry above. An adversarial review of commit ea167d5 itself
raised 40 findings, 11 survived verification, and all 11 are closed here. A
separate audit read every document in the repository against the code and
returned 173 corrections, every one of which is applied. The suite is green and
the tree photograph is clean at 2,090 paths.

The lesson worth keeping is the shape of the worst one. A fix widened the guard
it was written to protect, and nothing in the suite could see it.

**The volume check was putting the previous session's collector roster into the
packet, and containment reads the packet.** Giving verify_against_intraday a
signed median also gave it four per symbol structures:
minutes_compared_by_symbol, unavailable_symbols, vendor_zero_volume_symbols and
collector_silent_symbols. latest_volume_check spreads the whole summary, so all
four reached packet.json. analyst._packet_uppercase_tokens builds the allowed
set out of the raw packet TEXT and _TOKEN_RE finds AVGO inside the key
"AVGO.US", so every name the collector heard or was subscribed to LAST session,
73 of them on 2026-08-19, became a ticker this morning may claim while holding
no evidence about any of it. Measured against the real 2026-08-20 packet: AMAT,
AVGO, DE, HOOD, MU, NOK, RIOT, SAP, TLT and TSM moved from invented to allowed,
which is exactly the set a model reaches for in a market context sentence.
Tonight's nightly would have written the first new shape file and tomorrow's
08:45 packet would have read it. The packet now carries a whitelist of scalars
and the names stay in runs/<date>/verify_intraday.json where a human reads
them.

**The watchdog's new liveness gate created two blind bands.** A dated log
written inside job_log_stale_after_s was taken as proof of life, but the chain
is evaluated by exactly ONE pass inside its rerun window and the nightly by
exactly one at 22:45, so a job that died in the twenty minutes before that pass
consumed its only chance and was not even counted as a problem. The liveness
note justified the gate with "reads as alive at the 08:55 pass and as dead at
09:25", and CRITERIA's own analyst timeout note already said the 08:55 pass
reads NOT DUE. A job that EXITED writes a finish marker, so the marker now
outranks the mtime, which removes every death where a step returned; where only
the mtime can answer, the pass works out from the schedule whether a successor
firing exists and reports UNRESOLVED and counts a problem when none does. The
collector HELD branch had the same missing question and stranded the collector
for the whole morning if it fired at 08:55; it now holds only when a pass that
can act still exists, and starts the collector rather than stranding it after
that.

**The 07:00 catch-up fix was written and not deployed.** job_nightly.bat gained
a catchup mode and register_tasks.ps1 was edited to pass it, but the task
registered on the machine still carried no argument, so pool_recall's new
refusal would have fired every weekday at 07:01 and landed in the published
morning report as a failed step. Two fixes, because either alone is fragile:
the tasks are re-registered, and a refusal on the evidence is now NotMeasurable,
recorded as a skip with its reason, while anything else out of build() is still
a failure. A step that reports FAILED every weekday teaches its reader to stop
reading it.

**The corporate action guard only ever ran on the night the short leg filled.**
It sat inside "if wants_short:" and day5_close was written raw. On the ordinary
cadence the short leg fills on the night of D+1 and the long leg five nights
later with wants_short already False, so an ex date anywhere in D+2 to D+5 put a
post action close beside pre action premarket levels, silently and permanently.
Each leg now checks the units it writes, and a refused day5_close says so rather
than leaving a null indistinguishable from a pending fill.

**Four smaller ones, all of the same family: a fact and an absence written the
same way.** trap_basis published headlines_scored 0 and headlines_in_window 0
for a window the news call never reached, byte for byte what a window that WAS
read and held nothing publishes. The roundup sharing count was measured over
candidates whose news call never ran, so a quota thinned morning changed which
articles counted as roundups without saying so. discover threw away an in hand
prior close map when only the SECOND bulk call came back empty, so every
subscribed name reached the scan with pool_prior_close null and the scan bought
each one back. And _volume_check_direction had no agreement branch at all: a
collector that matched the vendor was published as "the two readings disagree",
which is the outcome the whole measurement exists to work towards.

**Two guards that guarded nothing.** conftest.redirect_captured_paths, the
harness fix from the entry above, was asserted by no claim: deleting it left the
whole suite green, because run_tests never enters standalone(). And
trading_day_state's calendar_known() short circuit meant test_vintage's stub of
is_trading_day no longer controlled the path it was stubbing, so that claim had
become machine dependent and would fail on a fresh clone. Both are closed, the
second by routing the unknown through the same seam as the answer so replacing
one function replaces the whole decision.

**The documents. 173 corrections, and the two worst were in this file.** The
entry above said "WMT published trap false on 3 of 45 headlines, COIN on 3 of
24, BABA on 3 of 17" and that the next morning would decide all three on their
whole window. WMT and BABA carry trap NULL, not false: their gaps are down,
-7.26 and -5.35 percent, and a trap is a gap UP contradicted by its news, so
their verdicts cannot move at all. Only COIN was right. The same entry said
build() "could only measure the day it was invoked on"; build(session_date=None)
has always taken a --date and the 07:00 firing simply passed none. Both are
corrected in place with the marker this file's header prescribes, because a
number that was wrong when it was written is a mistake rather than history.

Elsewhere: BUILD_PLAN said eight scheduled tasks against nine registered, and
put the day's bulk spend at 392 calls when discover makes three end of day
calls rather than two and the real figure is about 500. Its Layer 4 section
told a future session to add "rule 10, after the existing nine" to
prompt_analyst.md, which holds fourteen rules and whose rule 10 has been the
display rounding rule since 2026-08-14, so a session following it literally
would have overwritten one. It also listed gap_stats.return_stdev_20d under
"already built" without saying that all 10,997 rows of that column are NULL and
stay null until the Sunday rebuild, which is the denominator every Layer 4
move_sigma divides by. Both READMEs gave the Sunday universe build as 20:00,
the one time register_tasks.ps1 records as actively harmful because it is the
instant of the quota reset, and neither had a row for the meter sampler, which
fires 48 times a day. tasks/README.md pointed at src\market_today.py, a path
from before the package split. Every suite module's docstring told the reader to
run it as "python src\test_x.py", which cannot work: the file is under
src/tests/ and running it by path breaks the package imports. The architecture
pages still described picks as empty when it holds twelve live rows, said the
quantifier guard had never fired live when data/quantifier-flags.jsonl holds a
flag from that morning, and said the 2026-08-19 volume reading was still owed
when it landed at 07:01 that day. CRITERIA's analyst timeout table stopped at
2026-08-19 and its chain_due comment contradicted the file's own arithmetic
thirteen sections later.

**One knob deleted.** CRITERIA [scan] economic_importance = high was read by no
Python at all; economic_events() hardcodes the string and filters on the
[Economic importance] term list instead. A live looking knob that does nothing
is worse than no knob.

**And the em dash guard got wider.** It knew only the named entity, so a page
written with the decimal or hexadecimal numeric reference would have passed
while rendering identically. It knows all three now, case insensitively, and a
planted one of each is caught.

## 2026-08-20, seventh: all nineteen findings from the full review, closed

The purge entry above says the findings were open. They are not any more. Every
one carries a claim, the suite is green three runs running, and the tree
photograph counts 2,038 paths unchanged. What follows is what each one was.

**Containment invented tickers out of ordinary abbreviations, and it stopped
the whole morning.** _prose_tokens blanked ISO dates and clock times and
nothing else before _TOKEN_RE ran, so capitals joined by punctuation came apart
into single letters: "S&P 500 futures are flat" gave P and S, "U.S. equity
futures are soft" gave S and U, "the P/E is stretched" gave E and P.
universe.json carries 21 one letter listings and prose_token_stopwords stops
only A and I, so each fragment became a ticker claim and then an INVENTED one
unless the packet happened to quote a headline holding the same bare letter.
Injecting one ordinary Market trends sentence into the four archived reports
and checking each against its real packet invented P, S and U on 2026-08-17 and
2026-08-20 and P on 2026-08-19; 08-18 escaped only because its packet quotes a
headline containing "S&P 500". check_report exits 2, the chain stops on a non
zero return, and containment has no regeneration path, so the morning would
have lost render, verify, deliver and archive to a sentence any writer would
type. Abbreviations are now blanked like dates and times. Stopwording the
letters was the cheap fix and was rejected: it would have blinded the guard to
six real listings in prose, trading a false positive for a false negative in
the one check that exists to catch invented evidence.

**A multi company roundup paid its top catalyst class to every name in it.**
EODHD tags are ARTICLE scoped and classify_catalyst read them as company
scoped. On 2026-08-20 the CNBC piece "Stocks making the biggest moves
premarket: Walmart, Coinbase, Moderna, Alibaba and more", carrying 46 tags of
which 19 name companies, 14 issuers between them, and 27 name topics, desks and
bylines, EARNINGS among those 27 and Walmart's, conferred class earnings on
MSTR, COIN
and MARA, and "Biggest stock movers Thursday" did the same for BLSH. None was
on that morning's calendar. Class earnings is 3 of the score's 10 points, so
MSTR published 7.0 green where it should have been 4.0 yellow, and COIN, MARA
and BLSH published 6.0 yellow where they should have been 3.0 red. The obvious
fix does not work: the symbols array on every one of those articles is EMPTY,
so the filter that reads it was never running. Breadth decides it instead, on
two counts in CRITERIA [Score catalyst tags], because neither sees the whole
thing: the tag count catches a roundup the feed handed to one candidate, and
the sharing count catches one tagged by topic rather than by issuer. A name
whose every article is a roundup now comes out class none with catalyst_found
still true, which says the window was checked and paid nothing.

[corrected 2026-08-20: the tag count read "tagged with 45 issuers including
EARNINGS for Walmart". The article carries 46 tags; 19 of them name companies,
14 issuers between them, and the remaining 27 are topics, desks and bylines,
with EARNINGS among those 27. The fix reads the tag COUNT against
max_tags_for_one_company, so nothing downstream moves. CRITERIA's article scope
note and _scope_articles carry the same figure.]

**The trap verdict weighed three headlines and reported the truncated set as
complete.** news_keep is 3, attach_traps read only the kept list, and
min_headlines_for_balance is 2, so one negative against zero positives
satisfied "strictly more negative than positive" and reinstated the single
mis-scored headline verdict the balance rule was written that same day to stop.
COIN published trap false on 3 of 24 headlines, MSTR on 3 of 8 and MARA on 3
of 7, and WMT's trap_basis reported scored 3 unscored 0 with 42 of its 45
counted nowhere. The balance is now counted over the whole window and news_keep
is a display cap. This changes live verdicts: the next morning decides COIN,
MSTR and MARA on all of their headlines rather than on three.

[corrected 2026-08-20: this read "WMT published trap false on 3 of 45
headlines, COIN on 3 of 24, BABA on 3 of 17" and named WMT and BABA among the
verdicts that change. Both gapped DOWN, 7.26 and 5.35 percent, and attach_traps
returns null for a gap below [Traps] min_gap_pct before it weighs a headline,
so neither ever carried a false and neither verdict can move.
runs/2026-08-20/packet.json holds trap null for both with that reason beside
it. The truncation itself was real on all four windows, 45, 24, 17 and 8
headlines against three weighed. attach_catalysts' docstring carries the same
sentence.]

**The collector volume check returned an unsigned median and three consumers
asserted a direction from it.** scan.volume_check wrote "understated by about
that much again" into gaps_to_fill, analyst repeated it in the fallback, and
REPORT_TEMPLATE ordered the model to say it plainly; the 2026-08-20 report
published it. COLLECTOR_VOLUME.md refutes the assumption in the project's own
words: 2026-08-17 reads -88.49 percent and 2026-08-14 comes back at 3.83 times
the vendor in aggregate. On a morning shaped like the second one the report told
its reader every RVOL was understated while the numerator was inflated, which is
the direction that flatters volume. The check now returns a signed median, the
aggregate ratio, per symbol minute counts and both missing side counts, and it
publishes a direction of under, over, mixed or unknown with the phrase the
template quotes rather than composes. Archived readings written before the sign
existed degrade to "the direction of that disagreement is unknown", which is
what the fallback prints against runs/2026-08-20 today.

**The measurement that closed Alpaca recorded a refusal as an empty feed.**
DECISIONS.md 2026-08-17 closes Alpaca as a live discovery source on "23 sweeps
... every one empty" and argues the probe's own denominator makes that
emptiness informative. The raw file says 23 sweeps, 46 chunk failures, every
one HTTP 403, zero requests served, because sample() asks for the sip feed and
the free tier will not serve it live. sample() recorded those failures and
_table_rows never read the key, so a refusal and an empty premarket produced
identical output. The table now carries requests served and refused, the prose
refuses to interpret a sweep nothing answered, and the DECISIONS entry is
corrected in place with the marker that file prescribes. The conclusion stands
and is now narrower and stronger: a blanket refusal of the sip feed for a live
window is itself the evidence.

**A dark exchange calendar made the morning refuse instead of degrade.**
is_trading_day answers True with "calendar unavailable, assuming the market is
open" for every date, weekends included, and does not raise, so
previous_trading_session's except branch never fired for the fault that
actually happens. On a Monday it returned the Sunday and vintage then failed
every dated row: check_packet on the real 2026-08-17 packet returns 6
violations with no network at all, enforce() rewrites data/UNVERIFIED over the
human's note, and the chain stops before the analyst with no packet and no
report. market_today gained trading_day_state, which answers None when it
cannot say, and vintage stands down on None the way check (e) already did.
job_status.sessions_between reads it too: it counted a weekend as three
sessions and called healthy jobs overdue, and its docstring had promised the
weekday fallback since it was written.

**The watchdog relaunched live jobs on top of themselves.** maybe_rerun fired
on the absence of a finish marker alone, and a job that started seconds ago has
not written one. Only the collector was gated. A late wake is the trigger:
every task carries -StartWhenAvailable and two catching up within 0.15 seconds
is on record from 2026-08-19. Two scans would write packet.json at once, two
analyst steps each spend a CLI completion, and two archive builds race a non
atomic write. At night it was easier still, because a running task reports
267009 and fired_ok required "0", so the rerun fired even when the marker
existed. _job_alive now asks the two questions _collector_alive already asked,
with [Monitor] job_log_stale_after_s at 1200 seconds, derived above the
analyst's own worst case of 1,074.

**The discover rerun branch was unreachable.** It needed
445 <= now_m < 440. CRITERIA and tasks/README both promised a safety net that
no clock value could engage, and nothing anywhere detected a previous session's
watchlist as stale. The rerun now triggers on the condition that actually
matters, a watchlist from an earlier session with nothing yet subscribed, at
any hour, and both documents say so.

**An empty bulk payload read as a fetched one.** prior_session_movers checked
only the error slot, so a vendor publication lag recorded FETCHED_EMPTY, this
module's own wording for a source that succeeded with nothing, and every
consumer keys on NOT_FETCHED so the run exited 0. That source supplied 364 of
628 pool names on 2026-08-20. eodhd.quote_delayed had already closed this exact
guard with "the test is now on the data rather than the error"; this is the
caller it was not applied to.

**pool_recall recorded missing evidence as measured zeros.** build() measures
the day it is invoked for and the 07:00 catchup passes no --date, so every
weekday it asked the vendor for a session that had not opened, got an empty
bulk payload and wrote gapped 0, addressable 0 and no reason at all into
runs/<that day>/pool_recall.json. runs/2026-08-20/pool_recall.json, stamped
07:01:18, is the artifact. On an ordinary day the 22:15 pass overwrites those
zeros; on a night that does not reach the step they stand as a measured total
failure of a morning that produced no report. measure() collapsed an
unknown published set with "published or set()" while _rate()'s own docstring
argued the opposite case for the denominator. Both now refuse or null with the
reason beside them, and job_nightly.bat gained a catchup mode that
register_tasks.ps1 passes at 07:00: the evening pass is the one with a closed
session to measure. The registered task predates that argument and still
carries none, so the machine goes on running the whole nightly at 07:00 until
register_tasks.ps1 is run again.

[corrected 2026-08-20: this read that the catchup was "overwriting the previous
evening's real figures with gapped 0, addressable 0, recall 0.0". It writes the
file for the day it was invoked for, so the previous evening's file is never
touched: runs/2026-08-19/pool_recall.json still holds gapped 167 stamped
2026-08-19T22:15:13 after the 07:00 run of 08-20. The rates in the 07:00
artifact are null and not 0.0, because _rate returns null on an empty
denominator; the 0.0 belongs to the published collapse named next. It also said
build() could only measure the day it was invoked on, and build() has always
taken a --date. pool_recall.py's own comment has the direction right; the
header of tasks/job_nightly.bat repeats the wrong one.]

**Outcome arithmetic was split blind.** mfe_pct, mae_pct and
pm_high_broke_next_day subtracted raw collector premarket levels from the next
session's adjusted bar, so a corporate action with an ex date in between left
the two sides in different units: a 4-for-1 forward split writes both
excursions near -75 percent, a 1-for-10 reverse split near +900, unflagged,
into the table CRITERIA says its thresholds will be recalibrated against. The
module already refused to "put a fabricated excursion into the record" and this
was the one path through which it happened. close over adjusted_close is flat
between actions and steps at each one, so the row is refused when that ratio
moves by more than [Outcomes] max_adjustment_drift_pct.

**The morning told its reader the vendor had no float data on a morning it
never asked.** The thin quota path set quote = {} with no call made, and
attach_float_rotation could not tell that from a fetched quote missing the
field, so every candidate carried "the delayed quote carried no sharesFloat".
attach_traps hard coded "the news call failed" for a call that was skipped. The
template forbids the model to supply the reason a number is missing and orders
it to quote the packet's, so the packet has to be right. Both now say skipped.

**Prompt rule 5 still ordered the model to decide traps from sentiment.**
f1b1fb9 removed that instruction from REPORT_TEMPLATE and left it in
prompt_analyst.md, and _compose_stdin pipes both to the model in one stdin, so
it read rule 5 beside "TRAPS ARE DECIDED IN THE PACKET AND YOU MUST NOT
RE-DERIVE ONE". The state it fires on is live: MSTR at gap 9.06, trap false, a
headline at polarity -0.914.

**A truncated verification retired a session forever.** backfill decided a
session was measured with is_file() while the only reader of that artifact
skips a copy it cannot parse, and the writer used write_text, which truncates
before it writes. It now writes through a temp file and renames, and refuses to
call an unparsable summary a measurement.

**Four things in the harness, and the harness is what the rest of this rests
on.** ensure_dirs iterated a tuple of Paths frozen at import, so every call
inside the sandbox mkdir'd the four REAL directories; it reads the attributes at
call time now. standalone() printed that the real runs/ was not writable from
a hand run while test_repricing.RUN_DIR still pointed straight at
runs/2026-08-14, where claim_three opens a database; it rebinds the module's
captured paths and prints what it moved. test_repricing returned ok for the
whole module when two artifacts were absent, including three claims that read
neither, so attach_float_rotation and the sharesOutstanding guards were
unguarded on every machine but this one; only the five claims that replay that
morning are gated now. And the intraday stub served one fixed day whatever was
asked, so backfill's every _true_path call was rejected and the ten true
premarket and outcome columns were written by no test at all: inverting the
sign of the shortfall left the whole suite green. The stub answers the day it
is asked for, and two new claims pin all ten columns and both excursion signs.

**Fifteen em dashes, and now a guard.** Three in Python, eight in the running
record, four written as an HTML entity on the architecture pages, which is the
half a grep for the character would never have found and the half a reader
actually saw. Hard rule 4 was enforced on the model and on nothing else. It is
enforced on the repository now, both spellings, across every tracked file.

**One thing the fixes broke and the suite caught.** The new em dash walk ran
git ls-files, git refreshed and rewrote .git/index, and the tree photograph
failed on a file the check itself had changed. build_identifier learned this on
2026-08-14 and the note in differences() records it. Same fix,
--no-optional-locks, and three consecutive clean runs.

## 2026-08-20, sixth: the purge, and nothing rectified in the same pass

A full review ran over the whole tree and its findings are open. This entry is
only the deletions, kept separate so that a commit which removes things cannot
be confused with one that changes behaviour. Everything below was proven unused
before it was removed, the suite is green either side of it, and the tree
photograph counts 1,994 paths where it counted 2,005.

**Dead code, by reference count across all 51 modules.** `ApiResult.or_empty`
in core/eodhd.py had no caller and substituted a fallback for a vendor failure,
which hard rule 5 forbids, so removing it removes the temptation as well as the
code. `ettime.previous_weekdays` had no caller and put weekday date arithmetic
in the one blessed clock module, next to the rule that says session dates come
from the data the vendor returned. `conftest._allowed` was never called and
disagreed with the live filter beside it, matching any path component where the
live one matches only the entry's own name. The `snapshot = snapshot_tree`
alias had no remaining user. Twelve unused imports went, each checked by AST
rather than by eye. Seven copies of `OK_CODES = (0,)` went, in meter_sampler,
quantifier_flags, float_cache, float_rotation_study, probe_alpaca_live,
probe_socket_cap and vwap_gappers: none is read by anything, none of those
modules is in test_entrypoints' SCHEDULED list, and probe_alpaca_live carried a
comment explaining why it is deliberately not wrapped in job_status.run
directly above a constant implying it is. The sixteen live OK_CODES stay, one
for each entrypoint in test_entrypoints' SCHEDULED list. [corrected 2026-08-20:
this read "The seventeen live OK_CODES stay". 23 modules defined one before the
purge and seven went, which leaves sixteen.]

**Two spent scheduler wrappers.** tasks/job_probe_live_v1.bat and
tasks/job_probe_alpaca_live.bat both said in their own headers to delete them
once the question was answered. Both questions were answered on 2026-08-17 and
recorded in DECISIONS.md, neither task exists on the machine, and
register_tasks.ps1 never knew them. The research modules they wrapped stay,
because they are how the evidence behind both decisions is read back.
tasks/README.md and BUILD_PLAN.md's repository layout are corrected to match,
and the README now records that job_probe_socket_cap.bat survives with NO TASK
REGISTERED for it.

**Two fabricated sessions that were being published.** runs/2026-01-05/ and
runs/2026-01-06/ held test_containment fixtures for ARX.US, written at 09:51 on
2026-08-20 by a hand run of that module 44 minutes before the commit that added
conftest.standalone(). They were not an open hole: the suite is sandboxed and
the photograph is clean. They were residue, and build_archive had embedded both
into site/PremarketDesk.html as sessions indistinguishable in form from the six
real mornings. Deleted, archive rebuilt, six embedded and no Jan rows.

**One exact duplicate.** data/float_rotation_study.json is byte equal to
doc/research/float_rotation_study-2026-08-17-postfix.json once `_provenance` is
popped, and the tracked copy is the one DECISIONS.md cites and the only one
carrying provenance.

**Three .gitignore lines.** `premarketdesk.db`, `universe.json` and
`watchlist.json` were each already ignored by `data/` at line 6, confirmed with
`git check-ignore -v`. They are unanchored, so they would have silently
swallowed a future fixture of any of those names anywhere in the tree.

## 2026-08-20, fifth: the nine smaller findings from the same read, all closed

None of these was a false statement. Each was the report being accurate and
incomplete, or precise about the wrong thing, and each needed its own argument,
which is why they were held back from the pass above rather than swept in.

**A rank cap dropped six names and nothing recorded it.** "18 cleared the price
and gap floors and 12 were kept" is arithmetic a reader can do and an
explanation they cannot. rank_by_measured_gap now records cap, cap_source,
capped_out and capped_out_symbols, and gaps them, so a truncated name is
distinguishable from a rejected one.

**The bucket roll was enumerated by the model and the score has no sign.** Two
sentences, one cause. "MSTR and WMT green at 7" omitted SCSC, which also scored
7.0 green; and "the strongest scored names, both green at 8, are AAP and FUTU"
ranked by a score whose gap component uses the ABSOLUTE gap, on a morning AAP
was down 21.75 percent on an earnings miss. The new score_roll block holds every
scored ticker with its bucket, its score AND its direction, ordered strongest
first, and the template quotes it rather than assembling one.

**A screen condition that was never measured was counted as one that failed.**
"premarket_rvol 10 of 12" folded in AAP and SCSC, whose RVOL is null because the
baseline denominator is unusable, alongside eight measured and low. Every
eligibility test now carries a third element saying whether its input was
observed, screen_tally splits failed into measured_and_failed and unmeasured,
and failed_summary says "(K of those never measured)" inline. No eligibility
decision changed: withholding an unmeasured name from a screen was always right,
and only the reporting was wrong.

**Two vendor prior closes disagreed by 1.67 percent in silence.** SCSC's end of
day record said 51.42 and the delayed quote in the same packet said 52.2909,
which is the difference between a published gap of 16.34 percent and one of
14.4. Now recorded as prior_close_disagreement_pct, a magnitude like
pm_source_disagreement, and gapped above the CRITERIA floor. The end of day
record still wins; this is a disclosure and not a tiebreak.

**Four bars and fifty bars shared the word partial.** SCSC's entire premarket
record was four one minute bars holding 1,487 shares, and its gap, its VWAP and
its high all rested on them. pm_window_thin is now a separate flag from
pm_window_starts_late, with its own floor in CRITERIA and its own count in the
reason, because a window can open on time and still be thin and the fixes
differ.

**Two replay-only prints were described as no print at all.** The report said
the socket "delivered no trade" for HOV, LYTS, NBTX and UUP. True of the first
two; NBTX sent one 04:23 print of 20 shares and UUP one 07:00 print of 1 share,
correctly filtered from the window and correctly absent from the bars.
read_bars_file now counts replay per symbol and collector_coverage splits
silent_with_nothing from silent_with_replay_only, because a replayed print
proves the subscription was accepted and silence does not.

**Three RVOL denominators were up to six days old and looked like today's.**
Reusing a cached baseline inside refresh_after_days is the design. Presenting a
denominator warmed on 08-14 beside one warmed this morning with nothing to tell
them apart is not. baseline.age_days and baseline.computed_today now travel with
every RVOL, reported as a fact and never as a warning.

**The test suite wrote to real data when a module was run directly.** Found by
doing it: `python -m tests.test_containment` outside run_tests.py appended
sixteen of its own fixtures to the real data/quantifier-flags.jsonl, two of them
carrying a verdict, and the next SANDBOXED run then failed as well, because
conftest.activate() copies data/ in and the fixtures came with it. The suite
broke the suite. The tree photograph cannot catch this: the path already existed
and only its contents changed. conftest.standalone() now wraps a hand run in the
same sandbox run_tests uses, and every suite module routes its __main__ through
it. Refusing the direct run was the alternative and is worse, because running
one module is exactly what a person does while chasing a failure.

Eight claims covering the nine findings, in src/tests/test_regressions.py: the
roll-call omission and the unsigned score share one, because they were one
cause. [corrected 2026-08-20: this read "Nine claims, one per finding". The
commit adds eight and the file went 19 claims to 27.] Two new
CRITERIA keys with their notes: [Scan] min_bars_for_full_window and
prior_close_disagreement_pct.

The report of 2026-08-20 was regenerated a second time against a second
amendment, on the same terms as the first: nothing re-fetched, no price, volume
or timestamp touched. The screens were re-derived rather than trusted and came
back byte identical. One field could not be recovered and says so instead of
guessing: capped_out_symbols needs the pre-cap ranked list, and the 08:45 packet
only ever held the twelve that survived the cap. The count is arithmetic and is
sound; the symbols start being recorded from the next scheduled run.

## 2026-08-20, fourth: the morning report's own two defects, found by reading it

The audit above read the CODE. This one read the OUTPUT: the 08:45 report of
2026-08-20, line by line, against packet.json, the raw collector file, the
nightly's verification and the scheduler trail. The arithmetic all reconciled
and two things did not.

### The report described a ten-fold instrument error as an arithmetic detail

Premarket RVOL divides a numerator the collector socket supplies by a
denominator the vendor's intraday endpoint supplies. Those two feeds do not
agree, verify_against_intraday measures exactly how much they disagree on
identical minutes, and the 07:00 catch-up had written that morning's answer
five hours before the report was built: **90.0 percent median absolute
difference across 73 symbols, none inside one percent**. The three sessions
before read 90.0, 88.4 and 71.0.

The report said RVOL was a lower bound and gave one reason, the window
shortfall, which is arithmetic and is the smaller of the two. It could not give
the other, because nothing under src/morning read verify_intraday.json. The
measurement existed, was taken on schedule, and reached no reader.

collect_premarket.latest_volume_check now reads it, scan.volume_check puts it
in the packet as collector_volume_check and states it in gaps_to_fill, and
REPORT_TEMPLATE.md requires the report to quote its median, its symbol count
and its date wherever RVOL is discussed. An absent or stale check is itself a
gap: an unmeasured feed is not a clean one, and a morning silent about it reads
exactly like a morning that measured zero. See the volume check note in
CRITERIA.md and [Collector] volume_check_max_age_days.

**What it cost that morning.** Seven of twelve candidates cleared price, gap,
market cap and the prior session high and failed the day screen on premarket
RVOL by itself: SCSC, FUTU, MSTR, ASST, BLSH, COIN and MARA. FUTU measured
1.0282 against a 1.5 threshold. The report published "the day screen produced
nothing today" as an observation about the market. scan.rvol_only_day_failures
now counts that set into day_blocked_on_rvol_alone and the template requires it
named, so an empty watchlist that the instrument caused says so.

### Two traps were vendor sentiment errors, stated as conclusions

REPORT_TEMPLATE.md told the model "a positive gap on headlines whose sentiment
is negative is a trap and is said plainly". The packet carried no trap field,
so the model did what that sentence invites and read the worst single headline.
On 2026-08-20 it published MSTR as a trap on "Bitcoin tops $71K as crypto rally
gains momentum", scored -0.914 by the vendor against that same name's own
+0.963 and +0.833, and FUTU on "Here are the major earnings before the open
Thursday" at -0.422 against +0.836 and +0.691. Both are plainly mis-scored
text. Both reached a reader as statements about the market, and neither guard
could see it: the tickers were real and the polarity was quoted correctly.

This was the house rule being broken. Python decides, the model narrates, and a
trap is a decision. scan.attach_traps decides it now, on the BALANCE of a
ticker's scored headlines rather than the worst one, and keeps the counts in
trap_basis so a reader can disagree with the call. trap is NULL, never False,
when there is nothing to weigh: a gap down, fewer than two scored headlines, or
a news call that failed. Thresholds are in CRITERIA.md [Traps] with the balance
note; the template now forbids re-deriving a trap and requires trap_why to be
quoted.

### Also

- The fallback report states the trap verdict and the volume check rather than
  saying trap judgment "needs the narrative pass", which stopped being true.
- Three new claims in src/tests/test_regressions.py, one per finding. The trap
  claim uses the real 2026-08-20 MSTR and FUTU polarities as its fixture: a
  claim written from invented numbers proves the rule, this one proves the case.
- The report of 2026-08-20 was regenerated against an amended packet. scan.py
  cannot be re-run for a closed premarket window, so the three new passes were
  applied to the evidence the 08:45 run had already gathered, with nothing
  re-fetched and no price, volume or timestamp touched. The originals are
  preserved as runs/2026-08-20/packet.0845.json and report.0845.md, and the
  amendment says so in its own gaps list.

### One thing this did not fix

Nine smaller findings from the same read are recorded in BUILD_PLAN.md as 6a to
6i rather than fixed here: the six names a rank cap drops without saying so, a
score roll-call that omits a tied name, "strongest scored" being direction
blind on a name down 21.75 percent, null RVOL pooled with measured-low in one
tally, two vendor prior closes for SCSC disagreeing by 1.67 percent, a
premarket record of four bars described only as "partial", two replay-only
prints described as no print at all, three RVOL denominators up to six days old
with nothing beside them to say so, and the suite writing to real data when a
module is run directly. They are accuracy and completeness, not falsehood, and
each wants its own argument.

## 2026-08-20, third: an adversarial audit of the whole scheduled path, twenty defects fixed

Forty findings raised by six readers over the six packages and the .bat files,
each then handed to an independent verifier told to REFUTE it. Twenty survived
and all twenty are fixed here, with one claim each in the new
src/tests/test_regressions.py. The twenty that were refuted are not listed:
they were wrong, and a list of wrong things is how a next reader wastes a day.

### Wrong numbers reaching a reader

**The macro line was four hours late in every report ever written.** The EODHD
economic events feed is UTC with no offset on the string, and scan parsed it
with `fromisoformat(raw).replace(tzinfo=ET)`, which keeps the digits and
changes what they mean. Every archived packet carries it: 2026-08-19 has FOMC
Minutes at 18:00 ET against a real 14:00 release and Initial Jobless Claims at
12:30 against a real 08:30. A premarket briefing that moves the morning's only
macro print from an hour before the open to after lunch has inverted the one
thing that section is for. Now `ettime.to_et`, which attach_catalysts was
already using on the news feed, and the packet records that the times are a
conversion so the old ones cannot be compared against the new.

**return_stdev_20d was a 250 session standard deviation.** The closes list was
trimmed to lookback_sessions and the stdev taken over all of it;
min_sessions_for_move_sigma was doing duty as the window and it is a floor. New
[gap stats] return_stdev_sessions = 20, with a note on why a floor and a window
are different questions. Nothing consumes the column yet, so no report carried
it, but every Sunday was writing it wrong.

**A bar with no open broke the close chain.** gap_stats dropped such a bar
whole, which removed its close, so the next session's gap was measured against
a close two sessions back: a two session move stored as a one session gap, in
gap_propensity, which is [discovery] within_tier_key, the number 42
subscription slots are ordered by. The comment beside it had identified this
exact mechanism and fixed it for the returns list only.

**The fixed rule DST fallback put November on the wrong hour.** zoneinfo is
unavailable here so the fallback is load bearing. dt.tzinfo's default fromutc
runs the daylight test on the standard clock, which is right in March and an
hour out in November: every UTC instant from 06:00 to 06:59 on that Sunday came
back as 02:xx EST when it is 01:xx EST, and 02:00 EST was produced twice while
01:00 EST never was. It now carries its own fromutc comparing UTC instants, and
all 8,760 hours of 2026 round trip.

### Losses that were silent

**A rerun that knew less replaced a packet that knew more.** The RVOL cutoff
snaps to run_time only within ten minutes of 08:45, while the picks live window
is 07:00 to 09:30 and the watchdog may rerun a broken chain until 09:30. So a
09:25 rerun found no warmed baseline, nulled every pm_rvol, flipped
day_eligible false for all twelve, and upserted that over the 08:45 rows as
source 'live'. thin_rerun_stands_down asserted exactly this in its docstring
and tested only for a degraded quota. It now measures the evidence: candidates,
priced, with_rvol, scored, and stands down when the fresh run loses on any axis
and gains on none.

**flush marked minutes written before writing them.** Bars were popped from
open_bars and their keys added to `written` while the batch was built, and only
then was the file opened. An OSError there lost them twice: never on disk, and
`written` then made add_trade refuse every later trade for those minutes as a
late print. The OSError also reached run_websocket's socket handler, which
reported a disk fault as a lost connection and resubscribed into a 50 slot pool
known to refuse. Now written last, held and retried on failure, counted in
write_failures, and never raised at the socket.

**Replay was re-counted on every resubscription.** The vendor replays a last
trade per symbol on each subscribe and nothing deduplicated the replay rows, so
replay_volume in the packet, the number the tag was introduced to make
measurable, was multiplied by the connection count.

**The baseline reported its request as its result.** main discarded warm()'s
counts and recorded len(tickers), so a warm in which every ticker failed
recorded "tickers warmed 42" and exit 0, while the scan published a null
pm_rvol for the whole watchlist.

**A pick older than the session calendar was measured against the wrong
sessions.** _session_calendar fetches 40 calendar days; _sessions_after did not
check that the pick was inside it, so for an older row every entry qualified
and the first returned was the window's OLDEST session. A name halted the day
after a pick stays null and is re-selected nightly until, six weeks later, the
calendar no longer reaches it and the row is filled with excursions from a tape
weeks removed. It now raises CalendarTooShort and the row stays honestly null.

**A null close was written, counted and rewritten forever.** next_day_close
could be set to None beside real open/high/low, and the candidate query
re-selects on that column being null, so the row came back every night, was
re-fetched, recounted, and had outcomes_filled_at moved. The idempotency claim
in the docstring was false for exactly those rows.

**A pipe in a headline ate the rest of the headline.** The fallback report
interpolates vendor text straight into a markdown table cell; python-markdown
discards cells past the header count without complaint. New `_cell` helper.

### Guards that did not guard

**watchlist.json was written non-atomically.** A plain write_text truncates the
500 KB file before writing a byte, so an interruption at 07:15 leaves invalid
JSON where the last good watchlist was and the 07:20 collector exits with no
tape for any name, tape that cannot be fetched later. Yesterday's file would
have served: the collector applies no freshness test. universe.write_atomically
now takes a target and discover uses it.

**One failed exchange list wrote half a universe and passed every gate.** The
sweeps and the funnel are computed from that index so they agree with each
other; only the count fraction floor stands between it and the disk, and at 0.5
against a 1,519/1,235 split it catches a lost NYSE and not a lost NASDAQ. Which
half the vendor dropped decided whether the gate spoke, and max_age_days is 10
so the monitor's age keyed relaunch never fires on a fresh bad file. Now a
PartialBuildError three credits into the run.

**A hung schtasks killed the whole watchdog pass.** query_task absorbed a
non-zero exit and not TimeoutExpired or FileNotFoundError, so on a thrashing
machine the pass did none of its other work either: no collector restart, no
chain rerun, no backlog line, just a traceback, with the next chance thirty
minutes later.

**deliver had no send-once record.** The watchdog reruns the whole chain on the
reasoning that it is idempotent, and the chain's finish marker is written by
the archive step AFTER deliver, so an archive failure leaves a chain that has
already emailed looking unfinished. It now writes runs/<date>/delivered.json
and refuses a second send; an unreadable record reads as no record, because a
second copy is a cheaper mistake than no copy.

**The quantifier guard skipped headings.** Only the table skip was documented.
A heading is prose in the most prominent position on the page and is exactly
where a model summarising an empty screen puts a set-wide claim. The warn mode
flag rate was undercounting by however many lived there.

### Records that lied about themselves

**A quiet morning recorded a failed step.** verify_morning returned 1 on a
zero candidate packet against OK_CODES (0,), so a thin premarket day put a
failed scheduled step in the trail, the watchdog counted it, and the next
morning's disclaimer named it. Exit 0 now, with zero rows tabled.

**The watchdog recorded finding a problem as failing.** check_all returns 1
when it FINDS something, which job_monitor.bat documents as "come and look",
but OK_CODES was (0,) so every such pass recorded STATUS_FAILED. One unjudged
quantifier flag past its seven day window would have made every later pass
record failed, and two sessions later the morning report would tell the reader
the watchdog had never succeeded and had stopped running. OK_CODES is (0, 1)
and the count is now problems found.

**Two comments described code that does not exist.** analyst's token comment
cited a `_single_letter_listings` helper that was never written, and
job_status's meter comment claimed "about eighteen a day" when the trail
measures 84 to 92 job readings a day plus the sampler's 48. Both corrected in
place with the old text quoted, per this file's own convention.

### The suite

src/tests/test_regressions.py, sixteen claims covering all twenty findings, in
run_tests' SUITE. Grouped by how they were found rather than by theme, because
that is the only thing they have in common and a reader asking what the audit
caught should get one file.

## 2026-08-20, second: the volume instrument is ungated, and the analyst timeout is re-derived

The two consequences the morning review recorded rather than fixed, closed
before the 07:15 run. Reasoning in DECISIONS.md the same date.

### The collector volume check no longer depends on the picks table

`night.backfill_premarket` called `verify_against_intraday` at the very end of
`backfill()`, after the early return that fires when a day has no live picks
rows. Emptying picks on 2026-08-19 therefore also stopped the nightly writing
`runs/<date>/verify_intraday.json`. 2026-08-14, 08-17 and 08-18 have one;
2026-08-19 does not, and no night would have produced another until picks
refilled. The instrument for the project's top open question went quiet on the
night that question got most urgent, and nothing said so.

The check reads the collector bar file and the intraday feed and touches no
database at all, so it is now `verify_volume()`, called FIRST in `backfill()`
before any path that can return early.

A second sweep was added beside it. `_catchup_dates` asks which picks rows
still lack their true columns, so it can only ever find days that HAVE picks
rows. `unverified_sessions` asks which COLLECTED sessions were never measured,
which is the question that survives an empty table. It is bounded to sessions
the collector wrote a subscription list for, so an afternoon shakedown is not
mistaken for a premarket morning: 2026-08-13 holds 1,810 bars across 38 symbols
from 13:32 to 20:00 ET and BUILD_PLAN records that no verification is owed for
it. Without that test the sweep would spend 38 intraday calls measuring it and
write the answer into a preserved run directory.

Tonight's nightly will therefore measure 2026-08-19, which is the one reading
the register currently lacks.

`claim_verification_is_not_gated_on_picks` in test_entrypoints drives the day
with picks empty against a collector file that disagrees with the stubbed
vendor by ten percent, and asserts both that the summary is written and that
the disagreement is the one that was written, so an empty comparison cannot
pass it.

### timeout_s 293 to 537, on the same rule against better evidence

CRITERIA [analyst] set `timeout_s = 293` as three times the slowest of five dry
runs on 2026-08-14 (97.4, 86.5, 97.7, 91.1, 92.4 seconds). Four scheduled
mornings have since run. From analyst_usage.json, CLI duration: 89.1, 48.4,
98.5, 178.9 seconds, with output tokens 7,697, 4,000, 8,954, 16,005. From
data/job-status.jsonl, which times the whole step, the three mornings it covers
are 54.4, 107.5 and 185.3 seconds, against 19.0, 20.6 and 19.1 seconds for
every other step in the chain put together.

The rule is unchanged and its evidence is not, so the number is now three times
the slowest MORNING rather than three times the slowest dry run: 537.

Nothing has timed out. What forces this is the direction: 54.4, 107.5, 185.3 is
close to a doubling per session and it tracks output length rather than model
speed. One more session on that trend rides the first attempt past 293,
retries, rides the second, and hands a perfectly good morning the deterministic
plain table, which is the cost the 2026-08-18 regeneration work exists to stop
paying.

What it costs, arithmetic rather than assertion: two exhausted attempts now end
at 09:03:13 rather than 08:55:05. Both clear the 09:30 open, and both clear the
watchdog, whose [monitor] chain_due of 09:00 is only consulted on its half
hours, so the 08:55 pass reads NOT DUE and the next is 09:25.

The timeout note in CRITERIA carries the table and the arithmetic. BUILD_PLAN
item 5b is closed with the half that is not a code question left open: the step
doubling every session is not explained by raising the timeout, and 16,005
output tokens against a template whose nine sections did not change is its own
question.

## 2026-08-20: three defects the architecture pages already described correctly, and the pages brought back into sync

A full code review against the two architecture pages. What follows is what
changed; the reasoning is in DECISIONS.md the same date.

### Three code defects, all reproduced before fixing

**scan.py: an empty candidate pool ended the run with UnboundLocalError.**
`dropped_stale` was bound inside `build_packet`'s `if candidates:` branch and
read unconditionally in the payload beside `dropped` and `rank_stats`, which
were bound before it. A morning with an absent or empty watchlist therefore
lost the packet, the report, the picks rows and the email, where both pages say
the report goes out with no candidates and the holes named. Bound before the
branch now.

**scan.py: a watchlist that subscribes nobody wrote no gap.** `pool_candidates`
gapped on a MISSING watchlist and said nothing about a present one holding no
subscribed row, so that packet carried zero candidates and an empty
`gaps_to_fill`. It now names itself, with the pool row count and the
watchlist's own generated_at, and says the tables are empty for that reason
rather than because the market was quiet.

**market_today.py: the nightly calendar refresh deleted the cache before
fetching.** One vendor outage at 22:15 left no `data/exchange-details.json` at
all, and the guard's deliberate assume-open direction then applied to every job
the next morning. `get_details` takes a `force` flag that skips the memo and
the age check but not the fall-back-to-cache branch, and `--refresh` uses it,
so the old file stands until a new one is in hand.

### One test defect

**test_vintage leaked its calendar stub into every later suite.** The
`market_today.is_trading_day` replacement it takes in `main` was never
restored, and run_tests runs the suites in one process, so every suite after it
including test_entrypoints' calendar claims had been running against a weekday
rule with no holidays. Restored in a `finally`; the body moved to `_run`.

### Three claims added

`claim_scan_survives_an_empty_pool` drives the scan with a present-but-empty
watchlist and with no watchlist at all, and asserts a zero candidate packet
with both drop lists empty and gaps_to_fill non-empty reaches disk.
`claim_calendar_refresh_keeps_the_cache` seeds a calendar carrying Christmas,
fails the refresh, and asserts the cache survives and the guard still refuses
2026-12-25. Both live in test_entrypoints.py. The empty pool claim saves and
restores packet.json and watchlist.json around itself, because claim_analyst
runs next and reads the first.

### The two architecture pages, resynced

Both had drifted since the 2026-08-16 package split and the 2026-08-17
schedule change. Corrected in both: the universe job is Sunday 21:00, not
20:00; the discovery population is 2,754, not 2,745; the file map carries
artifacts, meter_sampler, quantifier_flags, build_archive, market_today,
job_status, site/, the eleven test modules, the ten research modules and
probe_alpaca.py at the src root; the nightly's steps are named as modules
rather than as the pre-split file paths; the "one vendor" rule is qualified to
the pipeline, with the Alpaca research probes named rather than left as a
silent exception; and the failure table carries the calendar row and the
corrected discover row.

The architecture page also gained nine components it had never carried
(C48-C58: job_meter_sampler.bat, meter_sampler, market_today, job_status,
artifacts, build_archive, quantifier_flags, site/PremarketDesk.html,
job-status.jsonl, quantifier-flags.jsonl and exchange-details.json), two
columns in the read and write matrix for the published archive and the job
trail, and its header now reads 56 components and seven job scripts as nine
tasks rather than 47 and six as eight.

Both pages gained a standing-state block at the top, because neither said any
of this: no email has ever been sent, the picks table is empty, collector
volume is the open question, and the quantifier guard has not fired live.

### Two consequences recorded rather than fixed

Both are now items 5a and 5b under "What remains" in BUILD_PLAN.md. The
nightly stopped writing `verify_intraday.json` when picks was emptied, because
that write sits after backfill's early return on a day with no live picks, so
the instrument for the top open question has stopped running. And the analyst
timeout's 3x headroom claim is now 1.6x against the slowest of four real
mornings, which is a measurement to redo rather than a fault to fix.

## 2026-08-19, eighth: the picks table is emptied, and nothing else is

### What was contaminated, measured before deciding

The premarket volume question reaches exactly one stored table. Two others were
checked and do not touch it: baseline, 130 rows, is built from EODHD intraday
calls rather than from collector bars, and gap_stats, 10,997 rows, is end of day
data. Neither has ever seen a collector bar.

picks did, through pm_rvol, pm_float_rotation and the two score components they
feed. All 51 rows:

| session | picks | day eligible | swing eligible | pm_rvol above 10 | worst pm_rvol |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-08-13 | 13 | 0 | 3 | 0 | all null |
| 2026-08-14 | 12 | 0 | 0 | 11 | 882,728.9362 |
| 2026-08-17 | 2 | 0 | 0 | 0 | 0.0724 |
| 2026-08-18 | 12 | 0 | 0 | 2 | 20.4751 |
| 2026-08-19 | 12 | 0 | 2 | 0 | 0.7418 |

Eleven of twelve picks on 2026-08-14 carry an impossible relative volume, six of
them above 100 and one at 882,728, which is the over counting session reaching a
stored decision. Their outcomes were filled on 2026-08-17, so any threshold fit
run today would have used those numbers as data.

Two things bound the damage. day_eligible is 0 on every session the project has
ever run, so the RVOL screen has never admitted a name and no false pick was
made. And pm_source_disagreement is 0.0 on every backfilled row: the collector's
premarket PRICES agree with the vendor to the cent, 19.5984 against 19.60 and
6.0002 against 6.09, so only volume was ever in question.

### What was done

picks is emptied, 51 rows to 0. Nothing else is touched: the bar files, the
packets, the reports, the archive, job-status.jsonl, baseline and gap_stats all
stand.

The rows were written to data/purged-picks-2026-08-19.jsonl first. They are the
evidence for an over count that still has no explanation, and the export is a
file rather than a table so it cannot reach a fit. Deleting it is one command
and nothing depends on it.

### The visible consequence

discover.py seeds one pool tier from prior picks, decayed by how many sessions
ago they appeared. With the table empty that source now returns
fetched_and_empty with sessions_considered 0, which is its designed honest empty
state rather than a failure, and the packet records it as such. The recent
runner tier will be thin until picks rebuild over recent_runner_lookback
sessions.

### What was deliberately not purged

The bar files are the only record of the 2026-08-14 over count, which is the one
open question with no candidate mechanism left. The packets are what the
verification pass read. job-status.jsonl is what closed the restart question,
and its GAPS, no collector records before 2026-08-15, were themselves a finding.
Deleting any of them would end an investigation that is still live, to tidy data
that is already quarantined behind data/UNVERIFIED.

## 2026-08-19, seventh: the replay is measured and is not the mechanism, and 2026-08-13 leaves the tables

### The replay, quantified before the probe rather than after

| session | first bar | subscribed | bars before | their share of session volume |
| --- | --- | --- | ---: | ---: |
| 2026-08-14 | 07:20:00 | 07:20:00 (intended, not observed) | 0 of 2,155 | 0.00% |
| 2026-08-17 | 06:26:00 | 07:20:01 | 67 of 3,102 | 0.47% |
| 2026-08-18 | 2026-08-17T15:59:00 | 07:20:02 | 71 of 3,231 | 0.92% |

Most of that is not stale. Splitting out the bars falling in the subscribe
minute itself leaves 1,467 genuinely early shares on 2026-08-17 and 4,376 on
2026-08-18, which is 0.11% and 0.27% of those sessions.

Re running the volume comparison with every pre subscription bar excluded:

| session | median abs diff all | excluded | aggregate socket/vendor all | excluded |
| --- | ---: | ---: | ---: | ---: |
| 2026-08-14 | 70.95% | 70.95% | 3.826 | 3.826 |
| 2026-08-17 | 88.43% | 88.36% | 0.103 | 0.103 |
| 2026-08-18 | 90.05% | 89.71% | 0.094 | 0.094 |

**Replay is not the over counting mechanism.** 2026-08-14 does not move at all,
and it cannot: that session has no job_status record and no subscriptions file,
so its subscription time is the configured 07:20 and its first bar is stamped
07:20, which means replay inside that minute is invisible at bar granularity.
The row records what the audit could see, not what was there. On the two
sessions where replay IS measurable it is worth half a point of median absolute
difference. A mechanism carrying a tenth of a percent of a session cannot
produce a 3.8x over count.

The over count therefore has no candidate mechanism left. No collector change
explains it either: the only commit touching collect_premarket.py before
2026-08-17's run is the package move, and the one that changed logic landed at
16:03 that afternoon, after the window closed, touching status frames only.

### Replay is now recorded rather than reconstructed

The audit had to rebuild the replay from a subscription time held in a different
file, and for one of three sessions that file does not exist. The collector no
longer discards an out of window trade: it aggregates it into a row tagged
`replay: true` with its reason and writes it to the same bar file.
read_bars_file, which every consumer goes through, filters those rows out of the
bars it returns and counts them into replay_rows, replay_volume and
replay_first_et instead. The evidence is in the file and cannot reach a total.

The packet keeps the two apart. collector_window_observed reports first_bar_et
from real bars only with contains_replay beside it; each candidate carries
pm_window_intended_start next to pm_window_start with pm_window_start_source
saying which is which; and pm_rvol_basis numerator_source names the window the
numerator covers with the scheduled one in brackets, instead of quoting the
schedule as though it were an observation. On 2026-08-19 every one of those
fields said 07:20 for a collector that started at 08:16.

Null on any of it means a file written before the tag existed, which is not
zero. The sessions in the tables above folded their replay into ordinary bars
and it is not recoverable from the file alone.

### 2026-08-13 is out of every comparison

It is not a premarket session. Its bars run 13:32 to 20:00, regular and after
hours trade; its three sidecar records are evening runs finishing 20:15, 20:35
and 20:56; and its 1,574 recorded messages cannot have produced its 270,086
trades, so whichever run wrote most of its bars recorded no stats at all.

It was carried as a second session at thirty eight subscriptions that looked
right, in the volume gap table and in the intraday check table written earlier
today, and its 69.77% was quoted in this changelog and in DECISIONS as one of
two good sessions. Both rows are removed, both quotes are corrected in place,
and the two tables that still name it are the run history and the tape window,
where it is labelled NOT A PREMARKET SESSION because those tables are the
evidence for its removal. Removed rather than annotated in the comparisons,
because a row in a comparison table gets counted whatever the note beside it
says.

There was only ever one session that looked right.

## 2026-08-19, sixth: the run history closes the restart question, and the probe is repointed at off exchange volume

### Reading the collector's own history first, because it cost nothing

Two records, and they cover different sessions. job-status.jsonl was born at
12:24 on 2026-08-14, hours after that morning's window closed, and the collector
step was not wrapped in it until 2026-08-15, so there is no job_status record for
the collector on either 2026-08-13 or 2026-08-14 and there cannot be one. The
collector's own stats sidecar does cover them, and neither of those mornings was
refused, so nothing is missing from what it recorded.

| session | runs | non zero exits | refusals | window covered |
| --- | ---: | ---: | ---: | --- |
| 2026-08-14 | 1 (sidecar) | not recorded | none | one connection, finished 09:25:00 |
| 2026-08-17 | 1 | 0 | 0 | 07:20:01 to 09:25:00, one connection, no reconnect |
| 2026-08-18 | 2 | 1 | 1 | 07:20:02 to 08:50:51 REFUSED, then 08:55:09 to 09:25:00 |
| 2026-08-19 | 2 | 1 | 1 | 08:16:51 to 08:35:28 REFUSED, then 08:37:14 to 09:25:00 |

Neither morning the volume comparison rests on was interrupted. 2026-08-17 is a
single unbroken run and carries the 88.43% shortfall; 2026-08-14 is a single
unbroken run and carries the reading that looked right. And a refusal does not
move the number: 2026-08-18 was refused and restarted and sits at 90.05% against
2026-08-17's uninterrupted 88.43%, a point and a half apart.

The restart question is closed, independently of the probe, and it agrees with
the probe.

### Two things the history exposed

2026-08-13 is not a premarket session. Its bars run 13:32 to 20:00, regular and
after hours trade, and its three sidecar records are evening runs. Its 1,574
recorded messages also cannot have produced its 270,086 trades, so whatever run
wrote most of its bars recorded no stats at all. It has been sitting in the
comparison tables as though it were a morning.

And the vendor's replay is in every session before the guard landed: 2026-08-17's
first bar is stamped 06:26, an hour before the collector subscribed, and
2026-08-18's is stamped 15:59 of the previous afternoon.

### The probe now asks the off exchange question first

The collector reads s, p, v, t, dp and ms off a trade message and nothing else.
It reads no condition code of any kind, its only off exchange signal is the dp
boolean, and dp has never once been true in any bar the project has written.

The probe reports three numbers per symbol now: total messages, messages the
collector's own rule would call an off exchange print, and the vendor's figure
for the same minutes. Plus a census of every key the feed sends, split into the
six the collector reads and everything it ignores, and every code-like value
with a count, so a code the parser has never heard of appears as itself rather
than as a missing number.

The third number is vendor SHARES, not trade count. EODHD's 1m bar is timestamp,
gmtoffset, datetime, open, high, low, close and volume: it publishes no trade
count, so there is nothing to compare a message count against, and the tool says
so in its own output rather than substituting quietly.

It is a separate command, `--compare FILE`, because the vendor does not publish a
session until it is over and the probe runs premarket. That pass costs one
intraday call per watched symbol and is the only quota this tool has ever spent;
the bat file's claim that it spends none is corrected to match.

A probe result written before the census carries no census key, and reporting
that absence as "the feed sent no codes" would be this project's own recurring
mistake made by the tool built to catch it. It prints as NOT MEASURED.

## 2026-08-19, fifth: five ways a known gap reached the reader as nothing at all

Twenty agents read runs/2026-08-19/report.md against its own packet, each
finding handed to an independent skeptic told to refute it. Five sections came
back clean: the disclaimer against all eight of its template conditions, the
twelve gapper blocks with their twenty eight headlines and every numeric token
traced, the watchlist cells and headers, the nine market rows and fifteen
earnings rows, and the trap section. Nothing was invented and every number
traced to a field.

What survived is one shape five times over. Something the code already knew was
partial, missing or broken reached the reader as nothing at all.

### The report said an RVOL scored zero when it was never computable

"Across the set the premarket RVOL component scored zero, since observed
premarket volume sat far under the 20 session baseline." Wrong three ways.

EL and YMM carry no premarket_rvol component at all. Their volume slot holds
premarket_float_rotation, substituted because pm_rvol is null, so a ratio that
was never computed is narrated as one that was computed and came out low. The
stated cause is then backwards for exactly those two: EL traded 2,231 shares
against a baseline median of 989 and YMM 1,617 against 670.5, both more than
double the baseline, and the packet's own recorded reason is the 1,000 share
floor on the DENOMINATOR. And for the other ten, pm_rvol_basis.is_lower_bound
is true on every one, which the report never says.

That last part was ours, not the model's. is_lower_bound has been computed,
stored per candidate and surfaced nowhere. The disclaimer named only the two
nulls, which told the reader the other ten had complete volume evidence. It now
reaches gaps_to_fill, which is the one list the template requires the disclaimer
to carry, and on today's packet it names all ten.

The template gained the three rules the sentence broke: a component that is
absent is not a component that scored zero, the reason a number is missing comes
from pm_rvol_reason and is never supplied, and a lower bound is said wherever the
ratio is discussed.

### The funnel's top was misdescribed

"Of 36 names the collector heard" is not what 36 counts. subscribed_considered
is what reached the ranking, after the no coverage and stale price drops. The
collector produced bars for 40 of the 42 subscribed names. The same sentence
then went on to name OPRA, FLNG, VELO and AVAH as dropped for a stale price, and
all four have bars in today's snapshot, so it named four symbols the collector
did hear that its own count excludes. The template said `heard`; it says
`ranked` now, with the difference written down.

### A sentence the template asked for that the template itself falsified

"WB and MH ... carry no premarket price and appear nowhere else in this report."
They appear twice in the disclaimer and again in the Summary, both required by
this same template. The clause is gone and its return is a test failure.

### job_health was silent on a morning the collector died

overdue() measures staleness of last_success in whole trading sessions, and
every window is one session or more. A step that failed at 08:16 and was rerun
at 08:37 is therefore current by every measure the packet had, and so is a step
that failed this morning having succeeded yesterday. The packet read
{"line": null, "overdue": []} on the morning the collector was refused and lost
fifty minutes of window, and the report's readers got the symptom, twelve names
with late premarket windows, with no route to the cause.

failures_today() is a separate reading for a separate question: steps that
recorded a non ok outcome today, whether or not a rerun fixed it, because the
rerun is the thing a reader would otherwise have to guess at. Repeats of one
step collapse to one phrase with a count, and the list is capped at the same
CRITERIA number the overdue side uses, because a line nobody reads is the
failure the whole mechanism exists to prevent. Today's morning would have
carried: "Scheduled jobs: collector failed at 08:16 ET (SubscriptionRefused),
and a later run succeeded." A clean morning still says nothing.

### collector_snapshot reported a silent morning over 54,407 trades

A refused run wrote {"subscription_refused": true} as its ENTIRE record, so its
connection and message counts died with it, and read_run_stats then summed the
missing keys as zeros. The packet said messages 0, connections 0, runs 1 for a
morning that had already folded 14,680 trades before the refusal and 39,727
messages after it.

Both halves are fixed. The counters now travel with the exception, so the
refusal is a fact ABOUT the run rather than a replacement for it. And every
counter in read_run_stats starts at None and stays None until some run carries a
number, which is the reasoning the status_frames comment had already spelled out
next door and which turned out to apply to all of them. Today's packet would now
read runs 2, connections 1, messages 39,727.

### The claims

src/tests/test_evidence_gaps.py, six claims and one new suite entry. Each was
checked by reintroducing the defect and watching the suite go red, including the
template drift guard, which had to have its own prohibitions reworded first
because they quoted the strings they ban.

## 2026-08-19, fourth: the subscription cap is innocent, and the sessions that looked right were wrong the other way

### The probe ran and answered

Rescheduled to 09:35 after the power took the 06:20 slot, eight arms, none
refused, 26 minutes, no quota. Median B/A message rate across the eight watched
ETFs is 0.87 at fifty subscriptions against eight. Arm B's filler came from
today's real subscription list and pushed 66.5 messages a second, fourteen times
what the collector sees on a fifty symbol morning, and lost nothing.

The fifty symbol cap does not starve delivery. The fix that was under
consideration, subscribing to fewer names, would have bought nothing and cost
the watchlist.

### The correlation it was testing has fallen apart

The collector's own intraday check had only ever been run on two sessions at a
time. Run across all four published sessions this afternoon, the median absolute
volume difference against EODHD's bars is 70.95% at thirty seven subscriptions
and 88.43% and 90.05% at fifty. The shortfall is in every published premarket
session including the one this project called good.

[corrected 2026-08-19: this paragraph read "69.77% and 70.95% at thirty seven
and thirty eight subscriptions" and "the two this project called good". The
69.77% was 2026-08-13, which is not a premarket session: its bars run 13:32 to
20:00 and its sidecar records are evening runs. It has been removed from every
comparison table, and there was only ever one session that looked good.]

It was called good on the strength of SPY, and SPY on 2026-08-14 was not
short at all. It was 373.88% OVER EODHD's own bars for the same minutes. The
collector reported thirteen times the vendor's TLT and ninety five times its DIA
that morning, and a tenth of both three days later. That is a measurement wrong
in both directions, and the subscription count was the only difference anyone had
noticed between the two kinds of wrong.

### Two mechanisms ruled out with it

Trades per hour of the window, read from the bars, show no decay inside any
session and the same curve shape across all three: the fifty symbol mornings are
down by about the same factor in their first hour as in their last. Nothing is
being throttled as the hold lengthens, so a two minute arm is not obviously too
short to see the effect.

The dark_pool_volume field is 0.0 in every bar of both sessions checked, whole
file totals. Consolidated prints arriving unattributed are not hiding in it. The
field has also therefore never been populated in any bar the project has ever
written, which is a separate thing to look at.

### What could not be measured today

EODHD has not published 1m intraday bars for 2026-08-19: the probe's own window
returns zero rows at 10:05, where the same clock window on the two previous
sessions returns 27 rows each. That fetch is the first socket against bars
reading with a known subscription size, a known symbol list and no collector in
the path, and it is a tomorrow job against the per symbol share counts already
written to data/socket-cap-probe-2026-08-19.json.

### The probe is re armed, and the reason is in its own docstring

The docstring says a result after 09:25 is on a different tape from the one the
defect appears in and that a positive result there is worth confirming
premarket. This is a negative result that contradicts the session evidence,
which needs the premarket run more rather than less. The identical script,
premarket, changes exactly one variable.

Re arming it needs a hand, because the scheduler change was refused:

    schtasks /Change /TN "\PremarketDesk\probe-socket-cap" /SD 08/20/2026 /ST 06:20

## 2026-08-19, third: the collector refused its own slots and died, and the window fix proved itself live

### What the morning did

The power was off at 06:20, so the socket cap probe never ran and neither did
discover at 07:15 or the collector at 07:20. The machine came back and the
watchdog restarted the chain: discover at 08:21, the collector at 08:16, the
nightly catchup at 08:21.

The collector then streamed 50 symbols happily from 08:16, folding 14,680
trades into 486 minutes. At 08:34 the remote host closed the connection. The
reconnect went out about a second later and the server refused it with
{"status_code":422,"message":"Symbols limit reached"}. The collector treated
that as fatal, exited 1, and the last 50 minutes of the window were lost.

The slots it was refused were its own. A hand restart at 08:37:13 subscribed
without complaint, so the account had released the dropped connection's 50
symbols somewhere inside 105 seconds. The process competing for the pool was
the collector, one second in its own past.

### The window fix worked, on its first morning

Yesterday's guard against replayed trades refused eight this morning, and two of
them were dated 2026-08-18: UUP at 15:53:13 and SFL at 15:59:56, the previous
afternoon. Without it those would have been folded into today's premarket
volume and today's premarket window would have looked as though it opened at
07:00 on a morning nothing was listening before 08:16.

That is the first live confirmation that the vendor replays a stale last trade
per symbol on subscribe, rather than an inference from archived files.

### A refusal is retried now, not fatal

The reasoning that made it fatal is corrected in place in both CRITERIA.md and
the exception's own docstring, because it was wrong when written rather than
overtaken: it said a refusal means another process holds the slots and
retrying would be refused every time until the window is gone, and it was
written from the vendor's documentation of the cap because no refusal had ever
been seen.

Refusals are retried max_subscription_retries times on a
subscription_retry_wait_s wait. The asymmetry is the argument. If the slots are
ours, waiting gets them back and the morning continues. If they are genuinely
somebody else's, four waits cost four minutes of a two hour window and the run
then fails exactly as it used to. The old behaviour paid the whole window to
avoid a four minute delay.

Two smaller corrections came with it. The exception text no longer asserts
"Nothing was collected", which it cannot know from inside a message handler and
which was false this morning over 14,680 folded trades. And the exit line now
reports what the run actually folded and calls the bar file a PARTIAL window,
rather than printing fixed text saying the run was never subscribed.

### The subscription probe, rescheduled and repaired

The 06:20 run was lost to the power. Two things changed before rescheduling it.

Its guard was a fixed hour, refusing anything after 07:10, which was the only
free slot when it was meant to run before the morning. That hour then refused
every remaining moment of a day in which the socket was free from 09:25 onward.
The constraint is the collector's window, not a time of day, and the guard asks
CRITERIA for it now and refuses any run that would overlap.

And the probe had the defect this morning revealed. It closes arm A and opens
arm B, and an arm B asking for 50 while arm A's 8 were still held by the
account would have been refused and would have measured a zero that means
nothing. It settles 90 seconds between arms now, and an arm that is refused is
marked and kept out of the rate table rather than averaged into it.

Rescheduled for 09:35 with StartWhenAvailable set, so the next outage delays it
rather than losing it.

### A third session at fifty subscriptions

Today is the third morning at 50 and it does not overturn the correlation. Over
the same eighteen clock minutes, 08:17 to 08:34:

| symbol | 08-17 | 08-18 | 08-19 |
| --- | ---: | ---: | ---: |
| SPY trades | 193 | 126 | 203 |
| QQQ trades | 230 | 207 | 267 |
| all symbols | 4,807 | 5,094 | 14,258 |

Today is 3.5x busier in aggregate, and that is AVGO and MU carrying news:
AVGO alone went from 116 and 134 trades to 3,983. The index ETFs did not move.
SPY sits at 203, 193 and 126 trades in eighteen minutes across the three, which
is about 11 a minute, against 171 a minute on 2026-08-14 at 38 subscriptions.
The collapse is present today too.

## 2026-08-19, second: the collector folds a previous session's trade, and the volume gap is narrowed to the subscription size

### A replayed trade is not this morning's tape

The EODHD subscription replays a last trade per symbol when it lands, carrying
its ORIGINAL timestamp, and the collector folded those into bars. On 2026-08-18
that put three bars dated 2026-08-17 into the 2026-08-18 premarket file, one
stamped 15:59 the previous afternoon. Forty-five more were stamped between
07:00 and 07:19 on a morning the collector connected at 07:20:02. Every one
carried exactly one trade, which is the signature.

The volume is 0.11 and 0.27 percent of the two sessions and that is not the
point. pm_window_starts_late is derived from the first bar present, so a
replayed 07:00 print makes a window the collector reached at 07:20 look covered
from 07:00, and the flag that exists to warn a reader about exactly that says
nothing. It is a vintage defect in miniature.

The collector now refuses any trade stamped outside the window the run is
collecting, counts them, names five in the log and records the count in the run
stats sidecar. The window opens at the configured start or at the process start
if that is earlier, so an ad hoc evening run does not refuse its own tape, and
a builder given no window refuses nothing at all. Proven against the real
2026-08-18 file rather than a fixture: 48 refused, two of them dated to the
previous session.

The window's open edge is floored to its minute, and the suite is why. Trade
timestamps arrive as whole seconds, so a trade printed in the same second the
process started carries an epoch up to a second below an open computed to the
microsecond. The replayed socket in test_entrypoints caught it immediately:
thirty trades refused as early, and a collector that wrote no minutes at all.
A fix that discards the first second of every morning would have been a worse
defect than the one it was fixing.

### The volume gap is not any of four things, and is narrowed to one

Four mechanisms are dead on the archived data. Mean trade size per bar is
ordinary in every session, so the size field is read correctly. Messages equal
trades folded in every session, so nothing is lost inside the collector. One
connection, zero reconnects and zero status frames on both clean mornings. And
the trade rate plotted by ten minute block is flat across the whole window on
both, with no step down and no recovery, which is not what a client falling
behind its socket looks like.

What separates the sessions that look right from the ones that do not is the
size of the subscription. Thirty-eight symbols on 2026-08-13 and 2026-08-14,
fifty on 2026-08-17 and 2026-08-18, fifty being the documented cap. SPY fell
from 171 trades a minute to 5.8 across that change while EODHD's own bars for
the same mornings moved by a factor of 1.3.

Two sessions each side is a correlation. src/research/probe_socket_cap.py makes
it a measurement: the eight context ETFs as a watch set present in both arms,
arm A subscribing to eight and arm B to fifty, alternating so the rising
premarket rate cannot be mistaken for the effect, and the replayed first message
per symbol discarded. It refuses to start after 07:10 because the fifty symbol
pool is account wide and a probe holding slots would starve the morning it is
meant to explain. Registered as a one time task for 06:20 on 2026-08-19, and it
spends no quota.

No collector behaviour was changed on the strength of the correlation. The
delivery gate stays where it is until the probe answers.

## 2026-08-19: the report scan's assumption is measured, and the sampler is exempted by behaviour

### Does the report scan have the hole the instruction scan had? Measured: no, today

Yesterday the instruction scan moved to paragraphs because a banned word split
across a line break read past it, and the report scan was left on lines on the
grounds that model output wraps nowhere. That was an assumption about a format
nobody controls, made in the same commit as the discovery of the identical bug
in a file that is controlled. It is measured now, over the three archived
reports.

A sentence continues across a line break if a prose line ends in a letter, a
comma or a semicolon and another prose line follows it immediately. By that
test:

| Session | Prose lines | Adjacent pairs | Split sentences | Median width | Max width |
| --- | --- | --- | --- | --- | --- |
| 2026-08-14 | 29 | 5 | 0 | 284 | 860 |
| 2026-08-17 | 22 | 5 | 0 | 207 | 792 |
| 2026-08-18 | 36 | 11 | 0 | 295 | 933 |

Zero split sentences across 21 adjacent prose pairs. The model is not wrapping
at any width: the median prose line is between 207 and 295 characters and the
longest is 933. Running the paragraph scan over the same three reports finds
exactly the hits the line scan finds, twelve, eight and ten, so the hole exists
in principle and has not fired.

Two adjacent pairs in 2026-08-17 did survive a looser first test, and they are
worth naming because they are the near miss. The model writes a candidate's
name as a bold line of its own and the block's first sentence on the next line,
so `**HTHT, H World Group**` sits directly above the sentence about it. Those
are two units of prose on consecutive lines, which is the structure a wrap
would need. They are not a split sentence, and no banned pair spans either
join, but they show the format is "sentences are never split" rather than "one
paragraph per line", and it is the first of those the line scan actually
depends on.

So the answer is no, on measured evidence, from a sample of three reports and
21 adjacent pairs. That is a small sample and nothing enforces the format. The
scan is unchanged in this commit deliberately, for the same reason it was left
alone yesterday: changing a live guard's behaviour in the same week its
enforcement setting changed would make the first week of warn-mode counts
uninterpretable. Revisit after that week, with this measurement as the baseline
to compare against.

### The sampler is exempted by its behaviour, not by its directory

The forensic sweep on 2026-08-18 turned up a live intermittent isolation
failure: the real logs/ sits inside the tree the suite photographs, and the
scheduled meter sampler appends to it from outside the suite at :00 and :30
every hour, so a run straddling one of those instants failed on a path the
suite never touched.

logs/ is NOT exempt, and the reason is not tidiness. A test writing there would
pollute the meter trail, and data/quantifier-flags.jsonl is the telemetry the
analyst guard's word list is about to be tuned on. Blinding the check to that
neighbourhood would blind it to the one contamination that would corrupt the
measurement, at exactly the moment the measurement starts.

What is exempt is the sampler's behaviour, and only when three conditions hold
together. The path is one of the two files the sampler writes, by name:
logs/meter-<quota day>.log and logs/meter-sampler.log. The change is a pure
append, with every byte that was there before still there, proven by a sha256
of the previous contents rather than by a size comparison. And the appended
bytes parse as what that file holds, which is JSON rows carrying at, quota_day,
source and step for the trail, and the sampler's own line grammar for the
stdout log. A truncation fails, a same length rewrite fails, an mtime touch
that adds no bytes fails, a new file under logs/ that is not a dated sampler
trail fails, and any other path under logs/ fails.

UTC midnight is handled explicitly rather than left to fail once a month. At
00:00 UTC the sampler starts a new meter-<quota day>.log instead of appending
to yesterday's, so that night's run sees a CREATED path. It goes through the
same three conditions with a zero length previous file, rather than through a
separate rule that could disagree with this one.

src/tests/test_sandbox.py is new and is in SUITE. Six claims: a tick appending
to both files passes; the midnight creation passes while a new job log under
logs/ does not; truncation, a same length rewrite and a rewritten prefix are
all refused; five appends the sampler would not have written are refused; a
test writing a job log, a new file under logs/ or the quantifier flag log is
still caught; and the exemption is anchored to the real logs directory rather
than travelling with the filename, which matters because conftest redirects
config.LOGS_DIR into the sandbox and an exemption reading it at check time
would silently exempt nothing.

Two intermittents were found by writing those claims, and both were in the new
code rather than in the thing it was checking.

The snapshot took the file size from stat and the digest from a later read.
The sampler appends between those two, so the recorded pair could describe a
file that never existed, with a digest covering more bytes than the size
claimed. The append check would then compare the wrong prefix and report an
ordinary tick as a rewrite. That is the intermittent this exemption exists to
remove, reintroduced one layer underneath it. Both now come from one read.

And one claim asserted an mtime-only touch by rewriting identical bytes and
trusting the clock to tick. It passed alone and failed inside the full suite,
where the mtime landed on the same value and the snapshot saw no change at all
rather than a change the exemption refused. It sets the mtime explicitly now.

### Proven on the real machine, not only in a temporary directory

The claims run against a fabricated logs directory, so they prove the predicate
and not the situation. The situation was proven separately by running the whole
suite back to back for seventeen minutes across a real sampler tick: 194 runs,
of which run 155 was in flight from 01:00:00 to 01:00:05 with the sampler
firing at 01:00:01, and it passed. Eight runs started within twenty seconds of
the tick and all eight passed.

Two of the 194 failed and neither was the sampler. One was this CHANGELOG being
edited while the loop ran, which is the check doing its job on the person
writing about it. The other named the path that could not be named yesterday.

### The path from 2026-08-18, identified

`.git/FETCH_HEAD`, 106 bytes, holding the current HEAD sha and the branch it
was fetched from. Run 105 of 194 failed on it at 00:55:51, reported as
"modified, mtime only, size unchanged at 106 bytes".

Watched directly afterwards, the behaviour is a truncate and rewrite of
byte-identical content. At 01:05:54 the file was 0 bytes with the sha256 of an
empty file; one second later it was 106 bytes again with the sha256 it had
before, `d518a521...`. Something outside this repository fetches on a timer:
the two observed touches were 00:55:51 and 01:05:54, ten minutes and three
seconds apart. A suite run takes about five seconds, which puts the collision
rate near one percent, and one percent is the rate at which a failure gets
rerun rather than investigated.

This is not the lost name recovered, and it should not be recorded as though it
were. It is an independent identification, and it fits every fact yesterday's
entry established: a modification rather than a creation, so the path count was
unchanged at 1644 on both sides; exactly one path; and not reproducible in four
consecutive reruns, which at one percent is unremarkable.

It also explains the one thing yesterday's forensics could not. The mtime sweep
found nothing changed inside the failing run's window, and that was read as
evidence that nothing had. A file rewritten every ten minutes carries only its
most recent mtime, and the sweep ran hours later, so a touch at 16:40:45 had
been overwritten dozens of times before anybody looked. The sweep could not
have found it. That is a limit of the method rather than a fact about the tree,
and the same sweep would fail the same way on any file with a short rewrite
cycle.

It is recorded and NOT fixed here. The obvious exemption, that a path whose
content digest is unchanged is not a change, does not cover the whole
behaviour: there is a real window during the rewrite when the file is zero
bytes, and a snapshot landing there sees a size change with content that
genuinely differs. Covering that means allowing an empty file to stand in for
its own contents, which is a wider hole than the sampler one and belongs to the
owner rather than to this commit.

## 2026-08-18, sixth: the guard goes to warn, its documents stop provoking it, and one lost path is written down

### Warn until the template stops asking

The fifth entry made a flag cost the narrative instead of the morning. It did
not ask how often a flag would fire. Running the guard over the three archived
reports answers that: 2026-08-14 flags twelve times, 2026-08-17 eight, and
2026-08-18 ten, with `no` accounting for eighteen of the thirty. Enforcing
today would mean the plain table on most mornings, which is a guard working
correctly and producing the wrong outcome daily.

So CRITERIA gains analyst.quantifier_guard, reading `warn`. Every flag is
logged with outcome `warned`, printed with its sentence, and named on the
report's disclaimer line. Nothing is regenerated and nothing falls back. The
week of telemetry the flag log was built for still accumulates, and it
accumulates under the template that provokes the flags, which is the more
informative half: a log filling now says which words and which instructions are
responsible, where one filling after the provocation is removed would only say
the remainder is quiet.

Three things have to be true before it reads `enforcing`, and they are written
into CRITERIA beside the knob rather than left in a commit message. T2, T3,
T15, T16, P1 and P2 resolved, so the instructions stop asking for a claim about
the set the model cannot compute. A real morning running clean, not a fixture.
And dispositions recorded against the flags already logged, because the word
list was going to be tuned on them and flipping first would mean tuning on a
sample that stopped growing.

An unrecognised value fails closed to enforcing and says so. A typo must not be
a silent way to switch the guard off.

The disclaimer note is a judgment call worth naming. Warn mode publishes a
claim the guard calls uncheckable, so the report says on its disclaimer line
that it carries one, how many, and which flag ids. That is the same rule the
fallback follows: a report that degraded quietly would be a report lying about
its own provenance, and a published flagged sentence is a quieter degradation
than the plain table, not a smaller one. It also puts the flag in front of the
one person who can judge it, on the morning it fired, which is the whole
difficulty with a log nobody opens.

### The guard and the instructions can no longer drift

Three times in three commits the instructions asked for exactly what the guard
forbids. The template asked for "the most common failed condition", a
superlative it gave the model no way to compute, and got a false universal
back. The fallback wrote the banned words in its own prose, so an analyst
timeout on an empty screen produced a report the guard rejected and therefore
no report. And rule 13 still said `no` was allowed one commit after `no` was
banned. That is the class the watchlist headers had, and it was closed there by
a claim asserting all four sources agree rather than by anyone being careful.

Claim 11 is the equivalent. REPORT_TEMPLATE.md, prompt_analyst.md and the
fallback's emitted prose are the three places report wording is written, and
all three are now checked against analyst.banned_words() and
analyst.set_words() rather than against a copy. The claim carries no word list
of its own, deliberately, since a fixture with its own copy would be a fourth
place to drift. Rule 13 now names the two lists on their own lines and the
claim asserts they equal the tuples exactly, so the prompt the model reads and
the guard the code enforces are the same list by construction.

Both instruction files were reworded to pass it. Two kinds of change, and they
are not the same kind. Instructions that ASKED for a banned word were reworded
with their meaning intact: "name every candidate whose pm_rvol is null" became
"name the candidates whose pm_rvol is null", which requests the identical list.
Whether the template should be asking for that list at all is T2 and T3 and is
still queued and still unanswered. Prose that QUOTES a banned phrasing as a
specimen keeps saying it, inside backticks, because a document that teaches "do
not write this" has to be able to write it. Backticks are how a document
already marks text it is exhibiting rather than uttering, so the exemption is
mechanical rather than a judgment call. A specimen has to fit on one line.

The instruction scan is stricter than the report scan in one way, and on
purpose. It reads a paragraph at a time rather than a line at a time, because
these files are hand wrapped at about seventy-eight columns and a banned word
routinely ends one line while its set word begins the next: "including mornings
when no / candidate is eligible" was in prompt_analyst.md and a line-at-a-time
scan read straight past it. Model output wraps nowhere, so the report scan is
left alone rather than changed under a live guard. Numbered rules are their own
units, or the last words of rule 5 would land within six words of the first
words of rule 6 and invent a pair neither sentence makes.

Proven by injection rather than by assertion. A banned word added to
REPORT_TEMPLATE.md, to prompt_analyst.md, and to fallback_report's own prose
each turned the suite red, and the sources restored green.

### The path the tree check named on 2026-08-18, and could not be made to name again

Recorded because an intermittent isolation breach that is only remembered is
one nobody can chase. The honest version first: the path's NAME was lost. The
run's output was piped through a grep that did not match the line carrying it,
so it never reached the transcript. It is not recoverable.

What is known. The run was the full suite immediately after the flag backlog
clamp was patched into monitor_jobs.py, at roughly 16:40:45 ET, bounded by that
file being written at about 16:40:35 and the next suite run finishing before
16:42:03. It reported exactly one changed path and the path count read 1644
both before and after, so it was a modification rather than a creation or a
deletion. It did not reproduce on the four runs that followed, one of which
rewrote src/ops/monitor_jobs.py first specifically to recreate the condition of
a source file having just been touched.

A forensic mtime sweep of the whole tree afterwards found nothing modified
inside that window except files written by hand, and .git/index was untouched
between 16:30 and the commit at 16:43:37. That rules out the cause this same
check was corrected for on 2026-08-14, where config.build_identifier() ran `git
status` and the index refresh it triggered failed the run; `--no-optional-locks`
is still doing its job. [corrected 2026-08-19: the sweep finding
nothing was read here as evidence that nothing changed, and it is not. An mtime
sweep run hours later can only see each file's MOST RECENT write, so it is
blind to any file with a rewrite cycle shorter than the delay before looking.
`.git/FETCH_HEAD` is rewritten about every ten minutes and was caught failing a
run on 2026-08-19; it could not have shown up in this sweep whether it was
responsible or not. The statement about .git/index stands, since that file is
written only on commit.] One candidate cannot be excluded: src/ops/monitor_jobs.py
itself, whose mtime was overwritten at 16:42:03 by the reproduction attempt,
which destroyed the only evidence that would have distinguished it.

The sweep did turn up a live intermittent breach of the same shape, which is
worth having even though it is not this one. The real logs/ directory sits
inside the tree the check photographs, and the scheduled tasks append to it
from outside the suite: the meter sampler fires at :00 and :30 every hour and
writes logs/meter-<quota day>.log and logs/meter-sampler.log, and at UTC
midnight it creates a new dated file rather than appending to the old one. A
suite run straddling one of those instants fails the tree check on a path the
suite never touched, and a run straddling UTC midnight fails on a created path.
The sampler fired at 16:30:03 and 17:00:01 on 2026-08-18, so it is not what
happened at 16:40:45, but it will happen.

[answered 2026-08-19: a second external toucher was found and is the likelier
candidate for this run. See the 2026-08-19 entry above.]

## 2026-08-18, fifth: a quantifier flag can no longer cost the morning its report

### The guard was charging the wrong price

The quantifier guard shipped yesterday returning exit 2 on a hit. The morning
chain stops on the first non-zero code, so render, deliver and archive never
ran. One sentence, and the morning got nothing at all, from a guard whose own
false positive rate is still a sample of six with nothing judged. That price is
what gets a guard commented out at 08:46, and this project's whole argument for
mechanical guards is that they survive the mornings nobody has time for.

A flag now buys a regeneration first. The rejected sentences are appended to the
piped document, the model writes the report again knowing exactly what to avoid,
and only if that second answer flags too does the morning drop to the plain
table fallback, with the reason and the offending sentence stamped into the
disclaimer line beside the flag id. Exit zero either way. The worst a false
positive can now do is remove the narrative from one morning, which is the trade
the guard's asymmetry argument already assumed it was making.

One regeneration and not more, from CRITERIA analyst.quantifier_regenerations. A
second failure against a correction that names the sentence is evidence about the
report or about the guard, not bad luck, and every attempt costs another
timeout_s off a clock that ends when the market opens.

Containment moved ahead of the quantifier check in the same restructure, and the
order matters twice. An invented ticker is fabricated evidence, still exits 2 and
still gets no regeneration and no fallback, because a second roll of the dice is
not the answer to a report that made something up. And asking that question first
is what makes the withheld disclaimer safe to quote from: a sentence stamped into
it has already been proven to name no ticker the packet does not carry.

### The fallback itself was failing the guard

Found while building the above, and it was live. The deterministic fallback
wrote "No candidate is day eligible this morning", "Every candidate carries a
found catalyst and full evidence" and a Summary reading "Day eligible: none",
and the guard ran over whatever text reached the disk, fallback included. So an
analyst timeout on a morning where either screen was empty produced a fallback
report that tripped the guard and exited 2. The path built to guarantee a report
on a bad morning was guaranteeing the opposite, and it had been that way since
the guard shipped.

Its prose is now written in counts, the same way the template's is: "0 of 12"
carries the denominator that "none are eligible" throws away, and a reader should
not have to learn two dialects depending on which pass wrote the morning. The
guard is separately no longer run over this function's output at all, since the
withheld disclaimer quotes the offending sentence on purpose and evidence has to
be quotable. Both, not either: the exemption now covers only the quoted evidence,
and a test asserts the fallback's own prose would pass the guard anyway.

### prompt_analyst.md rule 13 was telling the model to break the guard

Rule 13 ended with "Writing 'no candidate has X' is still allowed, since no is
not one of the banned words". `no` joined the ban in the fourth entry above and
the rule was not updated with it, so for one commit the prompt instructed the
model to write a sentence the guard would reject. Corrected, and the rule now
also says what a hit costs, since the model is the one being asked to avoid it.

### The watchdog counts the flags nobody has judged

Dispositions are recorded by hand, which is the same shape as the failure that
had pool_recall raising every night for a week while writing nothing and
DECISIONS citing its evidence as accumulating. A flag log that fills while
nobody judges means the rate never prints and the word list gets tuned in a
month on the intuition it was written with.

monitor_jobs now names the unjudged count on every pass, beside the jobs. A flag
raised this morning has not been ignored, so it is named without counting as a
problem; past CRITERIA monitor.flag_backlog_after_days the oldest one has
survived a week of mornings and joins the problem count with the command that
lists them. The rate tool also splits flags by outcome now, which answers the
other question tuning needs: not how often the guard is wrong, but what being
wrong costs. A word that regenerates away is a nuisance, a word that reaches the
fallback is a bill.

A morning the regeneration rescued is deliberately NOT recorded as a failed
analyst step. The report went out; calling the step failed would fire STEP FAILED
on a good morning, and a watchdog line that fires on good mornings is one nobody
reads by the end of the month. It is recorded in the flag log with its outcome,
in analyst_usage.json, and in the watchdog's unjudged count, which are three
places to find it and none to trip over.

Two claims added to test_containment: a model that will not stop asserting a
quantifier produces the plain table with its sentence and flag id in the
disclaimer and exit zero, and the watchdog names the unjudged count and calls a
week of silence a backlog. The one-parameter stub in test_entrypoints was
updated with them, having been the thing that would have TypeErrored on the
first morning the guard fired.

## 2026-08-18, fourth: the guard's flags are logged, `no` joins the ban, and the Summary counts stop being derived

### The rate is measured now, not asserted

The guard shipped yesterday with a false positive rate eyeballed at one in six
from a single afternoon's reports. That is defensible for a day and folklore
within a month, and this project has watched guards decay exactly that way: a
claim swallowed exceptions for a week, a calendar status was ignored, and
pool_recall wrote nothing nightly while DECISIONS cited its evidence as though
it had. A blunt guard on the morning path, where a hit blocks the report, is the
obvious next candidate the first time somebody is in a hurry at 08:46.

So every flag now appends to data/quantifier-flags.jsonl carrying the sentence,
the matched word, the session and a null disposition, and ops/quantifier_flags.py
lists them, records a verdict and prints the rate counted from those verdicts. It
REFUSES to print a rate until something has been judged, and says why, because a
rate over an unjudged sample reads as zero and is worse than no rate. Below
twenty judged it says so on every run.

Dismissal is cheap on purpose. The failure now prints the whole offending
sentence and the matched term beside a flag id, and names the exact command to
record a verdict against it. A flag nobody can judge without opening the report
is a flag that gets waved through.

The log write can never take the run with it: an OSError there prints a warning
and the guard carries on. Losing a line of telemetry must not become a lost
morning report. The --check path reports without logging, since replaying an old
report must not add flags to a rate that already counted them.

### `no` joins the ban, and `none` stays

"no candidate cleared the price test" is the same assertion as "none cleared it"
and is equally uncheckable, so the first version of the list was a spelling rule
rather than a guard. `no` is matched FORWARD ONLY, unlike the rest: it is a
determiner and governs the noun after it, so "there is no premarket high for AS,
so the candidate is dropped" asserts nothing about the set and still passes.

### The Summary counts, resolved ahead of the rest

The guard catches every, all, none and no. It does not catch "three candidates
cleared the price test", which is wrong the same way and which the Summary still
invited. A count is the shape the guard is blind to, so the counts went first.

Both numbers were already in the packet: candidate_provenance.ranking has
subscribed_considered, cleared_floors and kept, and screen_tally has
candidates_examined and the eligible count per screen. The template quotes all
five and no code was needed.

The decision underneath it is about the report rather than the defect. The
Summary sentence is now written the SAME WAY on a morning when nothing is
eligible, with zeros in it, instead of switching to prose. Prose written only
for the empty case runs on the fraction of mornings nobody reads closely, which
is precisely where both false universals were published. "0 of 12" also says
more than "none are eligible", because it carries the denominator: a screen that
rejected twelve names and a morning that found none to screen are different
failures, and the old wording could not tell them apart.

Queued behind them: T2, T3, T6, T12, T15, T16, P1, P2, in
doc/research/TEMPLATE_DERIVATIONS.md.

Proof: test_containment claim 7 now covers both the none and no spellings and
the determiner case, and claim 8 covers logging, the pending disposition, and
the rate refusing to report over an unjudged sample.

## 2026-08-18, third: the template stops asking the model to count, and a guard enforces it

### The audit, first

doc/research/TEMPLATE_DERIVATIONS.md lists every instruction in
REPORT_TEMPLATE.md and prompt_analyst.md that asks the model to count, rank,
compare, pick a most, filter the candidate set, or characterise it as a whole.
Seventeen in the template and five in the prompt. The verdict is per instruction
rather than blanket: four are judgements with no correct value and stay as prose,
three were applied now, and ten are listed as PROPOSED for the owner, because
moving a filter into the packet changes what the report says on a morning when
the filter is empty and that is a judgement about the report rather than a fix.

### The tally

scan.screen_tally counts, per screen condition, how many candidates failed and
how many cleared, and builds the sentence the template quotes. evaluate_eligibility
now records a condition KEY beside each failure sentence, because a tally counted
from prose breaks the first time a message is reworded. The failure sentences
themselves are byte identical, checked against the 2026-08-18 packet.

On that packet it reads: day require_above_prior_high 11 of 12, premarket_rvol 10
of 12. Those are the numbers the report got wrong.

### The guard, because a rule is not a guard

analyst.quantifier_violations rejects every, all, none, each, most and majority
within six words of candidate, name or watchlist, in prose, skipping table rows
so an empty watchlist's own none row does not fail every empty morning. A hit
fails the run at exit 2 beside the containment check.

This project has twice learned that an instruction is not a guard: the watchlist
headers are pinned in the template AND verified in code. The same pattern applies
here, and it earned itself immediately. Pointed at the reports already on disk it
found that 2026-08-18 carried TWO false universals rather than one. The second,
in Technical signals, said every candidate traded below its premarket VWAP and
its prior day high, when AS.US traded above both. Nobody had read that line. It
also found the same class in the 2026-08-14 report, unnoticed at the time.

Template changes: the day and swing empty-screen sentences now quote
screen_tally.failed_summary, and the Skips and traps section no longer orders the
model to write "every candidate carries a found catalyst and full evidence",
which was the one instruction in the template that demanded an unverifiable
universal and which the guard would have rejected. prompt_analyst.md gains rule
13 naming the banned words and pointing at the tally.

Proof: test_containment claim 7, both directions. A report asserting "every
candidate" fails, the tally sentence passes, and an empty watchlist table does
not trip on its own none row.

### Everything parked on the stop decision, re-checked

The 2026-08-16 third entry said "scoring has stopped" and closed six items on
that basis. Scoring never stopped; the scoring CALIBRATION work did, and the
morning chain scores every weekday. Each of the six was checked against what that
decision actually says. Three stand: the subscription cap table, the second
socket purchase, and Alpaca as a live discovery source. Three did not, and are
corrected in place: the candidate_count dependency is dormant rather than moot,
since candidate_count is a live CRITERIA knob read daily and stopping work on the
bands does not freeze the input they were fitted to; the day-setup eligibility
question was already corrected; and the looseness of the RVOL scoring bands is
corrected here for the same reason. Recorded in DECISIONS 2026-08-18 third so the
check is not repeated.

One citation of my own corrected with them: yesterday's entry said the stop's
"Continuing" list keeps the daily report running. That list names the two probes
and the post-open pass. It is the NEXT entry that names the morning chain, calling
it and the post-open pass the only remaining outputs. The conclusion was right
and the citation was wrong.

## 2026-08-18, second: two findings from the first empty morning that had a live candidate in it

Both are written up in DECISIONS.md 2026-08-18. Neither is fixed here and no
screen, threshold or collector behaviour was changed.

### The report's one explanatory sentence was false

An empty day watchlist was explained as "the most common failed condition was
price not above the prior day high, which every candidate missed". AS.US did not
miss it: 34.71 against a prior day high of 33.4194, with a single day failure,
the null RVOL. From the packet the tally is price 11 of 12 and RVOL 10 of 12, so
the mode is right and the universal is false.

The cause is structural rather than a wording slip. REPORT_TEMPLATE.md asks for
"the most common failed condition", the packet carries no such tally, and nothing
aggregates day_failed or swing_failed, so the model is asked to compute a
statistic in prose from twelve per candidate lists. Containment checks tickers
and vintage checks dates; neither checks a claim about the screen's own output.
On an empty morning that sentence is the whole report, and it named the wrong
cause.

The fix is named in DECISIONS and deliberately not built in this pass: compute
the tally in scan.py into the packet, and have the template quote it rather than
derive it, on the precedent of the watchlist headers that were made literal for
exactly this reason.

### The float rotation eligibility question is not inert, and it was the watchlist

2026-08-16 third listed the day-setup eligibility question for names rescued by
float rotation as "unresolved and now inert" because "scoring has stopped". That
is corrected in place: the same decision's Continuing list keeps the daily report
running, and what stopped was the scoring calibration work, not the publication
of scores.

2026-08-18 supplies the counterexample. AS.US, earnings before the open, up 6.57
percent, above its prior day high, scored 8.0 green on
volume_measure_used = premarket_float_rotation, and its whole day_failed list is
the null premarket RVOL. The baseline median is 383.5 shares, under the 1,000
share floor, against 37,169 shares actually traded premarket, about 97 times it.
It was the only one of twelve candidates to clear the prior high test, the other
eleven having gapped down into a long only screen, so this single open question
was the difference between an empty published day list and a one name one.

Whether a float rotation floor belongs in [Day setup] is a threshold question and
stays with the owner. What changed is that it now has a dated instance behind it.

## 2026-08-18: the collector volume check is sound and the collector is not

The definitive collector volume verification, runs/<date>/verify_intraday.json,
had run once on 2026-08-14 and reported 0 of 37 symbols within one percent at a
median absolute difference of 70.95 percent. Nobody had read it. BUILD_PLAN
still described the debt as pending rather than as landed and failing.

Diagnosed in doc/research/COLLECTOR_VOLUME.md, findings only, no collector code
touched.

The check prints an ABSOLUTE median, which throws away the bit that nearly
diagnoses the problem on its own. Signed, 2026-08-17 reads -88.49 percent with
all 29 comparable symbols negative, and 2026-08-14 reads -33.77 percent with 23
negative against 14 positive and an aggregate 3.83 times the vendor.

The check itself was verified before anything was concluded from it. It sums
only the minute keys both sides carry, and shifting the collector's keys a
minute either way makes the overlap worse rather than better, so the minutes are
correctly paired and there is no off by one of the kind pm_rvol already carries.
On 2026-08-17 every collector minute exists on the vendor side.

The decisive evidence is stability. Across the two mornings the vendor's figure
for the same ETF moves by 1.1x to 5x, which is an ordinary premarket, while the
collector's moves by 48x to 181x. TLT reads 780,284 then 711,930 on the vendor
side and 10,688,231 then 76,766 on the collector's. Late trade dropping is ruled
out at 0.00 and 0.30 percent of volume, both sessions ran the websocket rather
than the poll fallback, and every bar carries src "ws".

Verdict: the check is sound, the collector is at fault, and the failure is worse
than a constant shortfall. The collector is not reproducible session to session,
so no fixed correction factor can absorb it.

This puts every published pm_rvol and pm_float_rotation in doubt, both being
computed on collector volume, and it is a reason to leave data/UNVERIFIED where
it is rather than a detail to fix after go live.

Recorded alongside it, DECISIONS 2026-08-17 seventh: the rotation bands are
fitted on Alpaca volume and applied to collector volume. The scoring numerator
is the smaller one, so the bands admit fewer names than intended. Not re-fitted,
because the size of the gap depends on the collector question above and fitting
to a numerator that swings 181x between sessions would bake an accident into a
threshold.

## 2026-08-17, fifth: the rotation bands are re-derived after the screen fix, and do not move

The fourth entry fixed float_rotation_study.py, the script CRITERIA names as
the way to re-derive the float rotation score bands, and left the bands
themselves as the previous, broken, run had produced them. That was an
unmeasured claim sitting under a live scoring rule. It is now measured.

The edges are unchanged: two points above 0.0004, one point at or above 0.0002.
Confirmed twice, first by proving the screen fix cannot move them and then by
re-running the study, which cost 463 Alpaca requests, 567 seconds and zero
EODHD calls.

The screen fix provably cannot move them. Over all 1,870 symbols in the float
cache the corrected screen changes exactly one verdict and adds none: YPF, at
0.013 percent of its own shares outstanding, the same name CRITERIA's float
floor note already records as the only one under that line. Replaying all 61
cached session pairs through the study's own gap ranking, which reads
data/backtest/eod/ and not the network, puts YPF in the top candidate_count by
gap on zero of them, and the edges are fitted on the rescued subset of that
population.

The percentages AROUND the edges did move, and not because of this fix: the
re-run measured 300 rescued names paying 56.00 and 11.67 percent against a
target of 53.72 and 12.40, where 2026-08-16 measured 303 paying 55.45 and 12.21.
data/universe.json was rebuilt at 2026-08-17T00:50, between the two runs, and
the addressable population differs on 29 of the 61 sessions before the float
screen is reached at all. Both unrounded quantiles moved in the fourth
significant figure, 0.00045075 to 0.00045409 and 0.00021475 to 0.00021511, and
both still round to the same edge.

Two corrections in place under the wrong-when-written rule. The docstring added
in the fourth entry claimed a re-run "will not reproduce them to the name"; the
edges do. And the first version of this entry said the counts and payout shares
reproduced exactly, which was a claim about the screen fix in isolation
presented as though it described a re-run. The DECISIONS entry carries the
replaced table and why it was wrong.

One method claim retired with them: this work first argued a re-run was
impractical for needing Alpaca volume across 61 sessions. ALPACA_PROBE.md had
already measured the free tier sweeping 2,745 names at 1Min in 4 requests and
1.04 seconds, and the entry closing Alpaca as a LIVE discovery source says
plainly that it remains a historical reconstruction source for completed
sessions. The two are different questions and only the live one is closed. It
should simply have been run.

## 2026-08-17, fourth: six review findings closed, and the two the first round of fixes introduced

A full review of everything since the package reorganisation on 2026-08-14,
about 10,300 inserted lines across 49 files, found six defects. All six are
closed. The fixes were then reviewed adversarially, which found one blocking
defect and one regression IN THE FIXES THEMSELVES, and those are closed too.
That second round is recorded here at the same weight as the first, because a
fix that introduces a defect is the failure mode this project's whole review
habit exists to catch, and hiding it inside a green suite would waste the
evidence.

### The six findings

- **discover crashed the whole morning when the calendar could not answer.**
  write_universe_closes called vintage.previous_trading_session without the
  None guard the two calls ten lines above it both use. On None,
  eod_bulk_last_day sends no date parameter and the vendor returns the LATEST
  session, so the wrong close was bought as c3 at a flat 100 credits, and then
  third.isoformat() raised AttributeError. discover.main catches
  StaleUniverseError, QuotaRefusal, UnrankedPoolError and RuntimeError, and
  AttributeError is none of them, so the 07:15 job died before writing
  watchlist.json and the collector woke to no fresh watchlist. The third call
  is now skipped when the calendar cannot name the session, which also saves
  the credits, and the existing machinery records the consequence: c3 null,
  third_session_available False, prior session leg untouched. Proof:
  test_pool.claim_sixteen.
- **The new pre-write admissibility gate could refuse forever.**
  previous_count is read from the very file the refusal prevents replacing, so
  a legitimate shrink below min_count_fraction_of_previous refused again every
  Sunday against the same frozen baseline, and past max_age_days every morning
  job then refuses too. There is now a --force flag. See DECISIONS.md for why
  it reaches exactly one of the three verdicts.
- **A sharesOutstanding of exactly 0 bypassed every float sanity check.** 0.0
  is falsy but not None, so both ratio guards ("if outstanding and ...") and
  the absolute floor ("if outstanding is None and ...") were all skipped, and a
  bogus tiny float became the divisor unchecked. The three states are now
  distinguished: absent and zero both fall to the absolute share floor, and
  negative is refused outright. Proof: test_repricing claim 10.
- **Vintage check (e) failed every row when the calendar could not answer.**
  Checks (c) and (d) stand down on an unanswerable calendar, honouring this
  module's own rule that a check which cannot run must not fail a run it did
  not examine. Check (e) did not. It now stands down from the SESSION
  COMPARISON ONLY: a row with no leg, an unrecognised leg, no as_of_session or
  an unreadable one still fails, because a section built entirely on labelling
  cannot skip its labels. sessions_back is annotated dt.date | None and
  returns None rather than iterating on one. Proof: test_vintage claim 4.
- **float_cache carried the guard hole universe.py had just removed.**
  "if error and not data" misses a 200 with an unrecognised body, which
  quote_delayed returns as ({}, None), so a whole batch fell through counted as
  nothing. Both of universe.py's other two doors are now mirrored as well: a
  batch that answered nothing, and names absent from a batch that answered.
  The unanswered names are PERSISTED into the cache file, not merely printed.
- **The collector's status frames reached no reader.** They were collected and
  returned but dropped from the record appended to the stats sidecar. They now
  survive all three hops: persisted per run, summed by read_run_stats, and
  named in scan's collector_snapshot, which is what puts them in the packet.

### What the adversarial review found in the fixes

- **BLOCKING: the --force override silenced checks it was never shown to.**
  The override matched on verdict text through a helper used at all three
  return sites, and each was written "return answer(...)", so a matched
  override returned None immediately and every check BELOW it never ran. A
  payload whose unswept verdict was overridden was then admitted with its count
  far below the floor, in discover, every morning until the next rebuild.
  Closed structurally rather than by patching three sites: the override now
  applies only to the count fraction verdict, which is the LAST check, so there
  is nothing below it left to skip.
- **REGRESSION: the float fix loosened a guard that had been holding.** The
  brief that drove it asserted a negative sharesOutstanding was unguarded
  before the change. That was wrong. "if outstanding and share_float >
  outstanding * max_ratio" is truthy for a negative outstanding and every
  positive float exceeds a negative product, so negatives were already refused
  with a gap raised. The first fix skipped both ratio checks for negatives and
  began PUBLISHING a rotation for them, with an impossible share count beside
  it in the packet. Negatives refuse outright again, and an unusable
  sharesOutstanding is recorded as null in pm_float_rotation_basis rather than
  as a bare 0.0 that reads as a share count of zero.

### Smaller corrections in the same pass

Six comments and docstrings were asserting more than their code did, which in
this project is a defect rather than a nit: read_run_stats claimed scan
consumed what it returned (scan names keys one at a time, so a field needs both
hops); the --force help text described a scope the flag no longer had;
attach_float_rotation claimed every route ends in a gap while two did not, and
the pm_volume route now raises one to match attach_premarket_rvol exactly;
test_vintage counted four checks when there are five; float_cache claimed the
run announces a discarded map when it did so silently; and
float_rotation_study claimed the CRITERIA float floor note could be re-derived
from counters that count per session occurrence rather than per name, so it now
reports both. vintage.describe() gained its missing "e" entry, so a notable
movers refusal renders as a sentence rather than as "(e) e: 1 row(s)".
float_rotation_study also carried the same falsy-outstanding bug and a
hardcoded 1.01 where max_float_to_shares_outstanding belonged, which mattered
because CRITERIA points at that script to re-derive the score bands, so the
bands were being fitted with a different rule than the one that scores against
them. One new knob: api.max_symbols_named_per_line, because a fully starved
float sweep printed 1,870 tickers on one line.

Suite green at 9 modules and 16 scheduled entrypoints, hermetic, no path
changed under the working tree.

## 2026-08-17, third: the three session leg is dropped rather than left defined and never emitted

### One key removed, one reason recorded

three_session is gone from _LEG_NEWEST_SESSION_BACK in src/morning/vintage.py
and from BUILD_PLAN Layer 4. It had no source: a three session move universe
wide needs a fourth close, and data/universe-closes-<date>.json holds three.
The table now holds exactly the three legs the section emits, and DECISIONS.md
carries what restoring it would cost (one more 100 credit bulk call every
morning) and what it would buy (little the two session leg does not already
carry, answering a weekly trend question rather than a this morning one).

src/tests/test_vintage.py follows: the correctly mixed vintage case drops its
three_session row, and the stale case becomes a two session row stamped with
its baseline three sessions back, which is the same gap_stats trap the extra
bulk call exists to avoid.

### Two errors of fact in write_universe_closes, corrected in place

Both were introduced when the section was first specified and both survived
the naming change earlier today.

- The docstring described the third close as feeding a "three session leg" and
  the failure path as leaving "the two session legs" intact. Under the settled
  naming c3 is the TWO session leg's baseline, so a failed third call costs the
  two session leg and leaves the prior session leg untouched. The print on that
  path said the same thing and is corrected with it.
- The signature was `-> dict[str, Any] | None` and the docstring said it
  returns None when the third call fails. It does not and never did: the
  function always returns the payload, and the failed call is recorded in
  third_session_available. The annotation is now `-> dict[str, Any]`. A
  documented return value that no code path produces is the same shape as an
  enum key nothing emits, which is what this entry is about.

## 2026-08-17, second: the notable movers section is specified in the repository

### The design stopped living in a conversation

Every rule the owner set for the section over 2026-08-16 and 2026-08-17 is now
in BUILD_PLAN.md as Layer 4, written as specification rather than as
narrative: the scope fence, the per candidate fields, the legs with their
sources and vintage stamps, the lists and their deduplication, the catalyst
not checked rule, the fixed template text, the prompt rule, the degrade
behaviour and the done when conditions. Nothing about the section's design now
depends on a chat log. The code is still unbuilt.

### Three amendments the same day, and what they changed

- The universe legs read data/universe-closes-<date>.json. The earlier draft
  read the previous session's open gap out of pool_recall.json, which covers
  only names above the 3 percent gap floor and carries a second vintage. No
  leg reads pool_recall now, and the section's examined count is the universe
  rather than the gapper count.
- move_sigma divides by return_stdev_20d times the square root of the number
  of sessions the move spans, so every leg carries a sigma instead of the
  multi session legs carrying none. The independence assumption behind the
  scaling is recorded with it.
- Four lists, each ranked inside one leg, replacing one ranking over each
  name's newest available move. The premarket leg gets its own list rather
  than putting the 50 collector names into the same ordering as 2,704
  unselected ones.

CRITERIA.md [Notable] follows the same three: three legs and four lists rather
than four legs, the previous session's CLOSE rather than its true open gap,
and the square root scaling with its assumption. The knobs did not move.

### What the amendments cost

The three session leg is not emitted. Under the naming these rulings settle, a
leg is named for the sessions its move SPANS, and a three session move
universe wide needs a fourth close where the file holds three. Restoring it is
one more bulk call in discover, 100 credits a morning. Recorded in Layer 4 as
the owner's call, not taken here.

## 2026-08-17: the quota gate is sized in credits, and the market cap funnel names every door

### The call count was never the bill

The 2026-08-16 Sunday rebuild entered with 329 credits on the shared meter and
reported 172 http calls. Those two numbers together read as a job that cleared
comfortably. The meter moved 4,945.

CRITERIA.md gains a [quota costs] section, MEASURED rather than seeded, because
the arithmetic closes exactly on two independent runs:

| endpoint | unit | credits |
| --- | --- | ---: |
| eod-bulk-last-day | per call | 100 |
| us-quote-delayed | per SYMBOL, issued twenty at a time | 1 |
| eod | per call | 1 |
| exchange-symbol-list | per call | 1 |
| user | per call | 0 |

On the 00:06:53 rebuild: 2 + 1 + 20x100 + 2,942 staged names = 4,945, the delta
between entry and exit in logs/meter-2026-08-17.log. The 20:30:01 run staged
2,941 and read 4,944 at its exit. Neither sum has room for the meter reads, so
user is free. A third run later added two more meter reads for the new gates
and still moved exactly 4,945.

So the 2026-08-16 run did not clear comfortably. It needed 4,945 and held 329.
It survived because the counter rolled within its first seconds; the bulk sweep
alone would have exhausted 329 on its fourth of twenty calls.

### Gates sized to the work, at the two points where nothing is estimated

eodhd.require_quota prices a step from the table and refuses below that times
[quota] quota_headroom_multiple. universe.py gets two:

- after _session_dates, where three credits are spent and len(session_dates) is
  exact, so the 2,000 credit bulk sweep is priced rather than guessed. Refusing
  there costs three credits instead of two thousand.
- before the market cap sweep, where len(staged) is final. This is the gate
  that had to exist, and the meter read for it is free.

gap_stats gets the same treatment rather than universe carrying its budget,
because coupling them would refuse a rebuild on Sundays when only gap_stats was
unaffordable. It prices itself exactly: one eod per universe name, a measured
2,753 credits against the same 500 floor it used to check.

An unknown meter still refuses nothing. preflight leaves remaining as None on
three paths and the third is a reading dated to another quota day, which is
what the vendor serves for the half hour after a reset it rolls late. Refusing
there would convert a benign late roll into a skipped weekly rebuild, so
require_quota acts only when remaining is not None and never recomputes it from
api_requests, which the stale branch does populate.

Refusing is the cheaper failure. A refused Sunday leaves last week's file and
the monitor relaunches the job at universe_rerun_after_days; discover only
starts refusing on the fourth morning after a miss. Proceeding on a short meter
has no recovery: staged is sorted by dollar volume descending, so a starved
sweep amputates the illiquid tail rather than thinning evenly, and the result
stays inside expected_count_range and above min_count_fraction_of_previous
until roughly half the names are gone.

### Five doors, named, because one door counted is worse than none

The note this replaces read "46 names were dropped because no market cap came
back" against 2,942 examined and 2,754 admitted. That does not close: 142 names
failed the market cap floor with nothing recording they had been considered.
Naming the 46 alone would have made it worse, because the named list reads as
the explanation for the whole 2,942 to 2,754 drop and explains a quarter of it.

    2,942 examined
    2,754 admitted
      142 below the >= 500M floor
       20 answered with no market cap in the row
       26 absent from a batch that answered
        0 in a batch that answered nothing

market_cap_funnel carries the counts and the names in universe.json, and the
job log names the three doors that are evidence gaps. The floor names stay in
the payload only: that door is a decision made on evidence, and 142 tickers on
one line would bury the three that are not.

Separating them answered a question nobody had asked. The 46 were never one
thing, and neither group is missing data. The 20 are alternate share classes
and warrants priced under the primary class: BRK-A, BRK-B, HEI-A, LEN-B, MOG-A,
GEF-B, BH-A, UHAL-B, BF-B. The 26 are preferreds and warrants the vendor does
not quote at all: ALB-PA, ARES-P-B, BA-P-A, HPE-P-C, KKR-P-D, NEE-P-T, PCG-P-X,
JOBY-WS, and ZVZZT, which is NASDAQ's test symbol. The market cap gap was
quietly doing the filtering allowed_security_type was supposed to do.

A silent hole closed on the way. The old guard was `if error and not data`, and
eodhd.quote_delayed returns ({}, None) when a chunk comes back 200 with a body
it does not recognise: no error, no rows. The guard was False, the loop ran over
an empty dict, and twenty names fell into the vendor gap counter with nothing
written anywhere. The test is now on the data, so a batch that answered nothing
is recorded as unanswered whether or not it said why.

check_admissible acts on the distinction at [universe] max_unswept_fraction =
0.02, and build() now asks it BEFORE overwriting anything, raising
PartialBuildError instead of writing. That ordering is the whole point:
os.replace is destructive, and the monitor relaunches the rebuild on AGE, so a
truncated file with a fresh timestamp is never retried while a missing one is.
Enforcing only downstream would have made a lost batch cost the whole week.

The numerator counts only names nothing came back for. Names the vendor
answered a batch without mentioning are its coverage, not this run's failure,
and are structural at 26 of 2,942, so counting them would spend a third of the
ceiling on a constant. Excluded, the baseline is zero and 0.02 of 2,942 is 58
names: two lost batches of twenty clear, the third trips. Files written before
the funnel existed are skipped rather than failed.

### Corrections of fact

CRITERIA.md recorded eod-bulk-last-day at "98 counted calls each" in two places.
At 98 the rebuild reconciles to 4,905 and leaves 40 credits unexplained; at 100
it closes exactly. The 98 came off the client side call ledger, which counts
calls and is not the bill. Both sites carry the marker. The [job status steps]
comment still said Sunday 20:00 after the schedule moved to 21:00, and is
corrected the same way.

### Claims

test_pool gains claim 13 and claim 14. Claim 13 drives require_quota at three
points around the computed requirement from fed meters, with the requirement
priced from the same table the code reads so retuning a knob cannot leave it
asserting a dead number, and then drives both unknown meter paths to prove
neither refuses. Claim 14 drives the funnel from a stub covering all four batch
outcomes including the 200-with-no-rows shape that cannot be provoked from a
live run, asserts every examined name leaves by exactly one door, and asserts a
batch that answered nothing is not recorded as a vendor gap.

Claim 15 covers the wiring, which the first two do not: claim 13 would keep
passing if every call to require_quota were deleted from both modules, which is
the difference between testing a function and testing a change. It asserts both
universe gates and the gap_stats gate are called, that build checks its own
payload before writing, and it drives each exception to prove the handler order.
That last part cannot be asserted from an exit code, because every path returns
1: QuotaRefusal and PartialBuildError both subclass RuntimeError, and
universe.main has caught bare RuntimeError since long before either existed, so
a handler added below it is dead code whose only symptom is a refusal reported
as "build failed" with no reason on the job status line.

The entrypoint claim for universe now removes universe.json before driving the
rebuild. The sandbox carries a restamped copy of the real one, roughly 2,750
names, and the stub serves a thousand, so the new write time check correctly
refused it: comparing a stub against production counts tests the fixture rather
than the entrypoint. With no previous file there is nothing to compare, which
is also the only place the suite drives the branch of the first quota gate that
cannot size the market cap sweep yet.

## 2026-08-16, seventh: the meter is sampled on a clock, and the degrade threshold is claimed on its output

### A sampler, because the job trail cannot answer "when"

The job trail says which step spent what. It cannot say when, because it only
has readings where a job happens to run, and this schedule is sparse: nine jobs
in two short windows with nothing at all between the 22:45 monitor and the
07:00 catch-up. A sibling draining the shared key overnight is invisible to it,
and overnight is when 2026-08-16's drain would have had to happen to be as
complete as it was by the afternoon.

`ops/meter_sampler.py` reads the meter every thirty minutes, all day, every
day, appending to the same `logs/meter-<quota day>.log`. Every row now carries
a `source` column: `job` for an entry or exit reading around a scheduled step,
`sampler` for a clock reading, `reset` for the boundary row below. Forty eight
calls a day against a shared hundred thousand.

**Exactly one call per sample.** `record_meter` gained an optional pre-fetched
reading, so the sampler reads once and can write two rows from that one
observation. Without it the reset row would have re-read the meter, costing a
second call and, worse, recording numbers that disagreed with the roll it was
supposed to be documenting. The first version did exactly that and the test
caught it reporting `used=260` for a roll it had detected at `120`.

**The reset is a labelled row, not a gap.** When a sample sees the counter
fall, or sees `apiRequestsDate` change, a `source=reset` row is written first
carrying both sides: `rolled_from_api_requests`, `rolled_from_meter_day`,
`rolled_from_at` and the corresponding `rolled_to` fields. Two independent
signals because a roll landing on a day where almost nothing had been spent
would produce a fall too small to tell from noise.

Registered as `PremarketDesk\meter-sampler`, every day, repeating every 30
minutes for 24 hours. One shot per firing rather than a long-lived `--loop`
process, so a crash costs one sample instead of silencing the sampler for the
rest of the day. It writes no job status record: it is an instrument, not a
step, and CRITERIA.md [job status steps] must not gain an entry the watchdog
would then expect and report overdue.

Verified over a simulated day of 49 half-hourly samples across an overnight
roll: 49 calls for 49 samples, one labelled reset row, and zero negative
deltas. Real coverage accrues from 21:30 tonight; a full day including the
overnight window exists tomorrow.

### The degrade threshold, asserted on what the packet says

Claim 12 covers the refuse floor, where the job does not run and the exit code
is the whole story. The degrade threshold is the higher risk of the two,
because the job DOES run and produces a packet, and thin mode is where the
false-reason defects lived. A packet whose catalyst reads "none" when the news
feed was never called is not thin, it is wrong, and wrong in the direction that
looks fine.

`claim_scan_degrades_on_a_thin_meter` drives three points around 5,000 from fed
readings and asserts nothing about the exit code. On the degraded run it
requires that a packet exists, that `gaps_to_fill` names the actual remaining
figure, that `quota_preflight.degraded` is true, and that every candidate
records `catalyst_found` null with a `catalyst_why` saying unknown and a
`catalyst_class` that is NOT the string "none".

Three things that claim found on the way to passing, each a fixture defect
rather than a product one:

- A thinned RERUN of a day that already has a full width packet correctly
  stands down and writes `packet_degraded.json` beside it. The claim was
  reading `packet.json` and reporting three failures that were one wrong
  filename.
- `_write_watchlist` used `tier`, `pool_sources` and `prior_close`.
  `scan.pool_candidates` reads `pool_tier`, `pool_source` and
  `pool_prior_close`. Every candidate therefore reached the scan with no prior
  close, and a thinned run cannot spend a call to fetch one, so the packet was
  empty. Both spellings are now present.
- The collector bar fixture and the wall clock. Prices older than
  CRITERIA [price age] are dropped, correctly, so a fixture written at a fixed
  07:20 is stale by hours whenever the suite runs outside the morning. The
  claim now pins the clock to the scan's own run time for the duration, which
  is the only condition under which the pipeline it is testing assembles
  candidates at all.

That last one is the day dependence the frozen calendar sweep exists to find,
caught this time by a new claim rather than by the sweep.

## 2026-08-16, sixth: the quota counter does not roll at 00:00 UTC, and the meter trail caught it on its first real run

The trail added hours earlier ran for the first time in production tonight,
against the Sunday universe rebuild, and immediately reported a delta of
**-94,727**. That number is impossible as consumption and it is the finding.

### What the counter actually did

| Reading | ET | Meter says used | Remaining | Counter dates itself |
| --- | --- | ---: | ---: | --- |
| universe entry | 20:30:01 | 99,671 | 329 | 2026-08-16 |
| universe exit | 20:31:49 | 4,944 | 95,056 | 2026-08-17 |

00:00 UTC on 2026-08-17 was 20:00:00 ET. The counter had NOT rolled half an
hour later and rolled somewhere in the 108 seconds between those two readings,
so the vendor's reset lags the nominal boundary by 30 to 32 minutes.

**The 20:30 move made earlier today was therefore not enough**, and the
CHANGELOG sentence claiming it "clears the boundary in both halves of the
year" is corrected in place below. The universe job spent its first minute
reading a counter 329 short of exhausted. It has no refuse floor so it
proceeded and finished clean, producing 2,753 names; a job carrying discover's
floor of 500 would have stood down on a budget that was in fact seconds from
being full. Moved again to 21:00, roughly double the one lag observed.

One observation is not a measurement of the lag, only proof that it is not
zero. The trail now records `apiRequestsDate` on every reading, so the next
roll is visible rather than inferred.

### The delta guard was wrong, and its own output said so

`record_meter` guarded cross-day comparison on `quota_day()`, the day computed
from the wall clock. At 20:30:01 ET that already said 2026-08-17 while the
vendor's counter still said 2026-08-16, so both readings looked same-day and
the subtraction spanned a reset.

Fixed to guard on `apiRequestsDate`, the counter's own dating, which is the
only authoritative signal that it rolled. A missing date on either side now
yields no delta, because an unknown boundary is not a safe subtraction, and a
reading whose date trails the quota day is flagged `meter_day_is_stale` and
says so in the log line.

Replayed against tonight's exact sequence: the reset-spanning delta is
suppressed, the stale reading is labelled, and gap_stats still reports its true
`+2,753`, which matches its call report of 2,753 `eod` calls exactly.

### What the first real trail also settles

gap_stats consumed 2,753 calls, one per symbol, attributed to a single step
without inspecting a call report. That is the attribution the trail was built
for, working on day one. The universe leg cannot be attributed because its two
readings sit either side of the roll, which is now stated rather than
silently subtracted.

## 2026-08-16, fifth: the suite no longer touches the network, and every job records the shared meter

### No test may make a live quota call

**The defect.** test_pool claim 11 called `discover.build()`, which preflights
the shared EODHD key. A sibling project pushed that key below the refuse floor
of 500 remaining, and the claim began failing with nothing in this repository
changed. It had been passing all week for the same reason it then failed: it
was reading someone else's account state.

**Fixed at the boundary, not in the claim.** `eodhd.read_meter()` is now the
single network call `preflight` makes, and it is the seam. Everything
interesting in preflight stays under test, since only the READING is
substituted: the degrade and refuse thresholds, the stale meter day check and
the unreadable payload check all still run for real.

`conftest.activate()` now wraps the whole suite in `block_network()`, which
installs a `_BlockedSession` as the session every `EodhdClient` builds and
pins `read_meter` to a fixed healthy 99,000 remaining. Any un-stubbed call
raises `NetworkBlocked` naming what tried and how to stub it. Three suites
already stubbed at `client._session` and are unaffected.

**The sweep, done empirically rather than by inspection.** Twelve claims reach
`EodhdClient._request`: eight in test_entrypoints, three in test_txn_guard,
and test_pool claim 11. All twelve were already stubbed, so nothing needed
marking live, and the suite passed on the first run with the block installed.

**Verified with the network genuinely gone**, not merely stubbed: DNS severed
at `socket.getaddrinfo` after imports, proven by a real request failing first,
and the full suite still passes. Claim 11 now passes at every meter reading
from an empty key to an untouched one, because it pins its own reading; it is
about how the pool ranks, not about quota.

**New claim 12** drives the refusal path from a fed reading at three points
around the floor, so blocking the network did not also stop anything from ever
exercising the refusal.

**Two things the sweep exposed.** Claim 11's second leg swallowed every
exception as "the network stub missing", which is precisely how it absorbed a
QuotaRefusal for a week; it now fails on any unexpected exception on both
legs. And the first version of the live-claim matcher looked for the substring
`live`, which caught `claim_deliver`. The convention is now `claim_live_...`
or `..._live`, matched exactly.

`run_tests` gains `--live`, off by default, and reports either the live claims
it skipped or that the suite is hermetic.

### Every job records the shared meter at both ends

Nothing in this repository could say WHEN the shared key was drained or which
of its own jobs contributed, because the only reading taken was the preflight
inside three of the nine jobs. `job_status.run` now calls `record_meter` at
entry and at exit, appending to `logs/meter-<quota day>.log` with the delta
since the previous reading.

A job's own spend is its entry-to-exit delta. A sibling's spend is the gap
between one job's exit and the next job's entry. Deltas are only computed
within a quota day, because across the 00:00 UTC reset the counter falls and a
negative delta reported as consumption is worse than none.

Costs two calls per job, about eighteen a day against a shared 100,000, and
the instrument is visible in its own output rather than hidden. Never raises:
an unreadable meter is a missing line in an operational log and must not fail
a job that was otherwise fine.

Verified across a full pass of all sixteen scheduled entrypoints, every one of
which writes an entry and an exit reading. The first real day's numbers arrive
with Monday's run.

## 2026-08-16, fourth: the rotation bands are re-derived on the right population, and the schedule leaves the quota boundary

### The float rotation bands were fitted to names that never receive them

The bands added earlier today were matched to RVOL's payout on the OVERLAP, the
names carrying both measures. Those names are scored by RVOL and never reach
the rotation bands. The only names that do are the rescued ones, and they sit
materially lower: median ratio 0.6115 on the scored population and 0.4587
across all addressable.

So `> 0.0006 / >= 0.0003` paid full marks to 45.87 percent of the rescued names
against a 53.87 percent target, an 8 point shortfall in the direction that
penalises a name for having no history. That is the exact bias the alternatives
design existed to remove.

Re-derived on the rescued population: **`> 0.0004` and `>= 0.0002`**, paying
55.45 and 12.21 percent against a target of 53.87 and 12.43. Both distributions
and the edges' percentile position in each are in DECISIONS.md 2026-08-16
second.

Recorded with it: the edges are conditional on [Scan] candidate_count, because
the scored population is the top N by gap and rotation rises with gap size. The
two slices genuinely disagree about the direction of the fix, and the note in
CRITERIA says which one governs and how to re-derive.

### The overlap count reconciles

The earlier entry quoted 362 where the coverage table implied 5,282. Both are
right and they are different quantities: 5,282 is every addressable gapper with
both measures, 362 is that intersection restricted to the top candidate_count
by gap. The earlier entry gave the restricted number without naming the
restriction. `paired_n_all_addressable` is now measured directly and comes to
5,282, matching the coverage table exactly.

### The Monday probe records the lag, not just the outcome

`probe_alpaca_live` now writes a per sweep table of wall clock, newest bar
timestamp anywhere in the universe, the observed lag between them, that lag
against the documented 15 minutes, and the count of names with any premarket
bar plus its growth since the previous sweep. Whether the feed works decides
whether the design is possible; the lag decides what freeze time is achievable
and therefore what the report can contain, and a feed that works an hour behind
is the 2026-08-14 defect wearing a different vendor's name.

The table is rewritten to `data/probe-alpaca-live-table-<date>.md` after EVERY
sweep rather than once at the end. The run spans nearly two hours of a morning
that cannot be repeated and a crash at 09:00 must not take the first ninety
minutes with it.

Added `--dry-run YYYY-MM-DD`, which sweeps a completed session at five pinned
clock times. This probe gets exactly one Monday, so the plumbing was exercised
against 2026-08-14 first: the active count climbed 1,461 to 1,845 across the
morning and every column filled. The lag reads 0.0 there by construction, since
the bars were complete before the pinned clock reached them, and the written
table carries a loud banner saying so, because a zero minute lag is exactly the
number that gets quoted later by someone who did not read what produced it.

### The packet's build block is now asserted, not just written

scan.py has built a `build` block carrying the commit and a dirty flag into its
payload since 2026-08-14, and `write_packet` writes the whole payload, so live
packets do carry it. Nothing tested that it survives to the file. The existing
claim tested `config.build_identifier()` in isolation, which keeps passing if
the key is dropped from the payload or the writer stops writing it.

Neither runs/2026-08-13/packet.json nor runs/2026-08-14/packet.json has the
key, because both predate the line, and 2026-08-14 is the morning whose report
could not be tied back to the code that produced it. New claim in
test_entrypoints reads the packet off disk and fails if the block is absent. A
NULL commit is allowed, since an export with no .git is a legitimate way to run
this; what must not happen is the key being missing, because then the packet
cannot even say that it does not know.

### No scheduled job fires at the quota reset any more

The EODHD counter resets at 00:00 UTC, which is 20:00 ET in daylight time and
19:00 in standard. The Sunday universe rebuild was registered at 20:00, the
exact reset instant for half the year, so which quota day it billed to was a
race. It is the largest single job in the schedule, buying lookback_sessions
bulk calls in one run, and losing that race means spending them against a
counter that has been accumulating since the previous evening.

Moved to 20:30 in both `register_tasks.ps1` and the live task. Every other job
is a morning or late evening step and none sits near either reset time.

[corrected 2026-08-16: this read "which clears the boundary in both halves of
the year". It does not, and the very next run proved it. The vendor's counter
does NOT roll at 00:00 UTC. The 20:30 universe run read 99,671 used with 329
remaining at 20:30:01 and 4,944 at 20:31:49, so the roll landed 30 to 32
minutes late and the job spent its first minute against a counter that was 329
short of exhausted. Moved again to 21:00, roughly double the observed lag. See
the entry above for the correction and for the delta guard it also broke.]

## 2026-08-16, third: a name with no baseline can be scored, and two probes are set for Monday

Three pieces of work, one of which changes what the morning publishes.

### Float rotation fills the volume score slot when RVOL cannot

**The defect.** `pm_rvol` divides by a cached baseline, so it is null for any
name nobody has baselined. A null component made the whole score null, which
meant a name appearing for the first time arrived UNSCORED, and a first
appearance is often exactly the morning it is worth looking at. Measured over
61 cached sessions: 2,615 of 8,302 addressable gappers, 31.5 percent,
unscorable for want of history rather than for want of evidence.

**The fix.** `premarket_float_rotation`, premarket volume over shares float,
computed in scan.py beside pm_rvol from the same collector numerator and
carrying the same lower bound flag. It needs no history. The two are scored as
ALTERNATIVES filling one slot: RVOL when available because it is the better
measure, rotation otherwise, and only a candidate with neither is unscored.
The unscorable population falls from 2,615 to 145, down 94.5 percent.

The component is NAMED for whichever measure filled it, so the breakdown says
what made a name scorable, and `volume_measure_used` carries the same fact
under a stable key. Both land in picks, because a null pm_rvol beside a real
score reads as a bug unless the row says rotation stood in.

**The denominator costs nothing.** `sharesFloat` was already in the
us-quote-delayed response scan reads marketCap from. `sharesOutstanding` was
added to the kept fields purely so the float can be sanity checked against it.

**The bands are matched, not chosen.** Setting them from the rotation
distribution alone would have followed the instruction and still been a defect:
the two measures share one slot, so unmatched bands make the slot pay
differently depending on which measure filled it, and a name would score
differently for the mere fact of having no baseline. The edges are read off the
rotation distribution at the quantiles reproducing what the RVOL bands pay, on
the 362 names where both measures exist. RVOL pays two points to 53.87 percent
and one to 12.43; `> 0.0006` and `>= 0.0003` pay 54.42 and 12.71. Full
distribution in DECISIONS.md 2026-08-16.

**Two limits, recorded rather than buried.** [Day setup] `premarket_rvol` is
unchanged, so a rescued name is SCORED but still not day_eligible; scoring was
the clause and eligibility is left OPEN. And the matching inherits RVOL's own
calibration, which looks loose on this population at two points for 53.87
percent of the names it scores. That is recorded as an open question rather
than fixed quietly, because changing it moves every score in the table.

**Supporting work.** `research/float_cache.py` caches sharesFloat for the 1,870
distinct addressable gappers, once, at about one credit each, refusing to start
if the quota meter cannot cover it. `research/float_rotation_study.py`
reconstructs RVOL from Alpaca over the same window the live path uses and
produces the distribution above. Neither is a live dependency and neither is
imported by anything that runs in a morning.

### Silence and absence are not the same thing, and only one vendor can tell them apart

Prompted by the question of why an untraded stock is worth watching at all. The
reasoning is right about the stock and wrong about 8 percent of gappers:
measured over 20 sessions, 177 of 2,244 addressable UP gaps, 7.89 percent,
printed NOTHING between 04:00 and 08:30 and still gapped at the open. Nine of
those were 10 percent or more. The largest were re-checked against the raw tape
rather than the cache, so they are not artifacts.

That 7.89 percent is a ceiling on the product, not a vendor problem: no feed
shows a trade that did not happen.

The vendor problem is the other half. A name cannot be known not to have traded
unless something watched it, and with 50 slots against 2,745 names the other
2,695 are indistinguishable from names that did not trade. EODHD REST cannot
separate the two in premarket, since it returns the previous close for
everybody. Alpaca can, since bars come back only for symbols that printed.
Reasoning and numbers in DECISIONS.md 2026-08-16. NOT ADOPTED pending the probe
below.

### Two probes are registered for Monday 2026-08-17

`probe-live-v1` at 07:55 was already set. `probe-alpaca-live` is new, at 07:25,
sweeping the whole universe every five minutes from 07:30 to 09:20. It settles
what doc/ALPACA_PROBE.md could not: that probe ran on a Saturday against a
completed session, so it proved historical access and said nothing about a live
morning, and the whole argument above rests on the live case. It spends no
EODHD quota, taking prior closes from Alpaca daily bars, so it cannot compete
with discover or the scan for the shared counter.

### Test changes

`test_repricing` claim 4 asserted the unavailable component was named
`premarket_rvol`. It is now `premarket_volume`, the neutral name meaning the
slot was never filled, so the claim was updated rather than the code bent to
keep it. New claim 9 covers the clause directly: a first appearance name with
no baseline gets a numeric score, the breakdown names float rotation as what
made it scorable, RVOL still wins the slot when both exist, both float guards
refuse to divide, and a name with neither measure still scores null.

## 2026-08-16, second: every hand invokable writer under runs/ is guarded, not just the collector

The first pass guarded `snapshot_bars`, which was the tool that proved the
hazard. Two others had exactly the same shape and were left open:
`pool_recall --date` overwrites `runs/<date>/pool_recall.json` and
`backfill_premarket --date` overwrites `runs/<date>/verify_intraday.json`.
Both now route through `core/artifacts.py`.

**The owner rule, and why it is PMD_JOB rather than the date.** The obvious rule
is "a past date is spared". It is wrong here. backfill's 07:00 catch-up pass
legitimately fills YESTERDAY as part of the schedule, so a past date rule would
break the nightly rather than protect it.

The real distinction is whether the scheduler or a human is running the module,
and the project already had a name for that: the .bat files set `PMD_JOB` and a
hand run records `manual` in the status record. `artifacts.scheduled_run()`
reads that same variable, so there is one definition of "was this the
scheduler" instead of two that can drift. A scheduled run owns what it writes
and rewrites it freely. A hand run is spared unless it passes `--overwrite`.

Measured both ways on the same command against a past session:

    pool_recall: REFUSED to overwrite runs/2026-08-14/pool_recall.json
                 (13,229 bytes, written 2026-08-14 22:15:31)
    pool_recall: wrote runs/2026-08-14/pool_recall.handrun.json instead.

    PMD_JOB=nightly
    pool_recall: REPLACING runs/2026-08-14/pool_recall.json (13,229 bytes)

**The test names the modules.** Rather than assert behaviour for the three that
exist today, the claim reads each module's source and fails if a writer under
runs/ never calls `artifacts.resolve`. A fourth tool that forgets is the whole
failure mode returning, and it should fail the suite rather than wait for
someone to notice a missing artifact months later.

`tasks/README.md` records the ownership rule next to the existing PMD_JOB note.

## 2026-08-16: the suite is swept against six frozen calendars, and what that found

**Why.** test_entrypoints was green Monday to Friday and red on a Saturday, and
was written on a Thursday. That is a class rather than an incident: trading day
guards, staleness counters that count sessions rather than days, and the quota
day boundary are all calendar sensitive, and nobody knew how many assertions
moved with the date.

**The instrument.** `run_tests.py --freeze YYYY-MM-DD` pins the ET date and runs
the clock forward from 09:00 at real speed. It patches `ettime` on the module
rather than reading an environment variable, because the shipped code must not
grow a way to lie about the date, and nothing in src/ binds those functions
directly so replacing them reaches every caller.

The clock SHIFTS rather than stops, and that detail was learned the hard way.
The first attempt froze it outright, and the suite hung with a zero byte log:
`run_websocket` spins on `while ettime.now_et() < stop_at`, and a now() that
never advances never leaves that loop.

**The sweep.** Six calendars, identical conditions.

| Frozen date | Day | Result |
| --- | --- | --- |
| 2026-08-10 | Monday | PASS |
| 2026-08-12 | Wednesday | PASS |
| 2026-08-14 | Friday | PASS |
| 2026-08-15 | Saturday | PASS |
| 2026-08-16 | Sunday | PASS |
| 2026-09-07 | Labour Day, a market holiday | PASS |

**Finding one: no day of week dependence remains.** The only genuine one was
the calendar guard's ok_codes living in a `__main__` line no importing harness
executes, fixed earlier the same day. Saturday and Sunday now pass where the
suite was previously red on a Saturday, so the sweep is also the check on that
fix.

**Finding two, and it nearly went into this file as the wrong thing.** The
holiday run first FAILED, taking test_scrub and test_txn_guard with it:

    StaleUniverseError: universe.json was generated at 2026-08-13T11:51:26-04:00,
    which is 24.9 days ago. The limit in CRITERIA.md is max_age_days = 10.

Recording that as holiday dependence would have been wrong. A control run on
2026-09-08, an ordinary Tuesday one day further out, failed identically, and
2026-08-21, a Friday eight days from the fixture, passed. The dependence is on
DISTANCE from a fixed fixture stamp, not on the calendar.

That mattered more than a mislabelled entry. Every holiday in the cached
exchange calendar is more than ten days from the fixture, the nearest being
2026-07-03 at forty days before and 2026-09-07 at twenty five days after, so
the holiday case could not be examined at all. The honest report would have
been "holiday never tested", not "holiday fails".

**The fix.** With `--freeze` active, the sandbox copy of universe.json is
restamped to one day before the frozen clock, which removes the distance
variable and leaves the calendar as the only thing changing. The real fixture
is never touched: config.DATA_DIR is already redirected when the restamp runs.
Both the holiday and its Tuesday control now pass, so a market holiday is
genuinely exercised for the first time.

**No test needed renaming.** The clause asked that any test which must depend
on the day say so in its name. None does. What the sweep found was a fixture
age dependence in two suites, which should never have been date sensitive, so
it was injected rather than labelled.

**Standing caveat.** The sweep pins the date and fixes the hour at 09:00. It
therefore says nothing about TIME of day dependence, which is a separate class
and is not measured here. The monitor's rerun windows and the collector's stop
time are the obvious candidates.

## 2026-08-15, second: a refused subscription ends the collector instead of being printed and ignored

**The bug.** `{"status_code":422,"message":"Symbols limit reached"}` carries
neither `s` nor `p`, so it fell into the branch that handles authorisation and
status frames, printed `collector: server said {...}`, and returned. The run
then continued to its stop time subscribed to nothing, folded zero trades,
wrote an empty bar file and exited zero. Nothing downstream could tell that
apart from a quiet morning: the log ends with rc=0, the status record says ok,
and the packet simply has no premarket data.

**Why it is worse than it looks.** Measured on 2026-08-15, the 50 symbol pool
is ACCOUNT WIDE, not per connection as the vendor documents. Two sockets were
opened on the same token; the first took 25 and the second took 25, and the
second was then refused while holding only 25 of its own supposed 50, with the
account at 50. A separate run had one socket accept 50 and refuse at 75.

So a refusal does not mean "this socket asked for too much". It means another
process on this token is holding slots: a probe, a hand run collector, a second
scheduled instance. Any of those silently costs the whole morning.

**The fix.** A new `SubscriptionRefused(RuntimeError)`, raised the moment a
fatal status frame arrives. It is deliberately NOT a `ConnectionError`,
`OSError` or `WebSocketException`, because those three are exactly what the
reconnect loop catches and retries, and retrying is the wrong response: the
slots are held by someone else and every reconnect is refused again until the
window is gone. The test asserts the class is none of those three, so the bug
cannot come back wearing a reconnect.

`main` catches it rather than letting it propagate, so the log carries one
sentence instead of a traceback and the run stats are still written, then exits
1. A run that was never subscribed must not report success, and the morning
chain must not treat its bar file as a window.

Non fatal status frames are no longer only printed. `run_websocket` collects
them and the returned stats carry `status_frames` and the first ten of
`status_frames_seen`, because a morning that saw six odd frames and still
worked is a different morning from a clean one.

**Why now.** The rotation design under consideration, subscribing 50 at a time
and cycling the universe, issues roughly 440 subscribe frames in a morning
rather than one. A design that talks to the subscription endpoint 440 times
cannot sit on top of a refusal that fails silently.

## 2026-08-15: the two suite failures attributed, one real defect and one instrumentation defect

Both failures on HEAD were treated as evidence rather than as broken tests, and
they turned out to be different animals. The distinction matters for how much
the rest of the status records can be trusted, so each is labelled.

### backfill: A DEFECT THE INSTRUMENTATION SURFACED. The guard was right.

`TransactionHeldError: an EODHD request to intraday-1m was attempted with 1
open database transaction(s)` was a genuine read-fetch-write violation, the
fifth site, and the lock audit's four did not include it.

The mechanism, in `backfill()`. The loop held one `store.session()` open across
its whole body. Each iteration called `_true_path`, which spends one intraday
request, and ended with an `UPDATE`, with `commit()` only after the loop. So the
UPDATE at the end of iteration N opened a write transaction that was still open
when iteration N+1 made its network call, and a run over ten picks held the
write lock for the sum of ten HTTP requests. Any other writer meets `database
is locked`.

Why the lexical scan missed it is worth recording, because it is a different
blind spot from `baseline.ensure`, which hid behind a recursive call. Here the
network call and the write are both plainly visible in the same block. The
violation is not in their order within one iteration, where the fetch correctly
precedes the write. It is in the order ACROSS iterations, where the write wraps
around to the next fetch. A scan that reads a loop body once, in the order it is
written, sees fetch then write and passes it.

Fixed by splitting into three explicit phases: read and close, fetch with no
connection open, then reopen and write. The `picks` rows are materialised into
dicts because they now outlive their connection, and the DDL from
`ensure_columns` is committed before the read phase exits so no transaction
survives into the fetch.

Implication: the runtime guard caught something nine lines of careful reading
did not. That argues for trusting the other status records MORE, not less.

### calendar: AN INSTRUMENTATION DEFECT, in the test harness only.

`calendar recorded status 'failed', expected 'ok'` was not the calendar step
failing at anything. The step exited 3, `EXIT_CLOSED`, which is correct: 2026-08-15
is a Saturday.

The shipped entrypoint has always been right. `market_today.py` ends with
`job_status.run("calendar", main, ok_codes=(0, EXIT_CLOSED))`, so a closed
market records `ok` in every real run. No live status record was ever wrong,
and no weekend or holiday has ever been misreported.

The defect was in `test_entrypoints._drive`, whose docstring claims it runs each
entrypoint "the way the scheduler runs it" and which called
`job_status.run(step, module.main, argv)` with no `ok_codes`, taking the default
`(0,)`. The harness reaches the module and calls `main()` directly, so anything
declared inside the `if __name__ == "__main__":` line is invisible to it. A
literal in that line cannot be tested by a harness that never executes it.

This was latent and day-of-week dependent. `EXIT_CLOSED` is only returned when
the market is shut, so the suite was green Monday to Friday and red on a
Saturday. It was written on a Thursday.

Fixed by making the codes a module constant, `market_today.OK_CODES`, read both
by that `__main__` line and by `_drive` through
`getattr(module, "OK_CODES", (0,))`. Any future entrypoint with non-default
codes is now covered without touching the harness. `market_today` is currently
the only module in the project that passes `ok_codes` at all.

### test_repricing: neither. Self-inflicted, and repaired.

Recorded because it touched a committed artifact and because the hazard is
general.

While testing `price_from_collector` on 2026-08-15 I ran
`collect_premarket.snapshot_bars('2026-08-14', ...)` against the existing run
directory. That function is not read-only: it re-copies the live collector file
over the snapshot. It replaced the frozen 08:45 artifact, 1,419 bars ending at
08:43, with the full trading day, 2,155 bars ending at 09:24.
`test_repricing` reads exactly that file, so all eleven of its expected gaps
drifted and the suite went red for a reason unrelated to any code change.

Restored by filtering `data/premarket/2026-08-14.jsonl` to
`minute_epoch <= 08:43`. The reconstruction is exact rather than approximate:
it yields 1,419 lines, matching `collector_snapshot.bars_total` in that
morning's `packet.json`, and ARX returns to 37 bars closing 19.5842, the value
measured from the original before it was overwritten.

The general hazard: `snapshot_bars` mutates the run directory it is pointed at.
Running it against a past session to reproduce a bug destroys the frozen
evidence that session's tests depend on. It has no dry-run mode and nothing
warns.

## 2026-08-14, seventh: src/ is organised into packages by role

Forty files sat flat in src/: production modules, tests, one off probes and
measurement scripts, indistinguishable from each other. They are now eight
packages, and src/ itself is the import root.

| package | what belongs there |
|---|---|
| `core` | config, criteria, ettime, store, eodhd. Infrastructure everything rests on; nothing here knows what a gapper is. |
| `ops` | job_status, market_today, monitor_jobs. Whether the machine is running correctly. |
| `selection` | universe, discover, gap_stats. Which names are worth watching, decided before the open. |
| `collect` | collect_premarket, baseline. Today's tape and the baseline its RVOL is measured against. |
| `morning` | scan, vintage, analyst, render_report, verify_morning, deliver. The 08:45 chain in order. |
| `night` | backfill_premarket, fill_outcomes, pool_recall, build_archive. |
| `research` | backtest_pool, probe_live_v1, the two measure_ scripts. Instruments, not pipeline. |
| `tests` | conftest, run_tests and the nine test_ modules. |

**Module names did not change, only where they live.** `import config` became
`from core import config`, so every `config.X` usage in the codebase stayed
valid and the change was about 200 import lines rather than a rewrite of
thousands of call sites. That was the whole point of choosing this shape over
a renamed package hierarchy.

Scripts run as `python -m package.module` with `PYTHONPATH` set to src, which
is what every `.bat` now does. Running a file by path would put its own
package directory on `sys.path` instead of src, and every import would fail.

**The one genuinely dangerous edit** was `config.PROJECT_ROOT`. It was
`Path(__file__).parent.parent`, and config.py moved down a level, so it would
have silently pointed every writable path at src/ instead of the repository.
It is now spelled out in three named steps rather than chained, with a comment
saying why.

Verified before commit: every module imports in its new home; all 24 module
invocations across the seven `.bat` files resolve; `job_monitor.bat` runs end
to end through real Task Scheduler semantics and writes its dated log; nine
suites pass; both sandbox escape provers still fail correctly; `criteria.py`
resolves every key; and `config.build_identifier()` still finds `.git`.

One first run after the move reported a single changed path that could not be
captured and has not reproduced across five subsequent runs, including a
deliberate cold run with every `__pycache__` deleted. It left nothing behind
in the working tree. Recorded as unexplained rather than attributed, since the
last thing recorded as a transient in this project turned out to be a real
defect of our own making.

## 2026-08-14, sixth: everything outstanding, in the order it had to run

### The news window counts trading sessions

Production built the overnight news window from a calendar day and
`backtest_pool` from the prior trading session. They agree from Tuesday to
Friday and are two days apart on a Monday, which is when it costs most: a
calendar day back from Monday is Sunday 16:00, so the window never reached
Friday's close or anything published across the weekend. Both now call
`discover.news_window_start`, and the drift, not either choice, was the defect.

**Twelve of the sixty cached sessions were affected**, eleven Mondays and the
Tuesday after Memorial Day, each losing 48 or 72 hours. The conclusion
survives without qualification, because the cache was always built on the
corrected window: the backtest used the prior trading session from the start,
so the ordering was measured correctly and only production drifted. A re-run
reproduces the recorded figures exactly, 0.1164 for propensity against 0.0893
for dollar volume, with tier hit rates 0.56, 0.37, 0.40, 0.35.

### The universe write is atomic, and a partial one is refused

`universe.json` is written to a sibling `.partial` and renamed with
`os.replace`, which is atomic on both platforms, so a reader sees the whole
previous file or the whole new one. The Sunday job has never fired, its
roughly 4,700 calls bill to Monday's quota day on a key another project took
50,199 of 100,000 from, and a refused or interrupted run is a real
possibility.

Age was already enforced by `load_universe` through `max_age_days = 10`, so no
second threshold was added for it. What is new is `check_admissible`, which
compares the count against `previous_count` carried in the file itself, under
`min_count_fraction_of_previous`, seeded at 0.5. A stale universe is a usable
input and every later script knows how to refuse one. A half written one is
not, and nothing could tell them apart.

### An unranked pool is not cut

When `load_metrics` could not read the universe, discover still built the pool
and still cut it to 42, but every name sat in the fallback band with no key,
so the subscribed names were arbitrary and the morning looked entirely normal.
Below `min_ranked_fraction_to_subscribe`, seeded at 0.5 against an observed
0.98, discover now records the failure, writes no watchlist and exits non
zero. A missing report is recoverable; a plausible one built from a random
sample is not, because nothing downstream can tell it from a real one.

### A price inside the premarket window can still be hours old

The vintage gate asks whether a price is from today's premarket session, which
a 07:22 print satisfies perfectly while being 83 minutes stale at 08:45. That
is exactly what a collector killed at 08:10 leaves. Every candidate now
carries `price_age_seconds` against the scan clock, and beyond
`max_price_age_seconds`, seeded at 900, it drops into `dropped_stale_price`
with its own reason. Counted separately from `dropped_no_coverage` because the
fixes differ: a subscription slot versus a socket that went quiet.

`collector_window_observed` puts the first and last bar beside the scheduled
window, with `minutes_since_last_bar`, so a truncated morning is visible in
the packet that morning rather than in a status record the next day.

### Zero examined is never a pass

`probe_live_v1` printed "Every reading is from today" over a log of nulls. It
now computes its denominator before any branch that could conclude, and an
empty one reports EXAMINED NOTHING. The rule is in DECISIONS.md, and this was
the fifth instance of one shape in three weeks.

**The audit found a sixth, in the machinery written yesterday.**
`job_status.report_line(rows=[])` returned None and
`monitor_jobs.failed_steps` returned an empty list when no step had recorded
anything, so an absent record file read identically to sixteen healthy steps,
in the mechanism added because the other two sources of truth had agreed on a
lie. Both now report the empty case: the morning line says nothing has
recorded anything at all, and the watchdog reports NO RECORDS as its own
verdict rather than folding it into OK. `failed_steps` returns
`(failures, records_read)`, so no caller can mistake the two again.

180 guards were audited against the rule across all sixteen scheduled modules.
The great majority already comply, most of them deliberately: `score_partial`
and `score_unavailable`, the three-state source constants, `pm_rvol_reason`,
`collector_coverage`, `check_report`'s coverage block. The audit's list of
non-compliers is recorded for future work rather than fixed wholesale, since
several are latent shapes rather than live holes and the week before a first
Monday is the wrong time to change twenty guards.

### Containment sees single letter tickers

The token pattern needed two characters, so all 21 single letter listings were
invisible and a fabricated F or T row returned no findings while the run
printed that containment passed. Those are the symbols a model is most likely
to invent, being the most familiar in the market.

The measured cost of widening: across both archived reports, **zero new
invented-ticker findings**, and claims examined rose from 25 to 29 and from 20
to 23. Two reports is a small sample, so A and I joined the prose stopword
list. A is Agilent and also the English article; I is not a listing at all.
Both are stopped in prose only, and a Ticker column cell reading A is still
checked, which is the case the guard exists for.

### The build identifier no longer writes to the tree it measures

`git status` refreshes and rewrites `.git/index`, so the whole-tree isolation
check failed on a file the check itself had caused to change. It is
`git --no-optional-locks status` now, and three consecutive suite runs pass
with no allowlist addition. `.git` stays watched.

[corrected 2026-08-14: the session that introduced this reported the resulting
intermittent failure as a transient filesystem oddity consistent with a virus
scanner, and left a comment in conftest.py saying so. It was neither transient
nor external. The `universe.json` and git-object transients from the same
session remain genuinely unexplained and are left recorded as such.]

### The morning never fetches the calendar

`market_today.get_details` had no in-process cache, and `job_status.overdue()`
walks day by day per step while scan calls it twice, so a ten day gap across
sixteen steps was hundreds of re-reads and, once the cache went stale on
20 August, would have been hundreds of sequential HTTP attempts inside the
08:45 window. There is now a per-process memo, the nightly refreshes the
calendar with `market_today.py --refresh`, and scan sets `ALLOW_NETWORK` false
so a stale calendar is used as it stands with `calendar_cache` in the packet
recording that it was. Measured: zero network clients built across fourteen
lookups with a fresh cache, and zero with a 2,417 day old one.

### The short side, measured and left alone

Recorded in DECISIONS.md with the full tables. In one line: an upward-gap-only
propensity is worse on this cache at both caps, tier 1 is unchanged at 0.55
because direction cannot be known at 07:15, and the comparison is confounded
because the variant has 60 sessions of history against the shipped key's 250.
Nothing shipped changed, and the 2026-08-14 replay is byte identical to
4cd4a3b, digest 9918b22d.

## 2026-08-14, fifth: the premarket source question, and two fields corrected

### real-time/(symbol) is not real-time/?ex=US, and that had never been checked

`bulk_live_us()` hits `real-time/AAPL.US?ex=US` and serves the last completed
session, which is the defect that published the wrong prices on 2026-08-14.
`live_quotes()` hits the same endpoint family per ticker as
`real-time/{symbol}`, and nobody had ever checked whether the per ticker form
behaves the same way. The two answers lead to different systems: if it serves
the last completed session it is useless before the open and the candidate
pool prior is the only way to choose names at 07:15; if it serves today, a
2,745 name sweep at 07:15 sees the real overnight move for the whole universe
and replaces the prior outright at about 2,745 counted calls.

**A single call on 2026-08-14 at 13:42 ET settled half of it.** SPY came back
with a timestamp of 13:26 the same day, sixteen minutes behind the wall clock
but unambiguously the current session: close 775.65 against a previousClose of
777.88, volume 14.5M. A second sample two minutes later had advanced to 13:29.
So the per ticker form is **not** the exchange wide form's
last-completed-session behaviour. It is Live v1 with the roughly seventeen
minute delay this project already documents.

**That is not the answer to the question.** Whether the feed ticks during the
premarket window is a different fact from whether it ticks during regular
hours, and a lunchtime reading says nothing about it. A feed that only updates
from 09:30 would return the prior close all morning and be indistinguishable
from the bulk endpoint until the bell. Treating the regular hours reading as
the answer would be the same overreach that produced Thursday's report.

So `src/research/probe_live_v1.py` samples five context tickers every three minutes
from 08:00 to 09:15 and puts the collector's own bar for the same minute
beside each reading, the collector being ground truth because it is a trade
socket. Roughly 26 calls, five symbols to a request. It is standalone: nothing
imports it, nothing reads its output, it writes no status record, and
CRITERIA.md [job status steps] deliberately does not carry it. Registered as a
one time task for Monday 2026-08-17 at 07:55 and meant to be deleted after.

Its `--report` mode counts how many readings carried a feed timestamp inside
the premarket window and refuses to conclude anything about 07:15 from
readings that did not. On today's lunchtime sample it correctly reports
PARTIAL.

The lag column is what will decide the follow up even if the answer is yes: a
sweep at 07:15 reading a feed that is seventeen minutes behind is reading
06:58, which is early in the premarket session and may or may not carry the
overnight move.

### A field that could never be populated

`scan.py` read `selection_gap_pct` into every `dropped_no_coverage` record.
Nothing has written it since d224837, when discover stopped computing a
selection gap, so it was always null. That is worse than useless in this
project specifically: the rule is that missing evidence stays null with a
recorded reason, so a permanently null field reads as evidence that was
sought and not found rather than as a field with no writer.

Replaced with `pool_tier` and `pool_source`, which discover does write and
which answer the question the field was presumably there for: why this name
was in front of the collector at all. No document referenced the old key, and
the only other occurrences are in test_repricing, which builds its own in a
test-local fixture to stand for what a stale packet said. That fixture is why
the orphan stayed invisible: the regression test hands the read the value no
production path supplies.

### The same check found a second one, and it would have fired on Monday

The read-without-writer scan covered **446 reads** across every consumer of a
candidate, packet, watchlist row, picks row, market snapshot row or bar row,
in all sixteen scheduled modules plus the report template and the analyst
prompt. Two orphans, both from the same commit, both left behind by the same
rewrite.

The second is `collect_premarket.py`, printing the names it dropped to fit the
socket cap:

    print(f"    dropped {row['symbol']:<12} gap {float(row.get('gap_pct') or 0):+7.2f}%")

discover stopped writing `gap_pct` onto watchlist rows at d224837, the same
commit that stranded `selection_gap_pct`. The collector's own docstring even
records the removal, saying the re-sort by gap was dropped because the field
"no longer exists on a watchlist row". The re-sort went. This print did not.

**It has not fired yet only by an accident of timing.** d224837 landed at
10:02 on 2026-08-14 and the watchlist on disk was generated at 07:15:04 the
same morning, so the only watchlist the new code has ever met was written by
the old code and still carries the key. Monday 2026-08-17 at 07:15 is the
first watchlist written under the current code, and at 07:20 the collector
would have printed a confident `gap +0.00%` for every dropped name.

That `or 0` is the whole defect. A missing key becoming a plausible number is
the same failure as the stale price, one log line further down, in the exact
line that justifies which names were cut. The header lied too: "lowest
absolute gap first" has not been the order since d224837. The line now reports
tier, rank and pool source, which are fields that exist, and says it is
discover's ranking, which is what it is.

Both were found by an audit of reads rather than by a test, because a test
that replays an old packet supplies the very key that production stopped
writing. The general lesson is the one from the pool_recall week in a
different costume: a fixture that is more generous than reality hides exactly
the defect it is meant to catch.

### bulk_live_us has no caller in any scheduled job

The 9b5e43a report described the endpoint as retained for membership. It is
not used for that or for anything else in the pipeline. Audited: the only
caller in the repository is `measure_bulk_cost.py`, which exists to price the
endpoint on the vendor's own counter, and `test_pool.py` fails if the name
reappears in discover. None of the sixteen scheduled entrypoints reach it.

Its docstring opened with "Latest live OHLCV for every US listed ticker, in
one call", which is the claim that produced Thursday's report, and which
`scan.pool_candidates` had already been corrected to contradict while the
client itself still asserted it. It now names the actual behaviour, says it is
never a source of today's premarket, records that it is retained only for the
cost measurement, and warns explicitly that the per ticker form does not
behave the same way, so nobody reasons from one to the other in either
direction.

### Still open after this entry

The premarket half of the source question, which needs Monday's sampling run.
If `real-time/{symbol}` does tick before the bell, the follow up is a costed
comparison between a 2,745 call universe sweep at 07:15 and the pool prior,
and that is a bigger change than it sounds: the pool exists because no source
on this plan had today's move for the whole universe at 07:15. If that premise
is wrong, the tier ordering, the propensity ranking and the cap measurement
are all answers to a question that need not have been asked. None of that
should move before the probe reports.

## 2026-08-14, fourth: the isolation guard is inverted, and two numbers distributed

### The isolation check photographs the tree

The check that proves the suite wrote nothing outside its sandbox used to name
the roots it watched, and gained one per escape: runs/, then data/, then the
database, then site/ when the entrypoint tests caught build_archive rewriting
the published archive. Four fixes, each correct about the root it had just
been taught and blind to the next. That is what a check written as a list of
what to guard does.

It is inverted now. `conftest.snapshot_tree()` photographs every file and
directory under the repository before the suite and again after, and anything
that appears, disappears or changes outside a two entry allowlist,
`__pycache__` and `.pytest_cache`, fails the run and is named.

**The numbers.** The tree-wide photograph covers **1,379 paths**. The
enumerated version watched **275** of them. The other **1,104 paths were the
exposure**, and they include every one of src/, doc/, tasks/, logs/, .git/ and
the virtual environment. That is what could have been written to by a test
that hardcoded a path, at any point before this entry, without the suite
saying a word.

Directories are tracked for existence but not for mtime, because a directory's
mtime moves whenever anything inside it is created and an allowed
`__pycache__` write would otherwise fail the run through its parent. A new
directory still fails, so a test creating runs/2026-08-15/ is caught before it
writes anything into it.

`--prove-check` still writes to runs/ and still fails, naming the file.
`--prove-check-outside` is new and writes to tasks/, a root no version of the
enumerated check ever watched: it fails too, which is the point.

### The mains that were returning zero without recording

pool_recall got `job_status.failed()` in the previous entry. Auditing every
other main that returns zero on an exception path found six more, and the list
is written down here rather than quietly closed, because the size of what the
status record was missing is the useful part:

1. **collect_premarket**, on `KeyboardInterrupt`. A collector stopped at 08:10
   produced a genuine file covering half the window and exited zero. Nothing
   distinguished that from a quiet morning.
2. **discover**, when `load_metrics` could not read the universe. It catches
   every exception and continues with empty metrics, which does not stop the
   pool being built, it stops it being ranked: every name falls to the fallback
   band and the cut becomes arbitrary. This was the worst of the six.
3. **discover**, when a pool source raised. It was recorded in watchlist.json
   as `not_fetched` with its reason, which is the right place for the audit
   trail and the wrong place for a human to find out that the morning is being
   built from three priors instead of four.
4. **gap_stats**, which has always returned the list of symbols it could not
   fetch, and whose main has always thrown that list away. Every symbol could
   fail and it exited zero.
5. **build_archive**, on an unreadable packet.json. The session is archived
   without its counts, which is how the archive quietly stops being the record
   it exists to be.
6. **monitor_jobs**, on an unreadable rerun state file. It reads as "nothing
   has been rerun today", which silently stops `max_reruns_per_job_per_day`
   being enforced and lets a hard failure loop.

Every exit code is unchanged. Only the record changed. Where the failure is
per item rather than fatal, the trigger is producing nothing at all, which is
unambiguous and needs no threshold to judge.

test_entrypoints forces the calendar guard to raise and asserts both halves:
it still exits zero and still assumes the market is open, and it now records
the RuntimeError. That guard runs at the head of five of the six jobs, so it
was five of the twelve silent step invocations on its own.

### The watchdog reads step records, not only the final marker

The nightly reported OK every night for a week with pool_recall failing inside
it, because the marker it reads belongs to the archive and the archive really
did finish. `monitor_jobs.failed_steps()` now reads every status record for a
job on the day and reports the job as failed naming any step that recorded
one. A step that failed and was later rerun successfully is not reported,
because the last record is the one describing the state the machine is in now.

The marker check stays exactly as it was. The two answer different questions: a
step record catches a step that failed, and a marker catches a job that died
before writing any record at all. Both cases are asserted, including a nightly
killed before the archive, which writes no pool_recall record and would be
invisible to the step check alone.

### Screen passes, distributed

6.57 is a mean over a population whose gapper counts run 42 to 518 a session.
The socket decision was resting on it and on the 12.33 and 15.62 beside it.

| cap | min | p25 | median | mean | p75 | max |
|---|---|---|---|---|---|---|
| 42 | 0 | 2 | 5.0 | 6.6 | 11 | 25 |
| 67 | 0 | 3 | 7.5 | 9.8 | 15 | 38 |
| 92 | 0 | 4 | 8.5 | 12.3 | 18 | 54 |
| 142 | 0 | 5 | 9.5 | 15.6 | 23 | 70 |

The median differs from the mean materially and it steps differently. On means
the four caps go +3.2, +2.5, +3.3, which is the flat decay the record
described. On medians they go +2.5, +1.0, +1.0. The median to mean ratio falls
as the cap rises, 0.758, 0.765, 0.691, 0.609, which says extra slots pay off
disproportionately on sessions that were already busy: tripling the cap takes
the typical morning from 5 publishable names to 9.5 and the busiest from 25 to
70. At every cap the minimum is 0, so no amount of capacity buys a report on
the emptiest mornings.

**The socket arithmetic does change.** On means the third socket buys 58
percent of what the second buys and reads as a smaller version of the same
deal. On medians it buys 29 percent: the second socket adds 3.5 publishable
names to a normal morning, the third adds 1.0. The second remains the better
purchase either way, which is unchanged. The DECISIONS cap item carries the
distributions and three correction markers.

`backtest_pool` reports `screen_passed_distribution` alongside the mean, and
`blindspot` already reports its own after the previous entry.

## 2026-08-14, third: silent failure is made impossible, and two numbers close

pool_recall failed on every nightly run for a week and left nothing anybody
would see. The fix for that one step landed with the documentation
reconciliation below. This entry is about the question that mattered more:
how many other steps could do the same, answered by inventory rather than by
guessing, because guessing which ones were exposed is what produced the bug.

### What every scheduled step did when it failed, before this entry

Six .bat files, twenty one step invocations, sixteen distinct modules. The
"trace" column asks whether a failure would reach a human, not whether it
appeared anywhere: every step writes its exit into a dated log, and the whole
point of the pool_recall week is that a traceback in `logs/nightly-*.log` is
not a trace if nobody reads that file.

| Job (trigger) | Step | Exit code | main catches | Read downstream | Entrypoint test |
|---|---|---|---|---|---|
| universe (Sun 20:00) | universe | checked, stops job | RuntimeError | universe.json, by everything | none |
| universe | gap_stats | checked, ends job | none, propagates | gap_stats table, by discover | none |
| discover (07:15) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| discover | discover | checked, stops job | StaleUniverse, QuotaRefusal, RuntimeError | watchlist.json, by collector, baseline, scan | none |
| discover | baseline | checked, ends job | none, propagates | baseline table, by scan | none |
| collector (07:20) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| collector | collector | checked, ends job | KeyboardInterrupt | the bar file, by scan, backfill | none |
| morning-chain (08:45) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| morning-chain | scan | checked, stops chain | StaleUniverse, QuotaRefusal, StaleDataError | packet.json, by analyst, verify | none |
| morning-chain | analyst | checked, stops chain | none, propagates | report.md, by render | none |
| morning-chain | render | checked, stops chain | none, propagates | report.html, by deliver, archive | none |
| morning-chain | verify | IGNORED, by design | none, propagates | nothing, it prints a table | none |
| morning-chain | deliver | checked, stops chain | none, propagates | nothing | none |
| morning-chain | archive | checked, ends job | none, propagates | nothing | none |
| nightly (22:15, 07:00) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| nightly | backfill | checked, stops job | none, propagates | picks columns, by outcomes | none |
| nightly | outcomes | checked, stops job | none, propagates | picks columns | none |
| nightly | pool_recall | IGNORED, by design | Exception, returns 0 | NOTHING | none |
| nightly | archive | checked, ends job | none, propagates | nothing | none |
| monitor (07:25 x5, 22:45) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| monitor | monitor | checked, ends job | none, propagates | its own rerun state | none |

**Twelve of the twenty one could fail without leaving a trace**, across eight
modules. The calendar guard is five of the twelve on its own: it catches every
exception and returns 0 so a guard fault cannot kill a real morning, which is
right, and it then proceeds on an assumption nobody is told about. The rest are
pool_recall, verify, gap_stats, the collector, backfill, outcomes and the
watchdog. Two patterns produce all of them: a main that returns 0 on a path
that did no work, and an output nothing downstream reads.

**The last column is the finding.** Not one scheduled entrypoint had a test.
Every suite tested a function underneath one. That is not an accident of this
codebase; a pure function is easy to test, so it gets tested, and the wiring
where a rename can strand a name does not.

**And there was a fourth concealing layer, not three.** The watchdog checks
each job's final step marker, and the nightly's is the archive, which runs
after pool_recall and really did finish. So the nightly reported OK every
night while the step inside it wrote nothing. That layer is correct and stays:
a watchdog that failed the nightly because a diagnostic died would be worse.

### Every job now records whether it succeeded

`src/ops/job_status.py`. Every scheduled step appends one line to
`data/job-status.jsonl` as it exits: job name, start and end in ET, status,
exception type, and one count of what it produced. Written in a `finally`
block, catching BaseException, so a collector killed with Ctrl-C and a nightly
killed by a reboot both record dying. The `.bat` files set `PMD_JOB` so a
record says which job the step ran under, and a hand run records `manual`.

The exit code is unchanged everywhere. `job_status.failed(reason)` is how a
step keeps its zero and corrects its record: pool_recall calls it in the
handler that swallows its exception, so the chain still cannot break on a
diagnostic and the failure still reaches the morning. The calendar guard calls
it when it assumes the market is open after an error, and the analyst calls it
when the narrative falls back to the numbers only report.

Staleness is counted in trading sessions, not hours, so a weekend cannot raise
a false alarm and a Tuesday holiday cannot hide a real one. Windows are in
CRITERIA.md [job status steps], one per step, 1 for a weekday job and 5 for
the two that ride the Sunday schedule. A step with no success at all is
reported only once the record file itself is older than that step's window,
because nothing can be overdue before there was anywhere to record it, and a
line naming every step on the day this landed would have taught the reader to
skip it.

The morning report gains one line naming any overdue step, and nothing at all
when every step is current. It is written by `analyst.annotate_job_health` in
Python, appended to the disclaimer line the template guarantees, rather than
asked of the model in the prompt: the one morning a model forgets a prompt
rule is the morning it mattered. Past four overdue steps the line stops
listing them and says the machine or the schedule has stopped, naming the
worst few, because sixteen named steps is one problem rather than sixteen.

### Tests cover entrypoints now, not only the functions beneath them

`src/tests/test_entrypoints.py` drives all sixteen scheduled entrypoints through
their own `main`, with the arguments the `.bat` passes, against the sandbox
roots. The HTTP client is stubbed with a scripted session that records every
path, so each step asserts the endpoints it actually asked for. Two steps
reach the outside world through something other than the HTTP client and are
stubbed at the equivalent layer, both marked in the file: the collector's
socket, replayed through `_connect` with one deliberately silent symbol, and
the analyst's claude CLI, stubbed at `invoke_claude`.

Every entrypoint is also asserted through its status record, which is what
catches the pool_recall shape specifically. Its exit code is zero whether or
not `build()` worked, by design, so a test asserting the exit code would have
passed all week. The record is what tells the two apart.

The suite also checks the CRITERIA.md step list against the list of steps it
drives, in both directions. A step the scheduler runs that is missing from
that list would never be reported overdue, which is the one way the whole
mechanism can fail silently.

**It found a sandbox hole on its first run.** `build_archive` built its output
path as `config.PROJECT_ROOT / "site"` rather than reading it from config, so
the sandbox could not redirect it and the suite rewrote the real published
`site/PremarketDesk.html`. The mtime check did not catch it because it watched
`runs/` and `data/`, where the previous three escapes happened. `config.SITE_DIR`
now exists, conftest redirects it, and run_tests photographs it too.

### The collector reports its own coverage

Monday is the first morning at fifty subscriptions and the socket has only
ever been load tested at thirty eight, which was the old thirty plus eight
configuration. The collector now writes
`data/premarket/<date>-subscriptions.json` at subscribe time, before the first
trade, listing what it asked the socket for. It has to be written then: the
run stats sidecar is appended when the collector stops at 09:25, forty minutes
after the packet is built.

The packet gains `collector_coverage`: the count requested, the count that
produced at least one bar, and the names of any that produced none. A symbol
that was subscribed and stayed silent is a different failure from one that was
never subscribed, and both now appear, the second as
`unsubscribed_with_bars`. With no subscription list the block says so rather
than reporting every absent symbol as never subscribed.

`peak_trades_per_minute` comes off the bars, which already carry a trade count
per minute, so nothing was added to the receive loop. On the 2026-08-14
snapshot at thirty eight symbols that peak was 5,697 trades in a minute. The
late trade count is not there: it lives in the running builder and is only
written when the collector stops, so it stays null with that reason recorded
rather than being filled from a previous run.

### The two gapper counts reconcile, and neither was wrong

The blindspot stage implied 173.7 gappers a session while the backtest and the
live pool_recall both gave 99 for 2026-08-13. There is no definitional
difference: both stages read the same `outcome["gappers"]` object out of the
same cache file, built once by the fetch stage with the same `> 3` rule on the
absolute gap, so both directions count, measured as the session open against
the prior session close, over the same 2,745 name universe in every session.

The distribution explains it. Over the sixty cached sessions the count runs
42, p25 91, median 142, mean 173.7, p75 236, max 518. It is strongly right
skewed, so the mean sits well above the typical session, and 99 is rank 40 of
60, in the lightest third.

What made 2026-08-13 look like it should be heavy was its earnings calendar:
37 names before the open against a median of 6.5, the 9th heaviest of the
sixty. On the other two sources it is light, rank 48 of 60 on overnight news
and 53 of 60 on prior session movers. Earnings weight and gapper count
correlate at 0.465, so a heavy calendar does not imply many gappers, and
"heaviest calendar day" and "heaviest day" are not the same claim. No figure
needed correcting. `blindspot` now reports the distribution rather than the
mean alone, because a mean is a poor summary of a 42 to 518 spread.

### Corrections are marked

The four numbers corrected in place on 2026-08-14 now carry
`[corrected 2026-08-14: was X]` markers naming what they said before, and both
records state the rule at the top: errors of fact are corrected in place with
a marker, superseded decisions keep their original text. The DECISIONS item
citing pool_recall as accumulating evidence nightly is corrected to say the
evidence began accumulating on the date the fix landed.

## 2026-08-14, second: the documentation was reconciled and it found a bug

Five commits in one day changed discovery, pricing, ranking, the schedule and
the schema, and the documents were audited against the code rather than
against memory. Every document was read by a separate auditor and every claim
it raised was verified against the source before being acted on: 114
discrepancies confirmed, 11 refuted and left alone.

**The audit found a live bug, which is the part worth recording.**
pool_recall.build referred to a name, `floor`, that had been renamed to
`gap_rule` when the gap threshold moved from a number to a rule. The signature
and the one comparison were updated and three later uses were not, so every
nightly run raised NameError before writing anything. Nothing caught it: main
caught RuntimeError only, the nightly batch file ignores that step's exit code
by design so a diagnostic cannot fail the chain, and the only test exercised
pool_recall.measure, the pure function, never build, the one the scheduler
calls. So the measurement that DECISIONS.md cites as "accumulating the evidence
nightly" had accumulated nothing.

Fixed, and the hole it came through closed with it. main now catches Exception
and always prints the type, because a diagnostic that fails silently is worse
than no diagnostic. test_pool.py gained claim 8, which runs build end to end
against a stubbed client and a synthetic universe and asserts the file is
written with the right arithmetic in it: one gapper, recall 0.0, the missed
name listed.

**What else was wrong.** Both architecture pages predated all five commits.
CRITERIA still documented `max_quote_age_hours` and `run_after`, two keys with
no readers left, and described the bulk live deduplication and the live-first
market snapshot as though either still ran. REPORT_TEMPLATE and the analyst
prompt still told the model to report `collector_covered false`, a state that
can no longer reach the packet because drop_uncovered removes those candidates
before enrichment. The README described a low effort analyst measured at 65 to
78 seconds, a self check that prints a TLS line it does not print, and a
trading day guard on every job including the Sunday one that does not have it.
tasks/README listed five jobs and missed three steps. BUILD_PLAN said five
scheduled jobs and a 233 second timeout.

Four numbers in the append-only records were wrong when written and were
corrected in place, since a record that misstates its own measurement is not a
record: pool_recall makes two bulk calls not one, sixty sessions cost sixty two
bulk days not sixty one, 109 of 355 null-propensity gappers is 31 percent not
half, and the 88 percent miss is the whole miss rather than the cap's share,
which splits about 50 points to the cap and 38 to the pool's reach. The
collector load test figure of 38 symbols was the OLD configuration, 30 plus 8,
and the current cap already asks for 50, which makes the throughput
precondition on the cap decision stronger rather than weaker.

## 2026-08-14

### The bulk real-time endpoint lags a session, and nothing noticed

The first fully scheduled live morning ran clean, exit zero at every step, and
published a report describing the previous session.

`/real-time/{any}.US` returns the last COMPLETED session. At 08:45 ET on a
trading day the last completed session is yesterday, so the endpoint's `close`
is yesterday's close and its `previousClose` is the close before that. The
scan read the first as this morning's premarket price and the second as the
prior session close. Confirmed against EODHD's own end of day history for all
twelve candidates: twelve of twelve `prior_close` values equalled the 08-12
close, and eleven of twelve `price` values equalled the 08-13 close to the
cent.

Four fields were corrupted by that one read:

- `price`, which was the prior session's close rather than a premarket print.
- `prior_close`, which was the close of the session before that.
- `gap_pct`, computed between those two, which was therefore the prior
  session's own move. ARX was published at "gap +43.35 percent" when its real
  premarket gap that morning was +0.38 percent, and WDAY at +17.78 percent
  when its real gap was +0.14 percent.
- `pm_rvol`, whose numerator was the delayed quote's `ethVolume`. That field
  describes the previous extended session until the vendor rolls it, measured
  on this date as after 08:45 and before 08:56. At 08:45 it gave ARX
  20,744,130 shares of yesterday's post market.

`prior_high` was the only one of the group that was right, read from end of day
history and correctly dated to the prior session. That is what made the failure
visible: `price` and `prior_high` were both from 2026-08-13, so the
`require_above_prior_high` gate compared a session's close against its own
high, which can never pass. Both watchlists were structurally guaranteed empty,
and the report explained it as a dull tape.

Fixed by sourcing every published price from the collector, which is the only
feed on this plan carrying today's premarket, and by reading `prior_close` and
`prior_high` out of the same end of day record so they cannot drift apart
again. The bulk endpoint is kept for membership only, where ranking 2,745 names
in one call is a thing nothing else can do, and every field it produces is
named `selection_*` and overwritten before scoring. See DECISIONS.md.

### A vintage assertion that ends the run

Nothing in the pipeline had ever asked whether the data was from today, so
nothing objected. `src/morning/vintage.py` now asks, after pricing and before scoring,
and a violation ends the run: the gate marker is rewritten naming every failing
row and scan exits non-zero, which stops the morning chain before the analyst
call. There is no degrade path, because a stale price is not thin evidence to
hedge around.

Four checks. (a) every priced candidate's price timestamp falls inside today's
premarket window. (b) `prior_high` is not below `prior_close`, since a session's
high cannot be below its own close. (c) the prior close is dated to the prior
trading session per the exchange calendar, not merely to some earlier date.
(d) the market snapshot is from today, where a row explicitly labelled
`prior_session_only` is held instead to being correctly dated to the prior
session.

Check (b) alone would have caught this morning without a single vendor call:
six of the twelve candidates carried a `prior_high` below their own
`prior_close`. Replaying that packet through the check now fires (a), (b) and
(d), leaves (c) silent because that field was in fact correct, and names all
six impossible rows in the marker file. `src/tests/test_vintage.py`.

### A floor under the RVOL denominator

`usable_for_rvol` accepted any baseline with enough sessions and a median above
zero. ARX's premarket median was 23.5 shares and MH's was 10, so the ratio
built on them was arithmetic without meaning: ARX scored an RVOL of 882,728 and
maxed the RVOL scoring band by construction. Six of the twelve candidates sat
below the new floor.

`min_baseline_premarket_volume = 1000` shares, in CRITERIA.md under Baseline
next to its sibling `min_sessions_for_rvol`, which is the threshold it works
with and the function that reads it. A seed value chosen to exclude degenerate
denominators, not a validated threshold. Below it, `pm_rvol` is null with the
reason recorded and the RVOL component is unavailable, which routes through the
existing `score_partial` and `score_unavailable` machinery from 2758972 rather
than a second path: the total goes null, the conviction bucket goes null, and
the report says unscored.

A floor on the denominator, not a cap on the ratio. A cap would have turned
882,728 into a plausible looking number and hidden the fact that the
denominator was never usable.

### Containment went dark exactly when it mattered

`claims_checked` was 0 and `columns_scanned` was 0. Both screens were empty, so
the model omitted both watchlist tables entirely, and the tables are where the
guard finds the `Ticker` header it locates claims by. Meanwhile the report
named twelve tickers in bold prose, none of them validated. The check reported
a clean pass over a report it had not read.

Two changes, folded into the existing containment path rather than a second
one. REPORT_TEMPLATE.md and prompt rule 12 now require both tables to be
written even when empty, header and separator and a single `| none | | | |`
row, and the deterministic fallback report does the same. And containment now
extracts ticker shaped tokens from prose as well as table columns: a report
with prose ticker claims and no ticker column at all is a structural failure,
returning 2, not a pass with a footnote.

Prose is ambiguous where a Ticker column is not, so time expressions and ISO
dates are stripped before tokens are taken (`06:37 ET` is a time, and ET is
also Energy Transfer) and a stopword list in CRITERIA.md removes what survives.
That list contains some real tickers and is a recorded fail-open; see the prose
stopword note there.

### Also

- Candidates the collector never subscribed to are dropped rather than priced,
  named in the packet's new `dropped_no_coverage` list with a reason, and
  counted in the run summary. See DECISIONS.md.
- `packet.json` carries `build`, the resolved commit and a dirty flag, so a
  report can be tied to the code that wrote it.
- A null `gap_pct` no longer reads as a checked zero in the eligibility test,
  which would have produced "gap_pct 0.00 fails > 3", a claim about the stock
  made out of a fact about the pipeline.
- The gate table in verify_morning.py now shows the price and the minute it
  printed, alongside the collector premarket volume that feeds RVOL. The
  failure that made the gate earn its keep was invisible without a clock beside
  the price.

### Discover stopped ranking a stale feed and started building a pool

The stale vintage fix above repaired what the 08:45 scan did with its numbers.
It did not touch where the names came from. discover.py was still calling the
bulk /real-time endpoint at 07:15, ranking the whole universe by its gap, and
keeping the top 30, so it was still ranking the previous session's movers. The
collector only ever subscribes to what discover chose, so every morning's
evidence was still being gathered for the wrong names before the scan ran.

Gap ranking is gone from discover. Nothing there reads a price from today,
because at 07:15 no source on this plan has one for the whole universe.
Selection is now a prior assembled from four things knowable before the open,
unioned, deduplicated, and intersected with universe.json:

- **earnings before open today**, from the calendar API. EODHD supplies
  before_after_market and a report_date but no clock time, so a 07:00 reporter
  and an 08:30 reporter are not distinguishable in this feed. The field is
  recorded as the vendor gives it and timing_precision says so.
- **overnight news**, from a symbol-less sweep of the news feed over the window
  from 16:00 ET the prior day to the run clock, paged and bounded, with each
  name carrying the timestamp of its newest item.
- **prior session movers**, from two bulk end of day calls so the move is close
  to close. This is the input the pool always had, now labelled as the
  continuation prior it is rather than mistaken for today's gap.
- **recent runners**, from the picks table, weighted by a per session decay so
  three days ago outranks three weeks ago.

A source that fails records not_fetched and a source that succeeds with nothing
records fetched_and_empty, the distinction catalyst_why already draws, so a
pool missing its earnings names is never mistaken for a morning without
earnings.

The pool is ranked by tier, then by 20 day average dollar volume descending,
and cut at max_subscribed_candidates, seeded to 42 so it fits the collector's
50 socket slots alongside the 8 context tickers. Everything below the cut is
written to watchlist.json marked not_subscribed, so the cut is auditable.

At 08:45 the pool tier becomes a recorded field and nothing more. scan ranks
the subscribed names by the gap it actually measured from the collector, so a
tier 5 recent runner with the morning's biggest move ranks first. pool_source
and pool_tier are carried into the packet and the picks row.

Cost: two bulk end of day calls at a measured 98 counted calls each, one
calendar call and up to five news calls, against the one bulk live call at 100
that this replaces. About 100 counted calls a morning more, far below the
bulk_redesign_line.

### pool_recall, and what it already says

The nightly pass reads today's end of day for the whole exchange, works out
which universe names actually gapped at the open against their prior close,
and writes runs/<date>/pool_recall.json: how many gapped, how many the pool
held, the recall fraction, and the names it missed. Two bulk end of day
calls, today's and the prior session's, because the gap is measured open
against prior close and one call carries only one of them.
[corrected 2026-08-14: was "one bulk call"]

Backtested against 2026-08-13, whose real gappers are known:

- 99 universe names gapped beyond the 3 percent floor at the open.
- The pool held 72 of them. Recall 0.727.
- The 42 actually subscribed held 28. Recall 0.283.
- All 28 hits came from tier 1. Of 37 subscribed earnings names, 28 gapped.
- The five tier 2 slots that remained went to MU, NVDA, AAPL, MSFT and AMD by
  dollar volume. None of them gapped.

So the pool finds the gappers and the cut throws most of them away, and the
dollar volume tiebreak is what throws them: inside the news tiers it sorts
toward the largest names in the market, which are the least likely to gap.
On 2026-08-13 that cost little because 37 earnings names filled 37 of the 42
slots. On 2026-08-14, a light calendar with 2 earnings names, it would have
spent 40 of 42 slots on mega caps. The tier ordering is marked in CRITERIA.md
as a seed and an assumption about base rates; this is the first measurement
against it and it says the assumption is wrong below tier 1.

### The recall harness moved into the repository

The tool that produced the 2026-08-13 recall numbers was a scratchpad script.
It is the instrument that decides the tier ordering, so it is now
src/research/backtest_pool.py, version controlled and tested, and split into two stages
that never run together.

**fetch** reconstructs one historical session's inputs, the earnings calendar,
the overnight news sweep, the prior session end of day and universe membership,
together with its outcome, the open against the prior close for every universe
name. Both go to a cache keyed by session date under data/backtest/. This is
the only stage that touches the network.

**evaluate** reads the cache and nothing else, applies a named ordering
configuration, and reports pool recall, subscribed recall, per tier hit rates
and the missed names. src/tests/test_backtest.py arms every outbound path to raise
and then runs every ordering to completion, so the zero network claim is
asserted rather than asserted-to.

The split is the point. Fetching is slow, dated and expensive enough to afford
once; evaluating is free and will be run once per ordering candidate, and every
comparison has to come from the same bytes. Bulk end of day is cached per day
rather than per session because consecutive sessions share it, so sixty
sessions cost sixty two bulk days rather than a hundred and eighty, a session
needing its own day, its prior and the one before that.
[corrected 2026-08-14: was "sixty one bulk days rather than a hundred and
twenty"; sixty two is what the fetch actually spent, and three days per session
over sixty sessions is a hundred and eighty, not a hundred and twenty]

From cache alone the harness reproduces the published 2026-08-13 figures
exactly: 99 gapped, pool held 72 at 0.7273, subscribed held 28 at 0.2828.

### Gap propensity, measured rather than proxied

src/selection/gap_stats.py computes, for every universe name over a trailing 250
sessions, the fraction of sessions whose open sat beyond the discovery gap
floor from the prior close, the median absolute gap on those sessions, and 20
day ATR as a percent of price. It rides the universe rebuild schedule in
tasks/job_universe.bat, so nothing is computed at 07:15.

Rows are keyed by (ticker, as_of), which is what lets a backtest rank on a
window that ended before its earliest session instead of one that includes the
sessions being scored. A name with fewer than min_sessions of history stores a
null propensity and its real sessions_used, never a computed zero: a name
nobody has measured and a name that has not gapped in a year are different
facts, and order_pool sorts nulls last within their tier rather than as zero.

Measured cost: 2,745 symbols in 2,745 counted calls and 421 seconds, zero
failures. 2,708 measured and 37 null at the 2026-08-13 window.

### Sixty sessions cached

60 consecutive trading sessions from 2026-05-19 to 2026-08-13, spanning a full
quarterly earnings cycle so the sweep sees the heavy calendar case and the
light one rather than whichever the last fortnight happened to be. 62 bulk end
of day days, 27MB, under data/backtest/, which is gitignored.

Cost: the meter moved 52,888 to 62,736, so 9,848 counted calls, but the gap
propensity run overlapped it and the shared key has a sibling consumer, so that
figure is an upper bound rather than an attribution. The harness's own ledger
records 373 HTTP calls for the fetch: 58 bulk end of day at a measured 98
counted each, plus 249 news, 58 calendar and 8 others, which puts the fetch's
own share near 6,000.

The fetch checks the preflight every ten sessions and stops cleanly if the key
drops to the degrade threshold, reporting how many sessions were cached. A
partial cache is usable; evaluate takes whatever sessions it finds.

### Also

- test_store.py wrote to the live database, so it failed with "database is
  locked" whenever a real job held a write transaction, which is a fact about
  the machine rather than about the code under test. It now runs against a
  throwaway database, the same reasoning as the runs/ sandbox added to
  test_scrub.py.
- gap_stats.py held one write transaction open across two thousand HTTP calls,
  which is what locked the database. It now fetches first and writes once.

### The measured ordering was adopted

within_tier_key is gap_propensity and min_slots_per_tier is 4, both in
CRITERIA.md with a citation rather than a seed marking: the sweep window, the
session count, the out-of-sample date and the recall of the chosen
configuration against the one it replaces. Replayed under the shipped
configuration the 60 cached sessions give 0.1164 mean subscribed recall against
0.0842 for the dollar volume key it replaces, and 0.0893 for that key given the
same floor.

The harness gained a SHIPPED configuration that ranks through
discover.rank_value rather than a copy of it, so the row that claims to measure
production moves when CRITERIA moves.

### Null propensity falls back to ATR

gap_propensity needs 100 sessions, and newly listed names are over-represented
among hard gappers: SECZ gapped 25.6 percent on 2026-08-13 with a null
propensity. within_tier_fallback is atr_pct_20d, which needs only 20 sessions.
A name with neither sorts last and discover records the count.

It did not improve anything measurable, and it did not cost anything either:
with the fallback the sweep gives 0.1164, bit identical to plain propensity.
The reason is in the same table: only 0.2 subscribed names per session lack a
propensity, so the band the fallback reorders is almost always empty. Kept
under the clause that says keep it if it does not lose. Under the dollar volume
key that count was 1.3 per session, so the fallback would have mattered more to
the ordering it replaced than to the one it serves.

### Two new evaluate metrics

**screen_passed**, the count of subscribed names that would have cleared the
replayable part of the CRITERIA day screen, not merely gapped. Recall counts
names that moved; this counts names the morning could have published, which is
what the product is made of. The shipped configuration gives 6.57 per session
against 5.77 for dollar volume. Only gap_pct, price, market_cap and
require_above_prior_high are applied: premarket_rvol cannot be replayed for a
historical session because there is no premarket tape for names that were never
subscribed, so this is an upper bound on the real screen and SCREEN_SKIPPED in
the module says so.

**subscribed_without_primary**, the per session count of subscribed names the
ranking key cannot score, which is what says whether the fallback is doing
anything.

### Test isolation became structural

src/tests/conftest.py redirects every writable root, sourced from config so a test
cannot bypass it by building a path itself, and rebinds the six module level
constants that captured one at import time. src/tests/run_tests.py wraps the suite in
it and photographs the real runs/ and data/ before and after, failing on any
difference. Deliberately not a pytest conftest: pytest is not a dependency and
requirements.txt is three lines on purpose.

The full suite now runs with 203 files under the real roots before and 203
unchanged after. `run_tests.py --prove-check` appends a test that writes
straight to the real runs/ and the run fails naming the file, so the check is
demonstrated rather than assumed.

The audit that came with it found the lock problem was not one function. Three
sites held a transaction across a network call: gap_stats.build, fixed earlier;
baseline.warm, which held one across an intraday call per ticker for up to
fifty tickers at 07:15; and fill_outcomes, which held one across an end of day
call per pick. All three are now read, then fetch, then write. baseline.ensure
was a fourth, latent: nothing calls it any more, and it opened a session and
recursed so that compute() ran inside the transaction. Cleared as network free:
backfill_premarket at both sites, baseline.get, baseline `--show`,
discover.recent_runners, gap_stats.load_all, scan.attach_premarket_rvol,
scan.write_picks and store.init.

### The null-propensity question is closed

The ATR fallback tying told us about the subscribed set, where only 0.2 names a
session lack a propensity. That is not the same question as how much of the
target population propensity structurally cannot see, so the target population
was measured directly: `backtest_pool.py blindspot`, cache only, no fetch.

Across the 60 cached sessions, 10,424 universe names gapped beyond the floor.
355 of them carried a null propensity, a fraction of **0.0341**, ranked with the
2026-05-18 window the sweep used. Against the 2026-08-13 window, by which the
same names have another sixty sessions of history, it falls to 230 and
**0.0221**. Those two bracket the real figure, because the shipped system
recomputes weekly and so sits between them.

Per session the null fraction runs from 0.005 to 0.143 with a median of 0.034,
which is 5.9 unreachable gappers out of 173.7. History of the null ones, in
sessions, on the earlier window: 169 had under 10, 34 had 10 to 24, 43 had 25
to 49, and 109 had 50 to 99. Those 109 are 31 percent of the 355, and they are
the ones within a couple of months of crossing the 100 session line on their
own; the 169 with under 10 sessions are a year away from it.
[corrected 2026-08-14: was "so half of them are within a fortnight or two";
109 of 355 is 31 percent, and at 50 to 99 sessions of history they are months
short of the line rather than a fortnight]

The fraction is small, so the question is closed on the first of the two
conclusions: the fallback stays as inert insurance, and no reserved allocation
for short-history names is proposed. The arithmetic that settles it is that
capturing every one of those 5.9 names would add at most 3.4 points of recall.
Set against the same sixty sessions, the shipped configuration reaches 0.1164
of the gappers, so 88 points are missed in total: about 50 of them because the
pool held the name and the cap cut it, and about 38 because the pool never held
it at all.
[corrected 2026-08-14: was "a cap that currently misses 88 percent of gappers
for want of slots"; 88 points is the whole miss, and only about 50 of it is the
cap. Attributing all 88 to slots overstates what buying capacity would buy]
The binding constraint is the cap, which is already the open item.

### The lock rule is enforced rather than audited

store.assert_no_open_transaction is called at the HTTP chokepoint before any
request goes out, and raises TransactionHeldError if any live connection has a
write transaction open. It reads sqlite3's own in_transaction through a
registry of connections store.connect handed out, so nothing depends on a
caller declaring its state. That matters because three of the four sites found
by audit looked innocent and the fourth held its transaction behind a
recursion, where no lexical scan could reach it.

sqlite3.Connection cannot be weak referenced, so connect() returns a
_TrackedConnection subclass that can, and the registry holds those weakly so a
closed connection drops out on its own.

src/tests/test_txn_guard.py asserts three things: a request under a deliberately
opened transaction raises and names the endpoint; a connection that has only
read is not a transaction and does not trip it, while the same connection does
the moment a write begins one; and the whole morning chain runs clean, having
made 42 guarded requests and tripped none.

The nine sites cleared by the earlier audit are now enforced rather than
inspected, and so is every path nobody has read yet, including ones not yet
written.

### Packet schema

New keys: `build`, `vintage`, `dropped_no_coverage`. New candidate fields:
`price_time`, `price_source`, `pm_volume`, `prior_close`, `prior_source`,
`gap_reason`, `pm_rvol_basis`, and the `selection_*` group replacing the
candidate `price`, `prior_close` and `gap_pct` that the bulk feed used to
write directly. New market snapshot fields: `as_of` on every row,
`prior_session_only`, `prior_session_date`.

There is no SCHEMA.md in this repository to record that in. Noted here instead.
