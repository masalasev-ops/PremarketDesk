"""Reader for CRITERIA.md.

Every screen threshold in PremarketDesk lives in CRITERIA.md. No other module
in this project is allowed to hold a threshold literal. If you find yourself
typing a number into a screen, it belongs in that file instead.

The parser is deliberately small and deliberately strict. A missing key raises
and names the section, the key and the file, because a silently defaulted
threshold is a threshold you no longer own.

Run `python -m core.criteria` to print everything the file currently defines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core import config

# Suffixes allowed on a number so a market cap floor stays readable.
_MAGNITUDE = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}

_OPERATORS = (">=", "<=", ">", "<", "==")

_NUMBER_RE = re.compile(r"^[+-]?(\d[\d_]*)(\.\d+)?([KMB])?$", re.IGNORECASE)


class CriteriaError(ValueError):
    """Raised when CRITERIA.md is missing a parameter or holds a bad value."""


@dataclass(frozen=True)
class Rule:
    """A single comparison such as `> 3` or `>= 800M`."""

    op: str
    value: float
    source: str

    def test(self, observed: float | None) -> bool:
        """Missing data never passes. It is not a soft yes."""
        if observed is None:
            return False
        if self.op == ">":
            return observed > self.value
        if self.op == ">=":
            return observed >= self.value
        if self.op == "<":
            return observed < self.value
        if self.op == "<=":
            return observed <= self.value
        if self.op == "==":
            return observed == self.value
        raise CriteriaError(f"unknown operator {self.op!r} in {self.source}")

    def describe(self) -> str:
        return f"{self.op} {_format_number(self.value)}"


@dataclass(frozen=True)
class Band:
    """One line of an ordered banded lookup. rule None means the else line."""

    rule: Rule | None
    result: str

    def describe(self) -> str:
        left = self.rule.describe() if self.rule else "else"
        return f"{left} : {self.result}"


@dataclass
class Section:
    name: str
    title: str
    pairs: list[tuple[str, str]] = field(default_factory=list)

    def singles(self) -> dict[str, str]:
        """Last value wins for a repeated plain key."""
        return {key: value for key, value in self.pairs}


def _format_number(value: float) -> str:
    if value >= _MAGNITUDE["B"] and value % _MAGNITUDE["B"] == 0:
        return f"{value / _MAGNITUDE['B']:g}B"
    if value >= _MAGNITUDE["M"] and value % _MAGNITUDE["M"] == 0:
        return f"{value / _MAGNITUDE['M']:g}M"
    return f"{value:g}"


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")


def _strip_comment(line: str) -> str:
    hash_at = line.find("#")
    return line if hash_at < 0 else line[:hash_at]


def parse_number(raw: str, source: str) -> float:
    text = raw.strip()
    match = _NUMBER_RE.match(text)
    if not match:
        raise CriteriaError(f"{source}: {raw!r} is not a number")
    suffix = match.group(3)
    body = text[: -len(suffix)] if suffix else text
    try:
        value = float(body.replace("_", ""))
    except ValueError as exc:
        raise CriteriaError(f"{source}: {raw!r} is not a number") from exc
    if suffix:
        value *= _MAGNITUDE[suffix.upper()]
    return value


def parse_rule(raw: str, source: str) -> Rule:
    text = raw.strip()
    for op in _OPERATORS:
        if text.startswith(op):
            return Rule(op=op, value=parse_number(text[len(op):], source), source=source)
    raise CriteriaError(
        f"{source}: {raw!r} does not start with one of {', '.join(_OPERATORS)}"
    )


class Criteria:
    """Parsed CRITERIA.md. Build one with load()."""

    def __init__(self, sections: dict[str, Section], path: Path) -> None:
        self._sections = sections
        self.path = path

    # ---- section plumbing -------------------------------------------------

    def section(self, name: str) -> Section:
        found = self._sections.get(name)
        if found is None:
            known = ", ".join(sorted(self._sections)) or "none"
            raise CriteriaError(
                f"{self.path.name} has no section '{name}'. Sections found: {known}"
            )
        return found

    def section_names(self) -> list[str]:
        return list(self._sections)

    def _raw(self, section: str, key: str) -> str:
        values = self.section(section).singles()
        if key not in values:
            known = ", ".join(sorted(values)) or "none"
            raise CriteriaError(
                f"{self.path.name} section '{section}' has no key '{key}'. Keys found: {known}"
            )
        return values[key]

    def _where(self, section: str, key: str) -> str:
        return f"{self.path.name} [{section}] {key}"

    # ---- typed accessors --------------------------------------------------

    def rule(self, section: str, key: str) -> Rule:
        return parse_rule(self._raw(section, key), self._where(section, key))

    def number(self, section: str, key: str) -> float:
        return parse_number(self._raw(section, key), self._where(section, key))

    def integer(self, section: str, key: str) -> int:
        value = self.number(section, key)
        if value != int(value):
            raise CriteriaError(f"{self._where(section, key)}: {value} is not a whole number")
        return int(value)

    def flag(self, section: str, key: str) -> bool:
        raw = self._raw(section, key).strip().lower()
        if raw in ("true", "yes", "on", "1"):
            return True
        if raw in ("false", "no", "off", "0"):
            return False
        raise CriteriaError(f"{self._where(section, key)}: {raw!r} is not true or false")

    def text(self, section: str, key: str) -> str:
        return self._raw(section, key).strip()

    def text_list(self, section: str, key: str) -> list[str]:
        raw = self._raw(section, key)
        return [part.strip() for part in raw.split(",") if part.strip()]

    def clock(self, section: str, key: str) -> tuple[int, int]:
        """Return an ET wall clock time as (hour, minute)."""
        raw = self._raw(section, key).strip()
        match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
        if not match:
            raise CriteriaError(f"{self._where(section, key)}: {raw!r} is not HH:MM")
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise CriteriaError(f"{self._where(section, key)}: {raw!r} is not a valid clock time")
        return hour, minute

    def clock_text(self, section: str, key: str) -> str:
        hour, minute = self.clock(section, key)
        return f"{hour:02d}:{minute:02d}"

    def bands(self, section: str, key: str = "band") -> list[Band]:
        """Ordered bands. First match wins, and the else line must come last."""
        where = self._where(section, key)
        out: list[Band] = []
        for pair_key, raw in self.section(section).pairs:
            if pair_key != key:
                continue
            left, sep, right = raw.partition(":")
            if not sep:
                raise CriteriaError(f"{where}: {raw!r} is missing the ':' before its result")
            left, right = left.strip(), right.strip()
            if left.lower() == "else":
                out.append(Band(rule=None, result=right))
            else:
                out.append(Band(rule=parse_rule(left, where), result=right))
        if not out:
            raise CriteriaError(f"{where}: no '{key}' lines found")
        for band in out[:-1]:
            if band.rule is None:
                raise CriteriaError(f"{where}: the 'else' line must be the last one")
        return out

    def band_number(self, section: str, observed: float | None, key: str = "band") -> float:
        return parse_number(
            self.band_result(section, observed, key), self._where(section, key)
        )

    def band_result(self, section: str, observed: float | None, key: str = "band") -> str:
        bands = self.bands(section, key)
        for band in bands:
            if band.rule is None:
                return band.result
            if band.rule.test(observed):
                return band.result
        raise CriteriaError(
            f"{self._where(section, key)}: nothing matched {observed!r} and there is no else line"
        )

    def pair_map(self, section: str, key: str) -> dict[str, str]:
        """Read repeated `key = left : right` lines into an ordered dict."""
        where = self._where(section, key)
        out: dict[str, str] = {}
        for pair_key, raw in self.section(section).pairs:
            if pair_key != key:
                continue
            left, sep, right = raw.partition(":")
            if not sep:
                raise CriteriaError(f"{where}: {raw!r} is missing the ':' before its value")
            out[left.strip().lower()] = right.strip()
        if not out:
            raise CriteriaError(f"{where}: no '{key}' lines found")
        return out


def parse_text(text: str, path: Path) -> Criteria:
    sections: dict[str, Section] = {}
    current: Section | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        # An indented line is a markdown code block, which is how the syntax
        # examples above are written. Parameters always start at column zero.
        if line[:1].isspace():
            continue
        heading = re.match(r"^##\s+(.*\S)\s*$", line)
        if heading:
            title = heading.group(1)
            name = _slug(title)
            current = Section(name=name, title=title)
            sections[name] = current
            continue

        body = _strip_comment(line).strip()
        if not body or "=" not in body:
            continue
        if current is None:
            continue
        key, _, value = body.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            continue
        current.pairs.append((key, value))

    return Criteria(sections=sections, path=path)


# The accessor names a `_CRIT.<name>("section", "key")` call can use. check()
# below resolves every such call written with literal arguments.
_ACCESSORS = frozenset({
    "rule", "number", "integer", "flag", "text", "text_list", "clock",
    "clock_text", "bands", "band_number", "band_result", "pair_map", "section",
})
# Accessors whose second positional argument is not the key.
_SECTION_ONLY = frozenset({"bands", "band_number", "band_result", "section"})


def check(crit: Criteria, src_root: Path) -> dict[str, list[str]]:
    """Four questions the parser cannot ask at read time.

    1. Is any key prose? The parser reads every column zero line holding an
       equals sign under a `##` heading as a pair, and on 2026-09-02 [paper]
       carried the key "quotient: 10,000 / 0.04" from a sentence. A key with a
       space or a colon in it is a sentence.
    2. Does every literal `_CRIT.<accessor>("section", "key")` in src/ resolve?
       A typo in a key read inside a function surfaces at 08:45 on the first
       candidate; this surfaces it in the suite.
    3. Is a key read as a single value defined more than once in its section?
       Repeated keys are how pair_map and bands are written, so a repeat is
       only a defect for a key some literal call reads with a SCALAR accessor,
       and then it is always one: _raw takes the last pair, so the later line
       silently wins. [Analyst] mode was written as `mode = slots` and then
       explained in a note whose first line began "mode = slots since
       2026-09-02. Under it...", at column zero. That sentence parsed as a
       second mode. report_mode() saw a value that was neither freeform nor
       slots, said so on a line nobody reads, and fell back to freeform, so
       the slots restructure never ran in production: the 2026-09-02 chain
       spent 209 seconds and 17,989 output tokens on a freeform report while
       this file said slots. Question 1 could not catch it, because the key
       itself is a real key spelled correctly.
    4. Which pairs does no literal call read? Informational: keys are also
       read with a variable key (evaluate_eligibility iterates a section), so
       an unread pair is a candidate for deletion and not a defect.

    Returns {"prose_keys": [...], "unresolved": [...], "shadowed": [...],
    "unread": [...]}. The first three are defects.
    """
    import ast

    prose_keys: list[str] = []
    for name in crit.section_names():
        for key, _value in crit.section(name).pairs:
            if " " in key or ":" in key:
                prose_keys.append(f"[{name}] {key!r}")

    # Filled below with (section, key) for every literal call that reads one
    # value, so question 3 asks only of keys whose repetition is a mistake.
    scalar_reads: set[tuple[str, str]] = set()
    referenced: set[tuple[str, str]] = set()
    sections_referenced: set[str] = set()
    unresolved: list[str] = []
    for path in sorted(Path(src_root).rglob("*.py")):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_bytes().decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            unresolved.append(f"{path.name}: could not parse: {exc}")
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _ACCESSORS):
                continue
            literals = [a.value for a in node.args if isinstance(a, ast.Constant)
                        and isinstance(a.value, str)]
            if not literals or len(literals) != len(node.args):
                continue
            section = _slug(literals[0])
            where = f"{path.relative_to(src_root)}:{node.lineno}"
            try:
                sec = crit.section(section)
            except CriteriaError:
                unresolved.append(f"{where}: no section {literals[0]!r}")
                continue
            sections_referenced.add(section)
            if node.func.attr == "section":
                continue
            if node.func.attr in _SECTION_ONLY:
                key = literals[1] if len(literals) > 1 else "band"
            elif len(literals) < 2:
                continue
            else:
                key = literals[1]
            key = key.strip().lower()
            if not any(pair_key == key for pair_key, _ in sec.pairs):
                unresolved.append(f"{where}: [{section}] has no key {key!r}")
                continue
            referenced.add((section, key))
            if node.func.attr not in _SECTION_ONLY and node.func.attr != "pair_map":
                scalar_reads.add((section, key))

    shadowed: list[str] = []
    for section, key in sorted(scalar_reads):
        values = [value for pair_key, value in crit.section(section).pairs
                  if pair_key == key]
        if len(values) > 1:
            shadowed.append(
                f"[{section}] {key} is defined {len(values)} times and is read as one "
                f"value; the last wins, which is {values[-1][:60]!r}")

    unread: list[str] = []
    for name in crit.section_names():
        for key, _value in crit.section(name).pairs:
            if (name, key) not in referenced and name not in sections_referenced:
                unread.append(f"[{name}] {key}")
    return {"prose_keys": prose_keys, "unresolved": unresolved,
            "shadowed": shadowed, "unread": unread}


_cache: Criteria | None = None


def load(path: Path | None = None, refresh: bool = False) -> Criteria:
    """Parse CRITERIA.md once and hand back the same object thereafter."""
    global _cache
    if _cache is not None and not refresh and path is None:
        return _cache
    target = path or config.CRITERIA_PATH
    if not target.exists():
        raise CriteriaError(
            f"{target} is missing. It holds every screen threshold and nothing runs without it."
        )
    parsed = parse_text(target.read_text(encoding="utf-8"), target)
    if path is None:
        _cache = parsed
    return parsed


def _self_check() -> int:
    """Checkpoint 2 done condition: print every parameter the file defines."""
    crit = load()
    print(f"criteria file  {crit.path}")
    print()
    for name in crit.section_names():
        section = crit.section(name)
        if not section.pairs:
            continue
        print(f"[{name}]  {section.title}")
        for key, value in section.pairs:
            print(f"    {key:<32} {value}")
        print()

    print("resolved samples")
    day_gap = crit.rule("day_setup", "gap_pct")
    swing_gap = crit.rule("swing_setup", "gap_pct")
    print(f"    day gap rule            {day_gap.describe()}  (4 passes: {day_gap.test(4)})")
    print(f"    swing gap rule          {swing_gap.describe()}  (8 passes: {swing_gap.test(8)})")
    print(f"    day market cap          {crit.rule('day_setup', 'market_cap').describe()}")
    print(f"    universe dollar volume  {crit.rule('universe', 'avg_dollar_volume_20d').describe()}")
    print(f"    universe max age days   {crit.integer('universe', 'max_age_days')}")
    print(f"    subscribed candidates   {crit.integer('discovery', 'max_subscribed_candidates')}")
    print(f"    collector window        {crit.clock_text('collector', 'start_time')} to "
          f"{crit.clock_text('collector', 'stop_time')}")
    print(f"    context symbols         {crit.text_list('collector', 'context_symbols')}")
    print(f"    rvol points at 4.0      {crit.band_number('score_premarket_rvol', 4.0):g}")
    print(f"    rvol points at 2.0      {crit.band_number('score_premarket_rvol', 2.0):g}")
    print(f"    rvol points at 1.0      {crit.band_number('score_premarket_rvol', 1.0):g}")
    print(f"    rvol points when null   {crit.band_number('score_premarket_rvol', None):g}")
    print(f"    gap points at 9.0       {crit.band_number('score_gap', 9.0):g}")
    print(f"    bucket at 8             {crit.band_result('score_buckets', 8)}")
    print(f"    bucket at 5             {crit.band_result('score_buckets', 5)}")
    print(f"    bucket at 2             {crit.band_result('score_buckets', 2)}")
    print(f"    catalyst class points   {crit.pair_map('score_catalyst_class', 'class')}")
    print(f"    catalyst tag map size   {len(crit.pair_map('score_catalyst_tags', 'tag'))} tags")
    print()
    print("OK")
    return 0


def _check_main() -> int:
    """`python -m core.criteria --check`: the four questions, as a report."""
    report = check(load(), config.PROJECT_ROOT / "src")
    for label in ("prose_keys", "unresolved", "shadowed"):
        for line in report[label]:
            print(f"DEFECT  {label}: {line}")
    for line in report["unread"]:
        print(f"unread  {line}")
    defects = (len(report["prose_keys"]) + len(report["unresolved"])
               + len(report["shadowed"]))
    print(f"criteria --check: {defects} defect(s), {len(report['unread'])} pair(s) no "
          "literal call reads")
    return 1 if defects else 0


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(_check_main() if "--check" in _sys.argv[1:] else _self_check())
