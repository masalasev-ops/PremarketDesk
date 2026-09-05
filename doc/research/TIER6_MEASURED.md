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

  1. Ask the vendor question nobody has asked. 42 is the socket's 50 less the 8
     context tickers, and probe_socket_cap only ever asked whether 50 starves
     message delivery, never whether the plan allows more than 50. On this
     slope that is the highest value open question in selection, and it costs a
     read of the plan's terms rather than any quota.
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

### 6.10 The cap is the binding constraint, and it is a ceiling not a choice

Recall is still climbing at the 42 cap and the marginal subscription is worth
about 0.005 of big gap recall, flat across the last two steps. That is more
than the entire slot floor question of 6.1 was worth. 42 is the socket's 50
less the 8 context tickers, so the ceiling is a vendor limit. The table, the
extrapolated price of those 8 tickers and the unasked vendor question are in
CRITERIA's cap note and in doc/research/TIER6_MEASURED.md.
