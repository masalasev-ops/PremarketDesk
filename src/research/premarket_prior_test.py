"""Package 5.5: is the universe's own premarket tape a better discovery prior?

The rule and the bar are in doc/research/PREMARKET_PRIOR_PREREGISTRATION.md
and were committed before this file existed. Read that first. Nothing here
chooses a threshold; every number it could have tuned is named there.

Two stages, the split every study in this project uses:

  fetch     network, dated, writes data/research/premarket-sweep/<date>.json
  evaluate  reproducible from those bytes, makes no request at all

Alpaca is the vendor here and that is allowed: hard rule 3 admits it under
src/research/ and in night/true_volume.py, and nothing in this file can reach
a report. It writes one directory under data/research and prints.

    PYTHONPATH=src .venv/Scripts/python.exe -m research.premarket_prior_test fetch
    PYTHONPATH=src .venv/Scripts/python.exe -m research.premarket_prior_test evaluate
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

from core import config, criteria, files

_CRIT = criteria.load()

SWEEP_DIR = config.PROJECT_ROOT / "data" / "research" / "premarket-sweep"
SESSIONS_DIR = config.PROJECT_ROOT / "data" / "backtest" / "sessions"

# The window the pre-registration names, in ET. 07:00 and not 07:15, so the
# sweep is on disk before the discovery pass that would read it.
WINDOW_START_HHMM = (4, 0)
WINDOW_END_HHMM = (7, 0)

# Alpaca takes many symbols on one request. 600 was measured on 2026-09-06 at
# 0.47s with no pagination on a 2,648 name universe, so the whole sweep is
# about five requests a session.
BATCH = 600

# Under this many symbols returning a bar, the session is refused rather than
# scored. The pre-registration names it as the guard against Alpaca serving
# less history for older sessions and confounding the arms with the calendar.
MIN_SYMBOLS_WITH_BARS = 100

DOLLAR_FLOOR = 50_000.0
FLOOR_SENSITIVITIES = (10_000.0, 250_000.0)
K_PRIMARY = 10
K_SENSITIVITIES = (5, 20)


def _sessions() -> list[str]:
    return sorted(p.name for p in SESSIONS_DIR.iterdir() if p.is_dir())


def _et_to_utc_z(day: str, hhmm: tuple[int, int]) -> str:
    """The ET wall clock as a UTC instant, through the project's own clock.

    Not a fixed four hour offset: the replay spans a daylight saving boundary
    and a session in November is five hours behind UTC where one in August is
    four. Getting this wrong would shift the window by an hour on part of the
    population only, which is the confound the pre-registration refuses.
    """
    from core import ettime

    stamp = ettime.at_hm(ettime.parse_date(day), hhmm)
    return stamp.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ fetch

def fetch(limit: int | None, force: bool) -> int:
    import probe_alpaca

    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    probe = probe_alpaca.Probe()
    days = _sessions()
    if limit:
        days = days[:limit]

    written = spared = 0
    for index, day in enumerate(days, 1):
        target = SWEEP_DIR / f"{day}.json"
        if target.exists() and not force:
            spared += 1
            continue
        inputs = json.loads((SESSIONS_DIR / day / "inputs.json").read_text("utf-8"))
        closes = inputs.get("prior_closes") or {}
        symbols = sorted({s.split(".")[0] for s in closes})
        start = _et_to_utc_z(day, WINDOW_START_HHMM)
        end = _et_to_utc_z(day, WINDOW_END_HHMM)

        rows: dict[str, dict[str, Any]] = {}
        failures: list[str] = []
        for at in range(0, len(symbols), BATCH):
            chunk = symbols[at:at + BATCH]
            token = None
            while True:
                params = {
                    "symbols": ",".join(chunk), "timeframe": "1Min",
                    "start": start, "end": end, "feed": "sip",
                    "limit": 10000, "adjustment": "raw",
                }
                if token:
                    params["page_token"] = token
                code, payload, _elapsed = probe.get(params)
                if code != 200 or not isinstance(payload, dict):
                    failures.append(f"{chunk[0]}..{chunk[-1]}: HTTP {code}")
                    break
                for symbol, bars in (payload.get("bars") or {}).items():
                    row = rows.setdefault(
                        symbol, {"bars": 0, "volume": 0.0, "last": None,
                                 "last_at": None, "high": None})
                    for bar in bars:
                        row["bars"] += 1
                        row["volume"] += float(bar.get("v") or 0.0)
                        close = bar.get("c")
                        high = bar.get("h")
                        if close is not None:
                            # The bars come back in time order per symbol and
                            # per page, so the last one seen is the latest.
                            row["last"] = float(close)
                            row["last_at"] = bar.get("t")
                        if high is not None:
                            row["high"] = (float(high) if row["high"] is None
                                           else max(row["high"], float(high)))
                token = payload.get("next_page_token")
                if not token:
                    break

        files.write_text_atomically(target, json.dumps({
            "session_date": day,
            "window_et": f"{WINDOW_START_HHMM[0]:02d}:{WINDOW_START_HHMM[1]:02d}"
                         f" to {WINDOW_END_HHMM[0]:02d}:{WINDOW_END_HHMM[1]:02d}",
            "window_utc": {"start": start, "end": end},
            "feed": "sip",
            "adjustment": "raw",
            "universe_symbols": len(symbols),
            "symbols_with_bars": len(rows),
            "batch_failures": failures,
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "symbols": rows,
        }, indent=2, sort_keys=False) + "\n",
            attempts=files.ATTEMPTS, retry_s=files.RETRY_S)
        written += 1
        if index % 20 == 0 or index == len(days):
            print(f"  {index}/{len(days)}  {day}  {len(rows)} symbol(s) with bars, "
                  f"{probe.request_count} request(s) so far")

    print(f"sweep: {written} session(s) written, {spared} already on disk, "
          f"{probe.request_count} Alpaca request(s), 0 EODHD calls")
    return 0


# --------------------------------------------------------------- evaluate

def _ranked_sweep(sweep: dict[str, Any], closes: dict[str, Any],
                  floor: float) -> list[tuple[str, float]]:
    """Eligible symbols by absolute gap, descending, ties broken by symbol."""
    out: list[tuple[str, float]] = []
    for symbol, row in (sweep.get("symbols") or {}).items():
        last = row.get("last")
        if last is None or row.get("bars", 0) < 1:
            continue
        if float(row.get("volume") or 0.0) * float(last) < floor:
            continue
        prior = closes.get(f"{symbol}.US")
        if isinstance(prior, dict):
            prior = prior.get("close") or prior.get("prior_close")
        try:
            prior = float(prior)
        except (TypeError, ValueError):
            continue
        if prior <= 0:
            continue
        out.append((f"{symbol}.US", (float(last) - prior) / prior * 100.0))
    out.sort(key=lambda r: (-abs(r[1]), r[0]))
    return out


def _paired(a: list[float], b: list[float]) -> tuple[float, float, int, int, int]:
    """Mean difference, its t, and the win, loss and tie counts."""
    diffs = [x - y for x, y in zip(a, b)]
    mean = statistics.mean(diffs) if diffs else 0.0
    if len(diffs) > 1 and statistics.pstdev(diffs) > 0:
        t = mean / (statistics.stdev(diffs) / math.sqrt(len(diffs)))
    else:
        t = 0.0
    wins = sum(1 for d in diffs if d > 1e-12)
    losses = sum(1 for d in diffs if d < -1e-12)
    return mean, t, wins, losses, len(diffs) - wins - losses


def _sign_p(wins: int, losses: int) -> float:
    """Two sided sign test on the sessions that moved, exact binomial."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def evaluate(as_of: str | None) -> int:
    from night import pool_recall
    from research import backtest_pool

    big_floor = _CRIT.number("discovery", "recall_big_gap_pct")
    cap = _CRIT.integer("discovery", "max_subscribed_candidates")
    floor_slots = _CRIT.integer("discovery", "min_slots_per_tier")
    base_metrics = backtest_pool.load_metrics(as_of)
    ordering = backtest_pool.ORDERINGS["SHIPPED"]

    def shipped_for(day: str, inputs: dict[str, Any]) -> list[str] | None:
        """The names the shipped configuration would have subscribed.

        Metrics are resolved PER SESSION, the way sweep() does it, because
        two of the three fields are per session facts and reading them off
        today's universe is what made this stage unreproducible once already.
        """
        try:
            metrics, _where = backtest_pool.metrics_for_session(
                day, base_metrics, inputs)
            pool = backtest_pool.build_pool(inputs, metrics)
            ranked = backtest_pool.order_pool(pool, metrics, ordering)
            capped = backtest_pool.apply_cap(ranked, cap, tier_floor=floor_slots)
        except Exception:  # noqa: BLE001, a session that cannot rebuild is data
            return None
        return [r["symbol"] for r in capped if r.get("subscribed")]

    days = [d for d in _sessions() if (SWEEP_DIR / f"{d}.json").exists()]
    if not days:
        print("no sweep files. Run fetch first.")
        return 1

    arms: dict[str, list[float]] = {}
    refused: list[str] = []
    marginal_total = 0
    sessions_scored = 0

    for day in days:
        sweep = json.loads((SWEEP_DIR / f"{day}.json").read_text("utf-8"))
        if sweep.get("symbols_with_bars", 0) < MIN_SYMBOLS_WITH_BARS:
            refused.append(f"{day}: only {sweep.get('symbols_with_bars')} symbol(s) "
                           "returned a bar, under the pre-registered floor of "
                           f"{MIN_SYMBOLS_WITH_BARS}")
            continue
        inputs = json.loads((SESSIONS_DIR / day / "inputs.json").read_text("utf-8"))
        outcome = json.loads((SESSIONS_DIR / day / "outcome.json").read_text("utf-8"))
        gappers, _actions = backtest_pool.refuse_corporate_actions(
            day, inputs.get("prior_session"), outcome["gappers"])
        big = {s for s, r in gappers.items()
               if abs(float(r.get("gap_at_open_pct") or 0.0)) >= big_floor}
        if not big:
            continue

        shipped = shipped_for(day, inputs)
        if shipped is None:
            refused.append(f"{day}: the shipped arm could not be rebuilt")
            continue

        closes = inputs.get("prior_closes") or {}
        for floor in (DOLLAR_FLOOR, *FLOOR_SENSITIVITIES):
            ranked = [s for s, _g in _ranked_sweep(sweep, closes, floor)]
            alone = set(ranked[:cap])
            arms.setdefault(f"A floor {floor:,.0f}", []).append(
                len(alone & big) / len(big))
            if floor != DOLLAR_FLOOR:
                continue
            for k in (K_PRIMARY, *K_SENSITIVITIES):
                fresh = [s for s in ranked if s not in shipped][:k]
                union = set(list(shipped)[:cap - k]) | set(fresh)
                arms.setdefault(f"C K={k}", []).append(len(union & big) / len(big))
            marginal_total += len({s for s in ranked[:K_PRIMARY]} & big - set(shipped))
        arms.setdefault("B shipped", []).append(len(set(shipped) & big) / len(big))
        sessions_scored += 1

    if not sessions_scored:
        print("no session could be scored")
        return 1

    print(f"\npremarket prior test, {sessions_scored} session(s) scored, "
          f"{len(refused)} refused")
    for line in refused[:10]:
        print("  refused", line)
    print(f"\n  {'arm':22} {'mean recall':>12} {'vs shipped':>12} {'t':>8} "
          f"{'win':>5} {'lose':>5} {'sign p':>8}")
    base = arms.get("B shipped") or []
    for name in sorted(arms):
        vals = arms[name]
        if len(vals) != len(base):
            print(f"  {name:22} {statistics.mean(vals):12.4f}   (not paired)")
            continue
        mean, t, wins, losses, _ties = _paired(vals, base)
        p = _sign_p(wins, losses)
        flag = "" if name.startswith("B") else f"{mean:+12.4f} {t:8.2f} {wins:5} {losses:5} {p:8.4f}"
        print(f"  {name:22} {statistics.mean(vals):12.4f} {flag}")
    print(f"\n  big gappers the primary sweep adds that the shipped pool missed: "
          f"{marginal_total}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--sessions", type=int, default=None)
    f.add_argument("--force", action="store_true")
    e = sub.add_parser("evaluate")
    e.add_argument("--as-of", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "fetch":
        return fetch(args.sessions, args.force)
    return evaluate(args.as_of)


OK_CODES = (0,)

if __name__ == "__main__":
    sys.exit(main())
