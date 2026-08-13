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

# Uppercase tokens in the report that are ordinary finance or English usage,
# not tickers, and so are exempt from the containment check. Anything else
# uppercase must appear somewhere in the packet.
_NOT_TICKERS = frozenset({
    "AI", "AM", "PM", "ET", "EST", "EDT", "UTC",
    "EPS", "CEO", "CFO", "COO", "CTO", "PR", "IPO", "SEC", "FDA", "FED",
    "FOMC", "CPI", "PPI", "PCE", "GDP", "ISM", "PMI", "NFP",
    "VWAP", "RVOL", "SMA", "EMA", "ATR", "RSI", "MACD",
    "ETF", "ETFS", "ETN", "REIT", "ADR",
    "NYSE", "NASDAQ", "OTC", "US", "USA", "USD", "EU", "UK",
    "WTI", "DXY", "OPEC", "EIA", "DOE",
    "YOY", "QOQ", "MOM", "FY", "NA", "OK", "VS", "TBD",
    "AND", "THE", "NOT", "FOR", "ALL", "NO", "YES", "TOP", "NEW", "PT",
    "MA", "LLC", "INC", "CORP", "PLC",
})

_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")


# ------------------------------------------------------------ CLI plumbing

def resolve_cli() -> str:
    """Find the claude CLI in a form Windows CreateProcess can run.

    On this machine the npm shim exists as claude.ps1, claude.cmd and a bare
    claude. subprocess can run the .cmd directly, which was verified by probe,
    so that form is preferred and the bare name is the fallback.
    """
    for name in ("claude.cmd", "claude"):
        found = shutil.which(name)
        if found:
            return found
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


def invoke_claude(packet_text: str) -> tuple[str | None, dict[str, Any], str | None]:
    """Run the CLI. Returns (report_text, usage_record, error)."""
    model = _CRIT.text("analyst", "model")
    timeout_s = _CRIT.integer("analyst", "timeout_s")
    attempts = _CRIT.integer("analyst", "max_attempts")
    command = [resolve_cli(), "-p", "--model", model, "--output-format", "json"]
    stdin_doc = _compose_stdin(packet_text)

    last_error = None
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
            print(f"analyst: {last_error}")
            continue
        except OSError as exc:
            return None, {}, f"claude CLI could not be started: {exc}"

        if proc.returncode != 0:
            last_error = (
                f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:400]}"
            )
            print(f"analyst: {last_error}")
            continue

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            last_error = f"claude CLI output was not JSON: {exc}"
            print(f"analyst: {last_error}")
            continue

        if payload.get("is_error") or payload.get("subtype") != "success":
            last_error = (
                f"claude CLI reported an error result: subtype "
                f"{payload.get('subtype')!r}, result {str(payload.get('result'))[:300]!r}"
            )
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
        return _trim_to_report(str(payload.get("result") or "")), record, None

    return None, {}, last_error or "claude CLI failed for an unrecorded reason"


# ------------------------------------------------- the containment checker

def _packet_uppercase_tokens(packet_text: str) -> set[str]:
    """Every uppercase token the packet itself carries, symbols included.

    The containment rule is literal: a ticker the report mentions must appear
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


def check_report(report_text: str, packet_text: str) -> tuple[list[str], list[str]]:
    """Returns (invented_tickers, candidates_missing_from_report)."""
    allowed = _packet_uppercase_tokens(packet_text)
    report_tokens = set(_TOKEN_RE.findall(report_text))
    invented = sorted(
        token for token in report_tokens
        if token not in allowed and token not in _NOT_TICKERS
    )

    missing: list[str] = []
    try:
        packet = json.loads(packet_text)
    except json.JSONDecodeError:
        return invented, missing
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

    report_text, usage, error = invoke_claude(packet_text)
    if error or report_text is None or not report_text.strip():
        print(f"analyst: FAILED: {error or 'the model returned an empty report'}")
        return 1

    report_path = run_directory / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"analyst: wrote {report_path} ({len(report_text)} chars)")

    usage["generated_at"] = ettime.stamp(ettime.now_et())
    usage["packet"] = str(packet_path)
    usage_path = run_directory / "analyst_usage.json"
    usage_path.write_text(json.dumps(usage, indent=2, sort_keys=True), encoding="utf-8")
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
            "analyst: FAILED the containment check. These tickers appear in the "
            "report but nowhere in the packet: " + ", ".join(invented)
        )
        print("analyst: the report was written for inspection but must not be delivered.")
        return 2

    print("analyst: containment check passed, every report ticker exists in the packet")
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
