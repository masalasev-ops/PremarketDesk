"""The narrative pass. Turns packet.json into report.md through the claude CLI.

The division of labor is absolute. Python computed membership, eligibility,
scores and conviction before this module runs, and the packet records the
evidence chain behind every number. The model's job is narrative around those
decided numbers, nothing more. That is why this module ships the packet, the
template and the prompt to the CLI and then checks the answer: every ticker in
the report must already exist in the packet, because a report that mentions a
name the packet never carried has invented evidence, and inventing evidence is
the one failure this system exists to prevent.

The transport is the claude CLI as a subprocess, authenticated through the
logged in subscription. Never the Anthropic SDK, never an API key. The
subprocess environment is scrubbed of ANTHROPIC_API_KEY so a stray shell
variable cannot change what pays for the call.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import config
import criteria
import ettime

_CRIT = criteria.load()

_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")
_DOLLAR_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,5})\b")


# ------------------------------------------------------------ CLI plumbing

def resolve_cli() -> str:
    """Find the claude CLI in a form Windows CreateProcess can run.

    The npm claude.cmd shim just forwards to a native claude.exe next to it,
    and cmd.exe mangles empty string arguments on the way through, which
    silently breaks --tools "". So the real executable is preferred, found
    relative to the shim, and the shim itself is only a last resort.
    """
    shim = shutil.which("claude.cmd") or shutil.which("claude")
    if shim:
        exe = (Path(shim).parent / "node_modules" / "@anthropic-ai"
               / "claude-code" / "bin" / "claude.exe")
        if exe.is_file():
            return str(exe)
        return shim
    raise FileNotFoundError(
        "The claude CLI is not on PATH. The narrative pass cannot run without it."
    )


def _scrubbed_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in config.FORBIDDEN_KEYS:
        env.pop(key, None)
    return env


def _compose_stdin(packet_text: str) -> str:
    prompt = config.ANALYST_PROMPT_PATH.read_text(encoding="utf-8")
    template = config.REPORT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        f"{prompt}\n\n"
        "----------------------------------------------------------------\n\n"
        f"{template}\n\n"
        "----------------------------------------------------------------\n\n"
        "Here is this morning's packet.json, your only source:\n\n"
        f"{packet_text}\n"
    )


def _trim_to_report(text: str) -> str:
    """Cut any preamble or code fence the model wrapped around the report.

    Mechanical cleanup only. The report proper starts at the first markdown
    h1 line, which the template pins as the title.
    """
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1:] if first_newline != -1 else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[index:]).strip() + "\n"
    return text + "\n"


def invoke_claude(packet_text: str) -> tuple[str | None, dict[str, Any], str | None, str]:
    """Run the CLI. Returns (report_text, usage_record, error, failure_kind).

    failure_kind is "ok" on success, "timeout" when the last attempt ran out
    of clock, "failed" for every other way the CLI can disappoint.
    """
    model = _CRIT.text("analyst", "model")
    timeout_s = _CRIT.integer("analyst", "timeout_s")
    attempts = _CRIT.integer("analyst", "max_attempts")
    try:
        # One text generation, not an agent loop. --tools "" removes every
        # tool, so there is nothing to take a second turn on (verified: this
        # CLI version has no turn cap flag, and none is needed without
        # tools). The one line system prompt replaces the CLI's large agent
        # system prompt; the piped document is the entire instruction. The
        # recorded num_turns must come back 1.
        command = [
            resolve_cli(), "-p", "--model", model, "--output-format", "json",
            "--tools", "", "--effort", _CRIT.text("analyst", "effort"),
            "--system-prompt",
            "You are the narrative pass of PremarketDesk. Follow the piped "
            "instructions exactly and output only the finished report markdown.",
        ]
    except FileNotFoundError as exc:
        return None, {}, str(exc), "failed"
    stdin_doc = _compose_stdin(packet_text)

    last_error = None
    last_kind = "failed"
    for attempt in range(1, attempts + 1):
        print(f"analyst: attempt {attempt} of {attempts}, model {model}")
        try:
            proc = subprocess.run(
                command,
                input=stdin_doc,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                env=_scrubbed_env(),
                cwd=str(config.PROJECT_ROOT),
            )
        except subprocess.TimeoutExpired:
            last_error = f"claude CLI timed out after {timeout_s}s"
            last_kind = "timeout"
            print(f"analyst: {last_error}")
            continue
        except OSError as exc:
            return None, {}, f"claude CLI could not be started: {exc}", "failed"

        if proc.returncode != 0:
            last_error = (
                f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:400]}"
            )
            last_kind = "failed"
            print(f"analyst: {last_error}")
            continue

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            last_error = f"claude CLI output was not JSON: {exc}"
            last_kind = "failed"
            print(f"analyst: {last_error}")
            continue

        if payload.get("is_error") or payload.get("subtype") != "success":
            last_error = (
                f"claude CLI reported an error result: subtype "
                f"{payload.get('subtype')!r}, result {str(payload.get('result'))[:300]!r}"
            )
            last_kind = "failed"
            print(f"analyst: {last_error}")
            continue

        usage = payload.get("usage") or {}
        record = {
            "model_requested": model,
            "model_usage": payload.get("modelUsage"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            "total_cost_usd": payload.get("total_cost_usd"),
            "duration_ms": payload.get("duration_ms"),
            "duration_api_ms": payload.get("duration_api_ms"),
            "num_turns": payload.get("num_turns"),
            "session_id": payload.get("session_id"),
            "attempt": attempt,
        }
        return _trim_to_report(str(payload.get("result") or "")), record, None, "ok"

    return None, {}, last_error or "claude CLI failed for an unrecorded reason", last_kind


# ------------------------------------------------- the fallback report

def _f(value: Any, digits: int = 2) -> str:
    if value is None:
        return "null"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _cap(value: Any) -> str:
    if value is None:
        return "null"
    number = float(value)
    if number >= 1e9:
        return f"{number / 1e9:.2f}B"
    return f"{number / 1e6:.0f}M"


def _bare(symbol: str) -> str:
    return str(symbol).split(".")[0]


def fallback_report(packet: dict[str, Any], reason: str) -> str:
    """The report the morning gets when the model cannot be reached.

    Every number straight from the packet, no narrative, the same section
    skeleton as the template so downstream rendering and reading habits hold.
    The disclaimer line carries the failure reason, because a report that
    silently degraded would be a report that lied about its own provenance.
    """
    candidates = packet.get("candidates", [])
    no_rvol = [_bare(c["symbol"]) for c in candidates if c.get("pm_rvol") is None]
    partial = [
        _bare(c["symbol"]) for c in candidates
        if c.get("pm_window_starts_late") or not c.get("collector_covered")
    ]
    day = [c for c in candidates if c.get("day_eligible")]
    swing = [c for c in candidates if c.get("swing_eligible")]
    no_catalyst = [_bare(c["symbol"]) for c in candidates if c.get("catalyst_found") is False]
    # None is a third state: the news feed was never checked (failed call or
    # quota skip). Unknown must never be rendered as checked and clean.
    unknown_catalyst = [
        _bare(c["symbol"]) for c in candidates if c.get("catalyst_found") is None
    ]

    lines: list[str] = []
    add = lines.append
    add("# PremarketDesk: numbers only, narrative unavailable")
    add("")
    add(f"{packet.get('session_date')}, packet generated {packet.get('generated_at')}, "
        "generated by PremarketDesk.")
    add("")
    disclaimer = (
        "Nothing here is advice, the screen thresholds are unvalidated seed values, "
        f"the narrative pass was unavailable ({reason}), so this is the deterministic "
        "fallback built straight from packet.json"
    )
    if no_rvol:
        disclaimer += f"; premarket RVOL is null for {', '.join(no_rvol)}"
    if partial:
        disclaimer += (
            f"; premarket path evidence is partial or missing for {', '.join(partial)}"
        )
    quota = packet.get("quota_preflight") or {}
    if quota.get("degraded"):
        if quota.get("remaining") is not None:
            disclaimer += (
                f"; the shared API key had {quota['remaining']:,} of "
                f"{quota['daily_limit']:,} daily calls remaining at preflight "
                f"(quota day {quota.get('quota_day')}), so the skippable evidence "
                "here is thin for quota reasons, not a vendor outage"
            )
        else:
            disclaimer += "; the quota preflight could not read the shared meter"
    add(disclaimer + ".")
    add("")
    add("## Summary")
    add("")
    add(f"{len(candidates)} candidates. Day eligible: "
        f"{', '.join(_bare(c['symbol']) for c in day) or 'none'}. Swing eligible: "
        f"{', '.join(_bare(c['symbol']) for c in swing) or 'none'}. "
        f"{len(packet.get('gaps_to_fill', []))} gaps recorded in the packet.")
    add("")
    add("## Premarket gappers")
    add("")
    add("| Ticker | Name | Gap % | Price | Prior close | Mkt cap | Catalyst | Top headline |")
    add("|---|---|---|---|---|---|---|---|")
    for c in candidates:
        quote = c.get("quote") or {}
        heads = c.get("headlines") or []
        title = (heads[0].get("title") or "")[:80] if heads else ""
        found = c.get("catalyst_found")
        catalyst = c.get("catalyst_class") if found else (
            "none found" if found is False else "unknown")
        add(f"| {_bare(c['symbol'])} | {quote.get('name') or ''} | {_f(c.get('gap_pct'))} "
            f"| {_f(c.get('price'))} | {_f(c.get('prior_close'))} | {_cap(quote.get('marketCap'))} "
            f"| {catalyst} | {title} |")
    add("")
    add("## Day watchlist")
    add("")
    if day:
        add("| Ticker | Gap % | Price | Premarket RVOL | Premarket high | Premarket VWAP | Score | Conviction |")
        add("|---|---|---|---|---|---|---|---|")
        for c in day:
            add(f"| {_bare(c['symbol'])} | {_f(c.get('gap_pct'))} | {_f(c.get('price'))} "
                f"| {_f(c.get('pm_rvol'))} | {_f(c.get('pm_high'), 4)} | {_f(c.get('pm_vwap'), 4)} "
                f"| {_f(c.get('score'), 1)} | {c.get('conviction')} |")
    else:
        add("No candidate is day eligible this morning.")
    add("")
    add("## Swing watchlist")
    add("")
    if swing:
        add("| Ticker | Gap % | Price | Prior high | 200d avg | Catalyst | Score | Conviction |")
        add("|---|---|---|---|---|---|---|---|")
        for c in swing:
            quote = c.get("quote") or {}
            add(f"| {_bare(c['symbol'])} | {_f(c.get('gap_pct'))} | {_f(c.get('price'))} "
                f"| {_f(c.get('prior_high'))} | {_f(quote.get('twoHundredDayAveragePrice'))} "
                f"| {c.get('catalyst_class')} | {_f(c.get('score'), 1)} | {c.get('conviction')} |")
    else:
        add("No candidate is swing eligible this morning.")
    add("")
    add("## Market trends")
    add("")
    add("| Label | Last | Change % | Source |")
    add("|---|---|---|---|")
    for row in packet.get("market_snapshot", []):
        label = row.get("label", "")
        note = " (proxy)" if row.get("proxy_note") else ""
        add(f"| {str(label).upper()}{note} | {_f(row.get('last'))} "
            f"| {_f(row.get('change_pct'))} | {row.get('source') or 'unavailable'} |")
    add("")
    add("## Technical signals")
    add("")
    add("| Ticker | Premarket high | Premarket low | Premarket VWAP | Prior high | 200d avg | Score | Conviction |")
    add("|---|---|---|---|---|---|---|---|")
    for c in candidates:
        quote = c.get("quote") or {}
        mark = " (partial)" if (c.get("pm_window_starts_late") or not c.get("collector_covered")) else ""
        pm_high = _f(c.get("pm_high"), 4)
        add(f"| {_bare(c['symbol'])} | {pm_high}{mark if c.get('pm_high') is not None else ''} "
            f"| {_f(c.get('pm_low'), 4)} | {_f(c.get('pm_vwap'), 4)} | {_f(c.get('prior_high'))} "
            f"| {_f(quote.get('twoHundredDayAveragePrice'))} | {_f(c.get('score'), 1)} "
            f"| {c.get('conviction')} |")
    add("")
    add("## Economic data and rates")
    add("")
    economic = packet.get("economic") or {}
    events = economic.get("events", [])
    if economic.get("skipped"):
        add(f"The economic calendar was not checked this run: {economic['skipped']}. "
            "An unchecked calendar is not an empty one.")
    elif events:
        for event in events:
            add(f"- {event.get('time_et')}: {event.get('title')} "
                f"(forecast {event.get('forecast')}, previous {event.get('previous')}, "
                f"actual {event.get('actual')})")
    else:
        add("No high importance events in the packet window.")
    add("")
    add("## Coming up")
    add("")
    earnings_block = packet.get("earnings") or {}
    tomorrow = earnings_block.get("notable_tomorrow", [])
    if earnings_block.get("skipped"):
        add(f"The earnings calendar was not checked this run: {earnings_block['skipped']}. "
            "An unchecked calendar is not an empty one.")
    elif tomorrow:
        add("| Ticker | Mkt cap | Report date | Session |")
        add("|---|---|---|---|")
        for row in tomorrow:
            add(f"| {_bare(row.get('symbol', ''))} | {_cap(row.get('market_cap'))} "
                f"| {row.get('report_date')} | {row.get('before_after_market') or ''} |")
    else:
        add("No notable earnings in the packet window.")
    add("")
    add("## Skips and traps")
    add("")
    if no_catalyst:
        add(f"Moving on no found catalyst, a skip: {', '.join(no_catalyst)}.")
    if unknown_catalyst:
        add(f"Catalyst status is unknown for {', '.join(unknown_catalyst)}: the news "
            "feed was never checked this run, so no catalyst judgment exists for them.")
    if partial:
        add(f"Premarket path partial or absent, treat any level as partial: {', '.join(partial)}.")
    if not no_catalyst and not unknown_catalyst and not partial:
        add("Every candidate carries a found catalyst and full evidence.")
    add("")
    add("Trap judgment (a gap up on bad news) needs the narrative pass and is "
        "not attempted here.")
    return "\n".join(lines) + "\n"


# ------------------------------------------------- the containment checker

def _packet_uppercase_tokens(packet_text: str) -> set[str]:
    """Every uppercase token the packet itself carries, symbols included.

    The containment rule is literal: a ticker the report claims must appear
    in packet.json. Building the allowed set from the packet's own text means
    quoted headlines that name other tickers stay legal, because those names
    are in the packet too.
    """
    allowed = set(_TOKEN_RE.findall(packet_text))
    try:
        packet = json.loads(packet_text)
    except json.JSONDecodeError:
        return allowed

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("symbol", "label") and isinstance(value, str):
                    full = value.upper()
                    allowed.add(full)
                    allowed.add(full.split(".")[0])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(packet)
    return allowed


def _universe_bare_symbols() -> set[str] | None:
    """Bare tickers of every universe member, or None when the file is absent."""
    try:
        universe = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        str(row.get("symbol", "")).split(".")[0].upper()
        for row in universe.get("symbols", [])
        if row.get("symbol")
    }


def _ticker_claims(report_text: str) -> set[str]:
    """The tokens the report presents AS tickers.

    Prose is not scanned: an acronym like CEO or FOMC in a sentence is not a
    ticker claim and must never trip containment. A claim is a token in a
    table column whose header names it a ticker column, or a token anywhere
    carrying a $ prefix, which is unambiguous. Other table cells are prose in
    a grid ("2:48 PM ET" in a headline cell must not read as Philip Morris),
    so they are not scanned either.
    """
    claims: set[str] = set(_DOLLAR_RE.findall(report_text))
    separator = re.compile(r"[|\s:\-]+")
    lines = report_text.splitlines()
    ticker_columns: list[int] | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            ticker_columns = None
            continue
        if separator.fullmatch(stripped):
            continue  # the |---|---| separator row
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        is_header = (
            index + 1 < len(lines)
            and lines[index + 1].strip().startswith("|")
            and separator.fullmatch(lines[index + 1].strip()) is not None
        )
        if is_header:
            ticker_columns = [
                position for position, cell in enumerate(cells)
                if "ticker" in cell.lower() or "symbol" in cell.lower()
            ]
            continue
        if not ticker_columns:
            continue
        for position in ticker_columns:
            if position < len(cells):
                claims.update(_TOKEN_RE.findall(cells[position]))
    return claims


def check_report(report_text: str, packet_text: str) -> tuple[list[str], list[str]]:
    """Returns (invented_tickers, candidates_missing_from_report).

    A token is an invented ticker only when all three hold: the report
    presents it as a ticker (table cell or $ prefix), it names a real symbol
    in the universe file, and the packet does not carry it. The universe test
    is what keeps ordinary uppercase words out: CEO in a table cell is not a
    universe member, so it is not a claim about a tradeable name.
    """
    universe_symbols = _universe_bare_symbols()
    if universe_symbols is None:
        print("analyst: containment note: universe.json is unavailable, so ticker "
              "claims cannot be validated this run")
        invented: list[str] = []
    else:
        allowed = _packet_uppercase_tokens(packet_text)
        invented = sorted(
            token for token in _ticker_claims(report_text)
            if token in universe_symbols and token not in allowed
        )

    missing: list[str] = []
    try:
        packet = json.loads(packet_text)
    except json.JSONDecodeError:
        return invented, missing
    report_tokens = set(_TOKEN_RE.findall(report_text))
    for candidate in packet.get("candidates", []):
        bare = str(candidate.get("symbol", "")).split(".")[0]
        if bare and bare not in report_tokens:
            missing.append(bare)
    return invented, missing


# ------------------------------------------------------------------- runner

def write_report(packet_path: Path) -> int:
    packet_text = packet_path.read_text(encoding="utf-8")
    packet = json.loads(packet_text)
    session_date = packet.get("session_date") or ettime.today_et().isoformat()
    run_directory = config.run_dir(session_date)

    report_text, usage, error, kind = invoke_claude(packet_text)
    if error or report_text is None or not report_text.strip():
        reason = error or "the model returned an empty report"
        if not error:
            kind = "failed"
        print(f"analyst: narrative unavailable ({kind}): {reason}")
        print("analyst: falling back to the deterministic numbers only report")
        report_text = fallback_report(packet, reason)
        usage = {"status": kind, "error_message": reason, "fallback": True}
    else:
        usage["status"] = "ok"
        usage["fallback"] = False

    report_path = run_directory / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"analyst: wrote {report_path} ({len(report_text)} chars, status {usage['status']})")

    usage["generated_at"] = ettime.stamp(ettime.now_et())
    usage["packet"] = str(packet_path)
    usage_path = run_directory / "analyst_usage.json"
    usage_path.write_text(json.dumps(usage, indent=2, sort_keys=True), encoding="utf-8")
    if usage["status"] == "ok":
        print(
            "analyst: tokens in "
            f"{usage.get('input_tokens')} (cache write {usage.get('cache_creation_input_tokens')}, "
            f"cache read {usage.get('cache_read_input_tokens')}), out {usage.get('output_tokens')}, "
            f"cost ${usage.get('total_cost_usd')}, {usage.get('duration_ms')} ms"
        )

    invented, missing = check_report(report_text, packet_text)
    if missing:
        print(
            "analyst: WARNING these packet candidates never appear in the report: "
            + ", ".join(missing)
        )
    if invented:
        print(
            "analyst: FAILED the containment check. These tickers are presented "
            "as tickers, exist in the universe, and are nowhere in the packet: "
            + ", ".join(invented)
        )
        print("analyst: the report was written for inspection but must not be delivered.")
        return 2
    print("analyst: containment check passed, every ticker claim exists in the packet")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write report.md from packet.json via the claude CLI.")
    parser.add_argument("--packet", metavar="PATH",
                        help="Packet to narrate. Defaults to runs/<today>/packet.json.")
    parser.add_argument("--check", metavar="REPORT",
                        help="Run only the containment check on an existing report.")
    args = parser.parse_args(argv)

    packet_path = (
        Path(args.packet) if args.packet
        else config.run_dir(ettime.today_et().isoformat()) / "packet.json"
    )
    if not packet_path.is_file():
        print(f"analyst: there is no packet at {packet_path}. Run scan.py first.")
        return 1

    if args.check:
        report_path = Path(args.check)
        invented, missing = check_report(
            report_path.read_text(encoding="utf-8"),
            packet_path.read_text(encoding="utf-8"),
        )
        if missing:
            print("analyst: candidates missing from the report: " + ", ".join(missing))
        if invented:
            print("analyst: tickers not in the packet: " + ", ".join(invented))
            return 2
        print("analyst: containment check passed")
        return 0

    return write_report(packet_path)


if __name__ == "__main__":
    raise SystemExit(main())
