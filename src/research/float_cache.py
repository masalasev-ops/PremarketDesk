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
        # (gappers, census) since 2026-08-22; the cached bars carry no
        # adjusted_close, so the census reports every row unchecked.
        gappers, _census = pool_recall.actual_gappers(
            rows, prior_closes, universe_symbols, gap_rule)
        out |= set(pool_recall.addressable_target(gappers, universe_rows)["addressable"])
    return out


def load_cache() -> dict[str, Any]:
    """The cache file, with both of its symbol maps guaranteed to be present.

    "symbols" is what came back. "unanswered" is what did not, keyed the same
    way and carrying the reason, so a reader who opens the file can tell a name
    the vendor answered without a float from a name nothing ever came back for.
    A file written before that second map existed carries only the first, so it
    is filled in here rather than at every use site.
    """
    cache: dict[str, Any] = {"fetched_at": None, "symbols": {}, "unanswered": {}}
    payload: Any = None
    if CACHE_PATH.exists():
        try:
            payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except ValueError:
            print("float_cache: existing cache is not readable, starting over")
    if isinstance(payload, dict):
        cache.update(payload)
    elif payload is not None:
        print("float_cache: existing cache is not a JSON object, starting over")
    # Both maps are read as dicts everywhere below, so a file missing one, or
    # carrying something else under the key, is repaired here rather than
    # guarded against at each use. Starting over loses nothing that a rerun
    # cannot re-fetch, and the run says so rather than failing at the first
    # `.get` on whatever was in the file.
    for key in ("symbols", "unanswered"):
        if not isinstance(cache.get(key), dict):
            # Said out loud rather than repaired in silence. Discarding this map
            # sends the sweep below to re-fetch every name in it, and this
            # module exists because 1,870 names is 1,870 credits and that is not
            # something to spend twice. A run that prints "1,870 to fetch" over
            # a cache that was on disk a moment ago has to say why.
            if cache.get(key) is not None:
                print(f"float_cache: the cache's {key} map is a "
                      f"{type(cache[key]).__name__} rather than an object, so it "
                      "is being discarded and every name in it will be fetched again")
            cache[key] = {}
    return cache


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
    # The names asked for that came back with nothing, kept as a map from name
    # to reason rather than as a count for the same reason CapSweep in
    # selection/universe keeps one: the absences below are different facts and
    # only one of them is about the market. A symbol the vendor answered without
    # a sharesFloat is a hole in its float coverage. A symbol nothing came back
    # for was never really asked, and the useful things to know about it are its
    # name, because that is what the next run has to go back for, and which of
    # the two silences it met, because they fail differently.
    unanswered: dict[str, dict[str, str]] = {}
    # The two silences counted apart, under the names selection/universe gives
    # its own doors, because a batch that never answered is a network or vendor
    # outage to re-run and a name dropped out of a body that did answer is the
    # endpoint quietly serving less than it was asked for.
    in_an_unanswered_batch = absent_from_answered_batch = 0
    asked_on = eodhd.quota_day()
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        data, error = api.quote_delayed(chunk)
        # The test is on the DATA, not on the error, and that is the whole point
        # of this guard. It used to read `if error and not data`, which is the
        # same hole universe._attach_market_caps closed: when a chunk comes back
        # 200 with a body eodhd.quote_delayed does not recognise, it returns
        # ({}, None), so there is no error to record and no rows to record
        # against. The old guard was False, the loop below ran over an empty
        # dict and did nothing, and a whole batch of names left the run counted
        # as neither fetched nor missing, vanishing without a word anywhere and
        # indistinguishable from a vendor that simply carries no float for them.
        # Testing the data is the correct test because it asks the question that
        # actually matters here, did this batch answer, rather than the question
        # of whether it troubled itself to say why it did not.
        if not data:
            silence = error or "the response carried no rows"
            for name in chunk:
                unanswered[name] = {
                    "reason": f"the batch covering it was not answered: {silence}",
                    "asked_on": asked_on,
                }
                in_an_unanswered_batch += 1
            print(f"float_cache: batch {start // batch}, covering {len(chunk)} names, "
                  f"was not answered: {silence}")
        else:
            answered: set[str] = set()
            for symbol, quote in data.items():
                key = symbol.upper()
                cache["symbols"][key] = {field: quote.get(field) for field in _KEEP}
                # A name that has just answered is no longer a name nothing came
                # back for, so the note goes in the same statement that writes
                # the row. That is what keeps the persisted list below from
                # going stale: the file can never carry a name in both maps.
                cache["unanswered"].pop(key, None)
                answered.add(key)
            # The third door, and it is the one the guard above leaves open. A
            # batch can answer AND leave names out of its body: eodhd.quote_delayed
            # chunks internally and returns what it merged when one inner chunk
            # fails, so `data` is truthy while some of the twenty are simply not
            # in it. selection/universe records exactly this as
            # absent_from_answered_batch and names the day the endpoint
            # demonstrably did it, 26 names on the 2026-08-17 rebuild, so it is
            # not a hypothetical door. Without it those names are counted as
            # neither fetched nor missing nor unanswered, never reach
            # cache["symbols"], and are therefore re-requested at a credit each
            # on every future run with nothing anywhere saying why.
            #
            # The counting runs over the CHUNK rather than over the rows that
            # came back, which is what makes the parts sum to the whole below. A
            # row for a symbol nobody asked for is still kept, it just cannot be
            # one of the answers to a question this run asked.
            absent: list[str] = []
            for name in chunk:
                if name not in answered:
                    absent.append(name)
                    absent_from_answered_batch += 1
                    unanswered[name] = {
                        "reason": "its batch answered without mentioning it"
                                  + (f": {error}" if error else ""),
                        "asked_on": asked_on,
                    }
                elif cache["symbols"][name].get("sharesFloat"):
                    fetched += 1
                else:
                    missing += 1
            if absent:
                print(f"float_cache: batch {start // batch} answered "
                      f"{len(chunk) - len(absent)} of {len(chunk)} names, "
                      f"{len(absent)} absent from a body that did answer: "
                      f"{error or 'the response simply did not carry them'}")
        # Outside both branches on purpose. While this sat under the answered
        # path alone, a sweep whose LAST batch went unanswered never printed its
        # completion line, so the final thing on stdout was whatever earlier
        # multiple of the progress cadence came before it and a reader watching
        # the sweep saw it stop short of its own total with no word about the
        # rest. The batch notes above name a batch index rather than a running
        # total, so they do not compose into that picture on their own.
        done = min(start + batch, len(todo))
        if done % (batch * 20) == 0 or done == len(todo):
            print(f"float_cache: {done:,}/{len(todo):,}")

    # Merged rather than replaced. A --limit run asks for part of the list, and
    # a name it never got to still carries a true note from the run that did ask
    # for it. The only entry that can go stale is one whose name has since
    # answered, and that one is dropped up in the loop, where the answer arrives.
    cache["unanswered"].update(unanswered)

    # The stamp only advances when this run actually put a row in the file. It
    # used to be set unconditionally, so a sweep where every batch went
    # unanswered left a file claiming it was fetched today while carrying
    # nothing new at all, which is the same shape of lie PartialBuildError
    # exists to prevent in selection/universe: a starved run leaving a record
    # that reads as a healthy one. The file is still written, because the
    # unanswered map IS what a starved run learned and it is worth keeping, but
    # fetched_at keeps naming the day the symbols in it actually came from.
    if fetched or missing:
        cache["fetched_at"] = asked_on
    else:
        print("float_cache: no row came back this run, so fetched_at stays at "
              f"{cache.get('fetched_at') or 'never'} rather than claiming today")
    CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    print(f"float_cache: wrote {CACHE_PATH} with {len(cache['symbols']):,} symbols, "
          f"{fetched:,} carrying a float this run, {missing:,} answered without one, "
          f"{absent_from_answered_batch:,} absent from a batch that answered, "
          f"{in_an_unanswered_batch:,} in a batch that answered nothing")
    # The summary has to reconcile against what was asked for, the same way the
    # market cap funnel in selection/universe has to close. Every name in todo
    # left this sweep by exactly one of the four doors above, so if the four do
    # not sum to len(todo) then a name went somewhere this accounting does not
    # describe, which is a defect here rather than in the data and should say so
    # rather than quietly under report.
    accounted = fetched + missing + absent_from_answered_batch + in_an_unanswered_batch
    if accounted != len(todo):
        print(f"float_cache: the sweep does not reconcile: {len(todo):,} names were "
              f"asked for and {accounted:,} left by a recorded door, leaving "
              f"{len(todo) - accounted:,} unaccounted for, which is a defect in this "
              "accounting rather than in the data")
    if unanswered:
        # Named rather than counted, and reported on its own line, so a starved
        # sweep reads differently from a vendor with poor float coverage. Folded
        # together they arrive as one low float count with no way to tell the
        # two apart, and they call for opposite responses: the starved sweep is
        # re-run, the thin coverage is a fact about the data that the scoring
        # bands have to be set around.
        #
        # Written into the file as well as printed, which reverses the decision
        # that stood here, and the reason it was wrong is worth stating rather
        # than quietly repairing. That comment argued the cache is keyed by
        # symbol and a name absent from it is exactly the state the next run
        # acts on, since todo is want minus have. True of the re-ask question,
        # false of the read question: research/float_rotation_study opens this
        # file, and a name absent from it read there as a name answered without
        # a float, folding a starved cache into the vendor's float coverage in
        # the one module that sets the scoring bands. Stdout at build time is
        # not somewhere a later reader can consult. The staleness the old
        # comment feared is real and is handled where the answer arrives.
        #
        # Only the head of the list is printed. A fully starved sweep is roughly
        # 1,870 tickers, and one comma separated line of them as the last thing
        # before the process exits tells a reader less than the count does. The
        # file carries all of them.
        listed = _CRIT.integer("api", "max_symbols_named_per_line")
        names = sorted(unanswered)
        line = "float_cache: never answered for, still uncached: " + ", ".join(names[:listed])
        if len(names) > listed:
            line += (f", and {len(names) - listed:,} more, all of them under "
                     f"'unanswered' in {CACHE_PATH.name}")
        print(line)
    return cache


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
