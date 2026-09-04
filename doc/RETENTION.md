# RETENTION

Written 2026-09-04, after the owner asked why runs/ grows every day and
whether it could go into the database. The windows below are the owner's:
hot 30 sessions, and a cleanup of data older than three months.

Nothing in this file is built. It deletes nothing today: the oldest thing on
disk is dated 2026-08-13 and is 22 days old, so a three month rule first bites
on 2026-11-11. That is deliberate. A retention policy is cheapest to argue
about while it has nothing to destroy.

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

The raw tape goes and the packet stays. Per session that leaves the compressed
packet at about 32 KB, the compressed reports at about 33 KB, and the summary
row in the database, which is about 70 KB a session forever, or roughly 18 MB
a year against the 740 MB a year the tree grows now.

THE PACKET IS NEVER DELETED. Dropping it for cold sessions was proposed in
conversation on 2026-09-04, on the argument that the summary row and the
report would carry a cold day. It was withdrawn the same day and never reached
doc/SCREENS.md. The owner's next question was how to open a random past day's
SCREEN, and the packet is what a screen is drawn from: 32 KB compressed is not
worth that capability.

### Never, at any age

  data/premarket/*.jsonl   see the decision below, which is the owner's
  report.md, report.html   what a human actually saw. build_archive rebuilds
                           site/ FROM these, so pruning them shortens the
                           archive silently, which is prune_data's own
                           stated reason for leaving runs/ alone
  packet.json              compressed forever, 32 KB a session
  picks, paper_trades      database rows, not files, already small

## How a random day's screen still opens

This is the question that shaped the tiers, so it gets its own answer.

The desk inlines its data at build time, because Chrome blocks fetch on
file:// and build_archive found that before this file existed. The question is
whether every session can be inlined, and the measurement says yes with room
to spare.

  a compacted session          63,913 bytes
  gzipped                      14,856
  base64, as inlined           19,808

  30 sessions                  0.6 MB
  126 sessions, half a year    2.4 MB
  252 sessions, a year         4.8 MB
  504 sessions, two years      9.5 MB

So EVERY session the project has ever run fits in one site/Desk.html for
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

## The decision the owner has to make, and its cost

The owner said on 2026-09-04, of data older than three months, "I don't think
we need it at all for this project." Taken at face value that includes
data/premarket/*.jsonl, and this file assumes it does.

STATED ONCE, PLAINLY, BECAUSE IT IS IRREVERSIBLE. prune_data's whitelist calls
that file "NOT reproducible at any price: it is a recording of a tape that no
longer exists," and names it as the only record of the 2026-08-14 over count,
which is still unexplained. Deleting it at three months means:

  the capture rate can only ever be re measured over the last three months,
  and CRITERIA [Collector] premarket_capture_rate is a shipped constant of
  0.1172 that every RVOL and float rotation on every report divides by
  the truth pass cannot be re run over an older session
  the 2026-08-14 over count becomes permanently unexplainable

None of that blocks a report or a screen. All of it is research capability.
If the owner wants the disk back but not that loss, the middle option is to
gzip those files at three months instead of deleting them, at 13.1 percent,
which turns 310 MB a year into 41 MB a year and keeps every capability.

data/backtest/ IS A SEPARATE DECISION AND IS NOT COVERED BY THE THREE MONTH
RULE as written here. It is 27 MB, it does not grow daily, and it is dated by
study rather than by session: eod/ at 13 MB is the 61 session population the
shipped float rotation edges were fitted on, and a re fit reads it;
sessions/ at 14 MB is the replay behind the subscription cap recall table,
which is an open purchasing decision. Deleting either ends the study it
belongs to. Ask before including it.

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
  5. Cold at three months, behind --dry-run, after the owner confirms the cost
     above. Not before 2026-11-11, when the first session becomes eligible.

Steps 1, 3 and 4 destroy nothing. Step 2 is a code change with no data loss.
Step 5 is the only one that deletes, and it deletes nothing until November.

## The knobs this will add to CRITERIA.md

Listed here rather than added there, because criteria.py is a strict reader
and a key with no reader is clutter. They move to a `## Retention` section
with the code.

  hot_sessions            = 30      sessions kept uncompressed under runs/
  cold_after_days         = 90      days after which the raw tape is a
                                    candidate, subject to the decision above
  snapshot_drop_requires_verify     the duplicate tape goes only once
                                    verify_intraday has agreed for that session

MIND THE SHADOW TRAP WHEN THEY MOVE. A note in CRITERIA.md beginning in column
zero with `key = value` is parsed as a second parameter and the last one wins,
which disabled slots mode for a day. Never open a sentence in that file with
the name of a key.

## Open questions

  Whether data/premarket/*.jsonl is deleted or gzipped at three months. The
  owner's words say deleted; the cost is stated above; this file assumes
  deleted and the assumption is cheap to reverse before November.

  Whether data/backtest/ is in scope. Not included here. 27 MB, static, and
  each half ends a study if it goes.

  logs/ at 2.4 MB has no policy either. It is small, it is not evidence, and
  it is the obvious next whitelist entry once these five steps are done.
