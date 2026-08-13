"""Configuration and paths for PremarketDesk.

Reads a KEY=VALUE .env file with a tiny hand rolled parser, so the project
keeps its dependency list down to requests, websocket-client and markdown.

Precedence is deliberate. A real process environment variable always beats
the value in .env, which lets a scheduled task or a shell session override a
setting without editing the file.

This module never reads and never sets ANTHROPIC_API_KEY. The narrative pass
in analyst.py shells out to the claude CLI and authenticates through the
logged in subscription, so no API key belongs anywhere in this project.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The one environment variable this project refuses to touch.
FORBIDDEN_KEYS = frozenset({"ANTHROPIC_API_KEY"})

PROJECT_ROOT = Path(__file__).resolve().parent

ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
CRITERIA_PATH = PROJECT_ROOT / "CRITERIA.md"

DATA_DIR = PROJECT_ROOT / "data"
PREMARKET_DIR = DATA_DIR / "premarket"
RUNS_DIR = PROJECT_ROOT / "runs"
LOGS_DIR = PROJECT_ROOT / "logs"

DB_PATH = DATA_DIR / "premarketdesk.db"
UNIVERSE_PATH = DATA_DIR / "universe.json"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"

REPORT_TEMPLATE_PATH = PROJECT_ROOT / "REPORT_TEMPLATE.md"
ANALYST_PROMPT_PATH = PROJECT_ROOT / "prompt_analyst.md"

_ALL_DIRS = (DATA_DIR, PREMARKET_DIR, RUNS_DIR, LOGS_DIR)

# Parsed .env contents, filled lazily by load_env().
_env_file_cache: dict[str, str] | None = None


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or a forbidden one is asked for."""


def parse_env_text(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines into a dict.

    Rules, kept small on purpose:
      blank lines and lines whose first non space character is # are skipped
      an optional leading "export " is allowed and ignored
      the split happens at the first = only, so values may contain =
      a value wrapped in matching single or double quotes is unwrapped
      an unquoted value runs to end of line, so a token containing # survives
      a duplicated key means the last one in the file wins
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.lstrip("﻿").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load_env(path: Path | None = None, refresh: bool = False) -> dict[str, str]:
    """Load and cache the .env file. A missing file is not an error."""
    global _env_file_cache
    if _env_file_cache is not None and not refresh and path is None:
        return _env_file_cache

    target = path or ENV_PATH
    parsed: dict[str, str] = {}
    if target.exists():
        parsed = parse_env_text(target.read_text(encoding="utf-8"))

    dropped = sorted(k for k in parsed if k.upper() in FORBIDDEN_KEYS)
    for key in dropped:
        parsed.pop(key)
        print(
            f"config: ignoring {key} found in {target.name}. "
            "This project authenticates the narrative pass through the claude CLI "
            "subscription and must not carry an API key.",
            file=sys.stderr,
        )

    if path is None:
        _env_file_cache = parsed
    return parsed


def get(name: str, default: str | None = None) -> str | None:
    """Return a setting. Process environment first, then .env, then default."""
    if name.upper() in FORBIDDEN_KEYS:
        raise ConfigError(
            f"{name} must not be read by this project. The narrative pass uses the "
            "claude CLI subscription, not an API key."
        )
    from_process = os.environ.get(name)
    if from_process is not None and from_process.strip() != "":
        return from_process.strip()
    from_file = load_env().get(name)
    if from_file is not None and from_file.strip() != "":
        return from_file.strip()
    return default


def require(name: str) -> str:
    """Return a setting or raise a ConfigError naming the file to fix."""
    value = get(name)
    if not value:
        raise ConfigError(
            f"{name} is not set. Add it to {ENV_PATH} or set it in the environment. "
            f"See {ENV_EXAMPLE_PATH.name} for the expected shape."
        )
    return value


def eodhd_token() -> str:
    """The EODHD All-In-One token. The only market data credential we hold."""
    return require("EODHD_API_TOKEN")


def resend_api_key() -> str | None:
    """Resend key, or None when delivery should be skipped."""
    return get("RESEND_API_KEY")


def email_to() -> list[str]:
    """Recipient list, empty when delivery should be skipped."""
    raw = get("EMAIL_TO") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def ensure_dirs() -> None:
    """Create the working directories. Safe to call on every run."""
    for directory in _ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def run_dir(date_str: str) -> Path:
    """runs/YYYY-MM-DD, created on demand."""
    target = RUNS_DIR / date_str
    target.mkdir(parents=True, exist_ok=True)
    return target


def _self_check() -> int:
    """Checkpoint 1 done condition: imports work and the token loads."""
    print(f"project root      {PROJECT_ROOT}")
    print(f"env file          {ENV_PATH} exists={ENV_PATH.exists()}")
    ensure_dirs()
    print(f"data dir          {DATA_DIR}")

    for forbidden in sorted(FORBIDDEN_KEYS):
        in_process = forbidden in os.environ
        in_file = forbidden in parse_env_text(
            ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
        )
        print(f"forbidden key     {forbidden} in_process={in_process} in_env_file={in_file}")

    try:
        token = eodhd_token()
    except ConfigError as exc:
        print(f"FAIL              {exc}")
        return 1

    masked = token[:4] + "..." + token[-4:] if len(token) > 8 else "set"
    print(f"EODHD_API_TOKEN   loaded ({masked}), length {len(token)}")
    print(f"RESEND_API_KEY    {'set' if resend_api_key() else 'not set, delivery will skip'}")
    print(f"EMAIL_TO          {email_to() or 'not set, delivery will skip'}")

    import markdown
    import requests
    import websocket

    print(f"requests          {requests.__version__}")
    print(f"websocket-client  {websocket.__version__}")
    print(f"markdown          {markdown.__version__}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
