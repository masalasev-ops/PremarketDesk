"""What makes two names lookalikes: the match bands, and "reported overnight".

ONE DEFINITION IN ONE PLACE, and this module exists because there were two.

The Precedent screen matches a candidate against past candidates on six
conditions. Five of them are bands cut from numbers. The sixth is a boolean,
whether the name reported overnight, and it is the one condition the widening
ladder may NEVER drop, so getting it wrong corrupts the entire group rather
than loosening it.

It was wrong. The engine wrote the column from
`selection/discover.earnings_reporters`, which keeps a BeforeMarket row dated
TODAY or an AfterMarket row dated the PRIOR SESSION and drops the other two
kinds. The screen recomputed it at read time from mere membership in the
packet's earnings list, which is a wider window. Measured on the packet that
was already on disk: NIO.US on 2026-09-02 carries report_date 2026-09-01
BeforeMarket, a name that reported before the PREVIOUS morning's open and
gapped on that tape. The screen stamped it "reported overnight" and matched it
against past rows that genuinely reported between the prior close and this
open. Two definitions compared as one column, and neither side could see it.

So the predicate moved here, both callers import it, and a claim pins that
`discover` and the desk agree. The bands moved here for a second reason, given
below.

WHY THE BANDS ARE HERE AND NOT IN research/. `desk/precedent.py` needs the band
cutter, and importing it from `research/replay_outcomes` pulled
`research/replay_session` and `research/backtest_pool` behind it, and those
reach `probe_alpaca` and `core/eodhd`. Measured: `import desk.compact` loaded
408 modules with that edge and 181 without it. `desk/render` imports
`desk/compact`, and the 08:45 morning chain runs `desk.render` as its last
step, so the pre-open window was loading the vendor HTTP client, the socket
client and the Alpaca transport for the first time, and every compact and
render run printed an "EODHD call report, total http calls 0" into the log of a
step whose own comment says it makes no vendor call. `night/paper_ledger` keeps
exactly these imports inside `book()` for exactly this reason. A core module
both sides read is the fix that cannot come back.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from core import criteria

_CRIT = criteria.load()

# The three shapes of an overnight report, in the order a name that carries two
# rows should be read. Same strings discover.py has always written as tier_key,
# because they travel into [Pool tiers] and a rename here would be a rename
# there.
BEFORE_OPEN = "earnings_before_open"
AFTER_CLOSE = "earnings_after_close"
TIMING_UNKNOWN = "earnings_timing_unknown"


def overnight_tier(timing: Any, report_date: Any, session_date: Any,
                   prior_session: Any = None) -> str | None:
    """Which kind of overnight report this row is, or None for none of them.

    The rule, which is discover.earnings_reporters' rule and is now only
    written down once:

      BeforeMarket dated the session itself   reported before this open
      AfterMarket dated the prior session     reported after the last close
      no timing at all, dated inside the two  the same prior with less
        session window                        precision, not a weaker one
      anything else                           not overnight

    A BeforeMarket row dated the prior session already gapped yesterday and an
    AfterMarket row dated the session gaps tomorrow. Both are real earnings and
    neither is THIS morning's catalyst, which is the distinction the whole
    predicate exists to make.

    prior_session is optional because the desk does not carry one. When it is
    absent an AfterMarket row dated strictly BEFORE the session counts, which
    is the same set: the calendar call that produced these rows starts at the
    prior session, so there is nothing earlier in the window to catch by
    mistake. Passing it explicitly is still preferred and discover does.

    Returns None rather than False so a caller can tell "not an overnight
    report" from "no answer", which is the distinction the row above got wrong.
    """
    session = _as_date(session_date)
    if session is None:
        return None
    reported = _as_date(report_date)
    if reported is None:
        return None
    prior = _as_date(prior_session)
    word = str(timing or "").strip().lower()
    # TWO DIALECTS REACH THIS ARGUMENT AND BOTH MEAN "the vendor sent no
    # timing". discover.earnings_reporters computes its tier from the RAW
    # before_after_market field, where absent is an empty string, and then
    # STORES the row as timing "unknown" for a reader. desk/compact passes the
    # raw field and every cached session under data/backtest passes the stored
    # one. Testing only for the empty string made this function disagree with
    # discover on the timing_unknown tier for every cached row: measured
    # 2026-09-05 across 203 sessions, 2,545 of 9,366 rows, all of them a stored
    # "unknown" that this read as a known timing of some other kind and so
    # answered "not overnight" for.
    if word == "unknown":
        word = ""

    if word == "beforemarket" and reported == session:
        return BEFORE_OPEN
    if word == "aftermarket":
        # THE WINDOW, not the prior session's date exactly. A company that
        # reports after the close on a market holiday sitting between the prior
        # session and this one has still reported after the last close and
        # before this open, and testing equality dropped it. Measured
        # 2026-09-05 over 207 cached sessions this was the entire remaining
        # disagreement with discover: NAT on 2025-11-28, which reported on
        # Thanksgiving Day, and four names on 2026-02-17 that reported over the
        # Presidents' Day weekend. A row dated the session itself is still
        # excluded, because that one gaps tomorrow.
        if prior is not None and prior <= reported < session:
            return AFTER_CLOSE
        if prior is None and reported < session:
            return AFTER_CLOSE
        return None
    if not word:
        in_window = (prior <= reported <= session if prior is not None
                     else reported <= session)
        if in_window:
            return TIMING_UNKNOWN
    return None


def reported_overnight(timing: Any, report_date: Any, session_date: Any,
                       prior_session: Any = None) -> bool:
    """The boolean the Precedent match uses. See overnight_tier for the rule."""
    return overnight_tier(timing, report_date, session_date, prior_session) is not None


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


# ---------------------------------------------------------------- bands ----

def edges(key: str) -> list[float]:
    """One CRITERIA edge list, ascending, as floats.

    Raises rather than sorting a mis-entered list. An edge list that is not
    ascending would put a value in two bands or none, and quietly repairing it
    here would hide the typo from the person who made it.
    """
    values = [float(x) for x in _CRIT.text_list("precedent", key)]
    if values != sorted(values):
        raise ValueError(f"CRITERIA [Precedent] {key} is not ascending: {values}")
    return values


def band(value: float | None, band_edges: list[float], unit: str = "") -> str | None:
    """Which band a value falls in, as the text that is stored and printed.

    None in, None out. A value that was never measured has no band, and giving
    it one would put unmeasured names into a group that claims to describe
    measured ones.

    The value ON an edge belongs to the band ABOVE it, which is the convention
    CRITERIA states and the same one every screen condition in this project
    already uses.
    """
    if value is None:
        return None

    def show(number: float) -> str:
        text = f"{number:.4f}".rstrip("0").rstrip(".")
        return f"{text}{unit}"

    if value < band_edges[0]:
        return f"under {show(band_edges[0])}"
    for low, high in zip(band_edges, band_edges[1:]):
        if low <= value < high:
            return f"{show(low)} to {show(high)}"
    return f"{show(band_edges[-1])} and up"


def gap_band(gap_pct: float | None) -> str | None:
    """The gap band, which carries DIRECTION as well as size.

    A signed gap banded on the raw number puts a name down 6.2 percent in the
    same group as one up 3 percent, because both are "under 4%". Those are not
    lookalikes under this desk's entry rule, which is long only: the trigger is
    a stop order above the premarket high, so a gap down name reaching it is a
    reversal and a gap up name reaching it is a continuation. Pooling them
    would answer neither question.

    It matters here more than it would elsewhere. On 2026-09-01 the top twelve
    by ABSOLUTE gap came back twelve gap down names, so a whole morning of this
    desk's list can sit on one side, and CRITERIA [Score gap]'s own note plus
    IMPROVEMENT_PLAN 5.6's second owner decision both record that sign aware
    selection is still open. Whatever is decided there, a base rate that had
    already pooled the two directions could not be read afterwards.

    The edges stay one list of MAGNITUDES. Direction is a word in front, so a
    reader sees "up 6% to 8%" and the two directions can never collide.
    """
    if gap_pct is None:
        return None
    size = band(abs(gap_pct), edges("gap_band_edges"), "%")
    # Zero is UP by convention and the convention is arbitrary, so it is
    # written down rather than left to a sign test somebody reads twice. A gap
    # of exactly zero is a name that did not gap, it is one row in a thousand,
    # and it does not deserve a third direction of its own.
    return f"{'down' if gap_pct < 0 else 'up'} {size}"


def bands_for(gap_pct: float | None, pm_rvol: float | None,
              price: float | None, cap_musd: float | None) -> dict[str, str | None]:
    """The four banded conditions, cut identically at write time and read time.

    Both sides call THIS, which is the only reason a group is ever non empty:
    the engine freezes these strings onto the row and the screen recomputes
    them, and if the two ever produced different text for the same number every
    group would be empty forever with nothing raising anywhere.
    """
    return {
        "gap_band": gap_band(gap_pct),
        "rvol_band": band(pm_rvol, edges("rvol_band_edges"), "x"),
        "price_band": band(price, edges("price_band_edges")),
        "cap_band": band(cap_musd, edges("cap_band_edges"), "M"),
    }
