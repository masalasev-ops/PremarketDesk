"""Weekly discovery universe.

Run this on Sunday evening. It answers one question: which US common stocks
are liquid enough to be worth looking at when they gap on Monday morning.

The market cap floor here is deliberately below the day setup floor in
CRITERIA.md. A 900M name that gaps 20 percent is a 1.1B name by the time the
gap is on the screen, so it has to already be in the population the night
before or the morning pass can never see it. Screening the population at the
trading threshold is how you build a universe that structurally cannot contain
the trades you are looking for.

Cost, in http calls and in what the shared counter actually charges for them.
The two columns are different and the difference is the whole reason this file
carries a quota gate. Prices are in CRITERIA.md [quota costs], measured.

    calls  credits  what
        2        2  exchange symbol lists, NYSE and NASDAQ
        1        1  SPY end of day history, which supplies the session dates
       20    2,000  bulk end of day, one per session, a flat 100 each
      148    2,942  delayed quotes in batches of twenty, billed PER SYMBOL, only
                    for names that already cleared price, liquidity and history,
                    purely to attach market cap
        1        0  the account meter read, free at [quota costs] user : 0
      ---    -----
      172    4,945  measured on the 2026-08-17 rebuild

So the largest job in this project reports 172 http calls and takes five
percent of a shared daily hundred thousand. Sizing anything off the call count
gets it wrong by a factor of twenty eight.

Everything later in the day refuses to run against a stale universe. That gate
lives here in require_fresh_universe so there is one definition of stale.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, NamedTuple

from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status

_CRIT = criteria.load()


class StaleUniverseError(RuntimeError):
    """Raised when universe.json is missing or too old to trade against."""


class PartialBuildError(RuntimeError):
    """Raised when a completed build is not whole enough to replace the old one.

    The quota gates stop a run that cannot AFFORD the sweep. This is the other
    case: a run that could afford it, started it, and then lost batches part
    way through. The gates cannot see that, because they read the meter once
    before the sweep begins.

    It matters because os.replace is destructive. Without this the truncated
    file lands on top of last Sunday's good one, main returns 0 on a count
    that is still inside its expected range, the job records ok, and the
    monitor sees a fresh generated_at and reports the universe healthy while
    discover refuses on it every morning until the next Sunday. The monitor's
    relaunch is keyed to the file being OLD, so a fresh bad file never triggers
    it. Refusing to write is what keeps the recovery path that the quota
    refusal already has.
    """


def _norm_code(raw: str) -> str:
    """Bare ticker, no exchange suffix. The two bulk feeds disagree on this."""
    code = str(raw or "").strip().upper()
    return code.split(".", 1)[0] if code.endswith(".US") else code


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


# ---------------------------------------------------------------- freshness

def universe_age_days(payload: dict[str, Any]) -> float:
    generated = payload.get("generated_at")
    if not generated:
        return float("inf")
    try:
        when = dt.datetime.fromisoformat(generated)
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=ettime.ET)
    return (ettime.now_et() - when).total_seconds() / 86400.0


def load_universe(require_fresh: bool = True) -> dict[str, Any]:
    """Read universe.json, refusing a stale one and saying exactly why."""
    path = config.UNIVERSE_PATH
    max_age = _CRIT.integer("universe", "max_age_days")

    if not path.exists():
        raise StaleUniverseError(
            f"{path} does not exist. Run universe.py before anything else. "
            "Nothing downstream has a population to screen without it."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise StaleUniverseError(f"{path} could not be read: {exc}") from exc

    age = universe_age_days(payload)
    if require_fresh and age > max_age:
        stamp = payload.get("generated_at", "unknown")
        raise StaleUniverseError(
            f"{path.name} was generated at {stamp}, which is {age:.1f} days ago. "
            f"The limit in {config.CRITERIA_PATH.name} is max_age_days = {max_age}. "
            "Delistings, splits and new listings have moved since then. "
            "Re-run universe.py before trading off it."
        )
    return payload


def require_fresh_universe() -> dict[str, Any]:
    """For every later script. Refuses to run and says why, rather than guessing."""
    payload = load_universe(require_fresh=True)
    age = universe_age_days(payload)
    print(
        f"universe: {payload.get('count', 0)} names, generated {payload.get('generated_at')} "
        f"({age:.1f} days ago)"
    )
    # A file written past the admissibility gate says so on every step that
    # reads it, not only in the Sunday log nobody opens again. check_admissible
    # honours the override the human recorded, which is what lets the morning
    # run at all, and a step that then used the file without ever mentioning
    # the override would leave it looking exactly like a build that passed.
    override = payload.get("admissibility_override")
    if isinstance(override, dict) and override.get("verdict"):
        print(f"WARNING  universe: this file was written past the admissibility "
              f"gate by a human. The gate said: {override['verdict']}")
    return payload


def universe_symbols(payload: dict[str, Any]) -> list[str]:
    return [row["symbol"] for row in payload.get("symbols", []) if row.get("symbol")]


# ------------------------------------------------------------------- build

def _common_stock_index(
        api: eodhd.EodhdClient,
        notes: list[str]) -> dict[str, dict[str, str | None]]:
    """Bare ticker to what the vendor listed it AS, common stock only.

    Everything that is not Type == Common Stock is dropped here, which is what
    removes ETFs, funds, preferreds, warrants, units, rights and notes in one
    move rather than by maintaining a suffix blacklist.

    This kept the exchange and threw the rest of the row away until 2026-08-20,
    and the Name is the field that mattered. Layer 4's second list ranks by
    market cap, so the largest caps in the file are read by a human every
    morning, and a bare ticker cannot tell that reader whether a very large one
    is a real company or a vendor error. SPCX at 1.85 trillion and SKHY at 1.18
    were written up in DECISIONS.md as implausible on exactly that reasoning,
    and settling it took a vendor call that returned "Space Exploration
    Technologies Corp. Class A Common Stock" and "SK Hynix Inc. American
    Depositary Shares". Both caps were right and the finding was wrong. The
    name was in the response that built the file, in the same row as the Type
    this function already reads, and was discarded.

    Isin comes along for nothing and is the identifier a human can look up,
    which a ticker is not: tickers are reused and an ADR does not share one
    with its ordinary shares.
    """
    wanted_type = _CRIT.text("universe", "allowed_security_type")
    exchanges = _CRIT.text_list("universe", "exchanges")

    index: dict[str, str] = {}
    answered: list[str] = []
    for exchange in exchanges:
        rows, error = api.exchange_symbol_list(exchange)
        if error:
            notes.append(f"exchange symbol list for {exchange} failed: {error}")
            continue
        answered.append(exchange)
        kept = 0
        for row in rows:
            if str(row.get("Type", "")).strip().lower() != wanted_type.lower():
                continue
            code = _norm_code(row.get("Code", ""))
            if not code:
                continue
            def _text(field: str) -> str | None:
                value = str(row.get(field) or "").strip()
                return value or None

            index.setdefault(code, {
                "exchange": row.get("Exchange") or exchange,
                "name": _text("Name"),
                "isin": _text("Isin"),
            })
            kept += 1
        print(f"universe: {exchange} listed {len(rows)}, kept {kept} as {wanted_type}")

    # An exchange that did not answer is a MISSING HALF OF THE MARKET, not a
    # note. Raised here, three credits into the run, rather than left to the
    # admissibility gate, because that gate cannot see this: the bulk sweep,
    # the market cap sweep and the funnel are all computed from whatever this
    # returns, so they come out internally consistent, market_cap_funnel reports
    # zero unswept, and the count lands inside expected_count_range. Only the
    # count fraction floor stands between a half universe and the disk, and it
    # is 0.5: the 2026-08-17 file splits about 1,519 NYSE to 1,235 NASDAQ, so
    # losing NASDAQ leaves 0.552 of the previous count and clears the floor by
    # two points, while losing NYSE leaves 0.448 and is correctly refused.
    # Which half of the market the vendor drops decided whether the gate spoke.
    #
    # The consequence was a week long one. max_age_days is 10, so the monitor's
    # age-keyed relaunch never fires on a fresh bad file, and every 07:15 pass
    # until the next Sunday builds its pool from a universe with an entire
    # exchange missing. PartialBuildError is exactly the right shape for this
    # and its own docstring already argues the case.
    missing = [name for name in exchanges if name not in answered]
    if missing:
        raise PartialBuildError(
            f"the exchange symbol list failed for {', '.join(missing)} of "
            f"{', '.join(exchanges)}, so this build would cover only "
            f"{', '.join(answered) or 'no exchange at all'} and admit a "
            "universe with a whole exchange missing. Nothing downstream can "
            "tell that from a real one: the sweeps and the funnel are computed "
            "from this index, so they agree with each other, and the count "
            "fraction floor only catches it when the LARGER exchange is the one "
            "that failed. Last week's universe.json is left in place, which the "
            "10 day max_age_days makes usable until the next Sunday. Rerun "
            "tasks\\job_universe.bat when the vendor answers."
        )
    return index


def _session_dates(api: eodhd.EodhdClient, count: int, notes: list[str]) -> list[dt.date]:
    """Real trading session dates, taken from data rather than from a guess.

    Holidays are not enumerated anywhere in this project. A liquid reference
    symbol's own end of day history is the session calendar.
    """
    probe = _CRIT.text("universe", "session_calendar_symbol")
    today = ettime.today_et()
    # Enough calendar days to be sure of covering the requested sessions.
    start = today - dt.timedelta(days=count * 2 + 20)

    rows, error = api.eod(probe, start=start, end=today)
    if error or not rows:
        raise RuntimeError(
            f"could not read the session calendar from {probe}: {error or 'no rows'}"
        )

    dates = sorted({ettime.parse_date(str(r.get("date"))) for r in rows if r.get("date")})
    # Today's own session is excluded. It is either unfinished or not there.
    dates = [d for d in dates if d < today]
    if len(dates) < count:
        notes.append(
            f"session calendar only returned {len(dates)} sessions before {today}, wanted {count}"
        )
    return dates[-count:]


def _collect_bars(
    api: eodhd.EodhdClient,
    session_dates: list[dt.date],
    wanted: set[str],
    notes: list[str],
) -> dict[str, list[tuple[float, float]]]:
    """Per symbol list of (close, volume), oldest session first."""
    series: dict[str, list[tuple[float, float]]] = {}
    for day in session_dates:
        rows, error = api.eod_bulk_last_day("US", day=day)
        if error:
            notes.append(f"bulk end of day for {day} failed: {error}")
            continue
        matched = 0
        for row in rows:
            code = _norm_code(row.get("code") or row.get("Code") or "")
            if code not in wanted:
                continue
            close = _as_float(row.get("close") if "close" in row else row.get("Close"))
            volume = _as_float(row.get("volume") if "volume" in row else row.get("Volume"))
            if close is None or volume is None:
                continue
            series.setdefault(code, []).append((close, volume))
            matched += 1
        print(f"universe: {day} bulk returned {len(rows)} rows, {matched} in scope")
    return series


class CapSweep(NamedTuple):
    """What the market cap sweep learned, and what it failed to learn.

    caps        code -> market cap, for every name the vendor priced.
    answered    codes that appeared in some response, priced or not.
    unanswered  codes whose whole batch came back with nothing at all.

    A code in none of the three is one whose batch was answered while it was
    itself absent from the body. Those three outcomes are different facts and
    the payload records them separately, because until it did, all of them
    arrived at the same sentence: "dropped because no market cap came back".
    """

    caps: dict[str, float]
    answered: set[str]
    unanswered: set[str]


def _attach_market_caps(
    api: eodhd.EodhdClient,
    codes: list[str],
    notes: list[str],
) -> CapSweep:
    """Market cap from us-quote-delayed, the same field the morning scan reads.

    The old guard here was `if error and not data`, which had a hole big
    enough to lose twenty names at a time without a word anywhere. When a
    chunk comes back 200 with a body eodhd.quote_delayed does not recognise,
    it returns ({}, None): no error to record, and no rows to record against.
    The guard was False, the loop over an empty dict did nothing, and the
    twenty names fell through to the same counter as a genuine vendor gap.

    So the test is now on the data rather than on the error. A batch that
    answered nothing is recorded as unanswered whether or not it said why, and
    the names in it are never described as names the vendor had no cap for.
    """
    caps: dict[str, float] = {}
    answered: set[str] = set()
    unanswered: set[str] = set()
    batch = _CRIT.integer("api", "quote_batch_size")
    total = len(codes)
    for start in range(0, total, batch):
        window = codes[start:start + batch]
        data, error = api.quote_delayed([f"{c}.US" for c in window])
        if not data:
            unanswered.update(window)
            notes.append(
                f"market cap batch {start // batch}, covering {len(window)} names, "
                f"was not answered: {error or 'the response carried no rows'}"
            )
            continue
        for symbol, quote in data.items():
            code = _norm_code(symbol)
            answered.add(code)
            cap = _as_float(quote.get("marketCap"))
            if cap is not None:
                caps[code] = cap
        done = min(start + batch, total)
        if done % (batch * 25) == 0 or done == total:
            print(f"universe: market cap {done}/{total}")
    return CapSweep(caps=caps, answered=answered, unanswered=unanswered)


_FUNNEL_DOORS = (
    "admitted",
    "below_market_cap_floor",
    "no_market_cap_in_row",
    "absent_from_answered_batch",
    "in_an_unanswered_batch",
)


def market_cap_funnel(
    staged: list[dict[str, Any]],
    sweep: CapSweep,
    market_cap_rule: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sort every examined name through exactly one door, and name the doors.

    This used to be four lines inside build() that counted one door and
    ignored the rest. On the 2026-08-17 rebuild it reported "46 names were
    dropped because no market cap came back" out of 2,942 examined and 2,754
    admitted, which left 142 names failing the market cap floor with nothing
    anywhere recording that they had even been considered. Naming the 46 while
    the 142 stayed invisible would have made that record worse, not better,
    because a reader would reasonably take the named list as the explanation
    for the whole 2,942 to 2,754 drop. It explains a quarter of it.

    The doors are not the same KIND of fact, which is the point of separating
    them. below_market_cap_floor is a decision this project made on evidence it
    has. The other three are absences, and they differ in what is absent: the
    vendor answered and carried no market cap, the vendor answered a batch
    without mentioning the name, or nothing ever came back for the batch at
    all. Only the first of those is a fact about the market.

    Lifted out of build() so a claim can drive it without a network, which is
    the only way to exercise the batch that answers nothing.
    """
    admitted: list[dict[str, Any]] = []
    doors: dict[str, list[str]] = {
        "below_market_cap_floor": [],
        "no_market_cap_in_row": [],
        "absent_from_answered_batch": [],
        "in_an_unanswered_batch": [],
    }
    for row in staged:
        code = row["code"]
        cap = sweep.caps.get(code)
        if cap is None:
            if code in sweep.unanswered:
                doors["in_an_unanswered_batch"].append(code)
            elif code in sweep.answered:
                doors["no_market_cap_in_row"].append(code)
            else:
                doors["absent_from_answered_batch"].append(code)
            continue
        if not market_cap_rule.test(cap):
            doors["below_market_cap_floor"].append(code)
            continue
        row["market_cap"] = round(cap, 2)
        admitted.append(row)

    funnel: dict[str, Any] = {"examined": len(staged), "admitted": len(admitted)}
    funnel.update({door: len(names) for door, names in doors.items()})
    funnel["names"] = {door: sorted(names) for door, names in doors.items()}
    # The funnel has to close. If it ever does not, that is a defect in this
    # accounting rather than in the data, and it should say so rather than
    # quietly under report.
    funnel["unaccounted"] = funnel["examined"] - sum(funnel[d] for d in _FUNNEL_DOORS)
    return admitted, funnel


def funnel_notes(funnel: dict[str, Any], market_cap_rule: Any) -> list[str]:
    """The funnel as lines for the job log, naming names for the absences."""
    notes = []
    if funnel.get("unaccounted"):
        notes.append(
            f"the market cap funnel does not close: {funnel['unaccounted']} of "
            f"{funnel['examined']} names left by no recorded door, which is a "
            "defect in this accounting rather than in the data")
    notes.append(
        f"market cap funnel: {funnel['examined']:,} examined, "
        f"{funnel['admitted']:,} admitted, "
        f"{funnel['below_market_cap_floor']:,} below the "
        f"{market_cap_rule.describe()} floor, "
        f"{funnel['no_market_cap_in_row']:,} answered with no market cap in the row, "
        f"{funnel['absent_from_answered_batch']:,} absent from a batch that answered, "
        f"{funnel['in_an_unanswered_batch']:,} in a batch that answered nothing")
    # The floor names are in the payload but not named here: that door is a
    # decision made on evidence, and 142 tickers on one line would bury the
    # three doors that are evidence gaps.
    for door, label in (
        ("no_market_cap_in_row", "answered with no market cap in the row"),
        ("absent_from_answered_batch", "absent from a batch that answered"),
        ("in_an_unanswered_batch", "in a batch that answered nothing"),
    ):
        names = funnel["names"].get(door) or []
        if names:
            notes.append(f"{len(names)} {label}: {', '.join(names)}")
    return notes


def _prior_staged_count() -> int | None:
    """How many names the previous build put through the market cap sweep.

    The sweep is the per name half of the bill and its size is not knowable
    until the bulk sweep has already been paid for, so the only honest input
    to a gate that runs BEFORE the bulk sweep is what last week actually
    swept. Falls back to the previous admitted count, which is a true lower
    bound because admitted is a subset of staged, and then to None.

    None means unknown, and unknown is not zero: the caller gates on the bulk
    sweep alone and says so, rather than inventing a number for the half it
    cannot see.
    """
    try:
        existing = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for key in ("cleared_price_and_liquidity", "count"):
        value = existing.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def build(write: bool = True, force: bool = False) -> dict[str, Any]:
    """Rebuild the universe. force overrides one verdict of the pre-write gate.

    force is not a way of turning the gate off, and nothing scheduled passes
    it. It is the human answer to the one question the gate cannot answer for
    itself, which the gate block below states in full: whether a shrink is a
    build that lost batches or a floor the owner deliberately tightened. It
    reaches that verdict and no other. A run whose market cap sweep lost
    batches says so in its own funnel, and it is refused whether or not --force
    was passed, because a rerun clears that one without anyone having to decide
    anything.
    """
    config.ensure_dirs()
    api = eodhd.client()
    notes: list[str] = []

    price_rule = _CRIT.rule("universe", "price")
    dollar_volume_rule = _CRIT.rule("universe", "avg_dollar_volume_20d")
    market_cap_rule = _CRIT.rule("universe", "market_cap")
    min_sessions = _CRIT.integer("universe", "min_sessions")
    lookback = _CRIT.integer("universe", "lookback_sessions")
    count_min = _CRIT.integer("universe", "expected_count_min")
    count_max = _CRIT.integer("universe", "expected_count_max")

    print("universe: building")
    print(f"universe: admit when price {price_rule.describe()}, "
          f"20 day average dollar volume {dollar_volume_rule.describe()}, "
          f"market cap {market_cap_rule.describe()}, sessions >= {min_sessions}")

    listed_as = _common_stock_index(api, notes)
    print(f"universe: {len(listed_as)} common stocks across the listed exchanges")
    named = sum(1 for row in listed_as.values() if row.get("name"))
    print(f"universe: {named} of {len(listed_as)} carry a vendor instrument name")

    session_dates = _session_dates(api, lookback, notes)
    print(f"universe: {len(session_dates)} sessions, "
          f"{session_dates[0] if session_dates else 'n/a'} to "
          f"{session_dates[-1] if session_dates else 'n/a'}")

    # The first of two quota gates. Exactly three credits are spent at this
    # point and len(session_dates) is now exact, so the two thousand credit
    # bulk sweep about to start is priced rather than guessed. Refusing here
    # costs three credits. Refusing one line later would cost two thousand.
    prior_staged = _prior_staged_count()
    bulk_credits = eodhd.credit_cost(eod_bulk_last_day=len(session_dates))
    if prior_staged is None:
        need = bulk_credits
        what = (f"the {len(session_dates)} session bulk sweep alone (no previous "
                "build is on disk, so the market cap sweep after it cannot be "
                "sized yet)")
    else:
        need = bulk_credits + eodhd.credit_cost(us_quote_delayed_per_symbol=prior_staged)
        what = (f"the {len(session_dates)} session bulk sweep and a market cap sweep "
                f"of about {prior_staged:,} names (sized from the previous build)")
    eodhd.require_quota("universe", need, what)

    series = _collect_bars(api, session_dates, set(listed_as), notes)
    print(f"universe: {len(series)} symbols had at least one session")

    # Stage one, everything that costs no extra calls.
    staged: list[dict[str, Any]] = []
    for code, bars in series.items():
        sessions = len(bars)
        if sessions < min_sessions:
            continue
        price = bars[-1][0]
        if not price_rule.test(price):
            continue
        dollar_volume = sum(close * volume for close, volume in bars) / sessions
        if not dollar_volume_rule.test(dollar_volume):
            continue
        staged.append(
            {
                "code": code,
                "symbol": f"{code}.US",
                "exchange": (listed_as.get(code) or {}).get("exchange") or "UNKNOWN",
                # Null rather than a placeholder, because "the vendor sent no
                # name for this listing" and "the name is UNKNOWN" are different
                # facts and only one of them is about the instrument.
                "name": (listed_as.get(code) or {}).get("name"),
                "isin": (listed_as.get(code) or {}).get("isin"),
                "price": round(price, 4),
                "avg_dollar_volume_20d": round(dollar_volume, 2),
                "sessions": sessions,
            }
        )
    staged.sort(key=lambda row: row["avg_dollar_volume_20d"], reverse=True)
    print(f"universe: {len(staged)} cleared price, liquidity and history")

    # Stage two, the only part that spends calls per name, and the second
    # quota gate. This is the gate that has to exist: len(staged) is final
    # here, so the sweep is priced exactly with nothing estimated, and the
    # meter read costs nothing because user is zero in CRITERIA.md
    # [quota costs].
    #
    # It matters more than the first gate because of the sort above. staged is
    # ordered by dollar volume descending, so a sweep that runs out of quota
    # partway through does not thin the file evenly. It amputates the illiquid
    # tail, and the file it leaves still clears the count range and the
    # previous count fraction until roughly half the names are gone. Better to
    # spend nothing and keep last week's universe than to write a plausible
    # one that is quietly missing its tail.
    eodhd.require_quota(
        "universe",
        eodhd.credit_cost(us_quote_delayed_per_symbol=len(staged)),
        f"the market cap sweep of {len(staged):,} names")

    sweep = _attach_market_caps(api, [row["code"] for row in staged], notes)
    admitted, funnel = market_cap_funnel(staged, sweep, market_cap_rule)
    notes.extend(funnel_notes(funnel, market_cap_rule))

    admitted.sort(key=lambda row: row["symbol"])

    payload: dict[str, Any] = {
        "generated_at": ettime.stamp(),
        "count": len(admitted),
        "admitted_when": {
            "price": price_rule.describe(),
            "avg_dollar_volume_20d": dollar_volume_rule.describe(),
            "market_cap": market_cap_rule.describe(),
            "min_sessions": min_sessions,
            "security_type": _CRIT.text("universe", "allowed_security_type"),
            "exchanges": _CRIT.text_list("universe", "exchanges"),
        },
        "sessions": {
            "lookback": lookback,
            "used": len(session_dates),
            "first": session_dates[0].isoformat() if session_dates else None,
            "last": session_dates[-1].isoformat() if session_dates else None,
        },
        "expected_count_range": [count_min, count_max],
        # What the file this one replaces held. Carried so discover can tell a
        # market that moved from a rebuild that was cut short, which the count
        # alone cannot distinguish.
        "previous_count": _previous_count(),
        "listed_common_stocks": len(listed_as),
        "cleared_price_and_liquidity": len(staged),
        # Why each examined name is or is not in this file, by name and not
        # only by count. check_admissible reads it to answer "is this whole",
        # which the count alone cannot: a sweep starved of quota and a vendor
        # with no market cap for a name produce the same shortfall.
        "market_cap_funnel": funnel,
        "notes": notes,
        "api_calls": eodhd.call_count(),
        "symbols": admitted,
    }

    if len(admitted) < count_min or len(admitted) > count_max:
        warning = (
            f"universe count {len(admitted)} is outside the expected range "
            f"{count_min} to {count_max}. A small result usually means the bulk feed "
            "was short, a large one usually means the security type filter let "
            "something through. Check the notes before trading off this file."
        )
        payload["count_warning"] = warning
        print(f"WARNING  {warning}")

    if write:
        # Ask the "is it whole" question BEFORE replacing the old file, not
        # after. check_admissible has always existed and has only ever been
        # called downstream, by discover, on a file already on disk. That
        # ordering is fine for a question about age and useless for a question
        # about completeness: by the time discover can refuse the file, the
        # good one it would have fallen back to has been overwritten.
        refusal = _check_admissible(payload)
        if refusal is not None and refusal.kind != FORCEABLE_VERDICT:
            # Two of the three verdicts have no human answer, and --force stops
            # here for both. The refusal below has said so in words since the
            # day it was written, that names in a batch which answered nothing
            # "are the case this gate exists for and must never be forced
            # past", and until the override was scoped to the count fraction
            # verdict nothing enforced that sentence: a single
            # "if verdict and not force" wrote past the very verdict it warns
            # about.
            if refusal.kind == VERDICT_UNSWEPT_FRACTION:
                not_forceable = (
                    "--force does not apply to this verdict, and no flag does. "
                    "Unlike the count floor it is measured entirely from THIS "
                    "build's own funnel and never against the file on disk, so "
                    "it is not the frozen baseline trap --force exists for: "
                    "rerun when the vendor is answering, or when the shared "
                    "quota can pay for the whole market cap sweep, and it "
                    "clears with nobody having to decide anything. Writing past "
                    "it would put on disk the exact file this gate exists to "
                    "keep out of discover. The sweep runs in dollar volume "
                    "order, so one that lost batches has not thinned the "
                    "universe evenly, it has amputated the illiquid tail, and "
                    "the result still lands inside its expected count range "
                    "while the names it is missing are the ones a gap screen is "
                    "looking for.")
            else:
                not_forceable = (
                    "--force does not apply to this verdict. A payload carrying "
                    "no count is malformed rather than small, so there is no "
                    "judgement here for a human to have made and nothing a flag "
                    "could authorise. Something upstream of this line is broken "
                    "and forcing the write would only move the failure into "
                    "tomorrow morning.")
            raise PartialBuildError(
                f"{refusal.verdict} Refusing to overwrite the previous universe "
                f"with this one. {not_forceable}")
        if refusal is not None and not force:
            raise PartialBuildError(
                f"{refusal.verdict} Refusing to overwrite the previous universe "
                "with this one. The file already on disk is last week's and "
                "every later script knows how to refuse it once it is too old, "
                "which is a recoverable state. A fresh file that discover "
                "rejects is not: the monitor relaunches on age and this one "
                "would look new. If the shrink is REAL, rerun with --force. The "
                "usual reason for a real one is a floor tightened in "
                f"{config.CRITERIA_PATH.name}, which this gate cannot tell from "
                "a sweep that lost batches, because both arrive as a smaller "
                "count. Read the market cap funnel in the notes above first: "
                "names dropped by the floor were decided on evidence and are a "
                "real shrink, names in a batch that answered nothing are the "
                "case this gate exists for and are refused above this line, "
                "where no flag reaches them.")
        if refusal is not None:
            # Forced, and only the count fraction verdict can be here: the two
            # that carry no human answer raised above. The gate is not weakened
            # here, it is overridden by a human, and the file has to say so for
            # as long as it is the file on disk.
            #
            # The escape hatch is not optional for THIS verdict, because the
            # refusal measures this build against previous_count, which
            # _previous_count() reads from the very file the refusal keeps in
            # place. A genuine shrink below the floor is therefore measured
            # against the same frozen baseline every Sunday and refuses forever,
            # and once max_age_days has passed load_universe raises on that
            # unreplaceable file and the whole morning chain refuses with it. A
            # gate that can only be escaped by deleting the thing it is
            # defending is not a gate, it is a trap.
            #
            # The verdict text is carried verbatim rather than a boolean, for
            # two readers. A human opening the file later sees exactly what was
            # overridden instead of a flag they have to go and reconstruct, and
            # _check_admissible reads it back to tell the one verdict a human
            # accepted from any other verdict this file might later produce.
            payload["admissibility_override"] = {
                "verdict": refusal.verdict,
                "overridden_by": (
                    "a human, who passed --force to universe.py. The gate refused "
                    "this file and it was written anyway, so it is a build that "
                    "was overridden and never a build that passed."
                ),
            }
            print(f"WARNING  {refusal.verdict}")
            print("WARNING  --force was given, so this universe was written over "
                  "that refusal. The file records the verdict it was written "
                  "against, and every step that loads it says so.")
        write_atomically(payload)
        print(f"universe: wrote {config.UNIVERSE_PATH} with {len(admitted)} names")

    return payload


def _previous_count() -> int | None:
    """The name count of the universe file this build is about to replace."""
    try:
        existing = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    count = existing.get("count")
    return int(count) if isinstance(count, (int, float)) else None


class Admissibility(NamedTuple):
    """A refusal to use a universe file, and which check produced it.

    The kind is here so build() can tell the one verdict a human is allowed to
    override from the two that are not, without matching on the verdict text.
    That text names counts, a percentage and a criteria file, and it is written
    to be read by a person at 21:30 on a Sunday, so any substring test over it
    would break the first time the sentence is reworded, which is exactly the
    moment nobody is looking at this gate.
    """

    kind: str
    verdict: str


# The three refusals, named. FORCEABLE_VERDICT is one kind rather than a set
# because the argument for allowing an override is specific to the count
# fraction check and does not carry to the other two; _check_admissible makes
# that argument in full.
VERDICT_NO_COUNT = "no_count"
VERDICT_UNSWEPT_FRACTION = "unswept_fraction"
VERDICT_COUNT_FRACTION = "count_fraction"
FORCEABLE_VERDICT = VERDICT_COUNT_FRACTION


def _check_admissible(payload: dict[str, Any]) -> Admissibility | None:
    """Why this universe must not be used, or None when it is fine.

    Two questions, and they fail differently. Age is answered by
    load_universe, which raises. This answers the other one: is the file
    complete. A rebuild that admits far fewer names than the one before it is
    a partial run, not a market that halved overnight, and the count on its
    own cannot tell those apart. previous_count is what makes it decidable.

    One verdict, and exactly one, can be overridden: the count fraction one at
    the bottom, which a human already read and accepted by rebuilding with
    --force, and which build() records into admissibility_override before
    writing. It is the only one that needs an escape hatch, because it is the
    only one measured against the file the refusal keeps in place:
    _previous_count() reads previous_count out of exactly the universe.json a
    refusal refuses to replace, so a shrink that is REAL is measured against
    that same frozen baseline every Sunday and refuses forever. The other two
    have no such trap. The unswept fraction is computed entirely from this
    build's own funnel, so a rerun against a vendor that answers clears it with
    nobody deciding anything, and a payload carrying no count is malformed
    rather than small. Neither is forceable, here or in build().

    Scoping the override to the LAST check is also what makes it structurally
    unable to hide anything, rather than merely happening not to today. An
    override can only ever return None from the final branch of this function,
    so there is no check left below it to skip. That was not true when the
    override applied at all three sites: build() records the FIRST verdict its
    payload produced, so a run that tripped the unswept ceiling and was forced
    wrote that sentence into the file, and this function then matched it, and
    returned None on it, before ever reaching the count floor. The floor was
    silently off for that file in discover every morning until the next
    rebuild, on the one kind of file it most needed to be on for.

    The match is on the verdict TEXT, not on a flag, and that is the whole
    difference between an override and a switch. The text names the counts and
    the floor it was measured against, so it covers the sentence the human
    actually saw and nothing else: tighten the floor afterwards and the
    sentence changes, the override stops applying and the gate speaks again. A
    boolean would have silenced every future verdict too.
    """
    fraction = _CRIT.number("universe", "min_count_fraction_of_previous")
    count = payload.get("count")
    previous = payload.get("previous_count")

    if not isinstance(count, (int, float)):
        return Admissibility(VERDICT_NO_COUNT, "universe.json carries no count")

    # The size question and the evidence question are different, and the size
    # question cannot answer this one. A sweep that ran out of quota partway
    # drops names in dollar volume order, so the file stays within its
    # expected range and above the previous count fraction while its illiquid
    # tail is gone. What separates that from a real week is not how many names
    # are missing but WHY: a name the vendor priced below the floor was
    # decided, a name nothing ever got an answer for was only unasked.
    #
    # Older files carry no funnel and are skipped rather than failed. There is
    # nothing to compare, and treating an absent field as a failure would
    # refuse a universe that predates the field for no reason.
    funnel = payload.get("market_cap_funnel")
    if isinstance(funnel, dict):
        examined = funnel.get("examined")
        # ONLY the batches that answered nothing. absent_from_answered_batch
        # is deliberately excluded: that batch was answered and the vendor
        # simply did not carry the name, which is a fact about its coverage
        # rather than about this run. It is also structural and constant, 26
        # preferreds and warrants on 2026-08-17, so folding it in would spend
        # a third of the ceiling on a baseline that never varies and would
        # leave real losses only 1.6 batches of room.
        unswept = funnel.get("in_an_unanswered_batch") or 0
        limit = _CRIT.number("universe", "max_unswept_fraction")
        if isinstance(examined, (int, float)) and examined > 0 and unswept:
            share = unswept / examined
            if share > limit:
                # Returned unconditionally, with no consultation of the
                # override. A file that lost batches is not made whole by a
                # human having read a sentence about it, and this is the one
                # verdict a rerun fixes on its own.
                return Admissibility(VERDICT_UNSWEPT_FRACTION, (
                    f"universe.json never got an answer for {int(unswept)} of "
                    f"{int(examined)} names it examined ({share:.1%}), above the "
                    f"{limit:.1%} ceiling in {config.CRITERIA_PATH.name} "
                    "[universe] max_unswept_fraction. Those names were not "
                    "rejected, nothing came back for them at all, and because "
                    "the sweep runs in dollar volume order the ones it loses "
                    "are the illiquid tail rather than a random sample."))

    if not isinstance(previous, (int, float)) or previous <= 0:
        return None  # nothing to compare against, which is not a failure
    floor = previous * fraction
    if count < floor:
        verdict = (
            f"universe.json holds {int(count)} names against {int(previous)} in "
            f"the run before it, below the {fraction:g} floor of {floor:.0f} "
            f"in {config.CRITERIA_PATH.name} [universe] "
            "min_count_fraction_of_previous. That reads as a rebuild that was "
            "cut short rather than as a market that shrank, and a pool built "
            "from a partial universe is indistinguishable from a real one "
            "downstream.")
        override = payload.get("admissibility_override")
        accepted = override.get("verdict") if isinstance(override, dict) else None
        if accepted == verdict:
            # The human read this exact sentence and accepted it. Anything else
            # recorded there answers a different question and leaves this one
            # standing, which is why a file carrying an older build's unswept
            # verdict is still refused here rather than waved through.
            return None
        return Admissibility(VERDICT_COUNT_FRACTION, verdict)
    return None


def check_admissible(payload: dict[str, Any]) -> str | None:
    """The verdict text from _check_admissible, or None when the file is fine.

    The public shape, and the one discover reads: a sentence to refuse with, or
    nothing at all. build() calls _check_admissible directly instead, because
    it is the only caller that has to know WHICH verdict it got in order to
    decide whether --force is allowed to answer it.
    """
    refusal = _check_admissible(payload)
    return refusal.verdict if refusal else None


def write_atomically(payload: dict[str, Any], target: Path | None = None) -> None:
    """Write to a temporary file in the same directory, then rename into place.

    Serves two files. universe.json by default, which is what the argument
    below is about, and watchlist.json when discover passes its path: the
    watchlist has the same destructive-replace problem and a sharper version
    of the consequence, since a truncated one at 07:15 costs the collector its
    whole 07:20 window and that tape cannot be fetched afterwards. It stays
    here rather than moving to core because both callers already import this
    module and a move would be a bigger change than the fix.

    os.replace is atomic on Windows and on POSIX, so a reader either sees the
    whole previous file or the whole new one and never a half written one. The
    temporary file is a sibling because rename is only atomic within a
    filesystem.

    This matters more than it looks, and the first real firing showed why.
    The Sunday job bills a measured 4,945 credits to the same quota day as
    Monday morning, and the key is shared with another project that was
    measured taking 15,910 credits in thirty minutes on 2026-08-16. On
    2026-08-16 this job started with 329 credits against a bill of 4,945 and
    survived only because the vendor's counter rolled within its first
    seconds. A refused or interrupted run is not a hypothetical, and a plain
    write_text leaves a truncated file behind when it happens. A stale
    universe from last Sunday is a usable input and every later script knows
    how to refuse one that is too old. A half written one is not usable, and
    until this nothing could tell the two apart.
    """
    target = Path(target) if target is not None else config.UNIVERSE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    try:
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, target)
    finally:
        # A crash between the write and the replace leaves the partial file
        # behind; it is never read by anything, but it should not accumulate.
        temporary.unlink(missing_ok=True)


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the weekly discovery universe.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not rebuild. Report whether the existing universe.json is fresh.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Write the universe when the admissibility gate refuses it ON THE "
             "COUNT FRACTION VERDICT ALONE, which is the only verdict measured "
             "against the previous file and so the only one that can refuse "
             "forever against a frozen baseline. For a shrink that is real, a "
             "tightened CRITERIA.md floor being the usual reason. This flag is "
             "INERT against the other verdicts: a sweep that lost batches, or a "
             "payload carrying no count, refuses with or without it, because a "
             "rerun clears those by itself. The file records the verdict it was "
             "written against, so a forced universe can always be told from one "
             "that passed.",
    )
    args = parser.parse_args(argv)

    if args.check and args.force:
        # Rejected rather than ignored. --force is only ever read by build(),
        # and the --check branch below returns before build() is called, so the
        # combination used to do exactly nothing while looking like it did
        # something. The operator reaching for it is reaching for it at 21:30 on
        # a Sunday with a refusal on the screen, and the reading they would take
        # from a --check that still refuses is "I forced it and it refused
        # anyway", when in fact nothing was ever offered a chance to be forced.
        print("universe: --check and --force cannot be combined. --check only "
              "reads the universe.json already on disk and never writes one, so "
              "there is no admissibility gate here for --force to answer. Rerun "
              "without --check to rebuild, and --force will then apply to the "
              "gate that runs before the write.")
        return 1

    if args.check:
        try:
            payload = require_fresh_universe()
        except StaleUniverseError as exc:
            print(f"REFUSING TO RUN: {exc}")
            eodhd.print_call_report()
            return 1
        print(f"universe: fresh, {payload['count']} names")
        eodhd.print_call_report()
        return 0

    try:
        payload = build(force=args.force)
    except eodhd.QuotaRefusal as exc:
        # Ahead of the RuntimeError handler below, and it has to be: QuotaRefusal
        # subclasses RuntimeError, so without this a refusal is reported as
        # "build failed" with no reason recorded on the job status line. This
        # is discover's wording and discover's record, because it is the same
        # event: the shared key cannot pay, so nothing was attempted.
        print(f"REFUSING TO RUN: {exc}")
        job_status.failed(f"{type(exc).__name__}: {exc}")
        eodhd.print_call_report()
        return 1
    except PartialBuildError as exc:
        # Also ahead of the bare RuntimeError handler, and for the same reason.
        # This one spent the quota and produced a file; it simply refused to
        # let that file replace a better one. The record has to say so, because
        # the visible symptom otherwise is a universe that did not change.
        print(f"REFUSING TO WRITE: {exc}")
        job_status.failed(f"{type(exc).__name__}: {exc}")
        eodhd.print_call_report()
        return 1
    except RuntimeError as exc:
        print(f"universe: build failed, {exc}")
        eodhd.print_call_report()
        return 1

    job_status.produced("universe names", payload["count"])
    for note in payload["notes"]:
        print(f"universe note: {note}")
    eodhd.print_call_report()
    count_min, count_max = payload["expected_count_range"]
    return 0 if count_min <= payload["count"] <= count_max else 1


if __name__ == "__main__":
    raise SystemExit(job_status.run("universe", main, ok_codes=OK_CODES))
