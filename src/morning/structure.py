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

WHAT IT COSTS: NOTHING. attach_daily_history already calls eod once per
candidate, and [Quota costs] prices that call at one credit flat, per call and
not per row. Widening its from date returns a trading year instead of five
weeks for the same one credit, so this whole section is paid for by a call the
morning was already making. See attach_daily_history's history_days note.

EVERY LEVEL IS SPLIT ADJUSTED, and silently getting this wrong is the one way a
map like this misleads. The vendor returns close and adjusted_close on each
row; their ratio back adjusts an older bar onto today's basis, so a high from
before a two for one split is comparable to today's price rather than twice it.
On a name with neither split nor dividend the ratio is one throughout and the
scaling does nothing. A large single session step in that ratio is disclosed by
name and date, because a reader looking at a raw chart will see other numbers
and is owed the reason.
"""

from __future__ import annotations

from typing import Any

from core import criteria

_CRIT = criteria.load()


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def adjusted_series(bars: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Back adjust high, low and close onto today's price basis.

    The factor is adjusted_close / close on each row, which is what the vendor
    already publishes; this only applies it to the other two fields. A row
    missing either number is carried at factor one rather than dropped, because
    dropping it would put a hole in an ATR that reads as a quiet session.

    The second return is the dates whose factor stepped by more than
    [Daily structure] max_adjustment_step against the row before. That is the
    signature of a split or a large special dividend, and it is DISCLOSED
    rather than corrected: the correction has already been applied above, and
    the disclosure exists so a reader whose chart disagrees knows why.
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
        row = {"date": str(bar.get("date"))}
        for key in ("high", "low", "close"):
            value = _as_float(bar.get(key))
            row[key] = None if value is None else value * factor
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
    highs = [r["high"] for r in window if r["high"] is not None]
    lows = [r["low"] for r in window if r["low"] is not None]
    if not highs or not lows:
        return None
    high, low = max(highs), min(lows)
    position = None
    if price is not None and high > low:
        position = round((price - low) / (high - low) * 100.0, 1)
    return {
        "sessions": sessions,
        "high": round(high, 4),
        "low": round(low, 4),
        "position_pct": position,
        "from": window[0]["date"],
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


def measure(bars: list[dict[str, Any]], price: float | None) -> dict[str, Any]:
    """The whole map for one name. Pure: no clock, no API, no writes.

    `bars` are COMPLETED daily sessions in ascending date order, today's own
    row already excluded by the caller. Today's row must not be here: its high
    and low are still moving, and a 20 session high that includes a partial
    session is not a fact about the past.
    """
    windows_wanted = [_CRIT.integer("daily_structure", key) for key in
                      ("lookback_sessions_short", "lookback_sessions_medium",
                       "lookback_sessions_long")]
    sma_wanted = [_CRIT.integer("daily_structure", key) for key in
                  ("sma_fast", "sma_slow")]
    atr_sessions = _CRIT.integer("daily_structure", "atr_sessions")
    minimum = _CRIT.integer("daily_structure", "min_sessions")

    rows, adjustment_steps = adjusted_series(bars)
    block: dict[str, Any] = {
        "sessions": len(rows),
        "last_session": rows[-1]["date"] if rows else None,
        "adjustment_steps": adjustment_steps,
        "short": None,
    }
    if len(rows) < minimum:
        block["short"] = (
            f"{len(rows)} completed session(s) on file against the "
            f"{minimum} this map needs, so nothing below is drawn")
        block.update({"atr": None, "atr_pct": None, "windows": [], "sma": [],
                      "up_closes": None})
        return block

    atr = _atr(rows, atr_sessions)
    block["atr_sessions"] = atr_sessions
    block["atr"] = None if atr is None else round(atr, 4)
    block["atr_pct"] = (None if not (atr and price)
                        else round(atr / price * 100.0, 2))
    block["windows"] = [w for w in
                        (_window(rows, n, price) for n in windows_wanted) if w]
    block["sma"] = [s for s in (_sma(rows, n, price) for n in sma_wanted) if s]

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
