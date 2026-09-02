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
from typing import Any

# The one environment variable this project refuses to touch.
FORBIDDEN_KEYS = frozenset({"ANTHROPIC_API_KEY"})

# This file lives at src/core/config.py, so the project root is two levels up
# from the directory holding it. Getting this wrong relocates every writable
# path in the project by one directory, silently, which is why it is spelled
# out rather than chained: SRC_DIR is src/, PROJECT_ROOT is the repository.
CORE_DIR = Path(__file__).resolve().parent
SRC_DIR = CORE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
DOC_DIR = PROJECT_ROOT / "doc"

ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
CRITERIA_PATH = DOC_DIR / "CRITERIA.md"

DATA_DIR = PROJECT_ROOT / "data"
PREMARKET_DIR = DATA_DIR / "premarket"
# Study payloads. Regenerable bulk, so it lives under the gitignored data
# root rather than in doc/, where every one of them inflated every diff and
# reading diffs is the only review this project has. What stays committed is
# the finding: a note carrying the question, the headline numbers, the date,
# the commit and this path. The two 2026-08-16 and 2026-08-17 float rotation
# runs stay in doc/ because their own _provenance headers say they cannot be
# produced again, one having lost its script and the other its input.
STUDY_DIR = DATA_DIR / "research"
RUNS_DIR = PROJECT_ROOT / "runs"
LOGS_DIR = PROJECT_ROOT / "logs"
# The published archive. It lives here rather than being built from
# PROJECT_ROOT inside build_archive because a path a module constructs itself
# is a path the test sandbox cannot redirect, and the entrypoint tests caught
# exactly that: build_archive rewrote the real site/PremarketDesk.html from
# inside the sandbox, and the mtime check did not see it because it watches
# runs/ and data/, which is where the previous escapes happened.
SITE_DIR = PROJECT_ROOT / "site"

DB_PATH = DATA_DIR / "premarketdesk.db"
UNIVERSE_PATH = DATA_DIR / "universe.json"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"

REPORT_TEMPLATE_PATH = DOC_DIR / "REPORT_TEMPLATE.md"
ANALYST_PROMPT_PATH = DOC_DIR / "prompt_analyst.md"
SLOTS_PROMPT_PATH = DOC_DIR / "prompt_slots.md"

# The four working directories, named rather than captured. ensure_dirs()
# resolves each name against this module at CALL time, and that is the whole
# reason they are strings here. This used to be a tuple of Path objects frozen
# at import. The test sandbox rebinds config.DATA_DIR, PREMARKET_DIR, RUNS_DIR
# and LOGS_DIR to temporary copies and cannot rebind a tuple built from them,
# so ensure_dirs() was the one writer in the project a redirect could not
# reach: every call made inside the sandbox created the REAL data,
# data/premarket, runs and logs. No data ever landed in them, because every
# other writer reads the attribute at call time, but two things went wrong
# anyway. With the gitignored runs/ or logs/ cleared by hand, the first
# sandboxed call recreated them for real and the suite's whole-tree check
# failed on a path the harness itself had made, which reads as a test escaping
# the sandbox. And test_entrypoints' call, placed to materialise the SANDBOX
# directories, quietly materialised the repository's and did nothing for its
# stated purpose.
_ALL_DIR_NAMES = ("DATA_DIR", "PREMARKET_DIR", "RUNS_DIR", "LOGS_DIR",
                  "STUDY_DIR")

# EODHD addresses. These are locations, not criteria, so they live here rather
# than in CRITERIA.md. Every number that shapes a decision lives in that file.
EODHD_BASE_URL = "https://eodhd.com/api"
EODHD_WS_TRADES_URL = "wss://ws.eodhistoricaldata.com/ws/us"
RESEND_SEND_URL = "https://api.resend.com/emails"

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


def mask(secret: str) -> str:
    """The display form of a secret: an ellipsis and the last four characters.

    Last four only, not first-and-last: eight visible characters are enough
    to identify a token against a list even though they cannot be used, and
    identification is itself a leak. Four is enough for a human to tell
    which credential a log line is talking about.
    """
    if len(secret) > 8:
        return "..." + secret[-4:]
    return "***"


def scrub_secrets(text: Any) -> str:
    """Replace any known credential appearing in text with its masked form.

    Exception text can carry a URL with the API token embedded as a query
    parameter, and an exception string is exactly the kind of thing that gets
    printed into a log that sits on disk for months. Anything that might
    reach output goes through here first.
    """
    out = str(text)
    for secret in (get("EODHD_API_TOKEN"), get("RESEND_API_KEY")):
        if secret:
            out = out.replace(secret, mask(secret))
    return out


GIT_DIR = PROJECT_ROOT / ".git"


def _resolved_head() -> str | None:
    """The commit .git/HEAD points at, read from the files rather than from git.

    A detached HEAD holds the hash directly. A normal HEAD holds a ref, whose
    hash is either in .git/refs/ or, once git has packed them, in packed-refs.
    All three are handled because the failure mode of missing one is a packet
    that cannot say which build wrote it.
    """
    try:
        head = (GIT_DIR / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head or None

    ref = head[4:].strip()
    try:
        return (GIT_DIR / ref).read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    try:
        packed = (GIT_DIR / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in packed.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        commit, _, name = line.partition(" ")
        if name.strip() == ref:
            return commit.strip()
    return None


def build_identifier() -> dict[str, Any]:
    """Which build produced this run: the commit, and whether the tree was edited.

    Recorded in every packet from 2026-08-14 on, because the first live morning
    produced a report that could not be tied back to the code that wrote it.
    A dirty tree is not an error, it is a fact about reproducibility: the run
    cannot be recreated from the commit alone, and the reader should know.
    """
    import subprocess

    commit = _resolved_head()
    dirty: bool | None = None
    dirty_reason = None
    try:
        # --no-optional-locks is what keeps this read only. Plain `git status`
        # refreshes the index to cache stat information, which REWRITES
        # .git/index, and the test suite's whole-tree isolation check then
        # fails on a file the check itself caused to change. That produced an
        # intermittent failure that looked like a filesystem oddity for a day.
        # Adding .git to the allowlist would have hidden it at the cost of
        # blinding the check to a directory it currently watches, so the
        # measurement stopped writing instead.
        finished = subprocess.run(
            ["git", "--no-optional-locks", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if finished.returncode == 0:
            dirty = bool(finished.stdout.strip())
        else:
            dirty_reason = f"git status exited {finished.returncode}"
    except (OSError, subprocess.SubprocessError) as exc:
        dirty_reason = f"{type(exc).__name__}: {exc}"

    out: dict[str, Any] = {"commit": commit, "dirty": dirty}
    if commit is None:
        out["commit_reason"] = f"could not resolve HEAD under {GIT_DIR}"
    if dirty_reason:
        out["dirty_reason"] = dirty_reason
    return out


def resend_api_key() -> str | None:
    """Resend key, or None when delivery should be skipped."""
    return get("RESEND_API_KEY")


def email_to() -> list[str]:
    """Recipient list, empty when delivery should be skipped."""
    raw = get("EMAIL_TO") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def email_from() -> str:
    """Sender address. The resend.dev default needs no verified domain."""
    return get("EMAIL_FROM") or "PremarketDesk <onboarding@resend.dev>"


CA_BUNDLE_PATH = DATA_DIR / "ca-bundle.pem"

# Windows security suites terminate TLS and re-sign it with their own root,
# which certifi has never heard of. Norton drops its root here and points
# NODE_EXTRA_CA_CERTS at it. Verification stays on. We widen the trust store
# instead of turning the check off, because verify=False in a data pipeline is
# how you end up trusting whatever answers on port 443.
_EXTRA_CA_ENV_VARS = ("EODHD_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")
_EXTRA_CA_KNOWN_PATHS = (
    Path(r"C:\ProgramData\Norton\Antivirus\wscert.pem"),
)


def _extra_ca_files() -> list[Path]:
    found: list[Path] = []
    for name in _EXTRA_CA_ENV_VARS:
        raw = os.environ.get(name) or load_env().get(name)
        if raw:
            candidate = Path(raw.strip().strip('"'))
            if candidate.is_file():
                found.append(candidate)
    for candidate in _EXTRA_CA_KNOWN_PATHS:
        if candidate.is_file():
            found.append(candidate)
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved not in [p.resolve() for p in unique]:
            unique.append(path)
    return unique


def ca_bundle() -> str | bool:
    """What to hand requests as verify=.

    Returns True when certifi alone is enough, otherwise the path to a merged
    bundle of certifi plus any locally installed inspection roots. The merged
    file is rebuilt whenever one of its sources is newer than it.

    The write is atomic and the merge is checked, and both are load bearing on
    this machine rather than hygiene.

    A plain write_text left a truncated file behind whenever it was
    interrupted, and Norton is recorded in tasks/README.md as occasionally
    denying the first write of a file here. The staleness test above is an
    mtime comparison, so a truncated file carries a FRESH mtime and is then
    served for as long as its sources stay unchanged, which is until certifi
    is upgraded. The local inspection root is appended LAST, so a truncation
    loses exactly the root that makes an intercepted connection verify, and
    every EODHD call fails TLS afterwards. Loud, but at 07:15 on a weekday and
    for a reason nothing in the trace would name. universe.write_atomically is
    the precedent for the temp sibling and os.replace pair; it is not reused
    because it serialises a dict and because core must not import selection.

    The per source check covers the other half. read_text with
    errors="replace" turns an unreadable byte into a character rather than
    raising, so a source that came back empty or mangled would contribute a
    header comment and nothing else, and the merged file would look healthy at
    every size check. A source that carries no certificate at all means the
    merge cannot be trusted, and this returns True and says so rather than
    serving a trust store that is missing the one root it exists to add.
    """
    explicit = get("EODHD_CA_BUNDLE")
    if explicit and Path(explicit).is_file():
        return explicit

    extras = _extra_ca_files()
    if not extras:
        return True

    try:
        import certifi
    except ImportError:
        return True

    sources = [Path(certifi.where())] + extras
    newest = max(p.stat().st_mtime for p in sources)
    if CA_BUNDLE_PATH.is_file() and CA_BUNDLE_PATH.stat().st_mtime >= newest:
        return str(CA_BUNDLE_PATH)

    CA_BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = []
    for source in sources:
        body = source.read_text(encoding="utf-8", errors="replace").strip()
        if "BEGIN CERTIFICATE" not in body:
            print(f"config: {source} carried no certificate, so the merged CA "
                  "bundle was NOT written and certifi alone is being used. An "
                  "intercepted connection will fail to verify until this is "
                  "fixed, which is the safe direction.", file=sys.stderr)
            return True
        merged.append(f"# from {source}\n")
        merged.append(body)
        merged.append("\n")
    # Through core/files.py, the one atomic writer, since 2026-09-02. The
    # docstring above explains why this could not reuse universe's copy: core
    # cannot import selection. It can import core.
    from core import files

    files.write_text_atomically(CA_BUNDLE_PATH, "\n".join(merged))
    return str(CA_BUNDLE_PATH)


def tls_context():
    """An SSLContext that trusts the local TLS inspection root, if there is one.

    Norton Web/Mail Shield re-signs every HTTPS connection with a self signed
    root whose basicConstraints extension is not marked critical. Python 3.13
    onwards turns on VERIFY_X509_STRICT in create_default_context, and strict
    mode rejects exactly that. So when, and only when, such a root is actually
    installed, this clears that one flag.

    What stays switched on: chain building, signature checking, expiry checking
    and hostname matching. What is given up: one encoding pedantry about an
    extension marked critical or not. That is a very long way from verify=False.
    """
    import ssl

    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()

    extras = _extra_ca_files()
    for extra in extras:
        try:
            context.load_verify_locations(cafile=str(extra))
        except (OSError, ssl.SSLError) as exc:
            print(f"config: could not load extra CA {extra}: {exc}", file=sys.stderr)
    if extras:
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def tls_note() -> str:
    """One line describing the trust decision, for logs and the verification gate."""
    extras = _extra_ca_files()
    if not extras:
        return "TLS: certifi defaults, strict verification"
    names = ", ".join(p.name for p in extras)
    return f"TLS: certifi plus local inspection root ({names}), X509_STRICT relaxed"


def _all_dirs() -> tuple[Path, ...]:
    """The four working directories as this module has them bound right now.

    Reading them out of the module globals is deliberate. It is the same
    lookup a caller writing config.DATA_DIR performs, so anything that rebinds
    the attribute is followed here too. See the note beside _ALL_DIR_NAMES for
    what the import time capture cost.
    """
    return tuple(globals()[name] for name in _ALL_DIR_NAMES)


def ensure_dirs() -> None:
    """Create the working directories. Safe to call on every run."""
    for directory in _all_dirs():
        directory.mkdir(parents=True, exist_ok=True)


def run_dir(date_str: str) -> Path:
    """runs/YYYY-MM-DD, created on demand. For a caller about to WRITE."""
    target = RUNS_DIR / date_str
    target.mkdir(parents=True, exist_ok=True)
    return target


def run_path(date_str: str) -> Path:
    """runs/YYYY-MM-DD, WITHOUT creating it. For a caller about to READ.

    A directory under runs/ is evidence that a run happened. build_archive
    treats runs/ as the record, CRITERIA's closes retention note keeps runs/
    off the prunable whitelist because site/ is rebuilt from it, and a reader
    asking which mornings exist reads the directory listing. So a read that
    creates one destroys the meaning of the thing it is reading.

    It had been doing exactly that. Thirteen call sites asked run_dir for a
    path only to call .is_file() on something inside it and return when the
    answer was no, and every one of them left a directory behind. The 22:15
    weekly page walks a calendar week, weekends included, so runs/2026-08-15
    and runs/2026-08-16 were a Saturday and a Sunday recreated every night
    after being deleted on 2026-08-21, and the truth pass's --reread walk left
    runs/2026-05-04, a date this project has never had a morning on.
    backfill_premarket already worked around this locally, with the comment
    "RUNS_DIR / day rather than config.run_dir(day): this is a read only", which
    is the same fix made once where it was noticed.

    Same shape as store.connect versus store.guard_live_database: the
    distinction is in the function the caller chooses, so a reader who wants a
    path cannot get a side effect by asking for one.
    """
    return RUNS_DIR / date_str


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

    print(f"EODHD_API_TOKEN   loaded ({mask(token)}), length {len(token)}")
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
