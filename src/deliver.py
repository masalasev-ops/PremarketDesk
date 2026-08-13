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

import config
import eodhd
import ettime


def deliver(html_path: Path) -> int:
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
        print(f"deliver: FAILED to reach Resend: {exc}")
        return 1

    if response.status_code >= 300:
        print(f"deliver: Resend answered {response.status_code}: {response.text[:400]}")
        return 1

    try:
        message_id = response.json().get("id")
    except (ValueError, json.JSONDecodeError):
        message_id = None
    print(f"deliver: sent to {', '.join(recipients)}"
          + (f", Resend id {message_id}" if message_id else ""))
    return 0


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
    sys.exit(main())
