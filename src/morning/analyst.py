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
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import ettime
from ops import job_status

_CRIT = criteria.load()

# One to six characters. It was two to six until 2026-08-14, which made every
# single letter listing invisible to the containment check: a fabricated F or
# T row returned invented=[] and the run printed that containment passed.
# Those are the symbols a model is most likely to invent, because they are the
# most familiar ones in the market.
#
# Widening it costs almost nothing measurably. Across both archived reports it
# produced zero new invented-ticker findings and raised the claims examined
# from 25 to 29 and from 20 to 23.
#
# [corrected 2026-08-20: this comment used to end "so single character tokens
# are additionally required to be real listings, which _single_letter_listings
# supplies from universe.json. A one letter token that is not a listing cannot
# be a ticker claim and is dropped before it can become one." No such helper
# exists, and none ever did. There is no pre-drop.]
#
# What actually happens: a one character token is treated exactly like a six
# character one. It enters the claims set in _ticker_claims, and the only test
# applied to it is the `token in known_symbols` intersection in check_report,
# which every token of every length goes through. So the guard against a stray
# capital letter in prose is the stopword list, which is why A and I are on it
# and why the note beside them says they are stopped in PROSE only: a Ticker
# COLUMN cell reading A is unambiguous and is still checked, and that is the
# case the widening was for.
#
# The correction matters beyond tidiness. coverage["tokens_examined"] and
# coverage["claims_checked"] are counts of tokens that reached the
# intersection, not of tokens that survived a listings pre-filter, and anyone
# reasoning about the guard's coverage from the old comment would have read
# them as narrower than they are.
_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]{0,5}\b")
_DOLLAR_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,5})\b")


# ------------------------------------------------------------ CLI plumbing

def resolve_cli() -> str:
    """Find the claude CLI in a form Windows CreateProcess can run.

    The npm claude.cmd shim just forwards to a native claude.exe next to it,
    and cmd.exe mangles empty string arguments on the way through, which
    silently breaks --tools "". So the real executable is preferred, found
    relative to the shim, and the shim itself is only a last resort.
    """
    shim = shutil.which("claude.cmd") or shutil.which("claude")
    if shim:
        exe = (Path(shim).parent / "node_modules" / "@anthropic-ai"
               / "claude-code" / "bin" / "claude.exe")
        if exe.is_file():
            return str(exe)
        return shim
    raise FileNotFoundError(
        "The claude CLI is not on PATH. The narrative pass cannot run without it."
    )


def _scrubbed_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in config.FORBIDDEN_KEYS:
        env.pop(key, None)
    return env


_RULE = "----------------------------------------------------------------"


def _compose_stdin(packet_text: str, correction: str | None = None) -> str:
    prompt = config.ANALYST_PROMPT_PATH.read_text(encoding="utf-8")
    template = config.REPORT_TEMPLATE_PATH.read_text(encoding="utf-8")
    document = (
        f"{prompt}\n\n"
        f"{_RULE}\n\n"
        f"{template}\n\n"
        f"{_RULE}\n\n"
        "Here is this morning's packet.json, your only source:\n\n"
        f"{packet_text}\n"
    )
    if correction:
        # Last, so it is the final thing read before the answer is written.
        # A regeneration that repeats the rejected sentence has cost the
        # morning its narrative for nothing, and a blind retry is a coin
        # flip: naming the sentence is what makes the second attempt worth
        # spending.
        document += f"\n{_RULE}\n\n{correction}\n"
    return document


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


def invoke_claude(
    packet_text: str, correction: str | None = None
) -> tuple[str | None, dict[str, Any], str | None, str]:
    """Run the CLI. Returns (report_text, usage_record, error, failure_kind).

    failure_kind is "ok" on success, "timeout" when the last attempt ran out
    of clock, "failed" for every other way the CLI can disappoint.

    correction, when given, is appended to the piped document. It carries the
    reason a previous answer was thrown away, so a regeneration is told what
    to avoid rather than asked to differ by luck.
    """
    model = _CRIT.text("analyst", "model")
    timeout_s = _CRIT.integer("analyst", "timeout_s")
    attempts = _CRIT.integer("analyst", "max_attempts")
    try:
        # One text generation, not an agent loop. --tools "" removes every
        # tool, so there is nothing to take a second turn on (verified: this
        # CLI version has no turn cap flag, and none is needed without
        # tools). The one line system prompt replaces the CLI's large agent
        # system prompt; the piped document is the entire instruction. The
        # recorded num_turns must come back 1.
        command = [
            resolve_cli(), "-p", "--model", model, "--output-format", "json",
            "--tools", "", "--effort", _CRIT.text("analyst", "effort"),
            "--system-prompt",
            "You are the narrative pass of PremarketDesk. Follow the piped "
            "instructions exactly and output only the finished report markdown.",
        ]
    except FileNotFoundError as exc:
        return None, {}, str(exc), "failed"
    stdin_doc = _compose_stdin(packet_text, correction)

    last_error = None
    last_kind = "failed"
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
            last_kind = "timeout"
            print(f"analyst: {last_error}")
            continue
        except OSError as exc:
            return None, {}, f"claude CLI could not be started: {exc}", "failed"

        if proc.returncode != 0:
            last_error = (
                f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:400]}"
            )
            last_kind = "failed"
            print(f"analyst: {last_error}")
            continue

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            last_error = f"claude CLI output was not JSON: {exc}"
            last_kind = "failed"
            print(f"analyst: {last_error}")
            continue

        # VALID JSON IS NOT THE SAME AS THE SHAPE THIS EXPECTS. A bare array,
        # string, number or null parses cleanly and then raises AttributeError
        # on the .get() below, out of the module, with no report written at all.
        # Every other unusable answer here degrades to the retry and then to the
        # fallback report, which is the whole reason the fallback exists, and
        # this was the one shape that skipped both. A CLI version change is the
        # likeliest way to meet it.
        if not isinstance(payload, dict):
            last_error = (f"claude CLI output was JSON but not an object: "
                          f"{type(payload).__name__}")
            last_kind = "failed"
            print(f"analyst: {last_error}")
            continue

        if payload.get("is_error") or payload.get("subtype") != "success":
            last_error = (
                f"claude CLI reported an error result: subtype "
                f"{payload.get('subtype')!r}, result {str(payload.get('result'))[:300]!r}"
            )
            last_kind = "failed"
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
        return _trim_to_report(str(payload.get("result") or "")), record, None, "ok"

    return None, {}, last_error or "claude CLI failed for an unrecorded reason", last_kind


# ------------------------------------------------- the fallback report

def _f(value: Any, digits: int = 2) -> str:
    if value is None:
        return "null"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _cap(value: Any) -> str:
    if value is None:
        return "null"
    number = float(value)
    if number >= 1e9:
        return f"{number / 1e9:.2f}B"
    return f"{number / 1e6:.0f}M"


def _cell(value: Any) -> str:
    """A free text value, safe to drop into a markdown table cell.

    An unescaped pipe in vendor text ends the cell early. python-markdown's
    tables extension does not complain: it discards every cell past the header
    count, so a headline reading "Q2 beat | guidance raised" reaches the
    delivered HTML as "Q2 beat" and the rest is gone with nothing said. Feeds
    put pipes in headlines constantly, and this table is the fallback report,
    which is what a reader gets on the mornings the narrative already failed.
    Newlines are flattened for the same reason, one row per row.
    """
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _bare(symbol: str) -> str:
    return str(symbol).split(".")[0]


def _conviction(candidate: dict[str, Any]) -> str:
    """A null score is unscored, never a low bucket. See CRITERIA Score buckets."""
    if candidate.get("score") is None:
        return "unscored"
    return str(candidate.get("conviction"))


# The two ways the narrative can fail to reach the page, worded as the
# disclaimer says them. They are different failures and the reader has to be
# able to tell them apart: unavailable means the CLI never answered, withheld
# means it answered twice and Python refused what it said. Calling the second
# one unavailable would be the fallback lying about its own provenance, which
# is the single thing this report exists not to do.
CAUSE_UNAVAILABLE = "the narrative pass was unavailable"
CAUSE_WITHHELD = "the narrative pass was withheld"

_FALLBACK_TITLES = {
    CAUSE_UNAVAILABLE: "# PremarketDesk: numbers only, narrative unavailable",
    CAUSE_WITHHELD: "# PremarketDesk: numbers only, narrative withheld",
}


def fallback_report(
    packet: dict[str, Any], reason: str, cause: str = CAUSE_UNAVAILABLE
) -> str:
    """The report the morning gets when the model's answer cannot be used.

    Every number straight from the packet, no narrative, the same section
    skeleton as the template so downstream rendering and reading habits hold.
    The disclaimer line carries the failure reason, because a report that
    silently degraded would be a report that lied about its own provenance.

    Its prose is written in counts rather than quantifiers, for the same
    reason the template is: "0 of 12" carries the denominator that "none are
    eligible" throws away, and a reader should not have to learn two dialects
    depending on which pass wrote the morning. That the quantifier guard
    would also pass this text is a consequence rather than the point. The
    guard is never run over this function's output, because a fallback the
    guard rejected would leave the morning with nothing at all, and because
    the withheld disclaimer quotes the offending sentence as evidence and
    evidence must be quotable.
    """
    candidates = packet.get("candidates", [])
    no_rvol = [_bare(c["symbol"]) for c in candidates if c.get("pm_rvol") is None]
    partial = [
        _bare(c["symbol"]) for c in candidates
        if c.get("pm_window_starts_late") or not c.get("collector_covered")
    ]
    day = [c for c in candidates if c.get("day_eligible")]
    swing = [c for c in candidates if c.get("swing_eligible")]
    no_catalyst = [_bare(c["symbol"]) for c in candidates if c.get("catalyst_found") is False]
    # None is a third state: the news feed was never checked (failed call or
    # quota skip). Unknown must never be rendered as checked and clean.
    unknown_catalyst = [
        _bare(c["symbol"]) for c in candidates if c.get("catalyst_found") is None
    ]

    lines: list[str] = []
    add = lines.append
    add(_FALLBACK_TITLES.get(cause, _FALLBACK_TITLES[CAUSE_UNAVAILABLE]))
    add("")
    add(f"{packet.get('session_date')}, packet generated {packet.get('generated_at')}, "
        "generated by PremarketDesk.")
    add("")
    disclaimer = (
        "Nothing here is advice, the screen thresholds are unvalidated seed values, "
        f"{cause} ({reason}), so this is the deterministic "
        "fallback built straight from packet.json"
    )
    if no_rvol:
        disclaimer += f"; premarket RVOL is null for {', '.join(no_rvol)}"
    if partial:
        disclaimer += (
            f"; premarket path evidence is partial or missing for {', '.join(partial)}"
        )
    unscored = [_bare(c["symbol"]) for c in candidates if c.get("score") is None]
    if unscored:
        disclaimer += (
            f"; {', '.join(unscored)} are unscored, not low conviction: a score "
            "component input was never observed, and unknown is not zero"
        )
    # The estimate has to be named as an estimate here too, or the fallback
    # publishes the same tables as the model report with one fewer caveat, and
    # which report a reader got is an accident of whether an API call worked.
    correction = packet.get("capture_correction") or {}
    if correction:
        # A COUNT, not a list. scan.capture_correction_report sums the rows
        # whose basis starts with "this symbol", and reading it as a list gave
        # len() of an int one edit ago.
        own = int(correction.get("shares_from_this_symbols_own_measurement") or 0)
        default_share = correction.get("default_capture_share")
        on_default = int(correction.get("candidates") or 0) - own
        if own and not on_default:
            how = "each name's own measured capture share"
        elif not own:
            how = f"the file wide default capture share of {default_share}"
        else:
            how = (f"{own} names on their own measured capture share and "
                   f"{on_default} on the file wide default of {default_share}")
        disclaimer += (
            "; premarket volume here is an ESTIMATE, not a measurement: every "
            "RVOL and float rotation divides the collector's socket volume "
            f"scaled up by {how}. The true figure is written tonight by the "
            "truth pass from a different vendor's full consolidated tape, "
            "beside this estimate and never over it"
        )
    quota = packet.get("quota_preflight") or {}
    if quota.get("degraded"):
        if quota.get("remaining") is not None:
            disclaimer += (
                f"; the shared API key had {quota['remaining']:,} of "
                f"{quota['daily_limit']:,} daily calls remaining at preflight "
                f"(quota day {quota.get('quota_day')}), so the skippable evidence "
                "here is thin for quota reasons, not a vendor outage"
            )
        else:
            disclaimer += "; the quota preflight could not read the shared meter"
    add(disclaimer + ".")
    add("")
    add("## Summary")
    add("")

    def _named(rows: list[dict[str, Any]]) -> str:
        return (": " + ", ".join(_bare(c["symbol"]) for c in rows)) if rows else ""

    add(f"{len(candidates)} candidates examined. Day eligible {len(day)} of "
        f"{len(candidates)}{_named(day)}. Swing eligible {len(swing)} of "
        f"{len(candidates)}{_named(swing)}. "
        f"{len(packet.get('gaps_to_fill', []))} gaps recorded in the packet.")
    add("")
    add("## Premarket gappers")
    add("")
    add("| Ticker | Name | Gap % | Price | Prior close | Mkt cap | Catalyst | Top headline |")
    add("|---|---|---|---|---|---|---|---|")
    for c in candidates:
        quote = c.get("quote") or {}
        heads = c.get("headlines") or []
        title = (heads[0].get("title") or "")[:80] if heads else ""
        found = c.get("catalyst_found")
        catalyst = c.get("catalyst_class") if found else (
            "none found" if found is False else "unknown")
        add(f"| {_bare(c['symbol'])} | {_cell(quote.get('name'))} | {_f(c.get('gap_pct'))} "
            f"| {_f(c.get('price'))} | {_f(c.get('prior_close'))} | {_cap(quote.get('marketCap'))} "
            f"| {_cell(catalyst)} | {_cell(title)} |")
    add("")
    add("## Day watchlist")
    add("")
    # The header row goes down whether or not there is anything under it. An
    # omitted table takes its Ticker header with it, and that header is what
    # the containment guard locates ticker claims by, so an empty screen used
    # to switch the guard off for the whole report. See REPORT_TEMPLATE.md.
    add("| Ticker | Gap % | Price | Premarket RVOL | Premarket high | Premarket VWAP | Score | Conviction |")
    add("|---|---|---|---|---|---|---|---|")
    if day:
        for c in day:
            add(f"| {_bare(c['symbol'])} | {_f(c.get('gap_pct'))} | {_f(c.get('price'))} "
                f"| {_f(c.get('pm_rvol'))} | {_f(c.get('pm_high'), 4)} | {_f(c.get('pm_vwap'), 4)} "
                f"| {_f(c.get('score'), 1)} | {_conviction(c)} |")
    else:
        add("| none | | | | | | | |")
    add("")
    # The RVOL column is an ESTIMATE, and the fallback says so for the same
    # reason the template does: this runs on the morning the narrative already
    # failed, which is exactly the morning nobody reads closely.
    correction = packet.get("capture_correction") or {}
    if correction:
        add("Premarket RVOL and float rotation are computed on an estimate of "
            "consolidated premarket volume rather than on the shares the "
            "collector recorded, because the socket carries a measured "
            "fraction of the tape while both denominators measure all of it. "
            f"On this morning's rows {correction.get('clear_on_socket_volume')} "
            f"of {correction.get('candidates')} would clear the volume floor on "
            "the raw socket numerator and "
            f"{correction.get('clear_on_consolidated_estimate')} do on the "
            "estimate.")
        # Two sets, because they answer different questions and conflating
        # them published a false membership claim on the first live morning:
        # HOOD cleared the volume floor on the correction and is NOT on this
        # list, because it fails the prior day high.
        onto = correction.get("carried_onto_the_day_watchlist") or []
        floor_only = [s for s in (correction.get("carried_across_the_floor") or [])
                      if s not in onto]
        if onto:
            add("The correction is what put "
                + ", ".join(_bare(s) for s in onto)
                + " on this list.")
        if floor_only:
            add(", ".join(_bare(s) for s in floor_only)
                + (" also cleared the volume floor on the correction and is "
                   "not on this list, having failed another day condition."
                   if len(floor_only) == 1 else
                   " also cleared the volume floor on the correction and are "
                   "not on this list, having failed another day condition."))
        add("")
    if not day:
        add(f"The day screen produced nothing this morning: 0 of {len(candidates)} "
            "candidates are day eligible.")
        add("")
    add("## Swing watchlist")
    add("")
    add("| Ticker | Gap % | Price | Prior high | 200d avg | Catalyst | Score | Conviction |")
    add("|---|---|---|---|---|---|---|---|")
    if swing:
        for c in swing:
            quote = c.get("quote") or {}
            add(f"| {_bare(c['symbol'])} | {_f(c.get('gap_pct'))} | {_f(c.get('price'))} "
                f"| {_f(c.get('prior_high'))} | {_f(quote.get('twoHundredDayAveragePrice'))} "
                f"| {c.get('catalyst_class')} | {_f(c.get('score'), 1)} | {_conviction(c)} |")
    else:
        add("| none | | | | | | | |")
    add("")
    if not swing:
        add(f"The swing screen produced nothing this morning: 0 of {len(candidates)} "
            "candidates are swing eligible.")
        add("")
    # Layer 4, in the same order the template puts it, because a fallback that
    # silently drops a section teaches its reader that the section is optional.
    # This runs on the morning the model call failed, which is exactly the
    # morning nobody is reading closely.
    notable = packet.get("notable_movers") or {}
    add("## Notable movers")
    add("")
    add("These names were selected for the size and unusualness of their move, "
        "rather than for tradeability.")
    add("They have not been screened against the day or swing criteria.")
    add("No conviction applies to any of them.")
    add("Every row states which leg produced it and the session it is as of.")
    add("No leg can carry today's regular session move, because this report is "
        "written before the open.")
    add("A name may appear on more than one row, once per leg, because a row "
        "carries one window and one vintage.")
    add("No move here is adjusted for a split or any other corporate action, so "
        "a very large one may be an action rather than a move.")
    add("")
    add(NOTABLE_HEADER)
    add("|---|---|---|---|---|---|---|---|---|---|")
    notable_rows = notable.get("rows") or []
    for row in notable_rows:
        # _cell, not the raw value. The catalyst is a vendor headline and
        # feeds put pipes in headlines constantly; an unescaped one ends the
        # cell early and python-markdown discards everything past the header
        # count without complaining. This is the fallback report, which is what
        # a reader gets on the mornings the narrative already failed.
        # The state's own words, not the state NAME. catalyst_state reads
        # "fetched" when a headline was found, and dropping that string into
        # the cell prints the word fetched where the headline belongs, which
        # happens whenever the vendor row carried no title.
        state = row.get("catalyst_state") or "not checked"
        catalyst = row.get("catalyst")
        if not catalyst:
            catalyst = {"fetched": "no headline text on the article",
                        "no catalyst found": "no catalyst found",
                        "not checked": "not checked"}.get(state, state)
        # The age beside the stamp, not instead of it. A timestamp says WHEN
        # the print was and an age says how far behind the scan clock it is,
        # and the reader cannot get the second from the first without a clock
        # the report does not print. Only the premarket leg carries either.
        age = row.get("price_age_seconds")
        add(f"| {_bare(row.get('symbol') or '')} | {_cell(row.get('leg'))} "
            f"| {_cell(row.get('as_of_session'))} | {_f(row.get('move_pct'))} "
            f"| {_f(row.get('move_sigma'), 2)} | {_cap(row.get('market_cap'))} "
            f"| {_cell(catalyst)} "
            f"| {_cell(row.get('also_on_watchlist') or 'not screened')} "
            f"| {_cell(row.get('price_time') or '-')} "
            f"| {_f(age, 0) if age is not None else '-'} |")
    if not notable_rows:
        add("| none | | | | | | | | | |")
    # One paragraph for the whole table rather than a tenth column, because
    # NOTABLE_HEADER is fixed and _ticker_claims locates ticker columns by it.
    # The names are carried at all because list 2 ranks by market cap and a
    # ticker alone cannot tell a reader whether a very large one is a real
    # company or a vendor error. See DECISIONS.md 2026-08-20.
    name_reason = notable.get("instrument_name_reason")
    if name_reason:
        text = str(name_reason)
        add(text[:1].upper() + text[1:] + ".")
    else:
        said: list[str] = []
        sentences: list[str] = []
        for row in notable_rows:
            label = row.get("name")
            ticker = _bare(row.get("symbol") or "")
            if label and ticker and ticker not in said:
                said.append(ticker)
                sentences.append(f"{ticker} is {_cell(label)}.")
        if sentences:
            add(" ".join(sentences))
    add("")
    for leg, report in sorted((notable.get("legs") or {}).items()):
        if not report.get("available") and report.get("reason"):
            add(f"The {leg} leg was lost: {report['reason']}")
    # EVERY list, not only the short ones, and the sentence comes from the
    # packet rather than being assembled here. A list that returned nothing has
    # to say which nothing it is and how many it considered, and until
    # 2026-08-22 the two sigma lists came back empty every single morning with
    # one word, "short", standing in for "the column this ranks on has never
    # been computed".
    for name, report in sorted((notable.get("list_reports") or {}).items()):
        text = (report or {}).get("text")
        if text:
            add(str(text))
    examined = notable.get("universe_examined")
    counted = f"{examined:,}" if isinstance(examined, int) else "an unknown number of"
    add(f"The section examined {counted} universe symbols.")
    for leg, report in sorted((notable.get("legs") or {}).items()):
        looked = report.get("examined")
        looked_text = f"{looked:,}" if isinstance(looked, int) else "an unknown number"
        add(f"The {leg} leg examined {looked_text} and selected "
            f"{report.get('selected', 0)}.")
    add("")
    add("## Market trends")
    add("")
    add("| Label | Last | Change % | Source |")
    add("|---|---|---|---|")
    for row in packet.get("market_snapshot", []):
        label = row.get("label", "")
        note = " (proxy)" if row.get("proxy_note") else ""
        add(f"| {str(label).upper()}{note} | {_f(row.get('last'))} "
            f"| {_f(row.get('change_pct'))} | {row.get('source') or 'unavailable'} |")
    add("")
    add("## Technical signals")
    add("")
    add("| Ticker | Premarket high | Premarket low | Premarket VWAP | Prior high | 200d avg | Score | Conviction |")
    add("|---|---|---|---|---|---|---|---|")
    for c in candidates:
        quote = c.get("quote") or {}
        mark = " (partial)" if (c.get("pm_window_starts_late") or not c.get("collector_covered")) else ""
        pm_high = _f(c.get("pm_high"), 4)
        add(f"| {_bare(c['symbol'])} | {pm_high}{mark if c.get('pm_high') is not None else ''} "
            f"| {_f(c.get('pm_low'), 4)} | {_f(c.get('pm_vwap'), 4)} | {_f(c.get('prior_high'))} "
            f"| {_f(quote.get('twoHundredDayAveragePrice'))} | {_f(c.get('score'), 1)} "
            f"| {_conviction(c)} |")
    add("")
    add("## Economic data and rates")
    add("")
    economic = packet.get("economic") or {}
    events = economic.get("events", [])
    # `error` as well as `skipped`. scan.economic_events returns
    # {"events": [], "error": error} on a failed call and sets `skipped` only on
    # the quota degrade path, so a failed call fell through to the empty branch
    # and this report published "No high importance events in the packet window"
    # for a window nobody looked at.
    if economic.get("skipped") or economic.get("error"):
        why = economic.get("skipped") or economic.get("error")
        add(f"The economic calendar was not checked this run: {why}. "
            "An unchecked calendar is not an empty one.")
    elif events:
        for event in events:
            add(f"- {event.get('time_et')}: {event.get('title')} "
                f"(forecast {event.get('forecast')}, previous {event.get('previous')}, "
                f"actual {event.get('actual')})")
    else:
        add("No high importance events in the packet window.")
    add("")
    add("## Coming up")
    add("")
    earnings_block = packet.get("earnings") or {}
    tomorrow = earnings_block.get("notable_tomorrow", [])
    if earnings_block.get("skipped"):
        add(f"The earnings calendar was not checked this run: {earnings_block['skipped']}. "
            "An unchecked calendar is not an empty one.")
    elif tomorrow:
        add("| Ticker | Mkt cap | Report date | Session |")
        add("|---|---|---|---|")
        for row in tomorrow:
            add(f"| {_bare(row.get('symbol', ''))} | {_cap(row.get('market_cap'))} "
                f"| {row.get('report_date')} | {row.get('before_after_market') or ''} |")
    else:
        add("No notable earnings in the packet window.")
    add("")
    add("## Skips and traps")
    add("")
    if no_catalyst:
        add(f"Moving on no found catalyst, a skip: {', '.join(no_catalyst)}.")
    if unknown_catalyst:
        add(f"Catalyst status is unknown for {', '.join(unknown_catalyst)}: the news "
            "feed was never checked this run, so no catalyst judgment exists for them.")
    if partial:
        add(f"Premarket path partial or absent, treat any level as partial: {', '.join(partial)}.")
    if not no_catalyst and not unknown_catalyst and not partial:
        add(f"Catalyst found and premarket evidence complete for "
            f"{len(candidates)} of {len(candidates)} candidates.")
    add("")
    # Traps used to say "needs the narrative pass and is not attempted here",
    # which was true while the judgment lived in REPORT_TEMPLATE.md and the
    # model made it. scan.attach_traps decides it now, from the balance of the
    # headlines rather than the worst one, so the fallback can state it: a
    # verdict computed in Python is exactly the kind of thing this degraded
    # path is for.
    traps = [_bare(c["symbol"]) for c in candidates if c.get("trap") is True]
    unweighable = [_bare(c["symbol"]) for c in candidates if c.get("trap") is None]
    if traps:
        add(f"Gapping up against the balance of their own headlines, a trap: "
            f"{', '.join(traps)}.")
    else:
        add(f"Traps: 0 of {len(candidates)} candidates gap up against the "
            "balance of their own headlines.")
    if unweighable:
        add(f"Trap undecided for {', '.join(unweighable)}: trap_why on those "
            "rows carries the reason, and undecided is not a verdict of safe.")

    # The measured worth of every RVOL above, from the nightly check. Stated
    # here for the same reason the template requires it: a lower bound whose
    # size nobody names reads as a rounding note.
    check = packet.get("collector_volume_check")
    if check:
        # The last sentence used to read "so they understate by about that much
        # again", asserting a direction from a magnitude. The check returned an
        # UNSIGNED median, and COLLECTOR_VOLUME.md records the collector wrong
        # in both directions: 2026-08-17 at -88.49 percent against 2026-08-14 at
        # 3.83 times the vendor in aggregate. On a morning shaped like the
        # second one this told the reader every RVOL was understated when the
        # numerator was inflated, which is the direction that flatters volume.
        # direction_phrase is now computed in scan from the signed median and
        # the aggregate ratio, and is quoted rather than composed here.
        add("")
        signed = check.get("median_signed_pct")
        ratio = check.get("aggregate_ratio")
        extra = ""
        if signed is not None:
            extra += f", signed median {signed:+.1f}%"
        if ratio is not None:
            extra += f", aggregate {ratio:.2f} times the vendor"
        add(f"Collector volume check, {check.get('day')}: median absolute "
            f"difference {check.get('median_abs_pct'):.1f}% against the vendor's "
            f"one minute bars on identical minutes, across "
            f"{check.get('compared')} symbol(s), "
            f"{check.get('within_one_percent')} within one percent{extra}"
            f"{'. STALE, ' + str(check.get('age_days')) + ' days old' if check.get('stale') else ''}"
            ". That gap is the INPUT to the premarket RVOL figures above, not "
            "an error inside them: it is divided out per symbol as "
            "pm_capture_share, so the numerator above is an estimate of "
            "consolidated volume. What survives is the share's session to "
            "session dispersion, about 1.5 times against a level of about "
            "nine. The vendor side of the check reads: "
            + (check.get("direction_phrase")
               or "the direction of that disagreement is unknown") + ".")
    else:
        add("")
        add("Collector volume check: not written. The disagreement between the "
            "collector feed and the vendor feed is unmeasured, which is not the "
            "same as small.")

    blocked = packet.get("day_blocked_on_rvol_alone") or []
    if blocked:
        add(f"Failed the day screen on premarket RVOL alone, having cleared "
            f"the other day conditions: {', '.join(_bare(s) for s in blocked)}.")
    return "\n".join(lines) + "\n"


# ------------------------------------------------- the containment checker

def _packet_uppercase_tokens(packet_text: str) -> set[str]:
    """Every uppercase token the packet itself carries, symbols included.

    The containment rule is literal: a ticker the report claims must appear
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


def _universe_bare_symbols() -> set[str] | None:
    """Bare tickers of every universe member, or None when the file is absent."""
    try:
        universe = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        str(row.get("symbol", "")).split(".")[0].upper()
        for row in universe.get("symbols", [])
        if row.get("symbol")
    }


# Words that assert something about the whole candidate set, and the words that
# say the assertion is ABOUT that set. A quantifier near a candidate word is a
# claim no reader can check against the report in front of them.
#
# This is a GUARD, not a prompt rule, and the difference is the whole point.
# This project has twice learned that an instruction is not a guard. The
# watchlist headers were pinned in the template AND checked mechanically,
# because a rule saying "reproduce this row" is obeyed until the morning it is
# not. On 2026-08-18 the report asserted a condition was missed by "every
# candidate" when one of twelve cleared it, and no rule in prompt_analyst.md
# was violated: the template had ASKED for a superlative it gave the model no
# way to compute. Rule 2 already forbids deciding membership; this stops the
# model describing the set it was forbidden to decide.
#
# A model that needs one of these words now has packet screen_tally to quote
# instead, which carries the counts and a prebuilt summary sentence.
_QUANTIFIERS = ("every", "all", "none", "each", "most", "majority")
# `no` is the same assertion as `none` and was missed by the first version of
# this list. "no candidate cleared the price test" and "none cleared it" are one
# claim in two spellings, and the model can no more check the first than the
# second. It is FORWARD ONLY, unlike the others: `no` is a determiner, so it
# governs the noun after it, and "there is no premarket high for AS, and the
# candidate is dropped" is not a claim about the set. The others are matched in
# both directions because "the candidates all cleared" and "all the candidates
# cleared" are the same sentence.
_FORWARD_ONLY_QUANTIFIERS = ("no",)
_SET_WORDS = ("candidate", "candidates", "name", "names", "watchlist", "watchlists")
# Words either side, not characters. Six is wide enough to catch "every one of
# the candidates" and narrow enough that two unrelated sentences do not collide.
_QUANTIFIER_WINDOW_WORDS = 6


def flag_log_path() -> Path:
    """The running record of every quantifier flag this guard has ever raised."""
    return config.DATA_DIR / "quantifier-flags.jsonl"


# What became of the report the flag was raised against. A flag that a
# regeneration fixed cost the morning nothing; a flag that survived the
# regeneration cost it its narrative. Both are raises of the guard and both
# belong in the false positive denominator, but they are not the same event,
# and the difference is the number that says whether this guard is expensive.
OUTCOME_REGENERATED = "regenerated"
OUTCOME_FELL_BACK = "fell_back"
# Warn mode: the flag was raised and the narrative went out anyway. Kept
# distinct from the other two because it is the only outcome where the reader
# received the sentence, and a rate that mixed it in would answer neither
# question. See CRITERIA analyst.quantifier_guard.
OUTCOME_WARNED = "warned"

GUARD_WARN = "warn"
GUARD_ENFORCING = "enforcing"


def guard_mode() -> str:
    """warn or enforcing, from CRITERIA, with an unknown value failing closed.

    A typo in this knob must not be a silent way to switch the guard off, so
    anything unrecognised is treated as enforcing and says so. Failing open on
    a misspelling is how a guard quietly stops existing.
    """
    mode = _CRIT.text("analyst", "quantifier_guard").strip().lower()
    if mode not in (GUARD_WARN, GUARD_ENFORCING):
        print(f"analyst: WARNING CRITERIA analyst.quantifier_guard reads {mode!r}, "
              f"which is neither {GUARD_WARN!r} nor {GUARD_ENFORCING!r}. Treating it "
              "as enforcing, because an unreadable setting must not be a way to "
              "turn the guard off by accident.")
        return GUARD_ENFORCING
    return mode


def record_quantifier_flags(
    hits: list[dict[str, Any]], session: str, report_name: str,
    attempt: int = 1, outcome: str = OUTCOME_FELL_BACK,
) -> list[int]:
    """Append each flag to the running log and return the ids assigned.

    The rate is MEASURED, not asserted, and that is the whole reason this file
    exists. When the guard was built its false positive rate was eyeballed at
    one in six from a single afternoon's reports, which is a defensible number
    today and a dangerous one in three months. This project's own history is
    guards whose failures got rationalised away: a claim swallowed exceptions
    for a week, a calendar status was ignored, pool_recall wrote nothing nightly
    while DECISIONS cited its evidence as if it had. A blunt guard sitting on
    the morning path, where a hit blocks the report, is a candidate for exactly
    that the first morning somebody is in a hurry.

    So every hit is written down with room for a disposition, nobody has to
    remember which ones were nonsense, and the word list gets tuned on a month
    of dispositions rather than on an impression. ops/quantifier_flags.py reads
    this file, marks dispositions and prints the measured rate.

    Appended, never rewritten, and a failure to write is never allowed to take
    the run with it: losing a line of telemetry must not turn into a lost
    morning report.
    """
    path = flag_log_path()
    try:
        existing = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except (OSError, ValueError):
        existing = 0
    ids: list[int] = []
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for offset, hit in enumerate(hits, start=1):
                flag_id = existing + offset
                ids.append(flag_id)
                handle.write(json.dumps({
                    "id": flag_id,
                    "recorded_at": ettime.stamp(ettime.now_et()),
                    "session": session,
                    "report": report_name,
                    "line": hit["line"],
                    "quantifier": hit["quantifier"],
                    "set_word": hit["set_word"],
                    "sentence": hit["text"],
                    "attempt": attempt,
                    "outcome": outcome,
                    # Filled in later by a human through ops/quantifier_flags.py.
                    # Null means nobody has judged it yet, which is different
                    # from judged and found harmless.
                    "disposition": None,
                    "disposition_note": None,
                    "disposition_at": None,
                }, separators=(",", ":")) + "\n")
            handle.flush()
    except OSError as exc:
        print(f"analyst: WARNING could not append to {path.name}: {exc}")
        return []
    return ids


def quantifier_violations(report: str) -> list[dict[str, Any]]:
    """Every place the report asserts a quantifier over the candidate set.

    Markdown table rows are skipped entirely. The empty watchlist table's own
    `| none | | | | | | | |` row sits three lines under a heading carrying the
    word watchlist, so scanning tables would fail every empty morning, which is
    exactly the morning this guard is most needed on.

    HEADINGS ARE SCANNED, with their marker run stripped so the words are
    judged the same way prose is. They were skipped alongside table rows until
    2026-08-20 and the docstring only ever accounted for the table skip. A
    heading is not a table row: it is prose in the most prominent position on
    the page, and "## No candidates cleared the day screen" is exactly the
    sentence this guard exists to refuse, written where a reader is most likely
    to believe it. Skipping them also meant the flag rate the warn mode is
    being measured on undercounted by however many flags lived in headings,
    which is a measurement problem as well as a guard one.
    """
    out: list[dict[str, Any]] = []
    for number, line in enumerate(report.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("|"):
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        out.extend(_scan_prose(number, stripped))
    return out


def _scan_prose(number: int, stripped: str) -> list[dict[str, Any]]:
    """One chunk of prose, matched against the word list. THE matcher.

    Every caller comes through here, so the window rule and the direction rule
    have one implementation. What differs between callers is what they hand in
    as a chunk, not how the chunk is judged.
    """
    out: list[dict[str, Any]] = []
    lowered = [w.lower() for w in re.findall(r"[A-Za-z_]+", stripped)]
    for index, word in enumerate(lowered):
        forward_only = word in _FORWARD_ONLY_QUANTIFIERS
        if word not in _QUANTIFIERS and not forward_only:
            continue
        low = index if forward_only else max(0, index - _QUANTIFIER_WINDOW_WORDS)
        high = min(len(lowered), index + _QUANTIFIER_WINDOW_WORDS + 1)
        near = [w for w in lowered[low:index] + lowered[index + 1:high]
                if w in _SET_WORDS]
        if near:
            out.append({
                "line": number,
                "quantifier": word,
                "set_word": near[0],
                "text": stripped,
            })
    return out


def banned_words() -> tuple[str, ...]:
    """Every word the guard refuses near a set word, in one place.

    THE definition. REPORT_TEMPLATE.md, prompt_analyst.md and the fallback
    report are all checked against this tuple rather than against a copy of
    it, because three times in three commits the instructions asked for what
    the guard forbids: the template asked for a superlative it could not
    compute, the fallback's own prose used the words, and rule 13 still
    permitted `no` a commit after `no` was banned. A word list with four
    copies has four chances to drift and no way to notice.
    """
    return tuple(sorted(_QUANTIFIERS + _FORWARD_ONLY_QUANTIFIERS))


def set_words() -> tuple[str, ...]:
    """The words that say a quantifier is about the candidate set."""
    return tuple(sorted(_SET_WORDS))


# A banned phrasing inside backticks is a SPECIMEN, not a sentence. The
# instruction files have to be able to say "do not write `every candidate
# missed`", and a scanner that failed them for it would force the clearest
# teaching out of the documents that most need it. Backticks are how a
# document already marks text it is exhibiting rather than uttering, so that
# is the convention, and it is mechanical rather than a judgment call.
#
# Single line only, deliberately: a span that swallowed newlines could exempt
# half a document by way of one stray backtick.
_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")

# A numbered rule or a bullet starts a fresh unit. See instruction_violations.
_LIST_ITEM_RE = re.compile(r"^(?:\d+\.|[-*+])\s")


def instruction_violations(text: str) -> list[dict[str, Any]]:
    """The guard, run over an instruction file instead of over a report.

    Same word list, same window, same matcher. Two differences, both because
    an instruction file is not a report.

    Quoted specimens are removed first, replaced with spaces rather than
    deleted so the reported line number still points at the line somebody has
    to edit.

    And the unit is a PARAGRAPH, not a line, which makes this check stricter
    than the one the reports get. These files are hand wrapped at about
    seventy-eight columns, so a banned word routinely ends one line while its
    set word begins the next: "including mornings when no / candidate is
    eligible" is one sentence and two lines, and a line-at-a-time scan reads
    straight past it. Model output wraps nowhere, so the report scan does not
    need this and is left alone rather than changed under a live guard.
    """
    stripped = _CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)
    out: list[dict[str, Any]] = []
    start: int | None = None
    buffer: list[str] = []

    def flush() -> None:
        if start is not None and buffer:
            out.extend(_scan_prose(start, " ".join(buffer)))

    for number, line in enumerate(stripped.splitlines(), start=1):
        bare = line.strip()
        if not bare or bare.startswith("|") or bare.startswith("#"):
            flush()
            start, buffer = None, []
            continue
        if _LIST_ITEM_RE.match(bare):
            # A numbered rule is its own unit. prompt_analyst.md runs its rules
            # together with no blank line between them, so joining the block
            # whole would put the last words of rule 5 within six words of the
            # first words of rule 6 and invent a pair neither sentence makes.
            flush()
            start, buffer = number, [bare]
            continue
        if start is None:
            start = number
        buffer.append(bare)
    flush()
    return out


def _print_quantifier_flags(
    hits: list[dict[str, Any]], ids: list[int], attempt: int, attempts: int,
    enforcing: bool = True,
) -> None:
    """Say what was matched and where, in a form somebody can judge at 08:46.

    The matched term and the whole sentence, not a line number. A flag nobody
    can dismiss without opening the report is a flag that gets waved through,
    and a guard that gets waved through has stopped being a guard.
    """
    if not enforcing:
        print(f"analyst: the quantifier guard flagged {len(hits)} sentence(s). "
              "It is in WARN mode, so the narrative is being delivered as "
              "written and these are recorded for the rate rather than acted "
              "on. See CRITERIA analyst.quantifier_guard:")
    else:
        print(f"analyst: the quantifier guard rejected narrative attempt {attempt} "
              f"of {attempts}. The report asserts a quantifier over the candidate "
              "set, which no reader can check against the report in front of them:")
    for hit, flag_id in zip(hits, ids or [None] * len(hits)):
        print(f"  flag {flag_id} line {hit['line']}: matched "
              f"{hit['quantifier']!r} near {hit['set_word']!r}")
        print(f"      {hit['text']}")
    # Local, because ops.quantifier_flags imports this module and a
    # module level import here would be a cycle. monitor_jobs does the
    # same for the same reason.
    from ops import quantifier_flags

    print("analyst: packet screen_tally carries the counts to quote instead. "
          "See prompt_analyst.md rule 13.")
    if ids:
        print(f"analyst: logged to {flag_log_path().name}. If one of these is "
              "wrong, record it so the word list is tuned on data: "
              f"{quantifier_flags.RUN_PREFIX} --mark {ids[0]} false-positive "
              '--note "why"')


def quantifier_correction(hits: list[dict[str, Any]]) -> str:
    """The note appended to the packet when a flagged report is regenerated."""
    lines = [
        "STOP. Your previous answer to this exact request was REJECTED before "
        "anybody read it, and you are writing it again from the beginning.",
        "",
        "Rule 13 forbids asserting a quantifier over the candidate set. You "
        "cannot check such a claim and neither can the reader, which is why it "
        "is refused mechanically rather than argued about. These sentences "
        "broke it:",
        "",
    ]
    for hit in hits:
        lines.append(f"  matched {hit['quantifier']!r} near {hit['set_word']!r}: "
                     f"{hit['text']}")
    lines += [
        "",
        "Write the whole report again. Everything else about it is unchanged. "
        "Where you need to say something about the candidate set as a whole, "
        "quote the counts already computed in packet screen_tally, in the form "
        '"0 of 12", rather than reaching for a word like every, all, none, no, '
        "each, most or majority. This is the last attempt: if the next answer "
        "is rejected too, the morning gets a plain table with no narrative at "
        "all.",
    ]
    return "\n".join(lines)


# Long enough to read as a sentence, short enough that the disclaimer line
# stays a line. The full text is on the flag record, which the id points at.
_QUOTE_LIMIT = 240


def quantifier_reason(hits: list[dict[str, Any]], ids: list[int]) -> str:
    """Why the narrative was withheld, in the words the disclaimer will carry.

    The sentence itself, not a count of sentences. A reader who is told the
    narrative was withheld and not told what for has been handed a mystery
    instead of a report, and the person best placed to say the guard was
    wrong is the one reading the morning it fired.
    """
    first = hits[0]
    sentence = first["text"]
    if len(sentence) > _QUOTE_LIMIT:
        sentence = sentence[:_QUOTE_LIMIT].rstrip() + "..."
    where = f"logged as flag {ids[0]}" if ids else "not logged, the flag file could not be written"
    plural = "" if len(hits) == 1 else f", {len(hits)} in total"
    return (
        f"the model asserted a quantifier over the candidate set on both "
        f"attempts, matching {first['quantifier']!r} near {first['set_word']!r}{plural} "
        f'in "{sentence}" ({where}, judge it with python -m ops.quantifier_flags)'
    )


def _claimable_symbols() -> set[str] | None:
    """The symbols a ticker claim is validated against, or None when unknowable.

    The universe alone is not enough: it holds common stock only, so every
    ETF is outside it, including the eight context tickers the report talks
    about every single morning (SPY, QQQ and friends). A claim check that
    cannot see them is fail open for exactly the names the model is most
    likely to write. So claims are validated against the union of the
    universe and the fixed context list from CRITERIA.md.
    """
    universe = _universe_bare_symbols()
    if universe is None:
        return None
    context = {
        str(s).split(".")[0].upper()
        for s in _CRIT.text_list("collector", "context_symbols")
        if str(s).strip()
    }
    return universe | context


# The meridiem and the zone each end at a WORD BOUNDARY, and until 2026-08-22
# neither did. `\s*(?:AM|PM|...)?` matched the first two letters of any
# capitalised word after a time, so "07:15 AMD" was blanked to "07:15 AM" and
# left the fragment "D", and "16:00 ETSY" left "SY". Both fragments are real
# universe symbols. So a genuine claim about AMD vanished from the containment
# check, AND an invented ticker appeared that the model never wrote, which
# check_report reports as invention and analyst.py exits 2 on, stopping the
# morning chain before the report ships.
#
# A.M. and P.M. are listed before AM and PM so the dotted forms win, and each
# alternation carries its own lookahead rather than one at the end, because the
# zone group is optional and a trailing lookahead would not constrain a match
# that stopped at the meridiem.
_TIME_RE = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*(?:A\.M\.|P\.M\.|AM|PM)(?![A-Za-z]))?"
    r"(?:\s*(?:EDT|EST|GMT|UTC|ET)(?![A-Za-z]))?",
    re.IGNORECASE)
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.+-]+)?")

# Capitals joined by a dot, an ampersand or a slash are ONE abbreviation, and
# they are blanked here for the same reason dates and times are: _TOKEN_RE has
# no idea what punctuation means, so it took "S&P 500 futures are flat" apart
# into P and S, "U.S. equity futures are soft" into S and U, "the P/E is
# stretched" into E and P, and "R&D spending rose" into D and R. Every one of
# those fragments is a real listing. universe.json carries 21 one letter names
# and prose_token_stopwords stops only A and I, so each fragment became a
# ticker claim and then an INVENTED one on any morning whose packet did not
# happen to quote a headline carrying the same bare letter.
#
# Measured on 2026-08-20 by injecting one ordinary Market trends sentence into
# each archived report and checking it against that morning's real packet:
# 08-17 and 08-20 invented P, S and U, 08-19 invented P, and 08-18 escaped
# only because its packet quotes a headline containing "S&P 500". That is not
# a cosmetic failure. check_report exits 2 on an invented ticker, the chain's
# "if %RC% neq 0 exit /b %RC%" then skips render, verify, deliver and archive,
# and containment has no regeneration path, so an abbreviation any writer
# would reach for cost the morning everything downstream of the analyst.
#
# The other candidate fix was to add P, S, U, D, E and R to
# prose_token_stopwords. It was rejected: that blinds the guard to six real
# listings everywhere in prose, which pays for a false positive with a false
# negative in the one check that exists to catch invented evidence.
#
# A run counts as an abbreviation only when one of its pieces is short, which
# is the line between "S&P", "U.S.", "P/E", "AT&T" and "EV/EBITDA" on one side
# and "SPY/QQQ" on the other. Two full length tickers a writer slashed together
# are two claims and stay two claims. A bare ticker is untouched either way,
# "the move in NVDA." included, because the pattern needs capitals on BOTH
# sides of a separator and a sentence ending full stop has none.
#
# The hyphen is deliberately NOT one of the separators. It is the commonest
# punctuation in ordinary prose and treating every hyphenated word as an
# abbreviation would reach far past the three cases above. The fragments it
# leaves behind are real and known: the 2026-08-20 report quotes a headline
# saying "Economic D-Day" and D is Dominion Energy, which passes only because
# the packet carries that same headline. If a morning ever fails on one of
# those, the hyphen belongs here and this note is the argument for adding it.
_ABBREVIATION_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:[.&/][A-Z][A-Z0-9]*)+\.?")
_ABBREVIATION_SEPARATOR_RE = re.compile(r"[.&/]")
# One or two characters. Longer than that and the piece is a word in its own
# right rather than the wreckage of an abbreviation.
_SHORT_ABBREVIATION_PIECE = 2

# A ticker written with its exchange suffix. Prompt rule 8 forbids NVDA.US in
# the report body, but the guard still has to read it as a claim about NVDA
# rather than lose it, and without this line the abbreviation blanking above
# would swallow the whole thing, because US is two characters long and the run
# therefore looks abbreviated. Normalising the suffix away first preserves
# exactly the claim the old tokenizer already found there.
_EXCHANGE_SUFFIX_RE = re.compile(r"\b([A-Z][A-Z0-9]{0,5})\.US\b")


def _blank_abbreviations(text: str) -> str:
    """Blank punctuation joined abbreviations, leaving ticker claims alone.

    The short piece test is the whole of the judgement, and the note on
    _ABBREVIATION_RE says what it buys, what it costs, and why the line is
    drawn where it is.
    """
    def blank(match: re.Match[str]) -> str:
        pieces = [
            piece for piece in _ABBREVIATION_SEPARATOR_RE.split(match.group(0))
            if piece
        ]
        if any(len(piece) <= _SHORT_ABBREVIATION_PIECE for piece in pieces):
            return " "
        return match.group(0)

    return _ABBREVIATION_RE.sub(blank, text)


def _prose_tokens(report_text: str) -> set[str]:
    """Ticker shaped tokens from the report's prose, tables excluded.

    Prose is ambiguous where a Ticker column is not, so three filters run
    before anything is called a token. Time expressions and ISO dates are
    stripped first, because "06:37 ET" is a time and ET is also Energy
    Transfer. Punctuation joined abbreviations go next, because "S&P" is one
    word and not a claim about two one letter listings. Then the stopword list
    in CRITERIA.md removes the finance and unit acronyms that survive. What is
    left is intersected with the known symbols by the caller, so an ordinary
    capitalised word never becomes a claim.
    """
    stopwords = {
        s.strip().upper()
        for s in _CRIT.text_list("analyst", "prose_token_stopwords")
        if s.strip()
    }
    prose = "\n".join(
        line for line in report_text.splitlines() if not line.strip().startswith("|")
    )
    prose = _ISO_RE.sub(" ", prose)
    prose = _TIME_RE.sub(" ", prose)
    prose = _EXCHANGE_SUFFIX_RE.sub(r"\1 ", prose)
    prose = _blank_abbreviations(prose)
    return {token for token in _TOKEN_RE.findall(prose) if token not in stopwords}


# The two tables whose PRESENCE the guard requires, keyed by their literal
# header row from REPORT_TEMPLATE.md. Counting ticker columns was the old test
# and it stopped working the moment a third table carried a Ticker header: a
# briefing table with no trading meaning would satisfy a check that exists to
# prove the two trading tables were written. Replaying the 2026-08-14 report
# with a Notable movers table appended flipped structure_failed from True to
# False while both watchlists were still missing and 22 prose ticker claims
# still went unvalidated.
#
# So the requirement names the tables. Any other table with a Ticker header
# still contributes its cells as claims to validate, which is what keeps the
# briefing section honest, but it cannot satisfy this.
# Layer 4's header, carried here so fallback_report can emit it and checked
# against REPORT_TEMPLATE.md by claim_headers_cannot_diverge, on the precedent
# the two watchlist headers already set. It is deliberately NOT in
# _REQUIRED_TABLES below: the vacuum detector requires the two watchlists BY
# NAME, and a briefing table must never be able to satisfy that requirement.
# Its cells still reach the containment guard as claims to validate, which is
# what keeps the section honest about the tickers it publishes.
NOTABLE_HEADER = (
    "| Ticker | Leg | As of | Move % | Sigma | Market cap | Catalyst | "
    "On watchlist | Price time | Price age s |"
)

_REQUIRED_TABLES = {
    "day watchlist": (
        "| Ticker | Gap % | Price | Premarket RVOL | Premarket high | "
        "Premarket VWAP | Score | Conviction |"
    ),
    "swing watchlist": (
        "| Ticker | Gap % | Price | Prior high | 200d avg | Catalyst | "
        "Score | Conviction |"
    ),
}


def _header_cells(line: str) -> tuple[str, ...]:
    """A header row reduced to its cells, for comparison against the required set."""
    return tuple(cell.strip().lower() for cell in line.strip().strip("|").split("|"))


_REQUIRED_CELLS = {name: _header_cells(row) for name, row in _REQUIRED_TABLES.items()}


def _ticker_claims(report_text: str) -> tuple[set[str], int, set[str], set[str]]:
    """The tokens the report presents AS tickers, the columns scanned, and prose.

    A claim is a token in a table column whose header names it a ticker column,
    or a token anywhere carrying a $ prefix, which is unambiguous. Other table
    cells are prose in a grid ("2:48 PM ET" in a headline cell must not read as
    Philip Morris), so they are not scanned.

    Prose tokens are returned separately. They used to be ignored entirely, on
    the reasoning that an acronym in a sentence is not a ticker claim. That
    reasoning holds for what prose tokens may FAIL, and it broke down for what
    their presence PROVES: on 2026-08-14 both watchlist tables were omitted
    because both screens were empty, so zero columns were scanned, and the
    check reported a clean pass over a report that named twelve tickers in
    bold prose. Prose mentions are how that vacuum is now detected.

    The columns count exists because a check that scanned nothing must not be
    reported as a check that passed. REPORT_TEMPLATE.md pins the header
    wording the detector matches on; the count is how a drift from that
    wording becomes visible instead of silently weakening the guard.
    """
    claims: set[str] = set(_DOLLAR_RE.findall(report_text))
    columns_scanned = 0
    found_tables: set[str] = set()
    separator = re.compile(r"[|\s:\-]+")
    lines = report_text.splitlines()
    ticker_columns: list[int] | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            ticker_columns = None
            continue
        if separator.fullmatch(stripped):
            continue  # the |---|---| separator row
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        is_header = (
            index + 1 < len(lines)
            and lines[index + 1].strip().startswith("|")
            and separator.fullmatch(lines[index + 1].strip()) is not None
        )
        if is_header:
            ticker_columns = [
                position for position, cell in enumerate(cells)
                if "ticker" in cell.lower() or "symbol" in cell.lower()
            ]
            columns_scanned += len(ticker_columns)
            if ticker_columns:
                seen = tuple(cell.lower() for cell in cells)
                for name, wanted in _REQUIRED_CELLS.items():
                    if seen == wanted:
                        found_tables.add(name)
            continue
        if not ticker_columns:
            continue
        for position in ticker_columns:
            if position < len(cells):
                claims.update(_TOKEN_RE.findall(cells[position]))
    return claims, columns_scanned, _prose_tokens(report_text), found_tables


def check_report(
    report_text: str, packet_text: str
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Returns (invented_tickers, candidates_missing_from_report, coverage).

    A token is an invented ticker only when all three hold: the report
    presents it as a ticker (table cell or $ prefix), it names a real symbol
    in the universe file or the fixed context list, and the packet does not
    carry it. The known-symbol test is what keeps ordinary uppercase words
    out: CEO in a table cell is not a known symbol, so it is not a claim
    about a tradeable name.

    coverage records what the check actually examined, because this check
    fails open in three ways (no universe file, no recognisable ticker
    column, no $ claims) and a pass that examined nothing must be visibly
    different from a pass that examined everything. claims_checked zero
    means validation did not run in any meaningful sense, and the caller
    must say so where the reader will see it.
    """
    known_symbols = _claimable_symbols()
    table_claims, columns_scanned, prose_tokens, found_tables = _ticker_claims(report_text)
    prose_claims = (
        sorted(token for token in prose_tokens if token in known_symbols)
        if known_symbols is not None
        else []
    )
    claims = table_claims | set(prose_claims)

    # The vacuum detector. A report that names real tickers in its prose while
    # carrying no ticker column at all has not passed containment, it has
    # escaped it: the tables the guard reads were never written. That is a
    # structural failure of the report, reported as a failure rather than as a
    # pass with a footnote.
    missing_tables = sorted(set(_REQUIRED_TABLES) - found_tables)
    structure_failed = bool(missing_tables)
    coverage: dict[str, Any] = {
        "universe_available": known_symbols is not None,
        "columns_scanned": columns_scanned,
        "tokens_examined": len(claims),
        "claims_checked": len(claims) if known_symbols is not None else 0,
        "prose_claims": prose_claims,
        "tables_found": sorted(found_tables),
        "tables_missing": missing_tables,
        "structure_failed": structure_failed,
        "structure_reason": (
            f"the report is missing {len(missing_tables)} required table(s) "
            f"({', '.join(missing_tables)}). REPORT_TEMPLATE.md requires both "
            "watchlist tables to be written even when empty, with their header "
            "rows reproduced character for character. Any other table carrying a "
            "Ticker header contributes claims to validate but cannot stand in for "
            "them, so a briefing table does not make a missing watchlist pass."
        ) if structure_failed else None,
    }
    if known_symbols is None:
        print("analyst: containment note: universe.json is unavailable, so ticker "
              "claims cannot be validated this run")
        invented: list[str] = []
    else:
        allowed = _packet_uppercase_tokens(packet_text)
        invented = sorted(
            token for token in claims
            if token in known_symbols and token not in allowed
        )

    missing: list[str] = []
    try:
        packet = json.loads(packet_text)
    except json.JSONDecodeError:
        return invented, missing, coverage
    report_tokens = set(_TOKEN_RE.findall(report_text))
    for candidate in packet.get("candidates", []):
        bare = str(candidate.get("symbol", "")).split(".")[0]
        if bare and bare not in report_tokens:
            missing.append(bare)
    return invented, missing, coverage


def _why_unvalidated(coverage: dict[str, Any]) -> str:
    if not coverage.get("universe_available"):
        return "universe.json was unavailable"
    if coverage.get("structure_failed"):
        missing = coverage.get("tables_missing") or []
        return (f"the report omitted {len(missing)} required table(s) "
                f"({', '.join(missing)}), which REPORT_TEMPLATE.md requires to be "
                "written even when empty")
    if not coverage.get("columns_scanned") and not coverage.get("tokens_examined"):
        return ("no table carried a recognisable Ticker or Symbol header and "
                "no $ prefixed claims were found, so nothing was examined")
    return "no ticker claims were found to examine"


def annotate_unvalidated(report_text: str, coverage: dict[str, Any]) -> str:
    """Make a vacuous containment pass say so where the reader will see it.

    The sentence is appended to the disclaimer line, the one line the
    template guarantees exists and the reader is told to trust. If the
    disclaimer cannot be found the note goes at the end rather than nowhere.
    """
    note = (f"ticker claims in this report were NOT validated: "
            f"{_why_unvalidated(coverage)}")
    return _append_to_disclaimer(report_text, note)


def _append_to_disclaimer(report_text: str, note: str) -> str:
    """Put a sentence where the reader is already told to look."""
    lines = report_text.splitlines()
    for index, line in enumerate(lines):
        if "Nothing here is advice" in line:
            trimmed = line.rstrip()
            if trimmed.endswith("."):
                trimmed = trimmed[:-1]
            lines[index] = f"{trimmed}; {note}."
            return "\n".join(lines) + "\n"
    return report_text.rstrip("\n") + f"\n\n{note[0].upper() + note[1:]}.\n"


def annotate_warned_quantifiers(
    report_text: str, hits: list[dict[str, Any]], ids: list[int]
) -> str:
    """Say on the disclaimer line that a flagged sentence was published anyway.

    Warn mode delivers the narrative intact, which is the point of it, and
    that means a claim the guard calls uncheckable reaches the reader. Saying
    so is the same rule the fallback follows: a report that degraded quietly
    would be a report lying about its own provenance, and this is a quieter
    degradation than the fallback, not a smaller one.

    It also puts the flags in front of the one person who can judge them, on
    the morning they fired, which is the whole difficulty with a log nobody
    opens.
    """
    if not hits:
        return report_text
    named = ", ".join(str(i) for i in ids) if ids else "unlogged"
    return _append_to_disclaimer(
        report_text,
        f"{len(hits)} sentence(s) below make a claim about the whole candidate "
        f"set that the quantifier guard cannot check (flag {named}); the guard "
        "is in warn mode, so they were published rather than rewritten, and "
        "the packet screen_tally counts are what to read instead"
    )


def annotate_job_health(report_text: str, packet: dict[str, Any]) -> str:
    """Name any scheduled step that has not succeeded inside its window.

    Written here in Python rather than asked of the model, for the same reason
    every other number in this file is: the model narrates, it does not decide.
    A prompt rule can be forgotten by a model having an off morning, and the
    one morning it is forgotten is the morning it mattered. Silence is the
    normal case, so a healthy machine gets no line at all.
    """
    health = packet.get("job_health") or {}
    line = health.get("line")
    if not line:
        return report_text
    return _append_to_disclaimer(report_text, line.rstrip("."))


# ------------------------------------------------------------------- runner

def write_report(packet_path: Path) -> int:
    # Local, because ops.quantifier_flags imports this module and a
    # module level import here would be a cycle. monitor_jobs does the
    # same for the same reason.
    from ops import quantifier_flags

    packet_text = packet_path.read_text(encoding="utf-8")
    packet = json.loads(packet_text)
    session_date = packet.get("session_date") or ettime.today_et().isoformat()
    run_directory = config.run_dir(session_date)
    report_path = run_directory / "report.md"

    # One narrative attempt, plus however many regenerations CRITERIA allows.
    #
    # The quantifier guard used to cost the whole morning. A flag returned 2,
    # the chain stops on the first non-zero exit code, and render, deliver and
    # archive never ran: no report at all, over one sentence. That is the
    # wrong price for a guard whose own false positive rate is still being
    # measured, and it is the price a person in a hurry pays by switching the
    # guard off. So a flag now costs a regeneration first and the narrative
    # second, and never the report. The worst a false positive can do is hand
    # the morning the plain table, which is exactly the trade the guard's
    # asymmetry argument already assumed it was making.
    #
    # Until the template stops ASKING for the banned words the guard is in
    # warn mode, where every flag is logged and printed and nothing is acted
    # on. All three archived reports flag under the current template, so
    # enforcing today would mean the plain table most mornings, and a flag log
    # filling under the template that provokes it is better evidence than one
    # filling after the provocation is gone. CRITERIA names what has to be
    # true before the switch flips.
    enforcing = guard_mode() == GUARD_ENFORCING
    attempts = (_CRIT.integer("analyst", "quantifier_regenerations") + 1
                if enforcing else 1)
    report_text: str | None = None
    usage: dict[str, Any] = {}
    reason: str | None = None
    kind = "failed"
    cause = CAUSE_UNAVAILABLE
    correction: str | None = None
    flags_raised: list[dict[str, Any]] = []
    warned: list[dict[str, Any]] = []
    warned_ids: list[int] = []

    for attempt in range(1, attempts + 1):
        text, usage, error, kind = invoke_claude(packet_text, correction)
        if error or text is None or not text.strip():
            reason = error or "the model returned an empty report"
            if not error:
                kind = "failed"
            break

        # Containment first, and the order is deliberate. An invented ticker
        # is fabricated evidence, the one failure this system exists to
        # prevent, and it neither regenerates nor degrades: the report is
        # written for inspection and the chain stops. Asking that question
        # before the quantifier one is also what makes the withheld
        # disclaimer safe to quote from, because a sentence stamped into it
        # has already been proven to name no ticker the packet does not carry.
        invented, _missing, coverage = check_report(text, packet_text)
        if invented or coverage["structure_failed"]:
            report_text = text
            break

        hits = quantifier_violations(text)
        if not hits:
            report_text = text
            break

        if not enforcing:
            warned_ids = record_quantifier_flags(
                hits, session_date, report_path.name, attempt, OUTCOME_WARNED)
            _print_quantifier_flags(hits, warned_ids, attempt, attempts,
                                    enforcing=False)
            warned = hits
            flags_raised.extend(
                {**hit, "id": flag_id, "attempt": attempt}
                for hit, flag_id in zip(hits, warned_ids or [None] * len(hits))
            )
            report_text = text
            break

        final = attempt == attempts
        ids = record_quantifier_flags(
            hits, session_date, report_path.name, attempt,
            OUTCOME_FELL_BACK if final else OUTCOME_REGENERATED,
        )
        _print_quantifier_flags(hits, ids, attempt, attempts)
        flags_raised.extend(
            {**hit, "id": flag_id, "attempt": attempt}
            for hit, flag_id in zip(hits, ids or [None] * len(hits))
        )
        if not final:
            print(f"analyst: regenerating, {attempts - attempt} attempt(s) left. "
                  "The rejected sentences go back to the model with the report "
                  "request, so the second answer is told what to avoid.")
            correction = quantifier_correction(hits)
            continue
        kind = "quantifier"
        cause = CAUSE_WITHHELD
        reason = quantifier_reason(hits, ids)

    if report_text is None:
        print(f"analyst: {cause} ({kind}): {reason}")
        print("analyst: falling back to the deterministic numbers only report")
        # Never run back through quantifier_violations. This text is Python
        # written, its claims are true by construction, and its disclaimer
        # quotes the rejected sentence on purpose. A guard that rejected the
        # fallback would leave the morning with nothing, which is the exact
        # failure this path exists to prevent.
        report_text = fallback_report(packet, reason or "unrecorded", cause)
        usage = {
            "status": kind,
            "error_message": reason,
            "fallback": True,
            # The rejected attempt still cost tokens and still has a session
            # id worth keeping. A degraded morning is the one you most want
            # the transcript of.
            "last_attempt_usage": usage or None,
            "quantifier_flags": flags_raised or None,
        }
    else:
        usage["status"] = "ok"
        usage["fallback"] = False
        if warned:
            usage["quantifier_flags"] = flags_raised
            usage["quantifier_warned"] = True
            report_text = annotate_warned_quantifiers(report_text, warned, warned_ids)
        elif flags_raised:
            # The regeneration worked. Worth recording next to the report it
            # rescued: this is the number that says whether the guard is cheap.
            usage["quantifier_flags"] = flags_raised
            usage["quantifier_regenerated"] = True
    usage["quantifier_guard"] = GUARD_ENFORCING if enforcing else GUARD_WARN

    # Overdue scheduled steps, named before the report is written rather than
    # after, so the deterministic fallback report carries the line too.
    report_text = annotate_job_health(report_text, packet)

    report_path.write_text(report_text, encoding="utf-8")
    job_status.produced("report characters", len(report_text))
    if usage.get("fallback"):
        # The deterministic fallback is a real report and a real zero exit, and
        # the morning still gets numbers. It is not the model narrating, and a
        # run of fallback mornings is a thing to notice rather than discover.
        job_status.failed(f"{cause}, fell back to numbers only: "
                          f"{usage.get('error_message')}")
    elif usage.get("quantifier_warned"):
        # Warn mode. Not a failed step either: nothing was withheld and the
        # report is exactly what the model wrote. The flags are on the
        # disclaimer line, in the log with outcome warned, and in the
        # watchdog's unjudged count.
        print(f"analyst: {len(warned)} quantifier flag(s) recorded in warn mode "
              "and published. Judge them so the switch can flip: "
              f"{quantifier_flags.RUN_PREFIX} --pending")
    elif usage.get("quantifier_regenerated"):
        # Deliberately NOT job_status.failed. The morning got its narrative,
        # so calling the step failed would be crying wolf on a good report,
        # and a STEP FAILED that fires on good mornings is one nobody reads by
        # the end of the month. The event is already recorded three places
        # that cost nothing to ignore and nothing to find: the flag log with
        # its outcome, analyst_usage.json, and the watchdog's unjudged count.
        print("analyst: the quantifier guard rejected the first attempt and the "
              "regeneration passed. The narrative was delivered and the flag "
              "stands, logged as regenerated; judge it with "
              f"{quantifier_flags.RUN_PREFIX} --pending")
    print(f"analyst: wrote {report_path} ({len(report_text)} chars, status {usage['status']})")

    # Checked again, on purpose. The loop above asked the containment question
    # of the raw model text to decide whether to retry; this asks it of the
    # file that is actually on disk, job health line and all, because the
    # recorded coverage has to describe what was written rather than what was
    # considered.
    invented, missing, coverage = check_report(report_text, packet_text)
    if coverage["claims_checked"] == 0 or coverage["structure_failed"]:
        # A pass that examined nothing is not a pass, and the reader must be
        # able to tell. The disclaimer line gets the statement.
        report_text = annotate_unvalidated(report_text, coverage)
        report_path.write_text(report_text, encoding="utf-8")
        print("analyst: containment examined nothing "
              f"({_why_unvalidated(coverage)}); the disclaimer now states that "
              "ticker claims were not validated")

    usage["generated_at"] = ettime.stamp(ettime.now_et())
    usage["packet"] = str(packet_path)
    usage["containment"] = {
        **coverage,
        "invented": invented,
        "candidates_missing_from_report": missing,
    }
    usage_path = run_directory / "analyst_usage.json"
    usage_path.write_text(json.dumps(usage, indent=2, sort_keys=True), encoding="utf-8")
    if usage["status"] == "ok":
        print(
            "analyst: tokens in "
            f"{usage.get('input_tokens')} (cache write {usage.get('cache_creation_input_tokens')}, "
            f"cache read {usage.get('cache_read_input_tokens')}), out {usage.get('output_tokens')}, "
            f"cost ${usage.get('total_cost_usd')}, {usage.get('duration_ms')} ms"
        )

    if missing:
        print(
            "analyst: WARNING these packet candidates never appear in the report: "
            + ", ".join(missing)
        )
    if invented:
        print(
            "analyst: FAILED the containment check. These tickers are presented "
            "as tickers, exist in the universe, and are nowhere in the packet: "
            + ", ".join(invented)
        )
        print("analyst: the report was written for inspection but must not be delivered.")
        return 2
    if coverage["structure_failed"]:
        print("analyst: FAILED the containment check on structure. "
              + coverage["structure_reason"])
        print("analyst: the report was written for inspection but must not be delivered.")
        return 2
    # There is no quantifier check here. It moved into the narration loop
    # above, where a flag can still be answered with a regeneration and then
    # with the plain table. Running it again on the way out would put the old
    # failure back: the text on disk at this point is either model prose the
    # guard already cleared, or the fallback, whose disclaimer quotes the
    # rejected sentence and would fail a guard reading it as a claim.
    if coverage["claims_checked"]:
        print(f"analyst: containment check passed: {coverage['claims_checked']} "
              f"ticker claims validated across {coverage['columns_scanned']} "
              "ticker columns, every claim exists in the packet")
    return 0


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write report.md from packet.json via the claude CLI.")
    parser.add_argument("--packet", metavar="PATH",
                        help="Packet to narrate. Defaults to runs/<today>/packet.json.")
    parser.add_argument("--check", metavar="REPORT",
                        help="Run only the containment check on an existing report.")
    args = parser.parse_args(argv)

    packet_path = (
        Path(args.packet) if args.packet
        else config.run_path(ettime.today_et().isoformat()) / "packet.json"
    )
    if not packet_path.is_file():
        print(f"analyst: there is no packet at {packet_path}. Run scan.py first.")
        return 1

    if args.check:
        report_path = Path(args.check)
        invented, missing, coverage = check_report(
            report_path.read_text(encoding="utf-8"),
            packet_path.read_text(encoding="utf-8"),
        )
        print(f"analyst: coverage {coverage}")
        if missing:
            print("analyst: candidates missing from the report: " + ", ".join(missing))
        if invented:
            print("analyst: tickers not in the packet: " + ", ".join(invented))
            return 2
        if coverage["structure_failed"]:
            print("analyst: FAILED the containment check on structure. "
                  + coverage["structure_reason"])
            return 2
        quantifiers = quantifier_violations(report_path.read_text(encoding="utf-8"))
        if quantifiers:
            # --check is the operator path over a report already on disk, so it
            # reports without appending: replaying an old morning must not add
            # flags to the running rate that were already counted when it ran.
            for hit in quantifiers:
                print(f"analyst: quantifier guard, line {hit['line']}: matched "
                      f"{hit['quantifier']!r} near {hit['set_word']!r}")
                print(f"    {hit['text']}")
            print("analyst: not logged, --check replays a report rather than "
                  "producing one. See ops/quantifier_flags.py for the running rate.")
            return 2
        if coverage["claims_checked"] == 0:
            print("analyst: containment examined nothing "
                  f"({_why_unvalidated(coverage)}), which is not a pass")
        else:
            print("analyst: containment check passed")
        return 0

    return write_report(packet_path)


if __name__ == "__main__":
    raise SystemExit(job_status.run("analyst", main, ok_codes=OK_CODES))
