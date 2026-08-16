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
import sys
from pathlib import Path

from core import config
from core import eodhd
from core import ettime
from ops import job_status


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
        "subject": f"PremarketDesk morning report {session_date}",
        "html": html,
    }

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
    print(f"deliver: sent to {', '.join(recipients)}"
          + (f", Resend id {message_id}" if message_id else ""))
    job_status.produced("recipients emailed", len(recipients))
    return 0


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
        else config.run_dir(ettime.today_et().isoformat()) / "report.html"
    )
    if not html_path.is_file():
        print(f"deliver: there is no rendered report at {html_path}. "
              "Run render_report.py first.")
        return 1

    return deliver(html_path)


if __name__ == "__main__":
    sys.exit(job_status.run("deliver", main, ok_codes=OK_CODES))
