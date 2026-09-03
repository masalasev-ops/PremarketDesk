# The counterfactual watchlist

What each morning's day watchlist would have been if the day screen's volume
floor had been applied to the MEASURED premarket RVOL instead of to the
published estimate.

Instrument: `src/research/counterfactual_watchlist.py`. Payload:
`data/research/counterfactual_watchlist-2026-09-01.json`, which carries the raw
rows and not only the tables below, so every number here is arithmetic on a
file. Zero vendor calls. It writes to no table and reads picks only.

Run: `PYTHONPATH=src .venv\Scripts\python.exe -m research.counterfactual_watchlist`

## Why this exists now

`data/UNVERIFIED` has been gated on collector volume since 2026-08-18. The gate
was waiting on a measurement, and the measurement arrived: `night/true_volume.py`
has written `pm_rvol_true` into all 68 live picks rows from Alpaca's full SIP
tape. So the gate is now blocked on a DECISION rather than on a measurement, and
the decision needs to know what the decision would have bought.

## Read these three things before the headline number

Leading with "eleven names would have been admitted" would argue for the wrong
fix. Each of the three below changes what that sentence means.

### 1. The substitution swaps a WINDOW, not only a tape

Published `pm_rvol` divides a numerator that starts at [Collector] `start_time`,
07:20, by a baseline that accumulates from [Baseline] `session_start`, 04:00.
`pm_rvol_true` divides 04:00 to cutoff by 04:00 to cutoff. So part of the gap
between the two is not the socket missing volume. It is the published ratio
being bounded below by construction.

The three factors, over the 56 replayable rows. **Each carries its OWN row
count**, because they need different inputs and a row missing one still has the
others:

| factor | what it is | rows | sessions | median | min | max |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| window | 1 / `collector_window_share`, the numerator widened from 07:20 to 04:00 on ONE tape | 44 | 6 | 2.5252 | 1.0000 | 7.2743 |
| feed and estimate | true SIP volume over the socket's own minutes, divided by the numerator the morning published | 44 | 6 | 1.3869 | 0.3323 | 7.4307 |
| baseline | the published denominator over the true one, two vendors on the same clock window | 37 | 6 | 1.0146 | 0.7831 | 1.6027 |
| total | `pm_rvol_true / pm_rvol` | 47 | 7 | 5.0076 | 0.6627 | 71.4851 |

The ten rows that carry a total but no window or feed factor are the
pre-correction session, and section 2 is about exactly them. **The pooled total
of 5.0076 in the last line is the number section 2 says not to use**, and it is
printed here only so the three factors can be read against something.

Median `collector_window_share` is 0.3664 over all 68 picks rows and 0.4009 over
the 56 replayable ones, the difference being the refused session. So the late
start alone is a factor of about 2.7 of a total median near 5.

**Medians do not multiply.** 2.5252 times 1.3869 times 1.0146 is 3.55, not
5.0076, because each column is the median of its own ratio over its own rows.
The identity holds per ROW, not per column, and that is where it was checked.

**The window half is arithmetic and the feed half is empirical, and they have
different fixes.** No collector change reaches the window: moving `start_time`
earlier is a purchasing decision that `job_probe_socket_cost` was armed on
2026-08-31 to price. The window factor's minimum is exactly 1.0000, on WSM.US of
2026-08-26, whose 25,252 premarket shares all arrived after 07:20. That is the
lower bound made visible on a real row.

**The baseline denominator is not the story.** A median of 1.0146 says the EODHD
intraday baseline and the Alpaca SIP baseline agree at the middle of this
population. If the gap were a denominator artefact this column would carry it,
and it does not.

**The substitution is not one directional.** The total ratio's minimum is 0.6627:
CHA on 2026-08-28 published 316.14 and measured 209.50. Three rows measure lower
than they published. None of them crosses the floor downward, so nothing is lost,
but "the true number is always bigger" is false and a rule written on it would be.

The identity `window x feed x baseline` reproduces the total ratio on 37 of 37
rows where all four terms exist, with a worst relative residual of 2.53e-06,
which is the rounding of the stored columns and nothing else.

### 2. Rows published under a superseded arithmetic

The capture correction shipped on the evening of 2026-08-21. Rows before it
carry a RAW socket numerator with `pm_volume_estimated` null; rows after it
carry the corrected estimate. Splitting on that column:

| slice | rows | sessions | median total ratio | rows behind that median |
| --- | ---: | ---: | ---: | ---: |
| before the correction | 12 | 1 | 35.9094 | 10 |
| after the correction | 44 | 6 | 4.5884 | 37 |

**Close to an eight fold difference in the size of the correction**, 35.9094
against 4.5884. The pre-correction median is a ratio against a numerator that no
screen has divided by since 2026-08-21. Pooling the two produces 5.0076 over 47
rows and describes a screen that does not exist.

**And this is where the headline lives.** 7 of the 11 gained names come from
2026-08-20, which is the ONLY pre-correction session that survives the run time
guard. So the majority of the gain is measured against arithmetic retired on
2026-08-21, and the four names that are about today's screen sit on three
sessions.

The feed half cannot be computed for the pre-correction slice: those rows carry
neither `pm_volume_estimated` nor `pm_volume`, so the numerator the morning
divided cannot be read back. That is recorded as null with the reason on every
one of the twelve rows, not as a zero. The window half CAN be, because it needs
only `collector_window_share`, and since 2026-09-02 it is computed before the
numerator lookup and published for that slice too [corrected 2026-09-02: this
said both halves were uncomputable, which was the code returning early rather
than a property of the rows]. Every record now also carries
`collector_window_open`, the clock that session's collector actually opened at,
and the report slices on it beside the capture correction split.

### 3. The sample is SESSIONS, not rows

Twelve names from one morning share a tape and are one observation. CRITERIA
[Score watch] `min_group_rows` is 10 and `min_group_sessions` is 3, and both are
applied to every outcome median here, per metric, with the shortfall stated.

The gained set is 11 rows over 4 sessions. It clears both minima ONLY when
pooled. Every split of it falls short of one or the other:

| group | rows | sessions | verdict |
| --- | ---: | ---: | --- |
| all gained | 11 | 4 | published, except `day5_close` |
| fill plausible | 9 | 4 | withheld, 1 row short |
| fill implausible | 2 | 1 | withheld, 8 rows and 2 sessions short |
| before the correction | 7 | 1 | withheld, 3 rows and 2 sessions short |
| after the correction | 4 | 3 | withheld, 6 rows short |

So the only outcome medians this study may publish are the pooled ones, and the
pooled group is 7 parts one session to 4 parts three others.

## The baseline pass, and the two rows it caught

Before any substitution, the shipped functions were replayed over each packet
UNCHANGED and compared against the packet's own stored verdict. 56 rows replayed,
2 disagreed:

| session | name | stored | replays | differing component |
| --- | --- | --- | --- | --- |
| 2026-08-24 | NSSC.US | 7.0 green | 6.0 yellow | `premarket_float_rotation` 1.0 to 0.0 |
| 2026-08-26 | WSM.US | 6.0 yellow | 5.0 yellow | `premarket_float_rotation` 1.0 to 0.0 |

Neither is the counterfactual. CRITERIA [Score premarket float rotation] moved
its one point edge from 0.00014 to 0.0002 on 2026-08-31 and no historical row was
rescored, so a row scored under the old edge replays lower today. That section
names these two rows itself. Without this pass the drift would read as the
counterfactual LOWERING a score, which is backwards.

Both are recorded as `criteria_drifted` and EXCLUDED from the gained and lost
counts. **NSSC.US would have gained day eligibility** on the substitution, so the
honest reading of the headline is "11, or 12 if you accept a row whose baseline
no longer replays". It is held out rather than folded in because a row that fails
the replay cannot have its change attributed to the substitution.

## What the substitution moves

68 picks rows over 8 sessions. Every row lands in exactly one state.

| state | rows | sessions |
| --- | ---: | ---: |
| gained day eligibility | 11 | 4 |
| lost day eligibility | 0 | 0 |
| held, eligible on both numbers | 4 | 4 |
| absent, eligible on neither | 39 | 7 |
| criteria drifted, not attributable | 2 | 2 |
| unresolvable | 12 | 1 |

**2026-08-21 is refused whole.** Its packet records no `run_time_et`, so it is
not the scheduled 08:45 and it describes a different market. That is
`night/true_volume.reread()`'s own guard, and it catches the stub without
special casing a date. All 12 of its rows are UNRESOLVABLE with the packet's
recorded run time in the reason: never a pass, never a fail. A session that could
not be replayed and a session that replayed to no change are different states.

**Swing eligibility cannot move and does not.** [Swing setup] carries no volume
condition at all. 0 swing moves, reported because unchanged is an answer.

**Scores move on rows that do not change side.** 14 rows score higher and 1 lower;
11 change conviction bucket, including BABA.US, WOLF.US and HMY.US, which gain a
green without ever becoming day eligible, and BWLP.US, which drops green to
yellow. The score is not the screen, and a reader watching only the watchlist
would miss all of that.

## The eleven gained names, whole

Eleven rows is a sample a reader can hold, so here it is rather than only its
medians.

| session | name | pm_rvol | pm_rvol_true | score | fill | mfe_true | mae_true | broke pm high |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| 2026-08-20 | ASST.US | 0.8732 | 14.2983 | 2 to 4 | plausible | +17.04 | +15.22 | yes |
| 2026-08-20 | BLSH.US | 0.1917 | 9.2868 | 6 to 8 | implausible | +6.16 | +6.00 | yes |
| 2026-08-20 | COIN.US | 0.2901 | 10.4290 | 6 to 8 | plausible | +9.35 | +8.88 | yes |
| 2026-08-20 | FUTU.US | 1.0282 | 47.3703 | 8 to 10 | plausible | +1.75 | +5.04 | yes |
| 2026-08-20 | MARA.US | 0.3376 | 12.5566 | 6 to 8 | plausible | +20.09 | +12.56 | yes |
| 2026-08-20 | MSTR.US | 0.4942 | 13.0151 | 7 to 9 | plausible | +3.31 | +7.77 | yes |
| 2026-08-20 | SCSC.US | null | 17.1224 | 7 to 9 | implausible | -6.32 | +1.25 | no |
| 2026-08-25 | BE.US | 0.4786 | 2.5879 | 3 to 4 | plausible | +3.43 | +4.06 | yes |
| 2026-08-25 | NVTS.US | 0.2534 | 2.6726 | 6 to 7 | plausible | -1.59 | -0.20 | yes |
| 2026-08-26 | ANF.US | null | 478.1800 | 10 to 10 | plausible | +22.64 | +34.20 | yes |
| 2026-08-27 | DG.US | null | 664.1426 | 8 to 8 | plausible | -10.21 | +1.46 | no |

Three of the eleven, SCSC.US, ANF.US and DG.US, had a null `pm_rvol` rather than
a low one: they failed the screen on an UNMEASURED condition, not a measured one.
All three were scored through the float rotation fallback instead, so all three
carry a score while failing the screen on the same quantity the score used a
substitute for.

## Outcomes, per column, with each column's own filled count

They are not all filled and a missing `day5_close` is not a zero five day move.

Sign convention, from [Outcomes]: `mfe_pct_true` is positive when the next
session's high ran PAST `entry_ref_true`, and `mae_pct_true` is NEGATIVE when the
next session's low undercut `stop_ref_true`. A positive adverse excursion means
the stop reference was never breached.

All eleven gained names, 4 sessions:

| column | filled | sessions | median | note |
| --- | ---: | ---: | ---: | --- |
| next_day_open | 11 | 4 | 115.18 | dollar level, a cross name median has no referent |
| next_day_high | 11 | 4 | 121.90 | dollar level |
| next_day_low | 11 | 4 | 114.9225 | dollar level |
| next_day_close | 11 | 4 | 119.25 | dollar level |
| pm_high_broke_next_day | 11 | 4 | 1 | the premarket high broke on 9 of 11 |
| mfe_pct_true | 11 | 4 | +3.4304 | the next high reached the true entry level on 8 of 11 |
| mae_pct_true | 11 | 4 | +6.0000 | the next low undercut the true stop level on 1 of 11 |
| day5_close | 7 | 1 | WITHHELD | 3 rows and 2 sessions short |

**The four level columns are dollar prices.** A median across names of a level is
arithmetic without a referent: a 40 dollar name and a 1,500 dollar name weigh the
same in it and neither number says what happened. They are carried per row in the
payload and printed here only because every attached column was asked for one.

**`day5_close` is filled for 7 of 11 and all 7 are one session.** The four
post-correction gains are too recent to have a fifth session. That is a
not-yet-measured state, and the payload records the unfilled ticker against the
refusal reason where one exists.

**Every split is withheld.** Splitting on `fill_plausible` gives 9 plausible and
2 implausible, and neither clears `min_group_rows`. So the study cannot say
whether the excursions above survive the removal of names whose reference level
nobody could have transacted at, and the two implausible rows are exactly the two
whose behaviour is most in question. SCSC.US is the clearest: its entire
premarket that morning was 11 minutes and 5,873 shares, and the band around its
entry reference held 714 shares in ONE minute, 42,840 dollars against the 250,000
dollar floor in [Truth] `min_fill_band_notional`. Its `mfe_pct_true` of -6.32 is
one of the three negative excursions in the gained set, and it is measured from a
level that was a print rather than a market. BLSH.US is the other.

## What this does NOT do

It does not lift `data/UNVERIFIED`, propose a threshold, or add a section to
`site/Weekly.html`. `night/weekly_page.py`'s charter is no new data, no new
table and no measurement of its own, and a counterfactual re-runs the screen,
which is a measurement.

## The verdict, as three questions

Lifting `data/UNVERIFIED` is a threshold decision, and this project has already
settled that correcting a live screen belongs to the owner and not to the code.
So this ends in questions rather than a recommendation.

**1. Is a correction whose median is 4.59 on today's arithmetic and 35.91 on the
retired arithmetic one question or two?** The eleven gained names are 7 from the
retired regime and 4 from the current one. If the screen is judged on what it
would do tomorrow, the evidence is 4 names over 3 sessions, which is below both
of this project's own minimums for saying anything about them.

**2. Which half of the gap is the screen meant to be measuring?** About 2.7 of
the median 5 is the collector starting at 07:20 against a baseline accumulating
from 04:00. That half is bounded below by construction and no volume measurement
contradicts it. Substituting `pm_rvol_true` fixes it by widening the window,
which is a different change from fixing the feed, and it is the change
`job_probe_socket_cost` was armed on 2026-08-31 to price. Is the floor of 1.5
meant to be applied to a 07:20 ratio or an 04:00 one? That question has never
been asked out loud and both answers are defensible.

**3. Is 11 names over 4 sessions, 7 of them from one morning, enough to move a
live screen?** The outcomes lean favourable: the premarket high broke on 9 of 11
and the true stop level was undercut on 1 of 11. But every split of that number
is withheld under [Score watch], the sample is 4 sessions, and
`doc/research/SCORE_INVERSION.md` already records this project finding a
favourable-looking ordering that reversed at fifty rows.

The instrument is idempotent and needs no vendor call, so re-running it after
another two weeks of `pm_rvol_true` costs nothing and would answer question 3
with post-correction rows only. That is the cheapest way to a defensible answer,
and it is the recommendation this file will not make.
