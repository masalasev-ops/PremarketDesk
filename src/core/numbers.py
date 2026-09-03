"""One reading of "is this a number", for every module that asks a vendor.

Nine copies of `_as_float` lived across the tree until 2026-09-02, with three
behaviours: one also refused the string "NA", five refused the empty string
and NaN, and three accepted NaN as a float, so a vendor NaN reached the paper
ledger and the outcome fill as a number. This is the one reading, and the
strictest of the three: a value that is None, an empty string, the vendor's
"NA", not a number or infinite comes back as None, which the project's rule 4
then treats as missing rather than as zero.
"""

from __future__ import annotations

import math
from typing import Any

# What the vendor writes where a number is not available. Refused by name
# rather than by failing float(), because float("nan") succeeds.
_NOT_A_NUMBER_WORDS = frozenset({"", "NA", "N/A", "nan", "NaN", "null", "None"})


def as_float(value: Any) -> float | None:
    """A finite float, or None. Never raises.

    A bool is None, not 0.0 or 1.0. bool is a subclass of int, so float(False)
    is 0.0 and a vendor field that came back as false, which is how some of
    them say "not available", read as a measured zero until 2026-09-02, in
    the one function that exists to stop an absence reading as a number.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in _NOT_A_NUMBER_WORDS:
            return None
        value = text
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def as_int(value: Any) -> int | None:
    """A whole number, or None. A float that is not whole is refused."""
    number = as_float(value)
    if number is None or number != int(number):
        return None
    return int(number)
