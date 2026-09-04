"""A run directory becomes the payload the screens draw from.

WHY A COMPACTION AND NOT THE PACKET. runs/2026-09-03/packet.json is 254,252
bytes and the desk inlines every session it can reach, so the packet itself
does not scale: a year of them is 64MB before compression. Most of that
weight is prose the screens never draw, chiefly headlines_all at thirty
titles a name and the provenance sentences that explain a decision the packet
has already made. Dropping those and keeping every figure any mark plots takes
the same session to 63,913 bytes, and gzipped and base64 encoded for inlining
it is 19,808. A year is then under 5MB in one file.

NOTHING IS RECOMPUTED HERE. Every value below is copied out of the packet or
the midday packet as it was written. If a number is wrong on a screen it is
wrong in the packet, and the fix is upstream in scan.py where the measurement
lives. That is what makes this file safe to change.

The minute bars are the one thing read from outside the packet, because the
tape path is drawn from them and the packet carries only the aggregates. They
come from the run's own snapshot where it still exists and from the
collector's file where retention has removed the duplicate, which is the same
bytes either way: see CRITERIA [Retention] the duplicate snapshot note.

    PYTHONPATH=src .venv/Scripts/python.exe -m desk.compact --session 2026-09-03
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import ettime
from core import files
from core import store
from morning import render_report

_CRIT = criteria.load()

def _sym(symbol: str | None) -> str:
    """SNOW.US to SNOW. Bare tickers everywhere a reader sees one."""
    return (symbol or "").split(".")[0]


def _bars_for(session_date: str,
              windows: dict[str, tuple[str, str]]) -> dict[str, list[dict[str, Any]]]:
    """Minute closes and volumes per symbol, from whichever copy survives.

    The run's premarket_snapshot.jsonl is a strict subset of the collector's
    data/premarket/<date>.jsonl, measured over every session that carried
    both, so a candidate's bars are the same bytes in either file.

    THE TWO FILES ARE NOT INTERCHANGEABLE AND THE CLIP DOES NOT CLOSE THE GAP.
    The run copy is a point in time capture taken when scan ran; the collector
    file is the whole day for every subscribed name. Clipping the collector to
    the pm_window_start and pm_window_end the packet recorded gets most of the
    way, and it was measured on 2026-09-03: seven of twelve names then match
    exactly and five carry ONE extra minute, always the 08:44 bar, because
    that minute was still open when the snapshot was written and complete by
    the time the collector flushed. pm_window_end is stamped 08:44 for those
    names and 08:43 for the ones that match, so no inclusive or exclusive rule
    on it reproduces both.

    THAT IS WHY THE PAYLOAD IS FROZEN RATHER THAN RECONSTRUCTED. compact runs
    in the nightly while the run copy still exists and writes desk.json.gz
    beside it, and prune_data refuses to drop a snapshot until that file is
    there. The fallback below is for a session compacted after its snapshot
    went, which the interlock is meant to make impossible; it is kept so that
    such a session renders a tape path that is one minute long rather than no
    screen at all, and the payload records which source it came from.

    A replayed print is skipped. The collector tags one early first print per
    symbol per connection as a replay because it is stamped outside the
    window, and a tape path that opened on it would draw a line from
    yesterday's close.
    """
    run_copy = config.run_dir(session_date) / "premarket_snapshot.jsonl"
    source = files.resolve_maybe_gz(run_copy)
    clip = False
    if source is None:
        collector = config.PREMARKET_DIR / f"{session_date}.jsonl"
        source = files.resolve_maybe_gz(collector)
        clip = True
    if source is None:
        return {}

    bars: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    try:
        text = files.read_text_maybe_gz(source)
    except OSError:
        return {}
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        symbol = row.get("symbol")
        if symbol not in windows or row.get("replay"):
            continue
        stamp = row.get("minute_et") or ""
        minute = stamp[11:16]
        if not minute:
            continue
        if clip:
            start, end = windows[symbol]
            # Compared on the full stamp, not the clock, so a bar from another
            # date in the same file cannot pass on its time of day alone.
            if (start and stamp < start) or (end and stamp > end):
                continue
        bars[symbol].append({"t": minute, "c": row.get("c"), "v": row.get("v")})
    for rows in bars.values():
        rows.sort(key=lambda r: r["t"])
    return dict(bars)


def _frozen_run_bars(session_date: str,
                     symbols: list[str]) -> dict[str, list[dict[str, Any]]] | None:
    """The exact bars an earlier freeze took from the run copy, or None.

    WITHOUT THIS THE INTERLOCK ONLY HOLDS FOR ONE NIGHT. prune_data will not
    drop a session's duplicate snapshot until desk.json.gz exists, so the
    bars are frozen before the run copy goes. But this module recompacts
    EVERY known session on every run, and the morning chain, the midday
    chain and the nightly all run it, so the next build after the prune
    rebuilt those bars from the collector file and wrote the reconstruction
    over the freeze. Measured on 2026-09-04 over that session's twelve
    names: seven gained the 08:44 bar, which is the minute that was still
    open when the snapshot was written. All three run sessions on disk had
    already flipped from run_snapshot to collector_clipped by the time it
    was found, hours after the prune that made it possible.

    So the frozen bars are carried forward and nothing else is: the report
    prose, the midday rows and every figure the packet holds are rebuilt as
    before, and only the tape, which cannot be reproduced, is kept. None
    when there is no freeze, when the freeze was itself a reconstruction,
    or when it does not cover this session's whole candidate list, because
    a half carried tape is a third source and this file already has two.
    """
    previous = load_frozen(session_date)
    if not previous or previous.get("bars_source") != "run_snapshot":
        return None
    by_symbol = {c.get("sym"): (c.get("bars") or [])
                 for c in (previous.get("candidates") or [])}
    out: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        rows = by_symbol.get(_sym(symbol))
        if rows is None:
            return None
        out[symbol] = rows
    return out


def _headlines(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for head in candidate.get("headlines") or []:
        scope = head.get("article_scope") or {}
        sentiment = head.get("sentiment") or {}
        out.append({
            "t": head.get("title"),
            "at": (head.get("published_at") or "")[11:16],
            "pub": head.get("publisher"),
            "pol": sentiment.get("polarity"),
            "about": scope.get("about_this_name"),
        })
    return out


def _midday_rows(midday: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per ticker, what the 12:00 pass found against the published levels."""
    carry = (midday.get("carry_through") or {}).get("rows") or []
    return {
        row["ticker"]: {
            "state": row.get("state"),
            "why": row.get("state_reason"),
            "open": row.get("open"), "high": row.get("high"),
            "low": row.get("low"), "last": row.get("last"),
            "move": row.get("move_pct"), "day_rvol": row.get("day_rvol"),
            "fill": row.get("fill"),
            "best": row.get("best_vs_fill_pct"),
            "now": row.get("now_vs_fill_pct"),
            "worst": row.get("worst_vs_fill_pct"),
            "stop_state": row.get("stop_state"),
        }
        for row in carry if row.get("ticker")
    }


# A resolved git commit, so a packet built by anything else can be told from
# one built by a scheduled run. Moved here from build_archive on 2026-09-04
# when that module was retired; the reasoning below is its reasoning.
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _fixture_reason(packet: dict[str, Any]) -> str | None:
    """Why this packet was not written by a scheduled run, or None.

    Matched on the SHAPE of the commit rather than on the string "stub",
    because the next fixture to reach a run directory will not be spelled the
    same and a guard that names one value only ever catches that one.

    THE TWO SILENCES ARE NOT THE SAME AS A WRONG ANSWER. A packet with no
    build key at all predates 2026-08-14, when the field was added; a build
    dict whose commit is null is a run on a machine that could not resolve
    HEAD, which config.build_identifier writes deliberately with a
    commit_reason beside it. Neither says anything about whether a market was
    involved, so neither is reported. Only a commit that is PRESENT and is not
    a resolved HEAD is a statement no version of this code makes.

    The desk LABELS such a session rather than dropping it, for the reason the
    archive did: a session missing from the calendar reads as a day the market
    was shut, and this payload is the record. One that quietly omits what went
    wrong is the failure the guard exists to prevent.
    """
    build = packet.get("build")
    if not isinstance(build, dict):
        return None  # predates the field; the packet cannot be asked
    commit = build.get("commit")
    if commit is None:
        return None  # a legitimate run on a machine that could not resolve HEAD
    if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
        return f"its packet was built by {commit!r}, which is not a commit"
    return None


def _rendered(run_dir: Path, name: str) -> str | None:
    """A session's written report as an HTML fragment, or None if it has none.

    Reads through the gzip aware pair, so a warm session that prune_data has
    compressed reads exactly like a hot one. A session whose morning failed
    before the report was written is a supported state and returns None; the
    screen says so rather than drawing an empty page.
    """
    if files.resolve_maybe_gz(run_dir / name) is None:
        return None
    try:
        return render_report.to_html(files.read_text_maybe_gz(run_dir / name))
    except (OSError, ValueError) as exc:
        print(f"compact: {run_dir.name} {name} unreadable: {exc}")
        return None


def compact_session(session_date: str) -> dict[str, Any] | None:
    """The payload for one session, or None when that session has no packet.

    A run directory with no packet is a morning that never got past scan, and
    there is nothing for a screen to draw. It is skipped rather than rendered
    as an empty day, because an empty day on the Sessions screen would read as
    a quiet market rather than as a chain that did not finish.
    """
    run_dir = config.run_dir(session_date)
    packet_path = run_dir / "packet.json"
    if files.resolve_maybe_gz(packet_path) is None:
        return None
    packet = files.read_json_maybe_gz(packet_path)

    midday: dict[str, Any] = {}
    midday_path = run_dir / "midday_packet.json"
    if files.resolve_maybe_gz(midday_path) is not None:
        try:
            midday = files.read_json_maybe_gz(midday_path)
        except ValueError:
            midday = {}
    mid_by_ticker = _midday_rows(midday)

    raw_candidates = packet.get("candidates") or []
    windows = {
        c["symbol"]: (c.get("pm_window_start") or "", c.get("pm_window_end") or "")
        for c in raw_candidates if c.get("symbol")
    }
    run_copy_present = files.resolve_maybe_gz(
        run_dir / "premarket_snapshot.jsonl") is not None
    # A freeze that already holds the exact rows is preferred to rebuilding
    # them by clipping, and reading it is cheaper than reading the whole
    # day's tape as well. See _frozen_run_bars.
    kept = None if run_copy_present else _frozen_run_bars(
        session_date, list(windows))
    if kept is None:
        bars = _bars_for(session_date, windows)
        bars_source = "run_snapshot" if run_copy_present else "collector_clipped"
    else:
        bars = kept
        bars_source = "run_snapshot"

    earnings = {
        _sym(row.get("symbol")): row
        for row in ((packet.get("earnings") or {}).get("candidates") or [])
    }

    candidates = []
    for c in raw_candidates:
        quote = c.get("quote") or {}
        symbol = c.get("symbol")
        candidates.append({
            "sym": _sym(symbol),
            "name": quote.get("name") or _sym(symbol),
            "sector": quote.get("sector"),
            "price": c.get("price"), "prior_close": c.get("prior_close"),
            "prior_high": c.get("prior_high"),
            "gap": c.get("gap_pct"), "dir": c.get("gap_direction"),
            "pm_high": c.get("pm_high"), "pm_low": c.get("pm_low"),
            "pm_vwap": c.get("pm_vwap"),
            "entry": c.get("entry_ref"), "stop": c.get("stop_ref"),
            "rvol": c.get("pm_rvol"), "pm_vol": c.get("pm_volume"),
            "sigma": c.get("move_sigma"),
            "score": c.get("score"), "conv": c.get("conviction"),
            "components": [
                {"k": x.get("component"), "p": x.get("points"), "why": x.get("why")}
                for x in (c.get("score_components") or [])
            ],
            "catalyst": c.get("catalyst_class"), "catalyst_why": c.get("catalyst_why"),
            "day": bool(c.get("day_eligible")), "swing": bool(c.get("swing_eligible")),
            "day_failed": c.get("day_failed_conditions") or [],
            "swing_failed": c.get("swing_failed_conditions") or [],
            "trap": bool(c.get("trap")), "trap_why": c.get("trap_why"),
            "pol": c.get("headline_polarity"), "news": c.get("news_in_window"),
            "headlines": _headlines(c),
            "mcap": quote.get("marketCap"), "adv": c.get("avg_dollar_volume_20d"),
            "float_rot": c.get("pm_float_rotation"), "band": c.get("pm_band_state"),
            "rank": c.get("pool_rank"), "tier_why": c.get("pool_tier_reason"),
            "measure": c.get("volume_measure_used"),
            "covered": bool(c.get("collector_covered")),
            "bars": bars.get(symbol, []),
            "earn": earnings.get(_sym(symbol)),
            "mid": mid_by_ticker.get(symbol),
        })
    candidates.sort(key=lambda c: -(c["gap"] if c["gap"] is not None else -999))

    movers = [
        {
            "sym": _sym(r.get("symbol")), "name": r.get("name"),
            "leg": r.get("leg"), "move": r.get("move_pct"),
            "sigma": r.get("move_sigma"), "mcap": r.get("market_cap"),
            "watch": r.get("also_on_watchlist"),
        }
        for r in ((packet.get("notable_movers") or {}).get("rows") or [])
    ]

    mid_movers = (midday.get("movers") or {})
    payload = {
        "session": packet.get("session_date") or session_date,
        # THE WRITTEN REPORT, rendered here and inlined with the session.
        # site/PremarketDesk.html was build_archive's page until 2026-09-04
        # and the one thing it carried that this payload did not was the
        # prose. The desk took its name, so it takes its job: without these
        # two keys the rename would have quietly dropped the only way to read
        # an old morning's report across sessions, and the published artifact
        # cannot reach runs/<date>/report.html the way a local page can.
        # Rendered through render_report.to_html and never markdown.markdown,
        # for the reason that function's docstring gives.
        # None for a real morning. A sentence when the packet was not written
        # by a scheduled run, so the screens can say so instead of drawing a
        # fixture as a session that happened.
        "fixture": _fixture_reason(packet),
        "report": _rendered(run_dir, "report.md"),
        "report_midday": _rendered(run_dir, "report_midday.md"),
        "run_at": packet.get("run_time_et"),
        "generated": packet.get("generated_at"),
        "api_calls": packet.get("api_calls"),
        "vintage": packet.get("vintage"),
        # Which tape the bars came from, so a screen never has to guess and a
        # reader of an old payload can tell an exact capture from a
        # reconstruction. See _bars_for.
        "bars_source": bars_source,
        "tape": [
            {"label": t.get("label"), "last": t.get("last"), "chg": t.get("change"),
             "pct": t.get("change_pct"), "stale": bool(t.get("prior_session_only")),
             "as_of": t.get("as_of"), "src": t.get("source")}
            for t in (packet.get("market_snapshot") or [])
        ],
        "candidates": candidates,
        "tally": packet.get("screen_tally") or {},
        "shape": {k: (packet.get("list_shape") or {}).get(k)
                  for k in ("sectors", "catalyst_classes", "gap_direction")},
        "criteria": packet.get("criteria_summary") or {},
        "record": packet.get("record_so_far") or {},
        "movers": movers,
        "econ": (packet.get("economic") or {}).get("events") or [],
        "prov": packet.get("candidate_provenance") or {},
        "health": {
            "job": packet.get("job_health") or {},
            "quota": packet.get("quota_preflight") or {},
            "coverage": packet.get("collector_coverage") or {},
            "window": packet.get("collector_window_observed") or {},
            "capture": packet.get("capture_correction") or {},
            "evidence": packet.get("evidence_roll") or {},
        },
        "midday": None if not midday else {
            "generated": midday.get("generated_at"),
            "run_at": midday.get("run_time_et"),
            "universe": midday.get("universe_size"),
            "api_calls": midday.get("api_calls"),
            "tally": mid_movers.get("tally"),
            "floors": mid_movers.get("floors"),
            "session_elapsed": mid_movers.get("session_elapsed"),
            "rank_by": mid_movers.get("rank_by"),
            "movers": [
                {"sym": _sym(r.get("ticker") or r.get("symbol")),
                 "name": r.get("name"),
                 "move": r.get("move_pct"), "last": r.get("last"),
                 "prev": r.get("prev_close"), "rvol": r.get("day_rvol"),
                 "vol": r.get("volume"), "watch": r.get("also_on_watchlist"),
                 "news": r.get("news") or r.get("headline")}
                for r in (mid_movers.get("rows") or [])
            ],
        },
    }
    return payload


def frozen_path(session_date: str) -> Path:
    """Where a session's compacted payload lives once it has been frozen."""
    return config.run_dir(session_date) / "desk.json.gz"


def freeze(session_date: str, payload: dict[str, Any]) -> Path:
    """Write the payload beside the run it came from, gzipped.

    This is the artifact the desk inlines and the file prune_data reads before
    it will drop a duplicate snapshot. Written whole through the atomic writer
    and then compressed in place, so a reader sees the previous payload or
    this one and never a half written file.
    """
    destination = config.run_dir(session_date) / "desk.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    files.write_text_atomically(
        destination, json.dumps(payload, separators=(",", ":")), attempts=3, retry_s=0.4)
    packed = frozen_path(session_date)
    if packed.is_file():
        packed.unlink()
    files.gzip_in_place(destination, attempts=3, retry_s=0.4)
    return packed


def load_frozen(session_date: str) -> dict[str, Any] | None:
    """The frozen payload for a session, or None when it has never been built."""
    path = config.run_dir(session_date) / "desk.json"
    if files.resolve_maybe_gz(path) is None:
        return None
    try:
        return files.read_json_maybe_gz(path)
    except (OSError, ValueError):
        return None


def summary_row(payload: dict[str, Any]) -> dict[str, Any]:
    """The sessions table row for a compacted session."""
    cands = payload["candidates"]
    convictions = collections.Counter(c["conv"] for c in cands)
    directions = collections.Counter(c["dir"] for c in cands)
    top = cands[0] if cands else {}
    ranking = (payload["prov"].get("ranking") or {})
    mid = payload.get("midday")
    states = collections.Counter(
        (c["mid"] or {}).get("state") for c in cands if c.get("mid"))
    moves = [c["mid"]["move"] for c in cands
             if c.get("mid") and c["mid"].get("move") is not None]

    packet_path = config.run_dir(payload["session"]) / "packet.json"
    found = files.resolve_maybe_gz(packet_path)
    report = files.resolve_maybe_gz(config.run_dir(payload["session"]) / "report.md")

    return {
        "date": payload["session"],
        "generated_at": payload.get("generated"),
        "run_at": payload.get("run_at"),
        "candidates": len(cands),
        "day_eligible": (payload["tally"].get("day") or {}).get("eligible"),
        "swing_eligible": (payload["tally"].get("swing") or {}).get("eligible"),
        "green": convictions.get("green", 0),
        "yellow": convictions.get("yellow", 0),
        "red": convictions.get("red", 0),
        "gapped_up": directions.get("up", 0),
        "gapped_down": directions.get("down", 0),
        "top_symbol": top.get("sym"),
        "top_gap_pct": top.get("gap"),
        "pool_size": payload["prov"].get("pool_size"),
        "subscribed": payload["prov"].get("subscribed"),
        "ranked": ranking.get("subscribed_considered"),
        "cleared_floors": ranking.get("cleared_floors"),
        "kept": ranking.get("kept"),
        "capped_out": ranking.get("capped_out"),
        "midday_generated_at": (mid or {}).get("generated"),
        "triggered": states.get("triggered") if mid else None,
        "gapped_through": states.get("gapped_through") if mid else None,
        "never_triggered": states.get("never_triggered") if mid else None,
        "midday_median_move": statistics.median(moves) if moves else None,
        "packet_bytes": found.stat().st_size if found else None,
        "packet_compressed": 1 if (found and found.suffix == ".gz") else 0,
        "has_report": 1 if report else 0,
        "computed_at": ettime.stamp(),
    }


def known_sessions() -> list[str]:
    """Every session directory that carries a packet, newest first.

    Fenced by CRITERIA [Retention] history_from. The sessions before that
    floor were deleted on 2026-09-04, so today this filter removes nothing;
    it exists because a restore from the backup root, or a rerun that writes
    an old run directory, would otherwise put a session back on the screens
    that the owner cut for not being comparable. The floor is a decision and
    it should take a CRITERIA edit to move, not an accident.
    """
    if not config.RUNS_DIR.is_dir():
        return []
    floor = _CRIT.text("retention", "history_from")
    out = []
    for entry in config.RUNS_DIR.iterdir():
        if not entry.is_dir() or entry.name < floor:
            continue
        if files.resolve_maybe_gz(entry / "packet.json") is not None:
            out.append(entry.name)
    return sorted(out, reverse=True)


def write_summary(rows: list[dict[str, Any]]) -> int:
    """Upsert the sessions table. Full rewrite of the rows given, never append."""
    if not rows:
        return 0
    columns = list(rows[0])
    placeholders = ", ".join("?" for _ in columns)
    assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c != "date")
    sql = (f"INSERT INTO sessions ({', '.join(columns)}) VALUES ({placeholders}) "
           f"ON CONFLICT(date) DO UPDATE SET {assignments}")
    with store.session() as connection:
        store.init(connection)
        connection.executemany(sql, [tuple(r[c] for c in columns) for r in rows])
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compact a session for the desk.")
    parser.add_argument("--session", help="One session date. Default is every one.")
    parser.add_argument("--out", type=Path,
                        help="Also write the payload here, uncompressed.")
    parser.add_argument("--no-freeze", action="store_true",
                        help="Do not write runs/<date>/desk.json.gz. The "
                             "interlock in prune_data reads that file, so a "
                             "session compacted with this flag keeps its "
                             "snapshot.")
    args = parser.parse_args(argv)

    dates = [args.session] if args.session else known_sessions()
    rows, built = [], 0
    for date in dates:
        payload = compact_session(date)
        if payload is None:
            print(f"compact: {date} has no packet, skipped")
            continue
        rows.append(summary_row(payload))
        built += 1
        if not args.no_freeze:
            frozen = freeze(date, payload)
            print(f"compact: {date} frozen to {frozen.name}, "
                  f"{frozen.stat().st_size:,} bytes")
        if args.out:
            files.write_json_atomically(args.out, payload, indent=None)
            print(f"compact: {date} written to {args.out}")
    written = write_summary(rows)
    print(f"compact: {built} session(s) compacted, {written} summary row(s) stored")
    return 0


OK_CODES = (0,)


if __name__ == "__main__":
    sys.exit(main())
