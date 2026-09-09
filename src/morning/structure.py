"""The daily context map: where a name sits in its own recent history.

WHY THIS EXISTS, and why it prescribes nothing. Until 2026-09-08 the only two
price levels this desk put in front of a reader were entry_ref and stop_ref,
the premarket high and the premarket low, and they were labelled Entry and
Stop. Those are properties of one morning's premarket session, which is a few
hours of thin trade, and the screen that showed them made no distinction
between a name to be sold at 09:31 and one to be held for a week.

MEASURED ON THE 2026-09-08 PACKET, which is what settled it. Expressed in each
stock's own ATR(14), the published stop sat between 0.14 and 2.44 ATR below the
published entry across ten names: a seventeen fold spread from one rule. That
is because pm_low measures how far the premarket happened to wobble, which is a
function of how thin and how long the window was, and not a property of the
stock at all. Six of the ten stops were inside a QUARTER of one day's normal
range. Past the opening minutes those are not stops; they are near certain
exits on noise.

SO WHY IS THERE NO ENTRY OR STOP HERE. Because nothing in this project's record
supports publishing one. The paper ledger stands at five wins in seventeen at a
median of -1.70 percent, green ranks BELOW yellow and red on excursion, and
entry_ref is reached on 20 of 48 measured rows. An entry level published from
that record is a seed wearing a label. Refusing a breakout rule for having no
measured basis and then substituting an ATR multiple, an R multiple target and
a holding horizon, none of which has one either, is not discipline; it is the
same unmeasured threshold in three pieces.

A MAP IS DESCRIPTIVE AND CANNOT BE WRONG IN THE WAY A LEVEL CAN. It says where
the stock is, not what to do, which is the same boundary the notable movers
section has always held. If a validated entry rule is ever published it comes
from the ledger after the pre-registered judging point, not from a design
decision taken here.

    entry_ref and stop_ref remain, as internal ledger fields. paper_trades
    needs two numbers to book against and they are adequate for that. What
    stopped on 2026-09-08 is printing them to a reader as Entry and Stop. The
    ledger's reference and the reader's advice were the same two numbers only
    by an accident of naming.

WHY THE MAP IS WRITTEN TO picks, added 2026-09-09. Until then it was drawn on a
card and kept nowhere, which made it a decoration rather than an instrument.
Nothing could ask whether a name that gapped out of a 60 session base behaved
differently from one that gapped inside it, because no row recorded which of
those it was. Every field this module measures is now a typed column on picks,
written for the live morning by scan.write_picks and for every session already
in the record by night/backfill_structure.py, both through columns() below so
the two can never disagree about what a field means. See CRITERIA.md [Daily
structure] the columns note, and store._PICKS_LATER_COLUMNS.

    A CLASSIFICATION NEVER TRAVELS WITHOUT ITS INPUTS. gap_type is derived from
    SEED thresholds over measured readings, and every one of those readings is
    written beside it, so a reader who disagrees with where the line sits can
    re-draw it from the same rows rather than take the word. That is the
    catalyst_class rule applied to a second field.

WHAT IT COSTS: NOTHING. attach_daily_history already calls eod once per
candidate, and [Quota costs] prices that call at one credit flat, per call and
not per row. Widening its from date returns three trading years instead of five
weeks for the same one credit, so this whole section is paid for by a call the
morning was already making. See attach_daily_history's history_days note.

EVERY LEVEL IS SPLIT ADJUSTED, and silently getting this wrong is the one way a
map like this misleads. The vendor returns close and adjusted_close on each
row; their ratio back adjusts an older bar onto a later basis, so a high from
before a two for one split is comparable to today's price rather than twice it.
On a name with neither split nor dividend the ratio is one throughout and the
scaling does nothing. A large single session step in that ratio is disclosed by
name and date, because a reader looking at a raw chart will see other numbers
and is owed the reason.

    WHICH BASIS, and this is the part the backfill forced. The vendor computes
    adjusted_close against ITS latest data, so a series fetched today states
    every old bar in today's money. That is right for the morning, whose price
    is also today's. It is wrong for a row dated last November, whose pm_high
    and prior_close are in LAST NOVEMBER's money: a split since then would
    leave the map and the rest of the row on two different scales with nothing
    saying so. basis_factor is how a caller says which session's money it wants
    the levels in, and the backfill passes the adjustment factor of the mapped
    session's own bar. For the morning it is one and nothing happens.
"""

from __future__ import annotations

import statistics
from typing import Any

from core import criteria

_CRIT = criteria.load()


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def basis_factor_of(bar: dict[str, Any] | None) -> float | None:
    """The vendor's adjustment factor on one bar, or None if it has no usable pair.

    Split out so the backfill can read the factor of the session a row is ABOUT
    without knowing how adjusted_series builds one. A bar with no close or no
    adjusted_close has no factor; the caller then leaves the series on the
    vendor's own basis rather than guessing at one.
    """
    if not bar:
        return None
    close = _as_float(bar.get("close"))
    adjusted = _as_float(bar.get("adjusted_close"))
    if not close or not adjusted:
        return None
    return adjusted / close


def adjusted_series(
    bars: list[dict[str, Any]], basis_factor: float | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Back adjust open, high, low and close onto one price basis.

    The factor is adjusted_close / close on each row, which is what the vendor
    already publishes; this only applies it to the other four fields. A row
    missing either number is carried at factor one rather than dropped, because
    dropping it would put a hole in an ATR that reads as a quiet session.

    basis_factor divides every factor before it is applied, which restates the
    whole series in the money of whichever session that factor came from. Left
    None the series stays on the vendor's own basis, which for a series fetched
    this morning is this morning. See the WHICH BASIS note in the header.

    VOLUME IS NOT ADJUSTED. It is a share count, and a share count is not a
    price: the correction that makes a pre split high comparable to today makes
    a pre split volume wrong by the same factor in the other direction. The
    average published from it is therefore an average of what actually traded,
    and a split inside the window is disclosed by adjustment_steps like every
    other one.

    The second return is the dates whose factor stepped by more than
    [Daily structure] max_adjustment_step against the row before. That is the
    signature of a split or a large special dividend, and it is DISCLOSED
    rather than corrected: the correction has already been applied above, and
    the disclosure exists so a reader whose chart disagrees knows why. The step
    is read off the RAW factors, before basis_factor rescales them, because
    rescaling moves every factor by one constant and cannot create or hide a
    step between two of them.
    """
    step_limit = _CRIT.number("daily_structure", "max_adjustment_step")
    out: list[dict[str, Any]] = []
    steps: list[str] = []
    previous_factor: float | None = None
    for bar in bars:
        close = _as_float(bar.get("close"))
        adjusted = _as_float(bar.get("adjusted_close"))
        factor = (adjusted / close) if (close and adjusted) else 1.0
        if previous_factor and abs(factor / previous_factor - 1.0) > step_limit:
            steps.append(str(bar.get("date")))
        previous_factor = factor
        if basis_factor:
            factor = factor / basis_factor
        row: dict[str, Any] = {"date": str(bar.get("date"))}
        for key in ("open", "high", "low", "close"):
            value = _as_float(bar.get(key))
            row[key] = None if value is None else value * factor
        row["volume"] = _as_float(bar.get("volume"))
        out.append(row)
    return out, steps


def _atr(rows: list[dict[str, Any]], sessions: int) -> float | None:
    """Average true range over the last `sessions` completed bars.

    True range and not the plain high minus low, because a gap between one
    close and the next day's range is exactly the movement a gap screen cares
    about and the plain range cannot see it.
    """
    ranges: list[float] = []
    for index in range(1, len(rows)):
        high, low = rows[index]["high"], rows[index]["low"]
        previous_close = rows[index - 1]["close"]
        if high is None or low is None or previous_close is None:
            continue
        ranges.append(max(high - low,
                          abs(high - previous_close),
                          abs(low - previous_close)))
    if len(ranges) < sessions:
        return None
    window = ranges[-sessions:]
    return sum(window) / len(window)


def _extremes(rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    highs = [r["high"] for r in rows if r["high"] is not None]
    lows = [r["low"] for r in rows if r["low"] is not None]
    if not highs or not lows:
        return None, None
    return max(highs), min(lows)


def _sessions_since_close_above(
    rows: list[dict[str, Any]], level: float | None
) -> dict[str, Any] | None:
    """When this name last CLOSED above a level, counted back from the last bar.

    THIS IS WHAT TURNS A LEVEL INTO A FACT. "60 session high 54.20" says only
    where a line is. "60 session high 54.20, last closed above it 118 sessions
    ago" says the name has been under it for half a year, and "no close above
    it in the 760 sessions on file" says something stronger still. The card
    already printed the first and could not print either of the others.

    THE ARITHMETIC HAS A FLOOR AND A READER SHOULD KNOW IT. The level is the
    highest HIGH over the last N sessions, and a close never exceeds its own
    bar's high, so no session inside that window can close above it. The answer
    is therefore never smaller than N, and a name that just made a new high
    comes back with no answer at all rather than with a zero. Null here means
    the level has not been closed above anywhere in the history on file, which
    is the strongest reading of the three and the one a zero would destroy.
    """
    if level is None:
        return None
    for index in range(len(rows) - 1, -1, -1):
        close = rows[index]["close"]
        if close is not None and close > level:
            return {"sessions_ago": len(rows) - 1 - index,
                    "date": rows[index]["date"]}
    return None


def _window(rows: list[dict[str, Any]], sessions: int,
            price: float | None) -> dict[str, Any] | None:
    """The high, the low and where price sits between them, over one window.

    position_pct is a DESCRIPTION and not a score: 0 means price is at the low
    of the window and 100 at the high. It is null when the window is flat,
    because a name that has not moved has no position inside a range of zero.

    Null, with no window at all, when the history is short. A 250 session high
    computed over 30 sessions is not a 250 session high, and a figure that
    quietly means something other than its label is worse than a blank.
    """
    if len(rows) < sessions:
        return None
    window = rows[-sessions:]
    high, low = _extremes(window)
    if high is None or low is None:
        return None
    position = None
    if price is not None and high > low:
        position = round((price - low) / (high - low) * 100.0, 1)
    since = _sessions_since_close_above(rows, high)
    return {
        "sessions": sessions,
        "high": round(high, 4),
        "low": round(low, 4),
        "position_pct": position,
        "from": window[0]["date"],
        "since_close_above": None if since is None else since["sessions_ago"],
        "since_close_above_date": None if since is None else since["date"],
        "since_close_above_reason": None if since is not None else (
            f"no session in the {len(rows)} on file closed above "
            f"{round(high, 4)}, so there is no interval to report"),
    }


def _sma(rows: list[dict[str, Any]], sessions: int,
         price: float | None) -> dict[str, Any] | None:
    if len(rows) < sessions:
        return None
    closes = [r["close"] for r in rows[-sessions:] if r["close"] is not None]
    if len(closes) < sessions:
        return None
    value = sum(closes) / len(closes)
    return {
        "sessions": sessions,
        "value": round(value, 4),
        "price_vs_pct": (None if not (price and value)
                         else round((price - value) / value * 100.0, 2)),
    }


def _average_volume(rows: list[dict[str, Any]], sessions: int) -> dict[str, Any] | None:
    """Mean daily volume over the window, WITH the count it was taken over.

    The count travels with the mean here for the reason it travels with
    avg_volume_20d in scan.py: a field named for twenty sessions that averaged
    three of them asserts a denominator it does not have, and nothing
    downstream can tell. `of` is how many sessions the window actually spans,
    `sessions` how many of those carried a volume at all.
    """
    if not rows:
        return None
    window = rows[-sessions:]
    volumes = [r["volume"] for r in window if r["volume"] is not None]
    if not volumes:
        return None
    return {"sessions": len(volumes), "of": len(window),
            "value": round(sum(volumes) / len(volumes), 1)}


def _consolidation(rows: list[dict[str, Any]], sessions: int,
                   atr: float | None) -> dict[str, Any] | None:
    """The window's whole range said in units of one normal day's range.

    A COILED NAME AND AN EXTENDED NAME ARE DIFFERENT OBJECTS and until this
    landed nothing on the card distinguished them: both showed a position
    inside a range and neither said whether that range was three days wide or
    thirty. Crabel's 1990 work on narrow range days found that a compressed
    range precedes a large trending session about two thirds of the time,
    which is why this is a separate reading from the range position and not a
    restatement of it. Two names can sit at the same position_pct with ratios
    four apart.

    NOTHING HERE ACTS ON IT. It is a ratio of two measured spans, reported so
    the record can one day be grouped on it. See CRITERIA [Daily structure].
    """
    if atr is None or atr <= 0 or len(rows) < sessions:
        return None
    window = rows[-sessions:]
    high, low = _extremes(window)
    if high is None or low is None or not low:
        return None
    span = high - low
    return {
        "sessions": sessions,
        "range": round(span, 4),
        "range_pct": round(span / low * 100.0, 2),
        "ratio": round(span / atr, 2),
    }


def _gap_pct_into(rows: list[dict[str, Any]], index: int) -> float | None:
    """The gap into rows[index]: its open against the close before it.

    Measured the way [Day setup] gap_pct is measured, on the adjusted series,
    so a two for one split between the two sessions reads as no gap rather
    than as a fifty percent one.
    """
    if index <= 0:
        return None
    opened = rows[index]["open"]
    previous_close = rows[index - 1]["close"]
    if opened is None or not previous_close:
        return None
    return (opened - previous_close) / previous_close * 100.0


def _open_to_close_pct(row: dict[str, Any]) -> float | None:
    opened, close = row["open"], row["close"]
    if not opened or close is None:
        return None
    return (close - opened) / opened * 100.0


def _gap_context(rows: list[dict[str, Any]], price: float | None,
                 atr: float | None) -> dict[str, Any]:
    """What the name was doing BEFORE today, and where today's gap sits in it.

    THE FIRST QUESTION EVERY SOURCE ON GAPS ASKS, and this desk had no answer
    for it. A gap out of a four week base and a gap on the fifth straight up
    session are opposite objects and the report described them identically:
    same gap percent, same RVOL band, same catalyst class, same card.

    THE READINGS ARE MEASURED AND THE CALL IS DERIVED, which is the whole
    shape of this function. regime_range_atr, regime_net_move_atr, the recent
    gap count and the run are counts and ratios off the bars. `type` is a
    reading of those against SEED thresholds in CRITERIA, and it is written
    with the numbers that produced it so a reader who puts the line somewhere
    else can. Nothing here is a threshold anything passes or fails.

    THE TWO REGIME CALLS CANNOT BOTH FIRE. A window's net travel cannot exceed
    the range that contains it, so net_move_atr is bounded above by range_atr,
    and the consolidation ceiling sits below the trend floor. Between them is
    "neither", which is most windows and is reported as itself rather than
    forced into one of the two.

    A GAP AGAINST THE TREND IS COMMON, deliberately. It is neither a
    continuation nor an exhaustion of a move it opposes, and inventing a fifth
    word for it would be naming a thing this record has never measured.
    """
    gap_rule = _CRIT.rule("day_setup", "gap_pct")
    regime_n = _CRIT.integer("daily_structure", "gap_regime_sessions")
    recent_n = _CRIT.integer("daily_structure", "gap_recent_sessions")
    prior_n = _CRIT.integer("daily_structure", "prior_gap_sessions")
    coil_max = _CRIT.number("daily_structure", "gap_regime_range_atr_max")
    trend_min = _CRIT.number("daily_structure", "gap_regime_net_move_atr_min")
    run_min = _CRIT.integer("daily_structure", "gap_run_exhaustion_sessions")

    out: dict[str, Any] = {
        "threshold_pct": gap_rule.value,
        "threshold_rule": gap_rule.describe(),
        "gap_pct": None,
        "gap_direction": None,
        "regime": None,
        "gap_vs_regime": None,
        "recent_gaps": None,
        "prior_gaps": None,
        "type": "unknown",
        "type_why": None,
    }

    # ---- today's gap, off the same two numbers the day screen uses
    last_close = rows[-1]["close"] if rows else None
    if price is not None and last_close:
        gap = (price - last_close) / last_close * 100.0
        out["gap_pct"] = round(gap, 4)
        out["gap_direction"] = "up" if gap > 0 else "down" if gap < 0 else "flat"

    # ---- what the last regime_n sessions were doing
    regime: dict[str, Any] | None = None
    if len(rows) >= regime_n and atr:
        window = rows[-regime_n:]
        high, low = _extremes(window)
        first = next((r["close"] for r in window if r["close"] is not None), None)
        last = next((r["close"] for r in reversed(window)
                     if r["close"] is not None), None)
        if high is not None and low is not None and first and last is not None:
            span = high - low
            net = last - first
            regime = {
                "sessions": regime_n,
                "high": round(high, 4),
                "low": round(low, 4),
                "range_pct": round(span / low * 100.0, 2) if low else None,
                "range_atr": round(span / atr, 2),
                "net_move_pct": round(net / first * 100.0, 2),
                "net_move_atr": round(net / atr, 2),
                "call": None,
                "direction": None,
            }
            if abs(regime["net_move_atr"]) >= trend_min:
                regime["call"] = "trend"
                regime["direction"] = "up" if net > 0 else "down"
            elif regime["range_atr"] <= coil_max:
                regime["call"] = "consolidation"
            else:
                regime["call"] = "neither"
            if price is not None:
                regime_where = ("above the range" if price > high else
                                "below the range" if price < low else
                                "inside the range")
                out["gap_vs_regime"] = regime_where
    out["regime"] = regime

    # ---- how many of the last recent_n sessions gapped, and the run
    #      A COUNT AND A RUN ARE DIFFERENT FACTS. Three gaps scattered through
    #      a week is a busy name; three in a row is the sequence every source
    #      calls exhaustion, and a count alone cannot tell them apart.
    if len(rows) >= 2:
        span = rows[-recent_n:]
        offset = len(rows) - len(span)
        flags = [gap_rule.test(abs(g)) if (g := _gap_pct_into(rows, offset + i))
                 is not None else None for i in range(len(span))]
        run = 0
        for flag in reversed(flags):
            if flag:
                run += 1
            else:
                break
        out["recent_gaps"] = {
            "count": sum(1 for f in flags if f),
            "of": sum(1 for f in flags if f is not None),
            "window": recent_n,
            "run": run,
        }

    # ---- what this name has done on its own past gaps
    #      THE ONE ITEM HERE THAT IS EVIDENCE ABOUT THIS STOCK rather than
    #      about gapping stocks in general, which is what [Precedent] answers.
    if len(rows) >= 2:
        span = rows[-prior_n:]
        offset = len(rows) - len(span)
        moves: list[float] = []
        counted = 0
        measured = 0
        for i in range(len(span)):
            gap = _gap_pct_into(rows, offset + i)
            if gap is None:
                continue
            measured += 1
            if not gap_rule.test(abs(gap)):
                continue
            counted += 1
            move = _open_to_close_pct(span[i])
            if move is not None:
                moves.append(move)
        out["prior_gaps"] = {
            "count": counted,
            "of": measured,
            "window": prior_n,
            "median_open_to_close_pct": (round(statistics.median(moves), 2)
                                         if moves else None),
            "n": len(moves),
        }

    # ---- the call, last, out of everything above
    direction = out["gap_direction"]
    recent = out["recent_gaps"] or {}
    if regime is None or regime.get("call") is None or direction in (None, "flat"):
        # THREE DIFFERENT ABSENCES AND THEY DO NOT SHARE A SENTENCE. A short
        # history, a missing price and a gap of exactly nothing are three
        # states a reader would act on differently, and until each said its own
        # name a row with a perfectly good year of bars and no price reported
        # itself as one with no history.
        out["type"] = "unknown"
        if regime is None or regime.get("call") is None:
            out["type_why"] = (
                "there is not enough completed history to say what this name "
                "was doing before today")
        elif price is None:
            out["type_why"] = (
                "no price was available to measure a gap from, so the history "
                "below is drawn and nothing is read against it")
        else:
            out["type_why"] = (
                "the price is level with the last close, so the gap has no "
                "direction to read against anything")
        return out

    call, trend_direction = regime["call"], regime["direction"]
    run = recent.get("run") or 0
    where = out["gap_vs_regime"]
    if call == "trend" and direction == trend_direction and run >= run_min:
        out["type"] = "exhaustion"
        out["type_why"] = (
            f"the last {regime['sessions']} days moved "
            f"{regime['net_move_atr']} normal days {trend_direction}, and this "
            f"is the {run + 1}th day running to gap at "
            f"{gap_rule.describe()} percent")
    elif call == "trend" and direction == trend_direction:
        out["type"] = "runaway"
        out["type_why"] = (
            f"the last {regime['sessions']} days moved "
            f"{regime['net_move_atr']} normal days {trend_direction}, and "
            f"today's gap goes the same way")
    elif call == "consolidation" and where in ("above the range", "below the range"):
        out["type"] = "breakaway"
        out["type_why"] = (
            f"the last {regime['sessions']} days held a range "
            f"{regime['range_atr']} normal days wide, and today's price is "
            f"{where}")
    else:
        out["type"] = "common"
        # ONE PHRASE PER CALL, because "neither" is a value call takes and
        # "read as neither at 4.07" is not a sentence. This is the branch
        # most mornings land in.
        shape = {
            "trend": f"trended {trend_direction}",
            "consolidation": "held a range",
        }.get(call, "neither held a range nor trended")
        out["type_why"] = (
            f"the last {regime['sessions']} days {shape}, "
            f"{regime['range_atr']} normal days wide with "
            f"{regime['net_move_atr']} of net move, and today's gap "
            f"{direction} sits {where or 'nowhere measurable against it'}")
    return out


def measure(bars: list[dict[str, Any]], price: float | None,
            basis_factor: float | None = None) -> dict[str, Any]:
    """The whole map for one name. Pure: no clock, no API, no writes.

    `bars` are COMPLETED daily sessions in ascending date order, the mapped
    session's own row already excluded by the caller. That row must not be
    here: on the morning its high and low are still moving, and on a backfill
    including it would let the session explain itself, which is the one way
    this whole instrument could be quietly worthless. See
    night/backfill_structure.py and the claim that guards it.

    `basis_factor` restates the levels in the money of one session; see the
    WHICH BASIS note in the header. Left None the vendor's own basis stands.
    """
    windows_wanted = [_CRIT.integer("daily_structure", key) for key in
                      ("lookback_sessions_short", "lookback_sessions_medium",
                       "lookback_sessions_long")]
    sma_wanted = [_CRIT.integer("daily_structure", key) for key in
                  ("sma_fast", "sma_slow")]
    atr_sessions = _CRIT.integer("daily_structure", "atr_sessions")
    minimum = _CRIT.integer("daily_structure", "min_sessions")
    volume_sessions = _CRIT.integer("daily_structure", "avg_volume_sessions")
    coil_sessions = _CRIT.integer("daily_structure", "consolidation_sessions")

    rows, adjustment_steps = adjusted_series(bars, basis_factor)
    block: dict[str, Any] = {
        "sessions": len(rows),
        "last_session": rows[-1]["date"] if rows else None,
        "first_session": rows[0]["date"] if rows else None,
        "basis_factor": None if basis_factor is None else round(basis_factor, 8),
        "price": price,
        "adjustment_steps": adjustment_steps,
        "short": None,
    }
    if len(rows) < minimum:
        block["short"] = (
            f"{len(rows)} completed session(s) on file against the "
            f"{minimum} this map needs, so nothing below is drawn")
        block.update({"atr": None, "atr_pct": None, "windows": [], "sma": [],
                      "up_closes": None, "average_volume": None,
                      "consolidation": None, "gap_context": None})
        return block

    atr = _atr(rows, atr_sessions)
    block["atr_sessions"] = atr_sessions
    block["atr"] = None if atr is None else round(atr, 4)
    block["atr_pct"] = (None if not (atr and price)
                        else round(atr / price * 100.0, 2))
    block["windows"] = [w for w in
                        (_window(rows, n, price) for n in windows_wanted) if w]
    block["sma"] = [s for s in (_sma(rows, n, price) for n in sma_wanted) if s]
    block["average_volume"] = _average_volume(rows, volume_sessions)
    block["consolidation"] = _consolidation(rows, coil_sessions, atr)
    block["gap_context"] = _gap_context(rows, price, atr)

    # How many of the last short-window sessions closed up on the one before.
    # A count and its denominator together, never a bare percentage, for the
    # reason the avg_volume_20d note gives: a share without its count asserts
    # a denominator it may not have.
    span = min(windows_wanted[0], len(rows) - 1)
    up = sum(1 for i in range(len(rows) - span, len(rows))
             if rows[i]["close"] is not None and rows[i - 1]["close"] is not None
             and rows[i]["close"] > rows[i - 1]["close"])
    block["up_closes"] = {"up": up, "of": span} if span > 0 else None
    return block


# --------------------------------------------------------------- the columns

# The three windows and the two averages, in the order measure() emits them,
# named by ROLE and not by their session count. The count is a CRITERIA knob
# and a column called ds_high_60 would start lying the day it moved, which is
# the same failure fill_band_pct exists to prevent: every row here carries the
# window it was actually measured over beside the level it produced.
_WINDOW_ROLES = ("short", "medium", "long")
_SMA_ROLES = ("fast", "slow")


def columns(block: dict[str, Any] | None,
            reason: str | None = None,
            price_reason: str | None = None) -> dict[str, Any]:
    """One map, flattened to the picks columns, and the ONLY place that mapping lives.

    scan.write_picks calls this for the live morning and
    night/backfill_structure.py calls it for every session already in the
    record. Two flatteners would eventually disagree about what ds_pos_medium
    means, and a column whose meaning depends on which pass wrote it cannot be
    grouped on, which is the entire point of putting these in the table.

    EVERY COLUMN IS SET ON EVERY CALL, to None where there is nothing to say.
    A partial dict would leave whatever a previous run wrote in place, so a map
    that got worse would read as one that never changed.

    `reason` says why there is no map at all and `price_reason` why a map that
    exists has nothing to read against itself. They are separate because the
    two absences are: a row with a year of bars and no price still carries
    every level it measured, and calling that "no map" would throw them away.
    """
    out: dict[str, Any] = {
        "ds_sessions": None, "ds_first_session": None, "ds_last_session": None,
        "ds_short_reason": reason, "ds_adjustment_steps": None,
        "ds_basis_factor": None, "ds_price": None,
        "ds_price_reason": price_reason,
        "ds_atr": None, "ds_atr_pct": None, "ds_atr_sessions": None,
        "ds_up_closes": None, "ds_up_closes_of": None,
        "ds_avg_volume": None, "ds_avg_volume_sessions": None,
        "ds_avg_volume_of": None,
        "ds_consolidation_sessions": None, "ds_consolidation_range": None,
        "ds_consolidation_range_pct": None, "ds_consolidation_ratio": None,
        "ds_gap_pct": None, "ds_gap_direction": None,
        "ds_gap_threshold_pct": None, "ds_gap_threshold_rule": None,
        "ds_regime": None, "ds_regime_sessions": None, "ds_regime_direction": None,
        "ds_regime_range_pct": None, "ds_regime_range_atr": None,
        "ds_regime_net_move_pct": None, "ds_regime_net_move_atr": None,
        "ds_gap_vs_regime": None,
        "ds_gap_type": None, "ds_gap_type_why": None,
        "ds_recent_gap_sessions": None, "ds_recent_gap_of": None,
        "ds_recent_gap_window": None, "ds_recent_gap_run": None,
        "ds_prior_gap_count": None, "ds_prior_gap_of": None,
        "ds_prior_gap_window": None, "ds_prior_gap_median_otc_pct": None,
        "ds_prior_gap_n": None,
    }
    for role in _WINDOW_ROLES:
        out.update({f"ds_{role}_sessions": None, f"ds_high_{role}": None,
                    f"ds_low_{role}": None, f"ds_pos_{role}": None,
                    f"ds_since_above_{role}": None,
                    f"ds_since_above_{role}_date": None})
    for role in _SMA_ROLES:
        out.update({f"ds_sma_{role}_sessions": None, f"ds_sma_{role}": None,
                    f"ds_sma_{role}_vs_pct": None})
    if not block:
        return out

    out["ds_sessions"] = block.get("sessions")
    out["ds_first_session"] = block.get("first_session")
    out["ds_last_session"] = block.get("last_session")
    out["ds_basis_factor"] = block.get("basis_factor")
    out["ds_price"] = block.get("price")
    # The reason only stands while there is nothing to explain it away. A map
    # drawn against a real price has no missing price to give a reason for.
    if block.get("price") is not None:
        out["ds_price_reason"] = None
    steps = block.get("adjustment_steps") or []
    out["ds_adjustment_steps"] = ", ".join(steps) or None
    # The caller's reason answers "why is there no map at all". A block that
    # exists answers for itself, so it OVERWRITES that reason rather than
    # sitting under it: a drawn map beside a sentence explaining its absence
    # is the pair of facts a reader would have to pick between.
    out["ds_short_reason"] = block.get("short")
    if block.get("short"):
        return out

    out["ds_atr"] = block.get("atr")
    out["ds_atr_pct"] = block.get("atr_pct")
    out["ds_atr_sessions"] = block.get("atr_sessions")
    for role, window in zip(_WINDOW_ROLES, block.get("windows") or []):
        out[f"ds_{role}_sessions"] = window.get("sessions")
        out[f"ds_high_{role}"] = window.get("high")
        out[f"ds_low_{role}"] = window.get("low")
        out[f"ds_pos_{role}"] = window.get("position_pct")
        out[f"ds_since_above_{role}"] = window.get("since_close_above")
        out[f"ds_since_above_{role}_date"] = window.get("since_close_above_date")
    for role, average in zip(_SMA_ROLES, block.get("sma") or []):
        out[f"ds_sma_{role}_sessions"] = average.get("sessions")
        out[f"ds_sma_{role}"] = average.get("value")
        out[f"ds_sma_{role}_vs_pct"] = average.get("price_vs_pct")
    if block.get("up_closes"):
        out["ds_up_closes"] = block["up_closes"]["up"]
        out["ds_up_closes_of"] = block["up_closes"]["of"]
    if block.get("average_volume"):
        out["ds_avg_volume"] = block["average_volume"]["value"]
        out["ds_avg_volume_sessions"] = block["average_volume"]["sessions"]
        out["ds_avg_volume_of"] = block["average_volume"]["of"]
    if block.get("consolidation"):
        coil = block["consolidation"]
        out["ds_consolidation_sessions"] = coil["sessions"]
        out["ds_consolidation_range"] = coil["range"]
        out["ds_consolidation_range_pct"] = coil["range_pct"]
        out["ds_consolidation_ratio"] = coil["ratio"]

    context = block.get("gap_context") or {}
    if context:
        out["ds_gap_pct"] = context.get("gap_pct")
        out["ds_gap_direction"] = context.get("gap_direction")
        out["ds_gap_threshold_pct"] = context.get("threshold_pct")
        out["ds_gap_threshold_rule"] = context.get("threshold_rule")
        out["ds_gap_vs_regime"] = context.get("gap_vs_regime")
        out["ds_gap_type"] = context.get("type")
        out["ds_gap_type_why"] = context.get("type_why")
        regime = context.get("regime") or {}
        out["ds_regime"] = regime.get("call")
        out["ds_regime_sessions"] = regime.get("sessions")
        out["ds_regime_direction"] = regime.get("direction")
        out["ds_regime_range_pct"] = regime.get("range_pct")
        out["ds_regime_range_atr"] = regime.get("range_atr")
        out["ds_regime_net_move_pct"] = regime.get("net_move_pct")
        out["ds_regime_net_move_atr"] = regime.get("net_move_atr")
        recent = context.get("recent_gaps") or {}
        out["ds_recent_gap_sessions"] = recent.get("count")
        out["ds_recent_gap_of"] = recent.get("of")
        out["ds_recent_gap_window"] = recent.get("window")
        out["ds_recent_gap_run"] = recent.get("run")
        prior = context.get("prior_gaps") or {}
        out["ds_prior_gap_count"] = prior.get("count")
        out["ds_prior_gap_of"] = prior.get("of")
        out["ds_prior_gap_window"] = prior.get("window")
        out["ds_prior_gap_median_otc_pct"] = prior.get("median_open_to_close_pct")
        out["ds_prior_gap_n"] = prior.get("n")
    return out


def block_from_columns(row: dict[str, Any]) -> dict[str, Any] | None:
    """A stored picks row, back into the shape measure() returns.

    WHY THE INVERSE LIVES HERE, beside columns() and not at the caller that
    wanted it. desk/compact.py draws the map for a session whose PACKET
    predates it out of the picks row the backfill wrote, and it has to turn
    those columns back into a block to do it. A second mapping written over
    there would be a second opinion about what ds_pos_medium means, which is
    the exact failure putting one flattener here was meant to prevent. The
    round trip is asserted by claim_a_stored_map_draws_the_same_card.

    NOTHING IS RECOMPUTED and no threshold is read. Every value comes off the
    row, including the [Day setup] rule the gap counts were taken at, so a
    stored map draws the same card next year when that rule has moved.

    None when the row has no map, so a caller can tell "not measured" from
    "measured and short". A row with only ds_short_reason comes back as a
    block carrying that reason and no figures, which is what measure() itself
    returns for a name with too little history.
    """
    if row.get("ds_sessions") is None and not row.get("ds_short_reason"):
        return None
    steps = str(row.get("ds_adjustment_steps") or "")
    block: dict[str, Any] = {
        "sessions": row.get("ds_sessions"),
        "last_session": row.get("ds_last_session"),
        "first_session": row.get("ds_first_session"),
        "basis_factor": row.get("ds_basis_factor"),
        "price": row.get("ds_price"),
        "adjustment_steps": [s.strip() for s in steps.split(",") if s.strip()],
        "short": row.get("ds_short_reason"),
    }
    if block["short"]:
        block.update({"atr": None, "atr_pct": None, "windows": [], "sma": [],
                      "up_closes": None, "average_volume": None,
                      "consolidation": None, "gap_context": None})
        return block

    block["atr"] = row.get("ds_atr")
    block["atr_pct"] = row.get("ds_atr_pct")
    block["atr_sessions"] = row.get("ds_atr_sessions")
    block["windows"] = [
        {"sessions": row.get(f"ds_{role}_sessions"),
         "high": row.get(f"ds_high_{role}"), "low": row.get(f"ds_low_{role}"),
         "position_pct": row.get(f"ds_pos_{role}"),
         "from": None,
         "since_close_above": row.get(f"ds_since_above_{role}"),
         "since_close_above_date": row.get(f"ds_since_above_{role}_date"),
         "since_close_above_reason": None}
        for role in _WINDOW_ROLES if row.get(f"ds_{role}_sessions") is not None]
    block["sma"] = [
        {"sessions": row.get(f"ds_sma_{role}_sessions"),
         "value": row.get(f"ds_sma_{role}"),
         "price_vs_pct": row.get(f"ds_sma_{role}_vs_pct")}
        for role in _SMA_ROLES if row.get(f"ds_sma_{role}") is not None]
    block["up_closes"] = ({"up": row["ds_up_closes"], "of": row["ds_up_closes_of"]}
                          if row.get("ds_up_closes") is not None else None)
    block["average_volume"] = (
        {"value": row["ds_avg_volume"], "sessions": row.get("ds_avg_volume_sessions"),
         "of": row.get("ds_avg_volume_of")}
        if row.get("ds_avg_volume") is not None else None)
    block["consolidation"] = (
        {"sessions": row.get("ds_consolidation_sessions"),
         "range": row.get("ds_consolidation_range"),
         "range_pct": row.get("ds_consolidation_range_pct"),
         "ratio": row["ds_consolidation_ratio"]}
        if row.get("ds_consolidation_ratio") is not None else None)

    if row.get("ds_gap_type") is None:
        block["gap_context"] = None
        return block
    regime = None
    if row.get("ds_regime"):
        regime = {"sessions": row.get("ds_regime_sessions"),
                  "call": row.get("ds_regime"),
                  "direction": row.get("ds_regime_direction"),
                  "high": None, "low": None,
                  "range_pct": row.get("ds_regime_range_pct"),
                  "range_atr": row.get("ds_regime_range_atr"),
                  "net_move_pct": row.get("ds_regime_net_move_pct"),
                  "net_move_atr": row.get("ds_regime_net_move_atr")}
    block["gap_context"] = {
        "threshold_pct": row.get("ds_gap_threshold_pct"),
        "threshold_rule": row.get("ds_gap_threshold_rule"),
        "gap_pct": row.get("ds_gap_pct"),
        "gap_direction": row.get("ds_gap_direction"),
        "regime": regime,
        "gap_vs_regime": row.get("ds_gap_vs_regime"),
        "recent_gaps": ({"count": row.get("ds_recent_gap_sessions"),
                         "of": row.get("ds_recent_gap_of"),
                         "window": row.get("ds_recent_gap_window"),
                         "run": row.get("ds_recent_gap_run")}
                        if row.get("ds_recent_gap_of") is not None else None),
        "prior_gaps": ({"count": row.get("ds_prior_gap_count"),
                        "of": row.get("ds_prior_gap_of"),
                        "window": row.get("ds_prior_gap_window"),
                        "median_open_to_close_pct":
                            row.get("ds_prior_gap_median_otc_pct"),
                        "n": row.get("ds_prior_gap_n")}
                       if row.get("ds_prior_gap_of") is not None else None),
        "type": row.get("ds_gap_type"),
        "type_why": row.get("ds_gap_type_why"),
    }
    return block


def attach(candidates: list[dict[str, Any]],
           bars_by_symbol: dict[str, list[dict[str, Any]]]) -> int:
    """Put the map on every candidate that has the history for one.

    SCOPED TO NOTHING. It runs for every candidate rather than for the green
    ones alone, because the bars are already in hand for all of them and the
    call was already paid for; narrowing it would save no credit and would
    leave a reader on a yellow card wondering why the panel was missing.

    A candidate whose history never arrived gets daily_structure None, which
    the screen draws as an absence with its reason, not as an empty map.
    """
    attached = 0
    for candidate in candidates:
        bars = bars_by_symbol.get(candidate.get("symbol"))
        if not bars:
            candidate["daily_structure"] = None
            continue
        candidate["daily_structure"] = measure(bars, _as_float(candidate.get("price")))
        attached += 1
    return attached
