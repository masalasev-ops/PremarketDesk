# What tier 6 measured, 2026-09-05

The working notes behind IMPROVEMENT_PLAN's tier 6, moved out of it when that
file reached its 1,500 line cap. The plan keeps a short verdict per item and
points here; CRITERIA.md keeps the tables, beside the keys they are about,
because that is where a threshold's derivation belongs.

Nothing here is a threshold. Every number was measured over the 240 session
replay in data/backtest/sessions after 6.1's four repairs, so the replay no
longer ranks a session on this week's universe and no longer counts a corporate
action as a gap. Every run is cache only and spent no vendor call.

### 6.10 The cap is the binding constraint, and it is a ceiling not a choice

ADDED 2026-09-05, out of the other three. 6.1, 6.2 and the after close crossing
were three different questions that all ended at the same place: what happens
at the cut. So the cut was swept, which nothing had done. SHIPPED, floor 4, 240
sessions, and the table is in CRITERIA's new cap note.

Recall is STILL CLIMBING at 42. The marginal subscription is worth about 0.005
of big gap recall and that figure is flat across the last two steps rather than
decaying, so the cap has not reached diminishing returns anywhere in the
measured range. For scale, the whole slot floor argument of 6.1 was worth 0.004
in total: one more subscription is worth more than that entire question.

WHAT TO DO WITH IT, in the order the evidence supports.

  1. CLOSED 2026-09-05, the same day it was filed. The owner confirms EODHD
     does not allow more than 50, so this is a hard vendor ceiling and not a
     plan tier that could be bought past. Nothing is broken by it: the
     collector is built for the limit, never drops the 8 context symbols, fills
     the rest in discover's ranked order and logs by name whatever does not
     fit. The value of the sweep is therefore mostly NEGATIVE, and that is
     worth keeping: the floor, the freshness split and the tier 2 ordering are
     all rearrangements INSIDE 42 slots, which is exactly why measuring all
     three moved none of them. Effort spent on tier boundaries is effort spent
     at the wrong end.
  2. Price the 8 context tickers deliberately. They cost somewhere near 0.03 to
     0.04 of big gap recall by extrapolation, which is written as an
     extrapolation because it is past the measured range. It is not a pure
     trade either: they feed the market snapshot the report is written against.
     The point is that the price is now known and was not.
  3. Only then revisit the floor and the tiering. Both were measured today and
     neither moved, and both are second order against this.


RUN 2026-09-05, AND THE ARGUMENT DOES NOT SURVIVE ITS OWN TEST. Both
candidates were built as orderings G and H and measured over 240 sessions. The
table is in CRITERIA's new freshness note.

Window position, which is what this item implicitly asks for, is DECISIVELY
WORSE: -0.0159 past 3 percent at a t of -6.45 and -0.0259 past 8 percent at a
t of -4.90, better on 19 sessions and worse on 62. Promoting the evening bucket
is not free. It is a LARGE bucket, 82 names on 2026-09-02 alone, so moving it
into tier 2 dilutes that tier and pushes higher propensity names out of the
cap. The names this item wants reached are reached at the cost of more names
than it gains.

Dropping the split entirely is not distinguishable from the shipped rule,
+0.0027 at 3 percent with a t of 1.86 and +0.0004 at 8 percent with a t of
0.09. Useful to know, because it says the six hour boundary is not doing much
work in either direction, and not a reason to move anything.

news_fresh_hours stays at 6, upgraded from seed to measured. What this points
at is not the boundary but the tier 2 CAP, which 6.1 and the after close
crossing reach from two other directions: three in five gapping after close
reporters are found by the pool and then cut.

### Three subscribed context tickers are read by nothing, found 2026-09-05

Found while asking whether any of the 8 context slots could be freed, once the
owner confirmed EODHD's 50 is a hard ceiling. The answer is better than a trim:
three of the eight are already spending a slot for nothing.

  [Collector] context_symbols   SPY QQQ IWM DIA TLT USO UUP VIXY
  [Scan snapshot] snapshot      SPY QQQ IWM DIA USO, plus VIX.INDX,
                                US10Y.GBOND, US3M.GBOND, DXY.INDX

TLT, UUP and VIXY are subscribed and appear in NO snapshot row, so their bars
are collected and never read. Meanwhile the four rows that are not subscribed
fall through to the end of day feed, and the 2026-09-04 packet shows them
labelled source eod and prior_session_only true: the report printed yesterday's
move for the 10 year, the 3 month, the dollar and the VIX.

IT IS A DOUBLE LOSS. Three of fifty slots produce nothing, worth about 0.015 of
big gap recall on the cap slope measured above, which is three times the whole
slot floor question. And the rates, dollar and volatility rows are a day stale
while a live proxy for each sat subscribed and unread.

THE MECHANISM FOR FIXING IT ALREADY EXISTS AND IS ALREADY USED. wti maps to
USO.US and carries the proxy note "USO is an oil ETF standing in for WTI, EODHD
commodities are not on this plan". Someone subscribed TLT, UUP and VIXY for
exactly that purpose and only USO was ever wired up.

THE THREE ARE NOT EQUALLY WORTH WIRING, measured on premarket bar occupancy
over the four live sessions, which needs no statistics because a ticker that
prints twice in a 325 minute window will not be dense on the fifth morning:

  QQQ 805 bars, SPY 658, TLT 534, USO 463, IWM 327, DIA 144, VIXY 85, UUP 14

  TLT to 10y     134 bars a session. Clear win, live instead of a day stale.
  VIXY to vix    21 a session. Better than stale and thin enough that the row
                 should carry its bar count.
  UUP to dxy     3.5 a session, 2, 2, 8, 2. Not worth wiring. Independently
                 corroborated by the probe evidence note above, where UUP's
                 B/A was one message against none. Better to drop it from
                 context_symbols and take the slot back.

Wiring TLT and VIXY and dropping UUP nets one slot back and turns two stale
rows live. It changes what the report SHOWS, so it is the owner's call and is
recorded here rather than taken.
