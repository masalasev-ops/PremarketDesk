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
import json
import ssl
import statistics
import time
from pathlib import Path
from typing import Any, Iterable

import websocket

import config
import criteria
import discover
import ettime
import job_status

_CRIT = criteria.load()

BAR_SECONDS = _CRIT.integer("collector", "bar_seconds")
MAX_SUBSCRIPTIONS = _CRIT.integer("collector", "max_subscriptions")
BACKOFF_START_S = _CRIT.number("collector", "reconnect_backoff_start_s")
BACKOFF_MAX_S = _CRIT.number("collector", "reconnect_backoff_max_s")
POLL_INTERVAL_S = _CRIT.number("collector", "poll_interval_s")
AUTH_WAIT_S = _CRIT.number("collector", "auth_wait_s")
LATE_TRADE_GRACE_S = _CRIT.number("collector", "late_trade_grace_s")
VERIFY_WARMUP_MINUTES = _CRIT.number("collector", "verify_warmup_minutes")
VERIFY_WINDOW_MINUTES = _CRIT.number("collector", "verify_window_minutes")


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
    """
    path = subscriptions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "subscribed_at": ettime.stamp(ettime.now_et()),
        "requested_count": len(symbols),
        "socket_cap": MAX_SUBSCRIPTIONS,
        "symbols": sorted(symbols),
        "dropped_to_fit_cap": [row.get("symbol") for row in dropped],
    }, indent=2, sort_keys=True), encoding="utf-8")
    return path


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
    """
    path = stats_path(day)
    if not path.exists():
        return None
    totals = {"runs": 0, "connections": 0, "reconnects": 0,
              "resubscriptions": 0, "messages": 0}
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
            totals[key] += int(row.get(key) or 0)
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

    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.source = source
        self.open_bars: dict[tuple[str, int], dict[str, Any]] = {}
        self.written: set[tuple[str, int]] = set()
        self.rows_written = 0
        self.duplicates_skipped = 0
        self.trades_seen = 0
        self.late_trades = 0
        self.late_volume = 0.0
        self.total_volume = 0.0
        self._load_existing()

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
        ready = [
            key for key in self.open_bars
            if force or key[1] + BAR_SECONDS + LATE_TRADE_GRACE_S <= now_epoch
        ]
        if not ready:
            return 0
        ready.sort(key=lambda k: (k[1], k[0]))

        lines: list[str] = []
        for key in ready:
            bar = self.open_bars.pop(key)
            if key in self.written:
                self.duplicates_skipped += 1
                continue
            bar["vwap"] = round(bar["pv"] / bar["v"], 6) if bar["v"] else None
            bar["minute_et"] = ettime.stamp(ettime.from_epoch_s(bar["minute_epoch"]))
            lines.append(json.dumps(bar, separators=(",", ":")))
            self.written.add(key)

        if lines:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # One write and one flush per bar, so the file never holds a
            # buffered partial line while scan.py reads it at 08:45. The
            # handle is opened per settle batch and closed again, which also
            # flushes through to the OS on every batch.
            with self.path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")
                    handle.flush()
            self.rows_written += len(lines)
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
        if symbol:
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


def snapshot_bars(day: str, destination) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Copy the live bar file aside, then parse the copy.

    The collector appends until 09:25 and scan reads at 08:45, so the read
    overlaps the write. Copying first means the parse works on bytes that
    stopped moving, and the copy in runs/<date>/ records exactly what the
    packet saw.
    """
    import shutil

    source = bar_path(day)
    stats: dict[str, Any]
    if not source.exists():
        return {}, {
            "bars_total": 0, "last_bar_epoch": None, "last_bar_et": None,
            "partial_line_discarded": False, "bad_lines_skipped": 0,
            "source_missing": True,
        }
    shutil.copyfile(source, destination)
    bars, stats = read_bars_file(destination)
    stats["source_missing"] = False
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


def run_websocket(
    symbols: list[str], stop_at, builder: BarBuilder, chaos_reconnects: int = 0
) -> dict[str, Any]:
    """Collect until stop_at. chaos_reconnects deliberately drops the socket
    that many times, spread across the run, so the cost of a flaky morning
    (reconnect plus full resubscribe) can be measured rather than assumed."""
    backoff = BACKOFF_START_S
    connections = 0
    reconnects = 0
    messages = 0
    last_status = 0.0

    chaos_remaining = max(0, int(chaos_reconnects))
    chaos_next: float | None = None
    if chaos_remaining:
        window_s = max((stop_at - ettime.now_et()).total_seconds(), 60.0)
        chaos_interval = window_s / (chaos_remaining + 1)
        chaos_next = time.time() + chaos_interval

    while ettime.now_et() < stop_at:
        socket = None
        try:
            socket = _connect(symbols)
            connections += 1
            print(f"collector: connected, subscribed to {len(symbols)} symbols")
            backoff = BACKOFF_START_S

            while ettime.now_et() < stop_at:
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
                    _handle_message(raw, builder)

                now = time.time()
                builder.flush(now)
                if now - last_status >= 60:
                    last_status = now
                    print(
                        f"collector: {ettime.hhmm(ettime.now_et())} ET  "
                        f"trades {builder.trades_seen}  minutes written {builder.rows_written}  "
                        f"open bars {len(builder.open_bars)}"
                    )
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
        "resubscriptions": connections,
        "messages": messages,
    }


def _handle_message(raw: str, builder: BarBuilder) -> None:
    try:
        message = json.loads(raw)
    except ValueError:
        return
    if not isinstance(message, dict):
        return
    if "s" not in message or "p" not in message:
        # Authorisation and status frames land here and are simply noted.
        if message.get("status_code") and message.get("status_code") != 200:
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

    builder.add_trade(
        symbol=_full(str(message["s"])),
        price=price,
        volume=volume,
        epoch_s=epoch_s,
        dark_pool=bool(message.get("dp")),
        market_status=message.get("ms"),
    )


# -------------------------------------------------------------- poll fallback

def run_poll(symbols: list[str], stop_at, builder: BarBuilder) -> dict[str, Any]:
    """Live v1 polling for a day the socket is down.

    This is a degraded source and it says so. A poll gives a cumulative day
    volume and a last price, so each bar carries the volume that accumulated
    since the previous poll and a single price for open, high, low and close.
    Every row is stamped src=poll, and any premarket high derived from it
    understates the real one.
    """
    import eodhd

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

def verify_against_intraday(day: str, quiet: bool = False) -> dict[str, Any] | None:
    """Compare a collected day against EODHD 1m intraday, minute for minute.

    This is the definitive volume check: same minutes, same units, no delayed
    window arithmetic. Intraday for the current day is published a few hours
    behind, so this runs in the evening, and the nightly backfill calls it for
    the record. Returns the summary, or None when intraday has nothing yet.
    """
    import statistics as stats

    import eodhd

    api = eodhd.client()
    bars = read_bars(day)
    if not bars:
        print(f"collector: no collected bars for {day}, nothing to verify")
        return None

    results: list[tuple[str, int, float, float, float]] = []
    unavailable = 0
    for symbol in sorted(bars):
        mine = {b["minute_epoch"]: b for b in bars[symbol]}
        low, high = min(mine), max(mine)
        rows, error = api.intraday(
            symbol, ettime.from_epoch_s(low), ettime.from_epoch_s(high + BAR_SECONDS), "1m"
        )
        if error or not rows:
            unavailable += 1
            continue
        theirs = {int(r["timestamp"]): r for r in rows if r.get("timestamp") is not None}
        common = sorted(set(mine) & set(theirs))
        if not common:
            unavailable += 1
            continue
        my_volume = sum(float(mine[t]["v"]) for t in common)
        their_volume = sum(float(theirs[t].get("volume") or 0) for t in common)
        if their_volume <= 0:
            continue
        pct = (my_volume - their_volume) / their_volume * 100.0
        results.append((symbol, len(common), my_volume, their_volume, pct))

    if not results:
        print(
            f"collector: intraday has no bars yet for {day} "
            f"({unavailable} symbols empty). It is published a few hours behind, try later."
        )
        return None

    within = sum(1 for r in results if abs(r[4]) <= 1.0)
    median_abs = stats.median(abs(r[4]) for r in results)
    if not quiet:
        print("")
        print(f"verification against EODHD 1m intraday for {day}, identical minutes only")
        print(f"  {'symbol':<10} {'mins':>5} {'collected':>13} {'intraday':>13} {'diff %':>9}")
        for symbol, minutes, mine_v, theirs_v, pct in results:
            print(f"  {symbol:<10} {minutes:>5} {mine_v:>13,.0f} {theirs_v:>13,.0f} {pct:>8.2f}%")
        print(f"  {within} of {len(results)} symbols within one percent on volume")
        print(f"  median absolute difference {median_abs:.3f}%")
        if unavailable:
            print(f"  {unavailable} symbols had no intraday bars to compare")
    return {
        "day": day,
        "compared": len(results),
        "within_one_percent": within,
        "median_abs_pct": median_abs,
        "unavailable": unavailable,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect the premarket price path.")
    parser.add_argument("--poll", action="store_true",
                        help="Fall back to Live v1 polling for a day the socket is down.")
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
    args = parser.parse_args(argv)

    if args.verify_intraday:
        day = ettime.today_str() if args.verify_intraday == "today" else args.verify_intraday
        result = verify_against_intraday(day)
        import eodhd as _eodhd

        _eodhd.print_call_report()
        return 0 if result else 1

    config.ensure_dirs()
    import eodhd  # imported here so the atexit call report covers every mode

    watchlist = discover.load_watchlist()
    if watchlist.get("missing"):
        print(f"collector: {config.WATCHLIST_PATH} is missing. Run discover.py first.")
        return 1

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

    builder = BarBuilder(bar_path(), source="poll" if args.poll else "ws")

    # Written before the socket opens, so the 08:45 packet can name a symbol
    # that was subscribed and stayed silent. Monday is the first morning at
    # fifty subscriptions and the throughput has only ever been measured at
    # thirty eight, so this is the run that has to be able to say which names
    # the socket actually served.
    written_to = write_subscriptions(symbols, dropped)
    print(f"collector: subscription list written to {written_to.name}")

    calls_before = eodhd.call_count()
    try:
        if args.verify:
            stats = _run_verification(symbols, builder)
        elif args.poll:
            stats = run_poll(symbols, stop_at, builder)
        else:
            stats = run_websocket(symbols, stop_at, builder,
                                  chaos_reconnects=args.chaos_reconnects)
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
            "trades_folded": builder.trades_seen,
            "minutes_written": builder.rows_written,
            "chaos_reconnects_requested": args.chaos_reconnects,
        }
        with stats_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            handle.flush()
        print(f"collector: run stats appended to {stats_path().name}")

    if args.verify and isinstance(stats, dict) and stats.get("polls"):
        _report_verification(stats["polls"][0], stats["polls"][1], symbols)

    eodhd.print_call_report()
    return 0


def _poll_snapshot(symbols: list[str], label: str) -> dict[str, tuple[float, float]]:
    """Symbol to (as_of_epoch, cumulative_volume) from Live v1.

    The as-of time is the feed's own timestamp, not the wall clock. Live v1 runs
    roughly seventeen minutes behind, and using the wall clock instead is what
    made the first verification attempt meaningless.
    """
    import eodhd

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
    raise SystemExit(job_status.run("collector", main))
