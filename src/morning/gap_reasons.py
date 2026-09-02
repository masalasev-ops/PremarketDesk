"""What actually moved each name, in one or two plain sentences.

WHY THIS EXISTS. The gappers table carried a Top headline column, which is the
NEWEST story the feed tagged to a symbol and nothing more. On 2026-09-01 that
put "Palantir Leads Tech Stocks as Nasdaq Rebounds" against MSTR, a market wrap
about a different company, while eleven other MSTR stories sat in the window
unread. A column that answers "what is the most recent thing tagged to this"
when the reader is asking "why did this move" is not a small formatting problem.
The owner's words: it is making no improvement.

WHAT THIS IS NOT. It is not a second catalyst class and it touches no score. The
class is structured data read from vendor tags and it stays that way; this is
prose for a human, generated from the headlines the feed already returned, and
nothing downstream branches on it. Keeping the two apart is deliberate: a
sentence a model wrote must never become a number the screen acts on.

THE GROUNDING RULE, which is the whole of the safety here. The model is handed
one name's headlines and asked to answer from THOSE, naming the headline it
used. An answer whose named headline is not one of the ones supplied for that
symbol is DISCARDED, because a model that cannot point at its evidence is
guessing, and a plausible guess about why a stock moved is exactly the kind of
fabricated evidence this project refuses everywhere else. A name it cannot
explain gets a written "no story here explains it", which is a real and useful
answer: it says the move was not news driven, or that the feed missed it.

NOTHING IS INVENTED AND NOTHING IS SILENT. A refused row, a failed call and a
name with no headlines at all each carry their own reason, so the section can
never read as though a question was answered when it was not.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from core import config
from core import criteria

_CRIT = criteria.load()

# How many headlines one name may contribute. A cap, because a name with 45
# stories would otherwise crowd out the eleven others in the same request.
MAX_HEADLINES = 12

NO_NEWS = "no_headlines"
REFUSED = "refused"
UNANSWERED = "unanswered"

_SYSTEM = (
    "You explain why shares moved, for a reader with no finance background. "
    "You answer only from the headlines you are given and you never use "
    "outside knowledge. Output only JSON."
)

_INSTRUCTIONS = """You are given today's premarket gappers and the news headlines the feed
returned for each one. For each ticker, say in ONE or TWO short sentences what
the headlines suggest moved it.

RULES, and the third one matters most.

1. Write for somebody with no finance background. No jargon. If you must use a
   term like guidance or downgrade, say what it means in the same sentence.
2. Say what happened and why it would move the price. "It reported profits
   that beat what analysts expected" is useful. "Earnings catalyst" is not.
3. ANSWER ONLY FROM THE HEADLINES SUPPLIED FOR THAT TICKER. You must copy the
   exact title of the one headline you relied on into the "headline" field. If
   the headlines for a ticker are about the wider market, another company, or
   otherwise do not explain that ticker's move, set "why" to a short sentence
   saying the stories tagged to it do not explain the move, and set "headline"
   to null. That is a correct and expected answer. Do NOT reach for an
   explanation that is not in the headlines.
4. Do not predict, do not advise, and do not say whether the move will
   continue.

Output a single JSON object, no markdown fence, mapping each ticker to an
object with "why" and "headline". Include every ticker you were given.

Example shape:
{"AAA": {"why": "It said it will earn less this year than it had previously
told investors, which is why the price fell.", "headline": "AAA cuts full year
outlook"}, "BBB": {"why": "The stories tagged to it are about the market as a
whole rather than about this company, so they do not explain its move.",
"headline": null}}
"""


def _rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One compact record per candidate, headlines capped."""
    out = []
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "")
        if not symbol:
            continue
        # headlines_all is the whole window and headlines is the display cap of
        # three. The wider one where it exists, because a packet written before
        # it did must still be explainable.
        articles = (candidate.get("headlines_all")
                    or candidate.get("headlines") or [])
        titles = [str(a.get("title") or "").strip()
                  for a in articles if str(a.get("title") or "").strip()]
        out.append({
            "ticker": symbol.split(".", 1)[0],
            "symbol": symbol,
            "name": candidate.get("name") or candidate.get("instrument_name"),
            "gap_pct": candidate.get("gap_pct"),
            "titles": titles[:MAX_HEADLINES],
        })
    return out


def build_document(candidates: list[dict[str, Any]]) -> tuple[str, dict[str, list[str]]]:
    """The piped document, and the titles each ticker is allowed to cite."""
    rows = _rows(candidates)
    allowed = {row["ticker"]: row["titles"] for row in rows}
    lines = [_INSTRUCTIONS, "", "THE GAPPERS AND THEIR HEADLINES", ""]
    for row in rows:
        gap = row["gap_pct"]
        moved = ("moved an unrecorded amount" if gap is None
                 else f"gapped {'up' if gap > 0 else 'down'} {abs(gap):.2f} percent")
        lines.append(f"{row['ticker']} ({row['name'] or 'name not recorded'}), {moved}.")
        if row["titles"]:
            for title in row["titles"]:
                lines.append(f"  - {title}")
        else:
            lines.append("  - (the feed returned no headlines for this ticker)")
        lines.append("")
    return "\n".join(lines), allowed


_TICKER_OBJECT_RE = re.compile(
    r'"([A-Z][A-Z0-9.\-]{0,9})"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})')


def _parse(text: str) -> dict[str, Any] | None:
    """The JSON object out of the model's answer, or None.

    Whole document first. When that fails, the per ticker objects are salvaged
    one at a time, because until 2026-09-02 a single unbalanced brace in one
    ticker's `why` lost the section for every ticker: the whole answer was
    sliced from the first `{` to the last `}` and either parsed or did not.
    A ticker whose own object cannot be parsed is simply absent from the
    payload, and validate() then records it as unanswered with the reason, so
    the reader sees eleven explanations and one refusal rather than none.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(body[start:end + 1])
        if isinstance(payload, dict):
            return payload
    except ValueError:
        pass
    salvaged: dict[str, Any] = {}
    for match in _TICKER_OBJECT_RE.finditer(body):
        try:
            value = json.loads(match.group(2))
        except ValueError:
            continue
        if isinstance(value, dict):
            salvaged[match.group(1)] = value
    return salvaged or None


def validate(payload: dict[str, Any],
             allowed: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Keep only what the model can point at. Everything else gets a reason.

    THE CITED HEADLINE HAS TO BE ONE WE SUPPLIED, for that ticker. A model that
    names a headline nobody gave it has left the evidence behind, and a
    confident sentence about why a stock moved is the most persuasive shape a
    fabrication can take.
    """
    out: dict[str, dict[str, Any]] = {}
    for ticker, titles in allowed.items():
        answer = payload.get(ticker) if isinstance(payload, dict) else None
        if not titles:
            out[ticker] = {
                "why": None, "headline": None, "state": NO_NEWS,
                "reason": ("the news feed returned no story carrying this "
                           "ticker in the window, so there is nothing to "
                           "explain the move from")}
            continue
        if not isinstance(answer, dict) or not str(answer.get("why") or "").strip():
            out[ticker] = {
                "why": None, "headline": None, "state": UNANSWERED,
                "reason": "the explanation pass returned nothing for this ticker"}
            continue
        cited = answer.get("headline")
        cited_text = str(cited).strip() if cited is not None else None
        if cited_text and cited_text not in titles:
            out[ticker] = {
                "why": None, "headline": None, "state": REFUSED,
                "reason": ("the explanation named a headline that was not "
                           "among the ones supplied for this ticker, so it was "
                           "discarded rather than published unsourced")}
            continue
        out[ticker] = {
            "why": str(answer["why"]).strip(),
            "headline": cited_text,
            "state": "explained" if cited_text else "not_explained_by_the_feed",
            "reason": None}
    return out


def explain(candidates: list[dict[str, Any]]
            ) -> tuple[dict[str, dict[str, Any]], dict[str, Any], str | None]:
    """(per ticker records, usage, error). Never raises for a model failure."""
    from core import store
    from morning import analyst

    # NO SUBPROCESS WHILE TEST CODE IS LOADED. The suite stubs
    # analyst.invoke_claude and knew nothing about this second call, so the
    # first claim to reach write_report would have shelled out to the real CLI
    # and the suite would have stopped being hermetic without anybody deciding
    # that it should. Guarded by the import graph rather than by a flag
    # somebody has to remember, which is the argument store.guard_live_database
    # already makes for the database.
    loaded = store._test_module_is_loaded()
    if loaded is not None:
        return {}, {}, (f"{loaded} is loaded, so the explanation pass refused "
                        "to start a model subprocess. The suite is hermetic by "
                        "construction rather than by stubbing")

    document, allowed = build_document(candidates)
    if not allowed:
        return {}, {}, "there are no candidates to explain"

    model = _CRIT.text("analyst", "model")
    timeout_s = _CRIT.integer("analyst", "timeout_s")
    try:
        command = [
            analyst.resolve_cli(), "-p", "--model", model,
            "--output-format", "json", "--tools", "",
            "--effort", _CRIT.text("analyst", "effort"),
            "--system-prompt", _SYSTEM,
        ]
    except FileNotFoundError as exc:
        return {}, {}, str(exc)

    try:
        proc = subprocess.run(
            command, input=document, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
            env=analyst._scrubbed_env(), cwd=str(config.PROJECT_ROOT))
    except subprocess.TimeoutExpired:
        return {}, {}, f"the explanation pass timed out after {timeout_s}s"
    except OSError as exc:
        return {}, {}, f"the claude CLI could not be started: {exc}"

    if proc.returncode != 0:
        return {}, {}, (f"the claude CLI exited {proc.returncode}: "
                        f"{config.scrub_secrets(proc.stderr.strip()[:300])}")

    usage: dict[str, Any] = {}
    text = proc.stdout
    try:
        envelope = json.loads(proc.stdout)
    except ValueError:
        envelope = None
    if isinstance(envelope, dict):
        usage = {key: envelope.get(key) for key in
                 ("total_cost_usd", "duration_ms", "num_turns", "usage")
                 if key in envelope}
        text = str(envelope.get("result") or "")

    payload = _parse(text)
    if payload is None:
        return {}, usage, "the explanation pass returned no readable JSON"
    return validate(payload, allowed), usage, None


HEADING = "Why these gapped"


def section(records: dict[str, dict[str, Any]], error: str | None = None,
            level: str = "###") -> list[str]:
    """The markdown, ready to insert under the gappers table."""
    out = [f"{level} {HEADING}", ""]
    if error:
        out += [f"This section could not be written: {error}. The table above "
                "is unaffected.", ""]
        return out
    if not records:
        out += ["There were no gappers to explain.", ""]
        return out
    out += ["What the news the feed carried says about each move, in plain "
            "language. Where the stories tagged to a name do not explain it, "
            "this says so rather than reaching for a reason.", ""]
    for ticker in sorted(records):
        record = records[ticker]
        if record.get("why"):
            line = f"**{ticker}.** {record['why']}"
            if record.get("headline"):
                line += f" (Headline: {record['headline']})"
        else:
            line = f"**{ticker}.** Not explained here: {record.get('reason')}."
        out += [line, ""]
    return out
