"""Does subscribing to 50 symbols starve the feed? Measured, not argued.

The collector's premarket volume disagrees with EODHD's own 1m bars by about a
factor of ten, and doc/research/COLLECTOR_VOLUME.md establishes the check is
sound and the collector is at fault. What it does not establish is WHY.

The one structural difference between the sessions that look right and the ones
that do not is the size of the subscription:

    2026-08-13  38 symbols   270,086 trades   SPY 727 trades/min (open market)
    2026-08-14  38 symbols   191,194 trades   SPY 171 trades/min (premarket)
    2026-08-17  50 symbols    33,489 trades   SPY 5.8 trades/min
    2026-08-18  50 symbols    36,530 trades   SPY 5.3 trades/min

Fifty is the documented cap. Nothing else changed: one connection, zero
reconnects, no status frames, trade sizes plausible in every session, and
messages equal to trades folded, so nothing is lost inside the collector. The
collector's own source already carries the suspicion, written the day before
the first fifty symbol morning: "the throughput has only ever been measured at
thirty eight, so this is the run that has to be able to say which names the
socket actually served."

That is a correlation across two sessions each side. This turns it into a
measurement.

Method. One watch set present in BOTH arms, so the comparison is the same
symbols against themselves. Arm A subscribes to the watch set alone, well under
the cap. Arm B subscribes to the watch set plus enough filler to reach the cap.
The arms alternate rather than running back to back, because premarket rates
climb through the morning and two consecutive blocks would confound the
subscription size with the clock. Each arm is a fresh connection, and the first
message per symbol is discarded because the server replays a stale last trade
on subscribe.

Run it outside the collector's window, which is 07:20 to 09:25 ET. Before it
or after it are both fine and the tool refuses anything that would overlap: the
fifty symbol pool is account wide, so a probe holding slots would starve the
morning it is trying to explain. After 09:25 the tape is denser than premarket,
which makes the ratio easier to measure and is a different tape from the one
the defect appears in, so a positive result there is worth confirming in a
premarket run before acting on it.

    python -m research.probe_socket_cap --cycles 6 --seconds 120

Costs nothing on the vendor's counter. Measured 2026-08-13: connections,
subscribe frames and reconnects moved the account counter by exactly zero.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import ssl
import sys
import time
from typing import Any

import websocket

from core import config
from core import files
from core import criteria
from core import ettime
from collect import collect_premarket as collector

_CRIT = criteria.load()


# Every key the collector's own _handle_message reads off a trade message.
# Written here rather than imported because the point of the census is to
# compare what the parser looks at against what the feed sends, and a list
# derived from the parser at runtime would agree with it by construction.
# Checked against src/collect/collect_premarket.py _handle_message on
# 2026-08-19: it reads s, p, v, t, dp and ms, and nothing else.
COLLECTOR_READS = ("s", "p", "v", "t", "dp", "ms")

# The one off exchange signal the collector currently understands. It has been
# false in every bar the project has ever written: dark_pool_volume is 0.0 in
# every row of every session file. Either the feed never sets it or it sets
# something else, and those are the two answers this census separates.
COLLECTOR_OFF_EXCHANGE_KEY = "dp"

# Values that mark NOTHING. An empty condition list and an explicit False are
# the feed answering the off exchange question in the negative, and counting
# them as codes the collector ignores turns an answer into a false lead.
_SAYS_NOTHING = ("[]", "False", "None", "", "0", "0.0")

# Keys whose values are small enough to tabulate in full. A condition code
# list, an exchange id and a market status are all short; a price is not.
CENSUS_KEYS = ("c", "cond", "conditions", "x", "e", "dp", "ms", "z", "trf", "trfi")


def _census_values(message: dict[str, Any]) -> list[tuple[str, str]]:
    """Every (key, value) worth counting on one trade message.

    A list valued key contributes one entry per element, because a message
    carrying conditions [12, 37] is evidence about 12 and about 37 separately
    and folding it to the string "[12, 37]" loses exactly the fact being
    looked for.
    """
    out: list[tuple[str, str]] = []
    for key in CENSUS_KEYS:
        if key not in message:
            continue
        value = message[key]
        if isinstance(value, (list, tuple)):
            if not value:
                out.append((key, "[]"))
            for item in value:
                out.append((key, str(item)))
        else:
            out.append((key, str(value)))
    return out


def filler_symbols(watch: list[str], want: int) -> list[str]:
    """Symbols to pad arm B up to the cap, taken from today's watchlist.

    The real subscription list if there is one, because the question is about
    the load the collector actually puts on the socket. Falls back to the
    universe so the probe still runs on a day discover has not fired.
    """
    pool: list[str] = []
    subs = collector.read_subscriptions()
    if subs:
        pool = [s for s in subs.get("symbols", []) if s not in watch]
    if len(pool) < want:
        try:
            universe = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            universe = {}
        for row in universe.get("symbols", []):
            symbol = str(row.get("symbol") or "").upper()
            if symbol and symbol not in watch and symbol not in pool:
                pool.append(symbol)
            if len(pool) >= want:
                break
    return pool[:want]


def run_arm(symbols: list[str], watch: set[str], seconds: float) -> dict[str, Any]:
    """One connection, one subscription, one timed listen. Returns per symbol counts."""
    counts: dict[str, int] = {s: 0 for s in watch}
    volume: dict[str, float] = {s: 0.0 for s in watch}
    replayed: dict[str, int] = {s: 0 for s in watch}
    # The off exchange question, measured rather than assumed. flagged counts
    # messages the collector's own rule would call a dark pool print, and the
    # census records every value of every code-like key the feed sends, so a
    # code the parser has never heard of shows up as itself rather than as a
    # missing number.
    flagged: dict[str, int] = {s: 0 for s in watch}
    flagged_volume: dict[str, float] = {s: 0.0 for s in watch}
    census: dict[str, collections.Counter] = {s: collections.Counter() for s in watch}
    keys_seen: collections.Counter = collections.Counter()
    status: list[dict[str, Any]] = []
    total = 0

    sslopt: dict[str, Any] = {"context": config.tls_context(),
                              "cert_reqs": ssl.CERT_REQUIRED}
    socket = websocket.create_connection(collector._ws_url(), sslopt=sslopt,
                                         timeout=15)
    try:
        socket.settimeout(collector.AUTH_WAIT_S)
        deadline = time.time() + collector.AUTH_WAIT_S
        authorized = False
        while time.time() < deadline:
            try:
                raw = socket.recv()
            except websocket.WebSocketTimeoutException:
                break
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("status_code") == 200:
                authorized = True
                break
        if not authorized:
            raise ConnectionError("no authorization frame arrived")

        socket.send(json.dumps({
            "action": "subscribe",
            "symbols": ",".join(collector._bare(s) for s in symbols),
        }))
        socket.settimeout(1.0)
        refused = False

        # The clock starts AFTER the subscribe frame goes out, and anything
        # stamped before it is the replay rather than the tape.
        started = time.time()
        stop_at = started + seconds
        while time.time() < stop_at:
            try:
                raw = socket.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except (websocket.WebSocketConnectionClosedException, OSError) as exc:
                status.append({"error": config.scrub_secrets(exc)})
                break
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if "s" not in message or "p" not in message:
                if message.get("status_code") != 200:
                    status.append(message)
                    # A refused arm measures zero for a reason that has nothing
                    # to do with the question, and reporting that zero as a
                    # rate would be the probe answering its own question wrong.
                    if message.get("status_code") in collector._FATAL_STATUS_CODES:
                        refused = True
                        break
                continue
            total += 1
            symbol = collector._full(str(message["s"]))
            if symbol not in counts:
                continue
            try:
                stamp = float(message.get("t") or 0) / 1000.0
                size = float(message.get("v") or 0)
            except (TypeError, ValueError):
                continue
            if stamp < started:
                replayed[symbol] += 1
                continue
            counts[symbol] += 1
            volume[symbol] += size
            keys_seen.update(message.keys())
            for key, value in _census_values(message):
                census[symbol][f"{key}={value}"] += 1
            if message.get(COLLECTOR_OFF_EXCHANGE_KEY):
                flagged[symbol] += 1
                flagged_volume[symbol] += size
    finally:
        try:
            socket.close()
        except Exception:
            pass

    return {
        "subscribed": len(symbols),
        "seconds": seconds,
        "refused": refused,
        "messages_total": total,
        "counts": counts,
        "volume": volume,
        "replayed": replayed,
        "off_exchange": flagged,
        "off_exchange_volume": flagged_volume,
        "census": {s: dict(c) for s, c in census.items()},
        "keys_seen": dict(keys_seen),
        "status": status,
    }


def _report_off_exchange(runs: list[dict[str, Any]], watch: list[str]) -> None:
    """Two of the three numbers, and the census that says what the third means.

    The third number the question wants is the vendor's trade COUNT for the
    same minutes, and EODHD's 1m intraday bars do not carry one: a bar is
    timestamp, gmtoffset, datetime, open, high, low, close and volume, checked
    2026-08-19. Volume is the closest thing the vendor publishes and it is what
    compare_to_vendor() uses, with the substitution named rather than quietly
    made.
    """
    live = [r for r in runs if not r.get("refused")]
    print("")
    print("Off exchange prints the collector's own rule would recognise")
    print(f"  {'symbol':<10} {'messages':>10} {'flagged':>9} {'flagged %':>10} "
          f"{'shares':>14} {'flagged shares':>15}")
    for symbol in watch:
        msgs = sum(r["counts"][symbol] for r in live)
        scored = [r for r in live if "off_exchange" in r]
        flag = sum(r["off_exchange"].get(symbol, 0) for r in scored)
        vol = sum(r["volume"][symbol] for r in live)
        fvol = sum(r["off_exchange_volume"].get(symbol, 0.0)
                   for r in live if "off_exchange_volume" in r)
        if not scored:
            print(f"  {symbol:<10} {msgs:>10,} {'n/a':>9} {'n/a':>10} "
                  f"{vol:>14,.0f} {'n/a':>15}")
            continue
        pct = (flag / msgs * 100.0) if msgs else float("nan")
        print(f"  {symbol:<10} {msgs:>10,} {flag:>9,} {pct:>9.2f}% "
              f"{vol:>14,.0f} {fvol:>15,.0f}")

    keys: collections.Counter = collections.Counter()
    counted = [run for run in live if "keys_seen" in run]
    for run in counted:
        keys.update(run["keys_seen"])
    read = [k for k in keys if k in COLLECTOR_READS]
    ignored = [k for k in keys if k not in COLLECTOR_READS]
    print("")
    print("Keys the feed sent on trade messages")
    if not counted:
        print("  NOT MEASURED, this result predates the key census.")
    else:
        print(f"  read by the collector : {', '.join(sorted(read)) or 'none'}")
        print(f"  IGNORED by the collector: {', '.join(sorted(ignored)) or 'none'}")

    # A run recorded before the census existed carries no census key at all,
    # and that is not the same answer as a census that found nothing. Reading
    # it as "the feed sent no codes" would be this tool making the exact
    # mistake it was built to detect, so the absence is reported as absence.
    measured = [run for run in live if "census" in run]
    codes: collections.Counter = collections.Counter()
    for run in measured:
        for per_symbol in run["census"].values():
            codes.update(per_symbol)
    print("")
    print("Every code-like value the feed sent, with counts")
    if not measured:
        print("  NOT MEASURED. This probe result was written before the census "
              "existed, so it says nothing about what the feed sends. Rerun the "
              "probe to answer the question.")
    elif not codes:
        print("  NONE. The feed sent no condition code, no exchange id and no "
              "dark pool flag on any trade message. If the vendor volume for "
              "these minutes is far above the socket volume, the shortfall is "
              "structural: the trades stream is a subset of the consolidated "
              "tape and no change to the collector's parser reaches it.")
    else:
        for value, count in codes.most_common(40):
            key = value.split("=", 1)[0]
            mark = "  <- read" if key in COLLECTOR_READS else "  <- IGNORED"
            print(f"  {value:<24} {count:>9,}{mark}")
        print("")
        # A value that says nothing is here is the feed ANSWERING the off
        # exchange question, not a code the parser is missing. c=[] is an empty
        # condition list and dp=False is an explicit not a dark pool print. On
        # 2026-08-21 all 123 messages carried both, and the line that used to
        # print here named "a code under IGNORED" as the fixable case, which
        # pointed the only reader this tool has at a parser change that does
        # not exist. The census exists to separate a feed that sends nothing
        # from a parser that drops something, so it must not blur the two in
        # its own summary line.
        carrying = [v for v in codes if v.split("=", 1)[-1] not in _SAYS_NOTHING]
        droppable = sorted(v for v in carrying
                           if v.split("=", 1)[0] not in COLLECTOR_READS)
        if not carrying:
            print("  NONE of those values marks anything. Every one is the "
                  "feed saying there is no condition and no dark pool print, "
                  "so a shortfall against vendor volume is STRUCTURAL: the "
                  "trades stream is a subset of the consolidated tape and no "
                  "change to the collector's parser reaches it.")
        elif droppable:
            print("  A code under IGNORED that marks an off exchange print is "
                  "the fixable case: the feed carries the volume and the "
                  "parser drops it, which is why dark_pool_volume is empty in "
                  f"every bar. Candidates: {', '.join(droppable)}")
        else:
            print("  Every value that marks anything sits under a key the "
                  "collector already reads, so there is no parser fix here.")


def _report_delivery(runs: list[dict[str, Any]],
                     watch: list[str]) -> dict[str, Any]:
    """Message rate under the cap against message rate without it.

    A function rather than a stretch of main() so the reading can be
    re-derived from an archived payload with no socket, which is what
    a claim needs and what re-reading the 2026-08-19 result under the
    evidence floor needed. runs and watch are exactly the keys the
    payload already stores, so any past result can be re-read under
    any later rule.
    """
    # The RAW COUNTS are on the page beside the rates, because every ratio in
    # this table is only as good as the smaller of the two numbers behind it
    # and a rate per second hides that completely. On 2026-08-21 IWM printed
    # 0.14 off 49 messages against 9, and UUP printed 0.00 off one against
    # none, and the old table showed 0.14 and 0.00 with nothing to say so.
    print("Per symbol messages per second, watch set only, A against B")
    print(f"  {'symbol':<10} {'A msgs':>7} {'B msgs':>7} {'A msg/s':>10} "
          f"{'B msg/s':>10} {'B/A':>8} {'A shares/s':>12} {'B shares/s':>12}")
    min_messages = _CRIT.integer("collector", "min_probe_messages_per_arm")
    verdict_ratios: list[float] = []
    thin: list[tuple[int, str]] = []
    for symbol in watch:
        a = [r for r in runs if r["arm"] == "A" and not r.get("refused")]
        b = [r for r in runs if r["arm"] == "B" and not r.get("refused")]
        a_secs = sum(r["seconds"] for r in a) or 1.0
        b_secs = sum(r["seconds"] for r in b) or 1.0
        a_msgs = sum(r["counts"][symbol] for r in a)
        b_msgs = sum(r["counts"][symbol] for r in b)
        a_rate = a_msgs / a_secs
        b_rate = b_msgs / b_secs
        a_vol = sum(r["volume"][symbol] for r in a) / a_secs
        b_vol = sum(r["volume"][symbol] for r in b) / b_secs
        ratio = (b_rate / a_rate) if a_rate else float("nan")
        enough = min(a_msgs, b_msgs) >= min_messages
        if a_rate and enough:
            verdict_ratios.append(ratio)
        elif a_rate:
            thin.append((min(a_msgs, b_msgs), symbol))
        print(f"  {symbol:<10} {a_msgs:>7,} {b_msgs:>7,} {a_rate:>10.2f} "
              f"{b_rate:>10.2f} {ratio:>8.2f} {a_vol:>12.1f} {b_vol:>12.1f}"
              f"{'' if enough or not a_rate else '   <- too thin for a ratio'}")

    # The instrument's OWN noise, measured from the cycles this run already
    # collected rather than assumed. The two arms are SEQUENTIAL, never
    # simultaneous, so a B/A ratio carries whatever the tape did between them
    # as well as whatever the cap did. Each symbol's ratio is recomputed per
    # cycle and the spread of those is how far the same measurement moves when
    # nothing about the cap changed. A median that sits inside that spread is
    # not a reading, and on 2026-08-19 the well measured symbols still moved by
    # 1.4 to 2.4 times across four cycles, which is the same size as the effect
    # the probe is asked to detect.
    spreads: list[float] = []
    for symbol in watch:
        per_cycle: list[float] = []
        for cycle in sorted({r["cycle"] for r in runs}):
            paired = {r["arm"]: r for r in runs if r["cycle"] == cycle}
            leg_a, leg_b = paired.get("A"), paired.get("B")
            if not leg_a or not leg_b:
                continue
            count_a = leg_a["counts"][symbol]
            count_b = leg_b["counts"][symbol]
            if min(count_a, count_b) < min_messages:
                continue
            rate_a = count_a / (leg_a["seconds"] or 1.0)
            rate_b = count_b / (leg_b["seconds"] or 1.0)
            if rate_a:
                per_cycle.append(rate_b / rate_a)
        if len(per_cycle) >= 2 and min(per_cycle) > 0:
            spreads.append(max(per_cycle) / min(per_cycle))
    spreads.sort()
    verdict_ratios.sort()
    noise = spreads[len(spreads) // 2] if spreads else None
    median = verdict_ratios[len(verdict_ratios) // 2] if verdict_ratios else None
    supported = bool(median is not None and noise is not None
                     and not (1.0 / noise) <= median <= noise)

    print("")
    # Sorted by the SMALLER arm, descending, so "the best being" is true of
    # what follows it and the most informative symbol is the one a reader sees
    # first. Watch set order put UUP's zero in the same breath as IWM's nine.
    thin.sort(reverse=True)
    named = ", ".join(f"{symbol} on {count}" for count, symbol in thin)
    if median is None:
        print(f"probe: NO READING. No watched symbol carried {min_messages:,} "
              "messages on BOTH arms"
              + (f", the best being {named}" if thin else "")
              + ". A B/A ratio off a handful of messages measures when trades "
              "happened, not whether the cap starved delivery, and the arms "
              "ran one after the other rather than at once.")
        print("probe: what would change that is a richer tape or more cycles, "
              "not a different reading of these numbers. The premarket tape "
              "this probe exists to measure may simply be too thin to carry "
              "the question, which is itself an answer worth recording.")
    else:
        print(f"probe: median B/A message rate is {median:.2f}, over the "
              f"{len(verdict_ratios)} of {len(watch)} watched symbols that "
              f"carried {min_messages:,} messages on both arms"
              + (f". Too thin to count: {named}" if thin else ""))
        # Stated as a reading, not a verdict. What counts as starved is a
        # judgement about the collector, and it belongs in DECISIONS.md with
        # the numbers beside it rather than in a threshold here. What DOES
        # belong here is refusing to state a reading the run cannot support,
        # and the two ways it cannot are different and must not share a
        # sentence: an unmeasured noise floor is not a median inside one.
        if noise is None:
            print("probe: NO NOISE FLOOR. Fewer than two cycles carried "
                  "enough messages for any symbol, so how far this ratio "
                  "moves on its own went unmeasured on this run.")
            print("probe: the median above is therefore a number and not a "
                  "reading. There is nothing to read it against, so this run "
                  "is not evidence either way about the cap.")
        elif not supported:
            print(f"probe: those same symbols' own B/A moved by a factor of "
                  f"{noise:.1f} across this run's cycles with nothing about "
                  "the cap changing. That is the instrument's noise, measured "
                  "here rather than assumed.")
            print("probe: the median sits INSIDE that noise, so this run "
                  "separates nothing. It is not evidence that the cap starves "
                  "delivery and not evidence that it does not.")
        else:
            print(f"probe: those same symbols' own B/A moved by a factor of "
                  f"{noise:.1f} across this run's cycles, and the median sits "
                  "OUTSIDE that, so the run separates the two arms.")
            print("probe: a ratio near 1 means the cap does not starve "
                  "delivery and the volume gap has another cause. A ratio well "
                  "below 1 means it does, and the fix is to subscribe to fewer "
                  "symbols or to split the list across connections.")
    return {
        "min_messages_per_arm": min_messages,
        "symbols_with_enough": len(verdict_ratios),
        "symbols_watched": len(watch),
        "median_b_over_a": median,
        "own_noise_factor": noise,
        "reading_supported": supported,
    }


def _flagged_over(legs: list[dict[str, Any]], symbol: str) -> tuple[int, bool]:
    """Off exchange prints for one symbol, and whether any run recorded them.

    Returns (count, recorded). run.get("off_exchange", {}).get(symbol, 0)
    returned 0 for a run that HAD the field and saw nothing and for a run that
    never had the field at all, and those are opposite facts. The 2026-08-19
    payload, the only probe result that exists, predates off_exchange entirely:
    its runs carry arm, counts, cycle, messages_total, refused, replayed,
    seconds, started_at, status, subscribed and volume, and nothing else. Read
    through the old expression it printed a flagged column of zero for every
    symbol in both arms, which is the reading the whole off exchange question
    turns on, and it was an absence dressed as a measurement.
    """
    count = 0
    recorded = False
    for run in legs:
        if "off_exchange" not in run:
            continue
        recorded = True
        count += run["off_exchange"].get(symbol, 0)
    return count, recorded


def _vendor_shares_over(bars: dict[int, float], start: dt.datetime,
                        seconds: float) -> float:
    """Vendor shares for exactly the seconds an arm listened, not for whole bars.

    A 120 second arm that does not start on a minute boundary overlaps three
    one minute bars, and summing all three charged 180 seconds of tape against
    120 seconds of socket. That inflated the denominator by half for no reason
    but where the clock happened to fall, and it inflated it silently: the
    socket share printed below is the number this probe exists to produce, and
    a reading of 40 percent would have been published for a feed delivering 60.
    Each bar now contributes only the fraction of itself the arm covered, so
    the weights sum to seconds/60 whatever the alignment.

    Pro rating spreads a bar's volume evenly across its minute, which is an
    assumption rather than a measurement: EODHD publishes nothing finer than a
    minute, so the partial minutes at each end of an arm cannot be read any
    other way. Only the two end bars are ever partial, so at 120 seconds the
    assumption carries at most one minute of the three and the whole middle
    bar is exact. Starting each arm on a minute boundary would remove it
    entirely and is worth doing if this probe is ever run again.
    """
    lo = float(ettime.epoch_s(start))
    hi = lo + float(seconds)
    total = 0.0
    for ts, volume in bars.items():
        overlap = min(float(ts) + 60.0, hi) - max(float(ts), lo)
        if overlap > 0.0:
            total += volume * overlap / 60.0
    return total


def compare_to_vendor(path: pathlib.Path) -> int:
    """The third number: what EODHD's own bars say those minutes traded.

    Separate from the probe run because the probe runs premarket and the vendor
    has not published the current session by the time it finishes. This costs
    one intraday call per watched symbol, which is the only quota this tool has
    ever spent.
    """
    from core import eodhd

    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = [r for r in payload["runs"] if not r.get("refused")]
    if not runs:
        print("probe: every arm was refused, so there is nothing to compare.")
        return 1
    starts = [dt.datetime.fromisoformat(r["started_at"]) for r in runs]
    ends = [s + dt.timedelta(seconds=r["seconds"]) for s, r in zip(starts, runs)]
    api = eodhd.client()

    print(f"probe: comparing {path.name} against EODHD 1m bars for "
          f"{ettime.hhmm(min(starts))} to {ettime.hhmm(max(ends))} ET")
    print("probe: the vendor bar carries no trade count, only volume, so the "
          "third number is vendor SHARES for the same minutes. The substitution "
          "is the vendor's, not this tool's. A bar the arm only partly covered "
          "contributes only that fraction of itself, which is this tool's "
          "assumption and is described in _vendor_shares_over.")
    print("probe: split by arm, because a single blended percentage cannot "
          "answer an A/B. The arms listened to the same symbols minutes apart, "
          "so read A against B first.")
    print("")
    print(f"  {'symbol':<8} {'arm':>3} {'socket msgs':>12} {'flagged':>9} "
          f"{'socket shares':>14} {'vendor shares':>14} {'socket %':>10}")
    unrecorded = False
    for symbol in payload["watch"]:
        rows, error = api.intraday(symbol, min(starts) - dt.timedelta(minutes=2),
                                   max(ends) + dt.timedelta(minutes=2), "1m")
        if error or not rows:
            print(f"  {symbol:<8} {'':>3} vendor bars unavailable "
                  f"({error or 'no rows'}). "
                  "EODHD publishes a session after it closes.")
            continue
        bars = {int(r["timestamp"]): float(r.get("volume") or 0.0)
                for r in rows if r.get("timestamp") is not None}
        for arm in ("A", "B"):
            legs = [(run, start) for run, start in zip(runs, starts)
                    if run.get("arm") == arm]
            if not legs:
                print(f"  {symbol:<8} {arm:>3} every arm was refused or none ran, "
                      "nothing to compare")
                continue
            msgs = 0
            socket_shares = vendor_shares = 0.0
            for run, start in legs:
                msgs += run["counts"].get(symbol, 0)
                socket_shares += run["volume"].get(symbol, 0.0)
                vendor_shares += _vendor_shares_over(bars, start, run["seconds"])
            flag, flag_recorded = _flagged_over([run for run, _ in legs], symbol)
            if not flag_recorded:
                unrecorded = True
            shown = f"{flag:,}" if flag_recorded else "not rec"
            share = (socket_shares / vendor_shares * 100.0) if vendor_shares else float("nan")
            print(f"  {symbol:<8} {arm:>3} {msgs:>12,} {shown:>9} "
                  f"{socket_shares:>14,.0f} {vendor_shares:>14,.0f} {share:>9.2f}%")
    print("")
    if unrecorded:
        print("probe: flagged reads 'not rec' where the run predates the "
              "off_exchange counter. That is an ABSENCE of evidence about off "
              "exchange prints, not evidence that there were none, and the "
              "paragraph below forks on exactly that. A run taken after "
              "2026-08-20 records off_exchange, off_exchange_volume, census "
              "and keys_seen, and can answer it.")
        print("")
    print("probe: A against B is the first read. A near 100% beside a B far "
          "below it is the cap starving the feed, which the collector can act "
          "on by subscribing to fewer names. Two arms alike says the "
          "subscription size is not the cause, and the rest of this paragraph "
          "then applies to both.")
    print("")
    print("probe: a socket share near 100% with no flagged prints means the feed "
          "and the tape agree and there was never anything to find. A socket "
          "share far below 100% with no flagged prints and no ignored condition "
          "code means the trades stream omits off exchange volume, which no "
          "collector change reaches. A socket share far below 100% WITH flagged "
          "prints or an ignored code means the parser is dropping volume the "
          "feed delivered, which is a bug and is fixable.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="A/B the websocket's delivery under a small and a capped subscription.")
    parser.add_argument("--cycles", type=int, default=6,
                        help="A/B pairs to run. Six at two minutes is about 25 minutes.")
    parser.add_argument("--seconds", type=float, default=120.0,
                        help="Seconds to listen in each arm.")
    parser.add_argument("--settle", type=float, default=90.0,
                        help="Seconds to wait between arms while the account "
                             "releases the previous arm's slots. Not optional "
                             "padding: the cap is account wide and a closed "
                             "connection keeps its symbols for a while. On "
                             "2026-08-19 the collector reconnected one second "
                             "after a drop and was refused, and a hand restart "
                             "105 seconds later was not. An arm B that asked "
                             "for 50 while arm A's 8 were still held would be "
                             "refused and would measure a zero that means "
                             "nothing.")
    parser.add_argument("--watch", default=None,
                        help="Comma separated watch set. Defaults to the CRITERIA "
                             "context symbols, which trade every premarket.")
    parser.add_argument("--compare", default=None, metavar="FILE",
                        help="Skip the socket entirely and compare an existing "
                             "probe result against EODHD's 1m bars for the same "
                             "minutes. Run this the session AFTER the probe, "
                             "because the vendor does not publish a session "
                             "until it is over. Name a file in data/ or a path.")
    args = parser.parse_args(argv)

    if args.compare:
        target = pathlib.Path(args.compare)
        if not target.exists():
            target = config.DATA_DIR / args.compare
        if not target.exists():
            print(f"probe: no such probe result: {args.compare}")
            return 1
        return compare_to_vendor(target)

    watch = ([collector._full(s) for s in args.watch.split(",") if s.strip()]
             if args.watch else
             [collector._full(s) for s in _CRIT.text_list("collector", "context_symbols")])
    cap = collector.MAX_SUBSCRIPTIONS
    fillers = filler_symbols(watch, cap - len(watch))
    if len(watch) + len(fillers) < cap:
        print(f"probe: only {len(watch) + len(fillers)} symbols available, "
              f"the capped arm will not reach {cap}. The comparison is still valid "
              "but the B arm is not at the cap, so say so when reporting it.")

    # The constraint is the COLLECTOR'S WINDOW, not a fixed hour. Written as
    # 07:10 first, which was the only free slot when this was meant to run
    # before the morning; the power was off at 06:20 on 2026-08-19 and the run
    # was lost, and the fixed hour then refused every remaining moment of a day
    # in which the socket was free from 09:25 onward. The rule is that the
    # probe must not hold slots while the collector wants them, and the
    # collector's own configured window says exactly when that is.
    now = ettime.now_et()
    opens = ettime.at_hm(now.date(), _CRIT.clock("collector", "start_time"))
    closes = ettime.at_hm(now.date(), _CRIT.clock("collector", "stop_time"))
    finishes = now + dt.timedelta(
        seconds=args.cycles * (args.seconds + args.settle) * 2 + 60)
    if opens <= now <= closes or opens <= finishes <= closes:
        print(f"probe: REFUSING to run. The collector's window is "
              f"{_CRIT.clock_text('collector', 'start_time')} to "
              f"{_CRIT.clock_text('collector', 'stop_time')} ET and this run would "
              f"end at {ettime.hhmm(finishes)}. The fifty symbol pool is account "
              "wide, so a probe holding slots would starve the morning it is "
              "meant to explain.")
        return 1

    small = watch
    capped = watch + fillers
    print(f"probe: watch set {len(watch)}, arm A subscribes {len(small)}, "
          f"arm B subscribes {len(capped)} (cap {cap})")
    print(f"probe: {args.cycles} alternating cycles of {args.seconds:g}s per arm "
          f"with {args.settle:g}s to settle between them, about "
          f"{args.cycles * (args.seconds + args.settle) * 2 / 60:.0f} minutes")

    runs: list[dict[str, Any]] = []
    first = True
    for cycle in range(1, args.cycles + 1):
        for label, symbols in (("A", small), ("B", capped)):
            if not first and args.settle > 0:
                print(f"probe: settling {args.settle:g}s so the account releases "
                      "the previous arm's slots")
                time.sleep(args.settle)
            first = False
            started = ettime.stamp(ettime.now_et())
            try:
                result = run_arm(symbols, set(watch), args.seconds)
            except Exception as exc:
                print(f"probe: cycle {cycle} arm {label} failed: "
                      f"{config.scrub_secrets(exc)}")
                continue
            result.update({"cycle": cycle, "arm": label, "started_at": started})
            runs.append(result)
            rate = result["messages_total"] / args.seconds
            watched = sum(result["counts"].values())
            print(f"probe: cycle {cycle} arm {label}  subscribed "
                  f"{result['subscribed']:>2}  {result['messages_total']:>6} msgs "
                  f"({rate:>6.1f}/s)  watch set {watched:>6}  "
                  f"replayed {sum(result['replayed'].values()):>3}"
                  + ("  REFUSED" if result.get("refused") else ""))
            if result.get("refused"):
                print("    the subscription was refused, so this arm measured "
                      "nothing about delivery. Raise --settle and run again.")
            if result["status"]:
                print(f"    status frames: {result['status'][:3]}")

    if not runs:
        print("probe: no arm completed, nothing to report")
        return 1

    print("")
    _report_off_exchange(runs, watch)

    verdict = _report_delivery(runs, watch)

    payload = {
        "generated_at": ettime.stamp(ettime.now_et()),
        # The window, so the vendor comparison can be run once EODHD has
        # published these minutes. It has not published the current session at
        # the time any premarket run of this probe finishes, which is why the
        # third number is a separate command rather than a third column here.
        "window_start_et": min((r["started_at"] for r in runs), default=None),
        "window_end_et": ettime.stamp(ettime.now_et()),
        "collector_reads": list(COLLECTOR_READS),
        "cap": cap,
        "watch": watch,
        "arm_a_subscribed": len(small),
        "arm_b_subscribed": len(capped),
        "seconds_per_arm": args.seconds,
        "cycles": args.cycles,
        "runs": runs,
        # Written down so a later reader does not recompute the median from
        # runs[] without the two refusals that decide what it means.
        "verdict": verdict,
    }
    out = config.DATA_DIR / f"socket-cap-probe-{ettime.today_str()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    files.write_text_atomically(
        out, json.dumps(payload, indent=2, sort_keys=True), attempts=files.ATTEMPTS, retry_s=files.RETRY_S)
    print(f"probe: wrote {out}")
    print("probe: the vendor side of the off exchange question needs EODHD's own "
          "1m bars for these minutes, which are not published until the session "
          f"is over. Run:  python -m research.probe_socket_cap --compare {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
