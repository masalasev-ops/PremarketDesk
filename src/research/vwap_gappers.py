"""Is there anything in trading gappers against the session VWAP?

Research, not a feature. Nothing imports this, nothing schedules it, and it
writes only doc/research/VWAP_GAPPERS.md, a per trade CSV under data/, and a
bar cache under data/backtest/bars/. It adds no table, no threshold and no job.

The question is narrow on purpose: four VWAP rules, a benchmark, and a stop
rule written down before any number exists. The control set is the point. It
runs the same four rules on names that did NOT gap, matched on dollar volume
decile, so the result can separate "the VWAP rule works" from "the gap screen
picked busy names". If those two sets score alike, the gap screen contributes
nothing.

PRE-REGISTRATION IS ENFORCED HERE, NOT PROMISED. `--preregister` appends a
version block of rules and a stop rule to the report and refuses to overwrite
one that already exists. The run refuses to start unless that block is present,
and refuses to run twice into the same report. So the ordering claimed in the
report is a property of how the file was produced, not an assurance from
whoever ran it.

VERSION 2 supersedes version 1, whose rules overlapped: `reject` and `fade`
fired on the same bar for any gap-up opening above VWAP, and `reclaim` and
`reject` shared a "pulls back to VWAP" trigger that was never defined. Version
1's pre-registration and results stay in the report, because a defective test
that has been run is part of the record.

    python -m research.vwap_gappers --preregister    write the rules, once
    python -m research.vwap_gappers                  run and append results
    python -m research.vwap_gappers --cache-only     prove a rerun needs no network
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

from core import config, criteria, ettime
from night import pool_recall
import probe_alpaca

_CRIT = criteria.load()

EOD_DIR = config.DATA_DIR / "backtest" / "eod"
BAR_CACHE_DIR = config.DATA_DIR / "backtest" / "bars"
ASSETS_PATH = config.DATA_DIR / "alpaca_assets.json"
REPORT_DIR = config.PROJECT_ROOT / "doc" / "research"
REPORT_PATH = REPORT_DIR / "VWAP_GAPPERS.md"
# Under data/, which is gitignored. Thirteen megabytes of per trade rows is
# evidence to inspect locally, not something to carry in the repository.
TRADES_PATH = config.DATA_DIR / "vwap_gappers_trades.csv"

# The trading API, NOT the data API. api.alpaca.markets answers 401 for these
# credentials; paper-api serves the same asset records and needs no extra key.
ASSETS_URL = "https://paper-api.alpaca.markets/v2/assets"

SESSION_OPEN_HM = (9, 30)
LAST_ENTRY_OFFSET = 385          # 15:55, in minutes after 09:30
SESSION_MINUTES = 390            # 09:30 to 16:00

DEFAULT_COST_BPS = 10.0

# Long rules first, so a reader sees the two axes: no precondition, then the
# same trigger requiring the opposite condition to have happened first.
RULES = ("hold", "reclaim", "fade", "reject")
LONG_RULES = ("hold", "reclaim")
SHORT_RULES = ("fade", "reject")

CONTROL_MAX_ABS_GAP_PCT = 1.0
DECILES = 10

VERSION = 2
VERSION_MARKER = "# Version 2, pre-registered"
RESULTS_MARKER = "# Results, version 2"

PREREGISTRATION = """
---

# Version 2, pre-registered

**Pre-registered. No version 2 result exists at the time this section was
written.** Pre-registered at: {stamp}

Version 1 above is superseded and is left in place, because a defective test
that has actually been run is part of the record. Four faults were found in it,
all of which change the answer rather than merely tidying it:

1. `reject` and `fade` fired on the same bar for any gap-up that opened above
   VWAP, so two of the four rules were frequently the same trade.
2. `reclaim` and `reject` shared a trigger described as "pulls back to VWAP",
   which was never defined. Whoever implemented it picked a definition, and
   that definition drove the result.
3. The buy-the-open benchmark was computed across ALL gappers while each rule
   fired on a subset, so the two sides of the comparison were different
   populations.
4. The control set was "did not gap", which admitted a name that gapped down 8
   percent. Those are event names and belong in neither group.

Version 1 also assumed shorting is free, which on gapping small caps it is not.

## The question

Does trading a gapper against its session VWAP produce anything, and if it
does, is the edge in the VWAP rule or merely in the gap screen?

## Population

Every cached session in `data/backtest/eod`. For each session the test
population is every universe name whose open gapped more than 3 percent against
the prior close, using `pool_recall.actual_gappers`, so this and the recall work
agree by construction rather than by inspection.

Prior closes come from the cached end of day files, never from Alpaca, so a
prior close defect and a strategy result cannot wear each other's clothes.

Bars are 09:30 to 16:00 one minute SIP bars from Alpaca, cached locally on
first fetch. A second run must complete with no network calls at all, and the
report states cache hits against fetches.

## The control set

Names whose ABSOLUTE gap that session was under {control_gap:g} percent, so a
name that gapped down heavily is excluded from both groups rather than quietly
becoming a control.

Matched to the gappers by 20 day average dollar volume DECILE, same count per
decile, same days. Decile boundaries are computed once over the whole universe.
Where a decile holds fewer eligible controls than gappers, the shortfall is
taken and reported rather than back-filled from a neighbouring decile.

Within a decile the choice is a stable hash of session and symbol, which is
deterministic across runs and uncorrelated with anything the test measures.

## VWAP definition

Session VWAP, cumulative from 09:30, from each bar's own `vw` weighted by that
bar's volume, reset daily.

**Premarket volume is NOT included.** The VWAP a rule trades against starts at
the opening bell and knows nothing about the premarket session. Stated because
the choice changes the level materially on exactly these names, which by
construction had unusual premarket activity.

A bar "closes above VWAP" means its close exceeds the cumulative VWAP
*including that bar*.

## The rules, on two clean axes

Direction, and whether the trigger requires the opposite condition first.
Nothing here mentions approaching, pulling back, or any other undefined
gesture. One entry per name per session, no re-entries, no stops, no targets.

| Rule | Side | Entry | Exit |
| --- | --- | --- | --- |
| `hold` | long | first bar that closes ABOVE VWAP, no precondition | first later close below VWAP, else 15:55 |
| `reclaim` | long | first bar that closes ABOVE VWAP after at least one bar has closed below it | first later close below VWAP, else 15:55 |
| `fade` | short | first bar that closes BELOW VWAP, no precondition | first later close above VWAP, else 15:55 |
| `reject` | short | first bar that closes BELOW VWAP after at least one bar has closed above it | first later close above VWAP, else 15:55 |

All four exits are symmetric: a long exits on the first close below VWAP after
entry, a short on the first close above, each or the 15:55 bar, whichever comes
first.

Entry is at the CLOSE of the bar that satisfies the entry condition, because
the condition is not known until the bar closes.

**A known and reported consequence of these definitions.** When the session's
first bar closes below VWAP, `hold` and `reclaim` necessarily fire on the same
bar; likewise `fade` and `reject` when the first bar closes above. That
coincidence is a property of the definitions rather than a defect, and its rate
is reported, so no one reads two columns as two independent findings.

## Benchmark

Buy at the 09:30 open, sell at the 15:55 close.

Computed for each rule ONLY on the name-session pairs where that rule actually
fired, and reported as a paired difference. A rule that fires on a fifth of
names cannot be judged against a benchmark averaged over all of them.

The fraction of gapper name-sessions each rule fired on is reported beside its
returns, since a rule firing on 5 percent of names is a different proposition
from one firing on 80.

## Shorting is not assumed free

`fade` and `reject` are short rules and gappers are frequently hard to borrow.
Alpaca's asset records carry `shortable` and `easy_to_borrow`, and both short
rules are reported twice: across all names, and restricted to names flagged
easy to borrow. If the edge lives only in the unborrowables, it is not an edge.

Stated in advance: those flags are CURRENT, not historical. A name easy to
borrow today may not have been in May, so this bounds the problem rather than
solving it.

## Reporting

Per session, never pooled, because the session is the sample unit. For each
rule, the distribution ACROSS SESSIONS of: number of signals, hit rate, median
return, mean return, and interquartile range. Never a bare mean.

Every figure appears gross and net of a fixed round trip cost, a parameter
defaulting to {cost:g} basis points.

For every signal, minutes elapsed since 09:30 at entry, as a distribution. A
rule whose signals cluster in the first fifteen minutes is unusable without a
charting platform and screen presence at the open, regardless of its returns,
and that has to sit beside the returns rather than be found afterwards.

## What is not modelled, stated before the numbers

- Fills, spread and slippage are NOT modelled. Every return is indicative only
  and assumes the close of a one minute bar is obtainable, which it is not.
- `universe.json` holds CURRENT listings, so names delisted since are absent.
  The results are flattered in an unknown direction and by an unknown amount.
- The dollar volume used for decile matching is a single current snapshot, not
  a per session figure.
- Borrow COST is not modelled, only the availability flag.

## STOP RULE, version 2

Written before any version 2 number exists.

**If no rule beats the buy-the-open benchmark net of costs on a median session,
measured on the name-sessions where that rule fired, or if the rules perform
within noise of the decile-matched control, then there is nothing here and the
premarket discovery work stops.**

"Within noise" is a two sided sign test across sessions on the per session
median return difference, gapper minus control, at p >= 0.05. Named here so the
bar cannot move later.

---
"""


# --------------------------------------------------------------- data loading

def _sessions() -> list[tuple[str, str]]:
    days = sorted(path.stem for path in EOD_DIR.glob("*.json"))
    return list(zip(days, days[1:]))


def _eod(day: str) -> dict[str, Any]:
    return json.loads((EOD_DIR / f"{day}.json").read_text(encoding="utf-8"))


def _universe() -> dict[str, dict[str, Any]]:
    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    return {str(row.get("symbol", "")).upper(): row for row in payload["symbols"]}


def borrow_flags(session: Any, refresh: bool = False) -> dict[str, dict[str, bool]]:
    """shortable and easy_to_borrow per symbol, cached to disk.

    Current flags, not historical ones. Alpaca publishes no point in time
    borrow record on this plan, so this bounds the short rules rather than
    settling them, and the report says so.
    """
    if ASSETS_PATH.exists() and not refresh:
        try:
            return json.loads(ASSETS_PATH.read_text(encoding="utf-8"))
        except ValueError:
            pass
    response = session.get(
        ASSETS_URL, params={"status": "active", "asset_class": "us_equity"}, timeout=90)
    response.raise_for_status()
    flags = {
        asset["symbol"]: {
            "shortable": bool(asset.get("shortable")),
            "easy_to_borrow": bool(asset.get("easy_to_borrow")),
        }
        for asset in response.json()
    }
    ASSETS_PATH.write_text(json.dumps(flags, indent=1, sort_keys=True), encoding="utf-8")
    return flags


def decile_boundaries(universe: dict[str, dict[str, Any]]) -> list[float]:
    """Nine cut points over the universe's 20 day average dollar volume."""
    values = sorted(float(row["avg_dollar_volume_20d"]) for row in universe.values()
                    if row.get("avg_dollar_volume_20d"))
    return [values[min(int(i / DECILES * len(values)), len(values) - 1)]
            for i in range(1, DECILES)]


def _decile(value: float | None, cuts: list[float]) -> int | None:
    if not value:
        return None
    import bisect
    return bisect.bisect_right(cuts, float(value))


def _stable_key(session: str, symbol: str) -> str:
    return hashlib.md5(f"{session}:{symbol}".encode("utf-8")).hexdigest()


def population(today: str, prior: str, universe: dict[str, dict[str, Any]],
               cuts: list[float]) -> tuple[dict[str, Any], list[str], dict[str, int]]:
    """(gappers, controls, shortfall_by_decile), decile matched."""
    prior_cache, today_cache = _eod(prior), _eod(today)
    prior_closes = {s: b["c"] for s, b in prior_cache.items() if b.get("c")}
    rows = [{"code": s, "open": b.get("o"), "volume": b.get("v")}
            for s, b in today_cache.items()]
    gappers = pool_recall.actual_gappers(
        rows, prior_closes, set(universe), _CRIT.rule("discovery", "gap_pct"))

    # Eligible controls: barely moved at all. A name that gapped down eight
    # percent is an event name and belongs in neither group, which is the fault
    # that made version 1's control set meaningless.
    eligible: dict[int, list[str]] = {}
    for symbol, bar in today_cache.items():
        key = symbol.upper()
        if key in gappers or key not in universe:
            continue
        close, open_price = prior_closes.get(key), bar.get("o")
        if not close or not open_price:
            continue
        if abs((open_price - close) / close * 100.0) >= CONTROL_MAX_ABS_GAP_PCT:
            continue
        decile = _decile(universe[key].get("avg_dollar_volume_20d"), cuts)
        if decile is not None:
            eligible.setdefault(decile, []).append(key)

    wanted: dict[int, int] = {}
    for symbol in gappers:
        decile = _decile(universe.get(symbol, {}).get("avg_dollar_volume_20d"), cuts)
        if decile is not None:
            wanted[decile] = wanted.get(decile, 0) + 1

    controls: list[str] = []
    shortfall: dict[str, int] = {}
    for decile, count in sorted(wanted.items()):
        pool = sorted(eligible.get(decile, []), key=lambda s: _stable_key(today, s))
        controls.extend(pool[:count])
        if len(pool) < count:
            shortfall[str(decile)] = count - len(pool)
    return gappers, controls, shortfall


# ------------------------------------------------------------------ bar cache

def _cache_path(day: str) -> Path:
    return BAR_CACHE_DIR / f"{day}.json.gz"


def _read_cache(day: str) -> dict[str, list[list[float]]]:
    path = _cache_path(day)
    if not path.exists():
        return {}
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        print(f"vwap: cache for {day} unreadable, refetching")
        return {}


def _write_cache(day: str, bars: dict[str, list[list[float]]]) -> None:
    BAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(day)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(bars, handle, separators=(",", ":"))


def _offset(stamp: str, day: str) -> int | None:
    """Minutes after 09:30 ET. The cache stores this, not an ISO string."""
    try:
        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ettime.ET)
    except (ValueError, AttributeError):
        return None
    date = ettime.parse_date(day)
    opened = dt.datetime(date.year, date.month, date.day,
                         SESSION_OPEN_HM[0], SESSION_OPEN_HM[1], tzinfo=ettime.ET)
    return int(round((when - opened).total_seconds() / 60.0))


def fetch_bars(probe: probe_alpaca.Probe | None, day: str, codes: list[str],
               tally: dict[str, int]) -> dict[str, list[list[float]]]:
    """Bars per symbol for one session, cache first, network only for the rest.

    Cached as [offset, o, h, l, c, v, vw] per bar, which is a third the size of
    the vendor's own shape and carries everything the rules read. A symbol with
    genuinely no bars is cached as an empty list, so an illiquid name is not
    refetched on every run forever.
    """
    cached = _read_cache(day)
    missing = [code for code in codes if code not in cached]
    tally["cache_hits"] += len(codes) - len(missing)
    tally["fetched"] += len(missing)
    if not missing:
        return {code: cached[code] for code in codes}
    if probe is None:
        raise SystemExit(
            f"REFUSING: --cache-only was passed but {len(missing):,} symbols for "
            f"{day} are not cached. A cache-only run must touch no network."
        )

    date = ettime.parse_date(day)

    def utc(hour: int, minute: int) -> str:
        when = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=ettime.ET)
        return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    start, end = utc(*SESSION_OPEN_HM), utc(16, 0)
    fetched: dict[str, list[list[float]]] = {code: [] for code in missing}
    for index in range(0, len(missing), 500):
        chunk = missing[index:index + 500]
        token, pages = None, 0
        while True:
            params = {"symbols": ",".join(chunk), "timeframe": "1Min",
                      "start": start, "end": end, "limit": 10000, "feed": "sip"}
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            pages += 1
            tally["requests"] += 1
            if status != 200:
                tally["failed_requests"] += 1
                break
            for symbol, bars in ((payload.get("bars") or {}).items()):
                for bar in bars or []:
                    offset = _offset(bar.get("t"), day)
                    if offset is None or not (0 <= offset < SESSION_MINUTES):
                        continue
                    fetched.setdefault(symbol, []).append([
                        offset, bar.get("o"), bar.get("h"), bar.get("l"),
                        bar.get("c"), bar.get("v"), bar.get("vw"),
                    ])
            token = payload.get("next_page_token")
            if not token or pages >= 600:
                break

    for bars in fetched.values():
        bars.sort(key=lambda row: row[0])
    cached.update(fetched)
    _write_cache(day, cached)
    return {code: cached.get(code, []) for code in codes}


# ----------------------------------------------------------------- the rules

def with_vwap(raw: list[list[float]]) -> list[dict[str, Any]]:
    """Cumulative session VWAP from 09:30, premarket deliberately excluded."""
    out = []
    price_volume = volume_sum = 0.0
    for offset, _open, high, low, close, volume, vw in raw:
        if close is None:
            continue
        volume = float(volume or 0)
        if vw is not None and volume > 0:
            price_volume += float(vw) * volume
            volume_sum += volume
        if volume_sum <= 0:
            continue
        out.append({"offset": offset, "h": high, "l": low, "c": close,
                    "o": _open, "vwap": price_volume / volume_sum})
    return out


def run_rule(rule: str, bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One trade, or None when the rule never fired. Definitions in the report.

    Two axes and nothing else: direction, and whether the opposite condition
    must have happened first. No notion of approaching or pulling back, because
    version 1 proved that an undefined trigger is a free parameter and a free
    parameter decides the answer.
    """
    usable = [bar for bar in bars if bar["offset"] <= LAST_ENTRY_OFFSET]
    if len(usable) < 2:
        return None

    long_side = rule in LONG_RULES
    needs_opposite = rule in ("reclaim", "reject")

    entry_index = None
    seen_opposite = False
    for index, bar in enumerate(usable):
        above = bar["c"] > bar["vwap"]
        below = bar["c"] < bar["vwap"]
        wanted = above if long_side else below
        opposite = below if long_side else above
        if wanted and (seen_opposite or not needs_opposite):
            entry_index = index
            break
        if opposite:
            seen_opposite = True

    if entry_index is None or entry_index >= len(usable) - 1:
        return None

    entry_price = usable[entry_index]["c"]
    if not entry_price:
        return None

    exit_index, reason = len(usable) - 1, "15:55"
    for index in range(entry_index + 1, len(usable)):
        bar = usable[index]
        crossed = (bar["c"] < bar["vwap"]) if long_side else (bar["c"] > bar["vwap"])
        if crossed:
            exit_index, reason = index, "vwap_cross"
            break

    exit_price = usable[exit_index]["c"]
    if not exit_price:
        return None
    gross = (exit_price - entry_price) if long_side else (entry_price - exit_price)
    return {
        "rule": rule,
        "side": "long" if long_side else "short",
        "entry_offset": usable[entry_index]["offset"],
        "exit_offset": usable[exit_index]["offset"],
        "minutes_since_open": float(usable[entry_index]["offset"]),
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "gross_return_pct": round(gross / entry_price * 100.0, 6),
        "exit_reason": reason,
        "bars_held": usable[exit_index]["offset"] - usable[entry_index]["offset"],
    }


def buy_the_open(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [bar for bar in bars if bar["offset"] <= LAST_ENTRY_OFFSET]
    if len(usable) < 2:
        return None
    entry_price, exit_price = usable[0]["o"], usable[-1]["c"]
    if not entry_price or not exit_price:
        return None
    return {
        "rule": "buy_the_open", "side": "long",
        "entry_offset": usable[0]["offset"], "exit_offset": usable[-1]["offset"],
        "minutes_since_open": float(usable[0]["offset"]),
        "entry_price": round(entry_price, 4), "exit_price": round(exit_price, 4),
        "gross_return_pct": round((exit_price - entry_price) / entry_price * 100.0, 6),
        "exit_reason": "15:55", "bars_held": usable[-1]["offset"] - usable[0]["offset"],
    }


# ------------------------------------------------------------------- statistics

def _quantiles(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def at(share: float) -> float:
        return ordered[min(int(share * (len(ordered) - 1)), len(ordered) - 1)]

    return {
        "n": len(ordered), "min": round(ordered[0], 4), "p25": round(at(0.25), 4),
        "median": round(statistics.median(ordered), 4),
        "mean": round(statistics.fmean(ordered), 4),
        "p75": round(at(0.75), 4), "max": round(ordered[-1], 4),
        "iqr": round(at(0.75) - at(0.25), 4),
    }


def _sign_test(differences: list[float]) -> dict[str, Any]:
    """Two sided sign test. Named in the pre-registration, so it cannot move."""
    positive = sum(1 for d in differences if d > 0)
    negative = sum(1 for d in differences if d < 0)
    n = positive + negative
    if n == 0:
        return {"n": 0, "p_value": None, "positive": 0, "negative": 0}
    k = min(positive, negative)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return {"n": n, "positive": positive, "negative": negative,
            "p_value": round(min(1.0, 2 * tail), 5)}


def summarise(trades: list[dict[str, Any]], cost_bps: float) -> dict[str, Any]:
    """Per session first, then the distribution of those per session figures."""
    by_session: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        by_session.setdefault(trade["session"], []).append(trade)

    per_session = []
    for session, rows in sorted(by_session.items()):
        gross = [r["gross_return_pct"] for r in rows]
        net = [r["gross_return_pct"] - cost_bps / 100.0 for r in rows]

        def at(values: list[float], share: float) -> float:
            ordered = sorted(values)
            return ordered[min(int(share * (len(ordered) - 1)), len(ordered) - 1)]

        per_session.append({
            "session": session,
            "signals": len(rows),
            "hit_rate_gross": round(sum(1 for v in gross if v > 0) / len(gross), 4),
            "hit_rate_net": round(sum(1 for v in net if v > 0) / len(net), 4),
            "median_gross": round(statistics.median(gross), 4),
            "median_net": round(statistics.median(net), 4),
            "mean_gross": round(statistics.fmean(gross), 4),
            "mean_net": round(statistics.fmean(net), 4),
            "iqr_net": round(at(net, 0.75) - at(net, 0.25), 4),
        })

    if not per_session:
        return {"sessions": 0}
    entry_minutes = [t["minutes_since_open"] for t in trades
                     if t.get("minutes_since_open") is not None]
    return {
        "sessions": len(per_session),
        "trades": len(trades),
        "signals": _quantiles([r["signals"] for r in per_session]),
        "hit_rate_gross": _quantiles([r["hit_rate_gross"] for r in per_session]),
        "hit_rate_net": _quantiles([r["hit_rate_net"] for r in per_session]),
        "median_gross": _quantiles([r["median_gross"] for r in per_session]),
        "median_net": _quantiles([r["median_net"] for r in per_session]),
        "mean_gross": _quantiles([r["mean_gross"] for r in per_session]),
        "mean_net": _quantiles([r["mean_net"] for r in per_session]),
        "iqr_net": _quantiles([r["iqr_net"] for r in per_session]),
        "entry_minutes": _quantiles(entry_minutes),
        "share_entering_within_15min": round(
            sum(1 for m in entry_minutes if m <= 15.0) / len(entry_minutes), 4)
        if entry_minutes else None,
    }


def _median_by_session(trades: list[dict[str, Any]], cost_bps: float) -> dict[str, float]:
    by_session: dict[str, list[float]] = {}
    for trade in trades:
        by_session.setdefault(trade["session"], []).append(
            trade["gross_return_pct"] - cost_bps / 100.0)
    return {session: statistics.median(values) for session, values in by_session.items()}


def compare(mine_trades: list[dict[str, Any]], theirs_trades: list[dict[str, Any]],
            cost_bps: float) -> dict[str, Any]:
    """Per session median against per session median, net, paired on the session."""
    mine = _median_by_session(mine_trades, cost_bps)
    theirs = _median_by_session(theirs_trades, cost_bps)
    shared = sorted(set(mine) & set(theirs))
    differences = [mine[s] - theirs[s] for s in shared]
    if not differences:
        return {"sessions": 0}
    wins = sum(1 for d in differences if d > 0)
    return {
        "sessions": len(differences),
        "sessions_won": wins,
        "win_rate": round(wins / len(differences), 4),
        "median_difference": round(statistics.median(differences), 4),
        "mean_difference": round(statistics.fmean(differences), 4),
        "sign_test": _sign_test(differences),
    }


def paired_benchmark(rule_trades: list[dict[str, Any]],
                     benchmark_by_key: dict[tuple[str, str], dict[str, Any]],
                     cost_bps: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The benchmark restricted to the name-sessions this rule actually fired on.

    Version 1 compared a rule firing on a subset against buy-the-open averaged
    over every gapper, which is two different populations wearing one label.
    Here the benchmark trade is looked up per (session, symbol) so the two
    sides describe the same names on the same days.
    """
    matched = []
    for trade in rule_trades:
        found = benchmark_by_key.get((trade["session"], trade["symbol"]))
        if found is not None:
            matched.append(found)
    return matched, compare(rule_trades, matched, cost_bps)


# ------------------------------------------------------------------- the run

def run(sessions_limit: int | None, cost_bps: float, cache_only: bool) -> dict[str, Any]:
    text = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.is_file() else ""
    if VERSION_MARKER not in text:
        raise SystemExit(
            f"REFUSING to run: {REPORT_PATH} carries no version {VERSION} "
            "pre-registration. The rules and the stop rule must be written down "
            "before any number is produced. Run --preregister first."
        )
    if RESULTS_MARKER in text:
        raise SystemExit(
            f"REFUSING to run: {REPORT_PATH} already carries version {VERSION} "
            "results. Appending a second set would let a reader pick whichever "
            "run they preferred."
        )

    universe = _universe()
    cuts = decile_boundaries(universe)
    pairs = _sessions()
    if sessions_limit:
        pairs = pairs[-sessions_limit:]

    probe = None if cache_only else probe_alpaca.Probe()
    flags = borrow_flags(probe.session if probe else probe_alpaca.build_session())

    tally = {"cache_hits": 0, "fetched": 0, "requests": 0, "failed_requests": 0}
    trades: list[dict[str, Any]] = []
    skipped = {"no_bars": 0, "too_few_bars": 0}
    counts = {"gapper": 0, "control": 0}
    fired: dict[tuple[str, str], set[str]] = {}
    coincidence = {"hold_reclaim_same_bar": 0, "fade_reject_same_bar": 0,
                   "hold_and_reclaim_both": 0, "fade_and_reject_both": 0}
    shortfalls: dict[str, int] = {}
    print(f"vwap: {len(pairs)} sessions, cost {cost_bps:g} bps, "
          f"{'CACHE ONLY' if cache_only else 'network allowed'}")

    for index, (prior, today) in enumerate(pairs):
        gappers, controls, shortfall = population(today, prior, universe, cuts)
        if not gappers:
            continue
        for decile, missing in shortfall.items():
            shortfalls[decile] = shortfalls.get(decile, 0) + missing

        wanted = {s.split(".")[0]: ("gapper", s) for s in gappers}
        wanted.update({s.split(".")[0]: ("control", s) for s in controls})
        bars_by_code = fetch_bars(probe, today, sorted(wanted), tally)

        for code, (group, symbol) in wanted.items():
            raw = bars_by_code.get(code) or []
            if not raw:
                skipped["no_bars"] += 1
                continue
            bars = with_vwap(raw)
            if len(bars) < 2:
                skipped["too_few_bars"] += 1
                continue
            counts[group] += 1

            found: dict[str, dict[str, Any]] = {}
            for rule in RULES:
                trade = run_rule(rule, bars)
                if trade is not None:
                    found[rule] = trade
            opened = buy_the_open(bars)
            if opened is not None:
                found["buy_the_open"] = opened

            if group == "gapper":
                if "hold" in found and "reclaim" in found:
                    coincidence["hold_and_reclaim_both"] += 1
                    if found["hold"]["entry_offset"] == found["reclaim"]["entry_offset"]:
                        coincidence["hold_reclaim_same_bar"] += 1
                if "fade" in found and "reject" in found:
                    coincidence["fade_and_reject_both"] += 1
                    if found["fade"]["entry_offset"] == found["reject"]["entry_offset"]:
                        coincidence["fade_reject_same_bar"] += 1
                fired[(today, symbol)] = set(found) - {"buy_the_open"}

            asset = flags.get(code) or {}
            for trade in found.values():
                trade.update({
                    "session": today, "symbol": symbol, "group": group,
                    "easy_to_borrow": bool(asset.get("easy_to_borrow")),
                    "shortable": bool(asset.get("shortable")),
                })
                trades.append(trade)

        if (index + 1) % 10 == 0:
            print(f"vwap: {index + 1}/{len(pairs)} sessions, {len(trades):,} trades, "
                  f"cache {tally['cache_hits']:,} hits / {tally['fetched']:,} fetched, "
                  f"{tally['requests']:,} requests")

    print(f"vwap: {len(trades):,} trades over {len(pairs)} sessions. "
          f"Cache {tally['cache_hits']:,} hits, {tally['fetched']:,} fetched, "
          f"{tally['requests']:,} Alpaca requests.")

    def subset(rule: str, group: str, etb_only: bool = False) -> list[dict[str, Any]]:
        return [t for t in trades
                if t["rule"] == rule and t["group"] == group
                and (t["easy_to_borrow"] if etb_only else True)]

    benchmark_by_key = {
        (t["session"], t["symbol"]): t for t in trades if t["rule"] == "buy_the_open"
    }

    gapper_name_sessions = counts["gapper"]
    results: dict[str, Any] = {}
    for rule in RULES:
        gapper_trades = subset(rule, "gapper")
        control_trades = subset(rule, "control")
        _matched, versus_open = paired_benchmark(gapper_trades, benchmark_by_key, cost_bps)
        block = {
            "gapper": summarise(gapper_trades, cost_bps),
            "control": summarise(control_trades, cost_bps),
            "vs_buy_the_open_paired": versus_open,
            "vs_control": compare(gapper_trades, control_trades, cost_bps),
            "fire_rate": round(len(gapper_trades) / gapper_name_sessions, 4)
            if gapper_name_sessions else None,
        }
        if rule in SHORT_RULES:
            etb_trades = subset(rule, "gapper", etb_only=True)
            etb_controls = subset(rule, "control", etb_only=True)
            _m, etb_versus_open = paired_benchmark(etb_trades, benchmark_by_key, cost_bps)
            block["easy_to_borrow"] = {
                "gapper": summarise(etb_trades, cost_bps),
                "vs_buy_the_open_paired": etb_versus_open,
                "vs_control": compare(etb_trades, etb_controls, cost_bps),
                "trades": len(etb_trades),
                "share_of_trades": round(len(etb_trades) / len(gapper_trades), 4)
                if gapper_trades else None,
            }
        results[rule] = block

    return {
        "measured_at": ettime.stamp(ettime.now_et()),
        "version": VERSION,
        "cost_bps": cost_bps,
        "sessions_examined": len(pairs),
        "names": counts,
        "skipped": skipped,
        "cache": tally,
        "coincidence": coincidence,
        "control_shortfall_by_decile": shortfalls,
        "borrow": {
            "universe_flagged_easy": sum(1 for f in flags.values() if f["easy_to_borrow"]),
            "universe_flagged_shortable": sum(1 for f in flags.values() if f["shortable"]),
        },
        "buy_the_open": {
            "gapper": summarise([t for t in trades if t["rule"] == "buy_the_open"
                                 and t["group"] == "gapper"], cost_bps),
            "control": summarise([t for t in trades if t["rule"] == "buy_the_open"
                                  and t["group"] == "control"], cost_bps),
        },
        "rules": results,
        "trades": trades,
    }


# ---------------------------------------------------------------- the report

def write_trades_csv(trades: list[dict[str, Any]], cost_bps: float) -> Path:
    TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
    columns = ["session", "group", "symbol", "rule", "side", "entry_offset",
               "exit_offset", "minutes_since_open", "entry_price", "exit_price",
               "gross_return_pct", "net_return_pct", "exit_reason", "bars_held",
               "easy_to_borrow", "shortable"]
    with TRADES_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for trade in trades:
            row = dict(trade)
            row["net_return_pct"] = round(row["gross_return_pct"] - cost_bps / 100.0, 6)
            writer.writerow({key: row.get(key) for key in columns})
    return TRADES_PATH


def _row(label: str, block: dict[str, Any]) -> str:
    if not block or not block.get("n"):
        return f"| {label} | 0 | | | | | |"
    return (f"| {label} | {block['n']} | {block['min']} | {block['p25']} | "
            f"{block['median']} | {block['p75']} | {block['max']} |")


def _stat_table(side: dict[str, Any]) -> list[str]:
    return [
        "| statistic | sessions | min | p25 | median | p75 | max |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        _row("signals per session", side["signals"]),
        _row("hit rate gross", side["hit_rate_gross"]),
        _row("hit rate net", side["hit_rate_net"]),
        _row("median return gross", side["median_gross"]),
        _row("median return net", side["median_net"]),
        _row("mean return gross", side["mean_gross"]),
        _row("mean return net", side["mean_net"]),
        _row("IQR of returns net", side["iqr_net"]),
        "",
    ]


def _compare_rows(label_open: str, versus_open: dict[str, Any],
                  label_control: str, versus_control: dict[str, Any]) -> list[str]:
    def line(label: str, block: dict[str, Any]) -> str:
        return (f"| {label} | {block.get('sessions', 0)} | "
                f"{block.get('sessions_won', 0)} | {block.get('win_rate')} | "
                f"{block.get('median_difference')} | "
                f"{(block.get('sign_test') or {}).get('p_value')} |")

    return [
        "| comparison | sessions | won | win rate | median difference | sign test p |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        line(label_open, versus_open),
        line(label_control, versus_control),
        "",
    ]


def render(result: dict[str, Any]) -> str:
    cost = result["cost_bps"]
    cache = result["cache"]
    lines: list[str] = [
        "",
        RESULTS_MARKER,
        "",
        f"Run at: {result['measured_at']}",
        "",
        "Appended by a run that refused to start until the version 2 "
        f"pre-registration above existed. {result['sessions_examined']} sessions, "
        f"{result['names']['gapper']:,} gapper name-sessions and "
        f"{result['names']['control']:,} decile-matched control name-sessions with "
        f"usable bars. Round trip cost {cost:g} bps.",
        "",
        f"**Bar cache: {cache['cache_hits']:,} symbol-sessions served from cache, "
        f"{cache['fetched']:,} fetched, {cache['requests']:,} Alpaca requests.** "
        "A rerun with `--cache-only` completes with no network at all.",
        "",
        f"Dropped: {result['skipped']['no_bars']:,} name-sessions with no bars, "
        f"{result['skipped']['too_few_bars']:,} with fewer than two usable.",
        "",
        "Every return is a percentage. Every figure is a distribution ACROSS "
        "SESSIONS of a per session statistic, so a median of medians is meant "
        "literally and is not a pooled number.",
        "",
        "## Rule coincidence, as warned in the pre-registration",
        "",
        f"- `hold` and `reclaim` both fired on {result['coincidence']['hold_and_reclaim_both']:,} "
        f"gapper name-sessions, on the SAME bar in "
        f"{result['coincidence']['hold_reclaim_same_bar']:,} of them.",
        f"- `fade` and `reject` both fired on {result['coincidence']['fade_and_reject_both']:,} "
        f"gapper name-sessions, on the SAME bar in "
        f"{result['coincidence']['fade_reject_same_bar']:,} of them.",
        "",
        "Read the coinciding pairs as one finding, not two.",
        "",
    ]

    shortfall = result.get("control_shortfall_by_decile") or {}
    if shortfall:
        total = sum(shortfall.values())
        lines += [
            f"**Control shortfall:** {total:,} gapper name-sessions had no eligible "
            f"decile match, by decile {json.dumps(shortfall, sort_keys=True)}. Taken "
            "rather than back-filled from a neighbouring decile, so the control set "
            "is that much smaller rather than that much less matched.",
            "",
        ]

    borrow = result["borrow"]
    lines += [
        f"**Borrow flags:** {borrow['universe_flagged_easy']:,} of the assets Alpaca "
        f"returned are flagged easy to borrow and {borrow['universe_flagged_shortable']:,} "
        "shortable. On this universe the two flags are identical, so the easy to borrow "
        "split below is a weaker test than it appears: it removes the same names either "
        "way, and the flags are CURRENT rather than historical.",
        "",
    ]

    for name, block in (("Gappers", result["buy_the_open"]["gapper"]),
                        ("Controls", result["buy_the_open"]["control"])):
        if not block.get("sessions"):
            continue
        lines += [f"## Benchmark, buy the open, whole population: {name}", ""]
        lines += _stat_table(block)

    for rule in RULES:
        block = result["rules"][rule]
        side_word = "long" if rule in LONG_RULES else "short"
        lines += [
            f"## Rule {rule} ({side_word})",
            "",
            f"**Fired on {block['fire_rate']:.1%} of gapper name-sessions** "
            f"({block['gapper'].get('trades', 0):,} trades).",
            "",
        ]
        for label, side in (("on gappers", block["gapper"]),
                            ("on decile-matched controls", block["control"])):
            if not side.get("sessions"):
                lines += [f"### {label}", "", "No signals.", ""]
                continue
            lines += [f"### {label}", ""] + _stat_table(side)
            lines += [
                "Entry timing, minutes after 09:30: median "
                f"{side['entry_minutes'].get('median')}, p25 "
                f"{side['entry_minutes'].get('p25')}, p75 "
                f"{side['entry_minutes'].get('p75')}. "
                f"**{side['share_entering_within_15min']:.1%} of signals enter within "
                "the first fifteen minutes.**",
                "",
            ]

        lines += ["### Against both benchmarks, net of costs", ""]
        lines += _compare_rows(
            "vs buy the open, PAIRED on the name-sessions this rule fired on",
            block["vs_buy_the_open_paired"],
            "vs decile-matched control", block["vs_control"])

        etb = block.get("easy_to_borrow")
        if etb:
            lines += [
                "### Restricted to names flagged easy to borrow",
                "",
                f"{etb['trades']:,} trades, {etb['share_of_trades']:.1%} of this rule's "
                "gapper trades.",
                "",
            ]
            if etb["gapper"].get("sessions"):
                lines += _stat_table(etb["gapper"])
            lines += _compare_rows(
                "vs buy the open, paired, easy to borrow only", etb["vs_buy_the_open_paired"],
                "vs control, easy to borrow only", etb["vs_control"])

    lines += [verdict(result), ""]
    return "\n".join(lines)


def verdict(result: dict[str, Any]) -> str:
    """The stop rule, applied exactly as written, before the numbers were seen."""
    beat_open, beat_control = [], []
    for rule in RULES:
        block = result["rules"][rule]
        if (block["vs_buy_the_open_paired"].get("median_difference") or 0) > 0:
            beat_open.append(rule)
        versus_control = block["vs_control"]
        p_value = (versus_control.get("sign_test") or {}).get("p_value")
        if p_value is not None and p_value < 0.05 and \
                (versus_control.get("median_difference") or 0) > 0:
            beat_control.append(rule)

    lines = [
        "## Verdict against the stop rule, version 2",
        "",
        "The stop rule, as written before any version 2 number existed: if no rule "
        "beats the buy-the-open benchmark net of costs on a median session, measured "
        "on the name-sessions where that rule fired, OR the rules perform within "
        "noise of the decile-matched control at p >= 0.05 on a two sided sign test, "
        "there is nothing here and the premarket discovery work stops.",
        "",
        "- Rules beating the PAIRED buy-the-open on the median session, net: "
        f"{', '.join(beat_open) if beat_open else 'NONE'}",
        "- Rules beating the decile-matched control at p < 0.05: "
        f"{', '.join(beat_control) if beat_control else 'NONE'}",
        "",
    ]
    survivors = sorted(set(beat_open) & set(beat_control))
    if survivors:
        lines.append(
            "**VERDICT: the stop rule is NOT triggered.** "
            f"{', '.join(survivors)} clears both conditions. The premarket discovery "
            "work continues. This is one backtest with no fills, spread or slippage "
            "modelled, current rather than historical borrow flags, and a "
            "survivorship biased universe, so it licenses further work, not a trade."
        )
    else:
        lines.append(
            "**VERDICT: the stop rule IS triggered.** No rule clears both conditions, "
            "so on the evidence recorded here there is nothing in trading these "
            "gappers against session VWAP, and by the rule written before the numbers "
            "were seen the premarket discovery work stops."
        )
    return "\n".join(lines)


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VWAP on gappers, a research test.")
    parser.add_argument("--preregister", action="store_true",
                        help="Append this version's rules and stop rule. Refuses to repeat.")
    parser.add_argument("--sessions", type=int, default=None,
                        help="Only the most recent N sessions. Default is all cached.")
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS,
                        help=f"Round trip cost in basis points. Default {DEFAULT_COST_BPS:g}.")
    parser.add_argument("--cache-only", action="store_true",
                        help="Fail rather than touch the network. Proves a rerun is "
                             "fully served from the bar cache.")
    args = parser.parse_args(argv)

    if args.preregister:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        existing = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else ""
        if VERSION_MARKER in existing:
            raise SystemExit(
                f"REFUSING: {REPORT_PATH} already carries a version {VERSION} "
                "pre-registration. It happens once, and rewriting it would destroy "
                "the only evidence that the rules were written before the numbers."
            )
        stamp = ettime.stamp(ettime.now_et())
        with REPORT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(PREREGISTRATION.format(
                stamp=stamp, cost=DEFAULT_COST_BPS,
                control_gap=CONTROL_MAX_ABS_GAP_PCT))
        print(f"vwap: version {VERSION} pre-registration appended to {REPORT_PATH} "
              f"at {stamp}")
        return 0

    result = run(args.sessions, args.cost_bps, args.cache_only)
    csv_path = write_trades_csv(result["trades"], args.cost_bps)
    print(f"vwap: {len(result['trades']):,} trade rows written to {csv_path}")
    with REPORT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(render(result))
    print(f"vwap: results appended to {REPORT_PATH}")
    print()
    print(verdict(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
