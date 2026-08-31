"""The 12:00 pass: what the picks did, and what else moved.

Two questions the morning cannot answer, because at 08:45 the session it is
about has not opened yet.

  CARRY THROUGH  every live picks row for today, graded against the levels the
                 morning published. CRITERIA [Midday] carry through note holds
                 the rule and the reason it is [Paper]'s rule run against what
                 a daily quote can say rather than [Paper]'s rule itself.
  MOVERS         today's move across the whole universe, ranked, with news
                 fetched afterwards for the top of the list. Selection is on
                 PRICE. News explains what price found and never decides
                 membership, for the reason CRITERIA gives.

TODAY'S PRICES come from us-quote-delayed. EODHD does not publish today's
intraday bars until overnight, measured 2026-08-31 and written up in DECISIONS,
so the endpoint the night measures the morning with is unavailable here at any
hour of the trading day.

THE DENOMINATOR DOES NOT. Every move reported here is measured against the
prior session's close, and that close comes from eod-bulk-last-day for an
EXPLICITLY NAMED date. It is emphatically NOT the quote's own
previousClosePrice field, which was measured on 2026-08-31 and is not one
quantity: it matched the prior session for 34 percent of names and TODAY'S
close for 29 percent, with nothing in the payload saying which a given row
carried, and for SAIC.US it matched neither. See CRITERIA [Midday] the
denominator note. This is the same shape as the 2026-08-14 defect, where an
endpoint whose name said live served the last completed session.

NOTHING HERE WRITES TO picks OR paper_trades. Both are records of what an
earlier pass claimed, and a second writer booking against uncorrected levels
would destroy the comparison they exist for. This writes one packet.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from typing import Any

from core import artifacts
from core import config
from core import criteria
from core import eodhd
from core import ettime
from core import store
from ops import job_status

_CRIT = criteria.load()

PACKET_FILE = "midday_packet.json"

MAX_QUOTE_AGE_S = _CRIT.number("midday", "max_quote_age_seconds")
REQUIRE_PRIOR_CLOSE = _CRIT.flag("midday", "require_prior_session_close")
LIST_SIZE = _CRIT.integer("midday", "list_size")
NEWS_LOOKUPS = _CRIT.integer("midday", "news_lookups")
RANK_BY = _CRIT.text("midday", "rank_by")
OPEN_TOLERANCE_PCT = _CRIT.number("midday", "open_tolerance_pct")

# Verdicts. Named here so the renderer and the claims spell them one way.
NEVER_TRIGGERED = "never_triggered"
GAPPED_THROUGH = "gapped_through"
TRIGGERED = "triggered"
UNKNOWN = "unknown"

# What a stop can be said to have done, and the middle one is the whole reason
# CRITERIA argues for extending the collector past the open.
STOP_HELD = "held"
STOP_OUT = "stopped_out"
STOP_SEQUENCE_UNKNOWN = "stop_level_reached_sequence_unknown"
STOP_NOT_APPLICABLE = "not_applicable"


class PriorSessionUnknown(RuntimeError):
    """The session calendar could not name the session before today."""


def prior_session(api: eodhd.EodhdClient, today: dt.date) -> str:
    """The trading session before today, off the calendar symbol's EOD bars.

    Never weekday arithmetic, for the reason [Outcomes] gives: a Monday holiday
    makes the prior session Thursday and weekday math would compare against a
    day nobody traded. This is the denominator's expected date and every quote
    is checked against it.
    """
    symbol = _CRIT.text("universe", "session_calendar_symbol")
    bars, error = api.eod(symbol, start=today - dt.timedelta(days=15), end=today)
    if error or not bars:
        raise PriorSessionUnknown(
            f"session calendar unavailable from {symbol}: {error or 'no rows'}. "
            "Every move this pass reports is measured against the prior "
            "session's close, so without the calendar there is no denominator "
            "to check and the whole scan is refused rather than dated by "
            "weekday arithmetic.")
    dates = sorted({str(b["date"]) for b in bars if b.get("date")})
    today_str = today.isoformat()
    earlier = [d for d in dates if d < today_str]
    if not earlier:
        raise PriorSessionUnknown(
            f"the calendar's {len(dates)} sessions from {symbol} carry nothing "
            f"before {today_str}")
    return earlier[-1]


class PriorClosesUnusable(RuntimeError):
    """The prior session's closes could not be fetched, or are the wrong day."""


def prior_closes(api: eodhd.EodhdClient, expect_prior: str) -> dict[str, float]:
    """Every US close for one NAMED session, in one call.

    100 credits flat by [Quota costs] eod-bulk-last-day, and it covers the whole
    exchange rather than the universe, so the 359 names us-quote-delayed
    declined to carry a previous close for on 2026-08-31 are all answered by it.

    Verified 2026-08-31 against the single symbol eod endpoint that
    fill_outcomes and the morning already trust: the two agreed exactly on
    every name checked, while the quote's own previousClosePrice disagreed with
    both. Asking for a DATE is what makes this safe. There is no roll time to
    be on the wrong side of, because the request names the session.
    """
    result = api.eod_bulk_last_day("US", day=ettime.parse_date(expect_prior))
    if not result.ok:
        raise PriorClosesUnusable(
            f"the prior session's closes for {expect_prior} could not be "
            f"fetched: {config.scrub_secrets(result.error)}. Every move this "
            "pass reports divides by one of them, so there is nothing to "
            "publish rather than something to publish against a worse "
            "denominator")
    closes: dict[str, float] = {}
    wrong_date = 0
    for row in result.data or []:
        code = str(row.get("code") or "").strip().upper()
        close = _f(row.get("close"))
        if not code or close is None:
            continue
        if str(row.get("date") or "").strip() != expect_prior:
            wrong_date += 1
            continue
        closes[f"{code}.US"] = close
    if wrong_date:
        raise PriorClosesUnusable(
            f"{wrong_date:,} of the bulk rows for {expect_prior} carry a "
            "different date, so the payload is not the session it was asked "
            "for and no row from it may be used as a denominator")
    if not closes:
        raise PriorClosesUnusable(
            f"the bulk payload for {expect_prior} carried no usable closes")
    return closes


def _f(value: Any) -> float | None:
    """A float, or None. A blank string is not a zero."""
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _prev_close_date(raw: Any) -> str | None:
    """The date half of previousCloseDate, which arrives as '2026-08-28 17:00:00'."""
    text = str(raw or "").strip()
    return text.split(" ")[0] if text else None


def read_quote(row: dict[str, Any], now: dt.datetime, expect_prior: str,
               prior_close: float | None) -> dict[str, Any]:
    """One quote turned into today's session facts, or into a written reason.

    THREE FIELDS THIS DELIBERATELY DOES NOT READ, each for a measured reason.

      previousClosePrice  not one quantity. See the module docstring and
                          CRITERIA [Midday] the denominator note. prior_close
                          is passed in from eod-bulk-last-day instead.
      ethPrice, ethTime   stale at 08:45 on the morning they were needed,
                          2026-08-17, and this pass has no use for them.

    previousCloseDate IS read, and only to be reported. It was correct on every
    row measured while the price beside it was not, so it is evidence about the
    vendor rather than a check on anything, and nothing branches on it.
    """
    out: dict[str, Any] = {
        "open": _f(row.get("open")),
        "high": _f(row.get("high")),
        "low": _f(row.get("low")),
        "last": _f(row.get("lastTradePrice")),
        "prev_close": prior_close,
        "prev_close_source": "eod-bulk-last-day" if prior_close is not None else None,
        "vendor_prev_close_date_reported": _prev_close_date(row.get("previousCloseDate")),
        "volume": _f(row.get("volume")),
        "average_volume": _f(row.get("averageVolume")),
        "market_cap": _f(row.get("marketCap")),
        "name": (str(row.get("name") or "").strip() or None),
        "last_trade_at": None,
        "quote_age_seconds": None,
        "refused_reason": None,
    }

    stamped = ettime.from_epoch_ms(row.get("lastTradeTime"))
    if stamped is not None:
        out["last_trade_at"] = ettime.stamp(stamped)
        out["quote_age_seconds"] = int((now - stamped).total_seconds())

    # The denominator check. Not a check on the vendor's date field, which
    # proved worthless: it was RIGHT on rows whose price was wrong. This asks
    # whether the named prior session actually carried a close for this symbol.
    if REQUIRE_PRIOR_CLOSE and prior_close is None:
        out["refused_reason"] = (
            f"the {expect_prior} bulk close payload carries no close for this "
            "symbol, so there is no denominator for its move and it is left "
            "unmeasured rather than measured against the quote's own "
            "previousClosePrice, which is not one quantity")
    elif out["quote_age_seconds"] is None:
        out["refused_reason"] = (
            "the quote carried no lastTradeTime, so how old its prices are is "
            "unknown rather than merely large")
    elif out["quote_age_seconds"] > MAX_QUOTE_AGE_S:
        out["refused_reason"] = (
            f"its last trade is {out['quote_age_seconds']:,} seconds old "
            f"against the {MAX_QUOTE_AGE_S:,.0f} second limit in CRITERIA "
            "[Midday] max_quote_age_seconds")

    if out["refused_reason"]:
        for field in ("open", "high", "low", "last", "prev_close"):
            out[field] = None
    return out


def _pct(a: float | None, b: float | None) -> float | None:
    """a against b, in percent. None if either is missing or b is zero."""
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1.0) * 100.0, 4)


def grade(pick: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    """CRITERIA [Midday]'s four state rule, and it refuses to invent a sequence.

    The order of the branches is the order CRITERIA writes them, and the first
    one is first because the prototype on 2026-08-31 got it wrong: it read the
    session low against the stop on a row that never filled, where a low with
    no trade under it stops nothing.
    """
    entry = _f(pick.get("entry_ref"))
    stop = _f(pick.get("stop_ref"))
    o, hi, lo, last = quote["open"], quote["high"], quote["low"], quote["last"]

    out: dict[str, Any] = {
        "ticker": pick["ticker"],
        "score": pick.get("score"),
        "conviction": pick.get("conviction"),
        "day_eligible": pick.get("day_eligible"),
        "swing_eligible": pick.get("swing_eligible"),
        "gap_pct": pick.get("gap_pct"),
        "entry_ref": entry,
        "stop_ref": stop,
        "pm_high": _f(pick.get("pm_high")),
        "pm_low": _f(pick.get("pm_low")),
        "open": o, "high": hi, "low": lo, "last": last,
        "prev_close": quote["prev_close"],
        "volume": quote["volume"],
        "average_volume": quote["average_volume"],
        "day_rvol": None,
        "move_pct": _pct(last, quote["prev_close"]),
        "state": UNKNOWN,
        "state_reason": None,
        "fill": None,
        "fill_basis": None,
        "now_vs_fill_pct": None,
        "best_vs_fill_pct": None,
        "worst_vs_fill_pct": None,
        "worst_vs_fill_reason": None,
        "stop_state": STOP_NOT_APPLICABLE,
        "stop_state_reason": None,
        "decided_inside_the_open_tolerance": False,
        "open_tolerance_reason": None,
        "levels_are": ("entry_ref and stop_ref as the morning published them, "
                       "not the entry_ref_true and stop_ref_true the night "
                       "corrects them to. See CRITERIA [Midday]."),
    }
    if quote["volume"] and quote["average_volume"]:
        out["day_rvol"] = round(quote["volume"] / quote["average_volume"], 4)

    if quote["refused_reason"]:
        out["state_reason"] = quote["refused_reason"]
        return out
    if entry is None or o is None or hi is None:
        missing = [n for n, v in (("entry_ref", entry), ("open", o), ("high", hi))
                   if v is None]
        out["state_reason"] = (
            f"the grade needs {', '.join(missing)} and the quote did not carry "
            "it, so this row is unknown rather than untriggered")
        return out

    if hi < entry:
        out["state"] = NEVER_TRIGGERED
        out["state_reason"] = (
            f"the session high {hi:g} came up {_pct(hi, entry):.2f} percent "
            f"short of the {entry:g} entry")
        out["stop_state_reason"] = (
            "no fill, so the session low is not read against the stop: a low "
            "with no trade under it stops nothing")
        return out

    if o >= entry:
        out["state"] = GAPPED_THROUGH
        out["fill"] = o
        out["fill_basis"] = ("the session open, which carried through the entry, "
                             "exactly as CRITERIA [Paper] fills a gap through")
        out["state_reason"] = (
            f"the open {o:g} was {_pct(o, entry):+.2f} percent past the "
            f"{entry:g} entry")
    else:
        out["state"] = TRIGGERED
        out["fill"] = entry
        out["fill_basis"] = "the entry reference, reached after the open"
        out["state_reason"] = (
            f"the open {o:g} was below the {entry:g} entry and the session high "
            f"{hi:g} reached it, {_pct(hi, entry):+.2f} percent past")

    # Whether the open cleared the entry decides the whole row, and the quote's
    # open is not the opening auction print. Measured 2026-08-31 across 2,750
    # names: it agreed with the session's official open for 70 percent and
    # disagreed by a median 0.34 percent for the rest, worst among the least
    # liquid. So a row decided by less than that is flagged rather than
    # presented as settled.
    margin = _pct(o, entry)
    if margin is not None and abs(margin) <= OPEN_TOLERANCE_PCT:
        out["decided_inside_the_open_tolerance"] = True
        out["open_tolerance_reason"] = (
            f"the open was {margin:+.2f} percent from the entry, inside the "
            f"{OPEN_TOLERANCE_PCT:g} percent tolerance in CRITERIA [Midday] "
            "open_tolerance_pct. us-quote-delayed's open is the first "
            "consolidated print and not the opening auction, so this row could "
            f"read {TRIGGERED} rather than {GAPPED_THROUGH} against the "
            "official open, or the reverse")

    fill = out["fill"]
    out["now_vs_fill_pct"] = _pct(last, fill)
    out["best_vs_fill_pct"] = _pct(hi, fill)

    if out["state"] == GAPPED_THROUGH:
        # The fill is the session's FIRST print, so everything after it is
        # after it. Order is knowable here and only here.
        out["worst_vs_fill_pct"] = _pct(lo, fill)
    else:
        out["worst_vs_fill_reason"] = (
            "the fill happened after the open, and a daily low carries no "
            "timestamp, so whether the session low came before or after the "
            "fill is unknowable from a quote")

    if stop is None:
        out["stop_state_reason"] = (
            "the morning published no stop reference for this row, so there is "
            "no level to judge the low against")
    elif lo is None:
        out["stop_state_reason"] = (
            "the quote carried no session low, so whether the stop was reached "
            "is unknown rather than no")
    elif lo > stop:
        out["stop_state"] = STOP_HELD
        out["stop_state_reason"] = (
            f"the session low {lo:g} stayed above the {stop:g} stop")
    elif out["state"] == GAPPED_THROUGH:
        out["stop_state"] = STOP_OUT
        out["stop_state_reason"] = (
            f"the session low {lo:g} reached the {stop:g} stop, and the fill "
            "was the opening print, so the low is unambiguously after it")
    else:
        out["stop_state"] = STOP_SEQUENCE_UNKNOWN
        out["stop_state_reason"] = (
            f"the session low {lo:g} reached the {stop:g} stop, but the fill "
            "happened after the open and a daily low carries no timestamp, so "
            "whether that low came before or after the fill cannot be told "
            "from a quote. Extending CRITERIA [Collector] stop_time past the "
            "open is what would answer it")
    return out


# How many names each unpriced bucket names before it stops naming them. A
# count with no examples cannot be chased; 2,751 names in a packet cannot be
# read. See the unpriced note in the returned tally.
UNPRICED_EXAMPLES = 12


def rank_movers(quotes: dict[str, dict[str, Any]],
                named_this_morning: set[str],
                subscribed: set[str],
                pooled: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Everything clearing all three floors, ranked, with the tally behind it.

    A name the morning already named is excluded, because this half of the
    report is about what the morning did NOT say. A name discover ranked and
    the screen then passed over is KEPT and flagged, because the screen having
    seen it and declined it is a different fact from never having seen it.

    Nothing is dropped into a bare count. Every name that fails to be priced is
    counted under the FIELD that was missing and a capped sample is named,
    because 358 names in an unpriced bucket on 2026-08-31 could not be chased
    to a cause from the packet alone, which is the silence this project keeps
    losing measurements to.
    """
    move_rule = _CRIT.rule("midday", "min_move_pct")
    rvol_rule = _CRIT.rule("midday", "min_day_rvol")
    price_rule = _CRIT.rule("midday", "min_price")

    tally: dict[str, Any] = {
        "quoted": len(quotes), "refused": 0, "named_this_morning": 0,
        "no_last_price": 0, "no_previous_close": 0, "no_average_volume": 0,
        "no_volume": 0, "below_price": 0, "below_move": 0, "below_rvol": 0,
        "admitted": 0,
        "examples": {"no_last_price": [], "no_previous_close": [],
                     "no_average_volume": [], "no_volume": []},
        "unpriced_note": (
            "each of the four unpriced counts names the FIELD the vendor did "
            f"not carry, and the first {UNPRICED_EXAMPLES} symbols in each are "
            "listed. A name here was not judged and did not fail a floor"),
    }

    def lose(bucket: str, symbol: str) -> None:
        tally[bucket] += 1
        if len(tally["examples"][bucket]) < UNPRICED_EXAMPLES:
            tally["examples"][bucket].append(symbol)

    rows: list[dict[str, Any]] = []
    for symbol, q in quotes.items():
        if q["refused_reason"]:
            tally["refused"] += 1
            continue
        if symbol in named_this_morning:
            tally["named_this_morning"] += 1
            continue
        if q["last"] is None:
            lose("no_last_price", symbol)
            continue
        if q["prev_close"] is None or q["prev_close"] == 0:
            lose("no_previous_close", symbol)
            continue
        if not q.get("average_volume"):
            lose("no_average_volume", symbol)
            continue
        if not q.get("volume"):
            lose("no_volume", symbol)
            continue
        move = _pct(q["last"], q["prev_close"])
        if not price_rule.test(q["last"]):
            tally["below_price"] += 1
            continue
        if not move_rule.test(abs(move)):
            tally["below_move"] += 1
            continue
        rvol = q["volume"] / q["average_volume"]
        if not rvol_rule.test(rvol):
            tally["below_rvol"] += 1
            continue
        tally["admitted"] += 1
        rows.append({
            "symbol": symbol,
            "name": q["name"],
            "last": q["last"],
            "prev_close": q["prev_close"],
            "move_pct": move,
            "open": q["open"], "high": q["high"], "low": q["low"],
            "volume": q["volume"],
            "average_volume": q["average_volume"],
            "day_rvol": round(rvol, 4),
            "market_cap": q["market_cap"],
            # Three states and not two. The collector can only price what it
            # SUBSCRIBED to, 42 names of a pool that was 851 on 2026-08-31, so
            # "discover had it" and "the morning could have priced it" are
            # different facts and collapsing them would overstate the second.
            "morning_reach": (
                "subscribed" if symbol in subscribed else
                "pooled_not_subscribed" if symbol in pooled else "not_pooled"),
            "morning_reach_note": (
                "the collector was subscribed to this name and the 08:45 screen "
                "still did not publish it" if symbol in subscribed else
                "discover ranked this name into the pool at 07:15 and the "
                "subscription cap in CRITERIA [Collector] max_subscriptions cut "
                "it, so no premarket tape was ever collected for it"
                if symbol in pooled else
                "discover did not have this name at 07:15 at all, so nothing "
                "this morning could have reached it"),
            "news": None,
            "news_reason": None,
        })

    key = (lambda r: (-abs(r["move_pct"]), r["symbol"])) if RANK_BY == "move" else (
        lambda r: (-r["day_rvol"], r["symbol"]))
    rows.sort(key=key)
    return rows, tally


def attach_news(api: eodhd.EodhdClient, rows: list[dict[str, Any]],
                today: dt.date) -> int:
    """Headlines for the top of the ranked list. Never a membership filter.

    Called AFTER ranking, on rows price already chose, which is the whole
    argument in CRITERIA [Midday]: a news led scan cannot say it is blind to a
    mover with no tagged headline, and this one can.
    """
    fetched = 0
    for row in rows[:NEWS_LOOKUPS]:
        result = api.news(row["symbol"], start=today, end=today, limit=5)
        fetched += 1
        if not result.ok:
            row["news_reason"] = config.scrub_secrets(
                f"the news lookup failed, so why this name moved is unknown "
                f"rather than absent: {result.error}")
            continue
        # unescape, because the feed delivers "PG&amp;E" and a reader should
        # see "PG&E". The renderer escapes on the way out, which is the only
        # place escaping belongs: this is third party text and render_report
        # already carries the argument for why it is never trusted as markup.
        items = [
            {"title": html.unescape(str(item.get("title") or "")).strip(),
             "date": str(item.get("date") or "").strip()}
            for item in (result.data or [])
            if str(item.get("title") or "").strip()
        ]
        row["news"] = items
        if not items:
            row["news_reason"] = (
                "the vendor tagged no story to this symbol today, so this name "
                "moved on something the feed does not carry under its ticker. "
                "That is a silence in the feed and not evidence of no news")
    for row in rows[NEWS_LOOKUPS:]:
        row["news_reason"] = (
            f"outside the top {NEWS_LOOKUPS} the scan looks news up for, "
            "CRITERIA [Midday] news_lookups")
    return fetched


def morning_context(day: str) -> dict[str, Any]:
    """What the 08:45 report named, read off disk. No vendor call."""
    out: dict[str, Any] = {
        "packet_found": False, "packet_reason": None,
        "named_this_morning": [], "pooled": [], "subscribed": [],
        "watchlist_reason": None,
    }
    packet_path = config.RUNS_DIR / day / "packet.json"
    if packet_path.is_file():
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        out["packet_found"] = True
        named = {str(c.get("symbol") or "").upper()
                 for c in (packet.get("candidates") or [])}
        notable = packet.get("notable_movers") or {}
        named |= {str(r.get("symbol") or "").upper()
                  for r in (notable.get("rows") or [])}
        out["named_this_morning"] = sorted(s for s in named if s)
    else:
        out["packet_reason"] = (
            f"no packet at {packet_path.name} for {day}, so the movers list "
            "cannot exclude what the morning named and every name in it is "
            "reported as new when some may not be")

    if config.WATCHLIST_PATH.is_file():
        watchlist = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
        generated = str(watchlist.get("generated_at") or "")
        if generated.startswith(day):
            rows = watchlist.get("symbols") or []
            out["pooled"] = sorted(
                {str(s.get("symbol") or s.get("code") or "").upper()
                 for s in rows} - {""})
            out["subscribed"] = sorted(
                {str(s.get("symbol") or s.get("code") or "").upper()
                 for s in rows if s.get("subscribed")} - {""})
        else:
            out["watchlist_reason"] = (
                f"watchlist.json was generated {generated or 'at an unknown time'} "
                f"and this run is for {day}, so it is another session's file and "
                "every mover is reported as not_pooled whatever discover "
                "actually had")
    else:
        out["watchlist_reason"] = "watchlist.json is absent"
    return out


def live_picks(day: str) -> list[dict[str, Any]]:
    """Today's picks rows. Read only, and this module never writes that table."""
    with store.session() as conn:
        cursor = conn.execute(
            "SELECT ticker, score, conviction, day_eligible, swing_eligible, "
            "gap_pct, pm_high, pm_low, pm_vwap, entry_ref, stop_ref "
            "FROM picks WHERE date = ? ORDER BY ticker", (day,))
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def build_packet(day: str | None = None) -> dict[str, Any]:
    now = ettime.now_et()
    today = ettime.parse_date(day) if day else ettime.today_et()
    day = today.isoformat()

    universe = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    symbols = [str(s.get("symbol") or "").upper()
               for s in (universe.get("symbols") or [])]
    symbols = sorted({s for s in symbols if s})
    if not symbols:
        raise RuntimeError(
            f"{config.UNIVERSE_PATH.name} carries no symbols, so there is no "
            "population to sweep and a partial scan must not be published as a "
            "market wide one")

    need = eodhd.credit_cost(us_quote_delayed_per_symbol=len(symbols),
                             news=NEWS_LOOKUPS, eod=1, eod_bulk_last_day=1)
    preflight = eodhd.require_quota(
        "midday", need,
        f"the midday sweep over {len(symbols):,} universe names, one bulk day "
        f"for the denominator and {NEWS_LOOKUPS} news lookups")

    api = eodhd.client()
    expect_prior = prior_session(api, today)
    closes = prior_closes(api, expect_prior)

    quote_result = api.quote_delayed(symbols)
    raw = quote_result.data or {}
    quotes = {symbol: read_quote(row, now, expect_prior, closes.get(symbol))
              for symbol, row in raw.items()}

    context = morning_context(day)
    named = set(context["named_this_morning"])
    subscribed = set(context["subscribed"])
    pooled = set(context["pooled"])

    picks = live_picks(day)
    carry = [grade(pick, quotes.get(
        pick["ticker"].upper(),
        read_quote({}, now, expect_prior, closes.get(pick["ticker"].upper()))))
        for pick in picks]

    movers, tally = rank_movers(quotes, named, subscribed, pooled)
    movers = movers[:LIST_SIZE]
    news_calls = attach_news(api, movers, today)

    states = {state: sum(1 for row in carry if row["state"] == state)
              for state in (NEVER_TRIGGERED, GAPPED_THROUGH, TRIGGERED, UNKNOWN)}
    sequence_unknown = sum(1 for row in carry
                           if row["stop_state"] == STOP_SEQUENCE_UNKNOWN)

    return {
        "session_date": day,
        "generated_at": ettime.stamp(now),
        "run_time_et": ettime.hhmm(now),
        "configured_run_time": _CRIT.text("midday", "run_time"),
        "prior_session": expect_prior,
        "prior_closes_returned": len(closes),
        "build": config.build_identifier(),
        "quota_preflight": preflight,
        "price_source": {
            "endpoint": "us-quote-delayed",
            "fields": ["open", "high", "low", "lastTradePrice", "volume",
                       "averageVolume"],
            "denominator_endpoint": "eod-bulk-last-day",
            "denominator_note": (
                f"every move divides by the {expect_prior} close from "
                "eod-bulk-last-day, asked for by date. The quote's own "
                "previousClosePrice is NOT read: measured 2026-08-31 it "
                "matched the prior session for 34 percent of names and today's "
                "close for 29 percent, with nothing in the payload saying "
                "which, and it disagreed with the single symbol eod endpoint "
                "the rest of this project trusts"),
            "open_is_not_the_auction": (
                "us-quote-delayed's open is the first consolidated print. "
                "Measured 2026-08-31 it matched the session's official open "
                "for 70 percent of 2,750 names and differed by a median 0.34 "
                "percent for the rest, worst among the least liquid. Rows whose "
                "verdict turned on less than that carry "
                "decided_inside_the_open_tolerance"),
            "why_not_intraday": (
                "EODHD does not publish today's intraday bars until overnight. "
                "Measured 2026-08-31: today's completed session returned zero "
                "1m rows two hours after the close while the three sessions "
                "before it returned full days. See DECISIONS 2026-08-31"),
            "extended_hours_fields_read": False,
            "extended_hours_reason": (
                "ethPrice and ethTime were stale at 08:45 on the morning they "
                "were needed, 2026-08-17, and this pass has no use for them"),
        },
        "universe_size": len(symbols),
        "quotes_returned": len(raw),
        "quotes_missing": len(symbols) - len(raw),
        "quote_error": config.scrub_secrets(quote_result.error) if quote_result.error else None,
        "carry_through": {
            "rows": carry,
            "picks_found": len(picks),
            "states": states,
            "sequence_unknown_rows": sequence_unknown,
            "decided_inside_the_open_tolerance_rows": sum(
                1 for row in carry if row["decided_inside_the_open_tolerance"]),
            "sequence_unknown_note": (
                f"{sequence_unknown} of {len(carry)} graded rows reached their "
                "stop level after an intraday fill, where a daily high and low "
                "carry no order, so this pass cannot say whether the stop came "
                "before or after the entry. Extending CRITERIA [Collector] "
                "stop_time past the open is what would answer it"),
            "not_checked": (
                "CRITERIA [Paper]'s SKIP condition, fill_plausible, is computed "
                "by the night from Alpaca band volume and does not exist at "
                "midday. These grades do not ask whether the level was "
                "transactable"),
            "picks_reason": None if picks else (
                f"the picks table carries no live rows for {day}, so there is "
                "nothing to grade. That is a morning that published no "
                "candidates, not a failure of this pass"),
        },
        "movers": {
            "rows": movers,
            "list_size": LIST_SIZE,
            "rank_by": RANK_BY,
            "tally": tally,
            "news_calls": news_calls,
            "selection_note": (
                "selection is on PRICE across every universe name, and news is "
                "fetched afterwards for the top of the ranked list. A name that "
                "moved on no tagged headline is still HERE, carrying a reason "
                "that says the feed was silent. A news led scan could not have "
                "said that"),
            "floors": {
                "min_move_pct": _CRIT.rule("midday", "min_move_pct").describe(),
                "min_day_rvol": _CRIT.rule("midday", "min_day_rvol").describe(),
                "min_price": _CRIT.rule("midday", "min_price").describe(),
            },
        },
        "morning_context": context,
        "api_calls": eodhd.call_count(),
    }


def write_packet(payload: dict[str, Any], overwrite: bool) -> tuple[Any, bool]:
    path = config.run_dir(payload["session_date"]) / PACKET_FILE
    destination, spared = artifacts.resolve(
        path, overwrite or artifacts.scheduled_run(), what="midday")
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return destination, spared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The 12:00 pass: carry through and today's movers.")
    parser.add_argument("--date", default=None,
                        help="Session to run for. Defaults to today ET.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace an existing midday packet rather than "
                             "writing beside it.")
    args = parser.parse_args(argv)

    try:
        payload = build_packet(args.date)
    except (eodhd.QuotaRefusal, PriorSessionUnknown, PriorClosesUnusable) as exc:
        print(f"REFUSING TO RUN: {exc}")
        eodhd.print_call_report()
        return 1

    destination, _spared = write_packet(payload, args.overwrite)
    carry = payload["carry_through"]
    movers = payload["movers"]
    job_status.produced("movers", len(movers["rows"]))

    print("")
    print(f"midday: wrote {destination}")
    print(f"midday: {payload['quotes_returned']:,} of {payload['universe_size']:,} "
          f"universe names quoted, and {payload['prior_closes_returned']:,} "
          f"closes for the {payload['prior_session']} denominator")
    print(f"midday: {carry['picks_found']} picks graded  " + "  ".join(
        f"{name}={count}" for name, count in carry["states"].items()))
    for row in carry["rows"]:
        now_vs = (f"{row['now_vs_fill_pct']:+.2f}%"
                  if row["now_vs_fill_pct"] is not None else "     ?")
        best = (f"{row['best_vs_fill_pct']:+.2f}%"
                if row["best_vs_fill_pct"] is not None else "     ?")
        print(f"    {row['ticker']:<10} {row['state']:<16} "
              f"now {now_vs:>8} best {best:>8}  stop {row['stop_state']}")
    print(f"midday: {len(movers['rows'])} movers of {movers['tally']['admitted']} "
          f"admitted, ranked by {movers['rank_by']}")
    for row in movers["rows"]:
        headline = ""
        if row["news"]:
            headline = row["news"][0]["title"][:60]
        elif row["news_reason"]:
            headline = "(no story tagged today)" if "tagged no story" in row["news_reason"] else ""
        print(f"    {row['symbol']:<10} {row['move_pct']:+7.2f}%  "
              f"rvol {row['day_rvol']:>6.2f}  "
              f"{row['morning_reach']:<22} {headline}")
    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(job_status.run("midday", main))
