"""The desk: one document at site/PremarketDesk.html carrying every session.

Three modules, in the order they run:

  compact   a run directory becomes the one payload every screen draws from,
            and the summary row the sessions table keeps
  assets    the stylesheet and the application, as strings, the way
            core/page.py holds REPORT_CSS
  render    the shell, the inlined payloads and the application, written once

READS AND RENDERS, NOTHING ELSE. No vendor call, no measurement, no threshold
of its own. Every number on every screen is already in packet.json,
midday_packet.json or the database when this package runs. That is
night/weekly_page.py's constraint and the reason is its own: a reporting layer
that fetches is a second pipeline to keep right.

The seven screens and their reasoning are in doc/SCREENS.md.
"""
