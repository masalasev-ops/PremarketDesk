"""Does Alpaca's free tier serve the premarket LIVE, or only in hindsight?

Standalone. Nothing in any chain imports this, nothing reads its output, and it
writes only to data/probe-alpaca-live-<date>.jsonl. It exists to answer one
question and then to be deleted or kept as evidence.

The question, and why it is the only one that matters right now. doc/
ALPACA_PROBE.md measured a full 2,745 name sweep at 4 requests and 1.04
seconds, and DECISIONS.md 2026-08-16 argues from that number that discovery
should move off the 50 slot websocket entirely. Every one of those
measurements was taken on a SATURDAY against a completed session. They prove
historical access and nothing else.

Three ways the live case can differ from the historical one, all of them fatal
to that design if true:

  the free tier may serve SIP only after a delay, which is invisible when the
  data is a day old and decisive at 08:45;

  the sweep may return no bars at all for the current session until the feed
  rolls, which is exactly the failure mode the EODHD bulk endpoint had and
  which published the wrong prices on 2026-08-14;

  the lag may be real but small, in which case the design stands and the number
  to record is how small.

What actually happened was a fourth thing, recorded here because the three
above do not include it and the code was written as though they did. On
2026-08-16 and again on 2026-08-17 every request was REFUSED, HTTP 403: the
free tier will not serve the sip feed over a window that ends at the wall
clock. A refused sweep and an empty one produced identical zeros until
2026-08-20, when the served and refused counts were carried into the table and
the no-bars prose was made to stop interpreting a sweep nobody answered. The
only file on disk where this sweep was ever served is the 2026-08-14 dry run,
against a session that had already completed.

So this samples the whole universe every five minutes through the premarket and
records, per sample: how many symbols have any bar today, how far the newest
bar is behind the wall clock, and the top names by gap computed from those
bars. The collector's own file sits beside it as ground truth for the names it
subscribed to, the same role it plays in probe_live_v1: it is a trade socket,
so if a print happened it has it.

The prior closes come from Alpaca's own daily bars, fetched once at startup, so
this probe spends NO EODHD quota at all and cannot compete with the morning
chain for it.

Cost. About 4 requests per sample against a 200 per minute limit, plus 4 once
for the daily bars. Roughly 100 requests across the whole run.

  python -m research.probe_alpaca_live            run the sampling loop
  python -m research.probe_alpaca_live --once     take a single sample now
  python -m research.probe_alpaca_live --report   read the log back as a table
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from collect import collect_premarket
from core import config
from core import criteria
from core import ettime
import probe_alpaca

_CRIT = criteria.load()

START_HHMM = (7, 30)
STOP_HHMM = (9, 20)
INTERVAL_S = 300

# How many gappers to record per sample. Enough to see whether the leaderboard
# is stable as the morning goes on, not so many that the log becomes the data.
TOP_N = 20

# Symbols per request. Named rather than left inline because the report has to
# reconstruct a request count for sweeps logged before 2026-08-20, when the
# served and refused counts were not recorded at all, and that reconstruction
# needs to know how many chunks a sweep of a given size was cut into.
CHUNK_SIZE = 2000


def log_path(day: str | None = None) -> Path:
    return config.DATA_DIR / f"probe-alpaca-live-{day or ettime.today_str()}.jsonl"


def universe_codes() -> list[str]:
    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    return [row["code"] for row in payload["symbols"]]


def prior_closes(probe: probe_alpaca.Probe, codes: list[str], today: dt.date) -> dict[str, float]:
    """Yesterday's close per symbol, from Alpaca daily bars.

    Taken from Alpaca rather than the end of day cache so the probe is
    self contained: the cache is written by the nightly, and a probe that
    silently depends on last night's job having succeeded would report a feed
    problem when what actually happened was a missed nightly.
    """
    start = (today - dt.timedelta(days=10)).isoformat()
    end = (today - dt.timedelta(days=1)).isoformat()
    closes: dict[str, float] = {}
    for index in range(0, len(codes), CHUNK_SIZE):
        chunk = codes[index:index + CHUNK_SIZE]
        token = None
        while True:
            params = {"symbols": ",".join(chunk), "timeframe": "1Day",
                      "start": start, "end": end, "limit": 10000, "feed": "sip"}
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            if status != 200:
                break
            for symbol, bars in ((payload.get("bars") or {}).items()):
                if bars:
                    closes[symbol] = float(bars[-1].get("c") or 0)
            token = payload.get("next_page_token")
            if not token:
                break
    return closes


def sample(
    probe: probe_alpaca.Probe,
    codes: list[str],
    closes: dict[str, float],
    today: dt.date,
    as_of: dt.datetime | None = None,
) -> dict[str, Any]:
    """One whole universe sweep of today's premarket, with the wall clock beside it.

    as_of overrides the wall clock and exists only for --dry-run, which sweeps
    a PAST session so the table can be seen carrying real numbers before the
    one morning that matters. Nothing on the live path passes it.
    """
    taken_at = as_of or ettime.now_et()
    session_start = _CRIT.clock("baseline", "session_start")
    window_open = dt.datetime(today.year, today.month, today.day,
                              session_start[0], session_start[1], tzinfo=ettime.ET)
    start_utc = window_open.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = taken_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    last_price: dict[str, float] = {}
    last_epoch: dict[str, int] = {}
    volume: dict[str, float] = {}
    bars_total = 0
    errors: list[str] = []
    # Counted here rather than left to be inferred downstream. The 2026-08-17
    # run was read as an empty premarket for two whole days because nothing
    # after this function looked at the refusals: every chunk of every sweep
    # came back 403, and a refused sweep printed a zero active count that was
    # indistinguishable from a feed that answered and had nothing in it.
    requests_served = 0
    requests_refused = 0
    refusal_codes: set[int] = set()

    for index in range(0, len(codes), CHUNK_SIZE):
        chunk = codes[index:index + CHUNK_SIZE]
        token, pages = None, 0
        while True:
            params = {"symbols": ",".join(chunk), "timeframe": "1Min",
                      "start": start_utc, "end": end_utc, "limit": 10000, "feed": "sip"}
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            pages += 1
            if status != 200:
                requests_refused += 1
                refusal_codes.add(int(status))
                errors.append(f"chunk at {index}: status {status}")
                break
            requests_served += 1
            for symbol, bars in ((payload.get("bars") or {}).items()):
                for bar in bars or []:
                    bars_total += 1
                    stamp = bar.get("t") or ""
                    epoch = 0
                    if stamp:
                        try:
                            epoch = int(dt.datetime.fromisoformat(
                                stamp.replace("Z", "+00:00")).timestamp())
                        except ValueError:
                            epoch = 0
                    volume[symbol] = volume.get(symbol, 0.0) + float(bar.get("v") or 0)
                    if epoch >= last_epoch.get(symbol, 0):
                        last_epoch[symbol] = epoch
                        last_price[symbol] = float(bar.get("c") or 0)
            token = payload.get("next_page_token")
            if not token or pages >= 400:
                break

    newest = max(last_epoch.values()) if last_epoch else 0
    lag_minutes = (
        round((taken_at - ettime.from_epoch_s(newest)).total_seconds() / 60.0, 1)
        if newest else None
    )
    lags = [
        round((taken_at - ettime.from_epoch_s(e)).total_seconds() / 60.0, 1)
        for e in last_epoch.values() if e
    ]

    gaps = []
    for symbol, price in last_price.items():
        close = closes.get(symbol)
        if close and price:
            gaps.append({
                "symbol": symbol,
                "gap_pct": round((price - close) / close * 100.0, 4),
                "price": price,
                "prior_close": close,
                "premarket_volume": volume.get(symbol),
                "last_bar_et": ettime.stamp(ettime.from_epoch_s(last_epoch[symbol])),
            })
    gaps.sort(key=lambda row: abs(row["gap_pct"]), reverse=True)

    return {
        "taken_at_et": ettime.stamp(taken_at),
        "window": {"start": start_utc, "end": end_utc},
        "symbols_requested": len(codes),
        "symbols_with_bars": len(last_price),
        "bars_total": bars_total,
        "newest_bar_et": ettime.stamp(ettime.from_epoch_s(newest)) if newest else None,
        "lag_minutes_newest": lag_minutes,
        "lag_minutes_median": round(statistics.median(lags), 1) if lags else None,
        "gappers_over_3pct": sum(1 for g in gaps if abs(g["gap_pct"]) > 3.0),
        "top_gappers": gaps[:TOP_N],
        "requests_used": probe.request_count,
        # These three are recorded rather than derived from "errors", which is
        # truncated to four entries and therefore cannot be counted.
        "requests_served": requests_served,
        "requests_refused": requests_refused,
        "refusal_status_codes": sorted(refusal_codes),
        "errors": errors[:4],
    }


def _collector_check(record: dict[str, Any], day: str) -> dict[str, Any]:
    """The collector's own view of the same names, as ground truth.

    Only meaningful for names the collector subscribed to, which is the point:
    where both saw a name, the two premarket volumes should be close, and a
    large disagreement says one of the feeds is not describing this morning.
    """
    try:
        bars = collect_premarket.read_bars(day)
    except (OSError, ValueError):
        return {"available": False, "reason": "the collector file could not be read"}
    if not bars:
        return {"available": False, "reason": "the collector has written no bars yet"}

    collector_volume: dict[str, float] = {}
    for symbol, rows in bars.items():
        code = symbol.split(".")[0]
        collector_volume[code] = sum(float(r.get("volume") or 0) for r in rows)

    compared = []
    for row in record["top_gappers"]:
        mine = collector_volume.get(row["symbol"])
        if mine is None:
            continue
        theirs = row.get("premarket_volume") or 0
        compared.append({
            "symbol": row["symbol"],
            "collector_volume": mine,
            "alpaca_volume": theirs,
            "ratio": round(theirs / mine, 3) if mine else None,
        })
    return {
        "available": True,
        "collector_symbols": len(collector_volume),
        "overlap_with_top": len(compared),
        "compared": compared[:8],
    }


# The documented delay on a free tier SIP feed. Not a threshold anything acts
# on, and deliberately not in CRITERIA for that reason: it is the vendor's
# claim, and this probe exists to find out whether it holds. It is printed
# beside the observed lag so the two can be compared without arithmetic.
DOCUMENTED_LAG_MINUTES = 15.0

TABLE_PATH_STEM = "probe-alpaca-live-table"


def sweep_requests(record: dict[str, Any]) -> dict[str, Any]:
    """How many of one sweep's requests were answered, and how many refused.

    Sweeps logged from 2026-08-20 carry the counts on the record. Earlier ones
    carry only record["errors"], which sample() truncates to four entries, so
    for those the counts are reconstructed from what the log does say.

    The reconstruction rests on three facts about sample(). Every chunk costs
    at least one request. A chunk is abandoned at its first non-200, so it
    contributes at most one entry to the error list. And a chunk issues a
    SECOND request only when the first came back carrying a page token, which
    only happens when bars came with it. So for a sweep that returned no bars,
    every chunk made exactly one request and the error list accounts for every
    one of them that was turned away, which is knowable from an old record and
    is precisely the 2026-08-17 case.

    Where a reconstructed number is only a floor, the flags say so and the
    table prints "at least". Presenting a floor as a measurement is the same
    class of error this whole helper exists to undo.
    """
    requested = int(record.get("symbols_requested") or 0)
    chunks = max(1, -(-requested // CHUNK_SIZE))

    errors = [str(text) for text in (record.get("errors") or [])]
    codes = record.get("refusal_status_codes")
    if codes is None:
        codes = []
        for text in errors:
            head, _, tail = text.rpartition("status ")
            if head and tail.strip().isdigit():
                codes.append(int(tail.strip()))
        codes = sorted(set(codes))

    refused = record.get("requests_refused")
    # errors is capped at four entries, so a full list is a floor rather than
    # a count. It has never been reached: the universe is two chunks wide.
    refused_exact = refused is not None or len(errors) < 4
    if refused is None:
        refused = len(errors)
    refused = int(refused)

    served = record.get("requests_served")
    served_exact = served is not None
    if served is None:
        if not record.get("bars_total"):
            # No bars came back, so no page token did either, so every chunk
            # made exactly one request. This is a count, not a floor.
            served = max(chunks - refused, 0)
            served_exact = True
        else:
            # Bars came back, so at least one request per chunk was answered
            # and the page count is not recoverable from an old record. It is
            # not needed either: what the report has to know is whether
            # ANYTHING was served, and a floor answers that.
            served = max(chunks - refused, 1)
    return {"served": int(served), "served_exact": bool(served_exact),
            "refused": refused, "refused_exact": bool(refused_exact),
            "codes": list(codes)}


def _codes_text(codes: list[int]) -> str:
    """The refusal codes as text.

    Probe.get returns status 0 when the request never got an HTTP answer at
    all, which is a different failure from a refusal and would read as a status
    code if it were printed as a number.
    """
    if not codes:
        return "none"
    return ", ".join("no response" if code == 0 else str(code) for code in codes)


def _codes_phrase(codes: list[int]) -> str:
    """The refusal codes as they read inside a sentence."""
    if not codes:
        return "no recorded status"
    if codes == [0]:
        return "no HTTP answer at all"
    if len(codes) == 1:
        return f"status {codes[0]}"
    return f"statuses {_codes_text(codes)}"


def _count_text(value: int, exact: bool, short: bool = False) -> str:
    """A count, or a floor labelled as one."""
    if exact:
        return f"{value:,}"
    return f"{value:,}+" if short else f"at least {value:,}"


def _plural(count: int, noun: str, exact: bool = True) -> str:
    """A count and its noun, agreeing. A floor always takes the plural."""
    word = noun if (exact and count == 1) else f"{noun}s"
    return f"{_count_text(count, exact)} {word}"


def _table_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The numbers the decision rests on, one row per sweep.

    Wall clock, newest bar anywhere in the universe, the difference between
    them, and how many names had any premarket bar at all. The lag is the
    number that decides whether the sweep is usable: a feed that works but
    runs an hour behind cannot support an 08:45 freeze, and the report would
    have to say so rather than quietly publish stale prices, which is exactly
    the 2026-08-14 defect.

    The active count is here rather than inferred because its GROWTH through
    the morning is the other half of the picture. A count that climbs from a
    few hundred at 07:30 to a few thousand by 09:00 is a feed filling up
    normally; one that is flat near zero is a feed that does not serve this
    session at all.

    The served and refused counts joined them on 2026-08-20, because that last
    sentence turned out to have a third case it did not cover. A flat zero is
    also what a sweep looks like when every request in it was turned away, and
    until this row carried the refusals the two were the same table. The
    2026-08-17 run was 46 requests, all 403, and it printed as an empty feed.
    """
    rows = []
    previous = None
    for record in records:
        lag = record.get("lag_minutes_newest")
        active = record.get("symbols_with_bars", 0)
        requests = sweep_requests(record)
        rows.append({
            "clock_et": record["taken_at_et"][11:19],
            "newest_bar_et": (str(record.get("newest_bar_et") or "")[11:19]) or None,
            "observed_lag_minutes": lag,
            "vs_documented": (
                round(lag - DOCUMENTED_LAG_MINUTES, 1) if lag is not None else None),
            "median_lag_minutes": record.get("lag_minutes_median"),
            "active_names": active,
            "new_since_last": (active - previous) if previous is not None else None,
            "bars_total": record.get("bars_total", 0),
            "gappers_over_3pct": record.get("gappers_over_3pct", 0),
            "requests_served": requests["served"],
            "requests_served_exact": requests["served_exact"],
            "requests_refused": requests["refused"],
            "requests_refused_exact": requests["refused_exact"],
            "refusal_codes": requests["codes"],
        })
        previous = active
    return rows


def write_table(records: list[dict[str, Any]], day: str) -> Path:
    """Persist the per sweep table as markdown, so it outlives the terminal.

    A probe whose result only ever existed in a scrollback is a probe that has
    to be run again, and this one cannot be: it needs a live premarket.
    """
    rows = _table_rows(records)
    lags = [r["observed_lag_minutes"] for r in rows if r["observed_lag_minutes"] is not None]
    dry = any(record.get("dry_run") for record in records)
    served_total = sum(r["requests_served"] for r in rows)
    served_exact = all(r["requests_served_exact"] for r in rows)
    refused_total = sum(r["requests_refused"] for r in rows)
    refused_exact = all(r["requests_refused_exact"] for r in rows)
    codes_seen = sorted({code for r in rows for code in r["refusal_codes"]})
    # A served total of zero is never a floor: the reconstruction only produces
    # a floor when bars came back, and bars mean something was served.
    nothing_served = bool(refused_total) and not served_total
    # Some refused and some answered, which is the shape the served versus
    # refused split was added for and the one it could not describe. Every word
    # about refusals sat under "no sweep returned a bar", so a run where some
    # chunks came back 403 and the rest returned bars printed the best, median
    # and worst lag with no mention of the refusals anywhere in the file. Those
    # figures are readings of the part of the universe that answered, and
    # unlabelled they read as readings of the whole of it, which is the
    # 2026-08-17 misreport with the sign flipped: there an unanswered sweep was
    # published as an empty feed, here a partial answer is published as a full
    # one.
    partly_refused = bool(refused_total) and bool(served_total)

    def partial_refusal_note(with_bars: bool) -> list[str]:
        """The paragraph a partially refused run gets, bars or no bars."""
        body = (
            "Part of this run was never answered, so the lag above, the active "
            "count and the bar count are readings of the part that WAS. They "
            "are floors for the universe and never totals of it."
            if with_bars else
            "Part of this run was never answered, so the emptiness of the part "
            "that was cannot be extended over it. There is a reading here of "
            "what came back, and none of the whole morning.")
        return [
            "Read the refusal column first. Refused: "
            f"{_plural(refused_total, 'request', refused_exact)}, "
            f"{_codes_phrase(codes_seen)}. Answered: "
            f"{_count_text(served_total, served_exact)}. " + body,
            "",
        ]

    lines = [
        f"# Alpaca live premarket probe, {day}",
        "",
        f"{len(rows)} sweeps. Every number observed, nothing inferred from documentation.",
        "",
    ]
    if nothing_served:
        # Loudly, and at the top, for the same reason the dry run banner is:
        # the zeros below get quoted by someone who did not read the file that
        # produced them, and on 2026-08-17 that is exactly what happened.
        lines += [
            f"> **EVERY REQUEST IN EVERY SWEEP WAS REFUSED.** "
            f"{_plural(refused_total, 'request', refused_exact)} "
            f"across {_plural(len(rows), 'sweep')}, "
            f"{_codes_phrase(codes_seen)}, and not one "
            "of them answered. The zeros in the columns below count what came back "
            "from a feed that never replied, not what the premarket held, so NOTHING "
            "here is evidence about the contents of the feed. What the refusals are "
            "evidence of is narrower and firmer: this key was refused this feed for "
            "this window, on every request, for the whole of the run.",
            "",
        ]
    if partly_refused:
        # At the top for the same reason as the banner above it: the columns
        # get quoted by someone who did not read the file that produced them,
        # and a column filled from half a universe looks exactly like one
        # filled from all of it.
        lines += [
            f"> **PART OF THIS RUN WAS REFUSED.** "
            f"{_plural(refused_total, 'request', refused_exact)} came back "
            f"{_codes_phrase(codes_seen)} against "
            f"{_count_text(served_total, served_exact)} answered. Every column "
            "below counts what the ANSWERED requests returned, so the active "
            "names, the bar totals and the lag describe the part of the "
            "universe that was served and are floors for the whole of it.",
            "",
        ]
    if dry:
        # Loudly, and at the top. A table reporting a zero minute lag is exactly
        # the sort of number that gets quoted later by someone who did not read
        # the file that produced it.
        lines += [
            "> **DRY RUN. THE LAG COLUMN HERE IS MEANINGLESS.** These sweeps were taken "
            "against a session that had already completed, with the wall clock pinned to "
            "that morning, so the bars were finished before the clock reached them and "
            "the newest bar always lands exactly on the pinned time. A lag of zero here "
            "is an artifact of the construction and says NOTHING about the live feed. "
            "This file exists to prove the table fills in and the active count climbs, "
            "before the one live morning that cannot be repeated.",
            "",
        ]
    lines += [
        "| clock ET | newest bar ET | observed lag (min) | vs documented 15 | "
        "median lag | active names | new since last | bars | gap > 3% | "
        "requests served | requests refused | refusal codes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['clock_et']} | {row['newest_bar_et'] or 'none'} | "
            f"{row['observed_lag_minutes'] if row['observed_lag_minutes'] is not None else 'none'} | "
            f"{row['vs_documented'] if row['vs_documented'] is not None else 'none'} | "
            f"{row['median_lag_minutes'] if row['median_lag_minutes'] is not None else 'none'} | "
            f"{row['active_names']:,} | "
            f"{row['new_since_last'] if row['new_since_last'] is not None else ''} | "
            f"{row['bars_total']:,} | {row['gappers_over_3pct']} | "
            f"{_count_text(row['requests_served'], row['requests_served_exact'])} | "
            f"{_count_text(row['requests_refused'], row['requests_refused_exact'])} | "
            f"{_codes_text(row['refusal_codes'])} |"
        )
    lines.append("")
    if lags:
        lines += [
            "## Observed lag",
            "",
            f"- best {min(lags)} minutes, median {statistics.median(lags)}, worst {max(lags)}",
            f"- the documented rule is {DOCUMENTED_LAG_MINUTES:g} minutes on a free tier "
            "SIP feed, so a worst case materially above that changes what freeze time "
            "is achievable and therefore what the report can contain",
            "",
        ]
        if partly_refused:
            # This is the branch the note could not reach. It lived under the
            # else below, which needs "no sweep returned a bar", and a run with
            # some chunks refused and bars from the rest lands here.
            lines += partial_refusal_note(True)
    else:
        lines += ["## Observed lag", "",
                  "No sweep returned a bar, so there is no lag to report.",
                  ""]
        if nothing_served:
            # This branch REFUSES to interpret, and that is the whole point of
            # it. Until 2026-08-20 there was only the served-but-empty reading
            # below, and it was printed over the 2026-08-17 run, where all 46
            # requests came back 403. An unanswered sweep is not a measurement
            # of the feed's contents and must not be reported as one.
            lines += [
                f"There is also nothing to interpret. All "
                f"{_plural(refused_total, 'request', refused_exact)} "
                f"across {_plural(len(rows), 'sweep')} were refused with "
                f"{_codes_phrase(codes_seen)}, so the feed was never asked a question it "
                "answered. An empty premarket and a refused request produce the same "
                "zero here, and only the refusal column tells them apart.",
                "",
                "What the refusals DO establish, and it is the narrower and stronger "
                "of the two claims: this key was refused this feed for this window, on "
                "every request, across the whole run. That is a fact about entitlement, "
                "not about what the premarket contained, and it needs no reading of the "
                "active count at all.",
                "",
            ]
        elif partly_refused:
            lines += partial_refusal_note(False)
        else:
            lines += [
                f"All {_plural(served_total, 'request', served_exact)} were answered, "
                "and came back with nothing in them, which is what makes the emptiness "
                "a measurement.",
                "",
                "What that means depends on when this ran, and the table above says "
                "when. Sweeps taken across a trading morning with an empty active "
                "count are the answer: the free tier does not serve this session "
                "live. Sweeps taken outside a premarket window prove nothing at all, "
                "because there were no trades to serve.",
                "",
            ]
    path = config.DATA_DIR / f"{TABLE_PATH_STEM}-{day}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def report(day: str | None = None) -> int:
    session = day or ettime.today_str()
    path = log_path(session)
    if not path.is_file():
        print(f"probe: no log at {path}")
        return 0
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if not records:
        print(f"probe: {path.name} is empty")
        return 0

    rows = _table_rows(records)
    served_total = sum(r["requests_served"] for r in rows)
    served_exact = all(r["requests_served_exact"] for r in rows)
    refused_total = sum(r["requests_refused"] for r in rows)
    refused_exact = all(r["requests_refused_exact"] for r in rows)
    codes_seen = sorted({code for r in rows for code in r["refusal_codes"]})
    nothing_served = bool(refused_total) and not served_total
    partly_refused = bool(refused_total) and bool(served_total)

    print(f"probe: Alpaca live premarket, {path.name}, {len(records)} sweeps\n")
    print(f"{'clock ET':>9} {'newest bar':>11} {'lag min':>8} {'vs 15m':>7} "
          f"{'med lag':>8} {'active':>8} {'new':>6} {'bars':>9} {'gap>3%':>7} "
          f"{'served':>7} {'refused':>8} {'codes':>9}")
    for row in rows:
        print(f"{row['clock_et']:>9} {str(row['newest_bar_et'] or '-'):>11} "
              f"{str(row['observed_lag_minutes']):>8} "
              f"{str(row['vs_documented']):>7} "
              f"{str(row['median_lag_minutes']):>8} "
              f"{row['active_names']:>8,} "
              f"{str(row['new_since_last'] if row['new_since_last'] is not None else ''):>6} "
              f"{row['bars_total']:>9,} {row['gappers_over_3pct']:>7} "
              f"{_count_text(row['requests_served'], row['requests_served_exact'], True):>7} "
              f"{_count_text(row['requests_refused'], row['requests_refused_exact'], True):>8} "
              f"{_codes_text(row['refusal_codes']):>9}")

    table = write_table(records, session)
    print(f"\nprobe: per sweep table written to {table}")

    lags = [r.get("lag_minutes_newest") for r in records
            if r.get("lag_minutes_newest") is not None]
    last = records[-1]
    if nothing_served:
        # The verdict below reads the active count, and reading the active
        # count of a sweep nobody answered is what produced the 2026-08-17
        # misreport. It is not printed at all when there is nothing to read.
        print(f"\nnothing was served, so there is no verdict on the feed's contents. "
              f"All {_plural(refused_total, 'request', refused_exact)} across "
              f"{_plural(len(records), 'sweep')} were refused "
              f"with {_codes_phrase(codes_seen)}. The zero active count above is "
              f"what an unanswered sweep looks like, not what the premarket held. The "
              f"narrower claim the refusals do support: this key was refused this feed "
              f"for this window, on every request.")
    elif partly_refused:
        # The verdict below turns on the active count, and on a partially
        # refused run that count is a floor over the part of the universe that
        # answered. Printed as a verdict it would say the feed is empty when
        # what is empty is the half nobody was allowed to ask about, which is
        # the 2026-08-17 reading applied to a smaller slice.
        print(f"\npart of this run was refused: "
              f"{_plural(refused_total, 'request', refused_exact)} with "
              f"{_codes_phrase(codes_seen)}, against "
              f"{_count_text(served_total, served_exact)} answered. The active count "
              f"is a floor over the part of the universe that was served, so a count "
              f"near zero is not on its own evidence that the feed is empty: it is "
              f"also what refusing most of the requests looks like. The lag, where "
              f"there is one, is a reading of the served part and of nothing else.")
    else:
        print(f"\nthe verdict rests on two numbers. If active names stays near zero through "
              f"the morning, the free tier does not serve live premarket and the design in "
              f"DECISIONS.md 2026-08-16 does not stand. If it is in the thousands, it does, "
              f"and then the lag decides what freeze time is achievable.")
    if lags:
        print(f"observed lag: best {min(lags)}m, median {statistics.median(lags)}m, "
              f"worst {max(lags)}m, against a documented {DOCUMENTED_LAG_MINUTES:g}m")
    else:
        print("observed lag: nothing to report, no sweep returned a bar")
    print(f"last sweep: {last['symbols_with_bars']:,} names with bars, newest "
          f"{last.get('newest_bar_et')}, lag {last.get('lag_minutes_newest')} minutes, "
          f"{last.get('gappers_over_3pct', 0)} gapping over 3 percent")
    check = last.get("collector_check") or {}
    if check.get("available"):
        print(f"collector cross check: {check['overlap_with_top']} of the top names were "
              f"also subscribed; volume ratios {[c['ratio'] for c in check['compared']]}")
    return 0


def dry_run(day: str) -> int:
    """Sweep a past session at several clock times, to prove the table works.

    This probe gets exactly one Monday. If the table turns out to be empty or
    the lag arithmetic wrong, there is no second morning to try it on, so the
    plumbing is exercised here against a session that has already happened.

    The lag it reports is meaningless by construction: the wall clock is
    pinned to that morning while the bars are days old and complete, so the
    newest bar sits right at the pinned clock and the lag reads near zero.
    What is being checked is that bars arrive, that the active count climbs
    through the morning, and that every column of the table fills in.
    """
    session = dt.date.fromisoformat(day)
    codes = universe_codes()
    probe = probe_alpaca.Probe()
    print(f"probe: DRY RUN against {day}, a completed session. The lag column is "
          "meaningless here by construction; what this proves is that the table fills.")
    closes = prior_closes(probe, codes, session)
    print(f"probe: {len(closes):,} prior closes, {probe.request_count} requests")

    path = log_path(day)
    if path.exists():
        path.unlink()
    for hour, minute in ((7, 30), (8, 0), (8, 30), (8, 45), (9, 15)):
        as_of = ettime.at_hm(session, (hour, minute))
        record = sample(probe, codes, closes, session, as_of=as_of)
        record["collector_check"] = {"available": False,
                                     "reason": "dry run, the collector was not running"}
        record["dry_run"] = True
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        print(f"probe: {record['taken_at_et'][11:19]} "
              f"{record['symbols_with_bars']:,} names with bars, "
              f"newest {str(record.get('newest_bar_et') or '')[11:19]}, "
              f"{record.get('gappers_over_3pct', 0)} over 3 percent")
    return report(day)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe whether Alpaca serves live premarket.")
    parser.add_argument("--once", action="store_true", help="Take one sample and stop.")
    parser.add_argument("--report", action="store_true", help="Read the log back.")
    parser.add_argument("--date", default=None, help="Which day's log to report on.")
    parser.add_argument("--dry-run", metavar="YYYY-MM-DD", default=None,
                        help="Sweep a PAST session at several clock times, to prove "
                             "the table populates before the live morning. Writes to "
                             "that day's log, spends no EODHD quota, and touches "
                             "nothing the live run depends on.")
    args = parser.parse_args(argv)

    if args.report:
        return report(args.date)

    if args.dry_run:
        return dry_run(args.dry_run)

    today = ettime.today_et()
    day = today.isoformat()
    codes = universe_codes()
    probe = probe_alpaca.Probe()

    print(f"probe: fetching prior closes for {len(codes):,} symbols from Alpaca daily bars")
    closes = prior_closes(probe, codes, today)
    print(f"probe: {len(closes):,} prior closes, {probe.request_count} requests so far")

    def take_one() -> dict[str, Any]:
        record = sample(probe, codes, closes, today)
        record["collector_check"] = _collector_check(record, day)
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            handle.flush()
        # Rewrite the table after every sweep rather than once at the end. The
        # run spans nearly two hours on a morning that cannot be repeated, and
        # a crash at 09:00 must not take the first ninety minutes with it.
        try:
            written = [json.loads(line)
                       for line in log_path().read_text(encoding="utf-8").splitlines()
                       if line.strip()]
            write_table(written, day)
        except (OSError, ValueError) as exc:
            print(f"probe: could not refresh the table ({type(exc).__name__}), "
                  "the jsonl still has everything and --report can rebuild it")
        top = (record["top_gappers"] or [{}])[0]
        print(f"probe: {record['taken_at_et'][11:19]} {record['symbols_with_bars']:,} "
              f"symbols with bars, newest {str(record.get('newest_bar_et') or '')[11:19]}, "
              f"lag {record.get('lag_minutes_newest')}m, "
              f"{record.get('gappers_over_3pct', 0)} over 3 percent, "
              f"top {top.get('symbol')} {top.get('gap_pct')}")
        return record

    if args.once:
        take_one()
        return report()

    start = ettime.at_hm(today, START_HHMM)
    stop = ettime.at_hm(today, STOP_HHMM)
    if ettime.now_et() > stop:
        print(f"probe: it is {ettime.stamp(ettime.now_et())}, past the "
              f"{STOP_HHMM[0]:02d}:{STOP_HHMM[1]:02d} stop. Nothing to sample today.")
        return 0
    while ettime.now_et() < start:
        time.sleep(min(30.0, (start - ettime.now_et()).total_seconds()))

    print(f"probe: sweeping {len(codes):,} symbols every {INTERVAL_S}s until "
          f"{ettime.stamp(stop)}, writing {log_path().name}")
    while ettime.now_et() < stop:
        take_one()
        remaining = (stop - ettime.now_et()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(INTERVAL_S, remaining))

    return report()


if __name__ == "__main__":
    # Deliberately NOT wrapped in job_status.run, for the same reason
    # probe_live_v1 is not: this is a one off probe, not a scheduled step, and
    # CRITERIA.md [job status steps] would then have to carry a step that is
    # meant to stop existing.
    sys.exit(main())
