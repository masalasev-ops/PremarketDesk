"""Would a screen computed to 08:30 be the same screen? Answered offline, before Monday.

DECISIONS.md 2026-08-22 pre-registers the Monday test and names a third
question it cannot answer: if the sweep comes back served but the control is
refused, the feed is reachable at 08:45 and only fifteen minutes behind, and
the morning would have to accept a window ending at 08:30 instead of 08:45.
Whether that screen is worth having was left open. It does not have to be. The
collector's own minute bars are on disk for five sessions, the packets that
screened off them are beside those bars, and a window is a filter on minutes.
Nothing here calls a vendor and nothing here spends a credit.

WHAT IS RECOMPUTED. The day screen, all five conditions from CRITERIA
[Day setup], for every candidate in every surviving packet, twice: once with
the premarket window ending at the packet's own cutoff, and once ending
fifteen minutes earlier. Only the window moves. Market cap, prior high, prior
close, the baseline denominator and the catalyst are the packet's own and are
held fixed, because they are what they were that morning and no cutoff
changes them.

THE INSTRUMENT PROVES ITSELF FIRST. The 08:45 pass has to reproduce the
packet's own day_eligible for every candidate, and its price, gap, premarket
volume and RVOL to the digit, before the 08:30 pass is read as anything. A
recomputation that cannot reproduce production at production's own cutoff is
not measuring the cutoff, it is measuring the difference between this file and
scan.py. That check runs on every session and a failure is reported rather
than swallowed. This is the 2026-08-22 rule applied to itself: a probe whose
shape cannot produce the negative result is not an instrument.

TWO ARITHMETICS, BECAUSE THE PACKETS PREDATE THE CURRENT ONE. The packets on
disk divide the raw socket count by the baseline. Current scan.py divides the
socket count by that symbol's capture share first, which is the correction
added on 2026-08-21, and Monday's morning would use it. Running only the old
arithmetic would answer a question about retired code; running only the new
one would break the reproduction check. Both are run and both are reported.

THREE DENOMINATORS, AND WHY THE ANSWER IS A BRACKET AND NOT A NUMBER. RVOL is
a ratio of the same window on today against the median of prior sessions, so a
shorter window shortens BOTH halves. The baseline cache holds 08:45 only, and
building an 08:30 baseline means twenty sessions of minute bars per name from
the vendor, which is the one thing this file may not do. So:

  held    the 08:45 denominator, unchanged. Overstates the loss, and is also
          literally what an 08:30 screen would do on Monday against the cache
          as it stands, because nothing warms an 08:30 baseline.
  socket  the denominator scaled by the session's own median socket share of
          07:20 to 08:45 volume that was in by 08:30. Understates the loss:
          the last fifteen minutes are a larger slice of an 85 minute window
          than of the 04:00 to 08:45 window the baseline actually covers.
  tape    the denominator scaled by a factor built from the true-volume rows,
          which are the only thing on disk that knows what the tape did before
          07:20. Per name, the Alpaca 04:00 to 08:45 total and the Alpaca
          07:20 to 08:45 total are both recorded, so the socket's own within
          window shape can be projected onto the tape total and the 08:30
          share taken on a 04:00 basis. This is the closest offline stand in
          for a rewarmed baseline and it is an assumption, named as one.

held and socket bracket the truth. tape sits between them and is the number to
quote if one number is wanted.

WHAT THIS FILE DOES NOT DO. It proposes nothing. It does not touch CRITERIA,
production, or the Monday task. It reports a count.

    PYTHONPATH=src .venv/Scripts/python.exe -m research.cutoff_0830
    PYTHONPATH=src .venv/Scripts/python.exe -m research.cutoff_0830 --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from typing import Any

from collect import collect_premarket
from core import config
from core import criteria

_CRIT = criteria.load()

PRODUCTION_CUTOFF = "08:45"
SERVABLE_CUTOFF = "08:30"
PATH_STEM = "cutoff-0830"


# --------------------------------------------------------------- session pick

def _minutes(hhmm: str) -> int:
    hour, _, minute = hhmm.partition(":")
    return int(hour) * 60 + int(minute)


def sessions() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(usable, refused) sessions, with the reason on every refusal.

    A session is usable when a packet survives that screened a real premarket
    at the production clock AND the minute bars it screened off are still
    beside it. Both halves are checked and a session missing either is named
    with which half, because "five sessions" and "five of seven, and here are
    the two and why" are different reports and only the second can be argued
    with.
    """
    usable: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for run_dir in sorted(config.RUNS_DIR.glob("*")):
        if not run_dir.is_dir():
            continue
        day = run_dir.name
        packet_path = run_dir / "packet.json"
        if not packet_path.exists():
            refused.append({"day": day, "why": "no packet.json in the run directory"})
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        cutoff = packet.get("rvol_cutoff_hhmm")
        build = (packet.get("build") or {}).get("commit")
        if build == "stub":
            refused.append({"day": day, "why": (
                "the surviving packet is a hand written stub, build.commit "
                "'stub', carrying one invented candidate. There is no morning "
                "here to recompute")})
            continue
        if not cutoff:
            refused.append({"day": day, "why": "the packet carries no rvol_cutoff_hhmm"})
            continue
        if cutoff != PRODUCTION_CUTOFF:
            refused.append({"day": day, "why": (
                f"the packet's cutoff is {cutoff}, not the {PRODUCTION_CUTOFF} "
                "production clock. This was not a premarket run and an 08:30 "
                "window means nothing inside it")})
            continue
        # The packet has to have been built by a program this file can
        # reproduce. Until the afternoon of 2026-08-14 the morning priced from
        # the delayed quote and took premarket volume from its ethVolume
        # field, which gave ARX an RVOL of 882,728 off yesterday's post
        # market; pm_volume is null on every candidate in that packet and
        # price_source is unset. Recomputing a window inside it would produce
        # a tidy table about a program that no longer exists. The reproduction
        # check at the bottom of this file catches it too, and catching it
        # twice is the point: this gate says WHY, that one proves the gate is
        # not letting anything through.
        priced = [c for c in (packet.get("candidates") or [])
                  if c.get("price_source") == "collector"]
        if len(priced) != len(packet.get("candidates") or []):
            refused.append({"day": day, "why": (
                f"{len(packet.get('candidates') or []) - len(priced)} of "
                f"{len(packet.get('candidates') or [])} candidates carry no "
                "collector priced quote. This packet predates price and "
                "premarket volume coming from the collector file, so its "
                "screen cannot be recomputed from minutes")})
            continue
        snapshot = run_dir / "premarket_snapshot.jsonl"
        if not snapshot.exists():
            refused.append({"day": day, "why": "the frozen premarket snapshot is gone"})
            continue
        bars, _stats = collect_premarket.read_bars_file(snapshot)
        if len(bars) < 2:
            refused.append({"day": day, "why": (
                f"the frozen snapshot carries {len(bars)} symbol(s). The "
                "collector file was overwritten by a later hand run, so the "
                "minutes this packet screened off no longer exist")})
            continue
        usable.append({"day": day, "packet": packet, "bars": bars,
                       "packet_path": str(packet_path)})
    return usable, refused


# ------------------------------------------------------------- one recompute

def _window(bars: list[dict[str, Any]], cutoff: str) -> list[dict[str, Any]]:
    """The bars whose minute STARTS before the cutoff.

    A bar stamped 08:44 covers 08:44:00 to 08:45:00, so a window ending at
    08:45 holds it and a window ending at 08:30 does not hold 08:30's. Strictly
    less than, both times, so the two cutoffs are the same rule at two clocks
    and not two rules.
    """
    limit = _minutes(cutoff)
    return [b for b in bars if _minutes(str(b["minute_et"])[11:16]) < limit]


def _measure(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """price, premarket volume and the last print's clock, off one window."""
    if not bars:
        return {"price": None, "price_time": None, "pm_volume": None, "bars": 0}
    last = max(bars, key=lambda b: b["minute_epoch"])
    volume = sum(float(b.get("v") or 0) for b in bars)
    return {
        "price": round(float(last["c"]), 4),
        "price_time": last["minute_et"],
        "pm_volume": volume,
        "bars": len(bars),
    }


def _rvol(pm_volume: float | None, candidate: dict[str, Any],
          capture_share: float | None, denominator_scale: float) -> float | None:
    """RVOL under one arithmetic and one denominator scale, or None with no fiction.

    Every reason production publishes a null RVOL is honoured here: no
    collector coverage, an unusable baseline, no volume. A null is not a low
    reading and must never clear or fail a floor as though it were one.
    """
    baseline = candidate.get("baseline") or {}
    median = baseline.get("median_volume")
    if not candidate.get("collector_covered"):
        return None
    if median is None or median < _CRIT.number("baseline", "min_baseline_premarket_volume"):
        return None
    if (baseline.get("sessions_used") or 0) < _CRIT.number("baseline", "min_sessions_for_rvol"):
        return None
    if pm_volume is None:
        return None
    numerator = pm_volume if capture_share is None else pm_volume / capture_share
    return round(numerator / (median * denominator_scale), 4)


def _day_screen(candidate: dict[str, Any], price: float | None,
                gap_pct: float | None, rvol: float | None) -> tuple[bool, list[str]]:
    """CRITERIA [Day setup], all five conditions, missing data passing nothing."""
    quote = candidate.get("quote") or {}
    failed: list[str] = []
    gap = abs(gap_pct) if gap_pct is not None else None
    if gap is None or not _CRIT.rule("day_setup", "gap_pct").test(gap):
        failed.append("gap_pct")
    if not _CRIT.rule("day_setup", "price").test(price):
        failed.append("price")
    if not _CRIT.rule("day_setup", "market_cap").test(quote.get("marketCap")):
        failed.append("market_cap")
    if not _CRIT.rule("day_setup", "premarket_rvol").test(rvol):
        failed.append("premarket_rvol")
    if _CRIT.flag("day_setup", "require_above_prior_high"):
        prior_high = candidate.get("prior_high")
        if prior_high is None or price is None or price <= prior_high:
            failed.append("require_above_prior_high")
    return (not failed), failed


# ------------------------------------------------------------ capture shares

def _capture_shares(day: str) -> dict[str, float]:
    """Per symbol collector over vendor shares, the way attach_capture_estimate reads them.

    Same floors, same refusals, same fallback to the CRITERIA default. A share
    this file computed differently from scan.py would make the new arithmetic
    pass measure this file.
    """
    min_vendor = _CRIT.number("collector", "min_capture_vendor_volume")
    min_minutes = _CRIT.integer("collector", "min_capture_minutes")
    path = config.run_dir(day) / "verify_intraday.json"
    shares: dict[str, float] = {}
    if not path.exists():
        return shares
    check = json.loads(path.read_text(encoding="utf-8"))
    minutes_by = check.get("minutes_compared_by_symbol") or {}
    for symbol, row in (check.get("volume_by_symbol") or {}).items():
        if not isinstance(row, dict):
            continue
        vendor = row.get("vendor")
        mine = row.get("collector")
        minutes = minutes_by.get(symbol)
        if vendor is None or mine is None or vendor <= 0:
            continue
        if vendor < min_vendor:
            continue
        if minutes is not None and minutes < min_minutes:
            continue
        if mine / vendor >= 1.0:
            continue
        shares[symbol] = mine / vendor
    return shares


def _default_share() -> float:
    return _CRIT.number("collector", "premarket_capture_rate")


# ----------------------------------------------------- denominator scaling

def tape_scale() -> dict[str, Any]:
    """The 08:30 share of a 04:00 to 08:45 window, from the true-volume rows.

    night.true_volume records two Alpaca totals per name: pm_volume_true over
    04:00 to 08:45 and true_volume_socket_window over the collector's own
    07:20 to 08:45. The difference is what the tape did before the socket was
    listening, which is the one thing the collector can never report and the
    reason a socket derived scale is too small.

    Per name: project the socket's OWN 08:30 share of its 07:20 window onto
    the Alpaca 07:20 total, add back the pre 07:20 tape, and take the result
    over the Alpaca 04:00 total. The assumption is that the socket's minute
    shape inside 07:20 to 08:45 matches the tape's inside the same minutes,
    which is a weaker claim than the capture correction already makes and is
    still an assumption.
    """
    from core import store

    per_name: list[dict[str, Any]] = []
    with store.session() as connection:
        store.init(connection)
        rows = connection.execute(
            "SELECT date, ticker, pm_volume_true, true_volume_socket_window "
            "FROM picks WHERE pm_volume_true IS NOT NULL "
            "AND true_volume_socket_window IS NOT NULL"
        ).fetchall()
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_day.setdefault(row["date"], {})[row["ticker"]] = dict(row)

    skipped: list[dict[str, Any]] = []
    for day, names in sorted(by_day.items()):
        snapshot = config.run_dir(day) / "premarket_snapshot.jsonl"
        if not snapshot.exists():
            skipped.append({"day": day, "why": "no frozen snapshot beside the rows"})
            continue
        bars, _stats = collect_premarket.read_bars_file(snapshot)
        if len(bars) < 2:
            skipped.append({"day": day, "why": (
                f"the frozen snapshot carries {len(bars)} symbol(s), so the "
                "minute shape these rows would be projected through is gone")})
            continue
        for ticker, row in sorted(names.items()):
            symbol_bars = bars.get(ticker) or []
            full = _measure(_window(symbol_bars, PRODUCTION_CUTOFF))["pm_volume"]
            early = _measure(_window(symbol_bars, SERVABLE_CUTOFF))["pm_volume"]
            if not full:
                continue
            socket_share = (early or 0.0) / full
            tape_socket_window = float(row["true_volume_socket_window"])
            tape_full = float(row["pm_volume_true"])
            if tape_full <= 0 or tape_socket_window <= 0:
                continue
            pre_socket = tape_full - tape_socket_window
            if pre_socket < 0:
                continue
            projected = pre_socket + tape_socket_window * socket_share
            per_name.append({
                "day": day, "ticker": ticker,
                "socket_share_of_socket_window": round(socket_share, 6),
                "pre_socket_share_of_tape": round(pre_socket / tape_full, 6),
                "tape_share_by_0830": round(projected / tape_full, 6),
            })
    if not per_name:
        return {"scale": None, "n": 0, "rows": [], "skipped": skipped,
                "why": "no true-volume row has a usable snapshot beside it"}
    values = [r["tape_share_by_0830"] for r in per_name]
    return {
        "scale": round(statistics.median(values), 6),
        "n": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "days": sorted({r["day"] for r in per_name}),
        "rows": per_name,
        "skipped": skipped,
        "why": ("median across the true-volume rows of the Alpaca 04:00 to "
                "08:45 volume that the socket's own minute shape puts in by "
                "08:30"),
    }


def socket_scale(bars: dict[str, list[dict[str, Any]]],
                 symbols: list[str]) -> float | None:
    """Median share of 07:20 to 08:45 socket volume that was in by 08:30."""
    shares = []
    for symbol in symbols:
        symbol_bars = bars.get(symbol) or []
        full = _measure(_window(symbol_bars, PRODUCTION_CUTOFF))["pm_volume"]
        early = _measure(_window(symbol_bars, SERVABLE_CUTOFF))["pm_volume"]
        # A name with no bar before 08:30 kept none of its volume, which is a
        # zero and not a missing value: the socket heard it, later. None here
        # would silently drop exactly the names the cutoff hurts most.
        if full:
            shares.append((early or 0.0) / full)
    return round(statistics.median(shares), 6) if shares else None


# ------------------------------------------------------------------- the run

def reproduces(candidate: dict[str, Any], measured: dict[str, Any],
               gap_pct: float | None, rvol: float | None) -> list[str]:
    """Every way this file's 08:45 pass disagrees with the packet it is reading."""
    faults: list[str] = []

    def check(name: str, mine: Any, theirs: Any, tolerance: float = 0.0) -> None:
        if mine is None and theirs is None:
            return
        if mine is None or theirs is None:
            faults.append(f"{name}: recomputed {mine!r}, packet {theirs!r}")
            return
        if abs(float(mine) - float(theirs)) > tolerance:
            faults.append(f"{name}: recomputed {mine!r}, packet {theirs!r}")

    check("price", measured["price"], candidate.get("price"), 1e-6)
    check("pm_volume", measured["pm_volume"], candidate.get("pm_volume"), 1e-6)
    check("gap_pct", gap_pct, candidate.get("gap_pct"), 1e-4)
    check("pm_rvol", rvol, candidate.get("pm_rvol"), 1e-4)
    return faults


def run_session(session: dict[str, Any], tape: float | None) -> dict[str, Any]:
    day = session["day"]
    packet = session["packet"]
    bars = session["bars"]
    candidates = packet.get("candidates") or []
    symbols = [c["symbol"] for c in candidates]
    shares = _capture_shares(day)
    default_share = _default_share()
    socket = socket_scale(bars, symbols)

    # A scale of zero is not a small denominator, it is no denominator, and
    # dividing by it would publish an infinite RVOL that clears every floor.
    # 2026-08-19 produces exactly that: the collector was late and eight of
    # twelve candidates have no bar at all before 08:30, so the session's
    # median 08:30 share is 0.0. Refused with the reason kept, because a
    # session where the scale cannot be built is a different report from a
    # session where it was built and came out small.
    scales = {"held": 1.0}
    scales_refused: dict[str, str] = {}
    if socket is None:
        scales_refused["socket"] = "no candidate carried any premarket volume"
    elif socket <= 0:
        scales_refused["socket"] = (
            "the session's median 08:30 share of socket volume is 0.0, so more "
            "than half the candidates have no bar before 08:30 at all")
    else:
        scales["socket"] = socket
    if tape is None:
        scales_refused["tape"] = "no usable true-volume row anywhere on disk"
    elif tape <= 0:
        scales_refused["tape"] = "the tape scale came out non positive"
    else:
        scales["tape"] = tape

    arithmetics = {"as_run": False, "current": True}
    stale_limit_minutes = int(_CRIT.number("price_age", "max_price_age_seconds") // 60)

    rows: list[dict[str, Any]] = []
    faults: list[str] = []
    for candidate in candidates:
        symbol = candidate["symbol"]
        symbol_bars = bars.get(symbol) or []
        prior_close = candidate.get("prior_close")
        row: dict[str, Any] = {
            "symbol": symbol,
            "packet_day_eligible": bool(candidate.get("day_eligible")),
            "packet_day_failed": candidate.get("day_failed_conditions") or [],
            "measured": {},
            "cells": {},
        }
        for cutoff in (PRODUCTION_CUTOFF, SERVABLE_CUTOFF):
            measured = _measure(_window(symbol_bars, cutoff))
            price = measured["price"]
            gap_pct = (round((price - prior_close) / prior_close * 100.0, 4)
                       if price is not None and prior_close else None)
            row["measured"][cutoff] = {
                "price": price, "gap_pct": gap_pct,
                "pm_volume": measured["pm_volume"], "bars": measured["bars"],
                "price_time": measured["price_time"],
            }
            for arithmetic, corrected in arithmetics.items():
                share = shares.get(symbol, default_share) if corrected else None
                for scale_name, scale in scales.items():
                    rvol = _rvol(measured["pm_volume"], candidate, share, scale)
                    eligible, failed = _day_screen(candidate, price, gap_pct, rvol)
                    row["cells"][f"{arithmetic}|{scale_name}|{cutoff}"] = {
                        "pm_rvol": rvol, "day_eligible": eligible, "failed": failed,
                    }
                    if (cutoff == PRODUCTION_CUTOFF and arithmetic == "as_run"
                            and scale_name == "held"):
                        faults.extend(
                            f"{symbol} {fault}"
                            for fault in reproduces(candidate, measured, gap_pct, rvol))
                        if eligible != bool(candidate.get("day_eligible")):
                            faults.append(
                                f"{symbol} day_eligible: recomputed {eligible}, "
                                f"packet {bool(candidate.get('day_eligible'))}")
        rows.append(row)

    changes: dict[str, Any] = {}
    for arithmetic in arithmetics:
        for scale_name in scales:
            to_out: list[dict[str, Any]] = []
            to_in: list[dict[str, Any]] = []
            unchanged = 0
            for row in rows:
                before = row["cells"][f"{arithmetic}|{scale_name}|{PRODUCTION_CUTOFF}"]
                after = row["cells"][f"{arithmetic}|{scale_name}|{SERVABLE_CUTOFF}"]
                if before["day_eligible"] and not after["day_eligible"]:
                    to_out.append({"symbol": row["symbol"],
                                   "now_failing": [c for c in after["failed"]
                                                   if c not in before["failed"]],
                                   "rvol_0845": before["pm_rvol"],
                                   "rvol_0830": after["pm_rvol"]})
                elif after["day_eligible"] and not before["day_eligible"]:
                    to_in.append({"symbol": row["symbol"],
                                  "no_longer_failing": [c for c in before["failed"]
                                                        if c not in after["failed"]],
                                  "rvol_0845": before["pm_rvol"],
                                  "rvol_0830": after["pm_rvol"]})
                else:
                    unchanged += 1
            # The RVOL condition on its own, counted beside the whole screen.
            # day_eligible is an AND of five conditions and only one of them
            # moves with the cutoff, so a name already dead on
            # require_above_prior_high absorbs any amount of RVOL damage
            # invisibly. On 2026-08-18 HSAI's RVOL falls by more than half and
            # the screen never notices, because HSAI was below its prior high
            # either way. Counting only the screen would report that morning as
            # untouched, which is true of the OUTPUT and false about the
            # measurement the output rests on. This is the same error as
            # screen_tally folding unmeasured conditions into failed ones.
            rvol_rule = _CRIT.rule("day_setup", "premarket_rvol")
            rvol_out, rvol_in = [], []
            for row in rows:
                before = row["cells"][f"{arithmetic}|{scale_name}|{PRODUCTION_CUTOFF}"]
                after = row["cells"][f"{arithmetic}|{scale_name}|{SERVABLE_CUTOFF}"]
                passed_before = rvol_rule.test(before["pm_rvol"])
                passed_after = rvol_rule.test(after["pm_rvol"])
                if passed_before and not passed_after:
                    rvol_out.append({"symbol": row["symbol"],
                                     "rvol_0845": before["pm_rvol"],
                                     "rvol_0830": after["pm_rvol"]})
                elif passed_after and not passed_before:
                    rvol_in.append({"symbol": row["symbol"],
                                    "rvol_0845": before["pm_rvol"],
                                    "rvol_0830": after["pm_rvol"]})
            changes[f"{arithmetic}|{scale_name}"] = {
                "rvol_condition_passed_0845": sum(
                    1 for r in rows
                    if rvol_rule.test(
                        r["cells"][f"{arithmetic}|{scale_name}|{PRODUCTION_CUTOFF}"]["pm_rvol"])),
                "rvol_condition_passed_0830": sum(
                    1 for r in rows
                    if rvol_rule.test(
                        r["cells"][f"{arithmetic}|{scale_name}|{SERVABLE_CUTOFF}"]["pm_rvol"])),
                "rvol_condition_out": rvol_out,
                "rvol_condition_in": rvol_in,
                "eligible_0845": sum(
                    1 for r in rows
                    if r["cells"][f"{arithmetic}|{scale_name}|{PRODUCTION_CUTOFF}"]["day_eligible"]),
                "eligible_0830": sum(
                    1 for r in rows
                    if r["cells"][f"{arithmetic}|{scale_name}|{SERVABLE_CUTOFF}"]["day_eligible"]),
                "out": to_out, "in": to_in,
                "changed": len(to_out) + len(to_in), "unchanged": unchanged,
            }

    # What the day screen never sees, because the gate sits in front of it. The
    # [Price age] limit is 900 seconds and the documented lag is fifteen
    # minutes, so a window ending at 08:30 read at an 08:45 clock produces a
    # last print that is 900 seconds old or older BY CONSTRUCTION. Counted
    # here rather than folded into the screen, because it is a different
    # failure with a different fix and folding it in would hide it.
    stale = []
    for row in rows:
        stamp = row["measured"][SERVABLE_CUTOFF]["price_time"]
        if stamp is None:
            stale.append({"symbol": row["symbol"], "last_print": None,
                          "age_seconds_at_0845": None})
            continue
        minute = _minutes(str(stamp)[11:16])
        age = (_minutes(PRODUCTION_CUTOFF) - minute) * 60
        if age >= stale_limit_minutes * 60:
            stale.append({"symbol": row["symbol"], "last_print": stamp,
                          "age_seconds_at_0845": age})

    volumes = [(r["measured"][SERVABLE_CUTOFF]["pm_volume"] or 0.0,
                r["measured"][PRODUCTION_CUTOFF]["pm_volume"] or 0.0) for r in rows]
    kept = [early / full for early, full in volumes if full]

    return {
        "day": day,
        "candidates": len(rows),
        "capture_shares_measured": sum(1 for s in symbols if s in shares),
        "socket_scale": socket,
        "scales": scales,
        "scales_refused": scales_refused,
        "reproduction_faults": faults,
        "volume_kept_by_0830": {
            "median": round(statistics.median(kept), 6) if kept else None,
            "min": round(min(kept), 6) if kept else None,
            "max": round(max(kept), 6) if kept else None,
        },
        "stale_at_0830": stale,
        "changes": changes,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="dump the full result")
    args = parser.parse_args(argv)

    usable, refused = sessions()
    tape = tape_scale()
    results = [run_session(session, tape.get("scale")) for session in usable]

    # The pre-registration's own claim, turned into a number. "Those are the
    # densest fifteen minutes of the premarket" is a statement about volume
    # PER MINUTE, and it is separately true or false from whether the screen
    # notices. Both are computed, because the first being true is the reason
    # the second is worth checking and is not an answer to it.
    density = None
    if tape.get("scale") is not None:
        premarket_minutes = _minutes(PRODUCTION_CUTOFF) - _minutes(
            _CRIT.clock_text("baseline", "session_start"))
        lost_minutes = _minutes(PRODUCTION_CUTOFF) - _minutes(SERVABLE_CUTOFF)
        share_of_volume = 1.0 - tape["scale"]
        share_of_clock = lost_minutes / premarket_minutes
        density = {
            "lost_minutes": lost_minutes,
            "premarket_minutes": premarket_minutes,
            "share_of_clock": round(share_of_clock, 6),
            "share_of_volume": round(share_of_volume, 6),
            "times_an_average_premarket_minute": round(
                share_of_volume / share_of_clock, 4),
            "basis": ("the tape scale, so this is 04:00 to 08:45 on Alpaca's "
                      "consolidated tape and not the socket's 07:20 window"),
        }

    payload = {
        "density_of_the_lost_minutes": density,
        "question": ("DECISIONS.md 2026-08-22, the Monday pre-registration's third "
                     "question: whether a screen computed to 08:30 is worth having"),
        "production_cutoff": PRODUCTION_CUTOFF,
        "servable_cutoff": SERVABLE_CUTOFF,
        "sessions_used": [r["day"] for r in results],
        "sessions_refused": refused,
        "tape_scale": tape,
        "per_session": results,
    }

    out = config.DATA_DIR / f"{PATH_STEM}.json"
    out.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=1, sort_keys=True))
        return 0

    print(f"08:45 against 08:30, {len(results)} session(s), "
          f"{sum(r['candidates'] for r in results)} candidate name-sessions")
    print()
    for row in refused:
        print(f"  refused {row['day']}: {row['why']}")
    print()
    faults = [f for r in results for f in r["reproduction_faults"]]
    if faults:
        print(f"REPRODUCTION FAILED, {len(faults)} disagreement(s) with the packets. "
              "The 08:30 column below is not evidence about the cutoff.")
        for fault in faults[:30]:
            print(f"  {fault}")
    else:
        print("Reproduction: every 08:45 recomputation matches its packet's own "
              "price, gap, premarket volume, RVOL and day_eligible.")
    print()
    if tape.get("scale") is not None:
        print(f"tape scale {tape['scale']:.4f} from {tape['n']} true-volume row(s) "
              f"on {', '.join(tape['days'])}, spread {tape['min']:.4f} to "
              f"{tape['max']:.4f}")
    else:
        print(f"tape scale unavailable: {tape.get('why')}")
    if density:
        print(f"the fifteen minutes given up are {density['share_of_clock']:.1%} "
              f"of the premarket clock and carry {density['share_of_volume']:.1%} "
              f"of its volume, "
              f"{density['times_an_average_premarket_minute']:.2f}x an average "
              "premarket minute")
    print()
    header = (f"{'session':<12}{'names':>6}{'kept vol':>10}  "
              f"{'arithmetic':<10}{'denom':<8}"
              f"{'elig 0845':>10}{'elig 0830':>10}{'out':>5}{'in':>4}"
              f"{'rvol 0845':>11}{'rvol 0830':>10}{'out':>5}{'in':>4}")
    print(header)
    print("-" * len(header))
    for result in results:
        kept = result["volume_kept_by_0830"]["median"]
        first = True
        for key, change in sorted(result["changes"].items()):
            arithmetic, scale_name = key.split("|")
            print(f"{result['day'] if first else '':<12}"
                  f"{result['candidates'] if first else '':>6}"
                  f"{(f'{kept:.3f}' if first and kept is not None else ''):>10}  "
                  f"{arithmetic:<10}{scale_name:<8}"
                  f"{change['eligible_0845']:>10}{change['eligible_0830']:>10}"
                  f"{len(change['out']):>5}{len(change['in']):>4}"
                  f"{change['rvol_condition_passed_0845']:>11}"
                  f"{change['rvol_condition_passed_0830']:>10}"
                  f"{len(change['rvol_condition_out']):>5}"
                  f"{len(change['rvol_condition_in']):>4}")
            first = False
        for name, why in sorted(result.get("scales_refused", {}).items()):
            print(f"{'':<12}{'':>6}{'':>10}  denominator '{name}' refused: {why}")
        print(f"{'':<12}{'':>6}{'':>10}  stale at 08:30 under the "
              f"[Price age] 900s limit: {len(result['stale_at_0830'])} "
              f"of {result['candidates']}")
        print()

    print("totals across sessions")
    totals: dict[str, dict[str, int]] = {}
    for result in results:
        for key, change in result["changes"].items():
            bucket = totals.setdefault(key, {"0845": 0, "0830": 0, "out": 0, "in": 0,
                                              "r0845": 0, "r0830": 0,
                                              "rout": 0, "rin": 0, "sessions": 0})
            bucket["0845"] += change["eligible_0845"]
            bucket["0830"] += change["eligible_0830"]
            bucket["out"] += len(change["out"])
            bucket["in"] += len(change["in"])
            bucket["r0845"] += change["rvol_condition_passed_0845"]
            bucket["r0830"] += change["rvol_condition_passed_0830"]
            bucket["rout"] += len(change["rvol_condition_out"])
            bucket["rin"] += len(change["rvol_condition_in"])
            bucket["sessions"] += 1
    for key, bucket in sorted(totals.items()):
        arithmetic, scale_name = key.split("|")
        print(f"  {arithmetic:<10}{scale_name:<8}"
              f"day eligible {bucket['0845']:>3} at 08:45, "
              f"{bucket['0830']:>3} at 08:30, "
              f"{bucket['out']} out, {bucket['in']} in"
              f"   |   RVOL condition cleared {bucket['r0845']:>3} and "
              f"{bucket['r0830']:>3}, {bucket['rout']} out, {bucket['rin']} in")
        # A comparison whose 08:45 side is empty cannot produce a name that
        # changes side, so its zero is not a finding about the cutoff. Said
        # here rather than left for a reader to notice, because a row of zeros
        # beside a row of zeros is exactly how a null instrument gets read as
        # a result. The as_run arithmetic is null for this reason: the raw
        # socket count over a consolidated baseline could not reach the 1.5
        # floor at ANY cutoff, which is the defect the capture correction
        # exists to fix.
        if bucket["0845"] == 0:
            print(f"{'':<20}NULL for the screen: nothing was day eligible at "
                  "08:45 under this pair, so no name could leave it. The zero "
                  "above is about the arithmetic, not the cutoff.")
    print()
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
