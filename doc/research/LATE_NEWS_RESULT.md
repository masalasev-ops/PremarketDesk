# Result: would a third discovery pass at 08:15 catch anything?

Run 2026-09-06 against the rule and bar in src/research/late_news_test.py's
docstring, committed in c9876f0 before the module had produced a number.
Package 6.3 asked for exactly this before arming the pass.

61 sessions, a systematic one in four across the 240 cached ones, 353
news-feed calls at 5 credits each. The population change from 240 and its
reason are recorded in the module and were decided before any informative
number existed.

## It clears, at about a quarter of 5.5's reach

  names gaining a first story 07:15 to 08:15   mean 83.7 a session, max 178
  big gappers the pool missed and this reaches total 50, mean 0.820 a session
  sessions reaching at least one               25 of 61
  PRE-REGISTERED BAR                           0.5 a session

0.820 against a bar of 0.5. Examples of names it would have reached: MNKD,
MAZE, CRML, CDE, EOSE, EXK, NB, PAAS, NTLA, OGN, BHF, COLL.

THE FIGURE IS A LOWER BOUND. 12 of the 61 sessions hit
[Discovery] news_sweep_max_pages on the late sweep, so their late set is
truncated and every name past the cap is invisible to this measurement. A
session that truncates can only have MORE late names than counted, never
fewer, so the true mean is above 0.820 and the bar is cleared by more than
the margin shown.

## Read it beside 5.5, because the two answer the same question

Package 5.5, the same day, measured the Alpaca premarket sweep at 3.44 big
gappers a session that the shipped pool missed. This is 0.820, about a
quarter of that.

BUT 5.5 CANNOT BE BUILT ON THE CURRENT PLAN and this can. Alpaca refuses a
running session, so its 3.44 is an upper bound on something that needs a paid
plan and a bend of hard rule 1. The 08:15 pass needs neither: it is the same
four priors, the same vendor, the same code, run once more with an hour more
news.

So the ordering for anyone deciding what to do next is: this is the available
quarter, and 5.5 is the priced three quarters.

## What it costs, and the one thing it is not

About 306 credits a day for the third pass's bulk calls, plus its news sweep,
against a measured weekday total near 1,628 of 100,000. A third trigger on
job_discover in tasks/register_tasks.ps1, which is why arming it is the
owner's: it registers a scheduled task.

[Collector] max_pool_reloads is 3 today and that is the handover plus room for
two watchdog reruns. A third scheduled pass consumes one of those, so arming
this without raising the cap trades a repair for a pass. That is a CRITERIA
change and it belongs in the same commit as the trigger, never before it.

IT IS NOT A THIRD CHANCE AT THE SAME NAMES. A name reaching the pool at 08:15
is subscribed at 08:15 and the scan runs at 08:45, so it arrives with about
thirty minutes of tape where a 04:00 name has five hours. Its premarket high
is not comparable, its RVOL numerator covers a fraction of its denominator's
window, and `window_open_at` is what will say so per row. The value here is a
name going from NO tape to some, not from some to more, and any measurement
that later pools 08:15 names with 04:00 names on a volume ratio will be
measuring the clock rather than the market.

## Provenance, including a mistake worth keeping

The first fetch run crashed at its twentieth session on
`api.call_count()`, which does not exist on EodhdClient; the module level
`eodhd.call_count()` does. 178 calls were spent and 19 session files written
before it stopped, and none of that was wasted because the fetch skips what is
already on disk.

The two session smoke test hit the SAME line through its
`index == len(days)` branch and crashed too. It was read as a pass because
only the last eight lines of its output were checked and the traceback was
above them, and because `evaluate` then ran cleanly on the files that had
already been written, which looked like confirmation. A smoke test that
crashes and still writes its output is the worst shape a smoke test can have,
and the reading habit that missed it is the one this project already has a
note about: grep a log for tracebacks, do not tail it.
