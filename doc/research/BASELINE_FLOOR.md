# What does the RVOL denominator floor let through

## The finding

Premarket RVOL divides by a 20 session median of premarket volume. `[Baseline]`
carries a floor under that median, because a denominator near zero makes any
numerator look enormous. This study measures what the floor admits.

**241 names measured**, of which **2 carry a median of zero**. The shipped floor is
**1,000 shares** and the thin line is **10,000**, measured at the 08:45 cutoff over a
20 session lookback from a 04:00 session start.

The table is the whole finding: as the baseline median rises, the share of that
band's rows landing above the top scoring band falls, monotonically.

| Median premarket volume | Names | Share above the top band |
|---|---|---|
| 0 to 1,000 | 46 | 0.30 |
| 1,000 to 2,000 | 13 | 0.20 |
| 2,000 to 5,000 | 30 | 0.20 |
| 5,000 to 10,000 | 19 | 0.15 |
| 10,000 to 25,000 | 25 | 0.15 |
| 25,000 to 100,000 | 37 | 0.10 |
| above 100,000 | 69 | 0.05 |

A name whose baseline median sits under 1,000 shares is **six times** as likely to
be paid the top band as one above 100,000. That is the floor's cost stated as a
ratio rather than as a threshold, and it is why the floor exists rather than being
raised to make the ratios look better: raising it withholds names instead of
scoring them wrong, which is a different trade and has to be argued separately.

## Provenance

| | |
|---|---|
| Question | what does the premarket volume baseline floor admit, and at what rate |
| Instrument | `research/measure_baseline_floor.py`, swept by `research/sweep_baseline_floor.py` |
| Measured | 2026-08-28 18:43 ET |
| Commit | `e0dfafd`, "Measure the RVOL denominator floor, and disclose the ratios it lets through" |
| Payload | `data/research/baseline_floor_study-2026-08-28.json` |

Regenerable: yes, from the stored baselines. The payload left doc/ on 2026-09-01
at 7,286 lines, of which 241 rows are the per name detail behind the seven row
table above.
