# Collector volume, diagnosed

Written 2026-08-18. Findings only. No collector code was changed in this pass.

The nightly writes runs/<date>/verify_intraday.json, the check BUILD_PLAN.md
names as definitive for collector volume: collector bars against EODHD 1m
intraday, identical minutes only. Its first live reading, 2026-08-14, was 0 of
37 symbols within one percent at a median ABSOLUTE difference of 70.95 percent,
and nobody had looked at it. This is that look.

The check reports an absolute median, which discards the most informative bit.
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
| 2026-08-13 (open market) | 38 | n/a | 37,792 | 727 | 2,082,908 |
| 2026-08-14 | 38 | 191,194 | 21,428 | 171 | 1,550,327 |
| 2026-08-17 | 50 | 33,489 | 618 | 5.8 | 32,532 |
| 2026-08-18 | 50 | 36,530 | 573 | 5.3 | 29,410 |

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

Registered as a one time task for 06:20 on 2026-08-19. It spends no quota.

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

## What the same afternoon did to the other branch

Running the collector's own intraday check across every published session, which
had never been done for more than two of them at once:

| session | subscribed | symbols within one percent | median absolute difference |
| --- | ---: | ---: | ---: |
| 2026-08-13 | 38 | 0 of 38 | 69.77% |
| 2026-08-14 | 37 | 0 of 37 | 70.95% |
| 2026-08-17 | 50 | 1 of 50 | 88.43% |
| 2026-08-18 | 50 | 0 of 50 | 90.05% |

The shortfall is in every session, including both sessions this document called
the ones that look right. They look right only for SPY, and only by accident of
which direction they are wrong in: on 2026-08-14 the collector reported 373.88%
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
