"""Email the rendered report through Resend, or skip cleanly when unconfigured.

The skip is a feature, not a failure. RESEND_API_KEY and EMAIL_TO empty means
this machine is not supposed to send email yet, so the chain prints why and
exits zero rather than blowing up a morning run over a key that was never
meant to be there.

The TLS session comes from eodhd.build_session because Norton's HTTPS
inspection intercepts this host exactly like it intercepts the data provider,
and the fix belongs in one place.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from typing import Any

from core import config
from core import eodhd
from core import ettime
from core import page
from ops import job_status


def delivery_record_path(html_path: Path) -> Path:
    """Where the send-once record for this session lives, beside its report."""
    return html_path.parent / "delivered.json"


def write_delivery_record(html_path: Path, record: dict[str, Any]) -> str | None:
    """Record the send so a rerun cannot repeat it. Returns a warning, or None.

    THE EMAIL HAS ALREADY GONE by the time this is called, which makes this the
    one write in the tree whose failure cannot be answered by trying the whole
    step again. A plain write_text raised straight through deliver(), the chain
    stopped before build_archive wrote its finish marker, the watchdog read an
    unfinished chain and relaunched it, and the recipients got the morning
    twice. That is the exact outcome already_delivered exists to prevent,
    reached through the one path it does not cover, and it needs no exotic
    failure: this machine's antivirus intermittently denies a first file write,
    which README records under "When things go wrong".

    So three layers, weakest consequence last. The write goes through a temp
    sibling and os.replace, so a reader never sees half a record. It retries,
    because every documented instance of that denial has cleared on a retry.
    And it never raises: a morning that sent one email and could not say so is
    worse served by a crash than by a loud line in the log, since the crash is
    what summons the second copy.
    """
    path = delivery_record_path(html_path)
    body = json.dumps(record, indent=2, sort_keys=True)
    # core/files.py is the one atomic writer since 2026-09-02, retries included.
    from core import files

    last: Exception | None = None
    try:
        files.write_text_atomically(path, body, attempts=WRITE_ATTEMPTS,
                                    retry_s=WRITE_RETRY_S)
        return None
    except OSError as exc:
        last = exc
    return (
        f"deliver: WARNING the email WAS SENT and the send-once record at {path} "
        f"could not be written after {WRITE_ATTEMPTS} attempts ({last}). Nothing "
        "now stops a rerun of the morning chain sending a second copy. Write that "
        "file by hand, or accept the duplicate."
    )


def already_delivered(html_path: Path) -> dict[str, Any] | None:
    """The record of a send that already happened for this session, if there is one.

    An unreadable record reads as no record. That direction is deliberate and
    it is the opposite of this module's usual caution: a corrupt marker must
    not be able to suppress a morning's only email, and a second copy of a
    report is a far cheaper mistake than no copy at all.
    """
    path = delivery_record_path(html_path)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"deliver: {path.name} exists but could not be read, so this run "
              "treats the morning as undelivered. A second copy is a cheaper "
              "mistake than no copy.")
        return None
    return record if isinstance(record, dict) and record.get("sent_at") else None


_LOCAL_ONLY_RE = re.compile(r'<div class="local-only">.*?</div>\s*', re.S)


def strip_local_only(html: str) -> str:
    """Remove the renderer's footer of relative links before emailing.

    render_report writes a div of links to the previous session, the midday
    page, the archive and the weekly page. They are paths on this machine and
    every one of them is dead in a mail client, so the div goes rather than
    ship four broken links under every report.
    """
    return _LOCAL_ONLY_RE.sub("", html)


def email_subject(html_path: Path, session_date: str) -> str:
    """The report's own title line as the subject, so the inbox says the mood.

    Read from report.md beside the HTML, which is what render_report titled the
    page from. Falls back to the dated generic subject when the markdown is
    not there, which is the case for a hand rendered file.
    """
    markdown_path = html_path.with_suffix(".md")
    if markdown_path.is_file():
        for line in markdown_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return f"{line[2:].strip()} ({session_date})"
    return f"PremarketDesk morning report {session_date}"


def deliver(html_path: Path) -> int:
    # The first morning verification gate. verify_morning.py owns the marker;
    # a human deletes it after watching one real morning's numbers, and until
    # then no email leaves this machine no matter what keys are configured.
    from morning import verify_morning

    if verify_morning.UNVERIFIED_MARKER.exists():
        print(
            f"deliver: refusing to email, the verification gate {verify_morning.UNVERIFIED_MARKER} "
            "exists. Review the gate table from verify_morning.py on a real morning "
            "and delete that file to go live. The report is on disk at "
            f"{html_path}."
        )
        # Gated is a correct outcome, not a failure. Zero recipients is what
        # distinguishes it from a morning that really did send.
        job_status.produced("recipients emailed", 0)
        return 0

    # The watchdog reruns the WHOLE morning chain on the stated reasoning that
    # it is idempotent, and until 2026-08-20 this step was the one place that
    # was not: the chain's finish marker is written by the archive step AFTER
    # this one, so an archive that fails leaves a chain that has already
    # emailed looking unfinished, and the 09:25 pass relaunches it. The
    # recipients got the morning twice. Nothing else in the chain has this
    # shape, because every other step writes a file it can overwrite.
    sent = already_delivered(html_path)
    if sent is not None:
        print(f"deliver: this session was already emailed at {sent.get('sent_at')} "
              f"to {', '.join(sent.get('recipients') or []) or 'unknown recipients'}"
              + (f", Resend id {sent['message_id']}" if sent.get("message_id") else "")
              + f". Not sending again. Delete {delivery_record_path(html_path).name} "
              "to force a resend.")
        job_status.produced("recipients emailed", 0)
        return 0

    api_key = config.resend_api_key()
    recipients = config.email_to()

    if not api_key or not recipients:
        reasons = []
        if not api_key:
            reasons.append("RESEND_API_KEY is not set")
        if not recipients:
            reasons.append("EMAIL_TO is not set")
        print(f"deliver: skipping email, {' and '.join(reasons)}. "
              f"The report is on disk at {html_path}.")
        job_status.produced("recipients emailed", 0)
        return 0

    html = html_path.read_text(encoding="utf-8")
    session_date = html_path.parent.name
    payload = {
        "from": config.email_from(),
        "to": recipients,
        "subject": email_subject(html_path, session_date),
        # The footer of machine local links goes, and every var() is resolved
        # to its literal: a mail client that cannot read a custom property
        # would otherwise render the whole stylesheet's colours and rules as
        # nothing. See page.flatten_variables.
        "html": page.flatten_variables(strip_local_only(html)),
    }
    # A plain text part beside the HTML, from the markdown the HTML was
    # rendered from. A client that cannot show HTML, and a client that strips
    # the style block and leaves a ten column table borderless, both fall back
    # to this rather than to nothing.
    markdown_path = html_path.with_suffix(".md")
    if markdown_path.is_file():
        payload["text"] = markdown_path.read_text(encoding="utf-8")

    session = eodhd.build_session()
    try:
        response = session.post(
            config.RESEND_SEND_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
    except Exception as exc:
        # Broad catch, so the text is untrusted: scrub before it can reach a
        # log. scrub_secrets covers the Resend key as well as the data token.
        print(f"deliver: FAILED to reach Resend: {config.scrub_secrets(exc)}")
        return 1

    if response.status_code >= 300:
        print(f"deliver: Resend answered {response.status_code}: "
              f"{config.scrub_secrets(response.text[:400])}")
        return 1

    try:
        message_id = response.json().get("id")
    except (ValueError, json.JSONDecodeError):
        message_id = None
    # Written before the step reports success, so a crash between the POST and
    # here cannot leave a sent email with no record of it. It cannot raise: see
    # write_delivery_record on why a failure here must not end the step.
    warning = write_delivery_record(html_path, {
        "sent_at": ettime.stamp(ettime.now_et()),
        "recipients": recipients,
        "message_id": message_id,
        "session_date": session_date,
        "note": ("the send-once record. deliver.py refuses to email this session "
                 "again while this file exists, so a watchdog rerun of the "
                 "morning chain does not send a second copy."),
    })
    print(f"deliver: sent to {', '.join(recipients)}"
          + (f", Resend id {message_id}" if message_id else ""))
    if warning:
        print(warning)
        job_status.failed("the email was sent and the send-once record could "
                          "not be written; a chain rerun would send it again")
    job_status.produced("recipients emailed", len(recipients))
    return 0


# How hard write_delivery_record tries. Not CRITERIA keys: nothing here screens
# a market, and this file's threshold rule covers decision thresholds rather
# than the retry shape of one write. Sized against the documented antivirus
# denial, which clears within a second every time it has been seen.
WRITE_ATTEMPTS = 4
WRITE_RETRY_S = 0.5

# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Email report.html through Resend.")
    parser.add_argument("--html", metavar="PATH",
                        help="Rendered report to send. Defaults to runs/<today>/report.html.")
    args = parser.parse_args(argv)

    html_path = (
        Path(args.html) if args.html
        else config.run_path(ettime.today_et().isoformat()) / "report.html"
    )
    if not html_path.is_file():
        print(f"deliver: there is no rendered report at {html_path}. "
              "Run render_report.py first.")
        return 1

    return deliver(html_path)


if __name__ == "__main__":
    sys.exit(job_status.run("deliver", main, ok_codes=OK_CODES))
