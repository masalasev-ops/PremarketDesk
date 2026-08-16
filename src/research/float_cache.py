"""Cache sharesFloat for every name that has been an addressable gapper.

Float rotation needs a share count, and the share count is the one part of it
that costs quota. us-quote-delayed bills roughly one credit per symbol and
already carries sharesFloat next to the marketCap the universe build reads, so
no new endpoint is involved, but 1,870 names is 1,870 credits and that is not
something to spend twice.

So this writes data/float_cache.json once and the study reads it. The cache is
a research input for setting the scoring bands, NOT a live dependency: the
morning scan reads sharesFloat straight off the quote it already fetches for
market cap, and never opens this file.

One limitation, stated rather than buried. A float fetched today is applied to
a session from May. Floats move on buybacks, lockup expiries and secondary
offerings, so a per-name claim from this cache would be wrong. It is used for a
distribution, where that error is noise, and the bands it sets are coarse
enough that it does not decide a band edge.

Run:

    PYTHONPATH=src .venv/Scripts/python.exe -m research.float_cache
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from core import config, criteria, eodhd
from night import pool_recall

_CRIT = criteria.load()

EOD_DIR = config.DATA_DIR / "backtest" / "eod"
CACHE_PATH = config.DATA_DIR / "float_cache.json"

# The fields kept per symbol. sharesOutstanding rides along because the ratio
# of the two is the sanity check on a float that looks wrong: a float equal to
# shares outstanding usually means the vendor has no real float figure and is
# falling back, and a float above outstanding is impossible and gets dropped.
_KEEP = ("sharesFloat", "sharesOutstanding", "marketCap")


def addressable_symbols() -> set[str]:
    """Every name that was an addressable gapper on any cached session."""
    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    universe_rows = {str(r.get("symbol", "")).upper(): r for r in payload["symbols"]}
    universe_symbols = set(universe_rows)
    gap_rule = _CRIT.rule("discovery", "gap_pct")

    days = sorted(p.stem for p in EOD_DIR.glob("*.json"))
    out: set[str] = set()
    for prior, today in zip(days, days[1:]):
        prior_cache = json.loads((EOD_DIR / f"{prior}.json").read_text(encoding="utf-8"))
        today_cache = json.loads((EOD_DIR / f"{today}.json").read_text(encoding="utf-8"))
        prior_closes = {s: b["c"] for s, b in prior_cache.items() if b.get("c")}
        rows = [{"code": s, "open": b.get("o"), "volume": b.get("v")}
                for s, b in today_cache.items()]
        gappers = pool_recall.actual_gappers(rows, prior_closes, universe_symbols, gap_rule)
        out |= set(pool_recall.addressable_target(gappers, universe_rows)["addressable"])
    return out


def load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except ValueError:
            print("float_cache: existing cache is not readable, starting over")
    return {"fetched_at": None, "symbols": {}}


def build(limit: int | None = None) -> dict[str, Any]:
    api = eodhd.client()

    # Read the meter before spending, the same preflight discover and scan run.
    status, error = api.user_status()
    if error or not status:
        raise SystemExit(f"float_cache: could not read the quota meter: {error}")
    remaining = int(status["dailyRateLimit"]) - int(status["apiRequests"])
    print(f"float_cache: quota meter says {remaining:,} calls remaining today")

    cache = load_cache()
    have = set(cache["symbols"])
    want = addressable_symbols()
    todo = sorted(want - have)
    if limit is not None:
        todo = todo[:limit]

    print(f"float_cache: {len(want):,} addressable gappers, {len(have):,} already cached, "
          f"{len(todo):,} to fetch")
    if len(todo) > remaining:
        raise SystemExit(
            f"float_cache: REFUSING to start. {len(todo):,} symbols cost about the same "
            f"number of credits and the meter has {remaining:,}. Rerun after the counter "
            "resets at 00:00 UTC, or pass --limit to fetch part of it now."
        )
    if not todo:
        print("float_cache: nothing to fetch")
        return cache

    batch = _CRIT.integer("api", "quote_batch_size")
    fetched = missing = 0
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        data, error = api.quote_delayed(chunk)
        if error and not data:
            print(f"float_cache: batch at {start} failed: {error}")
            continue
        for symbol, quote in (data or {}).items():
            key = symbol.upper()
            row = {field: quote.get(field) for field in _KEEP}
            cache["symbols"][key] = row
            if row.get("sharesFloat"):
                fetched += 1
            else:
                missing += 1
        done = min(start + batch, len(todo))
        if done % (batch * 20) == 0 or done == len(todo):
            print(f"float_cache: {done:,}/{len(todo):,}")

    cache["fetched_at"] = eodhd.quota_day()
    CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    print(f"float_cache: wrote {CACHE_PATH} with {len(cache['symbols']):,} symbols, "
          f"{fetched:,} carrying a float this run, {missing:,} without one")
    return cache


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cache sharesFloat for the addressable gappers.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Fetch at most this many new symbols, for a partial run "
                             "when the quota meter is low.")
    args = parser.parse_args(argv)
    build(limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
