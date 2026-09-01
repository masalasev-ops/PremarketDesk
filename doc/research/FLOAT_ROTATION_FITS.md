# Where the float rotation bands came from

## The finding

A candidate with no premarket volume baseline cannot be scored on RVOL, so
`[Score premarket float rotation]` scores it on rotation instead. The two band sets
must pay alike, or which of them a name is scored under would change its score.

The newest fit, 2026-08-31, re-derived the edges on **189 rescued rows** out of a
12 candidate top by gap set, at the quantiles reproducing what the RVOL bands pay:

| | Rotation edge | RVOL target it reproduces |
|---|---|---|
| One point | 0.0002 | 0.1089 |
| Two points | 0.00033 | 0.5335 |

`claim_the_shipped_rotation_edges_match_the_newest_fit` reads THE NEWEST archived
payload rather than a named one, across both roots, so a later fit whose edges
disagree with what CRITERIA ships turns it red. Pinning one file would have passed
forever.

## Five runs, and why two of them stay committed

| Run | Payload | Regenerable |
|---|---|---|
| 2026-08-16 prefix | `doc/research/float_rotation_study-2026-08-16-prefix.json` | **No. The script is gone.** |
| 2026-08-17 postfix | `doc/research/float_rotation_study-2026-08-17-postfix.json` | **No. The input is gone.** |
| 2026-08-20 warmup fixed | `data/research/float_rotation_study-2026-08-20-warmup-fixed.json` | yes |
| 2026-08-21 eligibility | `data/research/float_rotation_study-2026-08-21-eligibility.json` | yes |
| 2026-08-31 floor sweep | `data/research/float_rotation_study-2026-08-31-floor-sweep.json` | yes |

The first two are the exception to the rule that study payloads live under data/,
and each carries a `_provenance` header saying so in its own words. The 2026-08-16
run cannot be regenerated because the script that produced it no longer exists: its
float screen carried a private copy of one CRITERIA floor written into the Python as
1.01 and missed the other two, replaced in `405c9ac`. The 2026-08-17 run cannot be
regenerated because its input is gone: it read `data/universe.json` as generated at
2026-08-17T00:50 holding 2,754 names, and the Sunday job overwrites that file
weekly. That the second was also unrepeatable was not obvious, and is why both
sides of the comparison are kept rather than only the first.

DECISIONS.md, 2026-08-17 sixth, cites both as columns of one table. A record that
cites a measurement nobody can open is an assertion, not evidence.

## Provenance

| | |
|---|---|
| Question | do the rotation bands pay what the RVOL bands pay, on the population that needs them |
| Instrument | `research/float_rotation_study.py` |
| Newest measured | 2026-08-31, 486 Alpaca requests |
| Commit | `a28d1dd`, "Run the denominator floor study, and find it is a three part change" |
| Payloads | the table above |
