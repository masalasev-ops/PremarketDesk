# Moving to another machine, and starting the history over

Written 2026-09-04, against commit 825bcbe, for a move from the Windows build
machine to a MacBook. Two separate questions that are easy to confuse:

  1. How does the project run on a different computer.
  2. How does the RECORD start over, so nothing from August is counted or
     shown.

They are separate because the second one is worth doing on this machine too,
and the first one does not achieve it by itself the way it looks like it
does. A fresh clone has no history, but it also has no baseline, no gap
propensity table and no measured capture shares, and those are not the same
thing as a clean record.

---

## Part 1: what actually travels

### In git

`src/`, `doc/`, `tasks/`, `requirements.txt`, `.env.example`, `README.md`.
That is the whole system. 86 source files and 25 documents. A clone plus a
token plus a virtual environment is a working install.

### Not in git, by `.gitignore`

`.venv/`, `.env`, `data/`, `runs/`, `logs/`, `site/`.

Every path the project writes is derived from `PROJECT_ROOT` in
`src/core/config.py`, which is computed from the file's own location. There
is not one absolute path anywhere in the tracked tree. The project does not
care where it is unpacked.

### The one thing that cannot be fetched again

`data/premarket/<date>.jsonl`, the collector's own socket capture. 13 MB
over 49 files. `doc/CRITERIA.md` calls it *not reproducible at any price,
being a recording of a tape that no longer exists*, and `prune_data`'s
whitelist protects it forever.

EODHD will re-serve end of day bars and published intraday bars for any past
session. It will not re-serve what this project's socket heard, because that
is a recording and not a query. If August is left behind on the Windows
machine, that recording is what is left behind. Everything else on this list
can be rebuilt.

### What rebuilds, and what each costs

| Thing | How it comes back | Cost |
| --- | --- | --- |
| `data/universe.json` | Sunday 21:00 nightly, universe mode | one sweep |
| `gap_stats` (16,519 rows) | same job, one counted call per name | measured at 2,745 calls, 421 seconds |
| `baseline` (308 rows) | fills itself as sessions run | about 20 sessions before the volume floors have their own history |
| `exchange-details.json`, `float_cache.json` | on demand, cached | trivial |
| `picks`, `paper_trades`, `sessions` | only by living through mornings | one a day |

None of that is expensive against a 100,000 call daily quota. The cost is
calendar time, not credits.

### The subtle loss, worth naming before you decide

The per symbol capture shares. `night/true_volume.py` measures, per name,
what fraction of the consolidated tape this socket actually heard, and the
morning uses that name's own measured share when it has one. With no
history every name falls back to the standing `[Collector]
premarket_capture_rate`, which is 11.72 percent.

That default is exactly what put PATH, ASST and MSTR over the volume floor on
2026-09-04 when what the socket actually heard does not clear it. The Health
screen says so. On a machine with no measured shares, every name is in that
position and nothing distinguishes them. It resolves itself as the nightly
accumulates, but the first few weeks on a fresh machine are measurably
blinder than the last few here, and the Health screen will not be able to
tell you which names are affected because the answer is all of them.

---

## Part 2: the MacBook

### The install

    git clone https://github.com/masalasev-ops/PremarketDesk.git
    cd PremarketDesk
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    cp .env.example .env          # then fill in EODHD_API_TOKEN

Python 3.11 or newer; this was built on 3.14.7. Three dependencies.

The narrative pass shells out to the `claude` CLI and authenticates through
the logged in subscription, so install that and log in. Never set
`ANTHROPIC_API_KEY`: `config.py` refuses to read it and scrubs it, along with
five siblings, out of the CLI's environment before the call.

Verify before scheduling anything:

    PYTHONPATH=src .venv/bin/python -m tests.run_tests
    PYTHONPATH=src .venv/bin/python -m ops.market_today

The suite is hermetic and touches no vendor. The guard should print today's
verdict and exit 0 or 3.

### The delivery gate

`data/UNVERIFIED` blocks `deliver.py` from emailing anything while it exists,
and `verify_morning.ensure_marker` recreates it when it is missing. A fresh
clone has no `data/` at all, so the first chain run creates the gate before
delivery is reached and the first morning will not email. That is the
intended behaviour, not an accident. Watch one real morning's gate table,
then delete the file by hand. Nothing deletes it for you.

### Five things that are Windows shaped

**1. The schedule.** `tasks/*.bat` and `tasks/register_tasks.ps1` drive
Windows Task Scheduler. macOS wants launchd. Seven jobs, and the triggers are
the part to copy exactly, not the mechanism:

| Job | When (ET) |
| --- | --- |
| discover | 03:55 and 07:15 |
| collector | 04:00, runs to 09:25 |
| morning chain | 08:45 |
| midday | 12:00 |
| monitor | 07:25 every 30 min to 09:25; 12:25, 12:55, 13:25; 22:45 |
| nightly | 22:15; 07:00; Sun 21:00 |
| meter sampler | every 30 min, all day, weekends included |

The `.bat` files carry real logic and not just an invocation: the trading day
guard and its exit 3, the log redirection, the chain ordering, and in the
nightly the clock reading that tells the three triggers apart. Port the
logic, one shell script per job, and let launchd only supply the times.

`ops/market_today` must stay the first step of every job except the meter
sampler. That is what makes Labour Day cost nothing.

**2. The watchdog's scheduler half.** `ops/monitor_jobs.py` calls `schtasks
/Query` to ask Windows whether a task fired and what it returned. There is no
drop in equivalent; `launchctl list` reports a last exit status but not a
last run time in the same shape.

The watchdog has two halves and only one of them is Windows bound. The other
reads `data/job-status.jsonl`, which every step appends to as it exits, and
that half is portable and is the half that catches a job that ran and failed.
The `schtasks` half catches a job that never fired at all. Port it against
`launchctl print` or run the watchdog on the job trail alone and accept that
a task which never fires is detected by its missing trail line rather than by
the scheduler being asked.

**3. The backup root.** `doc/CRITERIA.md [Backup] root` is
`%LOCALAPPDATA%\PremarketDesk\evidence`, expanded through the environment.
`os.path.expandvars` does not expand `%VAR%` on macOS, so it stays a literal
and lands as a relative directory next to wherever the job was launched,
which is the one thing that path exists to avoid. One line to change:

    root = $HOME/Library/Application Support/PremarketDesk/evidence

**4. `.venv/Scripts/python.exe` becomes `.venv/bin/python`.** In the `.bat`
files that matters. In docstrings it is cosmetic.

**5. Time zones, and this one gets better.** Windows ships no IANA database
and `tzdata` is not one of the three dependencies, so `core/ettime.py` falls
back to a hand written fixed rule for US Eastern. macOS ships the database,
so `zoneinfo` wins automatically and `ettime.TZ_SOURCE` will read
`zoneinfo`. Nothing to do. Check that string once after install; it is the
one line that tells you which of the two is in force.

The Norton exclusions in `doc/BUILD_PLAN.md` stop mattering. The macOS
equivalent to watch for is the first outbound websocket connection prompting
for network permission, which on a headless 04:00 job means the collector
sits waiting on a dialog nobody is awake to answer. Run the collector by hand
once, interactively, and approve it before it is ever scheduled.

### The thing that will actually bite: a laptop sleeps

This is the real difference and it is not a porting problem, it is a hardware
one. The Windows machine was awake at 03:55 because it never slept. A closed
MacBook at 03:55 runs nothing at all.

launchd's `StartCalendarInterval` does not queue missed firings usefully: a
job whose time passed while asleep runs once at wake, which for a collector
whose entire purpose is to be listening between 04:00 and 09:25 is worthless.
It would connect at, say, 09:40 and record an empty window that looks like a
quiet tape rather than like a machine that was asleep.

Two things are needed and neither is optional:

    sudo pmset repeat wakeorpoweron MTWRF 03:45:00

to wake the machine ten minutes before the 03:55 discover, and `caffeinate -i`
wrapping the collector so nothing sleeps during the window it is listening.
On battery with the lid shut, macOS will sleep regardless; this only works
reliably on mains power, and with the lid open unless an external display is
attached.

Worth deciding before the move: a laptop that travels is a poor host for a job
that must be listening at 04:00 five days a week. The collector is the one
step that cannot be caught up afterwards, for exactly the reason at the top of
this file.

---

## Part 3: starting the record over

### The premise, checked against the changelog

The reason given for a floor was that too much has changed since August for
those sessions to mean anything. That is right, and it is right about more
than August.

The two phase collector was built on 2026-09-02 and its first morning was
**2026-09-03**. Before that the socket took one pool and ran a different
window. Premarket volume, and therefore every RVOL and every float rotation,
is measured over a different span on 2026-09-01 and 2026-09-02 than on
2026-09-03 and 2026-09-04. The midday volume floor that compared 150 traded
minutes against 390 was fixed on 2026-09-02.

So a floor at 2026-09-01 drops August and keeps two sessions that are not
comparable to the two after them either. If the reason for the floor is
comparability, the honest floor is **2026-09-03**, which today leaves two
sessions. A floor at 2026-09-01 leaves four and is a rounder number. Both are
defensible; they are not the same claim, and the one thing not to do is set
09-01 and then read the four as a series.

Also worth knowing before deciding how much is at stake: of the 531 rows in
`picks`, 420 are `source = reconstructed`, dated 2026-07-31 to 2026-08-13, and
every production query is already fenced by `source`, so those are not what
the screens are showing. What August contributes to the record is 8 live
sessions and 56 picks.

### Two ways, and they are not exclusive

**A. Floor the display and keep the tape.** A date below which the desk, the
weekly page and the paper ledger do not look. The recordings stay on disk, so
a later question about August can still be asked, and the answer to "why is
the record short" is a documented floor rather than a gap.

NOT BUILT. The shape it would take: one key in `[Retention]`, say
`history_from`, honoured in `desk/render.index_rows`, in the record and
sessions screens, in `night/weekly_page.py`, and in the paper ledger's
aggregation. A hide and not a delete, so the floor can move back.

**B. Empty slate.** Delete `data/`, `runs/`, `logs/`, `site/` and let the
schedule refill them. The MacBook gets this for free by being a fresh clone.
Costs are in Part 1: the gap propensity sweep re runs on the first Sunday,
the baseline takes about 20 sessions to have its own history, and no name has
a measured capture share until the nightly has built one.

On this machine, if B is what is wanted, take a copy first:

    PYTHONPATH=src .venv/Scripts/python.exe -m night.backup_evidence --list

and keep `data/premarket/` somewhere off the tree, because that is the half
that cannot be fetched again.

### What was actually done, 2026-09-04

The owner chose B with the floor at 2026-09-01, having been shown that the
collector changed on 2026-09-03. Both halves were done the same afternoon.

DELETED, on this machine: 11 run directories 2026-08-17 to 2026-08-31, 26
collector tape files, 91 logs, 5 dated data files, and from the database 488
picks, 136 paper trades and 8 session rows. 11.04 MB. The job trail lost 595
of 859 lines, the quantifier flag log 6 of 20, the watchdog's rerun record
its only entry. Four sessions remain: 2026-09-01 to 2026-09-04, 43 picks, 62
paper trades.

KEPT, deliberately, and each for its own reason. The probes and studies under
data/, because they are the measurements that justify the numbers now in
CRITERIA and several are cited there by name; deleting them would leave the
thresholds standing on evidence that no longer exists. The baseline and
gap_stats tables, because neither is a session record: baseline is a rolling
median over VENDOR bars keyed by ticker and cutoff, gap_stats is a propensity
over the discovery universe rebuilt every Sunday, and dropping either would
blind the volume floors and the pool ranking for weeks while saying nothing
about August. And the backup root outside the tree, which still holds all
fifteen sessions, so this cut is reversible by hand until someone empties it.

RECORDED: CRITERIA [Retention] history_from. Enforced in exactly one place,
desk/compact.known_sessions, which is the only point a restored run directory
could put a cut session back on the screens. The database needs no fence
because the delete is the fence there; an attempt to add one to weekly_page
was refused by the suite, and CRITERIA's history floor note explains why.

If the four are ever read as a series, remember that 09-01 and 09-02 ran the
old collector and 09-03 and 09-04 the two phase one.
