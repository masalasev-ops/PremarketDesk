"""ops/publish.py against a stubbed wrangler, never the real site/ or the network.

The publish step is the one place in this project where files leave the
machine for somewhere public, so each of its refusals is proved on a planted
violation rather than trusted from reading the code:

  1. a closed gate, and a held scheduled run, skip with a reason in the job
     status record and call nothing;
  2. a file past the per file limit is refused by name;
  3. a credential, an api_token= string, a local path, and a credential
     hidden inside a gzipped payload are each refused by file and line, and
     the credential itself is never printed;
  4. an inline data block that does not parse is refused by file and line,
     and the keys of one that does are printed, decoded payloads included;
  5. a wrangler exit that is not zero is a failed step;
  6. the size report names every file, subdirectories included;
  7. a clean run passes wrangler the one folder, the project and the branch,
     and records the deployment URL.

Every site here is a temporary directory. conftest.block_network replaces
publish.run_wrangler with a refusal, and each claim installs its own stub on
top of that and restores it. The credentials are stub values set through
publish.credential, so no claim depends on what this machine's .env holds.

Run directly with `python -m tests.test_publish`, or as part of
`python -m tests.run_tests`. Both are sandboxed.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

from core import config
from ops import job_status
from ops import publish
from tests import conftest
from tests.conftest import run_claim

FAKE = {
    "CLOUDFLARE_API_TOKEN": "cf-stub-token-0123456789abcdefWXYZ",
    "CLOUDFLARE_ACCOUNT_ID": "0123456789abcdef0123456789abcdef",
    "EODHD_API_TOKEN": "eodhd-stub-token-9876543210",
    "RESEND_API_KEY": "re_stub_key_1122334455",
}
DEPLOYED = "https://a1b2c3d4.premarketdesk.pages.dev"


class _Wrangler:
    """Records every call and answers with a fixed exit code and output."""

    def __init__(self, code: int | None = 0,
                 output: str = f"Uploading... (3/3)\nDeployment complete! Take a peek over at {DEPLOYED}\n") -> None:
        self.code = code
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: list[str], cwd: Path, env: dict[str, str],
                 timeout_s: float) -> tuple[int | None, str]:
        self.calls.append({"args": list(args), "cwd": Path(cwd), "env": env,
                           "timeout_s": timeout_s})
        return self.code, self.output


@contextlib.contextmanager
def _stubbed(wrangler: _Wrangler, creds: dict[str, str] | None = None,
             job: str | None = None) -> Iterator[None]:
    """Install the wrangler stub and the credentials; set or clear PMD_JOB."""
    saved_run, saved_cred = publish.run_wrangler, publish.credential
    saved_job = os.environ.get(job_status.JOB_ENV_VAR)
    values = FAKE if creds is None else creds
    publish.run_wrangler = wrangler
    publish.credential = lambda name: values.get(name)
    if job is None:
        os.environ.pop(job_status.JOB_ENV_VAR, None)
    else:
        os.environ[job_status.JOB_ENV_VAR] = job
    try:
        yield
    finally:
        publish.run_wrangler, publish.credential = saved_run, saved_cred
        if saved_job is None:
            os.environ.pop(job_status.JOB_ENV_VAR, None)
        else:
            os.environ[job_status.JOB_ENV_VAR] = saved_job


@contextlib.contextmanager
def _site(files: dict[str, str | bytes]) -> Iterator[Path]:
    """A throwaway folder named site, holding exactly the given files."""
    box = Path(tempfile.mkdtemp(prefix="pmd-publish-"))
    site = box / "site"
    site.mkdir()
    try:
        for rel, body in files.items():
            path = site / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, bytes):
                path.write_bytes(body)
            else:
                path.write_text(body, encoding="utf-8")
        yield site
    finally:
        shutil.rmtree(box, ignore_errors=True)


def _run(site: Path) -> tuple[int, dict[str, Any], str]:
    """publish() through job_status.run, as the .bat runs it; code, record, output."""
    before = len(job_status.records())
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = job_status.run("publish", lambda: publish.publish(site),
                              ok_codes=publish.OK_CODES)
    rows = job_status.records()
    return code, (rows[before] if len(rows) > before else {}), out.getvalue()


def _page(body: str) -> str:
    return f"<!doctype html><html><head><title>t</title></head><body>\n{body}\n</body></html>\n"


def _packed(obj: Any) -> str:
    return base64.b64encode(gzip.compress(json.dumps(obj).encode("utf-8"))).decode("ascii")


CLEAN = {
    "PremarketDesk.html": _page('<p>desk</p>\n<script id="desk-index" type="application/json">'
                                '{"built_at": "2026-09-11", "sessions": []}</script>'),
    "Weekly.html": _page("<p>week</p>"),
    "_redirects": publish.REDIRECTS_LINE + "\n",
}


# ------------------------------------------------------------------- claims

def claim_a_closed_gate_calls_nothing(failures: list[str]) -> None:
    """Unset credentials, and a held scheduled run, each skip with a reason."""
    with _site(CLEAN) as site:
        for missing in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
            wrangler = _Wrangler()
            creds = {k: v for k, v in FAKE.items() if k != missing}
            with _stubbed(wrangler, creds):
                code, record, _out = _run(site)
            if wrangler.calls:
                failures.append(f"with {missing} unset, wrangler was still called")
            if code != 0 or record.get("status") != job_status.STATUS_OK:
                failures.append(f"with {missing} unset the step exited {code} and "
                                f"recorded {record.get('status')!r}; a closed gate "
                                "is a correct outcome, not a failure")
            note = record.get("note") or ""
            if not note.startswith("skipped") or missing not in note:
                failures.append(f"the skip with {missing} unset recorded no reason "
                                f"naming it: {note!r}")
            if record.get("produced_count") != 0:
                failures.append("a skipped publish recorded files as uploaded")

        # HELD: the marker stands a SCHEDULED run down and not a hand run.
        publish.HOLD_MARKER.parent.mkdir(parents=True, exist_ok=True)
        publish.HOLD_MARKER.write_text("held\n", encoding="utf-8")
        try:
            wrangler = _Wrangler()
            with _stubbed(wrangler, job="nightly"):
                code, record, _out = _run(site)
            if wrangler.calls or code != 0 or "held" not in (record.get("note") or ""):
                failures.append(f"a scheduled run with {publish.HOLD_MARKER.name} "
                                f"present was not held: exit {code}, "
                                f"{len(wrangler.calls)} wrangler call(s), note "
                                f"{record.get('note')!r}")
            wrangler = _Wrangler()
            with _stubbed(wrangler, job=None):
                code, _record, _out = _run(site)
            if code != 0 or len(wrangler.calls) != 1:
                failures.append("a hand run was stood down by the hold marker, so "
                                "the report that lifts the hold could never be made")
        finally:
            publish.HOLD_MARKER.unlink(missing_ok=True)
    print("  gate         unset credentials and a held scheduled run skip with a "
          "reason and call nothing; a hand run is not held")


def claim_an_oversized_file_is_refused(failures: list[str]) -> None:
    """A file one byte past the per file limit is refused by name, before upload."""
    limit = int(publish._CRIT.number("publish", "max_file_mb") * publish.MIB)
    with _site(dict(CLEAN)) as site:
        big = site / "archive" / "huge.bin"
        big.parent.mkdir()
        with big.open("wb") as handle:
            handle.truncate(limit + 1)
        wrangler = _Wrangler()
        with _stubbed(wrangler):
            code, record, out = _run(site)
    if wrangler.calls:
        failures.append("an oversized file was uploaded anyway")
    if code == 0 or record.get("status") == job_status.STATUS_OK:
        failures.append(f"an oversized file did not fail the step: exit {code}")
    if "archive/huge.bin" not in out or "REFUSED" not in out:
        failures.append("the refusal of an oversized file does not name it")
    print("  size         a file past the per file limit is refused by name and "
          "nothing is uploaded")


def claim_a_secret_or_a_local_path_is_refused(failures: list[str]) -> None:
    """Every credential and path spelling is refused by file and line, unprinted."""
    token = FAKE["CLOUDFLARE_API_TOKEN"]
    root_json = str(config.PROJECT_ROOT).replace("\\", "\\\\")
    plants = {
        "the Cloudflare token": f"<p>{token}</p>",
        "the EODHD token": f"<p>{FAKE['EODHD_API_TOKEN']}</p>",
        "the Resend key": f"<p>{FAKE['RESEND_API_KEY']}</p>",
        "an api_token= string": "<a href='x?API_TOKEN=abc'>x</a>",
        "a profile path": "<p>" + "C:" + "\\" + "Users" + "\\someone\\file.txt</p>",
        "a forward slashed profile path": "<p>c:/users/someone</p>",
        "the project root": f"<p>{config.PROJECT_ROOT}</p>",
        "the project root, JSON escaped": f"<p>{root_json}</p>",
        "the project root, forward slashed": f"<p>{config.PROJECT_ROOT.as_posix()}</p>",
    }
    for what, planted in plants.items():
        body = _page("<p>first</p>\n<p>second</p>\n" + planted)
        planted_line = body[:body.index(planted)].count("\n") + 1
        with _site({**CLEAN, "Weekly.html": body}) as site:
            wrangler = _Wrangler()
            with _stubbed(wrangler):
                code, _record, out = _run(site)
        if wrangler.calls or code == 0:
            failures.append(f"{what} in a page was not refused (exit {code}, "
                            f"{len(wrangler.calls)} upload(s))")
        elif f"Weekly.html:{planted_line}" not in out:
            failures.append(f"the refusal of {what} does not name Weekly.html:"
                            f"{planted_line}")
        for secret in FAKE.values():
            if secret in out:
                failures.append(f"refusing {what} printed a credential in full")

    # Hidden where a text scan cannot see: inside a gzipped payload.
    payload = {"2026-09-11": _packed({"packet": {"note": f"key {token}"}})}
    page = _page('<script id="desk-payloads" type="application/json">'
                 + json.dumps(payload) + "</script>")
    with _site({**CLEAN, "PremarketDesk.html": page}) as site:
        wrangler = _Wrangler()
        with _stubbed(wrangler):
            code, _record, out = _run(site)
    if wrangler.calls or code == 0:
        failures.append("a credential inside a gzipped payload was uploaded; the "
                        "scan only read the page text")
    elif "desk-payloads" not in out or "2026-09-11" not in out:
        failures.append("the refusal of a credential inside a payload does not "
                        "name the block and the entry")
    if token in out:
        failures.append("refusing a payload credential printed it in full")
    print(f"  secrets      {len(plants)} planted credentials and path spellings, and "
          "one inside a gzipped payload, each refused by file and line and never "
          "printed")


def claim_inline_data_is_stated_or_refused(failures: list[str]) -> None:
    """Keys are printed, decoded payloads included; a block that cannot parse is refused."""
    payload = {"2026-09-10": _packed({"packet": {}, "bars": [], "picks": []}),
               "2026-09-11": _packed({"packet": {}, "bars": []})}
    page = _page(
        '<script id="desk-glossary" type="application/json">{"ticker": "t", "gap": "g"}</script>\n'
        '<script id="desk-payloads" type="application/json">' + json.dumps(payload)
        + "</script>\n<script>var app = 1;</script>")
    with _site({**CLEAN, "PremarketDesk.html": page}) as site:
        wrangler = _Wrangler()
        with _stubbed(wrangler):
            code, _record, out = _run(site)
    if code != 0 or len(wrangler.calls) != 1:
        failures.append(f"a clean page with three scripts did not publish: exit {code}")
    for needle in ("#desk-glossary", "ticker, gap", "#desk-payloads",
                   "2026-09-10, 2026-09-11", "packet", "bars", "picks (1)",
                   "is code"):
        if needle not in out:
            failures.append(f"the inline data report does not state {needle!r}")

    broken = _page("<p>a</p>\n"
                   '<script id="desk-index" type="application/json">{"built_at": </script>')
    with _site({**CLEAN, "PremarketDesk.html": broken}) as site:
        wrangler = _Wrangler()
        with _stubbed(wrangler):
            code, _record, out = _run(site)
    if wrangler.calls or code == 0:
        failures.append("an inline data block that does not parse was uploaded")
    elif "PremarketDesk.html:3" not in out or "#desk-index" not in out:
        failures.append("the refusal of an unparseable block does not name the file, "
                        "the line and the block")
    print("  data         every block's keys are stated, a gzipped payload's own "
          "keys too, and a block that does not parse is refused by line")


def claim_a_wrangler_failure_fails_the_step(failures: list[str]) -> None:
    """A non zero wrangler exit, a timeout, and a success with no URL all fail."""
    for label, wrangler in (
            ("exit 1", _Wrangler(1, "X [ERROR] Authentication error [code: 10000]\n")),
            ("a timeout", _Wrangler(None, "wrangler did not finish\n")),
            ("exit 0 with no URL", _Wrangler(0, "Uploading...\n"))):
        with _site(CLEAN) as site:
            with _stubbed(wrangler):
                code, record, _out = _run(site)
        if code == 0 or record.get("status") == job_status.STATUS_OK:
            failures.append(f"wrangler reporting {label} was recorded as a success")
        if not record.get("note"):
            failures.append(f"wrangler reporting {label} left no reason in the record")
        if record.get("produced_count") != 0:
            failures.append(f"wrangler reporting {label} counted files as uploaded")
    # wrangler prints emoji, and a .bat's redirected log is written in the ANSI
    # code page. The first hand run died on exactly that, after the work.
    ansi = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    with _site(CLEAN) as site:
        wrangler = _Wrangler(0, f"✨ Success! Uploaded 3 files\n✨ Deployment "
                                f"complete! Take a peek over at {DEPLOYED}\n")
        with _stubbed(wrangler), contextlib.redirect_stdout(ansi):
            try:
                code = publish.publish(site)
            except UnicodeEncodeError as exc:
                code = None
                failures.append(f"wrangler's emoji crashed the step on a cp1252 "
                                f"stream: {exc}")
    if code not in (0, None):
        failures.append(f"a clean deploy printed to a cp1252 stream exited {code}")
    print("  wrangler     a non zero exit, a timeout and a silent success each fail "
          "the step with a reason, and its emoji cannot crash a log")


def claim_the_size_report_names_every_file(failures: list[str]) -> None:
    """Every file, nested ones included, is on the size report, refusal or not."""
    files = {**CLEAN, "assets/a.css": "body{}", "assets/deep/b.js": "x=1"}
    with _site(files) as site:
        wrangler = _Wrangler()
        with _stubbed(wrangler):
            code, record, out = _run(site)
    sizes = out.split("publish: sizes", 1)[-1].split("publish: inline data", 1)[0]
    for rel in files:
        if rel not in sizes:
            failures.append(f"the size report does not list {rel}")
    if f"in {len(files)} file(s)" not in sizes:
        failures.append("the size report's total does not count every file")
    if code != 0 or record.get("produced_count") != len(files):
        failures.append(f"a clean site of {len(files)} files recorded "
                        f"{record.get('produced_count')} uploaded (exit {code})")
    print(f"  size report  all {len(files)} files are listed with their sizes and "
          "a total")


def claim_a_clean_run_uploads_the_folder_and_nothing_else(failures: list[str]) -> None:
    """wrangler is handed the one folder, the project and the branch, and the URL is kept."""
    with _site(CLEAN) as site:
        wrangler = _Wrangler()
        with _stubbed(wrangler):
            code, record, out = _run(site)
    if code != 0 or len(wrangler.calls) != 1:
        failures.append(f"a clean site did not publish once: exit {code}, "
                        f"{len(wrangler.calls)} call(s)")
        return
    call = wrangler.calls[0]
    wanted = ["pages", "deploy", "site", "--project-name", "premarketdesk",
              "--branch", "main", "--commit-dirty=true"]
    if call["args"] != wanted:
        failures.append(f"wrangler was asked for {call['args']}, not {wanted}")
    if call["cwd"] != site.parent:
        failures.append("wrangler ran somewhere other than the folder holding site, "
                        "so the relative path site names something else")
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if call["env"].get(name) != FAKE[name]:
            failures.append(f"wrangler's environment does not carry {name}")
    if record.get("note") != f"deployed to {DEPLOYED}":
        failures.append(f"the deployment URL is not in the record: {record.get('note')!r}")
    if FAKE["CLOUDFLARE_API_TOKEN"] in out or FAKE["CLOUDFLARE_ACCOUNT_ID"] in out:
        failures.append("a clean run printed a Cloudflare value in full")
    print("  deploy       one folder, the project and the branch go to wrangler, "
          "and the deployment URL is recorded")


def claim_the_redirect_is_tracked_and_says_one_thing(failures: list[str]) -> None:
    """site/_redirects is committed, holds exactly the root line, and is the only tracked file there."""
    import subprocess

    path = config.PROJECT_ROOT / "site" / publish.REDIRECTS_NAME
    if not path.is_file():
        failures.append("site/_redirects is missing, so the bare URL answers 404")
    elif path.read_text(encoding="utf-8").strip() != publish.REDIRECTS_LINE:
        failures.append(f"site/_redirects holds something other than "
                        f"{publish.REDIRECTS_LINE!r}")
    listed = subprocess.run(
        ["git", "--no-optional-locks", "ls-files", "site"], cwd=str(config.PROJECT_ROOT),
        capture_output=True, text=True, timeout=30)
    tracked = [line for line in listed.stdout.splitlines() if line.strip()]
    if listed.returncode == 0 and tracked != ["site/_redirects"]:
        failures.append(f"git tracks {tracked} under site/; the rendered pages "
                        "must stay local and _redirects must be tracked")
    print("  redirect     site/_redirects is the one tracked file under site/ and "
          "sends the bare URL to the desk")


def claim_the_published_desk_names_no_machine(failures: list[str]) -> None:
    """The page publish uploads carries no word about the machine that built it.

    The owner, 2026-09-11, on the live site: nothing about packets, sources,
    vendors or how a figure was produced, anywhere, and scrubbed from what had
    already gone up. Built here from the sandbox's copy of the real sessions,
    so the claim reads what a real render would publish. Four surfaces, all
    public: the page text outside its scripts, every session payload once
    decoded, the glossary, and the page's own source. And the Health screen,
    every line of which is the machine describing itself, is on the copy
    built for this machine and nowhere in the published one, which is what
    the owner asked for once it had gone from both.
    """
    import re as _re

    from core import reader
    from desk import render as desk_render

    result = desk_render.render(compact_first=False)
    page = Path(result["path"]).read_text(encoding="utf-8")
    blocks = dict(_re.findall(
        r'<script id="([^"]+)" type="application/json">(.*?)</script>', page, _re.S))
    shell = _re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=_re.S)
    for hit in reader.machine_words(_re.sub(r"<[^>]+>", " ", shell)):
        failures.append(f"the published page's own text says {hit!r}")

    found = 0

    def walk(value: Any, where: str) -> None:
        nonlocal found
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{where}.{key}")
        elif isinstance(value, list):
            for item in value:
                walk(item, f"{where}[]")
        elif isinstance(value, str) and " " in value:
            found += 1
            words = reader.machine_words(_re.sub(r"<[^>]+>", " ", value))
            if words:
                failures.append(f"published session data {where} says {words[:3]}: "
                                f"{value[:100]!r}")

    for day, blob in json.loads(blocks.get("desk-payloads", "{}")).items():
        payload = json.loads(gzip.decompress(base64.b64decode(blob)))
        # Headlines and company names are the market's words, whatever they
        # say, and the reader filter leaves them alone for that reason.
        for candidate in payload.get("candidates") or []:
            candidate.pop("headlines", None)
            candidate.pop("name", None)
        walk(payload, day)
    if found < 50:
        failures.append(f"only {found} strings were read out of the published "
                        "sessions, so this claim is scanning almost nothing")
    for term, text in json.loads(blocks.get("desk-glossary", "{}")).items():
        if reader.machine_words(f"{term} {text}"):
            failures.append(f"the published glossary defines {term!r} in the "
                            "machine's own words")

    # THE SOURCE, which is one view-source away. Its comments are the machine
    # explaining itself and are not published: stripping the published
    # script again changes nothing, so none is left. And no string in it that
    # a screen could print names the machine, including the ones on branches
    # the sandbox's sessions never take, which the scan above cannot reach.
    scripts = _re.findall(r"<script>(.*?)</script>", page, _re.S)
    for script in scripts:
        if desk_render.strip_js_comments(script) != script:
            failures.append("the published script still carries comments")
        for match in _re.finditer(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'', script):
            literal = _re.sub(r"<[^>]+>", " ", match.group(1) or match.group(2) or "")
            if " " in literal.strip() and reader.machine_words(literal):
                failures.append(f"the published script can print {literal[:90]!r}")
    from core import page as core_page
    for style in _re.findall(r"<style[^>]*>(.*?)</style>", page, _re.S):
        if "/*" in style.replace(core_page.SHELL_MARK, ""):
            failures.append("a published stylesheet still carries a comment")

    # HEALTH IS LOCAL. Not in the published page's menu, script or data, and
    # in the copy built beside the Weekly page, with the figures it reads.
    from desk import assets
    if ('data-nav="health"' in page or "healthChecks" in page
            or assets.HEALTH_JS.strip()[:200] in page):
        failures.append("the Health screen is on the published desk")
    for day, blob in json.loads(blocks.get("desk-payloads", "{}")).items():
        if "health" in json.loads(gzip.decompress(base64.b64decode(blob))):
            failures.append(f"the published {day} session carries its health figures")
    local_page = Path(result["local_path"]).read_text(encoding="utf-8")
    if Path(result["local_path"]).parent == Path(result["path"]).parent:
        failures.append("the desk with Health was written into the published folder")
    if 'data-nav="health"' not in local_page or "healthChecks" not in local_page:
        failures.append("the local desk has no Health screen")
    local_blobs = json.loads(_re.search(
        r'<script id="desk-payloads" type="application/json">(.*?)</script>',
        local_page, _re.S).group(1))
    if local_blobs and not any("health" in json.loads(gzip.decompress(base64.b64decode(b)))
                               for b in local_blobs.values()):
        failures.append("the local desk's sessions carry no health figures to draw")
    print(f"  no machine   the published page, {found} strings across its sessions, "
          "its source and the glossary name no packet, vendor, file or step; "
          "Health is on the local desk only")


def claim_a_report_keeps_its_reader_half(failures: list[str]) -> None:
    """reader_markdown drops the machine and keeps every sentence about a share."""
    from core import reader

    source = "\n".join([
        "# PremarketDesk: a mood",
        "",
        "2026-09-11, packet generated 2026-09-11T08:45:02-04:00, generated by PremarketDesk.",
        "",
        "Nothing here is advice, the screen thresholds are unvalidated seed values, "
        "and every figure below was measured by this system rather than written by the model.",
        "",
        "## Summary",
        "",
        "SPY is up 0.66 percent on the collector. 20 evidence gaps recorded in the packet.",
        "",
        "## Market trends",
        "",
        "| Label | Last | Source |",
        "|---|---|---|",
        "| SPY | 762.80 | collector |",
        "",
        "## Premarket gappers",
        "",
        "ASTS, AST SpaceMobile. Catalyst class analyst_action, catalyst_found true. "
        "catalyst_why: EODHD news tag 'PRICE TARGET' mapped through CRITERIA.md, from "
        "'Berenberg launches space coverage'.",
        "",
        "## Skips and traps",
        "",
        "Traps: 0 of 10 candidates gap up against the balance of their own headlines.",
        "",
        "1 of 10 candidates carry a premarket RVOL built on a THIN denominator. "
        "These ratios are published, screened on and scored like the rest: CPRT.",
        "",
        "- CPRT: its denominator is a 5,100 share median",
        "",
        "Evidence gaps recorded by the scan, 2 in total:",
        "",
        "- short interest: 8 fundamentals call(s) at ten credits each.",
    ])
    out = reader.reader_markdown(source)
    for word in reader.machine_words(out):
        failures.append(f"a filtered report still says {word!r}")
    for kept in ("SPY is up 0.66 percent.", "| SPY | 762.80 |", reader.DISCLAIMER,
                 "Catalyst: analyst action, from the story 'Berenberg launches space coverage'.",
                 "Traps: 0 of 10 candidates"):
        if kept not in out:
            failures.append(f"a filtered report lost the reader's sentence {kept!r}")
    for gone in ("These ratios are published", "CPRT: its denominator", "Source"):
        if gone in out:
            failures.append(f"a filtered report kept the diagnostic {gone!r}")
    print("  reader copy  a report loses its packet stamp, its Source column, its "
          "diagnostics and every machine sentence, and keeps the rest word for word")


def claim_each_list_keeps_its_line(failures: list[str]) -> None:
    """The What else moved screen's "How each list came out" lines survive.

    The first scrub dropped them for saying "leg", and the owner asked for
    them back the same day: the counts are a reader's fact. Both shapes are
    checked, the one morning.scan writes and the one sessions before
    2026-09-03 froze with the list and leg keys raw.
    """
    from core import reader

    now = ("The prior session by sigma list is ranked: 5 selected of 2734 "
           "qualified of 2751 considered on the prior session leg.")
    old = ("The prior_session_by_sigma list is ranked: 5 selected of 2750 "
           "qualified of 2751 considered on the prior_session leg.")
    payload = {"mover_lists": {"a": {"state": "ranked", "text": now},
                               "b": {"state": "ranked", "text": old}}}
    lists = reader.desk_payload(payload)["mover_lists"]
    if lists["a"].get("text") != now:
        failures.append(f"a list's line did not reach the published desk: {lists['a']!r}")
    wanted = old.replace("prior_session_by_sigma", "prior session by sigma").replace(
        "prior_session", "prior session")
    if lists["b"].get("text") != wanted:
        failures.append("an older session's list line did not reach the published "
                        f"desk in words: {lists['b']!r}")
    print("  list lines   each ranked list's counts reach the desk, older sessions "
          "put in words")


def main(argv: list[str] | None = None) -> int:
    if config.RUNS_DIR == config.PROJECT_ROOT / "runs":
        print("SKIP  not running under the sandbox; use python -m tests.run_tests")
        return 0
    failures: list[str] = []
    print("publish, against a stubbed wrangler and throwaway sites:")
    run_claim(failures, claim_a_closed_gate_calls_nothing, failures)
    run_claim(failures, claim_an_oversized_file_is_refused, failures)
    run_claim(failures, claim_a_secret_or_a_local_path_is_refused, failures)
    run_claim(failures, claim_inline_data_is_stated_or_refused, failures)
    run_claim(failures, claim_a_wrangler_failure_fails_the_step, failures)
    run_claim(failures, claim_the_size_report_names_every_file, failures)
    run_claim(failures, claim_a_clean_run_uploads_the_folder_and_nothing_else, failures)
    run_claim(failures, claim_the_redirect_is_tracked_and_says_one_thing, failures)
    run_claim(failures, claim_the_published_desk_names_no_machine, failures)
    run_claim(failures, claim_a_report_keeps_its_reader_half, failures)
    run_claim(failures, claim_each_list_keeps_its_line, failures)
    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  publish refuses every planted violation, skips cleanly when gated, "
          "and fails loudly when wrangler does")
    return 0


if __name__ == "__main__":
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
