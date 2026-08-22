"""One page that says whether the week worked, from what is already on disk.

Everything here was being written and nothing was reading it. job-status.jsonl
records every scheduled step of every run; the meter trail records the shared
quota before and after each of them; quantifier-flags.jsonl records every
sentence the guard stopped; runs/<date>/verify_intraday.json records the
definitive collector against vendor comparison; picks records what was
published and, since 2026-08-21, what was actually true. Five sources, all
append only, none of them ever read back.

READS AND RENDERS, NOTHING ELSE. No new data, no new table, no new scheduled
job. It adds no measurement of its own and takes no vendor call: if a number is
not already on disk it does not appear here. That constraint is the reason this
is worth having at all, because a reporting layer that fetches is a second
pipeline to keep right.

Four sections and no more, in the order a person actually asks them:

  Did it run           jobs fired, non zero exits, mornings that produced a
                       report at all
  Is it trustworthy    the collector against vendor comparison as a SERIES
                       rather than one reading, and what the truth pass has
                       measured the capture share actually to be
  What did it publish  candidates a morning, how many reached each watchlist,
                       how many went unscored and why
  What did it cost     this project's spend against the shared key's siblings,
                       and the closest any morning came to the preflight floor

    PYTHONPATH=src .venv/Scripts/python.exe -m night.weekly_page
    PYTHONPATH=src .venv/Scripts/python.exe -m night.weekly_page --days 30
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import statistics
import sys
from typing import Any

from core import config
from core import criteria
from core import ettime
from core import store
from night import true_volume
from ops import job_status

_CRIT = criteria.load()

OUT_PATH = config.PROJECT_ROOT / "site" / "Weekly.html"


def _days(window: int) -> list[str]:
    today = ettime.today_et()
    return [(today - dt.timedelta(days=back)).isoformat()
            for back in range(window - 1, -1, -1)]


def _read_jsonl(path, days: set[str], key: str) -> list[dict[str, Any]]:
    """Rows whose date field falls inside the window. Bad lines are skipped.

    A malformed line in an append only log is not a reason to render nothing.
    It is a reason to render everything else, and the count of what was skipped
    goes on the page so a silently shrinking series cannot look like a quiet
    week.
    """
    rows: list[dict[str, Any]] = []
    skipped = 0
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        stamp = str(row.get(key) or "")[:10]
        if stamp in days:
            rows.append(row)
    if skipped:
        rows.append({"_skipped": skipped})
    return rows


def did_it_run(days: list[str]) -> dict[str, Any]:
    window = set(days)
    rows = [r for r in job_status.records() if str(r.get("started_at"))[:10] in window]
    by_day: dict[str, dict[str, Any]] = {
        day: {"steps": 0, "ok": 0, "failed": [], "report": False} for day in days}
    for row in rows:
        day = str(row["started_at"])[:10]
        seen = by_day[day]
        seen["steps"] += 1
        if row.get("status") == job_status.STATUS_OK:
            seen["ok"] += 1
        else:
            seen["failed"].append(
                f"{row.get('step')} ({row.get('status')}"
                + (f", exit {row['exit_code']}" if row.get("exit_code") not in (0, None) else "")
                + ")")
    for day in days:
        by_day[day]["report"] = (config.run_path(day) / "report.md").is_file()
    return {"by_day": by_day,
            "steps": sum(v["steps"] for v in by_day.values()),
            "failures": sum(len(v["failed"]) for v in by_day.values()),
            "reports": sum(1 for v in by_day.values() if v["report"])}


def is_it_trustworthy(days: list[str]) -> dict[str, Any]:
    series = []
    for day in days:
        path = config.run_path(day) / "verify_intraday.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        series.append({
            "day": payload.get("day") or day,
            "compared": payload.get("compared"),
            "median_abs_pct": payload.get("median_abs_pct"),
            "aggregate_ratio": payload.get("aggregate_ratio"),
            "within_one_percent": payload.get("within_one_percent"),
            "unavailable": payload.get("unavailable"),
        })

    with store.session() as connection:
        store.init(connection)
        rows = connection.execute(
            "SELECT date, ticker, capture_observed, estimate_error, "
            "collector_window_share FROM picks WHERE source='live' "
            "AND capture_observed IS NOT NULL ORDER BY date, ticker"
        ).fetchall()
    shares = [r["capture_observed"] for r in rows]
    errors = [r["estimate_error"] for r in rows if r["estimate_error"] is not None]
    windows = [r["collector_window_share"] for r in rows
               if r["collector_window_share"] is not None]
    shipped = _CRIT.number("collector", "premarket_capture_rate")
    return {
        "series": series,
        "capture": {
            "rows": len(shares),
            "sessions": len({r["date"] for r in rows}),
            "low": min(shares) if shares else None,
            "high": max(shares) if shares else None,
            "median": statistics.median(shares) if shares else None,
            "below_shipped": sum(1 for s in shares if s < shipped),
            "shipped": shipped,
            "spread": (max(shares) / min(shares)) if shares and min(shares) else None,
        },
        "estimate_error": {
            "low": min(errors) if errors else None,
            "high": max(errors) if errors else None,
            "median": statistics.median(errors) if errors else None,
            "understated": sum(1 for e in errors if e < 1.0),
            "rows": len(errors),
        },
        "window_share": {
            "median": statistics.median(windows) if windows else None,
            "low": min(windows) if windows else None,
            "high": max(windows) if windows else None,
        },
        "flags": _read_jsonl(config.DATA_DIR / "quantifier-flags.jsonl",
                             set(days), "recorded_at"),
    }


_PACKET_FAILURES: dict[str, dict[str, bool]] = {}


def _volume_was_the_only_failure(day: str, ticker: str) -> bool:
    """Did this name fail the day screen on premarket_rvol and nothing else.

    Read from runs/<day>/packet.json, which is the only record of WHY a
    candidate failed; picks carries the verdict and not the reasons. Cached per
    day because the page walks every row of every session in the window.

    A name that also failed the prior day high does not join a watchlist
    however large its true volume turns out to be, and counting it would
    overstate the estimate's cost.
    """
    if day not in _PACKET_FAILURES:
        found: dict[str, bool] = {}
        path = config.run_path(day) / "packet.json"
        if path.is_file():
            try:
                packet = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                packet = {}
            for candidate in packet.get("candidates") or []:
                only, resolvable = true_volume._only_failure_was_volume(candidate)
                found[candidate["symbol"]] = bool(only and resolvable)
        _PACKET_FAILURES[day] = found
    return _PACKET_FAILURES[day].get(ticker, False)


def what_did_it_publish(days: list[str]) -> dict[str, Any]:
    with store.session() as connection:
        store.init(connection)
        rows = connection.execute(
            "SELECT date, ticker, day_eligible, swing_eligible, score, "
            "score_unavailable, volume_measure_used, pm_rvol, pm_rvol_true "
            "FROM picks WHERE source='live' AND date >= ? ORDER BY date",
            (days[0],),
        ).fetchall()
    by_day: dict[str, dict[str, Any]] = {}
    reasons: dict[str, int] = {}
    for row in rows:
        seen = by_day.setdefault(row["date"], {
            "candidates": 0, "day": 0, "swing": 0, "unscored": 0,
            "rescued_by_truth": 0})
        seen["candidates"] += 1
        seen["day"] += int(bool(row["day_eligible"]))
        seen["swing"] += int(bool(row["swing_eligible"]))
        if row["score"] is None:
            seen["unscored"] += 1
            for reason in str(row["score_unavailable"] or "unrecorded").split(", "):
                reasons[reason] = reasons.get(reason, 0) + 1
        # A name the morning left off the day watchlist that the night's true
        # numbers would have PUT ON IT. Not the same as a name whose true RVOL
        # clears the floor, and the difference is large: on 2026-08-20 twelve
        # candidates, ten cleared the floor on true volume and only SEVEN would
        # have been admitted, because the other three also failed the prior day
        # high, which no volume number touches. This column counted ten until
        # 2026-08-21 and overstated the defect in the same direction, and for
        # the same reason, as the estimate understated it.
        #
        # The extra condition comes from the packet, which is the only record
        # of WHY a name failed. A session whose packet is missing counts
        # nothing here rather than counting everything.
        #
        # The BEST available ratio comes from true_volume.volume_ratio, which
        # refuses to hand back the estimate when the measurement is in the same
        # row. The comparison against pm_rvol below is the one place the
        # estimate is read deliberately, because the whole point of the column
        # is the difference between the two.
        floor = _CRIT.rule("day_setup", "premarket_rvol")
        best, which = true_volume.volume_ratio(row)
        if (which == "measured" and floor.test(best)
                and not row["day_eligible"]
                and _volume_was_the_only_failure(row["date"], row["ticker"])):
            seen["rescued_by_truth"] += 1
    return {"by_day": by_day, "reasons": reasons,
            "floor": _CRIT.rule("day_setup", "premarket_rvol").describe()}


def what_did_it_cost(days: list[str]) -> dict[str, Any]:
    """What the shared counter moved, per QUOTA day.

    THE ROW LABELS ARE QUOTA DAYS AND NOT ET DAYS, and the difference is the
    whole of the defect this replaces. meter-<day>.log is written one file per
    quota day, the counter resets at 00:00 UTC, and CRITERIA [Quota] says in
    terms that one ET weekday spans two of them: the morning jobs bill to the
    quota day that opened the previous evening and the 22:15 nightly bills to
    the next. So each file OPENS with pre-roll readings carrying the previous
    counter, flagged meter_day_is_stale, followed by a counter:rolled row.

    This used to filter the file by ET DATE and subtract the first surviving
    api_requests from the last, which straddled the reset. Measured on the real
    log for quota day 2026-08-21: 93,070 minus a pre-roll 81,309 published
    11,761 for a day whose own counter moved 26,309 to 93,070, or 66,761. A
    narrower window excluded the pre-roll rows and published 7,608 instead, from
    a first reading taken most of the way through the day. Both are wrong and
    both are wrong DOWNWARD, on the one page whose subject is what the key cost.

    Fixed by reading the counter this file is about: the rows that are not
    pre-roll. max(moved, 0) is kept, but it is now a guard against a truncated
    file rather than the thing hiding the reset.
    """
    per_day: dict[str, dict[str, Any]] = {}
    for day in days:
        # NOT filtered by ET date. The file is already one quota day; what has
        # to be excluded is the pre-roll readings inside it, which belong to
        # the previous counter and are flagged as such by meter_sampler.
        trail = [r for r in job_status.read_trail(day)
                 if not r.get("meter_day_is_stale")]
        if not trail:
            continue
        # OURS is the movement across our own steps, entry to exit. It is an
        # UPPER bound: a sibling spending while one of our steps runs lands
        # inside the same delta and cannot be separated, because the vendor
        # publishes one counter for the whole key. Stated as a bound rather
        # than as a figure, since the alternative is a number that looks exact
        # and is not.
        ours = sum(r.get("delta_since_previous") or 0
                   for r in trail if r.get("when") == "exit")
        first, last = trail[0], trail[-1]
        moved = (last.get("api_requests") or 0) - (first.get("api_requests") or 0)
        per_day[day] = {
            "ours_upper_bound": max(ours, 0),
            "total_moved": max(moved, 0),
            "siblings_lower_bound": max(moved - ours, 0),
            "low_water_remaining": min(
                (r.get("remaining") for r in trail
                 if r.get("remaining") is not None), default=None),
        }

    closest = None
    degrade = _CRIT.integer("quota", "degrade_below_remaining")
    refuse = _CRIT.integer("quota", "refuse_below_remaining")
    for day in days:
        path = config.run_path(day) / "packet.json"
        if not path.is_file():
            continue
        try:
            preflight = (json.loads(path.read_text(encoding="utf-8"))
                         .get("quota_preflight") or {})
        except (ValueError, OSError):
            continue
        remaining = preflight.get("remaining")
        if remaining is None:
            continue
        if closest is None or remaining < closest["remaining"]:
            closest = {"day": day, "remaining": remaining,
                       "degraded": bool(preflight.get("degraded")),
                       "read_at": preflight.get("read_at")}
    return {"per_day": per_day, "closest": closest,
            "degrade_below": degrade, "refuse_below": refuse}


# ------------------------------------------------------------------ rendering

def _n(value: Any, places: int = 0) -> str:
    if value is None:
        return "<span class=null>null</span>"
    if isinstance(value, float):
        return f"{value:,.{places}f}"
    return f"{value:,}"


def _esc(value: Any) -> str:
    return html.escape(str(value))


_CSS = """
:root{--bg:#faf9f7;--ink:#1c1b19;--dim:#6b6862;--line:#e0ddd6;--card:#fff;
--good:#1f6f4a;--warn:#a8681a;--bad:#a52f2f;--accent:#2b4c7e}
:root:not([data-theme=light]) {}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#16151a;--ink:#eceae6;--dim:#96938c;--line:#2e2c33;--card:#1e1d23;
--good:#5fbf8f;--warn:#d99a4e;--bad:#e0726f;--accent:#7fa6d9}}
:root[data-theme=dark]{--bg:#16151a;--ink:#eceae6;--dim:#96938c;--line:#2e2c33;
--card:#1e1d23;--good:#5fbf8f;--warn:#d99a4e;--bad:#e0726f;--accent:#7fa6d9}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:64rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
h1{font-size:1.6rem;margin:0 0 .2rem;letter-spacing:-.01em}
h2{font-size:1.05rem;margin:2.4rem 0 .2rem;letter-spacing:.06em;
text-transform:uppercase;color:var(--accent)}
.sub{color:var(--dim);margin:0 0 1.6rem;font-size:.9rem}
.note{color:var(--dim);font-size:.86rem;margin:.35rem 0 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:1rem 1.1rem;margin:.75rem 0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.88rem;
font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:.34rem .55rem;border-bottom:1px solid var(--line);
white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--dim);font-weight:600;font-size:.78rem;text-transform:uppercase;
letter-spacing:.04em}
tr:last-child td{border-bottom:none}
.big{font-size:1.7rem;font-weight:600;letter-spacing:-.02em}
.row{display:flex;flex-wrap:wrap;gap:.75rem}
.row>.card{flex:1 1 11rem;margin:0}
.lab{color:var(--dim);font-size:.78rem;text-transform:uppercase;
letter-spacing:.05em;margin-bottom:.25rem}
.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.null{color:var(--dim);font-style:italic}
.bar{height:7px;background:var(--line);border-radius:4px;overflow:hidden;
margin-top:.4rem}
.bar>i{display:block;height:100%;background:var(--accent)}
footer{color:var(--dim);font-size:.82rem;margin-top:3rem;
border-top:1px solid var(--line);padding-top:1rem}
"""


def render(days: list[str], ran: dict, trust: dict, published: dict,
           cost: dict) -> str:
    out: list[str] = []
    add = out.append
    add("<title>PremarketDesk Weekly</title>")
    add(f"<style>{_CSS}</style>")
    add("<div class=wrap>")
    add("<h1>PremarketDesk weekly</h1>")
    add(f"<p class=sub>{days[0]} to {days[-1]}, rendered "
        f"{_esc(ettime.stamp(ettime.now_et()))}. Every number here was already "
        "on disk. This page takes no vendor call and adds no measurement.</p>")

    # 1 -----------------------------------------------------------------
    add("<h2>Did it run</h2>")
    add("<div class=row>")
    add(f"<div class=card><div class=lab>Steps recorded</div>"
        f"<div class=big>{_n(ran['steps'])}</div></div>")
    klass = "bad" if ran["failures"] else "good"
    add(f"<div class=card><div class=lab>Non zero exits</div>"
        f"<div class='big {klass}'>{_n(ran['failures'])}</div></div>")
    add(f"<div class=card><div class=lab>Mornings with a report</div>"
        f"<div class=big>{_n(ran['reports'])} of {len(days)}</div></div>")
    add("</div>")
    add("<div class='card scroll'><table><tr><th>Day</th><th>Steps</th>"
        "<th>OK</th><th>Report</th><th>What failed</th></tr>")
    for day in days:
        seen = ran["by_day"][day]
        if not seen["steps"] and not seen["report"]:
            continue
        failed = ", ".join(seen["failed"]) or "<span class=good>nothing</span>"
        mark = "yes" if seen["report"] else "<span class=dim>no</span>"
        add(f"<tr><td>{day}</td><td>{_n(seen['steps'])}</td>"
            f"<td>{_n(seen['ok'])}</td><td>{mark}</td><td>{failed}</td></tr>")
    add("</table></div>")

    # 2 -----------------------------------------------------------------
    add("<h2>Is the data trustworthy</h2>")
    add("<p class=note>The collector against the vendor on identical minutes, "
        "as a series. One reading says the socket missed the tape that day; a "
        "series says whether it is stable enough to correct for.</p>")
    add("<div class='card scroll'><table><tr><th>Session</th>"
        "<th>Symbols compared</th><th>Median abs gap %</th>"
        "<th>Aggregate ratio</th><th>Within 1%</th><th>Unreached</th></tr>")
    for row in trust["series"]:
        add(f"<tr><td>{_esc(row['day'])}</td><td>{_n(row['compared'])}</td>"
            f"<td>{_n(row['median_abs_pct'], 2)}</td>"
            f"<td>{_n(row['aggregate_ratio'], 4)}</td>"
            f"<td>{_n(row['within_one_percent'])}</td>"
            f"<td>{_n(row['unavailable'])}</td></tr>")
    if not trust["series"]:
        add("<tr><td colspan=6><span class=null>no verify_intraday.json in "
            "this window</span></td></tr>")
    add("</table></div>")

    cap = trust["capture"]
    if cap["rows"]:
        add(f"<p class=note>What the capture share ACTUALLY was, from the "
            f"nightly truth pass, over {_n(cap['rows'])} rows across "
            f"{_n(cap['sessions'])} session(s). The morning divides by one "
            f"number, {cap['shipped']}.</p>")
        add("<div class=row>")
        add(f"<div class=card><div class=lab>Median observed</div>"
            f"<div class=big>{_n(cap['median'], 4)}</div>"
            f"<div class=note>shipped {cap['shipped']}</div></div>")
        add(f"<div class=card><div class=lab>Range</div>"
            f"<div class=big>{_n(cap['low'], 4)} to {_n(cap['high'], 4)}</div>"
            + (f"<div class='note bad'>{cap['spread']:.1f} fold spread</div>"
               if cap["spread"] else "") + "</div>")
        add(f"<div class=card><div class=lab>Below the shipped share</div>"
            f"<div class='big warn'>{_n(cap['below_shipped'])} of "
            f"{_n(cap['rows'])}</div>"
            "<div class=note>divided by too large a share, so understated"
            "</div></div>")
        add("</div>")
        err = trust["estimate_error"]
        if err["rows"]:
            add(f"<div class=card><div class=lab>How far the published number "
                f"was out</div><div class=big>{_n(err['median'], 3)} median, "
                f"{_n(err['low'], 3)} to {_n(err['high'], 3)}</div>"
                f"<div class=note>Published volume over true volume. 1.0 is "
                f"exactly right. {_n(err['understated'])} of the "
                f"{_n(err['rows'])} rows that carried an estimate at all came "
                f"in under it. The other {_n(cap['rows'] - err['rows'])} "
                "predate the capture correction, so the morning published raw "
                "socket volume and there is no estimate to score.</div></div>")
        win = trust["window_share"]
        if win["median"] is not None:
            add(f"<div class=card><div class=lab>What the 07:20 start sees of "
                f"the 04:00 tape</div><div class=big>{_n(win['median'], 4)}"
                f"</div><div class=note>Range {_n(win['low'], 4)} to "
                f"{_n(win['high'], 4)}. This is the other lower bound, called "
                "arithmetic since 2026-08-14 and measured only since the truth "
                "pass existed.</div></div>")
    else:
        add("<div class=card><span class=null>The truth pass has not written a "
            "capture_observed yet, so the capture share is still an assumption "
            "rather than a measurement.</span></div>")

    flags = [f for f in trust["flags"] if "_skipped" not in f]
    add(f"<div class=card><div class=lab>Sentences the quantifier guard "
        f"stopped</div><div class=big>{_n(len(flags))}</div>"
        + ("".join(f"<div class=note>{_esc(f.get('session'))}: "
                   f"{_esc(str(f.get('sentence'))[:160])}</div>"
                   for f in flags[:5]) if flags else
           "<div class=note>No sentence in this window overstated a set.</div>")
        + "</div>")

    # 3 -----------------------------------------------------------------
    add("<h2>What did it publish</h2>")
    add("<div class='card scroll'><table><tr><th>Session</th>"
        "<th>Candidates</th><th>Day watchlist</th><th>Swing watchlist</th>"
        "<th>Unscored</th><th>Would have been admitted on true volume</th></tr>")
    for day in days:
        seen = published["by_day"].get(day)
        if not seen:
            continue
        add(f"<tr><td>{day}</td><td>{_n(seen['candidates'])}</td>"
            f"<td>{_n(seen['day'])}</td><td>{_n(seen['swing'])}</td>"
            f"<td>{_n(seen['unscored'])}</td>"
            f"<td>{_n(seen['rescued_by_truth'])}</td></tr>")
    if not published["by_day"]:
        add("<tr><td colspan=6><span class=null>no live picks rows in this "
            "window</span></td></tr>")
    add("</table>")
    add(f"<p class=note>The last column counts names the morning left OFF the "
        f"day watchlist that the night's true volume would have put on it: "
        f"premarket_rvol was the only condition they failed, against the day "
        f"screen's {_esc(published['floor'])}, and the true number clears it. "
        "A name that also failed the prior day high does not join a watchlist "
        "however large its volume turns out to be, so it is not counted here. "
        "This is the cost of the estimate in names rather than in ratios.</p>"
        "</div>")
    if published["reasons"]:
        add("<div class=card><div class=lab>Why a row went unscored</div>"
            "<table>")
        for reason, count in sorted(published["reasons"].items(),
                                    key=lambda kv: -kv[1]):
            add(f"<tr><td>{_esc(reason)}</td><td>{_n(count)}</td></tr>")
        add("</table><p class=note>Unscored is not low conviction. A score "
            "component input was never observed, and unknown is not zero.</p>"
            "</div>")

    # 4 -----------------------------------------------------------------
    add("<h2>What did it cost</h2>")
    add("<p class=note>The EODHD key is SHARED. The vendor publishes one "
        "counter for the whole key, so a sibling spending while one of this "
        "project's steps runs lands inside the same delta and cannot be "
        "separated. Ours is therefore an upper bound and the siblings' a lower "
        "bound, stated as bounds rather than as figures that would look exact "
        "and would not be.</p>")
    add("<div class='card scroll'><table><tr><th>Day</th>"
        "<th>Ours, at most</th><th>Siblings, at least</th>"
        "<th>Key moved</th><th>Lowest remaining seen</th></tr>")
    for day in days:
        seen = cost["per_day"].get(day)
        if not seen:
            continue
        add(f"<tr><td>{day}</td><td>{_n(seen['ours_upper_bound'])}</td>"
            f"<td>{_n(seen['siblings_lower_bound'])}</td>"
            f"<td>{_n(seen['total_moved'])}</td>"
            f"<td>{_n(seen['low_water_remaining'])}</td></tr>")
    if not cost["per_day"]:
        add("<tr><td colspan=5><span class=null>no meter trail in this window"
            "</span></td></tr>")
    add("</table></div>")
    closest = cost["closest"]
    if closest:
        margin = closest["remaining"] - cost["degrade_below"]
        klass = "bad" if margin <= 0 else ("warn" if margin < 5000 else "good")
        add(f"<div class=card><div class=lab>Closest any morning came to the "
            f"preflight floor</div>"
            f"<div class='big {klass}'>{_n(margin)}</div>"
            f"<div class=note>{closest['day']}: {_n(closest['remaining'])} "
            f"calls left at preflight, against a degrade floor of "
            f"{_n(cost['degrade_below'])} and a refuse floor of "
            f"{_n(cost['refuse_below'])}. "
            + ("The morning ran degraded." if closest["degraded"] else
               "The morning ran on full evidence.")
            + "</div></div>")

    add("<footer>Rendered by night/weekly_page.py at the end of the nightly "
        "job. It reads job-status.jsonl, the meter trail, "
        "quantifier-flags.jsonl, runs/&lt;date&gt;/verify_intraday.json and "
        "the picks table, and writes this file. Nothing else.</footer>")
    add("</div>")
    return "\n".join(out)


def build(window: int) -> Any:
    days = _days(window)
    page = render(days, did_it_run(days), is_it_trustworthy(days),
                  what_did_it_publish(days), what_did_it_cost(days))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    return OUT_PATH


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the weekly page from what is already on disk.")
    parser.add_argument("--days", type=int, default=7, metavar="N",
                        help="How many days back the page covers.")
    args = parser.parse_args(argv)
    out = build(max(1, args.days))
    print(f"weekly: wrote {out} covering {args.days} day(s), "
          f"{out.stat().st_size:,} bytes, no vendor call")
    job_status.produced("weekly page bytes", out.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("weekly", main, ok_codes=OK_CODES))
