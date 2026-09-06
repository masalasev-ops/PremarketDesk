# Result: the Alpaca premarket sweep as a fifth discovery prior

Run 2026-09-06 against doc/research/PREMARKET_PRIOR_PREREGISTRATION.md, which
was committed in bcf56dc before src/research/premarket_prior_test.py existed.
The rule, the floor, the K, the arms and the bar are all as pre-registered and
not one of them was changed after a number was seen.

240 sessions fetched, 239 scored, 0 refused by the coverage guard. 1,190
Alpaca requests and ZERO EODHD calls. The sweep cache is under
data/research/premarket-sweep and is gitignored, about 39 MB.

## The bar was cleared, and not narrowly

Mean subscribed recall of gappers at or past 8 percent, per session:

  arm                    mean recall   vs shipped       t    win   lose   sign p
  B shipped                   0.3242
  C K=10       PRIMARY        0.5923      +0.2681   21.27    221      6   0.0000
  C K=5                       0.5452      +0.2210   19.77    220      3   0.0000
  C K=20                      0.5955      +0.2713   19.44    218      7   0.0000
  A alone, floor 50k          0.6026      +0.2784   18.68    209     15   0.0000
  A alone, floor 10k          0.6505      +0.3263   22.05    220      9   0.0000
  A alone, floor 250k         0.4979      +0.1737   11.27    174     36   0.0000

Both pre-registered conditions hold on the primary arm and hold on every
sensitivity: the paired t is 21.27 against a bar of p below 0.05, and the sign
test is 221 wins to 6 losses. Ten slots out of forty five, given to names the
tape says are already moving, take big gap recall from 0.32 to 0.59. Over the
239 sessions that is 822 big gappers the shipped pool missed and the sweep's
top ten caught.

## What this actually says, stated exactly

IT IS NOT A BETTER PRIOR. It is direct observation replacing prediction, and
observation should win. The four shipped priors all describe the PAST: who
reports today, what was in the news overnight, who moved yesterday, who ran
recently. The sweep looks at what is happening this morning. The reason the
project has never done that is not oversight, it is that no EODHD endpoint on
this plan serves the whole universe's premarket before the open.

So the reading is not "the priors are bad". It is that the priors are
being asked to predict something that, three hours before the scan, is already
observable through a vendor this project does not use for selection.

A hand check of one session, 2026-06-16, is what says the arithmetic is sound
rather than a leak: RXT read +14.29 percent at 07:00 and opened +14.37, PURR
read +14.03 and opened +10.62, and the eight below them faded under the 8
percent line by the open. Two of the top ten were genuine big gappers, which
is a believable hit rate and not the perfect foresight a bug would produce.

## AND IT CANNOT BE BUILT ON THIS PLAN

The free Alpaca plan serves the SIP feed for a session that is OVER and
refuses a RUNNING one. doc/ALPACA_PROBE.md measured it: all 46 requests
sweeping 1Min sip bars over a window ending at the wall clock on a live
trading morning returned HTTP 403. At 07:00 on session D, D is running.

The IEX feed, which the free plan does serve live, is not a substitute and was
already measured: 0 bars and 0 shares across the premarket window against SIP's
1,410,664 shares on the same symbol and window. IEX carries about a
twenty fifth of SIP in the regular session and nothing at all before the open.

Rechecked 2026-09-06 while writing this, so the restriction is current and not
carried from an August document: SIP one minute bars come back for every
completed session through 2026-09-04 and the sweep above ran on 240 of them.
What is refused is the session you are standing in.

So the result converts package 5.6 item 4 from a question with nothing under
it into a priced one, and the price has two parts rather than one:

  1. an Alpaca plan that serves SIP on a running session, and
  2. bending hard rule 1 to admit a second vendor into SELECTION

The second is smaller than it sounds and the distinction is worth keeping
sharp. The sweep would choose WHO the collector listens to. Every number that
reaches a report would still come from the EODHD socket and REST, exactly as
today, because the collector is still the only source of the premarket tape a
candidate is priced from. Alpaca would decide who to point the microphone at
and would never be quoted.

## What it does to the cap work

It inverts the conclusion of CRITERIA's cap note, and that is the most
useful thing here.

That note, measured 2026-09-05, said the subscription cap is selection's
binding constraint and that effort spent on tier boundaries is spent at the
wrong end. The first half is now wrong. Moving the cap from 42 to 45, which
was the whole of 2026-09-06's morning, bought 0.0129 of big gap recall.
Swapping ten of those forty five slots for observed movers buys 0.2681, twenty
times as much, out of the same fifty sockets.

The binding constraint was never the number of slots. It is WHICH NAMES fill
them, and every measurement in tier 6 was a rearrangement of a prior that
cannot see the morning it is choosing for. The floor, the freshness split and
the tier 2 ordering each moved nothing for the same reason.

## What was NOT measured, and must not be assumed

  - Whether the shipped pool's names are worth more per slot than the sweep's
    on any question other than big gap recall. The pool is built to find names
    with a CATALYST, and a name moving on no news is not the same object even
    when it gaps as far. Nothing here scores the two on what they did after the
    open, only on whether they gapped.
  - Whether a 07:00 sweep on a live morning would return what the historical
    one returns. It cannot be tested on this plan at all, so the recall above
    is an upper bound on a live implementation and is written as one.
  - Any interaction with the collector's 50 socket ceiling beyond the slot
    arithmetic. A name the sweep adds still has to be subscribed to be priced.
