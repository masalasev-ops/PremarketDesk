"""The live ladder: where every published pick stands against its own entry.

WHY THIS EXISTS. Measured over the 86 paper trades on file, 77 percent of the
entries that ever trigger do so within five minutes of the open and the median
time to trigger is ZERO minutes: the entry is taken at the open or not at all.
The median time to peak is 17 minutes. So the decision this desk exists to
support is made between 09:30 and roughly 09:47, and until now the desk went
dark at 09:25 and said nothing again until the 12:00 midday pass.

The noon reading was never late. It is a scorecard for a trade that was over
before ten o'clock, and reading it as though it were the moment of truth is
what makes the desk look like a post mortem instrument. The half hour it was
missing is the half hour that decides everything.

WHAT IT ANSWERS, and it is one question: which of this morning's names is
closest to its entry, right now. A reader with ten cards and one screen cannot
watch ten tickers, and the entry is a level published at 09:12 that either
trades or does not.

SEQUENCE IS KNOWABLE HERE AND NOWHERE ELSE, which is the second thing the
extended window buys and is worth more than the first. CRITERIA's midday state
table has said since it was written that a TRIGGERED row cannot say whether the
session low came before or after the fill, because a daily high and low carry
no order, and that "the third case is the whole argument for extending
[Collector] stop_time past the open: minute bars with timestamps turn it into
the second case's certainty". These are minute bars with timestamps. A stop
reached AFTER a trigger is a stop out and is reported as one; a low before the
trigger stops nothing and is not.

WHAT IT IS NOT. It computes no score, ranks nothing new, and makes no
recommendation. Every level on it was published at 08:45 and frozen into the
packet; this pass only says where the tape is against those levels. Nothing
here may write to the packet, the picks table or the ledger, because a figure
measured at 09:41 against a moving tape is not the record of a session and must
never be mistaken for one.

    PYTHONPATH=src .venv/Scripts/python.exe -m morning.ladder
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from collect import collect_premarket
from core import config
from core import criteria
from core import ettime
from core import files
from ops import job_status

_CRIT = criteria.load()

# Waiting, and the three ways it stops waiting. Named rather than inferred at
# the reader, and deliberately the SAME words the midday pass uses for the
# same states, so a reader moving between the two screens is not asked to
# learn a second vocabulary for one fact.
STATE_WAITING = "waiting"
STATE_TRIGGERED = "triggered"
STATE_GAPPED_THROUGH = "gapped_through"
STATE_STOPPED = "stopped"


def ladder_path(day: str | None = None) -> Path:
    return config.SESSION_DIR / f"ladder-{day or ettime.today_str()}.json"


def _bar_time(bar: dict[str, Any]) -> dt.datetime | None:
    stamp = bar.get("minute_et")
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None


def published(day: str) -> tuple[list[dict[str, Any]], str | None]:
    """This morning's picks and their levels, read from the frozen packet.

    THE PACKET AND NOT A FRESH SCREEN. The levels a reader is watching are the
    ones that were published to them at 08:45, so re-deriving an entry here
    would put a different number on the screen from the one in their hand, and
    it would do it silently. This pass has no opinion about what the entry
    should be.
    """
    path = config.run_path(day) / "packet.json"
    if not path.is_file():
        return [], f"no packet for {day}, so nothing was published to watch"
    try:
        packet = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [], f"the {day} packet could not be read: {type(exc).__name__}: {exc}"
    out = []
    for c in packet.get("candidates") or []:
        # entry_ref and stop_ref are what the PACKET calls them. The desk
        # payload renames them to entry and stop on the way to the screen, and
        # reading the screen's names here found nothing at all: this pass has
        # to speak the packet's vocabulary because the packet is what it reads.
        entry, stop = c.get("entry_ref"), c.get("stop_ref")
        if entry is None:
            continue
        symbol = str(c.get("symbol") or "")
        out.append({
            # Both, and for different jobs. The bar file is keyed on the whole
            # vendor symbol and the screen prints the bare ticker.
            "symbol": symbol,
            "sym": symbol.split(".")[0],
            "entry": entry,
            "stop": stop,
            "conv": c.get("conviction"),
            "score": c.get("score"),
            "prior_close": c.get("prior_close"),
        })
    return out, None if out else f"the {day} packet carries no priced candidate"


def walk(bars: list[dict[str, Any]], entry: float,
         stop: float | None) -> dict[str, Any]:
    """One name's minutes, in order, against its two published levels.

    IN ORDER, and that is the whole point of the function. It would be shorter
    to take a max and a min over the window and compare both to the levels,
    and that is precisely the arithmetic the midday pass is stuck with when it
    has only a daily high and low: it cannot say whether the low came before
    the fill, so it must report a stop level as reached with the sequence
    unknown and must never call it a stop out. Walking the minutes answers the
    question the aggregate cannot.

    The first bar's OPEN is read separately from its high, because a session
    that opens already through the entry is a different state from one that
    trades up to it: the fill is the open and not the level.
    """
    result = {
        "state": STATE_WAITING, "last": None, "at": None,
        "high": None, "low": None,
        "triggered_at": None, "fill": None,
        "stopped_at": None, "stop_sequence_unknown": False, "bars": len(bars),
    }
    if not bars:
        return result
    ordered = sorted(bars, key=lambda b: b.get("minute_epoch") or 0)
    first = ordered[0]
    for i, bar in enumerate(ordered):
        high, low, close = bar.get("h"), bar.get("l"), bar.get("c")
        when = _bar_time(bar)
        stamp = when.strftime("%H:%M") if when else None
        if close is not None:
            result["last"], result["at"] = close, stamp
        if high is not None:
            result["high"] = high if result["high"] is None else max(result["high"], high)
        if low is not None:
            result["low"] = low if result["low"] is None else min(result["low"], low)

        if result["state"] == STATE_WAITING:
            if i == 0 and first.get("o") is not None and first["o"] >= entry:
                result.update({"state": STATE_GAPPED_THROUGH,
                               "triggered_at": stamp, "fill": first["o"]})
            elif high is not None and high >= entry:
                result.update({"state": STATE_TRIGGERED,
                               "triggered_at": stamp, "fill": entry})
        # A low BEFORE the trigger stops nothing: there was no position under
        # it. A low AFTER it does, and that certainty is the whole reason this
        # window is worth reading.
        #
        # WITHIN the triggering minute it is not knowable, and this says so
        # rather than choosing. A minute bar carries a high and a low and no
        # order between them, so a stop level touched in the same minute as
        # the fill is the midday pass's third case exactly: reported as
        # reached, never as a stop out. Deciding it either way here would be
        # inventing a sequence out of a bar that does not carry one, and the
        # pessimistic guess is still a guess.
        if (result["state"] in (STATE_TRIGGERED, STATE_GAPPED_THROUGH)
                and stop is not None and low is not None and low <= stop):
            same_minute = stamp is not None and stamp == result["triggered_at"]
            result.update({"state": STATE_STOPPED, "stopped_at": stamp,
                           "stop_sequence_unknown": same_minute})
    return result


def build(day: str | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    """Every published name against the tape since the open."""
    day = day or ettime.today_str()
    now = now or ettime.now_et()
    open_at = ettime.at_hm(now.date(), _CRIT.clock("ladder", "open_time"))
    close_at = ettime.at_hm(now.date(), _CRIT.clock("ladder", "close_time"))

    names, why = published(day)
    payload: dict[str, Any] = {
        "session": day,
        "generated": ettime.stamp(now),
        "open_time": _CRIT.clock_text("ladder", "open_time"),
        "close_time": _CRIT.clock_text("ladder", "close_time"),
        "window_over": now >= close_at,
        "before_open": now < open_at,
        "names": [],
        "why": why,
    }
    if not names:
        return payload

    bars = collect_premarket.read_bars(day)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol, rows in (bars or {}).items():
        kept = []
        for bar in rows:
            # A REPLAYED PRINT IS NOT THIS SESSION'S TAPE. The subscription
            # replays each symbol's last trade on connect, stamped whenever it
            # happened, and one of those landing at 09:30:00 would read as the
            # opening print and could trigger an entry that never traded.
            if bar.get("replay"):
                continue
            when = _bar_time(bar)
            if when is None or when < open_at or when > close_at:
                continue
            kept.append(bar)
        if kept:
            by_symbol[symbol] = kept

    rows = []
    for pick in names:
        mine = by_symbol.get(pick["symbol"]) or by_symbol.get(pick["sym"]) or []
        walked = walk(mine, pick["entry"], pick["stop"])
        entry = pick["entry"]
        last = walked["last"]
        rows.append({
            **pick,
            **walked,
            # Signed, and from the READER's side: negative means the tape is
            # still under the entry and has that far to climb.
            "to_entry_pct": None if last is None else (last - entry) / entry * 100.0,
        })
    # Closest to its entry first, which is the one question the screen answers.
    # A name with no tape sorts last rather than first: an unknown distance is
    # not a short one.
    rows.sort(key=lambda r: (r["to_entry_pct"] is None,
                             -(r["to_entry_pct"] or -999)))
    payload["names"] = rows
    payload["covered"] = sum(1 for r in rows if r["bars"])
    return payload


def write(payload: dict[str, Any]) -> Path:
    path = ladder_path(payload["session"])
    # As in selection/discover: the writer makes its own directory,
    # because ensure_dirs covers the chain and nothing else.
    path.parent.mkdir(parents=True, exist_ok=True)
    files.write_json_atomically(path, payload, indent=1)
    return path


# Zero and nothing else. This pass reads two files and reaches no vendor, so
# there is no partial success for it to report: either it measured the tape
# against the published levels or something is wrong that a screen refreshing
# every two minutes must not paper over.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default=None, help="session date, default today")
    parser.add_argument("--dry-run", action="store_true",
                        help="print and write nothing")
    args = parser.parse_args(argv)

    payload = build(args.day)
    live = [r for r in payload["names"] if r["bars"]]
    print(f"ladder: {len(payload['names'])} published name(s), {len(live)} with "
          f"tape since {payload['open_time']}")
    for row in payload["names"][:12]:
        far = row["to_entry_pct"]
        print(f"  {str(row['sym']):<10} {row['state']:<15} "
              f"{'n/a' if far is None else format(far, '+.2f') + '%':>8} to entry"
              + (f", triggered {row['triggered_at']}" if row["triggered_at"] else ""))
    if args.dry_run:
        print("ladder: --dry-run, nothing written")
        return 0
    path = write(payload)
    job_status.produced("names on the ladder", len(payload["names"]))
    print(f"ladder: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("ladder", main, ok_codes=OK_CODES))
