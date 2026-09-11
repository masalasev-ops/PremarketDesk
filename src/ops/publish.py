"""Upload site/ to Cloudflare Pages, or skip cleanly when it may not.

The same shape as morning/deliver.py, and for the same reason: a closed gate
is a correct outcome, not a failure. CLOUDFLARE_API_TOKEN or
CLOUDFLARE_ACCOUNT_ID unset means this machine is not supposed to publish, so
the step prints why, records why, and exits zero.

WHAT LEAVES THE MACHINE is the contents of config.SITE_DIR and nothing else.
wrangler is handed that one directory. The database, data/, runs/, doc/ and
the code are never named to it, and every file it is about to upload is read
here first, because three things can put something in a page that its screens
never show:

  size     Cloudflare Pages refuses a single file over [Publish] max_file_mb,
           and the desk inlines every session, so it grows every weekday.
           Every file's size is printed on every run, so the growth is read
           rather than discovered on the morning it crosses the line.
  secrets  no file may carry the EODHD token, the Resend key, either
           Cloudflare value, an api_token= string, or an absolute local path
           (the profile root or this project's root). The desk's payloads are
           gzipped and base64 encoded, so a plain text scan cannot see inside
           them: every one is decoded and scanned as well.
  data     every inline data block, a <script> whose type is JSON, has its
           top level keys printed, and a gzipped payload inside one has ITS
           keys printed too. What the page carries beyond what it displays is
           then stated in the log on every run rather than assumed. A block
           that does not parse is a refusal, because its contents cannot be
           stated.

Any refusal names the file and the line, uploads nothing, and fails the step.
A wrangler exit that is not zero fails the step too. Neither fails the chain
it rides in: see the .bat files, which run this after the desk and read its
exit code only to write the finish marker.

HELD UNTIL THE FIRST REPORT HAS BEEN READ. data/PUBLISH_HELD stands the
SCHEDULED runs down, a run under PMD_JOB, exactly as data/UNVERIFIED stands
delivery down. A hand run ignores it, because the hand run is how the report
that lifts the hold gets produced. Delete the file to let the chains publish.

The two Cloudflare values never reach output. They are handed to wrangler in
its environment and nowhere else, config.scrub_secrets masks both, and every
line of wrangler's output goes through it before it is printed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from ops import job_status

_CRIT = criteria.load()

PROJECT_NAME = "premarketdesk"
PRODUCTION_BRANCH = "main"
TOKEN_VAR = "CLOUDFLARE_API_TOKEN"
ACCOUNT_VAR = "CLOUDFLARE_ACCOUNT_ID"

# A file whose EXISTENCE is the state, like UNVERIFIED and DORMANT, so it is
# in conftest's rebind list: an un-redirected one would read as the real
# machine's answer inside the suite.
HOLD_MARKER = config.DATA_DIR / "PUBLISH_HELD"

# The root URL. Cloudflare Pages reads this file from the uploaded folder; it
# is the one tracked file under site/ and nothing that renders writes it.
REDIRECTS_NAME = "_redirects"
REDIRECTS_LINE = "/ /PremarketDesk.html 302"

MIB = 1024 * 1024

# Types a <script> can carry that make it data rather than code.
_DATA_TYPES = ("application/json", "application/ld+json", "importmap")
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))""")
# gzip's magic number, 1f 8b 08, as it reads once base64 encoded.
_GZIP_B64_PREFIX = "H4sI"
_URL_RE = re.compile(r"https://[A-Za-z0-9.-]+\.pages\.dev[^\s'\"<>]*")

OK_CODES = (0,)


# ------------------------------------------------------------------ the gate

def credential(name: str) -> str | None:
    """A setting through config.get. The one seam a claim rebinds to close the gate."""
    return config.get(name)


def gate() -> str | None:
    """Why this run may not publish, or None when it may."""
    missing = [name for name in (TOKEN_VAR, ACCOUNT_VAR) if not credential(name)]
    if missing:
        return f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set"
    if os.environ.get(job_status.JOB_ENV_VAR) and HOLD_MARKER.exists():
        return (f"held: {HOLD_MARKER.name} exists, so the scheduled publish stands "
                "down until the owner has read the first hand run's report. "
                f"Delete {HOLD_MARKER} to let the chains publish")
    return None


# ------------------------------------------------------------ the three checks

class Violation:
    """One reason not to upload, pinned to a file and a line."""

    def __init__(self, path: str, line: int | None, what: str) -> None:
        self.path = path
        self.line = line
        self.what = what

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"{where}  {self.what}"


def site_files(site: Path) -> list[Path]:
    """Every file wrangler would upload, sorted, subdirectories included."""
    return sorted(p for p in site.rglob("*") if p.is_file())


def _rel(path: Path, site: Path) -> str:
    return path.relative_to(site).as_posix()


def check_sizes(files: list[Path], site: Path) -> tuple[list[str], list[Violation]]:
    """One line per file, and a refusal for any file past the per file limit."""
    limit_mb = _CRIT.number("publish", "max_file_mb")
    limit = int(limit_mb * MIB)
    lines: list[str] = []
    refused: list[Violation] = []
    total = 0
    for path in files:
        size = path.stat().st_size
        total += size
        share = size / limit * 100
        lines.append(f"{_rel(path, site):<32} {size:>12,} bytes  {size / MIB:7.2f} MB  "
                     f"{share:5.1f}% of the {limit_mb:g} MB limit")
        if size > limit:
            refused.append(Violation(_rel(path, site), None,
                                     f"is {size / MIB:.2f} MB, past the {limit_mb:g} MB "
                                     "Cloudflare Pages per file limit"))
    lines.append(f"{'total':<32} {total:>12,} bytes  {total / MIB:7.2f} MB  "
                 f"in {len(files)} file(s)")
    return lines, refused


def _needles() -> list[tuple[str, str, bool]]:
    """(label, text, case sensitive) for everything that must not be uploaded.

    Secrets are matched exactly and labelled by name only. The paths are
    matched in every spelling a page can hold them in: backslashed, forward
    slashed, JSON escaped, and URL encoded for the project root, whose name
    carries two spaces.
    """
    out: list[tuple[str, str, bool]] = []
    for name in config.SECRET_NAMES:
        value = credential(name)
        if value and len(value) >= 8:
            out.append((f"the value of {name} ({config.mask(value)})", value, True))
    out.append(("an api_token= string", "api_token=", False))
    profile = "c:" + "\\" + "users"
    out.append(("an absolute local path under C:/Users", profile, False))
    out.append(("an absolute local path under C:/Users", "c:/users", False))
    out.append(("an absolute local path under C:/Users", profile.replace("\\", "\\\\"), False))
    root = str(config.PROJECT_ROOT)
    posix = config.PROJECT_ROOT.as_posix()
    for spelling in (root, posix, root.replace("\\", "\\\\"), posix.replace(" ", "%20")):
        out.append(("the project root, an absolute local path", spelling, False))
    return out


def _scan(text: str, needles: list[tuple[str, str, bool]]) -> list[tuple[int, str]]:
    """(1 based line, label) for every needle in text, once per needle per line.

    The line's own content is never returned: it may be the secret.
    """
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        seen: set[str] = set()
        for label, needle, exact in needles:
            hit = needle in line if exact else needle.lower() in lowered
            if hit and label not in seen:
                seen.add(label)
                found.append((number, label))
    return found


def _attrs(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        _name, _quoted, double, single, bare = match.groups()
        value = double if double is not None else single if single is not None else bare
        out[match.group(1).lower()] = value or ""
    return out


def _decode_payload(value: str) -> tuple[str, Any]:
    """A gzipped base64 JSON payload, decoded, or raises ValueError."""
    try:
        raw = gzip.decompress(base64.b64decode(value, validate=True))
        return raw.decode("utf-8"), json.loads(raw)
    except (binascii.Error, OSError, EOFError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc


def _keys(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(str(k) for k in value) or "(an empty object)"
    if isinstance(value, list):
        return f"(a list of {len(value)})"
    return f"(a {type(value).__name__})"


def inspect_page(text: str, rel: str,
                 needles: list[tuple[str, str, bool]]) -> tuple[list[str], list[Violation]]:
    """The inline data a page carries, stated, plus what is refused inside it.

    Returns report lines and violations. Scans the decoded payloads for the
    same needles as the page text, because gzip and base64 hide them from it.
    """
    lines: list[str] = []
    refused: list[Violation] = []
    for match in _SCRIPT_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        attrs = _attrs(match.group(1))
        body = match.group(2)
        kind = attrs.get("type", "").strip().lower()
        label = f"#{attrs['id']}" if attrs.get("id") else "(no id)"
        if "src" in attrs:
            lines.append(f"{rel}:{line}  script {label} loads {attrs['src']}, "
                         "external, not inline data")
            continue
        if kind not in _DATA_TYPES:
            lines.append(f"{rel}:{line}  script {label} is code, {len(body):,} "
                         "characters, not a data block")
            continue
        try:
            data = json.loads(body)
        except ValueError as exc:
            refused.append(Violation(rel, line, f"inline data block {label} does "
                                     f"not parse as JSON ({exc}), so what it carries "
                                     "cannot be stated"))
            continue
        lines.append(f"{rel}:{line}  data {label}, {len(body):,} characters, "
                     f"top level keys: {_keys(data)}")
        if not isinstance(data, dict):
            continue
        inner: dict[str, int] = {}
        packed = 0
        for key, value in data.items():
            if not (isinstance(value, str) and value.startswith(_GZIP_B64_PREFIX)):
                continue
            try:
                decoded_text, decoded = _decode_payload(value)
            except ValueError as exc:
                refused.append(Violation(rel, line, f"inline data block {label} "
                                         f"entry {key!r} looks gzipped and does not "
                                         f"decode ({exc}), so what it carries cannot "
                                         "be stated"))
                continue
            packed += 1
            for inner_line, what in _scan(decoded_text, needles):
                refused.append(Violation(rel, line, f"carries {what}, inside {label} "
                                         f"entry {key!r} once decoded, at its line "
                                         f"{inner_line}"))
            if isinstance(decoded, dict):
                for inner_key in decoded:
                    inner[str(inner_key)] = inner.get(str(inner_key), 0) + 1
        if packed:
            listed = ", ".join(f"{k} ({n})" if n != packed else k
                               for k, n in inner.items()) or "(nothing)"
            lines.append(f"{rel}:{line}    {packed} gzipped entr{'y' if packed == 1 else 'ies'} "
                         f"decoded, keys inside them: {listed}")
    return lines, refused


def check_contents(files: list[Path], site: Path) -> tuple[list[str], list[Violation]]:
    """The secret scan over every file, and the data block report over every page."""
    needles = _needles()
    lines: list[str] = []
    refused: list[Violation] = []
    for path in files:
        rel = _rel(path, site)
        text = path.read_bytes().decode("utf-8", errors="replace")
        refused.extend(Violation(rel, number, f"carries {what}")
                       for number, what in _scan(text, needles))
        if path.suffix.lower() in (".html", ".htm"):
            page_lines, page_refused = inspect_page(text, rel, needles)
            lines.extend(page_lines or [f"{rel}  no <script> blocks"])
            refused.extend(page_refused)
    return lines, refused


# ------------------------------------------------------------------ wrangler

def wrangler_env() -> dict[str, str]:
    """The environment wrangler runs in: the two Cloudflare values and a CA.

    The values come through config.get, so a .env entry works as well as a
    real environment variable. NODE_EXTRA_CA_CERTS is set when it is not
    already, because this machine's antivirus re-signs TLS and a scheduled
    task does not inherit the variable an interactive shell has: without it
    Node refuses the intercepted certificate.
    """
    env = dict(os.environ)
    for key in config.FORBIDDEN_KEYS:
        env.pop(key, None)
    for name in (TOKEN_VAR, ACCOUNT_VAR):
        value = credential(name)
        if value:
            env[name] = value
    if not env.get("NODE_EXTRA_CA_CERTS"):
        bundle = config.ca_bundle()
        if isinstance(bundle, str):
            env["NODE_EXTRA_CA_CERTS"] = bundle
    env["WRANGLER_SEND_METRICS"] = "false"
    # Plain text for the .bat's log: without this every warning arrives
    # wrapped in terminal colour codes.
    env["NO_COLOR"] = "1"
    return env


def run_wrangler(args: list[str], cwd: Path, env: dict[str, str],
                 timeout_s: float) -> tuple[int | None, str]:
    """Run `npx wrangler <args>`. Returns (exit code or None, combined output).

    THE NETWORK BOUNDARY for this module and the one thing conftest stubs.
    The local install is checked first so npx cannot quietly fetch a wrangler
    from the registry at 22:15 when node_modules is missing.
    """
    local = config.PROJECT_ROOT / "node_modules" / ".bin"
    if not ((local / "wrangler.cmd").is_file() or (local / "wrangler").is_file()):
        return 127, (f"wrangler is not installed under {local}. Run `npm install` "
                     "in the project root; package.json pins it")
    npx = shutil.which("npx")
    if npx is None:
        return 127, "npx is not on PATH, so wrangler cannot be run"
    try:
        done = subprocess.run([npx, "wrangler", *args], cwd=str(cwd), env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        return None, f"{partial}\nwrangler did not finish within {timeout_s:g}s and was stopped"
    except OSError as exc:
        return 127, f"wrangler could not be started: {exc}"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _printable(text: str) -> str:
    """text as the stream this process prints to can hold it.

    wrangler decorates its output with emoji, and a Windows process whose
    output is redirected to a .bat's log prints in the ANSI code page, which
    has none of them. The first hand run raised UnicodeEncodeError on the
    line that announced a created project, after wrangler had already done
    the work. A replaced character in a log beats a step that dies reporting
    its own success.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_output(output: str) -> list[str]:
    lines = [config.scrub_secrets(line) for line in output.splitlines() if line.strip()]
    for line in lines:
        print(_printable(f"publish:   | {line}"))
    return lines


def deployment_url(output: str) -> str | None:
    """The deployment's own URL out of wrangler's output, or None."""
    found = _URL_RE.findall(output)
    return found[0].rstrip(".,)") if found else None


# ------------------------------------------------------------------ the step

def publish(site: Path, check_only: bool = False) -> int:
    reason = None if check_only else gate()
    if reason:
        print(f"publish: skipping, {reason}. site/ stays on this machine.")
        job_status.note(f"skipped: {reason}")
        job_status.produced("files uploaded", 0)
        return 0

    if not site.is_dir() or not site_files(site):
        why = f"{site} holds no files, and deploying an empty folder would take the site down"
        print(f"publish: REFUSED, {why}")
        job_status.note(f"refused: {why}")
        job_status.produced("files uploaded", 0)
        return 1

    files = site_files(site)
    print(f"publish: {len(files)} file(s) under {site}, each read before upload")
    if not (site / REDIRECTS_NAME).is_file():
        print(f"publish: note, {REDIRECTS_NAME} is missing, so the bare project URL "
              "will answer 404 rather than open the archive")

    print("publish: sizes")
    size_lines, refused = check_sizes(files, site)
    for line in size_lines:
        print(f"publish:   {line}")
    print("publish: inline data")
    data_lines, content_refused = check_contents(files, site)
    for line in data_lines:
        print(f"publish:   {line}")
    refused.extend(content_refused)

    if refused:
        print(f"publish: REFUSED, {len(refused)} problem(s), nothing was uploaded:")
        for violation in refused:
            print(f"publish:   {violation}")
        job_status.note(f"refused before upload: {refused[0]}"
                        + (f" and {len(refused) - 1} more" if len(refused) > 1 else ""))
        job_status.produced("files uploaded", 0)
        return 1

    if check_only:
        print(f"publish: --check, all three checks pass on {len(files)} file(s) and "
              "nothing was uploaded")
        job_status.note("checked only, nothing uploaded")
        job_status.produced("files uploaded", 0)
        return 0

    timeout_s = _CRIT.number("publish", "deploy_timeout_s")
    args = ["pages", "deploy", site.name, "--project-name", PROJECT_NAME,
            "--branch", PRODUCTION_BRANCH, "--commit-dirty=true"]
    print(f"publish: npx wrangler {' '.join(args)}")
    code, output = run_wrangler(args, site.parent, wrangler_env(), timeout_s)
    printed = _print_output(output)
    if code != 0:
        last = printed[-1] if printed else "no output"
        print(f"publish: FAILED, wrangler exited {code}")
        job_status.note(f"wrangler exited {code}: {last}")
        job_status.produced("files uploaded", 0)
        return 1

    url = deployment_url(config.scrub_secrets(output))
    if url is None:
        print("publish: FAILED, wrangler exited 0 and printed no deployment URL, so "
              "where this landed cannot be stated")
        job_status.note("wrangler exited 0 and printed no deployment URL")
        job_status.produced("files uploaded", 0)
        return 1

    print(f"publish: deployed {len(files)} file(s) to {url}")
    job_status.note(f"deployed to {url}")
    job_status.produced("files uploaded", len(files))
    return 0


def create_project() -> int:
    """Create the Pages project once. An existing project is success.

    Run by hand, not by the chains: `python -m ops.publish --create-project`.

    WITH --force, and only here. wrangler 4.131 hands a `pages project
    create` for a project that does not exist yet to the Workers based
    successor of Pages, but ONLY when it detects an AI coding agent in its
    environment (CLAUDECODE among a dozen others, read in its detectAgent).
    Run from the scheduler or by a person the same command creates a plain
    Pages project. The first attempt on 2026-09-11 ran inside an agent
    session, was handed off, and failed with "Could not detect a directory
    containing static files", creating nothing. --force skips that hand off,
    so the command creates the same thing whoever runs it. wrangler's own
    source says it is needed once: once the project exists, a deploy to it is
    never handed off, so publish() passes no such flag.
    """
    missing = [name for name in (TOKEN_VAR, ACCOUNT_VAR) if not credential(name)]
    if missing:
        print(f"publish: cannot create the project, {' and '.join(missing)} not set")
        return 1
    args = ["pages", "project", "create", PROJECT_NAME,
            "--production-branch", PRODUCTION_BRANCH, "--force"]
    print(f"publish: npx wrangler {' '.join(args)}")
    code, output = run_wrangler(args, config.PROJECT_ROOT, wrangler_env(),
                                _CRIT.number("publish", "deploy_timeout_s"))
    _print_output(output)
    if code == 0:
        print(f"publish: created the Pages project {PROJECT_NAME}")
        job_status.note(f"created the Pages project {PROJECT_NAME}")
        return 0
    if "already exists" in output.lower():
        print(f"publish: the Pages project {PROJECT_NAME} already exists, which is "
              "what this wanted")
        job_status.note(f"the Pages project {PROJECT_NAME} already exists")
        return 0
    print(f"publish: FAILED, wrangler exited {code}")
    job_status.note(f"project create: wrangler exited {code}")
    return 1


def main(argv: list[str] | None = None) -> int:
    # Every line this step prints, not only wrangler's: a data block key or a
    # file name can carry a character the ANSI code page lacks. See _printable.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Upload site/ to Cloudflare Pages.")
    parser.add_argument("--create-project", action="store_true",
                        help="Create the Pages project once, then exit. An existing "
                             "project counts as success.")
    parser.add_argument("--check", action="store_true",
                        help="Run the three checks and print the report, upload "
                             "nothing. Ignores the gate, since it sends nothing.")
    args = parser.parse_args(argv)
    if args.create_project:
        return create_project()
    return publish(config.SITE_DIR, check_only=args.check)


if __name__ == "__main__":
    sys.exit(job_status.run("publish", main, ok_codes=OK_CODES))
