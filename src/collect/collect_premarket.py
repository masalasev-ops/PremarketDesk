"""Premarket collector. Streams from 07:20 to 09:25 ET and builds the price path.

This file is the only source of today's premarket price path. Nothing else in
this project is allowed to infer a premarket high, low or VWAP from a quote
snapshot, because a snapshot tells you where a name is, not where it has been.
If the collector was not listening, the honest answer downstream is null, and
scan.py says so rather than guessing.

How it works. One websocket connection to the EODHD US trades feed. Every
trade is folded into a local one minute bar. A minute is written to
data/premarket/YYYY-MM-DD.jsonl only once it is complete, so no row is ever
revised. Restarting mid morning is safe: the already written minutes are read
back at startup and never rewritten, which is also why a second run inside the
same minute adds no duplicate rows.

The websocket path makes zero REST requests from this process, which is
checked at the end of every run. That is a client side fact and says nothing
about what the vendor meters for the socket itself; the vendor side answer
comes from measure_socket_cost.py, which reads the account counter before and
after a run and records the delta as a measured fact.

Symbol budget. The feed allows 50 concurrent subscriptions. The eight context
symbols are never dropped, because a premarket price path with no idea what
the index futures did is a price path you cannot read. The watchlist takes the
remaining slots in order of absolute gap, and anything that does not fit is
logged by name and gap so the omission is on the record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import ssl
import statistics
import time
from pathlib import Path
from typing import Any

import websocket

from core import config
from core import criteria
from selection import discover
from core import ettime
from ops import job_status

_CRIT = criteria.load()

BAR_SECONDS = _CRIT.integer("collector", "bar_seconds")
# A run directory is named for its session. Matched rather than parsed so an
# archive folder or anything a human drops under runs/ is never mistaken for
# one. The same test backfill_premarket keeps for bar files, for the same
# reason.
_RUN_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SUBSCRIPTIONS = _CRIT.integer("collector", "max_subscriptions")
BACKOFF_START_S = _CRIT.number("collector", "reconnect_backoff_start_s")
BACKOFF_MAX_S = _CRIT.number("collector", "reconnect_backoff_max_s")
POLL_INTERVAL_S = _CRIT.number("collector", "poll_interval_s")
AUTH_WAIT_S = _CRIT.number("collector", "auth_wait_s")
LATE_TRADE_GRACE_S = _CRIT.number("collector", "late_trade_grace_s")
VERIFY_WARMUP_MINUTES = _CRIT.number("collector", "verify_warmup_minutes")
VERIFY_WINDOW_MINUTES = _CRIT.number("collector", "verify_window_minutes")
SUBSCRIPTION_RETRY_WAIT_S = _CRIT.number("collector", "subscription_retry_wait_s")
MAX_SUBSCRIPTION_RETRIES = _CRIT.integer("collector", "max_subscription_retries")
POOL_RELOAD_CHECK_S = _CRIT.number("collector", "pool_reload_check_s")
MAX_POOL_RELOADS = _CRIT.integer("collector", "max_pool_reloads")
VOLUME_CHECK_AGREEMENT_PCT = _CRIT.number("collector", "volume_check_agreement_pct")


def bar_path(day: str | None = None) -> Path:
    return config.PREMARKET_DIR / f"{day or ettime.today_str()}.jsonl"


def stats_path(day: str | None = None) -> Path:
    return config.PREMARKET_DIR / f"{day or ettime.today_str()}-stats.jsonl"


def subscriptions_path(day: str | None = None) -> Path:
    return config.PREMARKET_DIR / f"{day or ettime.today_str()}-subscriptions.json"


def write_subscriptions(symbols: list[str], dropped: list[dict[str, Any]]) -> Path:
    """What the collector asked the socket for, written before any trade arrives.

    This exists so the 08:45 scan can tell a subscribed symbol that produced
    nothing from a symbol that was never subscribed at all. The run stats
    sidecar cannot answer that: it is appended when the collector stops at
    09:25, which is forty minutes after the packet is built.

    Rewritten by each run of the day rather than appended, because the current
    subscription list is the answer, not the history of them. A restart that
    subscribes to a different set replaces this, and the count of runs is in
    the stats sidecar for anyone who needs the history.

    window_open_at SURVIVES EVERY REWRITE, and that is the one field here that
    is about the session rather than about the current subscription. It is the
    first moment anything subscribed today, which is when the socket's window
    opened. The night's truth pass needs it: capture_observed divides socket
    volume by the tape over THE MINUTES THE SOCKET WAS LISTENING TO, and
    before 2026-09-02 that was read from [Collector] start_time. Reading a
    knob for a fact about a past session is exactly the mistake this project
    keeps paying for: the knob moved from 07:20 to 04:00 on 2026-09-02, and
    every session before it would have been re-measured against a window its
    socket never had, turning collector_window_share into 1.0 for mornings
    that really only heard the last two hours. The two phase handover rewrites
    this file mid-run, so "the last subscribed_at" is not the answer either.
    """
    path = subscriptions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = ettime.stamp(ettime.now_et())
    window_open_at = now
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        window_open_at = str(existing.get("window_open_at") or
                             existing.get("subscribed_at") or now)
    except (OSError, ValueError, TypeError):
        pass
    path.write_text(json.dumps({
        "subscribed_at": now,
        "window_open_at": window_open_at,
        "requested_count": len(symbols),
        "socket_cap": MAX_SUBSCRIPTIONS,
        "symbols": sorted(symbols),
        "dropped_to_fit_cap": [row.get("symbol") for row in dropped],
    }, indent=2, sort_keys=True), encoding="utf-8")
    return path


def window_open_hhmm(day: str | None = None) -> str | None:
    """The ET clock time the socket's window opened on a day, or None.

    Read from the subscription sidecar rather than from [Collector]
    start_time, so a session is measured against the window it actually had
    rather than against the one configured today. None when no sidecar exists,
    which the caller reads as "fall back to the knob" because for a session
    with no record the knob is the best available answer.
    """
    record = read_subscriptions(day)
    if not record:
        return None
    stamp = str(record.get("window_open_at") or record.get("subscribed_at") or "")
    try:
        return ettime.hhmm(dt.datetime.fromisoformat(stamp))
    except (TypeError, ValueError):
        return None


def read_subscriptions(day: str | None = None) -> dict[str, Any] | None:
    """The collector's subscription list for a day, or None if it never wrote one."""
    path = subscriptions_path(day)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def read_run_stats(day: str | None = None) -> dict[str, Any] | None:
    """Aggregate connection stats across every collector run of the day.

    One JSON line is appended per run, so a restarted morning sums honestly
    instead of the last run overwriting the first.

    This is the only reader of that sidecar in the project, and it is the
    second of three hops, not the last one. scan.py does not consume what this
    returns wholesale: it names the keys it wants one at a time into
    collector_snapshot, so a field has to be BOTH aggregated here AND named
    there before it can reach the packet or the report, however faithfully the
    collector wrote it down. status_frames was stopped at the first of those
    two doors and is now through both, which is what makes the argument at its
    declaration in run_websocket actually land. Anything added to the loop
    below needs the matching line in scan.py or it stops here.

    status_frames_seen is deliberately not aggregated. It is the frames
    themselves, capped at ten per run, and there is nothing to add up: two runs
    that each saw a different frame have two facts, not one number. A caller
    that needs them reads the last line of the sidecar the way
    measure_socket_cost.py already does.
    """
    path = stats_path(day)
    if not path.exists():
        return None
    # status_frames starts at None rather than 0, and the two are different
    # answers. A --poll run has no socket and records null, and a record
    # appended before the field existed carries nothing at all; folding either
    # into a running integer would report "no odd frames this morning" for a
    # morning nobody counted, which is the one thing this aggregate exists to
    # stop being invisible. It stays None until some run carries a number.
    # Every counter starts at None for the reason spelled out above for
    # status_frames, which turned out to apply to all of them. A run that
    # recorded no count at all, because it was refused before it wrote one or
    # because it predates the field, must not fold into a zero: summing it that
    # way reports "this morning saw no messages" for a morning nobody counted,
    # and that is exactly what the packet said on 2026-08-19. None until some
    # run carries a number, then the sum of the runs that carried one.
    totals: dict[str, Any] = {"runs": 0, "connections": None, "reconnects": None,
                              "resubscriptions": None, "messages": None,
                              "status_frames": None}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        totals["runs"] += 1
        for key in ("connections", "reconnects", "resubscriptions", "messages"):
            if row.get(key) is None:
                continue
            try:
                value = int(row[key])
            except (TypeError, ValueError):
                continue
            totals[key] = value if totals[key] is None else totals[key] + value
        frames = row.get("status_frames")
        if isinstance(frames, (int, float)):
            totals["status_frames"] = (totals["status_frames"] or 0) + int(frames)
    return totals if totals["runs"] else None


def _bare(symbol: str) -> str:
    """The websocket wants AAPL, the rest of this project speaks AAPL.US."""
    symbol = symbol.strip().upper()
    return symbol[:-3] if symbol.endswith(".US") else symbol


def _full(symbol: str) -> str:
    symbol = symbol.strip().upper()
    return symbol if "." in symbol else f"{symbol}.US"


def minute_floor(epoch_seconds: float) -> int:
    """Bar start. Minute boundaries are identical in UTC and ET, offsets are whole hours."""
    return int(epoch_seconds // BAR_SECONDS) * BAR_SECONDS


# ------------------------------------------------------------ symbol budget

def select_symbols(watchlist: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """Context symbols plus the names discover marked subscribed.

    The ordering decision belongs to discover, which ranks the pool by tier and
    then by 20 day average dollar volume and marks everything past the cap
    not_subscribed. This used to re-sort by gap_pct, a field that no longer
    exists on a watchlist row and which came from the stale bulk feed when it
    did. Re-deriving the cut here would mean two places deciding the same
    thing, and the audit trail in watchlist.json would stop matching what was
    actually subscribed.

    The socket cap is still enforced as a backstop, because the socket is a
    hard limit and CRITERIA's two numbers could drift apart.
    """
    context = [_full(s) for s in _CRIT.text_list("collector", "context_symbols")]

    rows = [
        r for r in watchlist.get("symbols", [])
        if r.get("symbol") and r.get("subscribed", True)
        and _full(r["symbol"]) not in context
    ]

    budget = max(MAX_SUBSCRIPTIONS - len(context), 0)
    kept, dropped = rows[:budget], rows[budget:]
    if dropped:
        print(f"collector: {len(dropped)} name(s) discover marked subscribed do not "
              f"fit the {MAX_SUBSCRIPTIONS} socket cap alongside {len(context)} "
              "context tickers. Check max_subscribed_candidates in CRITERIA.md "
              "[discovery] against max_subscriptions in [collector].")

    subscribed = context + [_full(r["symbol"]) for r in kept]
    return subscribed, dropped


# --------------------------------------------------------------- bar making

class BarBuilder:
    """Folds trades into one minute bars and appends completed ones exactly once."""

    def __init__(self, path: Path, source: str,
                 window: tuple[float, float] | None = None) -> None:
        self.path = path
        self.source = source
        # The epoch seconds this run is collecting between, or None to accept
        # any timestamp. See add_trade for what it refuses and why.
        self.window = window
        self.open_bars: dict[tuple[str, int], dict[str, Any]] = {}
        self.written: set[tuple[str, int]] = set()
        self.rows_written = 0
        self.duplicates_skipped = 0
        self.trades_seen = 0
        self.late_trades = 0
        self.late_volume = 0.0
        self.total_volume = 0.0
        self.out_of_window_trades = 0
        self.out_of_window_volume = 0.0
        self.out_of_window_examples: list[dict[str, Any]] = []
        # Replayed minutes, kept apart from open_bars so they can never be
        # folded into a total, and written to the same file tagged so they can
        # never be lost either. Counting them in a log line was enough to stop
        # the vintage defect and not enough to measure it afterwards: on
        # 2026-08-19 the only way to ask how much replay 2026-08-17 carried was
        # to reconstruct it from a subscription time recorded in a different
        # file, and for 2026-08-14 that file does not exist.
        self.replay_bars: dict[tuple[str, int], dict[str, Any]] = {}
        self.replay_rows_written = 0
        # A replayed minute already on disk, offered again. The vendor replays
        # a last trade per symbol on EVERY subscription, and this run
        # resubscribes on every reconnect, so without this the same replayed
        # print is appended once per connection and read back as that many
        # times the volume. replay_volume in the packet is the number a human
        # reads to judge how much replay a session carried, which is the whole
        # reason the tag was introduced, so inflating it by the reconnect count
        # defeats the measurement it exists to make.
        self.duplicate_replay_skipped = 0
        # Minutes that could not be appended. Counted rather than lost: see
        # flush() for why the UNWRITTEN ones go back into open_bars instead of
        # being marked written, and why the ones that landed must not.
        self.write_failures = 0
        self.last_write_error: str | None = None
        # Times this run found the file ending mid line and closed it before
        # appending. Non zero means a previous run died between a write and its
        # flush; see _terminate_torn_tail.
        self.torn_tails_terminated = 0
        # Trades whose own fields this parser could not place on a clock. See
        # _handle_message: non zero means the feed sent something this code
        # does not understand, which is a different fact from a quiet tape and
        # from a dropped connection.
        self.unparseable_trades = 0
        self._load_existing()

    def _terminate_torn_tail(self, handle: Any) -> None:
        """Close an unterminated final line before appending after it.

        read_bars_file trusts only lines that end in a newline, and discards an
        unterminated final one as the writer caught mid append. That is right
        for a READER. For this writer it was a trap: the file is opened in
        append mode, so the first bar of a restarted run was written straight
        onto the fragment, producing one unparseable line out of two real
        records and losing the new minute as well as the torn one.

        A fragment can only be the tail, so one newline repairs it. The
        fragment itself stays where it is and is counted as a bad line by
        every reader, which is the honest outcome: something was lost, and it
        is visible rather than glued to something that was not.
        """
        if handle.tell() == 0:
            return
        try:
            with self.path.open("rb") as probe:
                probe.seek(-1, 2)
                if probe.read(1) == b"\n":
                    return
        except OSError:
            return  # cannot tell; the append is no worse than it was
        handle.write("\n")
        handle.flush()
        self.torn_tails_terminated += 1
        print(f"collector: {self.path.name} ended mid line, so a newline was "
              "written before this batch. The fragment stays as an unreadable "
              "line rather than being glued to the first bar after it.")

    def _load_existing(self) -> None:
        """Read back what a previous run already wrote. This is the restart safety."""
        if not self.path.exists():
            return
        bad = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                self.written.add((str(row["symbol"]), int(row["minute_epoch"])))
            except (ValueError, KeyError, TypeError):
                bad += 1
        print(
            f"collector: resuming, {len(self.written)} minutes already on disk"
            + (f", {bad} unreadable lines ignored" if bad else "")
        )

    def add_trade(self, symbol: str, price: float, volume: float, epoch_s: float,
                  dark_pool: bool, market_status: str | None) -> None:
        self.trades_seen += 1

        # A trade stamped outside the window this run is collecting is not
        # this morning's tape, and folding it in is a vintage defect: the bar
        # file says a minute was covered when nothing was listening in it.
        #
        # It is not hypothetical. The server replays a last trade per symbol
        # when the subscription lands, and that trade carries its ORIGINAL
        # timestamp. On 2026-08-18 that put three bars dated 2026-08-17, one of
        # them 15:59 the previous afternoon, into the 2026-08-18 premarket file,
        # and eleven more on 2026-08-17 stamped minutes before the collector had
        # connected. Every one carried exactly one trade, which is the
        # signature: one replayed message per symbol.
        #
        # The damage is not the volume, which was trivial. It is that
        # pm_window_starts_late is derived from the first bar present, so a
        # replayed 07:00 print makes a window the collector reached at 07:20
        # look like it was covered from 07:00, and the flag that exists to warn
        # a reader about exactly that says nothing.
        if self.window is not None and not (self.window[0] <= epoch_s <= self.window[1]):
            self.out_of_window_trades += 1
            self.out_of_window_volume += volume
            if len(self.out_of_window_examples) < 20:
                self.out_of_window_examples.append({
                    "symbol": symbol,
                    "at": ettime.stamp(ettime.from_epoch_s(int(epoch_s))),
                    "v": volume,
                })
            # Recorded rather than discarded. It is tagged replay, kept out of
            # every total by read_bars_file, and in the file so a later reader
            # can measure what arrived without needing the trade itself. The
            # tag is the whole of the protection: a consumer that wants these
            # has to ask for them by name.
            self._add_replay(symbol, price, volume, epoch_s, market_status)
            return

        self.total_volume += volume
        key = (symbol, minute_floor(epoch_s))

        # This minute is already on disk. Rows are append only and never
        # revised, which is what makes a restart safe, so this trade cannot be
        # merged in. Count it rather than dropping it in silence.
        if key in self.written:
            self.late_trades += 1
            self.late_volume += volume
            return

        bar = self.open_bars.get(key)
        if bar is None:
            bar = {
                "symbol": symbol,
                "minute_epoch": key[1],
                "o": price,
                "h": price,
                "l": price,
                "c": price,
                "v": 0.0,
                "pv": 0.0,
                "trades": 0,
                "dark_pool_volume": 0.0,
                "market_status": market_status,
                "src": self.source,
            }
            self.open_bars[key] = bar
        bar["h"] = max(bar["h"], price)
        bar["l"] = min(bar["l"], price)
        bar["c"] = price
        bar["v"] += volume
        bar["pv"] += price * volume
        bar["trades"] += 1
        if dark_pool:
            bar["dark_pool_volume"] += volume
        if market_status:
            bar["market_status"] = market_status

    def _add_replay(self, symbol: str, price: float, volume: float,
                    epoch_s: float, market_status: str | None) -> None:
        """One tagged row per replayed symbol minute, aggregated like a bar."""
        key = (symbol, minute_floor(epoch_s))
        bar = self.replay_bars.get(key)
        if bar is None:
            bar = {
                "symbol": symbol,
                "minute_epoch": key[1],
                "o": price, "h": price, "l": price, "c": price,
                "v": 0.0, "pv": 0.0, "trades": 0,
                "dark_pool_volume": 0.0,
                "market_status": market_status,
                "src": self.source,
                # The tag every reader keys on. Present and true only on these
                # rows, absent on every ordinary bar, so a file written before
                # this existed reads as carrying no replay rows rather than as
                # carrying unknown ones. That is a claim about the FILE, not
                # about the session: sessions before the window guard folded
                # their replay into ordinary bars and it is not recoverable
                # from the file alone.
                "replay": True,
                "replay_reason": (
                    "stamped outside this run's collection window, which the "
                    "subscription's replayed last trade per symbol does"
                ),
            }
            self.replay_bars[key] = bar
        bar["h"] = max(bar["h"], price)
        bar["l"] = min(bar["l"], price)
        bar["c"] = price
        bar["v"] += volume
        bar["pv"] += price * volume
        bar["trades"] += 1
        if market_status:
            bar["market_status"] = market_status

    def add_synthetic(self, symbol: str, price: float, volume: float, epoch_s: float) -> None:
        """Used only by the polling fallback, where there are no individual trades."""
        self.add_trade(symbol, price, volume, epoch_s, False, "poll")

    def flush(self, now_epoch: float, force: bool = False) -> int:
        """Append every bar whose minute has finished and settled.

        The grace period matters. Trades do not arrive in timestamp order, so
        closing a minute the instant the clock passes it throws away every late
        print. Waiting late_trade_grace_s catches nearly all of them at the cost
        of putting each row on disk that much later.
        """
        # Replay rows settle immediately. Their minute finished before this
        # run began, so there is nothing to wait for, and holding them to the
        # grace period would risk losing them to a run that dies early.
        replay_ready = sorted(self.replay_bars, key=lambda k: (k[1], k[0]))
        ready = [
            key for key in self.open_bars
            if force or key[1] + BAR_SECONDS + LATE_TRADE_GRACE_S <= now_epoch
        ]
        if not ready and not replay_ready:
            return 0
        ready.sort(key=lambda k: (k[1], k[0]))

        # Nothing is marked written and no counter moves until the bytes are
        # on disk. The order used to be the other way round: keys were popped
        # from open_bars and added to `written` while the batch was being
        # built, and only then was the file opened. An OSError there lost those
        # minutes twice over, because `written` then made add_trade refuse
        # every later trade for them as a late print, so they could not even be
        # rebuilt from the tape still arriving. rows_written did not move
        # either, so the counter and the file disagreed in the opposite
        # direction from the loss.
        pending: list[tuple[tuple[str, int], dict[str, Any], bool]] = []
        lines: list[str] = []

        def finish(bar: dict[str, Any]) -> str:
            bar["vwap"] = round(bar["pv"] / bar["v"], 6) if bar["v"] else None
            bar["minute_et"] = ettime.stamp(ettime.from_epoch_s(bar["minute_epoch"]))
            return json.dumps(bar, separators=(",", ":"))

        for key in replay_ready:
            bar = self.replay_bars.pop(key)
            # Replay rows are deduplicated against `written` exactly like real
            # bars now. They were not, so a resubscription rewrote them.
            if key in self.written:
                self.duplicate_replay_skipped += 1
                continue
            lines.append(finish(bar))
            pending.append((key, bar, True))
        for key in ready:
            bar = self.open_bars.pop(key)
            if key in self.written:
                self.duplicates_skipped += 1
                continue
            lines.append(finish(bar))
            pending.append((key, bar, False))

        if not lines:
            return 0

        # How many of this batch's lines are known to be on disk. Counted
        # rather than assumed, because the batch is written one line at a time
        # and a fault can land in the middle of it.
        landed = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # One write and one flush per bar, so the file never holds a
            # buffered partial line while scan.py reads it at 08:45. The
            # handle is opened per settle batch and closed again, which also
            # flushes through to the OS on every batch.
            with self.path.open("a", encoding="utf-8") as handle:
                self._terminate_torn_tail(handle)
                for line in lines:
                    handle.write(line + "\n")
                    handle.flush()
                    landed += 1
        except OSError as exc:
            # Put back ONLY WHAT DID NOT LAND, and DO NOT raise. Raising would
            # reach run_websocket's `except (..., OSError)`, which would report
            # a disk fault as a lost connection, count a reconnect and
            # resubscribe into a 50 slot pool that is known to refuse. Instead
            # the unwritten minutes stay open, the next flush retries them, and
            # a fault that persists shows up as a bar file that stops growing
            # with the reason counted beside it rather than as a phantom socket
            # drop.
            #
            # THE SPLIT IS THE FIX. This used to restore the whole batch and
            # say "nothing has been marked written", which was true of the
            # bookkeeping and false of the disk: each line is flushed
            # individually, so a fault on line five of ten leaves four on disk
            # and re-queues them. The next settle wrote them a second time,
            # read_bars_file does not deduplicate on (symbol, minute), and the
            # duplicate minute is counted twice in pm_volume, which is the
            # numerator of premarket RVOL and of float rotation.
            for key, bar, is_replay in pending[landed:]:
                (self.replay_bars if is_replay else self.open_bars).setdefault(key, bar)
            self.write_failures += 1
            self.last_write_error = f"{type(exc).__name__}: {exc}"
            print(f"collector: FAILED partway through appending {len(lines)} "
                  f"minute(s) to {self.path.name}: {self.last_write_error}. "
                  f"{landed} reached disk and are marked written; "
                  f"{len(lines) - landed} are held for the next settle.")
            # The landed ones are on disk and must be marked, or they are
            # written again below. Fall through to the same bookkeeping the
            # success path uses, over the prefix that actually landed.
            pending = pending[:landed]

        real = 0
        for key, _bar, is_replay in pending:
            self.written.add(key)
            if is_replay:
                self.replay_rows_written += 1
            else:
                real += 1
        # rows_written counts MINUTES OF THIS MORNING'S TAPE and nothing
        # else. Folding the replay rows into it would make the collector's
        # own exit line report a wider window than it covered, which is the
        # defect the tag exists to prevent, one layer up.
        self.rows_written += real
        return len(lines)


# --------------------------------------------------------------- reading back

def read_bars_file(path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Parse a bar file, tolerating a writer mid-append.

    Only lines terminated by a newline are trusted. A trailing partial line
    means the collector was flushed mid-write at the moment of the read, so
    that fragment is counted and discarded rather than parsed or raised on.
    Returns (bars_by_symbol, stats).
    """
    out: dict[str, list[dict[str, Any]]] = {}
    stats: dict[str, Any] = {
        "bars_total": 0,
        "last_bar_epoch": None,
        "last_bar_et": None,
        "partial_line_discarded": False,
        "bad_lines_skipped": 0,
        # Replay rows are counted here and returned nowhere else. Every
        # consumer of this function reads a premarket window and none of them
        # wants a print from the previous afternoon in it, so the filter sits
        # here rather than at four call sites where the fifth would forget.
        "replay_rows": 0,
        "replay_volume": 0.0,
        "replay_first_et": None,
        # Per symbol, not just the total. A symbol whose ONLY row is a replayed
        # print is absent from the bars dict exactly like a symbol the socket
        # never answered for, and on 2026-08-20 the packet called both silent:
        # NBTX delivered one 04:23 print of 20 shares and UUP one 07:00 print
        # of 1 share, and the report said the socket "delivered no trade for
        # them". The filter is right and the sentence was not, and the sentence
        # could not be better because the count was aggregate.
        "replay_by_symbol": {},
    }
    if not path.exists():
        return out, stats

    text = path.read_bytes().decode("utf-8", errors="replace")
    lines = text.split("\n")
    if lines and lines[-1] != "":
        # No trailing newline: the final line is incomplete. Drop it.
        stats["partial_line_discarded"] = True
        lines = lines[:-1]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            stats["bad_lines_skipped"] += 1
            continue
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        if row.get("replay"):
            stats["replay_rows"] += 1
            stats["replay_volume"] += float(row.get("v") or 0.0)
            stats["replay_by_symbol"][symbol] = (
                stats["replay_by_symbol"].get(symbol, 0) + 1)
            at = row.get("minute_et")
            if at and (stats["replay_first_et"] is None or at < stats["replay_first_et"]):
                stats["replay_first_et"] = at
            continue
        out.setdefault(symbol, []).append(row)
    for rows in out.values():
        rows.sort(key=lambda r: r.get("minute_epoch", 0))
        stats["bars_total"] += len(rows)
        last = rows[-1].get("minute_epoch")
        if last is not None and (stats["last_bar_epoch"] is None or last > stats["last_bar_epoch"]):
            stats["last_bar_epoch"] = last
    if stats["last_bar_epoch"] is not None:
        stats["last_bar_et"] = ettime.stamp(ettime.from_epoch_s(stats["last_bar_epoch"]))
    return out, stats


def read_bars(day: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Today's collected minutes, per symbol, oldest first.

    This is what everything except scan.py reads. Scan takes a snapshot copy
    first, because at 08:45 the collector is still appending to this file;
    see snapshot_bars.
    """
    bars, _ = read_bars_file(bar_path(day))
    return bars


def snapshot_bars(
    day: str, destination, overwrite: bool = False
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Copy the live bar file aside, then parse the copy.

    The collector appends until 09:25 and scan reads at 08:45, so the read
    overlaps the write. Copying first means the parse works on bytes that
    stopped moving, and the copy in runs/<date>/ records exactly what the
    packet saw.

    overwrite defaults to FALSE because this function mutates a run directory.
    scan owns today's snapshot and passes True, since a watchdog rerun of the
    morning chain is meant to produce a fresh one. A human pointing this at a
    past session to reproduce something is not the owner, and the default
    spares the frozen artifact and writes beside it instead. That default
    exists because on 2026-08-15 a hand run of this function replaced the
    frozen 08:45 snapshot for 2026-08-14 with the whole trading day, and the
    only reason it was noticed is that test_repricing reads that file.
    """
    import shutil

    from core import artifacts

    source = bar_path(day)
    stats: dict[str, Any]
    if not source.exists():
        return {}, {
            "bars_total": 0, "last_bar_epoch": None, "last_bar_et": None,
            "partial_line_discarded": False, "bad_lines_skipped": 0,
            "source_missing": True, "destination": str(destination), "spared": False,
        }
    destination, spared = artifacts.resolve(
        Path(destination), overwrite, what="snapshot"
    )
    shutil.copyfile(source, destination)
    bars, stats = read_bars_file(destination)
    stats["source_missing"] = False
    stats["destination"] = str(destination)
    stats["spared"] = spared
    return bars, stats


# ------------------------------------------------------------------ websocket

def _ws_url() -> str:
    return f"{config.EODHD_WS_TRADES_URL}?api_token={config.eodhd_token()}"


def _connect(symbols: list[str]) -> websocket.WebSocket:
    """Connect, wait to be authorised, then subscribe.

    The order matters. The server sends {"status_code":200,"message":"Authorized"}
    shortly after the socket opens, and a subscribe frame sent before it arrives
    is answered with {"status":500,"message":"Server error"} and a closed
    connection. That failure is silent in the sense that the socket looks fine
    and simply never delivers a trade, which is the worst way for a collector to
    fail, so we wait for the frame and say so if it never comes.
    """
    sslopt: dict[str, Any] = {"context": config.tls_context(), "cert_reqs": ssl.CERT_REQUIRED}
    socket = websocket.create_connection(_ws_url(), sslopt=sslopt, timeout=15)
    socket.settimeout(AUTH_WAIT_S)

    authorized = False
    deadline = time.time() + AUTH_WAIT_S
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
        if isinstance(message, dict) and message.get("status"):
            raise ConnectionError(f"server refused the connection: {message}")

    if not authorized:
        socket.close()
        raise ConnectionError(
            "no authorization frame arrived within "
            f"{AUTH_WAIT_S:g}s. Subscribing before that frame gets a 500 and a "
            "socket that never delivers a trade."
        )

    payload = {"action": "subscribe", "symbols": ",".join(_bare(s) for s in symbols)}
    socket.send(json.dumps(payload))
    socket.settimeout(1.0)
    return socket


class _PlannedResubscribe(Exception):
    """Not a fault. The clock reached resubscribe_time and the pool changed.

    Carried as an exception because the outer loop of run_websocket already
    knows how to close a socket and open another one with a fresh symbol list,
    and that path runs on every reconnect of every morning. Reusing it is the
    whole reason the two phase collector is a small change rather than a
    second connection manager: the resubscribe is a reconnect that was asked
    for rather than suffered. It costs no backoff and counts as no reconnect.
    """


def run_websocket(
    symbols: list[str], stop_at, builder: BarBuilder, chaos_reconnects: int = 0,
    reload_at=None, reload: Any = None,
) -> dict[str, Any]:
    """Collect until stop_at. chaos_reconnects deliberately drops the socket
    that many times, spread across the run, so the cost of a flaky morning
    (reconnect plus full resubscribe) can be measured rather than assumed.

    reload_at and reload are the two phase morning. From 2026-09-02 the
    collector starts at 04:00, before discover has run, on a provisional pool
    written by the 03:55 pass. At reload_at, which is discover's old start
    plus the five minutes the schedule has always allowed it, `reload` is
    called; it returns the symbol list from the watchlist as it now stands,
    and if that differs from what this socket is subscribed to the connection
    is replaced. A name on both lists keeps its tape from 04:00 without a
    break, because the bar file is per day and per symbol and knows nothing
    about connections.

    Why this matters more than the volume ratio it was proposed for: measured
    2026-08-29 over six sessions, the published entry reference sat a median
    1.19 percent from the true premarket high and up to 20.9 percent, and
    nearly all of that gap is 04:00 to 07:20 going unheard rather than the
    socket missing trades inside minutes it listened to. Ten to one on the
    median. The levels the report prints were wrong, not just the ratio.

    reload is called at most once and its failure is never fatal. A morning
    listening to the provisional pool is a morning with a tape; a morning that
    died at 07:20 reaching for a better one is not, and the tape cannot be
    fetched later.
    """
    backoff = BACKOFF_START_S
    connections = 0
    reconnects = 0
    refusals = 0
    messages = 0
    last_status = 0.0
    current = list(symbols)
    planned_resubscribes = 0
    reload_error: str | None = None
    last_reload_check = 0.0
    # Non fatal status frames, kept rather than only printed. A morning that
    # saw six odd frames and still worked is a different morning from a clean
    # one, and the run stats are where that difference has to survive.
    status_frames: list[dict[str, Any]] = []

    chaos_remaining = max(0, int(chaos_reconnects))
    chaos_next: float | None = None
    if chaos_remaining:
        window_s = max((stop_at - ettime.now_et()).total_seconds(), 60.0)
        chaos_interval = window_s / (chaos_remaining + 1)
        chaos_next = time.time() + chaos_interval

    while ettime.now_et() < stop_at:
        socket = None
        try:
            socket = _connect(current)
            connections += 1
            print(f"collector: connected, subscribed to {len(current)} symbols")
            backoff = BACKOFF_START_S

            while ettime.now_et() < stop_at:
                # The handover, checked on a stamp rather than once on a clock.
                # discover_due is 07:25, five minutes AFTER resubscribe_time,
                # so a watchdog rerun of a failed 07:15 pass lands after a
                # single-shot handover would already have given up. Watching
                # the watchlist's own generated_at instead means the pool is
                # picked up whenever it arrives, and a pass that never arrives
                # costs nothing but the checks.
                if (reload is not None and reload_at is not None
                        and planned_resubscribes < MAX_POOL_RELOADS
                        and ettime.now_et() >= reload_at
                        and time.time() - last_reload_check >= POOL_RELOAD_CHECK_S):
                    last_reload_check = time.time()
                    try:
                        wanted = reload()
                    except Exception as exc:  # noqa: BLE001
                        # Broad on purpose. Whatever went wrong reading a file
                        # on disk, this socket is already carrying the
                        # provisional pool's tape and must keep carrying it.
                        wanted = None
                        reload_error = f"{type(exc).__name__}: {exc}"
                        print(f"collector: the handover could not read the new pool "
                              f"({reload_error}). Staying on the pool this run "
                              "started with, which is a tape rather than none.")
                    if wanted is not None:
                        added = sorted(set(wanted) - set(current))
                        gone = sorted(set(current) - set(wanted))
                        print(f"collector: {ettime.hhmm(ettime.now_et())} ET, "
                              "resubscribing to the pool discover wrote. "
                              f"{len(added)} added, {len(gone)} dropped, "
                              f"{len(set(wanted) & set(current))} kept with their "
                              "tape from the start of the window.")
                        if added:
                            print("collector:   added   " + ", ".join(_bare(s) for s in added))
                        if gone:
                            print("collector:   dropped " + ", ".join(_bare(s) for s in gone))
                        current = list(wanted)
                        planned_resubscribes += 1
                        raise _PlannedResubscribe()
                if (chaos_remaining and chaos_next is not None
                        and time.time() >= chaos_next):
                    chaos_remaining -= 1
                    chaos_next = time.time() + chaos_interval
                    raise ConnectionError(
                        "forced chaos reconnect for the cost measurement"
                    )
                try:
                    raw = socket.recv()
                except websocket.WebSocketTimeoutException:
                    raw = None
                except (websocket.WebSocketConnectionClosedException, OSError) as exc:
                    raise ConnectionError(str(exc)) from exc

                if raw:
                    messages += 1
                    _handle_message(raw, builder, status_frames)

                now = time.time()
                builder.flush(now)
                if now - last_status >= 60:
                    last_status = now
                    print(
                        f"collector: {ettime.hhmm(ettime.now_et())} ET  "
                        f"trades {builder.trades_seen}  minutes written {builder.rows_written}  "
                        f"open bars {len(builder.open_bars)}"
                    )
        except _PlannedResubscribe:
            # No backoff and no reconnect count: nothing failed. The finally
            # below closes the socket and the outer loop opens the next one
            # with `current` as it now stands.
            pass
        except SubscriptionRefused as exc:
            # Almost always this run's own slots, still held by the connection
            # that dropped a second ago. Waiting gets them back; dying does
            # not. Four waits cost four minutes of a two hour window, and the
            # alternative already cost a whole morning once. If the slots
            # really do belong to somebody else, the retries run out and this
            # raises exactly as it used to.
            refusals += 1
            if ettime.now_et() >= stop_at or refusals > MAX_SUBSCRIPTION_RETRIES:
                # The counters travel with the exception. Without this the
                # caller has nothing to write but the refusal marker, so the
                # run's connections and messages never reach read_run_stats and
                # the packet reports a morning that heard nothing. On
                # 2026-08-19 collector_snapshot read messages 0, connections 0
                # over a morning that had already folded 14,680 trades.
                exc.run_stats = {
                    "connections": connections,
                    "reconnects": reconnects,
                    "subscription_refusals": refusals,
                    "resubscriptions": connections,
                    "planned_resubscribes": planned_resubscribes,
                    "pool_reload_error": reload_error,
                    "messages": messages,
                    "status_frames": len(status_frames),
                    "status_frames_seen": status_frames[:10],
                }
                raise
            print(f"collector: the subscription was refused, attempt {refusals} "
                  f"of {MAX_SUBSCRIPTION_RETRIES}. Waiting "
                  f"{SUBSCRIPTION_RETRY_WAIT_S:.0f}s for the slots to be "
                  "released. See CRITERIA.md, the symbols limit note.")
            time.sleep(SUBSCRIPTION_RETRY_WAIT_S)
        except (ConnectionError, websocket.WebSocketException, OSError) as exc:
            if ettime.now_et() >= stop_at:
                break
            reconnects += 1
            # The websocket URL carries the API token as a query parameter,
            # and a handshake exception can quote the URL. This print lands
            # in a log that sits on disk for months, so it is scrubbed.
            print(f"collector: connection lost ({config.scrub_secrets(exc)}). "
                  f"Reconnecting in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
        finally:
            if socket is not None:
                try:
                    socket.close()
                except Exception:
                    pass

    # Every successful connection sends exactly one subscribe frame covering
    # the full symbol list, so resubscriptions equals connections.
    return {
        "connections": connections,
        "reconnects": reconnects,
        "subscription_refusals": refusals,
        "resubscriptions": connections,
        "planned_resubscribes": planned_resubscribes,
        "pool_reload_error": reload_error,
        "messages": messages,
        "status_frames": len(status_frames),
        "status_frames_seen": status_frames[:10],
    }


class SubscriptionRefused(RuntimeError):
    """The server refused the subscription, so this connection hears nothing.

    Deliberately NOT a ConnectionError, OSError or WebSocketException. Those
    three are retried immediately with a short backoff, and this one must not
    be: an immediate retry is what causes it.

    [corrected 2026-08-19: this docstring previously said "retrying is exactly
    the wrong response here: the 50 symbol pool is account wide, so a refusal
    means another process is holding the slots and reconnecting will be refused
    again every time until the window is gone", and the run ended on the first
    refusal. That was written from the vendor's documentation of the cap rather
    than from a refusal, because none had been seen. On 2026-08-19 the
    collector streamed 50 symbols from 08:16, the remote host closed the
    connection at 08:34, the reconnect went out about a second later and was
    refused: the account was still holding the dropped connection's 50 symbols.
    The other process was this one, a second in its own past. It exited and
    lost the last 50 minutes of the window. A hand restart at 08:37:13
    subscribed without complaint. Refusals are now retried on a wait, and the
    old text is kept because the reasoning was untested rather than careless.]

    Raising out of the loop ends the run with the reason recorded, which is
    still what happens once the retries are spent. Until 2026-08-15 this frame
    was printed and swallowed: the collector then ran to its stop time, folded
    zero trades, wrote an empty bar file and exited zero, and the first sign of
    trouble was a morning report with no premarket data in it.
    """


# Status frames that mean the subscription did not take. Anything else non-200
# is recorded and surfaced but does not stop a run that may still be working.
_FATAL_STATUS_CODES = frozenset({422})


def _handle_message(
    raw: str, builder: BarBuilder, status_log: list[dict[str, Any]] | None = None
) -> None:
    try:
        message = json.loads(raw)
    except ValueError:
        return
    if not isinstance(message, dict):
        return
    if "s" not in message or "p" not in message:
        # Authorisation and status frames land here.
        code = message.get("status_code")
        if code and code != 200:
            if status_log is not None:
                status_log.append(message)
            if code in _FATAL_STATUS_CODES:
                # States the refusal and nothing about the run. Whether
                # anything was collected is the caller's fact, not this
                # function's, and the old wording asserted "Nothing was
                # collected" from inside a message handler that cannot know:
                # on 2026-08-19 it said so over 14,680 folded trades.
                raise SubscriptionRefused(
                    f"the server refused the subscription: {message}. The 50 "
                    "symbol pool is account wide and shared across every "
                    "connection on this token, including this collector's own "
                    "just dropped one, which the server can still be holding "
                    "seconds later."
                )
            print(f"collector: server said {message}")
        return

    try:
        price = float(message["p"])
        volume = float(message.get("v") or 0)
        epoch_s = float(message.get("t") or 0) / 1000.0
    except (TypeError, ValueError):
        return
    if epoch_s <= 0 or price <= 0:
        return

    try:
        builder.add_trade(
            symbol=_full(str(message["s"])),
            price=price,
            volume=volume,
            epoch_s=epoch_s,
            dark_pool=bool(message.get("dp")),
            market_status=message.get("ms"),
        )
    except (OSError, OverflowError, ValueError) as exc:
        # A MALFORMED MESSAGE IS NOT A LOST CONNECTION, and until this it was
        # indistinguishable from one. The `t` field is milliseconds; a value in
        # microseconds, in nanoseconds, or simply corrupt divides to an epoch
        # outside datetime's range, and ettime.from_epoch_s raises OSError
        # [Errno 22] on Windows for exactly that. This function is called
        # inside run_websocket's message loop, whose handler is
        # `except (ConnectionError, WebSocketException, OSError)`, so ONE bad
        # trade tore down a healthy socket, counted a reconnect, and
        # resubscribed into a 50 slot pool the server is known to refuse while
        # it still holds the slots this run just dropped. The guard on
        # epoch_s bounds it only from below.
        #
        # Counted, not silent. A feed that starts sending a different unit
        # would otherwise look like a quiet tape, and this counter is what
        # tells the two apart.
        builder.unparseable_trades += 1
        if builder.unparseable_trades <= 3:
            print(f"collector: discarded a trade this parser cannot place: "
                  f"{type(exc).__name__}: {exc}. Message keys "
                  f"{sorted(message)}, t={message.get('t')!r}. It is NOT a "
                  "connection fault and the socket is left alone.")


# -------------------------------------------------------------- poll fallback

def run_poll(symbols: list[str], stop_at, builder: BarBuilder) -> dict[str, Any]:
    """Live v1 polling for a day the socket is down.

    This is a degraded source and it says so. A poll gives a cumulative day
    volume and a last price, so each bar carries the volume that accumulated
    since the previous poll and a single price for open, high, low and close.
    Every row is stamped src=poll, and any premarket high derived from it
    understates the real one.
    """
    from core import eodhd

    api = eodhd.client()
    previous_volume: dict[str, float] = {}
    polls = 0

    while ettime.now_et() < stop_at:
        data, error = api.live_quotes(symbols)
        polls += 1
        if error and not data:
            print(f"collector: poll failed, {error}")
        now = time.time()
        for symbol, row in (data or {}).items():
            try:
                price = float(row.get("close"))
                volume = float(row.get("volume") or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            delta = volume - previous_volume.get(symbol, volume)
            previous_volume[symbol] = volume
            builder.add_synthetic(symbol, price, max(delta, 0.0), now)
        builder.flush(now)
        print(
            f"collector: {ettime.hhmm(ettime.now_et())} ET  poll {polls}  "
            f"minutes written {builder.rows_written}"
        )

        remaining = (stop_at - ettime.now_et()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(POLL_INTERVAL_S, remaining))

    return {"polls": polls}


# -------------------------------------------------------------------- runner

# Where one reading sits relative to the vendor. Names rather than bare
# strings, because the direction below is decided by comparing two of these to
# each other and a typo in a comparison of two string literals is silent.
_BELOW, _AGREES, _ABOVE = "below", "agrees", "above"

_MEDIAN_WORDS = {
    _BELOW: "the typical symbol recorded LESS than the vendor",
    _AGREES: "the typical symbol matched the vendor",
    _ABOVE: "the typical symbol recorded MORE than the vendor",
}
_AGGREGATE_WORDS = {
    _BELOW: "the aggregate tape recorded LESS",
    _AGREES: "the aggregate tape matched it",
    _ABOVE: "the aggregate tape recorded MORE",
}


def _reading_side(distance_pct: float, tolerance_pct: float) -> str:
    """Which side of the vendor one reading sits on, or that it sits on it.

    distance_pct is that reading's distance from the vendor in percent. The
    signed median is already in those units; the aggregate ratio becomes them
    as (ratio - 1) * 100.
    """
    if abs(distance_pct) <= tolerance_pct:
        return _AGREES
    return _BELOW if distance_pct < 0 else _ABOVE


def _volume_check_direction(
    median_signed: float, ratio: float | None
) -> tuple[str, str]:
    """Which way the collector is wrong, that it is wrong both ways, or neither.

    Two readings, and they answer different questions. The signed median is the
    TYPICAL symbol. The aggregate ratio is the whole tape, so a handful of
    enormous positives can carry it while most symbols sit below the vendor.
    2026-08-14 is exactly that morning: a signed median of -33.77 percent
    beside an aggregate 3.83 times the vendor's volume, recorded in
    doc/research/COLLECTOR_VOLUME.md. A single word that averaged the two would
    be a claim nothing measured, so a direction is only returned when both
    readings say the same thing about the collector.

    Both readings are now placed against an agreement band, [collector]
    volume_check_agreement_pct, rather than against zero, and there is a word
    for the case where both land inside it. Until 2026-08-20 the tests were
    "median_signed < 0 and ratio < 1" for under and its mirror for over, with
    everything else falling through to mixed, and that had no branch at all for
    a collector that MATCHES the vendor, which is the outcome this measurement
    exists to work towards. A perfectly agreeing session came back "mixed: the
    two readings disagree, the typical symbol falling on one side of the vendor
    and the aggregate tape on the other", a sentence that is false of a session
    where neither reading is on a side. So did every pair with one reading
    inside the noise and the other outside it: a signed median of -50 against
    an aggregate ratio of exactly 1.0 is a real disagreement, but it is not the
    two readings straddling the vendor. REPORT_TEMPLATE.md orders the model to
    quote direction_phrase verbatim, so each of those went out as written. The
    mixed phrase is now built from what the two readings actually said.
    """
    if ratio is None:
        return "unknown", (
            "the vendor reported no volume at all over the compared minutes, so "
            "there is no direction to read")
    tolerance = VOLUME_CHECK_AGREEMENT_PCT
    median_side = _reading_side(median_signed, tolerance)
    ratio_side = _reading_side((ratio - 1.0) * 100.0, tolerance)
    if median_side == _AGREES and ratio_side == _AGREES:
        return "agree", (
            f"the collector matched the vendor to within {tolerance:g} percent "
            "on both readings, the typical symbol and the aggregate tape, so "
            "the feed adds no measurable distortion to a ratio built on a "
            "collector numerator")
    if median_side == _BELOW and ratio_side == _BELOW:
        return "under", (
            "the collector recorded LESS than the vendor on both readings, the "
            "typical symbol and the aggregate tape, so a ratio built on a "
            "collector numerator understates by about that much")
    if median_side == _ABOVE and ratio_side == _ABOVE:
        return "over", (
            "the collector recorded MORE than the vendor on both readings, the "
            "typical symbol and the aggregate tape, so a ratio built on a "
            "collector numerator OVERSTATES by about that much")
    return "mixed", (
        f"the two readings do not agree: {_MEDIAN_WORDS[median_side]} and "
        f"{_AGGREGATE_WORDS[ratio_side]}, so a ratio built on a collector "
        "numerator may be over or under and neither may be assumed")


def verify_against_intraday(day: str, quiet: bool = False) -> dict[str, Any] | None:
    """Compare a collected day against EODHD 1m intraday, minute for minute.

    This is the definitive volume check: same minutes, same units, no delayed
    window arithmetic. Intraday for the current day is published a few hours
    behind, so this runs in the evening, and the nightly backfill calls it for
    the record. Returns the summary, or None when intraday has nothing yet.

    The summary is SIGNED, and until 2026-08-20 it was not. This function
    computed a per symbol signed difference and then persisted only its
    magnitude, and three consumers asserted a direction that a magnitude cannot
    carry: scan.volume_check wrote "an RVOL below is understated by about that
    much again" into gaps_to_fill, analyst.py repeated it in the degraded
    fallback, and REPORT_TEMPLATE.md ordered the model to say it plainly, which
    runs/2026-08-20/report.md published. The project's own diagnosis refutes
    the assumption. doc/research/COLLECTOR_VOLUME.md records the collector
    wrong in BOTH directions: 2026-08-14 came back 3.83 times the vendor in
    aggregate against 2026-08-17 at -88.49 percent across all 29 comparable
    symbols. So the signed median, the aggregate ratio and the direction the
    two of them agree on all come back now, a session where they disagree is
    reported as mixed rather than as either, and a session where both readings
    sit inside the agreement band is reported as agreement rather than as a
    disagreement running both ways.

    The MEASUREMENT was biased the same way the summary was, so both missing
    sides are counted rather than dropped. The loop walks the collected bars,
    so a subscribed symbol the socket never answered for landed in neither
    compared nor unavailable: LYTS.US and NBTX.US on 2026-08-20 were in
    neither, and the summary read as though those two had been measured and
    agreed. A vendor volume of zero over the common minutes was skipped without
    incrementing anything either. Every symbol that has collected bars and
    every symbol the subscription list names now lands in exactly one of
    compared, unavailable, vendor_zero_volume or collector_silent, and those
    four sum to symbols_accounted.

    symbols_accounted is NOT the subscription count, and calling it that is
    what this docstring got wrong on the day it was written.
    write_subscriptions rewrites its file on every collector run, on purpose,
    so a morning the collector was restarted onto a different list leaves that
    file holding the last run while the bar file holds every run's trades.
    2026-08-19 is such a morning and it is in the archive: the socket was
    refused at 08:35 because the account's own dropped connection still held
    the fifty slots, a hand restart at 08:37:14 subscribed to a different
    fifty, and the file names 50 symbols against 73 that carry bars, so the
    four buckets sum to 75 there against a `subscribed` of 50.
    bars_outside_subscription counts the symbols the list does not reach and
    subscribed_reason says why in a sentence, because a reader comparing
    compared against subscribed on that day has to be told why 73 is larger
    than 50 rather than left to decide which of the two numbers is broken.

    Per symbol comparable minute counts come back too. A symbol compared on two
    minutes and one compared on 125 are not the same evidence, and a caller
    could not tell them apart from a summary publishing only a count of
    symbols.
    """
    import statistics as stats

    from core import eodhd

    api = eodhd.client()
    bars = read_bars(day)
    if not bars:
        print(f"collector: no collected bars for {day}, nothing to verify")
        return None

    results: list[tuple[str, int, float, float, float]] = []
    unavailable: list[str] = []
    vendor_zero: list[str] = []
    for symbol in sorted(bars):
        mine = {b["minute_epoch"]: b for b in bars[symbol]}
        low, high = min(mine), max(mine)
        rows, error = api.intraday(
            symbol, ettime.from_epoch_s(low), ettime.from_epoch_s(high + BAR_SECONDS), "1m"
        )
        if error or not rows:
            unavailable.append(symbol)
            continue
        theirs = {int(r["timestamp"]): r for r in rows if r.get("timestamp") is not None}
        common = sorted(set(mine) & set(theirs))
        if not common:
            unavailable.append(symbol)
            continue
        my_volume = sum(float(mine[t]["v"]) for t in common)
        their_volume = sum(float(theirs[t].get("volume") or 0) for t in common)
        if their_volume <= 0:
            # Counted, not dropped. A vendor zero over the common minutes is a
            # symbol this check could not measure, and it used to leave the loop
            # without incrementing anything at all, so it disappeared out of
            # every denominator the summary published.
            vendor_zero.append(symbol)
            continue
        pct = (my_volume - their_volume) / their_volume * 100.0
        results.append((symbol, len(common), my_volume, their_volume, pct))

    # The other missing side. read_bars only knows what the socket answered
    # for, so a name that was subscribed and never heard from is invisible to
    # the loop above. The subscription list is what the collector asked for and
    # is the only record of the difference.
    subscriptions = read_subscriptions(day) or {}
    requested = sorted(str(s) for s in (subscriptions.get("symbols") or []))
    collector_silent = sorted(set(requested) - set(bars))
    # And the side that is not missing but extra, which the four buckets used
    # to imply could not exist. The loop above walks the bar file, so a symbol
    # with bars is counted whether or not the subscription list on disk names
    # it, and on a restarted morning that list is only the last run's. Counted
    # and named rather than folded in quietly, because a symbol carrying bars
    # that the list does not name is itself a fact about the morning: it says
    # the collector ran twice on two different watchlists.
    outside_subscription = sorted(set(bars) - set(requested))
    accounted = len(set(bars) | set(requested))

    if not results:
        print(
            f"collector: intraday has no bars yet for {day} "
            f"({len(unavailable)} symbols empty). It is published a few hours behind, try later."
        )
        return None

    within = sum(1 for r in results if abs(r[4]) <= 1.0)
    median_abs = stats.median(abs(r[4]) for r in results)
    median_signed = stats.median(r[4] for r in results)
    collector_total = sum(r[2] for r in results)
    intraday_total = sum(r[3] for r in results)
    ratio = (collector_total / intraday_total) if intraday_total > 0 else None
    below = sum(1 for r in results if r[4] < 0)
    above = sum(1 for r in results if r[4] > 0)
    direction, direction_phrase = _volume_check_direction(median_signed, ratio)
    if not requested:
        subscribed_reason = (
            f"the collector wrote no subscription list for {day}, so a symbol it "
            "never heard cannot be told from one nobody asked for")
    elif outside_subscription:
        subscribed_reason = (
            f"the subscription list for {day} was written at "
            f"{subscriptions.get('subscribed_at') or 'an unrecorded time'} and "
            "every collector run rewrites it, so on a restarted morning it "
            f"names the last run only: {len(outside_subscription)} symbol(s) "
            "here carry collected bars it does not name, and the four buckets "
            f"account for {accounted} symbol(s) rather than the "
            f"{len(requested)} on the list")
    else:
        subscribed_reason = None
    if not quiet:
        print("")
        print(f"verification against EODHD 1m intraday for {day}, identical minutes only")
        print(f"  {'symbol':<10} {'mins':>5} {'collected':>13} {'intraday':>13} {'diff %':>9}")
        for symbol, minutes, mine_v, theirs_v, pct in results:
            print(f"  {symbol:<10} {minutes:>5} {mine_v:>13,.0f} {theirs_v:>13,.0f} {pct:>8.2f}%")
        print(f"  {within} of {len(results)} symbols within one percent on volume")
        print(f"  median absolute difference {median_abs:.3f}%")
        print(f"  median SIGNED difference {median_signed:+.3f}%, "
              f"{below} symbol(s) below the vendor and {above} above")
        if ratio is not None:
            print(f"  aggregate {collector_total:,.0f} collected against "
                  f"{intraday_total:,.0f} intraday, {ratio:.4f} times the vendor")
        print(f"  direction {direction}: {direction_phrase}")
        if unavailable:
            print(f"  {len(unavailable)} symbols had no intraday bars to compare")
        if vendor_zero:
            print(f"  {len(vendor_zero)} symbols reported zero vendor volume on "
                  "the common minutes and could not be compared")
        if collector_silent:
            print(f"  {len(collector_silent)} subscribed symbols the collector "
                  f"never heard: {', '.join(collector_silent)}")
        if outside_subscription:
            print(f"  {len(outside_subscription)} symbols carry collected bars "
                  "that the subscription list on disk does not name, so the "
                  "collector was restarted onto a different list during the "
                  f"morning: {', '.join(outside_subscription)}")
        if requested:
            print(f"  the four buckets above account for {accounted} symbol(s) "
                  f"against a subscription list of {len(requested)}")
        else:
            print(f"  the four buckets above account for {accounted} symbol(s); "
                  "no subscription list was written for this day, so there is "
                  "nothing to check that total against")
    return {
        "day": day,
        "compared": len(results),
        "within_one_percent": within,
        "median_abs_pct": median_abs,
        # Everything below this line arrived on 2026-08-20. The four keys above
        # are unchanged, so a reader of an older summary and a reader of this
        # one are looking at the same fields where they overlap.
        "median_signed_pct": median_signed,
        "direction": direction,
        "direction_phrase": direction_phrase,
        "symbols_collector_below_vendor": below,
        "symbols_collector_above_vendor": above,
        "collector_volume_total": collector_total,
        "intraday_volume_total": intraday_total,
        "aggregate_ratio": ratio,
        "minutes_compared_by_symbol": {r[0]: r[1] for r in results},
        "minutes_compared_total": sum(r[1] for r in results),
        # The two volumes behind every number above, per symbol, added
        # 2026-08-21. They were computed and discarded on every run before
        # that, and they are the only thing that can answer whether this
        # shortfall is CALIBRATABLE.
        #
        # The reasoning, because the key looks redundant beside aggregate_ratio
        # and is not. A single ratio for the session says how much of the tape
        # the socket heard on average. It cannot say whether the share is a
        # stable property of a symbol or noise that happens to average out, and
        # only the first of those can be divided back out of a numerator. The
        # 2026-08-19 socket probe measured per symbol shares from 2.06 to 12.05
        # percent with a B/A ratio ranging 0.66 to 2.30, which is exactly the
        # dispersion that decides it, and nothing on disk let anyone check it
        # across sessions.
        #
        # Raw volumes rather than a derived rate, deliberately. A rate stored
        # beside the numbers it comes from is a second representation that will
        # eventually disagree with the first, which this repository has already
        # paid for once with prior_close and prior_high.
        #
        # Safe to add: _PACKET_VOLUME_CHECK_KEYS in scan.py is a whitelist, so
        # this stays in the file and never widens the containment allow set
        # with a roster of symbols the morning holds no evidence about.
        "volume_by_symbol": {
            r[0]: {"collector": r[2], "vendor": r[3]} for r in results},
        "unavailable": len(unavailable),
        "unavailable_symbols": unavailable,
        "vendor_zero_volume": len(vendor_zero),
        "vendor_zero_volume_symbols": vendor_zero,
        "collector_silent": len(collector_silent),
        "collector_silent_symbols": collector_silent,
        # What the four buckets above actually sum to, published so nobody has
        # to reconstruct it from `subscribed` and be wrong on a restart day.
        "symbols_accounted": accounted,
        "bars_outside_subscription": len(outside_subscription),
        "bars_outside_subscription_symbols": outside_subscription,
        "subscribed": len(requested) or None,
        "subscribed_at": subscriptions.get("subscribed_at"),
        "subscribed_reason": subscribed_reason,
    }


VOLUME_CHECK_FILE = "verify_intraday.json"


def latest_volume_check(before_day: str) -> dict[str, Any] | None:
    """The most recent written verify_against_intraday summary, read off disk.

    READS ONLY. verify_against_intraday itself costs one intraday call per
    collected symbol, fifty of them on an ordinary morning, and the 08:45
    window does not spend that. The nightly takes the measurement and writes it
    to runs/<date>/verify_intraday.json; this hands it to whoever needs to
    quote it. See the volume check note in CRITERIA.md.

    Strictly BEFORE before_day, because today's own check cannot exist yet: the
    vendor publishes intraday hours behind live, which is the whole reason the
    check is nightly.

    Returns the summary with `age_days` and `stale` added, or None when no
    check has ever been written. Age is reported rather than enforced here, so
    the caller decides what a stale measurement is worth and can say so; a
    reader silently dropping an old number would leave the morning looking
    unmeasured when it is merely out of date, and those are different facts.
    """
    max_age = _CRIT.integer("collector", "volume_check_max_age_days")
    directory = config.RUNS_DIR
    if not directory.is_dir():
        return None

    cutoff = ettime.parse_date(before_day)
    best: tuple[str, dict[str, Any]] | None = None
    for child in directory.iterdir():
        if not child.is_dir() or not _RUN_DATE_RE.match(child.name):
            continue
        if child.name >= before_day:
            continue
        path = child / VOLUME_CHECK_FILE
        if not path.is_file():
            continue
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A half written or hand mangled summary is no measurement. Skipped
            # rather than raised: this is read on the morning path, and a bad
            # file from three weeks ago must not be what ends a run.
            continue
        if not isinstance(summary, dict) or summary.get("compared") is None:
            continue
        if best is None or child.name > best[0]:
            best = (child.name, summary)

    if best is None:
        return None
    day, summary = best
    age = (cutoff - ettime.parse_date(day)).days
    # A summary written before verify_against_intraday recorded a sign carries
    # a magnitude and nothing else. Those files are still on disk and the
    # morning has to read them rather than crash on them, so the absence is
    # filled in as an absence: direction "unknown" and sign_recorded False, so
    # a caller reaches for the word "understated" only where something measured
    # it. The old files are not rewritten. A measurement is not editable after
    # the fact.
    signed = summary.get("median_signed_pct")
    read = {
        **summary,
        "day": summary.get("day") or day,
        "age_days": age,
        "stale": age > max_age,
        "max_age_days": max_age,
        "source": f"runs/{day}/{VOLUME_CHECK_FILE}, written by the nightly backfill",
        "sign_recorded": signed is not None,
    }
    if signed is None:
        read["median_signed_pct"] = None
        read["direction"] = "unknown"
        read["direction_phrase"] = (
            "this reading was written before the check recorded a sign, so the "
            "direction of the disagreement is unknown and must not be stated")
    return read


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)

# The override token, in ONE place. It has to be spelled identically in three
# unrelated languages: this module's argparse flag, monitor_jobs' args tuple,
# and job_collector.bat's `if /i` compare. Nothing links them, and a typo in
# any one is silent in the worst way: the .bat falls through to the plain
# invocation, the collector refuses the very file the last-resort branch had
# just decided was better than no tape, and the monitor still logs that it
# passed the flag. Python's two spellings are derived from this name; the
# .bat cannot import it, so a claim reads the file and asserts the third
# agrees.
STALE_WATCHLIST_ARG = "stale-watchlist-ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect the premarket price path.")
    parser.add_argument("--poll", action="store_true",
                        help="Fall back to Live v1 polling for a day the socket is down.")
    # FOR INSTRUMENTS, and there is exactly one. A research run that wants a
    # live socket must not land in the session capture: on 2026-09-01
    # measure_socket_cost put 932 regular hours bars into that morning's
    # premarket file, every symbol's latest price then read 10:07, and the
    # vintage guard refused a packet built from it. Absent, nothing changes
    # and the scheduled collector writes where it always has.
    parser.add_argument("--premarket-dir", default=None, metavar="PATH",
                        help="Write the capture, its stats and its "
                             "subscription list here instead of "
                             "data/premarket. For instruments only.")
    parser.add_argument("--minutes", type=float, default=None,
                        help="Run for this many minutes instead of until the CRITERIA.md stop time.")
    parser.add_argument("--chaos-reconnects", type=int, default=0, metavar="N",
                        help="Deliberately drop the socket N times, spread across the "
                             "run, so measure_socket_cost.py can price a flaky morning.")
    parser.add_argument("--verify", action="store_true",
                        help="Bracket the run with two Live v1 polls and compare volume. "
                             "Directional only, see the verification note in CRITERIA.md.")
    parser.add_argument("--verify-intraday", metavar="DAY", nargs="?", const="today",
                        help="Compare an already collected day against EODHD 1m intraday "
                             "bars, minute for minute. The definitive check, run it in the "
                             "evening once intraday has caught up.")
    parser.add_argument("--snapshot", metavar="DAY",
                        help="Freeze that day's collector file into runs/DAY/ and report "
                             "what it holds. Refuses to replace an existing snapshot "
                             "unless --overwrite is given.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Allow --snapshot to replace an existing artifact under "
                             "runs/. Without it the original is spared and the copy is "
                             "written beside it.")
    parser.add_argument("--" + STALE_WATCHLIST_ARG, action="store_true",
                        help="Subscribe even when watchlist.json was not written "
                             "today. For ONE caller: the monitor's last-resort "
                             "branch, past the last pass that could rerun discover "
                             "inside the collector window. See CRITERIA [Monitor], "
                             "the stale watchlist note. Not for hand runs.")
    args = parser.parse_args(argv)

    # REBOUND, not passed down. bar_path, stats_path and subscriptions_path
    # all read config.PREMARKET_DIR at call time, so moving the attribute
    # moves all three together and cannot leave one of them behind in the
    # real directory. Threading a parameter through each would be three
    # chances to miss one.
    if args.premarket_dir:
        config.PREMARKET_DIR = Path(args.premarket_dir).expanduser().resolve()
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        print(f"collector: writing to {config.PREMARKET_DIR} rather than the "
              "session capture, because --premarket-dir was given")

    if args.snapshot:
        day = ettime.today_str() if args.snapshot == "today" else args.snapshot
        destination = config.run_dir(day) / "premarket_snapshot.jsonl"
        bars, stats = snapshot_bars(day, destination, overwrite=args.overwrite)
        if stats.get("source_missing"):
            print(f"snapshot: no collector file for {day}, nothing to freeze")
            return 1
        print(f"snapshot: wrote {stats['destination']}")
        print(f"snapshot: {stats['bars_total']:,} bars, {len(bars):,} symbols, "
              f"last complete bar {stats.get('last_bar_et')}")
        if stats.get("spared"):
            print("snapshot: the original was NOT replaced")
        return 0

    if args.verify_intraday:
        day = ettime.today_str() if args.verify_intraday == "today" else args.verify_intraday
        result = verify_against_intraday(day)
        from core import eodhd as _eodhd

        _eodhd.print_call_report()
        return 0 if result else 1

    config.ensure_dirs()
    from core import eodhd  # imported here so the atexit call report covers every mode

    watchlist = discover.load_watchlist()
    if watchlist.get("missing"):
        print(f"collector: {config.WATCHLIST_PATH} is missing. Run discover.py first.")
        return 1

    # And it has to be TODAY'S. A watchlist from another session is refused
    # rather than used, with no degrade path and no override flag, for the
    # reason morning/vintage.py gives for having neither: it is not thin
    # evidence this run can hedge around, it is the wrong pool wearing the
    # costume of the right one.
    #
    # 2026-08-24 is the morning that paid for this. A power cut ran from 01:00
    # to 07:49 ET. Every weekday task carries -StartWhenAvailable, so Task
    # Scheduler caught the whole set up at one instant, 07:54:58, which
    # collapsed the 07:15 to 07:20 gap between discover and this process to
    # nothing. This process read watchlist.json in the same second discover was
    # replacing it, got the file from the session before, and select_symbols
    # found no row in it marked subscribed. An empty list is not an error, so
    # the run carried on and subscribed to the context tickers and nothing
    # else. It then ran healthy for fourteen minutes, and the watchdog read it
    # as alive because it was: monitor_jobs restarts a collector that is DEAD,
    # and this one was listening perfectly to the wrong thing. Every one of the
    # day's 42 candidates would have reached the 08:45 scan with no coverage,
    # which the report says as "on the watchlist but the collector recorded no
    # bars for it" -- a sentence that reads like a quiet tape rather than like
    # a collector that was never asked.
    #
    # This is the fourth hard rule applied to an empty list, which is where the
    # 2026-08-22 review found two thirds of its twenty three defects: a missing
    # answer presented as a measured one, leaking wherever the missing thing
    # had a falsy value rather than a null. An unsubscribed pool is one more.
    #
    # Refusing is also what repairs it, and that machinery already exists. A
    # refusal writes no subscription list, and monitor_jobs reruns discover
    # while none has been written today and restarts a collector that is not
    # alive inside the window, so the next pass rebuilds the file and starts
    # this process on it. The atomic write in selection/discover.py keeps a
    # TORN watchlist from reaching here; this keeps a whole stale one from
    # getting past. Neither --snapshot nor --verify-intraday is affected: both
    # return well above this line and never subscribe to anything.
    generated_at = watchlist.get("generated_at")
    try:
        generated_on = ettime.parse_date(str(generated_at))
    except (TypeError, ValueError):
        generated_on = None

    today = ettime.today_et()
    if generated_on != today:
        said = generated_on.isoformat() if generated_on else "no date this can read"
        if not args.stale_watchlist_ok:
            print(f"collector: REFUSED, the watchlist is not today's. "
                  f"{config.WATCHLIST_PATH.name} carries generated_at "
                  f"{generated_at!r}, which is {said}, and today is "
                  f"{today.isoformat()}.")
            print("collector: subscribing on it would listen to another session's "
                  "pool, or to the context tickers alone, and the 08:45 scan would "
                  "report that silence as a quiet tape rather than as a collector "
                  "that never listened. Run discover first. The watchdog does this "
                  "by itself on its next pass.")
            return 1
        # The one caller that may say this is the monitor's last-resort branch,
        # past the last pass that could rerun discover inside the window. There
        # the choice is no longer between right names now and right names in
        # half an hour, it is between possibly wrong names and no tape at all,
        # and CRITERIA [Monitor] decides for the tape. Loud rather than silent:
        # the whole defect this refusal exists for was a run that looked
        # healthy, and scan raises its own gap on the same fact from the packet.
        print(f"collector: the watchlist is NOT today's, it is {said} against "
              f"{today.isoformat()}, and --stale-watchlist-ok was given, so this "
              "run subscribes on it anyway.")
        print("collector: the names below may belong to another session. Only "
              "the monitor's last-resort branch passes this flag; if a human "
              "did, that was a mistake and the morning will screen names this "
              "tape does not cover.")

    symbols, dropped = select_symbols(watchlist)
    print(f"collector: watchlist generated at {watchlist.get('generated_at')}")
    print(f"collector: subscribing to {len(symbols)} symbols "
          f"(cap {MAX_SUBSCRIPTIONS}, {len(_CRIT.text_list('collector', 'context_symbols'))} of them context)")
    if dropped:
        # Reported by tier and rank, which is what discover actually cut on.
        # This used to print gap_pct, a key discover stopped writing at
        # d224837, through `float(row.get("gap_pct") or 0)`. That `or 0` is
        # the part that mattered: it would have printed a confident
        # "gap +0.00%" for every dropped name from Monday onwards, since the
        # 2026-08-14 watchlist on disk was the last one written by the old
        # code. A fabricated flat gap in the exact line that justifies which
        # names were cut is the same failure as the stale price, one log line
        # further down. The header lied too: select_symbols has not re-sorted
        # by gap since d224837, it keeps discover's ranking.
        print(f"collector: DROPPED {len(dropped)} names to fit the cap, "
              "lowest ranked by discover first:")
        for row in dropped:
            tier = row.get("pool_tier")
            rank = row.get("pool_rank")
            sources = ", ".join(row.get("pool_source") or []) or "no source recorded"
            print(f"    dropped {row['symbol']:<12} "
                  f"tier {tier if tier is not None else '?'} "
                  f"rank {rank if rank is not None else '?':>4}  {sources}")
    else:
        print("collector: no names dropped, the whole watchlist fits under the cap")

    import datetime as dt

    now = ettime.now_et()
    if args.verify:
        # Verification runs on its own schedule, because it has to warm up past
        # the Live v1 delay before the comparison window can begin.
        stop_at = now + dt.timedelta(minutes=VERIFY_WARMUP_MINUTES + VERIFY_WINDOW_MINUTES)
        print(f"collector: verification mode, running about "
              f"{VERIFY_WARMUP_MINUTES + VERIFY_WINDOW_MINUTES:g} minutes")
    elif args.minutes is not None:
        stop_at = now + dt.timedelta(minutes=args.minutes)
        print(f"collector: running until {ettime.stamp(stop_at)}")
    else:
        stop_at = ettime.at_hm(now.date(), _CRIT.clock("collector", "stop_time"))
        print(f"collector: running until {ettime.stamp(stop_at)}")
        if stop_at <= now:
            print("collector: the stop time has already passed today, nothing to do")
            return 0

    # The window this run will accept trades for. It opens at the configured
    # collector start, or at the moment this process started if that is
    # earlier, so an ad hoc evening run is not refusing its own tape. It stays
    # open late_trade_grace_s past the stop, which is how long the builder
    # already waits for a print to arrive out of order.
    #
    # Deliberately NOT the moment this process started on a rerun. The 08:55
    # watchdog restart on 2026-08-18 resumed a file already holding 07:20
    # onward, and a window that opened at 08:55 would have refused every late
    # print belonging to the minutes it was resuming.
    #
    # Floored to its own minute, and that is not tidiness. Trade timestamps
    # arrive as whole milliseconds of a whole second, so a trade printed in the
    # same second the process started carries an epoch up to a second BELOW the
    # window's opening instant and would be refused for being early. The suite's
    # replayed socket caught exactly that: thirty trades stamped 0.89 seconds
    # before an open computed to the microsecond, and a collector that wrote no
    # minutes at all. Bars are minute granular anyway, so the minute the
    # collector started in is part of the window by construction.
    window_open = float(minute_floor(min(
        ettime.at_hm(now.date(), _CRIT.clock("collector", "start_time")), now
    ).timestamp()))
    builder = BarBuilder(
        bar_path(),
        source="poll" if args.poll else "ws",
        window=(window_open, stop_at.timestamp() + LATE_TRADE_GRACE_S),
    )

    # Written before the socket opens, so the 08:45 packet can name a symbol
    # that was subscribed and stayed silent. Monday is the first morning at
    # fifty subscriptions and the throughput has only ever been measured at
    # thirty eight, so this is the run that has to be able to say which names
    # the socket actually served.
    written_to = write_subscriptions(symbols, dropped)
    print(f"collector: subscription list written to {written_to.name}")

    # The second phase. This run starts at [Collector] start_time, which is
    # before discover has built today's pool, on the provisional watchlist the
    # 03:55 pass wrote. At resubscribe_time the real one exists, so it is read
    # and the socket moved onto it. See the two phase note in CRITERIA.
    reload_at = None
    if not (args.verify or args.poll or args.minutes is not None):
        reload_at = ettime.at_hm(now.date(), _CRIT.clock("collector", "resubscribe_time"))
        if reload_at <= now or reload_at >= stop_at:
            # A run that started after the handover, which is every watchdog
            # restart and every hand run, already read the final watchlist.
            reload_at = None
        else:
            print(f"collector: two phase run, listening on the pool this "
                  f"watchlist names and rereading it at "
                  f"{ettime.hhmm(reload_at)} ET")

    # The generated_at this run subscribed on. The handover fires when the
    # file carries a different one, so a watchdog rerun of a failed 07:15 pass
    # is picked up too, and a pool that never changes costs nothing.
    subscribed_stamp = str(watchlist.get("generated_at"))

    def reload_pool() -> list[str] | None:
        """The symbol list if the watchlist has been replaced, else None.

        None means stay put, and every refusal returns it rather than raising:
        there is nothing wrong with the tape this run is already carrying and
        it must keep carrying it. Refuses on exactly the ground the startup
        path refuses on, a watchlist that is not today's, because the handover
        must not become the door that lets another session's pool in.
        """
        nonlocal subscribed_stamp
        fresh = discover.load_watchlist()
        if fresh.get("missing"):
            return None
        stamp = str(fresh.get("generated_at"))
        if stamp == subscribed_stamp:
            return None
        try:
            fresh_on = ettime.parse_date(stamp)
        except (TypeError, ValueError):
            fresh_on = None
        if fresh_on != ettime.today_et():
            print("collector: the watchlist changed but is not today's, so this "
                  "run stays on the pool it started with")
            return None
        wanted, dropped_now = select_symbols(fresh)
        if not wanted:
            print("collector: the new watchlist names nothing to subscribe to, "
                  "so this run stays on the pool it started with")
            return None
        subscribed_stamp = stamp
        write_subscriptions(wanted, dropped_now)
        print(f"collector: the watchlist was replaced, generated_at {stamp}")
        return wanted

    calls_before = eodhd.call_count()
    refused: str | None = None
    try:
        if args.verify:
            stats = _run_verification(symbols, builder)
        elif args.poll:
            stats = run_poll(symbols, stop_at, builder)
        else:
            stats = run_websocket(symbols, stop_at, builder,
                                  chaos_reconnects=args.chaos_reconnects,
                                  reload_at=reload_at, reload=reload_pool)
    except SubscriptionRefused as exc:
        # Caught rather than allowed to propagate, so the log carries this
        # sentence instead of a traceback and the run stats still get written.
        # The exit code is what makes it a failure, and it must be non zero:
        # this run collected nothing and the morning must not be told otherwise.
        print("")
        print(f"collector: FATAL {exc}")
        # The refusal is a fact ABOUT the run, not a replacement for it.
        # Whatever the socket had already done before the server refused a
        # reconnect is still true and still has to reach the packet.
        stats = dict(getattr(exc, "run_stats", None) or {})
        stats["subscription_refused"] = True
        refused = str(exc)
        job_status.failed(f"SubscriptionRefused: {config.scrub_secrets(exc)}")
    except KeyboardInterrupt:
        print("collector: interrupted, flushing completed minutes")
        stats = {"interrupted": True}
        # Exit zero, because the minutes already folded are real and worth
        # keeping. Record the interruption, because a collector that stopped
        # at 08:10 produced a genuine file covering half the window, and
        # nothing else in the packet distinguishes that from a quiet morning.
        job_status.failed("KeyboardInterrupt: the collector was interrupted "
                          "before its stop time, so the bar file covers only "
                          "part of the premarket window")
    finally:
        builder.flush(time.time(), force=True)

    calls_during = eodhd.call_count() - calls_before
    job_status.produced("minutes written", builder.rows_written)

    late_share = (builder.late_volume / builder.total_volume * 100.0) if builder.total_volume else 0.0
    print("")
    print(f"collector: minutes written      {builder.rows_written}")
    print(f"collector: minutes not rewritten {builder.duplicates_skipped}")
    print(f"collector: trades folded        {builder.trades_seen}")
    print(f"collector: late trades dropped  {builder.late_trades} "
          f"({builder.late_volume:,.0f} shares, {late_share:.2f}% of volume)")
    if builder.duplicate_replay_skipped:
        print(f"collector: replay not rewritten {builder.duplicate_replay_skipped} "
              "(a resubscription offered a replayed minute already on disk)")
    if builder.write_failures:
        print(f"collector: WRITE FAILURES       {builder.write_failures}, last "
              f"{builder.last_write_error}. Minutes were held and retried rather "
              "than lost; a non zero count here means the disk, not the socket.")
    if builder.out_of_window_trades:
        print(f"collector: out of window        {builder.out_of_window_trades} "
              f"({builder.out_of_window_volume:,.0f} shares) refused, stamped "
              "outside this run's collection window. The subscription replays a "
              "last trade per symbol carrying its original timestamp, so some of "
              "these belong to a previous session.")
        for row in builder.out_of_window_examples[:5]:
            print(f"    {row['at'][:19]}  {row['symbol']:<10} {row['v']:,.0f} shares")
    print(f"collector: connection stats     {stats}")
    print(f"collector: REST calls during    {calls_during} (this process, client side; "
          "what the vendor meters for the socket is measured by measure_socket_cost.py)")
    if not args.verify and not args.poll and calls_during != 0:
        print("collector: WARNING this process made REST requests on the websocket "
              "path; it should make none")
    print(f"collector: file                 {bar_path()}")

    if isinstance(stats, dict) and not args.verify:
        record = {
            "finished_at": ettime.stamp(ettime.now_et()),
            "mode": "poll" if args.poll else "ws",
            "connections": stats.get("connections"),
            "reconnects": stats.get("reconnects"),
            "resubscriptions": stats.get("resubscriptions"),
            "messages": stats.get("messages"),
            # Both null on a --poll run, which has no socket and therefore no
            # status frames to have seen: the mode field beside them is what
            # says why, and null is not zero. Why they are kept at all rather
            # than only printed is argued where status_frames is declared, in
            # run_websocket.
            "status_frames": stats.get("status_frames"),
            "status_frames_seen": stats.get("status_frames_seen"),
            "trades_folded": builder.trades_seen,
            "minutes_written": builder.rows_written,
            # Refused for carrying a timestamp outside this run's window. The
            # count is the measurement of how much the subscription replay
            # contributes, and it is the number to watch if the vendor ever
            # changes that behaviour.
            "out_of_window_trades": builder.out_of_window_trades,
            "out_of_window_volume": builder.out_of_window_volume,
            "out_of_window_examples": builder.out_of_window_examples[:5],
            # Replayed minutes already on disk that a resubscription offered
            # again, and settle batches the filesystem refused. Both are zero
            # on a healthy morning and both used to be invisible: the first as
            # inflated replay_volume, the second as minutes that vanished.
            "duplicate_replay_skipped": builder.duplicate_replay_skipped,
            "write_failures": builder.write_failures,
            "last_write_error": builder.last_write_error,
            "chaos_reconnects_requested": args.chaos_reconnects,
        }
        with stats_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            handle.flush()
        print(f"collector: run stats appended to {stats_path().name}")

    if args.verify and isinstance(stats, dict) and stats.get("polls"):
        _report_verification(stats["polls"][0], stats["polls"][1], symbols)

    eodhd.print_call_report()
    if refused:
        # Says what this run actually did. The old wording was fixed text
        # asserting the run "was never subscribed and collected nothing", which
        # is true of a refusal on the FIRST connection and false of a refusal
        # on a reconnect. On 2026-08-19 it printed that sentence over 486
        # written minutes and 14,680 folded trades, which is the collector
        # lying about its own output in the one log a human reads after a
        # failure.
        if builder.rows_written or builder.trades_seen:
            print(f"collector: exiting 1. This run folded {builder.trades_seen:,} "
                  f"trade(s) into {builder.rows_written:,} minute(s) and was then "
                  "refused, so the bar file is a PARTIAL window ending where the "
                  "refusal began. It is real as far as it goes and the morning "
                  "chain must not read it as the whole window.")
        else:
            print("collector: exiting 1, this run was never subscribed and "
                  "collected nothing. The morning chain must not treat the bar "
                  "file as a window.")
        return 1
    return 0


def _poll_snapshot(symbols: list[str], label: str) -> dict[str, tuple[float, float]]:
    """Symbol to (as_of_epoch, cumulative_volume) from Live v1.

    The as-of time is the feed's own timestamp, not the wall clock. Live v1 runs
    roughly seventeen minutes behind, and using the wall clock instead is what
    made the first verification attempt meaningless.
    """
    from core import eodhd

    api = eodhd.client()
    data, error = api.live_quotes(symbols)
    if error and not data:
        print(f"collector: {label} poll failed, {error}")
        return {}
    out: dict[str, tuple[float, float]] = {}
    for symbol, row in (data or {}).items():
        try:
            out[symbol] = (float(row.get("timestamp") or 0), float(row.get("volume") or 0))
        except (TypeError, ValueError):
            continue
    if out:
        lag = ettime.now_et() - ettime.from_epoch_s(
            statistics.median(t for t, _ in out.values())
        )
        print(f"collector: {label} poll captured {len(out)} symbols, "
              f"feed is {lag.total_seconds() / 60:.1f} minutes behind the clock")
    return out


def _run_verification(symbols: list[str], builder: BarBuilder) -> dict[str, Any]:
    """Warm up, poll, collect the comparison window, poll again."""
    import datetime as dt

    warmup_stop = ettime.now_et() + dt.timedelta(minutes=VERIFY_WARMUP_MINUTES)
    print(f"collector: verification warmup until {ettime.stamp(warmup_stop)}, "
          f"so the delayed Live v1 window has already been collected")
    first = run_websocket(symbols, warmup_stop, builder)

    poll_a = _poll_snapshot(symbols, "opening")

    window_stop = ettime.now_et() + dt.timedelta(minutes=VERIFY_WINDOW_MINUTES)
    print(f"collector: comparison window until {ettime.stamp(window_stop)}")
    second = run_websocket(symbols, window_stop, builder)
    builder.flush(time.time(), force=True)

    poll_b = _poll_snapshot(symbols, "closing")

    return {
        "connections": first.get("connections", 0) + second.get("connections", 0),
        "reconnects": first.get("reconnects", 0) + second.get("reconnects", 0),
        "polls": (poll_a, poll_b),
    }


def _report_verification(
    poll_a: dict[str, tuple[float, float]],
    poll_b: dict[str, tuple[float, float]],
    symbols: list[str],
) -> None:
    """Compare collected bars against a Live v1 poll over the identical window.

    Each symbol gets its own window, taken from that symbol's own poll
    timestamps, because the feed does not lag every name by the same amount.
    Bars are summed over exactly that window and nothing else.
    """
    bars = read_bars()
    print("")
    print("verification, collected bars against a Live v1 poll of the same window")
    print(f"  {'symbol':<10} {'window':>15} {'poll delta':>12} {'bar sum':>12} "
          f"{'diff':>10} {'diff %':>9}")

    within = 0
    compared = 0
    skipped: list[str] = []
    deltas: list[float] = []

    for symbol in sorted(symbols):
        start = poll_a.get(symbol)
        end = poll_b.get(symbol)
        if not start or not end:
            skipped.append(f"{symbol} missing from a poll")
            continue
        start_epoch, start_volume = start
        end_epoch, end_volume = end
        if end_epoch <= start_epoch:
            skipped.append(f"{symbol} feed did not advance")
            continue

        poll_delta = end_volume - start_volume
        collected = bars.get(symbol, [])
        if not collected:
            skipped.append(f"{symbol} no bars collected")
            continue
        first_bar = min(b["minute_epoch"] for b in collected)
        if first_bar > start_epoch:
            skipped.append(f"{symbol} collection started after the poll window opened")
            continue

        # Bars whose whole minute lies inside the poll window.
        bar_sum = sum(
            float(b.get("v") or 0)
            for b in collected
            if start_epoch <= b["minute_epoch"] and b["minute_epoch"] + BAR_SECONDS <= end_epoch
        )
        if poll_delta <= 0:
            skipped.append(f"{symbol} poll volume did not move")
            continue

        compared += 1
        diff = bar_sum - poll_delta
        pct = diff / poll_delta * 100.0
        deltas.append(abs(pct))
        if abs(pct) <= 1.0:
            within += 1
        window = f"{(end_epoch - start_epoch) / 60:.0f}m"
        print(f"  {symbol:<10} {window:>15} {poll_delta:>12,.0f} {bar_sum:>12,.0f} "
              f"{diff:>10,.0f} {pct:>8.2f}%")

    print(f"  {within} of {compared} symbols agreed within one percent on volume")
    if deltas:
        print(f"  median absolute difference {statistics.median(deltas):.2f}%")
    for note in skipped:
        print(f"  skipped: {note}")


if __name__ == "__main__":
    raise SystemExit(job_status.run("collector", main, ok_codes=OK_CODES))
