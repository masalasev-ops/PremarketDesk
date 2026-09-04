# RETENTION

Written 2026-09-04, after the owner asked why runs/ grows every day and
whether it could go into the database. Every window and every decision below
is the owner's, taken the same day: hot 30 sessions, a cleanup of data older
than three months, the raw tape GZIPPED at that age rather than deleted, and
data/backtest/ deleted outright on the ground that it is refetchable.

[BUILT 2026-09-04, steps 1, 3, 4 and the mechanism of 5. What runs tonight is
night/prune_data.sweep_runs, wired into the nightly after desk.compact and
before the desk rebuild. It freed 4.46 MB the first time it ran, taking runs/ from
11 MB to 5.6 MB, by dropping ten proven duplicate snapshots. Step 2, having
scan stop writing the duplicate at all, is NOT built and is the one item left.
See CHANGELOG 2026-09-04 sixtieth.]

It deletes nothing on an age. The oldest thing on disk is dated 2026-08-13 and
is 22 days old, so the three month rule first bites on 2026-11-11, and when it
does it compresses rather than deletes. The one thing removed at any age is the
duplicate snapshot, under three interlocks, and only after the run's own copy
has been read and proven contained in the collector's.

## What was measured, 2026-09-04

  runs/                9.9 MB over 14 sessions, about 1.7 MB a session lately
  data/                47 MB, of which backtest/ is 27 MB and premarket/ 12 MB
  logs/                2.4 MB
  premarketdesk.db     2.6 MB, five tables, 17,556 rows

The daily growth is runs/ at about 1.7 MB plus data/premarket/ at about
1.24 MB, so roughly 3 MB a session and about 740 MB a year, with no retention
on either. data/backtest/ is 27 MB of one off research inputs and does not
grow daily.

Compression, measured on runs/2026-09-03:

  packet.json               254,252 -> 31,886   12.5%
  premarket_snapshot.jsonl  1,014,951 -> 132,730  13.1%
  report.html               72,405 -> 18,105   25.0%
  report.md                 55,152 -> 15,025   27.2%
  midday_packet.json        55,076 -> 10,077   18.3%
  pool_recall.json          38,126 -> 4,218    11.1%

## The finding that does most of the work

runs/<date>/premarket_snapshot.jsonl IS A STRICT SUBSET OF
data/premarket/<date>.jsonl. Not similar to it, a subset: every line of the
run copy appears in the collector file, and the run copy has no line of its
own. Tested over all eleven sessions that carry both.

  2026-08-21  run   258 lines  collector   258  subset  0 unique
  2026-08-24  run   993         collector 2,089  subset  0 unique
  2026-09-03  run 4,065         collector 4,973  subset  0 unique
  2026-09-04  run 5,404         collector 5,867  subset  0 unique
  total 6,024,048 bytes, 100 percent duplicated

That is 61 percent of everything under runs/, and it is a second copy of the
one file prune_data protects forever on the ground that it is not reproducible
at any price. The copy is the derivable one.

## The four tiers

### Hot, the newest 30 sessions

Everything exactly as it is written today. Uncompressed, in runs/<date>/, open
in a text editor, greppable, diffable. Thirty sessions is about six trading
weeks, which is longer than any question this project has had to answer by
hand.

### Warm, older than 30 sessions

The same files, gzipped in place: packet.json.gz, report.md.gz,
report.html.gz, midday_packet.json.gz, pool_recall.json.gz. About 1.6 MB a
session becomes about 210 KB. Nothing is lost and nothing moves, so a warm
session is one gunzip away from being hot again.

Readers open through one helper in core/files.py, which already owns the
atomic write and is the right place for the paired read.

### Cold, older than three months

The raw tape is gzipped, not deleted. The owner was offered both on 2026-09-04
and chose compression, so every capability the tape carries survives at 13.1
percent of the bytes.

Per session that leaves the compressed tape at about 162 KB, the compressed
packet at about 32 KB, the compressed reports at about 33 KB, the compressed
midday packet and recall at about 14 KB, and the summary row in the database:
roughly 241 KB a session forever, or about 61 MB a year against the 740 MB a
year the tree grows now. A 92 percent reduction with nothing lost.

THE PACKET IS NEVER DELETED. Dropping it for cold sessions was proposed in
conversation on 2026-09-04, on the argument that the summary row and the
report would carry a cold day. It was withdrawn the same day and never reached
doc/SCREENS.md. The owner's next question was how to open a random past day's
SCREEN, and the packet is what a screen is drawn from: 32 KB compressed is not
worth that capability.

### Never, at any age

  data/premarket/*.jsonl   gzipped at three months, never deleted. 310 MB a
                           year becomes 41 MB and the capture rate stays re
                           measurable over every session ever recorded
  report.md, report.html   what a human actually saw. desk/compact inlines
                           the desk's Report screen FROM these, so pruning
                           them empties that screen silently, which is
                           prune_data's own stated reason for leaving runs/
                           alone. They are gzipped past hot_sessions and
                           never deleted at any age
  packet.json              compressed forever, 32 KB a session
  picks, paper_trades      database rows, not files, already small

## How a random day's screen still opens

This is the question that shaped the tiers, so it gets its own answer.

The desk inlines its data at build time, because Chrome blocks fetch on
file:// and build_archive found that before this file existed, in the page
whose filename the desk took later the same day. The question is
whether every session can be inlined, and the measurement says yes with room
to spare.

  a compacted session          63,913 bytes
  gzipped                      14,856
  base64, as inlined           19,808

  30 sessions                  0.6 MB
  126 sessions, half a year    2.4 MB
  252 sessions, a year         4.8 MB
  504 sessions, two years      9.5 MB

So EVERY session the project has ever run fits in one site/PremarketDesk.html
for
years, and `#/session/2026-08-21/morning` resolves without a server, without
a fetch and without a second file. The page inflates the payload with
DecompressionStream, which is native in Chrome and Edge and needs no library.

Three ways in, and they are all the same data:

  the Sessions screen at #/sessions, one row a session with its gap spine at
  row scale, which is the browsing answer
  a date in the header, which is the jumping answer
  the route pasted from someone else, which is the sharing answer

The `inline_sessions` knob in SCREENS.md survives as a ceiling rather than a
window: raise it and the file grows by 20 KB a session, which is the honest
cost of never having to think about this again.

WHAT A COLD SESSION LOSES ON SCREEN: nothing on Morning, Sessions, Record or
Name. The per candidate minute bars the tape path draws are inside the packet
already, which is what the prototype read them from. What goes is the ability
to re derive those bars from the raw tape if a bug is ever found in how scan
clipped them, and to re measure the capture rate over that session.

## The decisions, taken 2026-09-04

THE RAW TAPE IS GZIPPED, NOT DELETED. The owner was shown the cost of deleting
data/premarket/*.jsonl, which prune_data calls the only record of the
2026-08-14 over count, and chose compression: 310 MB a year becomes 41 MB and
the capture rate stays re measurable over every session ever recorded. The
shipped constant that measurement backs is CRITERIA [Collector]
premarket_capture_rate at 0.1172, which every RVOL and float rotation on every
report divides by.

DATA/BACKTEST/ IS DELETED. The owner's instruction was "if it's not necessary
and can be refetched, then delete backtest. I don't want unnecessary baggage."
Both halves of that condition were tested before anything was removed and both
hold. What follows is the provenance, written down BEFORE the bytes went,
because deleting 27 MB must not also delete the knowledge of what it was.

### What data/backtest/ was

  eod/        62 daily bulk end of day files, 2026-05-15 to 2026-08-13, 13 MB.
              The population the float rotation scoring edges were fitted on,
              read by float_rotation_study, float_cache, addressable_sweep and
              vwap_gappers.
  sessions/   60 session directories, 2026-05-19 to 2026-08-13, 14 MB, each an
              inputs.json of the reconstructed earnings calendar, overnight
              news sweep, movers and prior closes, and an outcome.json of the
              open against the prior close for every universe name. The replay
              behind backtest_pool's tier ordering and the subscription cap
              recall table.
  premarket/  10 files, 164 KB, replay_session output.

It was pre history: none of it is a session this project ran. It was fetched
on 2026-08-14 so that day one had something to calibrate against, and it had
not changed since 2026-08-13, which was 22 days before it was deleted. It
never grew. It was never part of the daily growth this file exists to stop.

### Why deleting it was safe

NOTHING SCHEDULED READS IT. No .bat in tasks/ runs a research module. The
morning chain, the midday pass and the nightly never open it. Deleting it
cannot affect a report, a screen or a number a reader sees.

THE FINDINGS SURVIVE, ONLY THE INPUT WENT. The fitted edges are in CRITERIA
[Score premarket float rotation] with their derivation and the record of
getting them wrong once and correcting them on 2026-08-16. The study outputs
are still on disk: data/float_rotation_study.json, data/addressable_sweep.json,
data/float_cache.json and data/cutoff-0830.json. What was lost is the ability
to RE fit, not the fit.

IT IS REFETCHABLE BY ONE COMMAND, whose defaults are already the exact window
that was deleted:

    PYTHONPATH=src .venv/Scripts/python.exe -m research.backtest_pool fetch         --sessions 60 --end 2026-08-13

That costs about 6,200 counted calls, which is 62 bulk end of day days at the
metered 100 each, because consecutive sessions share their end of day reads
and sixty sessions need sixty two days rather than a hundred and eighty. The
shared key allows 100,000 a day and the pipeline spends about 900 on bulk
plus about 2,900 on the midday sweep, so a rebuild is about six percent of one
day's quota. backtest_pool's docstring calls the fetch "expensive and can only
be afforded once", and that sentence is about not refetching inside an
evaluation loop, which is why the module is split into fetch and evaluate at
all. It is not a claim that the fetch can never be run again.

### The one thing deleting it did cost, and it is not free

tests/test_backtest.py claim 4 reads the real cache and pins evaluate_session
over 2026-08-13 against PUBLISHED_0813. With the cache gone it does not fail,
it SKIPS, printing "claim 4 SKIPPED, 2026-08-13 is not in the cache", and the
suite still reports ok.

THAT IS THE PROJECT'S OWN WORST FAILURE MODE. The 2026-08-22 review's
conclusion was that two thirds of what it found was a missing answer read as a
measured one, and a green suite carrying a silently skipped claim is exactly
that shape. The claim is not deleted and not weakened; it is simply not
testing anything until someone refetches. Anyone reading a green suite as
evidence that the pool ordering still evaluates as published is reading it
wrong. Refetch before trusting that claim, or before changing anything
backtest_pool touches.

## The discipline this follows

prune_data.py already has the right shape and this work extends it rather than
writing a second sweeper beside it.

  A WHITELIST, NOT AN AGE RULE. One entry per file class that may ever be
  deleted, each bringing its own retention key and its own argument for why
  nothing can read it after that window. A sweeper that deletes whatever looks
  stale is one careless pattern away from deleting the only copy of something.

  THE AGE COMES FROM THE FILENAME, NOT THE MTIME. A file describes the session
  its name carries whoever copied it and whenever. An mtime rule spares a file
  a backup touched and deletes one it did not, which makes the window a
  property of the filesystem rather than of the data.

  Age is counted in SESSIONS for the hot window and in DAYS for the cold one,
  because thirty sessions is a working span and three months is a calendar
  promise. Both are read from CRITERIA.

  --dry-run says what would go and deletes nothing, which prune_data already
  supports and which every step below inherits.

## Order of work

  1. The duplicate tape. The nightly deletes runs/<date>/premarket_snapshot
     .jsonl once verify_intraday has run and agreed for that session. Nothing
     in the morning path reads a past session's snapshot, so this needs no
     reader change and is the whole of the 61 percent. Recovers 6 MB now.
  2. Stop writing it at all, by having scan clip the window off
     data/premarket/<date>.jsonl directly. This is more literally hard rule 6,
     which says premarket high, low and VWAP come from the collector file,
     than reading a copy of it is. Touches scan.py, artifacts.py and the two
     suites that read the snapshot by name.
  3. Warm compression at 30 sessions, and the gzip aware reader in core/files.
  4. The sessions table in the database, holding the compacted summary row.
     This is what Sessions, Record and Name query instead of opening a hundred
     packets, and it is the piece SCREENS.md needs anyway.
  5. Cold at three months, behind --dry-run. Gzip, not delete, so it destroys
     nothing either. Not before 2026-11-11, when the first session becomes
     eligible.

NO STEP IN THIS LIST DELETES ANYTHING. Step 1 removes a byte for byte
duplicate whose original is kept forever, steps 3 and 5 compress, step 4 adds
a table, and step 2 is a code change with no data loss. data/backtest/ was
deleted by hand on 2026-09-04 and is not part of the scheduled policy: nothing
in prune_data will ever touch it, because there is nothing left to touch.

## The knobs this will add to CRITERIA.md

Listed here rather than added there, because criteria.py is a strict reader
and a key with no reader is clutter. They move to a `## Retention` section
with the code.

  hot_sessions            = 30      sessions kept uncompressed under runs/
  cold_after_days         = 90      days after which the raw tape and the
                                    warm files are gzipped. Nothing at this
                                    age is deleted
  snapshot_drop_requires_verify     the duplicate tape goes only once
                                    verify_intraday has agreed for that session

MIND THE SHADOW TRAP WHEN THEY MOVE. A note in CRITERIA.md beginning in column
zero with `key = value` is parsed as a second parameter and the last one wins,
which disabled slots mode for a day. Never open a sentence in that file with
the name of a key.

## Open questions

  logs/ at 2.4 MB has no policy. It is small, it is not evidence, and it is
  the obvious next whitelist entry once these five steps are done.

  Whether the backtest cache is ever refetched, and when. It is not needed
  until someone re fits the float rotation edges or reopens the subscription
  cap question, and test_backtest claim 4 is silently skipping until then.
  The command and its cost are recorded above.

  ANSWERED 2026-09-04, for half of it: site/PremarketDesk.html WAS the
  archive, the owner retired that page the same afternoon and the desk took
  its filename, so the question is now only about site/Weekly.html. It is
  45 KB, rebuilt from runs/ and the database by the nightly, and it answers
  one question the desk's Record screen does not: what the week cost.
  Kept for now. SCREENS.md carries the same question from the other side.
