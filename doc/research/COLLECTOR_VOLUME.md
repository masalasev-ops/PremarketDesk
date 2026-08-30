# Collector volume, diagnosed

Written 2026-08-18. Findings only. No collector code was changed in this pass.

The nightly writes runs/<date>/verify_intraday.json, the check BUILD_PLAN.md
names as definitive for collector volume: collector bars against EODHD 1m
intraday, identical minutes only. Its first live reading, 2026-08-14, was 0 of
37 symbols within one percent at a median ABSOLUTE difference of 70.95 percent,
and nobody had looked at it. This is that look.

The check reports an absolute median, which discards the most informative bit.
[corrected 2026-08-20: it does not any more, and this document is why.
verify_against_intraday now persists median_signed_pct, the aggregate ratio,
the per symbol above and below counts, and a `direction` of under, over, mixed
or unknown, returning mixed where the typical symbol and the aggregate tape
fall on opposite sides of the vendor, which is the 2026-08-14 row below. The
sentence stands as written because it was true when written. Summaries already
on disk are not rewritten, so a reading taken before 2026-08-20 comes back with
direction unknown rather than a guessed sign.]
Everything below is SIGNED, positive meaning the collector recorded more volume
than the vendor over the same minutes.

## Headline

| session | compared | signed median | abs median | negative | positive | within 1% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-08-14 | 37 | -33.77% | 70.95% | 23 | 14 | 0 |
| 2026-08-17 | 29 | -88.49% | 88.49% | 29 | 0 | 0 |

| session | collector total | intraday total | ratio |
| --- | ---: | ---: | ---: |
| 2026-08-14 | 24,899,631 | 6,508,433 | 3.8257 |
| 2026-08-17 | 682,965 | 6,870,865 | 0.0994 |

The two sessions do not tell the same story, which is itself the finding.
2026-08-17 is uniformly negative, 29 of 29, tightly clustered. 2026-08-14 is
mixed, 23 negative and 14 positive, and its aggregate is 3.83 times the vendor's
because a handful of enormous positives outweigh the many negatives. A signed
median of -33.77 percent beside a total ratio of 3.83 is the signature of a
distribution driven by outliers, and the absolute median the check prints hides
both facts.

## Is the check measuring the same minutes

Asked first, because a window mismatch reported as a volume defect is a bug this
repository already carries once, in pm_rvol's 07:20 numerator over its 04:00
denominator.

The check intersects the two sides on minute keys and sums only the intersection,
so a pure window mismatch should surface as few common minutes rather than as a
volume gap. The risk is subtler: if the two sides key the same minute differently,
say one stamping the bar start and the other the bar end, the intersection would
still be large while pairing each collector minute against the WRONG vendor
minute. The shift columns test exactly that.

### 2026-08-14

| symbol | collector mins | window | intraday mins | window | common | collector only | intraday only | common if +1min | if -1min |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| ANGX.US | 11 | 07:36 to 09:20 | 16 | 07:46 to 09:20 | 3 | 8 | 13 | 0 | 3 |
| AOSL.US | 12 | 07:31 to 09:22 | 20 | 07:31 to 09:22 | 5 | 7 | 15 | 3 | 3 |
| ARX.US | 59 | 07:20 to 09:22 | 66 | 07:20 to 09:23 | 41 | 18 | 25 | 32 | 32 |

### 2026-08-17

| symbol | collector mins | window | intraday mins | window | common | collector only | intraday only | common if +1min | if -1min |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| AAOI.US | 113 | 07:19 to 09:24 | 127 | 07:19 to 09:25 | 113 | 0 | 14 | 113 | 112 |
| AEHR.US | 41 | 07:17 to 09:20 | 114 | 07:17 to 09:21 | 41 | 0 | 73 | 36 | 38 |
| AMAT.US | 108 | 07:19 to 09:24 | 127 | 07:19 to 09:25 | 108 | 0 | 19 | 108 | 107 |

**The keys align and the check is sound.** On 2026-08-17 every collector minute
is present on the vendor side, collector only is 0 for all three, and shifting
the collector keys by a minute in either direction makes the overlap WORSE
(113 to 113 and 112, 108 to 108 and 107). There is no off by one. The vendor
simply covers more minutes than the collector heard, which is the collector
missing minutes rather than the two sides describing different windows.

2026-08-14 overlaps far less well, and in the informative direction: the
collector holds minutes the vendor does NOT (8, 7 and 18 of them), which no
window offset explains.

## Per symbol, signed, sorted

### 2026-08-14, signed median -33.77%

| symbol | mins | collector | intraday | signed % |
| --- | ---: | ---: | ---: | ---: |
| CBRS.US | 116 | 86,817 | 2,012,273 | -95.69% |
| BIRK.US | 94 | 82,097 | 919,330 | -91.07% |
| AVAH.US | 10 | 686 | 3,872 | -82.28% |
| CLBT.US | 63 | 28,020 | 144,310 | -80.58% |
| ARX.US | 41 | 59,865 | 292,116 | -79.51% |
| CRMD.US | 4 | 726 | 2,524 | -71.24% |
| FRMI.US | 73 | 56,158 | 193,340 | -70.95% |
| SNDK.US | 125 | 272,303 | 878,879 | -69.02% |
| WDAY.US | 48 | 7,561 | 22,111 | -65.80% |
| BLSH.US | 10 | 1,224 | 3,335 | -63.30% |
| OMER.US | 18 | 2,276 | 5,956 | -61.79% |
| RPD.US | 8 | 1,409 | 3,433 | -58.96% |
| ANGX.US | 3 | 814 | 1,949 | -58.23% |
| WIX.US | 16 | 1,166 | 2,347 | -50.32% |
| XE.US | 53 | 10,048 | 19,511 | -48.50% |
| SECZ.US | 43 | 26,562 | 51,221 | -48.14% |
| MH.US | 5 | 476 | 866 | -45.03% |
| QMCO.US | 63 | 14,941 | 26,476 | -43.57% |
| HUBS.US | 18 | 1,418 | 2,141 | -33.77% |
| TPR.US | 84 | 30,531 | 45,655 | -33.13% |
| GTM.US | 2 | 573 | 802 | -28.55% |
| LFTO.US | 12 | 1,628 | 2,019 | -19.37% |
| NABL.US | 2 | 1,329 | 1,396 | -4.80% |
| TBBB.US | 4 | 1,713 | 1,271 | +34.78% |
| DKL.US | 4 | 673 | 480 | +40.21% |
| VIXY.US | 41 | 57,171 | 28,114 | +103.35% |
| BGSI.US | 1 | 142 | 60 | +136.67% |
| REZI.US | 34 | 30,969 | 11,134 | +178.15% |
| SPY.US | 125 | 1,550,327 | 327,159 | +373.88% |
| AOSL.US | 5 | 4,574 | 954 | +379.45% |
| BSP.US | 36 | 47,037 | 5,253 | +795.43% |
| IWM.US | 114 | 1,098,500 | 121,519 | +803.97% |
| QQQ.US | 125 | 5,907,879 | 481,346 | +1127.37% |
| TLT.US | 118 | 10,688,231 | 780,284 | +1269.79% |
| USO.US | 124 | 3,882,971 | 105,650 | +3575.32% |
| DIA.US | 92 | 875,442 | 9,217 | +9398.12% |
| UUP.US | 2 | 65,374 | 130 | +50187.69% |

### 2026-08-17, signed median -88.49%

| symbol | mins | collector | intraday | signed % |
| --- | ---: | ---: | ---: | ---: |
| UUP.US | 2 | 660 | 24,877 | -97.35% |
| IWM.US | 70 | 14,979 | 214,389 | -93.01% |
| QQQ.US | 116 | 32,568 | 439,907 | -92.60% |
| INTC.US | 126 | 131,797 | 1,716,683 | -92.32% |
| SPY.US | 106 | 32,532 | 412,429 | -92.11% |
| USO.US | 78 | 29,556 | 338,502 | -91.27% |
| HTHT.US | 20 | 5,081 | 57,440 | -91.15% |
| SAP.US | 12 | 360 | 4,049 | -91.11% |
| AVGO.US | 114 | 16,116 | 175,722 | -90.83% |
| ASML.US | 65 | 884 | 9,577 | -90.77% |
| AMD.US | 122 | 54,335 | 538,565 | -89.91% |
| BABA.US | 93 | 33,241 | 319,003 | -89.58% |
| TLT.US | 105 | 76,766 | 711,930 | -89.22% |
| MU.US | 126 | 109,052 | 948,574 | -88.50% |
| TSM.US | 101 | 10,785 | 93,698 | -88.49% |
| HUBS.US | 17 | 619 | 5,195 | -88.08% |
| AEHR.US | 41 | 2,351 | 19,617 | -88.02% |
| AMAT.US | 108 | 12,611 | 98,841 | -87.24% |
| WDC.US | 106 | 13,611 | 102,726 | -86.75% |
| WDAY.US | 28 | 923 | 6,718 | -86.26% |
| LITE.US | 106 | 8,939 | 63,359 | -85.89% |
| AAOI.US | 113 | 35,073 | 246,930 | -85.80% |
| AXTI.US | 107 | 36,446 | 227,277 | -83.96% |
| STX.US | 93 | 5,304 | 31,806 | -83.32% |
| VIXY.US | 14 | 1,941 | 9,990 | -80.57% |
| AVAV.US | 25 | 816 | 4,127 | -80.23% |
| DIA.US | 46 | 14,566 | 46,745 | -68.84% |
| TEAM.US | 12 | 876 | 1,841 | -52.42% |
| MKSI.US | 7 | 177 | 348 | -49.14% |

## The decisive comparison: which side is stable

Eight ETFs were collected on both sessions, so they can be read across the two.
The vendor's numbers for the same symbol two sessions apart sit in the same
order of magnitude. The collector's do not.

| symbol | intraday 08-14 | intraday 08-17 | vendor swing | collector 08-14 | collector 08-17 | collector swing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TLT.US | 780,284 | 711,930 | 1.1x | 10,688,231 | 76,766 | 139x |
| QQQ.US | 481,346 | 439,907 | 1.1x | 5,907,879 | 32,568 | 181x |
| SPY.US | 327,159 | 412,429 | 1.3x | 1,550,327 | 32,532 | 48x |
| IWM.US | 121,519 | 214,389 | 1.8x | 1,098,500 | 14,979 | 73x |
| USO.US | 105,650 | 338,502 | 3.2x | 3,882,971 | 29,556 | 131x |
| VIXY.US | 28,114 | 9,990 | 2.8x | 57,171 | 1,941 | 29x |
| DIA.US | 9,217 | 46,745 | 5.1x | 875,442 | 14,566 | 60x |
| UUP.US | 130 | 24,877 | 191x | 65,374 | 660 | 99x |

Premarket ETF volume varies session to session, so a swing of 1.1x to 5x on the
vendor side is ordinary. A swing of 48x to 181x on the collector side, for the
same symbols over the same two mornings, is not. The reference is the steady
side and the measurement is the moving one.

## Causes ruled out

- **Window mismatch.** The check sums only the minute keys both sides carry, and
  the shift test shows the keys are correctly paired rather than offset. Ruled
  out above.
- **Late trade dropping.** The collector discards trades arriving after
  late_trade_grace_s. It dropped 0 shares, 0.00 percent of volume, on 2026-08-14
  and 3,934 shares, 0.30 percent, on 2026-08-17. Three tenths of one percent
  cannot produce an 88 percent shortfall.
- **Poll fallback.** Both sessions ran mode "ws" with 1 connection, 0 reconnects
  and 1 resubscription, and every bar in both files carries src "ws". Neither
  session fell back to Live v1 polling, so the known unsound cumulative volume
  path is not involved.
- **A thin tape.** 2026-08-17's collector folded 33,489 trades against
  2026-08-14's 191,194, for MORE symbols, 50 against 38. The vendor's totals for
  the two mornings are comparable. A 5.7x difference in trades folded on a tape
  the vendor says was similar is a property of the collector, not the market.

## Verdict

**The check is sound. The collector is at fault.**

The check compares identical, correctly keyed minutes, and its reference is
stable across sessions in a way the collector is not. Nothing in its
construction accounts for a gap of this size or for the gap changing sign
between two mornings.

What the collector does is not one defect with one direction. On 2026-08-17,
the clean morning, it under-recorded uniformly: every one of 29 symbols
negative, median -88.49 percent, meaning it captured roughly an eighth of the
volume the vendor reports over the very same minutes. On 2026-08-14 it
over-recorded the ETFs by up to 50,188 percent while under-recording most
common stocks, ending 3.83 times the vendor in aggregate.

So the collector is not merely low, it is NOT REPRODUCIBLE session to session.
That is the more serious finding, because a consistent fraction could be
calibrated around and an unstable one cannot.

## What this puts in doubt

Collector premarket volume is the numerator of BOTH volume measures, pm_rvol
and pm_float_rotation, and pm_volume is the basis both record. Every RVOL and
every float rotation published so far rests on it. The float rotation bands are
separately miscalibrated for a related reason recorded in DECISIONS.md
2026-08-17 seventh: they were fitted on Alpaca volume and are applied to
collector volume.

The delivery gate data/UNVERIFIED is still in place, and BUILD_PLAN's go live
step asks for the morning gate table to be reviewed before it is deleted. That
table shows RVOLs computed on this numerator. This finding is a reason to leave
the gate exactly where it is.

## Caveats on these readings

- 2026-08-17's reading covers 29 of 50 collected symbols. The other 21 had no
  EODHD intraday bars at the time this was run, roughly 02:00 ET on 2026-08-18,
  because intraday publishes a few hours behind. The check should be re-run once
  that day is fully published, and the numbers here revised if it moves.
- 2026-08-14 is the morning that carried the known vintage defect, where the
  bulk feed served the previous session. It is reported here in full because it
  is on the record, not because it is trusted. The verdict rests on 2026-08-17.
- Two sessions is two sessions. The uniform negative result on the clean morning
  is the strongest single piece of evidence here, and it is one morning.

## Not done here, deliberately

No collector code was changed. The obvious next question is WHY the websocket
tape disagrees with the vendor's own published bars by this much, which means
looking at what the trade messages carry and whether every subscribed symbol
streams for the whole window. That is a separate pass.

---

# The separate pass, 2026-08-19

The question left open above was why. This is what the archived bar files
answer on their own, before any live measurement.

## What the collector is not doing wrong

Four candidate mechanisms are dead on the existing data.

**It is not misreading the size field.** Mean trade size per bar is ordinary in
every session that matters. SPY's median bar averages 65 shares on 2026-08-14,
36 on 2026-08-17 and 26 on 2026-08-18; QQQ 70, 22 and 30. Those are premarket
odd lots, which is what premarket is made of. A collector reading the wrong
field would show implausible sizes, and it does not.

**It is not losing messages inside itself.** The run stats record messages
equal to trades folded in every session: 191,194 and 191,194 on 2026-08-14,
33,489 and 33,489 on 2026-08-17. Every frame that arrived was parsed and folded.
Whatever is missing never arrived.

**It is not a socket that died and recovered.** One connection, zero
reconnects, one resubscription, zero status frames on both clean sessions.

**It is not throughput collapsing under load.** Plotted by ten minute block,
the trade rate on 2026-08-17 and 2026-08-18 is flat across the whole window,
between roughly 2,000 and 3,300 trades per block from 07:20 to 09:25. There is
no step down, no gap and no recovery. A client falling behind its socket does
not look like this.

## What the collector IS doing wrong, found and fixed here

The subscription replays a last trade per symbol when it lands, and that trade
carries its ORIGINAL timestamp. The collector folded those into bars.

On 2026-08-18 that put three bars dated 2026-08-17 into the 2026-08-18
premarket file, one of them stamped 15:59 the previous afternoon. Another
forty-five were stamped between 07:00 and 07:19 on a morning the collector
connected at 07:20:02. Every single one carried exactly one trade, which is the
signature: one replayed message per symbol. 2026-08-17 carries forty-seven of
them, 2026-08-14 none, because that run's window opened at the same minute it
connected.

The volume is trivial, 1,467 shares on 2026-08-17 and 4,376 on 2026-08-18,
which is 0.11 and 0.27 percent. That is NOT what makes it a defect.
pm_window_starts_late is derived from the first bar present, so a replayed
07:00 print makes a window the collector reached at 07:20 look covered from
07:00, and the flag that exists to warn a reader about exactly that says
nothing. It is a vintage defect in miniature: a previous session's trade
counted as this morning's.

The collector now refuses any trade stamped outside the window the run is
collecting, counts them, names five of them in the log and records the count in
the run stats. Proven by replaying the real 2026-08-18 file through the fixed
builder, which refuses 48 trades including the two dated to the previous
session, and by a builder given no window refusing nothing.

It does not close the volume gap and is not claimed to.

## What the volume gap is narrowed to

One structural difference separates the sessions that look right from the ones
that do not, and it is the size of the subscription.

| session | subscribed | messages | SPY trades | SPY per minute | SPY shares |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-08-14 | 38 | 191,194 | 21,428 | 171 | 1,550,327 |
| 2026-08-17 | 50 | 33,489 | 618 | 5.8 | 32,532 |
| 2026-08-18 | 50 | 36,530 | 573 | 5.3 | 29,410 |

[corrected 2026-08-19: this table carried a fourth row, "2026-08-13 (open
market) | 38 | n/a | 37,792 | 727 | 2,082,908", read as a second session at
thirty eight subscriptions that looked right. It is not a premarket session at
all. Its bars run 13:32 to 20:00, regular and after hours trade; its three
sidecar records are evening runs finishing 20:15, 20:35 and 20:56; and its
1,574 recorded messages cannot have produced its 270,086 trades, so whichever
run wrote most of its bars recorded no stats at all, which is why the messages
column read n/a. It is removed rather than annotated because a row in a
comparison table gets counted whatever the note beside it says.]

Fifty is the documented cap. The subscription files confirm both later mornings
requested exactly 50 unique symbols with nothing dropped to fit. The same
symbols, over comparable mornings, fell from 171 trades a minute to 5.8, a
factor of about thirty, while EODHD's own bars for those mornings put SPY at
327,159 and 412,429 shares, a factor of 1.3.

The collector's own source already carried the suspicion, written the day
before the first fifty symbol morning: "Monday is the first morning at fifty
subscriptions and the throughput has only ever been measured at thirty eight,
so this is the run that has to be able to say which names the socket actually
served."

Two sessions each side is a correlation, not a cause, and it is not enough to
change the collector on. src/research/probe_socket_cap.py turns it into a
measurement: one watch set of the eight context ETFs present in both arms, arm
A subscribing to those eight alone, arm B subscribing to fifty, the arms
alternating so the rising premarket rate cannot be mistaken for the effect, and
the first message per symbol discarded because of the replay documented above.
It refuses to start after 07:10, because the fifty symbol pool is account wide
and a probe holding slots would starve the morning it is meant to explain.
[corrected 2026-08-20: the fixed hour is gone. probe_socket_cap.py now refuses
any run that would start inside, or finish inside, the collector's own
configured window, CRITERIA [collector] start_time to stop_time, which is what
the reason above actually argues for. The fixed 07:10 refused every remaining
moment of 2026-08-19 once the power outage moved the run, including the hours
after 09:25 when the socket was free, which is why the answer below was taken
at 09:35.]

Registered as a one time task for 06:20 on 2026-08-19. It spends no quota.
[corrected 2026-08-20: it was registered for 06:20 and lost to a power outage,
then re-armed with `schtasks /Change` against a task that had never been
created, which failed silently, and the run that produced everything below was
taken by hand at 09:35. There is now a supported way to arm it,
`register_tasks.ps1 -Probe YYYY-MM-DD`, which registers one trigger at 06:30
and wakes the machine. It is armed for 2026-08-21.]

## What the answer decides

If arm B's per symbol rate is near arm A's, the cap is innocent and the gap has
another cause, and the next place to look is whether EODHD's trades feed is a
venue subset while its intraday bars are consolidated, which would make the
shortfall a permanent property to calibrate against rather than a bug to fix.

If arm B's rate is far below arm A's, the cap is the cause and the fix is a
choice between subscribing to fewer names and splitting the list across
connections. That choice has a cost either way: fewer names means a smaller
watchlist, and more connections may or may not be within what the account
allows, which the same probe can answer by trying it.

Either way the answer is a measurement rather than an inference, and until it
lands the delivery gate data/UNVERIFIED stays where it is.


# The answer, 2026-08-19 09:35 to 10:01

## The cap is innocent

The probe ran its full eight arms, none refused, and the two subscription sizes
deliver the same rate per symbol.

| symbol | A msg/s at 8 subs | B msg/s at 50 subs | B/A |
| --- | ---: | ---: | ---: |
| SPY.US | 1.21 | 1.13 | 0.94 |
| QQQ.US | 4.88 | 5.96 | 1.22 |
| IWM.US | 0.86 | 0.64 | 0.74 |
| DIA.US | 0.46 | 0.34 | 0.74 |
| TLT.US | 0.46 | 0.34 | 0.74 |
| USO.US | 0.07 | 0.09 | 1.28 |
| UUP.US | 0.01 | 0.00 | 0.67 |
| VIXY.US | 0.17 | 0.15 | 0.87 |

Median B/A is 0.87 across the eight. Arm B's forty two filler symbols came from
today's real subscription list rather than from a quiet universe slice, so the
load on the socket was the load the collector puts on it, and arm B pushed 66.5
messages a second against the collector's 4.7 on a fifty symbol morning. A
subscription at the cap, carrying the morning's own noisy names, at fourteen
times the collector's message rate, did not lose a symbol.

By the test this document pre registered, that is the first branch: the cap is
innocent and the gap has another cause.

**[corrected 2026-08-21: the verdict stands and its headline number never
carried it.** Each symbol's B/A was recomputed per cycle on this same payload,
four cycles of both arms, with nothing about the cap changing between them. The
well measured symbols moved by a factor of 2.4 across those cycles. The effect
this table is being read for is the distance of 0.87 from 1.00, which is 1.15.
A measurement whose own repeat spread is twice the effect it is asked about
separates nothing, and the median above should never have been offered as the
reason for anything.

Two other legs of this section do carry the verdict and neither is a ratio of
rates. Arm B held fifty symbols at fourteen times the collector's message rate
and lost no symbol, which is an existence test, not a comparison. And the
vendor comparison later in this file put the socket at 2.1 to 12.1 percent of
EODHD's consolidated bars at BOTH subscription sizes, which is a shortfall the
cap cannot explain because it does not change with the cap. The conclusion is
therefore unchanged and its support is now named correctly.

probe_socket_cap.py computes that spread from the cycles it already runs and
prints it beside the median, and CRITERIA [Collector] min_probe_messages_per_arm
keeps a symbol out of the median unless both arms carried 20 messages for it,
which is why UUP.US on 3 and 2 no longer counts toward the eight. Under those
rules this payload reads: median 0.87 over 7 of 8 symbols, own noise 2.4, NOT
a supported reading. See CRITERIA's probe evidence note.**

## What the same afternoon did to the other branch

Running the collector's own intraday check across every published session, which
had never been done for more than two of them at once:

| session | subscribed | symbols within one percent | median absolute difference |
| --- | ---: | ---: | ---: |
| 2026-08-14 | 37 | 0 of 37 | 70.95% |
| 2026-08-17 | 50 | 1 of 50 | 88.43% |
| 2026-08-18 | 50 | 0 of 50 | 90.05% |
| 2026-08-19 | 73 | 0 of 73 | 90.0% |

[the 2026-08-19 row was taken by the 07:00 catch-up on 2026-08-20 and the 08:45
packet read it straight back out of runs/2026-08-19/verify_intraday.json. It was
recorded only on the architecture page until 2026-08-29, which is the wrong home
for a reading: that page describes the machine, this document is the diagnosis.]

[corrected 2026-08-19: written the same afternoon with a 2026-08-13 row reading
"38 | 0 of 38 | 69.77%", and with the sentence below saying BOTH sessions this
document called good. 2026-08-13 is not a premarket session and is removed; the
sentence is about 2026-08-14 alone.]

The shortfall is in every published premarket session, including the one this
document called the session that looks right. It looks right only for SPY, and
only by accident of which direction it is wrong in: on 2026-08-14 the collector
reported 373.88%
MORE SPY volume than EODHD's own bars for the same minutes, not less.

That was already visible in the decisive comparison table above and was read as
evidence about which side is stable. It is more than that. A collector that
reports thirteen times the vendor's TLT and ninety five times its DIA on one
morning, and a tenth of both on the next, is not a starved collector. It is a
collector that is wrong in both directions, and the subscription count was the
only difference anybody had noticed between the two kinds of wrong.

## Mechanisms this pass rules out

- **Progressive throttling inside a session.** Trades per hour of the ET
  window, from the bars: 2026-08-14 at 37 subscriptions ran 38,059 then 102,353
  then 50,782; 2026-08-17 at 50 ran 8,758 then 18,030 then 6,604; 2026-08-18 at
  50 ran 11,804 then 15,510 then 9,122. The fifty symbol sessions are down by
  roughly the same factor in the FIRST hour as in the last, and the shape of the
  three curves is the same. Nothing decays, so nothing is being throttled as the
  hold lengthens. Whatever separates the sessions is present from the first
  minute of the window.
- **Dark pool volume counted on one side only.** The bar schema carries a
  dark_pool_volume field. It is 0.0 in every bar of both sessions checked, whole
  file totals, so consolidated prints arriving unattributed cannot be closing or
  opening any part of the gap. It also means a recorded column has never once
  been populated, which is worth knowing separately from this question.

## What the probe could not control for

Two differences between the probe and a morning survive, and the probe was run
under both of them because the power outage moved it.

- **The tape.** The probe ran 09:35 to 10:01, after the open. The defect appears
  from 07:20 to 09:25, premarket. Delivery could differ by session type.
- **The hold.** Arms are 120 seconds. The collector holds one subscription for
  about two hours. The hourly counts above argue against decay, but they measure
  the collector's own sessions rather than a controlled pair.

The probe's own docstring anticipated the first of these and asked for a
premarket confirmation of a POSITIVE result. This is a negative result that
contradicts the session evidence, which is the case that needs the premarket run
more, not less. Re running the identical script premarket changes exactly one
variable and is the next measurement.

## The one clean reading nobody has taken

Every socket against bars comparison so far has the collector in the path, on a
morning nobody controlled. The probe window is the first case where a known
subscription size, a known symbol list and a known clock window can be compared
against EODHD's own bars for the same minutes with no collector involved.

It could not be taken today. EODHD's 1m intraday bars for 2026-08-19 return zero
rows at 10:05, while the same clock window on 2026-08-18 and 2026-08-17 returns
27 rows each, so the vendor has not published the current session yet. The
comparison is a fetch of eight symbols tomorrow against
data/socket-cap-probe-2026-08-19.json, which already holds per symbol share
counts per arm.
[corrected 2026-08-20: it has been taken. The section title is left as it was
written because it was true then. The reading, and the arithmetic error it went
through first, are the last section of this file.]

Until that lands, note the order of magnitude it is likely to show. The probe's
arm A carried SPY at about 3,888 shares a minute and arm B at about 4,984, while
EODHD's bars put SPY at 225,752 shares in the 09:35 minute of the previous
session. If tomorrow's fetch confirms that shape, the socket is delivering a
small percentage of the consolidated tape at BOTH subscription sizes, which is
the venue subset possibility this document pre registered as the next place to
look, and it would make the shortfall a property to calibrate against rather
than a bug to fix. The over reporting on 2026-08-14 would still need its own
explanation, because a venue subset cannot deliver more than the whole.

## What is no longer blocked, and what still is

The rotation bands stay blocked. The delivery gate data/UNVERIFIED stays where it
is. What has changed is that the fix under consideration is no longer
"subscribe to fewer names": the probe says that would buy nothing.


# The run history behind every reading above, 2026-08-19

Everything above compares volumes without ever asking how many collector runs
produced them. A morning that was refused and restarted covers its window in two
pieces with a gap between, and that alone could account for a shortfall. Two
independent records answer it, and they disagree about which sessions they can
speak for.

## What each source can and cannot say

data/job-status.jsonl was born 2026-08-14 at 12:24, hours after that morning's
window closed, and its first record of any kind is the calendar guard. The
collector step was not wrapped in it until 2026-08-15. **There is therefore no
job_status record for the collector on 2026-08-13 or 2026-08-14, and there
cannot be one.** The question this section was asked to answer assumed both
mornings were covered; only 2026-08-17 is.

data/premarket/{day}-stats.jsonl is the collector's own sidecar, one line per
run, and it does cover both. It is untouched by the two defects fixed on
2026-08-19: a refused run wrote only its marker, and neither of these mornings
was refused, so nothing is missing from what it recorded here.

## The history

| session | runs | non zero exits | refusals | window each run covered |
| --- | ---: | ---: | ---: | --- |
| 2026-08-13 NOT A PREMARKET SESSION | 3 (sidecar) | not recorded | none recorded | evening runs finishing 20:15, 20:35, 20:56 |
| 2026-08-14 | 1 (sidecar) | not recorded | none recorded | one connection, finished 09:25:00 |
| 2026-08-17 | 1 | 0 | 0 | 07:20:01 to 09:25:00, 7,498s, one connection, no reconnect |
| 2026-08-18 | 2 | 1 | 1 | 07:20:02 to 08:50:51 REFUSED, then 08:55:09 to 09:25:00 |
| 2026-08-19 | 2 | 1 | 1 | 08:16:51 to 08:35:28 REFUSED, then 08:37:14 to 09:25:00 |

And what the tape itself covered, read from the bars rather than from either
record:

| session | bars | symbols | first bar | last bar | trades | shares |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| 2026-08-13 NOT A PREMARKET SESSION | 1,810 | 38 | 13:32 | 20:00 | 270,086 | 52,063,236 |
| 2026-08-14 | 2,155 | 38 | 07:20 | 09:24 | 191,194 | 26,333,845 |
| 2026-08-17 | 3,102 | 50 | 06:26 | 09:24 | 33,393 | 1,310,492 |
| 2026-08-18 | 3,231 | 50 | 15:59 | 09:25 | 36,444 | 1,592,611 |
| 2026-08-19 | 1,995 | 73 | 07:21 | 09:24 | 54,349 | 2,319,288 |

## What the history settles

**Neither morning the comparison rests on was interrupted.** 2026-08-17 is a
single run, exit zero, one connection, no reconnect, covering 07:20:01 to
09:25:00 without a gap, and it carries the 88.43% shortfall. 2026-08-14 is a
single run on its own sidecar, one connection, zero reconnects, and it carries
the reading that looked right. A refusal or a restart cannot account for the
difference between them because neither of them had one.

**A refusal does not move the shortfall.** 2026-08-18 was refused at 08:50:51
and restarted, and its median absolute difference is 90.05% against 88.43% for
the uninterrupted 2026-08-17. Two mornings at fifty subscriptions, one clean and
one broken in exactly the way that was supposed to explain the gap, differ by
about a point and a half.

So by the test this section was set: both were single clean runs, the
subscription hypothesis is dead, and the probe carries the whole question. That
agrees with what the probe measured independently, which is worth having as two
findings rather than one.

## Two things the history exposes that nothing above accounted for

**2026-08-13 is not a premarket session.** Its bars run 13:32 to 20:00, which is
regular and after hours trade, and its three sidecar records are evening runs.
It appears in the table above the way the other mornings do and it is not
comparable to them. Its 1,574 recorded messages also cannot have produced its
270,086 trades, so the run that wrote most of its bars recorded no stats at all.
Any conclusion resting on 2026-08-13 should be re read.

**The replay predates the window guard on 2026-08-17 too.** Its first bar is
stamped 06:26, an hour before the collector subscribed, and 2026-08-18's is
stamped 15:59 of the previous afternoon. Both are the vendor's replayed last
trade per symbol, and both are inside the volumes every reading above is
computed from. The guard that refuses them landed on 2026-08-18 and proved
itself on 2026-08-19; every session before that carries them.

The 73 symbols on 2026-08-19 are not an error. Discover reran at 08:21 after the
outage and the second collector run used the new list, so the day's file is the
union of two watchlists.

# The next measurement is the off exchange question

The probe answered the cap question and the run history closes the restart
question, which leaves one hypothesis this document pre registered and never
tested: that EODHD's trades websocket carries a venue subset while its intraday
bars are consolidated. If it does, the shortfall is a property to calibrate
against. If instead the feed delivers off exchange prints and the collector
discards them, it is a bug, and dark_pool_volume being 0.0 in every bar the
project has ever written is the symptom.

Those two are distinguishable and the probe now measures them first.

## What the collector recognises today

Read from _handle_message: it takes s, p, v, t, dp and ms off a trade message
and nothing else. **It reads no condition code of any kind.** Its only off
exchange signal is the dp boolean, and dp has never once been true: the
dark_pool_volume column it feeds is 0.0 in every bar of every session file.

That is one fact with two possible causes, and they call for opposite responses.

## What the probe now reports

Per watched symbol, three numbers rather than two: total messages, messages the
collector's own rule would call an off exchange print, and the vendor's figure
for the same minutes. Plus a census of every key the feed sent on a trade
message, split into the six the collector reads and everything it ignores, and
every code-like value with a count.

The third number is the vendor's SHARES, not its trade count. EODHD's 1m
intraday bar is timestamp, gmtoffset, datetime, open, high, low, close and
volume, checked 2026-08-19: it publishes no trade count, so there is nothing to
compare a message count against. The substitution is named in the tool's own
output rather than made quietly.

It is also a separate command. The vendor does not publish a session until it is
over, and the probe runs premarket, so its own window is unreadable at the moment
it finishes. `--compare FILE` does the fetch the following session and costs one
intraday call per watched symbol, which is the only quota this tool has ever
spent.

## How the answer reads

- No flagged print, no ignored code-like key, and a socket share far below the
  vendor: the trades stream omits off exchange volume. Structural, and no change
  to the collector reaches it. The shortfall becomes a calibration.
- A flagged print, or a code the parser ignores, together with a socket share
  far below the vendor: the feed delivers the volume and the parser drops it.
  That is a bug, dark_pool_volume empty everywhere is its fingerprint, and it is
  fixable.
- A socket share near the vendor's: there was never anything to find and every
  reading above needs re examining.

One guard on all of it. A probe result written before this census carries no
census key, and a report that read that absence as "the feed sent nothing" would
be this document's own recurring mistake made by the tool built to catch it. The
absence prints as NOT MEASURED.


# The replay, measured, 2026-08-19

Every reading above was computed over bars that include whatever the
subscription replayed. This measures how much that was, and re runs the
comparison without it, so an over count and an under count can be told apart
rather than averaged into one ratio.

## How much arrived before the collector subscribed

| session | first bar | subscribed at | source of that time | bars before it | their share of session volume |
| --- | --- | --- | --- | ---: | ---: |
| 2026-08-14 | 07:20:00 | 07:20:00 | CRITERIA intended start, NOT an observation | 0 of 2,155 | 0.00% |
| 2026-08-17 | 06:26:00 | 07:20:01 | job_status, first run | 67 of 3,102 (2.16%) | 6,123 of 1,310,492 (0.47%) |
| 2026-08-18 | 2026-08-17T15:59:00 | 07:20:02 | job_status, first run | 71 of 3,231 (2.20%) | 14,701 of 1,592,611 (0.92%) |

The 2026-08-14 zero is a limit of the measurement, not a finding. That session
has no job_status record and no subscriptions file, so the only subscription
time available is the configured 07:20, and its first bar is stamped exactly
07:20. Replay landing inside that minute is invisible at bar granularity. The
row says the audit found nothing there, not that nothing was there.

Most of what the other two sessions carry is not an hour old either. Splitting
the pre subscription bars by whether they fall in the subscribe minute itself:

| session | same minute as subscribe | genuinely earlier | oldest |
| --- | ---: | ---: | --- |
| 2026-08-17 | 20 bars, 4,656 shares | 47 bars, 1,467 shares | 06:26:00 |
| 2026-08-18 | 23 bars, 10,325 shares | 48 bars, 4,376 shares | 2026-08-17T15:59:00 |

So the genuinely stale replay is 1,467 shares on 2026-08-17 and 4,376 on
2026-08-18: 0.11% and 0.27% of those sessions.

## The comparison, both ways

One intraday fetch per symbol, two comparisons out of it, over the minutes both
sides carry.

| session | median abs diff, all bars | replay excluded | aggregate socket/vendor, all bars | replay excluded |
| --- | ---: | ---: | ---: | ---: |
| 2026-08-14 | 70.95% | 70.95% | 3.826 | 3.826 |
| 2026-08-17 | 88.43% | 88.36% | 0.103 | 0.103 |
| 2026-08-18 | 90.05% | 89.71% | 0.094 | 0.094 |

Per symbol, on the three ETFs present in all three sessions:

| symbol | 08-14 all | 08-14 excl | 08-17 all | 08-17 excl | 08-18 all | 08-18 excl |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SPY.US | 373.88% | 373.88% | -92.11% | -92.11% | -94.52% | -94.48% |
| QQQ.US | 1127.37% | 1127.37% | -92.60% | -92.56% | -93.13% | -93.04% |
| TLT.US | 1269.79% | 1269.79% | -89.22% | -89.24% | -89.24% | -89.37% |

## The verdict, and it is not the two mechanism one

**Replay is not the over counting mechanism.** Excluding every pre subscription
bar moves 2026-08-14's aggregate from 3.826 to 3.826, which is to say by
nothing, because that session has nothing to exclude at this granularity. On the
two sessions where replay is measurable it is worth about half a point of median
absolute difference and about a thousandth of the aggregate ratio. A mechanism
carrying 0.11% of a session's volume cannot produce a 3.8x over count.

So the two mechanism reading the audit was set up to test does not survive its
own measurement. What remains is:

- One session over reporting by 3.8x aggregate, up to 12.7x on TLT, unexplained.
- Two sessions under reporting by about 10x, consistently, which is what the off
  exchange question is for.
- Replay, real, measurable, and too small to be either of them.

**No collector change explains the swing either.** The only commit touching
collect_premarket.py between the two sessions that landed before 2026-08-17's
run is the package move, which created the file at its existing content. The one
that changed logic landed at 16:03 on 2026-08-17, after that morning's window
closed, and touched status frames only. Nothing in the volume path moved.

The probe therefore still owns the under count, and the over count now has no
candidate mechanism at all.

## What is recorded from here on

The audit above had to reconstruct the replay from a subscription time held in a
different file, and for one of the three sessions that file does not exist. That
is fixed rather than left as a technique.

The collector no longer discards an out of window trade. It aggregates it into a
row tagged `replay: true` with the reason beside it and writes it to the same
bar file, and read_bars_file, which every consumer goes through, filters those
rows out of the bars it returns and counts them into `replay_rows`,
`replay_volume` and `replay_first_et` instead. So the evidence is in the file
and can never reach a volume total.

The packet carries the two apart and never collapses them.
`collector_window_observed` reports `first_bar_et` from real bars only, and
`contains_replay`, `replay_rows`, `replay_volume` and `replay_first_et` beside
it. Each candidate carries `pm_window_intended_start` next to `pm_window_start`,
with `pm_window_start_source` saying which is which, and `pm_rvol_basis`
numerator_source now names the window the numerator actually covers with the
scheduled one in brackets rather than quoting the schedule as though it were an
observation.

Null on all of it means a file written before the tag existed, which is not
zero: the sessions in the tables above folded their replay into ordinary bars,
and it is not recoverable from the file alone.
# The clean reading, taken 2026-08-20

The comparison the section above said was owed is done. Eight intraday calls
against data/socket-cap-probe-2026-08-19.json, covering 09:35 to 10:01 ET, with
no collector anywhere in the path: a known subscription size, a known symbol
list and a known clock window against EODHD's own consolidated bars for the same
minutes.

## The denominator was wrong until the moment before it was read

The 2026-08-20 review filed this at high severity without verifying it, and it
was real. compare_to_vendor selected every one minute bar that overlapped an arm
AT ALL and then counted each of them WHOLE. An arm is 120 seconds. An arm that
does not begin on a minute boundary overlaps three bars, so 180 seconds of tape
were charged against 120 seconds of socket.

It is not "about 1.5x". Every one of the eight arms in this file started between
one and thirty four seconds into a minute:

| arm | started | seconds into the minute | whole bars charged |
| --- | --- | ---: | ---: |
| A1 | 09:35:01 | 1 | 3 |
| B1 | 09:38:32 | 32 | 3 |
| A2 | 09:42:02 | 2 | 3 |
| B2 | 09:45:33 | 33 | 3 |
| A3 | 09:49:03 | 3 | 3 |
| B3 | 09:52:33 | 33 | 3 |
| A4 | 09:56:04 | 4 | 3 |
| B4 | 09:59:34 | 34 | 3 |

Twenty four bar minutes charged where sixteen were listened to, on every arm,
exactly 1.5x. Each bar now contributes only the fraction of itself the arm
covered, which sums to seconds/60 whatever the alignment. Pro rating spreads a
bar's volume evenly across its minute, which is this tool's assumption and not a
measurement, and only the two end bars of an arm are ever partial. Every
percentage below would have read two thirds of itself yesterday, and the
guidance printed under the table reads "far below 100%" as evidence of a defect.

## The reading

Split by arm, because a single blended percentage cannot answer an A/B. The
flagged column reads `not rec` for a reason given under the table, and the
comparison was run before that column was fixed: it printed a measured looking
zero in all sixteen rows.

| symbol | arm | socket msgs | flagged | socket shares | vendor shares | socket % |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| SPY | A | 580 | not rec | 28,543 | 914,854 | 3.12% |
| SPY | B | 544 | not rec | 27,554 | 807,986 | 3.41% |
| QQQ | A | 2,342 | not rec | 130,849 | 1,766,454 | 7.41% |
| QQQ | B | 2,863 | not rec | 172,133 | 1,557,379 | 11.05% |
| IWM | A | 413 | not rec | 23,796 | 543,265 | 4.38% |
| IWM | B | 307 | not rec | 13,960 | 483,844 | 2.89% |
| DIA | A | 223 | not rec | 10,869 | 373,985 | 2.91% |
| DIA | B | 164 | not rec | 8,522 | 196,012 | 4.35% |
| TLT | A | 223 | not rec | 54,767 | 1,635,123 | 3.35% |
| TLT | B | 164 | not rec | 44,098 | 1,432,395 | 3.08% |
| USO | A | 32 | not rec | 3,057 | 113,016 | 2.70% |
| USO | B | 41 | not rec | 2,643 | 128,190 | 2.06% |
| UUP | A | 3 | not rec | 3,265 | 62,424 | 5.23% |
| UUP | B | 2 | not rec | 1,994 | 16,550 | 12.05% |
| VIXY | A | 83 | not rec | 5,471 | 164,678 | 3.32% |
| VIXY | B | 72 | not rec | 5,454 | 161,805 | 3.37% |

Arm A subscribed to 8 symbols, arm B to 50. Weighted across all eight symbols,
arm A delivered 4.68 percent of the consolidated tape and arm B 5.78 percent.
The median per symbol share is 3.33 percent for A and 3.39 percent for B. The
per symbol B/A ratio has a median of 1.05, a minimum of 0.66 and a maximum of
2.30, and the vendor totals differ between the arms only because each arm B leg
sits three and a half minutes later in a decaying tape than its arm A partner.

## What it settles

**The cap is innocent, now against the vendor's own bars rather than against
itself.** The internal A/B on 2026-08-19 already said the capped arm was not
starved. This is the independent confirmation, and it is stronger: the capped
arm delivered marginally MORE of the tape than the small one, on the symbols
with enough messages to mean anything. Subscribing to fewer names buys nothing.
That fix is closed as a candidate.

**The socket delivers a few percent of the consolidated tape at any
subscription size.** All sixteen readings fall between 2.06 and 12.05 percent.
This is the order of magnitude the section above pre registered as likely, and
it is the same order as the roughly tenfold under count the whole document is
about. A collector that hears three percent of the tape and reports it as
premarket volume is not broken; it is reporting a venue subset as though it were
the market.

**Nothing at all is known about off exchange prints in this window, and the
tool said otherwise.** The flagged column was read as
`run.get("off_exchange", {}).get(symbol, 0)`, which returns 0 for a run that
HAD the counter and saw nothing and for a run that never had the counter, and
these runs never had it. The comparison published a flagged column of zero for
every symbol in both arms, and zero flagged prints is precisely the reading
that would close the fork below. It now prints `not rec` and says why. What IS
known, from a different source, is that dark_pool_volume is 0.0 in every bar
row of every session this project has written; that is the collector's own
files, not this probe's arms.

## What it does not settle, and what will

The printed guidance forks on whether an IGNORED condition code marks those
prints. A share far below 100 percent with no flagged prints AND no ignored code
means the trades stream simply omits off exchange volume, which no collector
change reaches and which would make the shortfall a property to calibrate
against. The same share WITH an ignored code means the parser is dropping volume
the feed delivered, which is a bug and is fixable.

**This file cannot answer either side of it.** Its runs carry arm, counts,
cycle, messages_total, refused, replayed, seconds, started_at, status,
subscribed and volume, and nothing else. `off_exchange`, `off_exchange_volume`,
`census` and `keys_seen` were all added to the probe AFTER 2026-08-19, so the
payload holds no condition code evidence and no `dp` evidence either. The fork
is open on the evidence, not closed by it, and until 2026-08-20 the tool
reported it as closed.

The 2026-08-21 firing records the census, and it records it on a PREMARKET tape,
which is the tape the defect appears in rather than the 09:35 regular hours tape
everything above was measured on. Both of the open questions therefore land on
the same run.

## What is still blocked

The rotation bands stay blocked. data/UNVERIFIED stays where it is. What has
changed since the section above is that the shortfall now has a measured size at
both subscription sizes, taken with no collector in the path, and one of the two
remaining mechanisms is scheduled to be tested rather than argued about.

# The capture rate, per symbol, 2026-08-21

The four sections above chase one question: why does the socket disagree with
the vendor's own bars. This section asks a different one that nobody had asked,
and it is the one that decides whether the project can move.

**Not "why is the numerator small" but "is it small by a STABLE amount".** A
shortfall that is a stable property of a symbol can be divided back out of an
RVOL numerator. A shortfall that is noise cannot, whatever its cause. Those
have opposite consequences and no reading above separates them.

Nothing on disk could answer it. verify_against_intraday computed a per symbol
collector volume and vendor volume on every session it ran and persisted
neither, keeping the session summary. A session aggregate says how much of the
tape the socket heard on average and is silent about dispersion. The function
keeps `volume_by_symbol` now, and the six collected sessions were re-measured
against the vendor to backfill it: 297 intraday calls, no collector change,
`doc/research/collector-capture.json`.

## There are two regimes, and averaging them is what made this look chaotic

| session | collector over vendor | symbols |
| --- | ---: | ---: |
| 2026-08-13 | 1.4926 | 38 |
| 2026-08-14 | 3.8257 | 37 |
| 2026-08-17 | 0.1028 | 50 |
| 2026-08-18 | 0.0938 | 50 |
| 2026-08-19 | 0.0862 | 73 |
| 2026-08-20 | 0.0908 | 29 |

The document's own verdict rests on the collector being "wrong in BOTH
directions", and it cites 2026-08-14 at 3.83 times against 2026-08-17 at minus
88 percent as though they were two readings of one phenomenon. They are not.
The first two sessions over report and every session from 2026-08-17 sits in a
band of 0.086 to 0.103. Four consecutive sessions inside two percentage points
is not a confused instrument.

That does not explain the early over count, and this section does not try to:
2026-08-14 carried the known vintage defect and the replay measurement is in
the section above. What it does is stop the early sessions contaminating every
statistic computed over "all sessions", which is what they had been doing.

## The share is stable per symbol, which is the finding

Restricted to the four sessions from 2026-08-17, over symbols measured on three
or more of them:

| | all six sessions | the four clean sessions |
| --- | ---: | ---: |
| symbols measured 3+ times | 32 | 25 |
| median per symbol max/min spread | 3.53 | **1.48** |
| p75 spread | 88.08 | 2.22 |
| symbols varying by less than 2x | 11 of 32 | **18 of 25** |

The liquid names are tighter still: AXTI 1.2, TLT 1.2, NBIS 1.2, MU 1.4,
BABA 1.4, QQQ 1.4, INTC 1.4, SPY 1.5, IWM 1.5, LITE 1.5. The wide ones are thin
names where a session turns on a handful of prints.

**So the shortfall is calibratable.** That is a conclusion the readings above
could not reach, not because they were wrong but because the rows they needed
were being thrown away.

## What it costs, in names

pm_rvol divides collector volume by a baseline `collect/baseline.py` builds
from the vendor's 1m intraday bars. Two tapes. The published RVOL is therefore
understated by about 1/f, roughly nine times, and the [Day setup] floor of 1.5
is applied to a number that cannot reach it.

Six mornings, 62 candidates, **zero day eligible, ever**, [2026-08-21: still exactly true, and now also a measure of the cost: re-read against Alpaca full SIP, those six mornings would have held twenty four names instead of six. See DECISIONS 2026-08-21 eighth.] and 19 of the 62
failed on the RVOL line alone. Correcting each candidate by the capture rate
measured for its own symbol:

| session | candidates with an RVOL | clear 1.5 as published | clear 1.5 adjusted | day eligible now | day eligible adjusted |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-08-17 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-18 | 11 | 2 | 5 | 0 | 0 |
| 2026-08-19 | 10 | 0 | 1 | 0 | 0 |
| 2026-08-20 | 10 | 2 | 9 | 0 | **6** |

The six on 2026-08-20 are FUTU, MSTR, ASST, BLSH, COIN and MARA, each of which
had already cleared price, gap, market cap and the prior session high. On
2026-08-18 and 2026-08-19 the corrected names still fail other lines, so the
correction does not manufacture a watchlist. It unblocks one line, and on one
of four sessions that was the only line left.

## What was and was not done with this

**[corrected 2026-08-21: this section said the measurement changes no decision.
That was true for about twenty five minutes. The owner read it and instructed
the correction, and commit a62429b made day_eligible depend on it. Both
identifiers it names are also gone: `scan.rvol_capture_adjusted` became
`scan.capture_correction_report`, and the claim became
`claim_both_volume_ratios_divide_the_same_tape`. The original text is kept
below because the LINE it draws is the part worth rereading, and the entry
under it records where that line actually fell.]**

`scan.capture_correction_report` publishes the raw ratio beside the corrected
one, the capture share used and where it came from, the names the correction
carried across the volume floor, and separately the names that then reached the
day watchlist, into the packet and the gaps.

**It changes decisions, on the owner's instruction.** Both volume ratios divide
`pm_volume_consolidated`, so `day_eligible` depends on the capture share.
`claim_both_volume_ratios_divide_the_same_tape` holds the arithmetic through
the real functions, that `pm_volume` still carries the observation, and that a
symbol the check measured uses its own share rather than the default.

The original text, kept because the distinction it draws is right and only its
verdict was overtaken:

> `scan.rvol_capture_adjusted` publishes the adjusted number, the capture share
> used, and the names the correction would carry, into the packet and the gaps.
> **It changes no decision.** `day_eligible` is untouched, because whether to
> correct a live screen is a threshold question and belongs to the owner.

What this also does is make the gate table say something. data/UNVERIFIED asks
a human to watch one real morning before going live, and until 2026-08-21 that
table showed an RVOL column with no way to tell an instrument reading from a
quiet market. It now prints the socket volume, the capture share, the estimate
and the baseline median in that order, so both divisions can be done by hand on
the page. That is a second correction: the table stopped reconciling on the
morning the estimate landed and said nothing about it, which is the failure
this whole file exists to prevent, committed by the fix rather than by the
defect.

## The 2026-08-21 probe: one fork closed, the other still open

It ran at 06:30 on a premarket tape, which is the tape the defect appears in
and the reason it was armed for a morning rather than taken by hand again.
Twenty eight minutes, eight cycles, one connection drop that cost arm A its
first cycle. It spent no quota.

**On the cap question it says nothing, and that is the finding.** The whole run
carried 123 trade messages across eight symbols. IWM printed a B/A of 0.14 off
49 messages against 9. UUP printed 0.00 off one against none. TLT printed 3.37
off two against nine. Not one watched symbol reached 20 messages on both arms,
so there is no ratio here to take a median of, and the run is refused as NO
READING rather than reported as 0.58.

That number, 0.58, is what the probe printed on the morning, under the sentence
"a ratio well below 1 means it does, and the fix is to subscribe to fewer
symbols". Beside 2026-08-19's 0.87 on 8,056 messages it would have read as the
cap biting in premarket and not in the session. The entire difference between
the two runs is that one had 65 times more tape.

**What the premarket tape can and cannot support is itself worth recording.**
This probe compares message RATES, and the premarket rate for eight liquid ETFs
before 07:00 is a message every few seconds at best. Twenty eight minutes of it
is not enough for a rate comparison, and no arrangement of cycles inside the
window before the collector starts changes that by much. The question can be
answered on a regular hours tape after 09:25, which is where 2026-08-19's
answer came from, or not at all. Neither run has answered it on the tape the
defect lives on.

## The off exchange fork, answered

The census did work, and it is the half of this run that pays for it.

Every one of the 123 trade messages carried `c=[]`, an EMPTY condition list,
and `dp=False`, an explicit not a dark pool print. Zero prints were flagged by
the collector's own rule, on every symbol, in both arms. The keys the feed sent
were s, p, v, t, dp, ms and c, and the only one the collector ignores is c,
which was empty every time.

So the fork this file has carried since 2026-08-19 closes on the structural
side: **the trades stream does not mark off exchange prints, it omits them.**
There is no condition code being dropped by the parser, because there is no
condition code. dark_pool_volume is 0.0 in every bar the project has written
because the feed never says otherwise, and no change to the collector reaches
the missing volume.

That makes the capture calibration the whole answer rather than a stopgap, and
it is the answer already shipped: CRITERIA [Collector] premarket_capture_rate
with the per symbol measurement from doc/research/collector-capture.json.

**The honest size of this evidence.** 123 messages, one premarket window, eight
ETFs. It is 123 out of 123, which is why it reads as an answer rather than a
hint, but the census has never run on a rich tape: the 8,056 message run
predates it. A census on a regular hours tape would cost nothing but socket
time and would settle it past argument. Until then this is one clean sample,
small, and unanimous.

The probe also stopped naming a parser fix underneath that output. It used to
print "a code under IGNORED that marks an off exchange print is the fixable
case" beneath a census of c=[] and dp=False, which pointed its only reader at a
change that does not exist. A value that says nothing is here is the feed
answering, not a code being ignored, and the two now print differently.

## The compounded shortfall, as one number

This file and CRITERIA between them have published two fractions and left the
reader to multiply. They are now measured per row and the product is stated
here so nobody has to.

**The socket carried a median 0.0296 of the true premarket tape. About one
share in thirty four.** Range 0.0087 to 0.3334 over 24 rows and two sessions,
a spread of 38 fold.

| | low | median | high |
| --- | ---: | ---: | ---: |
| feed capture, on the socket's own 07:20 window | 0.0288 | 0.0948 | 0.4231 |
| window share, 07:20 window over the 04:00 session | 0.1562 | 0.3552 | 0.9779 |
| **compounded, socket over true premarket** | **0.0087** | **0.0296** | **0.3334** |

Per session: 2026-08-20 ran 0.0144 to 0.3334 with a median of 0.0350;
2026-08-21 ran 0.0087 to 0.0873 with a median of 0.0268.

**Multiplying the two published medians gives 0.0337 and the rows give 0.0296.**
The two fractions are not independent, so the product of the medians is not the
median of the products, and a reader doing the multiplication by hand would get
a different answer from the one the data gives. That is the reason this section
exists rather than a sentence pointing at the other two.

Both fractions are measured on the same rows over the same windows, from
Alpaca full SIP, by night/true_volume.py. Neither is a seed.

## What is still open

Whether the socket cap starves delivery ON A PREMARKET TAPE. Both runs of the
probe fail to answer it: 2026-08-19 on the rate median its own dispersion
swallows, 2026-08-21 on a tape too thin to produce a median at all. What
carries "the cap is innocent" today is the vendor comparison, 2.1 to 12.1
percent at both subscription sizes, and the fact that fifty symbols at fourteen
times the collector's rate lost no symbol. Both were measured at 09:35 on a
regular hours tape. Neither has been repeated before 07:20.

**The capture measurement holds regardless**, because it is a measurement of
the ratio between the two tapes and not of the cause, and it is what the live
screen now divides by.

One caveat on the numbers, stated rather than buried. 2026-08-20 compared 29
symbols against 49 carrying bars, because intraday had not fully published when
this ran. The other twenty are unmeasured for that session, not measured and
agreeing.
