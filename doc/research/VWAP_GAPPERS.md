# VWAP on gappers

## Status

**Pre-registered. No result exists at the time this section was written.**

Pre-registered at: 2026-08-16T11:05:47-04:00

This section was written by `--preregister`, which refuses to overwrite an
existing report. The results below it were appended by a later run, which
refuses to start unless this section already exists. The ordering is therefore
a property of the files, not a claim.

## The question

Does trading a gapper against its session VWAP produce anything, and if it
does, is the edge in the VWAP rule or merely in the gap screen?

## Population

Every cached session in `data/backtest/eod`, the same set the addressable
sweep used. For each session the population is every universe name whose open
gapped more than 3 percent against the prior close, using
`pool_recall.actual_gappers`, so this and the recall work agree by
construction rather than by inspection.

Prior closes come from the cached end of day files, never from Alpaca. A
prior close defect and a strategy result must not be able to wear each other's
clothes.

Bars are 09:30 to 16:00 one minute SIP bars from Alpaca.

## VWAP definition

Session VWAP, cumulative from 09:30, computed from each bar's own `vw` field
weighted by that bar's volume, and reset every day.

**Premarket volume is NOT included.** The VWAP a rule trades against starts at
the opening bell and knows nothing about the premarket session. This is stated
because the choice changes the level materially on exactly these names, which
by construction have unusual premarket activity.

A bar "closes above VWAP" means its close exceeds the cumulative VWAP
*including that bar*.

## The rules, and there are four

One entry per name per session. No re-entries. No stops and no targets, since
adding them multiplies the search space and the question here is only whether
anything is there at all.

Entry is at the CLOSE of the bar that confirms the signal, never at the price
that triggered it, because the confirmation is not known until the bar closes.
Exit is at the close of the bar that satisfies the exit condition, or at the
15:55 bar, whichever comes first.

A "touch" means: bar t has `low <= VWAP(t)` while the previous bar closed
above its VWAP. That is the shared trigger for `reclaim` and `reject`, which
differ only in which way the next bar resolves, so the two are mutually
exclusive on the same event.

| Rule | Side | Entry | Exit |
| --- | --- | --- | --- |
| `reclaim` | long | a touch at bar t, then bar t+1 closes above VWAP; enter at that close | first later close below VWAP, else 15:55 |
| `hold` | long | the first bar of the session that closes above VWAP | first later close below VWAP, else 15:55 |
| `reject` | short | a touch at bar t, then bar t+1 closes below VWAP; enter at that close | first later close above VWAP, else 15:55 |
| `fade` | short | the first bar of the session that closes below VWAP | first later close above VWAP, else 15:55 |

## Benchmarks

**One, buy the open.** Buy at the 09:30 open and sell at the 15:55 close, same
names, same sessions. This answers whether a rule beats simply holding the
gapper.

**Two, the non-gapped control, and this is the point.** All four rules run
against names that did NOT gap that session, matched to the gappers on 20 day
average dollar volume, same count, same days. This answers whether the edge is
in the VWAP rule or in the gap. If the rules score the same on both sets, the
gap screen contributes nothing.

Both comparisons are reported for every rule.

## Reporting

Per session, never pooled, because the session is the sample unit. For each
rule, the distribution ACROSS SESSIONS of: number of signals, hit rate, median
return, mean return, and interquartile range. Never a bare mean.

Every figure appears gross and net of a fixed round trip cost, a parameter
defaulting to 10 basis points.

For every signal, minutes elapsed since 09:30 at entry, reported as a
distribution. A rule whose signals cluster in the first fifteen minutes is
unusable without a charting platform and screen presence at the open,
regardless of its returns, and that has to sit next to the returns rather than
be discovered afterwards.

## What is not modelled, stated before the numbers

- Fills, spread and slippage are NOT modelled. Every return here is indicative
  only and assumes the close of a one minute bar is obtainable, which it is
  not.
- `universe.json` holds CURRENT listings, so names delisted since are absent.
  The survivors are the ones that survived, and the results are flattered in an
  unknown direction and by an unknown amount.
- The dollar volume used to match controls is a single current snapshot from
  `universe.json`, not a per session figure, so a name's liquidity in May is
  approximated by its liquidity in August.
- No borrow availability or cost is modelled for the two short rules, which on
  gapping small caps is the difference between a backtest and a trade.

## STOP RULE

Written before any number exists, so the decision cannot be made after seeing
them.

**If no rule beats the buy-the-open benchmark net of costs on a median
session, or if the rules perform within noise of the non-gapped control, then
the conclusion is that there is nothing here and the premarket discovery work
stops.**

"Within noise of the control" is judged by a two sided sign test across
sessions on the per session median return difference, gapper minus control, at
p >= 0.05. The test and its threshold are named here so the bar cannot move
later.

---

# Results

Run at: 2026-08-16T11:13:28-04:00

Appended by a run that refused to start until the pre-registration above existed. 61 sessions examined, 10,507 gapper name-sessions and 10,509 control name-sessions with usable bars, 755 Alpaca requests. Round trip cost 10 bps.

Dropped: 4 name-sessions with no bars, 0 with fewer than two, 0 sessions dropped whole for an incomplete sweep.

Every return is a percentage. Every figure below is a distribution ACROSS SESSIONS of a per session statistic, so a median of medians is meant literally and is not a pooled number.

## Benchmark one, buy the open: Gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 130 | 227 | 517 |
| hit rate gross | 61 | 0.0381 | 0.381 | 0.4917 | 0.5796 | 0.9014 |
| hit rate net | 61 | 0.0381 | 0.381 | 0.4857 | 0.5673 | 0.8844 |
| median return gross | 61 | -6.4122 | -0.7673 | -0.1008 | 0.6877 | 4.1184 |
| median return net | 61 | -6.5122 | -0.8673 | -0.2008 | 0.5877 | 4.0184 |
| mean return gross | 61 | -6.6938 | -0.7728 | -0.1132 | 0.9946 | 3.956 |
| mean return net | 61 | -6.7938 | -0.8728 | -0.2132 | 0.8946 | 3.856 |
| IQR of returns net | 61 | 3.1922 | 4.0104 | 4.6321 | 5.5947 | 7.6017 |

## Benchmark one, buy the open: Controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 130 | 227 | 518 |
| hit rate gross | 61 | 0.2615 | 0.4083 | 0.5134 | 0.5904 | 0.7647 |
| hit rate net | 61 | 0.2 | 0.3917 | 0.4866 | 0.5738 | 0.7441 |
| median return gross | 61 | -1.3367 | -0.2947 | 0.0526 | 0.402 | 1.2428 |
| median return net | 61 | -1.4367 | -0.3947 | -0.0474 | 0.302 | 1.1428 |
| mean return gross | 61 | -1.3675 | -0.3728 | 0.0911 | 0.4676 | 1.8099 |
| mean return net | 61 | -1.4675 | -0.4728 | -0.0089 | 0.3676 | 1.7099 |
| IQR of returns net | 61 | 1.6076 | 2.0787 | 2.3904 | 2.708 | 4.1118 |

## Rule reclaim

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 35 | 82 | 123 | 212 | 483 |
| hit rate gross | 61 | 0.0621 | 0.1667 | 0.202 | 0.2488 | 0.413 |
| hit rate net | 61 | 0.0414 | 0.1494 | 0.1801 | 0.2319 | 0.3913 |
| median return gross | 61 | -0.5278 | -0.3693 | -0.3068 | -0.2534 | -0.0938 |
| median return net | 61 | -0.6278 | -0.4693 | -0.4068 | -0.3534 | -0.1938 |
| mean return gross | 61 | -0.5341 | -0.3162 | -0.1027 | 0.0781 | 1.2085 |
| mean return net | 61 | -0.6341 | -0.4162 | -0.2027 | -0.0219 | 1.1085 |
| IQR of returns net | 61 | 0.4116 | 0.5664 | 0.6197 | 0.7529 | 1.9592 |

Entry timing, minutes after 09:30: median 13.0, p25 4.0, p75 46.0. **53.5% of signals enter within the first fifteen minutes.**

### on non-gapped controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 34 | 80 | 115 | 200 | 467 |
| hit rate gross | 61 | 0.1 | 0.1667 | 0.205 | 0.2558 | 0.3438 |
| hit rate net | 61 | 0.0758 | 0.1345 | 0.1772 | 0.2203 | 0.2877 |
| median return gross | 61 | -0.2187 | -0.1723 | -0.1567 | -0.1401 | -0.0964 |
| median return net | 61 | -0.3187 | -0.2723 | -0.2567 | -0.2401 | -0.1964 |
| mean return gross | 61 | -0.2811 | -0.1619 | -0.0797 | 0.0221 | 0.2525 |
| mean return net | 61 | -0.3811 | -0.2619 | -0.1797 | -0.0779 | 0.1525 |
| IQR of returns net | 61 | 0.1948 | 0.2981 | 0.3388 | 0.4071 | 0.6592 |

Entry timing, minutes after 09:30: median 18.0, p25 6.0, p75 57.0. **45.7% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open | 61 | 27 | 0.4426 | -0.193 | 0.44263 |
| vs non-gapped control | 61 | 2 | 0.0328 | -0.1443 | 0.0 |

## Rule hold

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 40 | 88 | 130 | 226 | 516 |
| hit rate gross | 61 | 0.0711 | 0.2048 | 0.2632 | 0.3359 | 0.6875 |
| hit rate net | 61 | 0.0609 | 0.1807 | 0.2403 | 0.3009 | 0.6458 |
| median return gross | 61 | -0.8216 | -0.4844 | -0.3786 | -0.2837 | 0.5966 |
| median return net | 61 | -0.9216 | -0.5844 | -0.4786 | -0.3837 | 0.4966 |
| mean return gross | 61 | -0.821 | -0.3293 | -0.0763 | 0.1541 | 0.7655 |
| mean return net | 61 | -0.921 | -0.4293 | -0.1763 | 0.0541 | 0.6655 |
| IQR of returns net | 61 | 0.5473 | 0.8785 | 1.0457 | 1.2026 | 2.1967 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 3.0. **40.2% of signals enter within the first fifteen minutes.**

### on non-gapped controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 41 | 88 | 127 | 227 | 514 |
| hit rate gross | 61 | 0.1325 | 0.2033 | 0.2644 | 0.2893 | 0.4393 |
| hit rate net | 61 | 0.0964 | 0.1705 | 0.2203 | 0.2558 | 0.4206 |
| median return gross | 61 | -0.3307 | -0.2783 | -0.2278 | -0.1799 | -0.087 |
| median return net | 61 | -0.4307 | -0.3783 | -0.3278 | -0.2799 | -0.187 |
| mean return gross | 61 | -0.4037 | -0.2237 | -0.1703 | 0.0015 | 0.4552 |
| mean return net | 61 | -0.5037 | -0.3237 | -0.2703 | -0.0985 | 0.3552 |
| IQR of returns net | 61 | 0.3903 | 0.5249 | 0.5746 | 0.6684 | 1.1936 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 4.0. **41.5% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open | 61 | 28 | 0.459 | -0.2503 | 0.60892 |
| vs non-gapped control | 61 | 12 | 0.1967 | -0.1334 | 0.0 |

## Rule reject

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 40 | 87 | 127 | 213 | 509 |
| hit rate gross | 61 | 0.0702 | 0.169 | 0.199 | 0.2542 | 0.5759 |
| hit rate net | 61 | 0.0614 | 0.154 | 0.1825 | 0.2271 | 0.5642 |
| median return gross | 61 | -0.6141 | -0.3924 | -0.3388 | -0.2541 | 0.5918 |
| median return net | 61 | -0.7141 | -0.4924 | -0.4388 | -0.3541 | 0.4918 |
| mean return gross | 61 | -0.6863 | -0.3321 | -0.1382 | -0.0076 | 1.2798 |
| mean return net | 61 | -0.7863 | -0.4321 | -0.2382 | -0.1076 | 1.1798 |
| IQR of returns net | 61 | 0.414 | 0.5771 | 0.6774 | 0.7672 | 2.8954 |

Entry timing, minutes after 09:30: median 9.0, p25 4.0, p75 30.0. **61.8% of signals enter within the first fifteen minutes.**

### on non-gapped controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 41 | 88 | 124 | 217 | 508 |
| hit rate gross | 61 | 0.0959 | 0.1707 | 0.2103 | 0.2613 | 0.3415 |
| hit rate net | 61 | 0.0682 | 0.1299 | 0.1752 | 0.2167 | 0.3171 |
| median return gross | 61 | -0.2655 | -0.2194 | -0.1847 | -0.1551 | -0.1106 |
| median return net | 61 | -0.3655 | -0.3194 | -0.2847 | -0.2551 | -0.2106 |
| mean return gross | 61 | -0.3533 | -0.1728 | -0.0924 | -0.023 | 0.1656 |
| mean return net | 61 | -0.4533 | -0.2728 | -0.1924 | -0.123 | 0.0656 |
| IQR of returns net | 61 | 0.2717 | 0.3282 | 0.3721 | 0.4422 | 0.8548 |

Entry timing, minutes after 09:30: median 13.0, p25 5.0, p75 35.0. **54.8% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open | 61 | 25 | 0.4098 | -0.2021 | 0.20003 |
| vs non-gapped control | 61 | 6 | 0.0984 | -0.1363 | 0.0 |

## Rule fade

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 129 | 224 | 514 |
| hit rate gross | 61 | 0.0549 | 0.2056 | 0.2459 | 0.3147 | 0.5526 |
| hit rate net | 61 | 0.044 | 0.1735 | 0.2219 | 0.2931 | 0.5414 |
| median return gross | 61 | -0.7868 | -0.478 | -0.3868 | -0.3138 | 0.4421 |
| median return net | 61 | -0.8868 | -0.578 | -0.4868 | -0.4138 | 0.3421 |
| mean return gross | 61 | -0.7148 | -0.4286 | -0.2245 | -0.0549 | 1.1497 |
| mean return net | 61 | -0.8148 | -0.5286 | -0.3245 | -0.1549 | 1.0497 |
| IQR of returns net | 61 | 0.5042 | 0.8511 | 1.0372 | 1.2874 | 3.2124 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 4.0. **42.3% of signals enter within the first fifteen minutes.**

### on non-gapped controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 128 | 222 | 518 |
| hit rate gross | 61 | 0.113 | 0.1736 | 0.2147 | 0.2615 | 0.4454 |
| hit rate net | 61 | 0.0787 | 0.1449 | 0.1793 | 0.2154 | 0.3866 |
| median return gross | 61 | -0.3912 | -0.2821 | -0.2457 | -0.2101 | -0.0836 |
| median return net | 61 | -0.4912 | -0.3821 | -0.3457 | -0.3101 | -0.1836 |
| mean return gross | 61 | -0.4345 | -0.2725 | -0.1821 | -0.1288 | 0.1666 |
| mean return net | 61 | -0.5345 | -0.3725 | -0.2821 | -0.2288 | 0.0666 |
| IQR of returns net | 61 | 0.3475 | 0.4629 | 0.5302 | 0.6053 | 0.8063 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 5.0. **43.3% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open | 61 | 25 | 0.4098 | -0.3407 | 0.20003 |
| vs non-gapped control | 61 | 9 | 0.1475 | -0.1593 | 0.0 |

## Verdict against the stop rule

The stop rule, as written before any number existed: if no rule beats the buy-the-open benchmark net of costs on a median session, OR the rules perform within noise of the non-gapped control at p >= 0.05 on a two sided sign test, there is nothing here and the premarket discovery work stops.

- Rules beating buy-the-open on the median session, net: NONE
- Rules beating the non-gapped control at p < 0.05: NONE

**VERDICT: the stop rule IS triggered.** No rule clears both conditions, so on the evidence recorded here there is nothing in trading these gappers against session VWAP, and by the rule written before the numbers were seen the premarket discovery work stops.

---

# Version 2, pre-registered

**Pre-registered. No version 2 result exists at the time this section was
written.** Pre-registered at: 2026-08-16T14:10:19-04:00

Version 1 above is superseded and is left in place, because a defective test
that has actually been run is part of the record. Four faults were found in it,
all of which change the answer rather than merely tidying it:

1. `reject` and `fade` fired on the same bar for any gap-up that opened above
   VWAP, so two of the four rules were frequently the same trade.
2. `reclaim` and `reject` shared a trigger described as "pulls back to VWAP",
   which was never defined. Whoever implemented it picked a definition, and
   that definition drove the result.
3. The buy-the-open benchmark was computed across ALL gappers while each rule
   fired on a subset, so the two sides of the comparison were different
   populations.
4. The control set was "did not gap", which admitted a name that gapped down 8
   percent. Those are event names and belong in neither group.

Version 1 also assumed shorting is free, which on gapping small caps it is not.

## The question

Does trading a gapper against its session VWAP produce anything, and if it
does, is the edge in the VWAP rule or merely in the gap screen?

## Population

Every cached session in `data/backtest/eod`. For each session the test
population is every universe name whose open gapped more than 3 percent against
the prior close, using `pool_recall.actual_gappers`, so this and the recall work
agree by construction rather than by inspection.

Prior closes come from the cached end of day files, never from Alpaca, so a
prior close defect and a strategy result cannot wear each other's clothes.

Bars are 09:30 to 16:00 one minute SIP bars from Alpaca, cached locally on
first fetch. A second run must complete with no network calls at all, and the
report states cache hits against fetches.

## The control set

Names whose ABSOLUTE gap that session was under 1 percent, so a
name that gapped down heavily is excluded from both groups rather than quietly
becoming a control.

Matched to the gappers by 20 day average dollar volume DECILE, same count per
decile, same days. Decile boundaries are computed once over the whole universe.
Where a decile holds fewer eligible controls than gappers, the shortfall is
taken and reported rather than back-filled from a neighbouring decile.

Within a decile the choice is a stable hash of session and symbol, which is
deterministic across runs and uncorrelated with anything the test measures.

## VWAP definition

Session VWAP, cumulative from 09:30, from each bar's own `vw` weighted by that
bar's volume, reset daily.

**Premarket volume is NOT included.** The VWAP a rule trades against starts at
the opening bell and knows nothing about the premarket session. Stated because
the choice changes the level materially on exactly these names, which by
construction had unusual premarket activity.

A bar "closes above VWAP" means its close exceeds the cumulative VWAP
*including that bar*.

## The rules, on two clean axes

Direction, and whether the trigger requires the opposite condition first.
Nothing here mentions approaching, pulling back, or any other undefined
gesture. One entry per name per session, no re-entries, no stops, no targets.

| Rule | Side | Entry | Exit |
| --- | --- | --- | --- |
| `hold` | long | first bar that closes ABOVE VWAP, no precondition | first later close below VWAP, else 15:55 |
| `reclaim` | long | first bar that closes ABOVE VWAP after at least one bar has closed below it | first later close below VWAP, else 15:55 |
| `fade` | short | first bar that closes BELOW VWAP, no precondition | first later close above VWAP, else 15:55 |
| `reject` | short | first bar that closes BELOW VWAP after at least one bar has closed above it | first later close above VWAP, else 15:55 |

All four exits are symmetric: a long exits on the first close below VWAP after
entry, a short on the first close above, each or the 15:55 bar, whichever comes
first.

Entry is at the CLOSE of the bar that satisfies the entry condition, because
the condition is not known until the bar closes.

**A known and reported consequence of these definitions.** When the session's
first bar closes below VWAP, `hold` and `reclaim` necessarily fire on the same
bar; likewise `fade` and `reject` when the first bar closes above. That
coincidence is a property of the definitions rather than a defect, and its rate
is reported, so no one reads two columns as two independent findings.

## Benchmark

Buy at the 09:30 open, sell at the 15:55 close.

Computed for each rule ONLY on the name-session pairs where that rule actually
fired, and reported as a paired difference. A rule that fires on a fifth of
names cannot be judged against a benchmark averaged over all of them.

The fraction of gapper name-sessions each rule fired on is reported beside its
returns, since a rule firing on 5 percent of names is a different proposition
from one firing on 80.

## Shorting is not assumed free

`fade` and `reject` are short rules and gappers are frequently hard to borrow.
Alpaca's asset records carry `shortable` and `easy_to_borrow`, and both short
rules are reported twice: across all names, and restricted to names flagged
easy to borrow. If the edge lives only in the unborrowables, it is not an edge.

Stated in advance: those flags are CURRENT, not historical. A name easy to
borrow today may not have been in May, so this bounds the problem rather than
solving it.

## Reporting

Per session, never pooled, because the session is the sample unit. For each
rule, the distribution ACROSS SESSIONS of: number of signals, hit rate, median
return, mean return, and interquartile range. Never a bare mean.

Every figure appears gross and net of a fixed round trip cost, a parameter
defaulting to 10 basis points.

For every signal, minutes elapsed since 09:30 at entry, as a distribution. A
rule whose signals cluster in the first fifteen minutes is unusable without a
charting platform and screen presence at the open, regardless of its returns,
and that has to sit beside the returns rather than be found afterwards.

## What is not modelled, stated before the numbers

- Fills, spread and slippage are NOT modelled. Every return is indicative only
  and assumes the close of a one minute bar is obtainable, which it is not.
- `universe.json` holds CURRENT listings, so names delisted since are absent.
  The results are flattered in an unknown direction and by an unknown amount.
- The dollar volume used for decile matching is a single current snapshot, not
  a per session figure.
- Borrow COST is not modelled, only the availability flag.

## STOP RULE, version 2

Written before any version 2 number exists.

**If no rule beats the buy-the-open benchmark net of costs on a median session,
measured on the name-sessions where that rule fired, or if the rules perform
within noise of the decile-matched control, then there is nothing here and the
premarket discovery work stops.**

"Within noise" is a two sided sign test across sessions on the per session
median return difference, gapper minus control, at p >= 0.05. Named here so the
bar cannot move later.

---

# Results, version 2

Run at: 2026-08-16T14:15:06-04:00

Appended by a run that refused to start until the version 2 pre-registration above existed. 61 sessions, 10,507 gapper name-sessions and 10,492 decile-matched control name-sessions with usable bars. Round trip cost 10 bps.

**Bar cache: 0 symbol-sessions served from cache, 21,002 fetched, 750 Alpaca requests.** A rerun with `--cache-only` completes with no network at all.

Dropped: 3 name-sessions with no bars, 0 with fewer than two usable.

Every return is a percentage. Every figure is a distribution ACROSS SESSIONS of a per session statistic, so a median of medians is meant literally and is not a pooled number.

## Rule coincidence, as warned in the pre-registration

- `hold` and `reclaim` both fired on 10,199 gapper name-sessions, on the SAME bar in 5,051 of them.
- `fade` and `reject` both fired on 10,187 gapper name-sessions, on the SAME bar in 5,262 of them.

Read the coinciding pairs as one finding, not two.

**Control shortfall:** 18 gapper name-sessions had no eligible decile match, by decile {"9": 18}. Taken rather than back-filled from a neighbouring decile, so the control set is that much smaller rather than that much less matched.

**Borrow flags:** 5,276 of the assets Alpaca returned are flagged easy to borrow and 5,275 shortable. On this universe the two flags are identical, so the easy to borrow split below is a weaker test than it appears: it removes the same names either way, and the flags are CURRENT rather than historical.

## Benchmark, buy the open, whole population: Gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 130 | 227 | 517 |
| hit rate gross | 61 | 0.0381 | 0.381 | 0.4917 | 0.5796 | 0.9014 |
| hit rate net | 61 | 0.0381 | 0.381 | 0.4857 | 0.5673 | 0.8844 |
| median return gross | 61 | -6.4122 | -0.7673 | -0.1008 | 0.6877 | 4.1184 |
| median return net | 61 | -6.5122 | -0.8673 | -0.2008 | 0.5877 | 4.0184 |
| mean return gross | 61 | -6.6938 | -0.7728 | -0.1132 | 0.9946 | 3.956 |
| mean return net | 61 | -6.7938 | -0.8728 | -0.2132 | 0.8946 | 3.856 |
| IQR of returns net | 61 | 3.1922 | 4.0104 | 4.6321 | 5.5947 | 7.6017 |

## Benchmark, buy the open, whole population: Controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 130 | 227 | 518 |
| hit rate gross | 61 | 0.1707 | 0.4154 | 0.5019 | 0.6161 | 0.7588 |
| hit rate net | 61 | 0.1585 | 0.3846 | 0.4674 | 0.6071 | 0.7235 |
| median return gross | 61 | -1.0417 | -0.3723 | 0.0052 | 0.4874 | 1.2704 |
| median return net | 61 | -1.1417 | -0.4723 | -0.0948 | 0.3874 | 1.1704 |
| mean return gross | 61 | -1.2626 | -0.3709 | -0.0176 | 0.4579 | 1.7692 |
| mean return net | 61 | -1.3626 | -0.4709 | -0.1176 | 0.3579 | 1.6692 |
| IQR of returns net | 61 | 1.2247 | 1.8454 | 2.1751 | 2.4719 | 3.7713 |

## Rule hold (long)

**Fired on 99.2% of gapper name-sessions** (10,421 trades).

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 40 | 88 | 130 | 226 | 516 |
| hit rate gross | 61 | 0.0711 | 0.2048 | 0.2632 | 0.3359 | 0.6875 |
| hit rate net | 61 | 0.0609 | 0.1807 | 0.2403 | 0.3009 | 0.6458 |
| median return gross | 61 | -0.8216 | -0.4844 | -0.3786 | -0.2837 | 0.5966 |
| median return net | 61 | -0.9216 | -0.5844 | -0.4786 | -0.3837 | 0.4966 |
| mean return gross | 61 | -0.821 | -0.3293 | -0.0763 | 0.1541 | 0.7655 |
| mean return net | 61 | -0.921 | -0.4293 | -0.1763 | 0.0541 | 0.6655 |
| IQR of returns net | 61 | 0.5473 | 0.8785 | 1.0457 | 1.2026 | 2.1967 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 3.0. **89.9% of signals enter within the first fifteen minutes.**

### on decile-matched controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 88 | 127 | 226 | 515 |
| hit rate gross | 61 | 0.1084 | 0.1899 | 0.2429 | 0.3095 | 0.4508 |
| hit rate net | 61 | 0.0723 | 0.1625 | 0.2105 | 0.2783 | 0.4146 |
| median return gross | 61 | -0.3322 | -0.2473 | -0.205 | -0.1656 | -0.0578 |
| median return net | 61 | -0.4322 | -0.3473 | -0.305 | -0.2656 | -0.1578 |
| mean return gross | 61 | -0.3872 | -0.2413 | -0.1362 | -0.0175 | 0.3217 |
| mean return net | 61 | -0.4872 | -0.3413 | -0.2362 | -0.1175 | 0.2217 |
| IQR of returns net | 61 | 0.3615 | 0.4535 | 0.5352 | 0.6641 | 1.3322 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 4.0. **90.0% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open, PAIRED on the name-sessions this rule fired on | 61 | 28 | 0.459 | -0.2584 | 0.60892 |
| vs decile-matched control | 61 | 10 | 0.1639 | -0.1918 | 0.0 |

## Rule reclaim (long)

**Fired on 97.1% of gapper name-sessions** (10,199 trades).

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 40 | 87 | 127 | 220 | 500 |
| hit rate gross | 61 | 0.0521 | 0.1818 | 0.2308 | 0.2727 | 0.4045 |
| hit rate net | 61 | 0.0417 | 0.1515 | 0.2026 | 0.2472 | 0.3933 |
| median return gross | 61 | -0.4861 | -0.3616 | -0.2946 | -0.2569 | -0.0827 |
| median return net | 61 | -0.5861 | -0.4616 | -0.3946 | -0.3569 | -0.1827 |
| mean return gross | 61 | -0.5415 | -0.3044 | -0.1136 | 0.07 | 0.9247 |
| mean return net | 61 | -0.6415 | -0.4044 | -0.2136 | -0.03 | 0.8247 |
| IQR of returns net | 61 | 0.4712 | 0.5637 | 0.67 | 0.8347 | 1.7135 |

Entry timing, minutes after 09:30: median 7.0, p25 3.0, p75 20.0. **69.5% of signals enter within the first fifteen minutes.**

### on decile-matched controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 41 | 87 | 125 | 221 | 508 |
| hit rate gross | 61 | 0.1048 | 0.175 | 0.2165 | 0.2548 | 0.3708 |
| hit rate net | 61 | 0.0806 | 0.1383 | 0.1842 | 0.216 | 0.3596 |
| median return gross | 61 | -0.2441 | -0.1798 | -0.1609 | -0.1411 | -0.0665 |
| median return net | 61 | -0.3441 | -0.2798 | -0.2609 | -0.2411 | -0.1665 |
| mean return gross | 61 | -0.2736 | -0.1648 | -0.0888 | 0.0235 | 0.2659 |
| mean return net | 61 | -0.3736 | -0.2648 | -0.1888 | -0.0765 | 0.1659 |
| IQR of returns net | 61 | 0.2249 | 0.2997 | 0.3463 | 0.4079 | 0.9514 |

Entry timing, minutes after 09:30: median 8.0, p25 3.0, p75 22.0. **66.9% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open, PAIRED on the name-sessions this rule fired on | 61 | 24 | 0.3934 | -0.2194 | 0.12373 |
| vs decile-matched control | 61 | 3 | 0.0492 | -0.1235 | 0.0 |

## Rule fade (short)

**Fired on 99.0% of gapper name-sessions** (10,399 trades).

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 89 | 128 | 224 | 514 |
| hit rate gross | 61 | 0.0549 | 0.2075 | 0.2459 | 0.3147 | 0.5526 |
| hit rate net | 61 | 0.044 | 0.1735 | 0.2219 | 0.2931 | 0.5414 |
| median return gross | 61 | -0.7868 | -0.478 | -0.3881 | -0.3138 | 0.4421 |
| median return net | 61 | -0.8868 | -0.578 | -0.4881 | -0.4138 | 0.3421 |
| mean return gross | 61 | -0.7148 | -0.4286 | -0.2245 | -0.0549 | 1.1497 |
| mean return net | 61 | -0.8148 | -0.5286 | -0.3245 | -0.1549 | 1.0497 |
| IQR of returns net | 61 | 0.5042 | 0.8511 | 1.0372 | 1.2874 | 3.2124 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 4.0. **89.9% of signals enter within the first fifteen minutes.**

### on decile-matched controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 88 | 129 | 222 | 517 |
| hit rate gross | 61 | 0.0725 | 0.1765 | 0.2069 | 0.2452 | 0.3782 |
| hit rate net | 61 | 0.0584 | 0.1429 | 0.1724 | 0.2065 | 0.3549 |
| median return gross | 61 | -0.3642 | -0.27 | -0.2186 | -0.1772 | -0.0749 |
| median return net | 61 | -0.4642 | -0.37 | -0.3186 | -0.2772 | -0.1749 |
| mean return gross | 61 | -0.4348 | -0.2646 | -0.1788 | -0.1058 | 0.1465 |
| mean return net | 61 | -0.5348 | -0.3646 | -0.2788 | -0.2058 | 0.0465 |
| IQR of returns net | 61 | 0.2682 | 0.4253 | 0.4872 | 0.5327 | 0.9416 |

Entry timing, minutes after 09:30: median 1.0, p25 0.0, p75 5.0. **87.3% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open, PAIRED on the name-sessions this rule fired on | 61 | 26 | 0.4262 | -0.2553 | 0.30568 |
| vs decile-matched control | 61 | 5 | 0.082 | -0.1781 | 0.0 |

### Restricted to names flagged easy to borrow

9,746 trades, 93.7% of this rule's gapper trades.

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 38 | 81 | 122 | 211 | 483 |
| hit rate gross | 61 | 0.0595 | 0.2041 | 0.2568 | 0.3175 | 0.5444 |
| hit rate net | 61 | 0.0476 | 0.1681 | 0.2273 | 0.2896 | 0.5323 |
| median return gross | 61 | -0.7696 | -0.4751 | -0.3881 | -0.3021 | 0.3885 |
| median return net | 61 | -0.8696 | -0.5751 | -0.4881 | -0.4021 | 0.2885 |
| mean return gross | 61 | -0.7611 | -0.425 | -0.2262 | -0.0372 | 1.1059 |
| mean return net | 61 | -0.8611 | -0.525 | -0.3262 | -0.1372 | 1.0059 |
| IQR of returns net | 61 | 0.5472 | 0.8249 | 1.0234 | 1.2636 | 3.2353 |

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open, paired, easy to borrow only | 61 | 26 | 0.4262 | -0.3259 | 0.30568 |
| vs control, easy to borrow only | 61 | 5 | 0.082 | -0.1617 | 0.0 |

## Rule reject (short)

**Fired on 97.0% of gapper name-sessions** (10,187 trades).

### on gappers

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 40 | 87 | 127 | 219 | 511 |
| hit rate gross | 61 | 0.0549 | 0.1683 | 0.1994 | 0.2595 | 0.4942 |
| hit rate net | 61 | 0.033 | 0.1433 | 0.181 | 0.2405 | 0.4864 |
| median return gross | 61 | -0.6178 | -0.3579 | -0.3142 | -0.2388 | -0.0133 |
| median return net | 61 | -0.7178 | -0.4579 | -0.4142 | -0.3388 | -0.1133 |
| mean return gross | 61 | -0.6627 | -0.2899 | -0.1505 | 0.037 | 1.0187 |
| mean return net | 61 | -0.7627 | -0.3899 | -0.2505 | -0.063 | 0.9187 |
| IQR of returns net | 61 | 0.3551 | 0.5694 | 0.6797 | 0.7641 | 2.9198 |

Entry timing, minutes after 09:30: median 6.0, p25 3.0, p75 21.0. **69.5% of signals enter within the first fifteen minutes.**

### on decile-matched controls

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 42 | 87 | 126 | 221 | 511 |
| hit rate gross | 61 | 0.058 | 0.1574 | 0.1827 | 0.2146 | 0.3006 |
| hit rate net | 61 | 0.0311 | 0.1229 | 0.1508 | 0.1772 | 0.2644 |
| median return gross | 61 | -0.3167 | -0.1899 | -0.1641 | -0.1445 | -0.1113 |
| median return net | 61 | -0.4167 | -0.2899 | -0.2641 | -0.2445 | -0.2113 |
| mean return gross | 61 | -0.382 | -0.1989 | -0.1356 | -0.0879 | 0.1239 |
| mean return net | 61 | -0.482 | -0.2989 | -0.2356 | -0.1879 | 0.0239 |
| IQR of returns net | 61 | 0.1986 | 0.3047 | 0.3445 | 0.3912 | 0.5642 |

Entry timing, minutes after 09:30: median 9.0, p25 3.0, p75 24.0. **65.7% of signals enter within the first fifteen minutes.**

### Against both benchmarks, net of costs

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open, PAIRED on the name-sessions this rule fired on | 61 | 26 | 0.4262 | -0.1299 | 0.30568 |
| vs decile-matched control | 61 | 6 | 0.0984 | -0.1347 | 0.0 |

### Restricted to names flagged easy to borrow

9,543 trades, 93.7% of this rule's gapper trades.

| statistic | sessions | min | p25 | median | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| signals per session | 61 | 37 | 80 | 121 | 206 | 480 |
| hit rate gross | 61 | 0.0476 | 0.1622 | 0.1972 | 0.26 | 0.496 |
| hit rate net | 61 | 0.0357 | 0.1429 | 0.169 | 0.2394 | 0.4879 |
| median return gross | 61 | -0.6198 | -0.3586 | -0.2987 | -0.2355 | -0.0066 |
| median return net | 61 | -0.7198 | -0.4586 | -0.3987 | -0.3355 | -0.1066 |
| mean return gross | 61 | -0.6671 | -0.3087 | -0.1326 | 0.0198 | 1.0177 |
| mean return net | 61 | -0.7671 | -0.4087 | -0.2326 | -0.0802 | 0.9177 |
| IQR of returns net | 61 | 0.4153 | 0.565 | 0.686 | 0.7522 | 2.9448 |

| comparison | sessions | won | win rate | median difference | sign test p |
| --- | ---: | ---: | ---: | ---: | ---: |
| vs buy the open, paired, easy to borrow only | 61 | 28 | 0.459 | -0.1242 | 0.60892 |
| vs control, easy to borrow only | 61 | 5 | 0.082 | -0.1298 | 0.0 |

## Verdict against the stop rule, version 2

The stop rule, as written before any version 2 number existed: if no rule beats the buy-the-open benchmark net of costs on a median session, measured on the name-sessions where that rule fired, OR the rules perform within noise of the decile-matched control at p >= 0.05 on a two sided sign test, there is nothing here and the premarket discovery work stops.

- Rules beating the PAIRED buy-the-open on the median session, net: NONE
- Rules beating the decile-matched control at p < 0.05: NONE

**VERDICT: the stop rule IS triggered.** No rule clears both conditions, so on the evidence recorded here there is nothing in trading these gappers against session VWAP, and by the rule written before the numbers were seen the premarket discovery work stops.
