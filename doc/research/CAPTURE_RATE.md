# What share of the tape does the collector actually see

## The finding

The socket carries a fraction of the consolidated tape, and `premarket_capture_rate`
is the single divisor that scales what it saw back up to what printed. This study
measures that share against Alpaca's full tape, session by session and name by name.

Over the **46 rows across 6 sessions that survive every guard**, the median observed
capture is **0.0999**. Against all 68 paired rows across 8 sessions, with the guards
NOT applied, it is **0.0866**. The distance between those two numbers is the point of
the study: the second is what a reader takes off the table without the guards.

The shipped `[Collector] premarket_capture_rate` is **0.1172**.

**The residual the divisor cannot reach.** Median `collector_window_share` over the
same guarded set is **0.4074**. That is the share of the tape inside the collector's
own window to the 08:45 cutoff, and it is a scheduling number rather than a feed number.
Every session in this study predates 2026-09-03, so that window opened at 07:20 for
all of them; since then it is per session and per name, read from the subscription
sidecar, and 04:00 for a name on the 03:55 pool.
A divisor corrects what the feed misses while listening; it cannot correct what was
never listened to. See DECISIONS.md for which half each proposed remedy reaches.

**One guard could not be applied at all.** `min_capture_minutes` needs the count of
minutes the socket and the tape both covered, and nothing persists it: picks carries
`true_bars`, which is Alpaca minutes inside the window, and no column counts the
intersection. The study says so rather than reporting the guard as passed.

## Provenance

| | |
|---|---|
| Question | what share of the consolidated tape does the socket capture, and does one divisor fit it |
| Instrument | `research/measure_capture_rate.py`, re-asked by `research/sweep_capture_rate.py` |
| Measured | 2026-09-01, 0 vendor calls (offline against stored rows) |
| Commit | `adb6e92`, "Re-derive the capture rate offline, and move nothing while the window is in play" |
| Payload | `data/research/capture_rate_study-2026-09-01.json` |

Regenerable: yes, offline and for no quota. The payload left doc/ on 2026-09-01
because it is 3,180 lines of per row output and reading diffs is the only review
this project has.

## What contradicted an assumption

`night/true_volume.py` and CRITERIA both asserted that thin names capture least.
Over the 46 guarded rows, terciles of `avg_volume_20d` give median capture shares of
**0.178 thin, 0.087 mid, 0.084 thick**, Spearman rho **-0.405**. Thin names capture
MORE, by more than double. The spread is real and a single divisor still cannot
correct it; what was wrong was the sign. Six sessions is below `[Truth]
baseline_sessions`, so this is a contradicted assumption rather than a finding to
act on. Both documents were corrected on 2026-08-31.
