"""Period normalisation. Canonical forms: quarter 'YYYY-Qn', year 'YYYY'."""

import re

from policy_agent.ingest.paths import SCOPE_FROM, SCOPE_TO

_Q = re.compile(r"^(\d{4})-Q([1-4])$")
_YM = re.compile(r"^(\d{4})-(\d{2})$")
_SINGSTAT = re.compile(r"^(\d{4})([1-4])Q$")
_Y = re.compile(r"^\d{4}$")


def to_quarter(raw: str) -> str:
    """'2026-Q2', '2026-06' (quarter-end month) or '20262Q' -> '2026-Q2'."""
    raw = raw.strip()
    if m := _Q.match(raw):
        return raw
    if m := _YM.match(raw):
        month = int(m.group(2))
        if month not in (3, 6, 9, 12):
            raise ValueError(f"not a quarter-end month: {raw}")
        return f"{m.group(1)}-Q{month // 3}"
    if m := _SINGSTAT.match(raw):
        return f"{m.group(1)}-Q{m.group(2)}"
    raise ValueError(f"unrecognised quarter: {raw!r}")


def to_year(raw: str) -> str:
    raw = str(raw).strip()
    if not _Y.match(raw):
        raise ValueError(f"unrecognised year: {raw!r}")
    return raw


def in_window(period: str, period_type: str) -> bool:
    """Quarters inside [SCOPE_FROM, SCOPE_TO]; years only when fully inside the window."""
    if period_type == "quarter":
        return SCOPE_FROM <= period <= SCOPE_TO
    first = int(SCOPE_FROM[:4]) + (0 if SCOPE_FROM.endswith("Q1") else 1)
    last = int(SCOPE_TO[:4]) - (0 if SCOPE_TO.endswith("Q4") else 1)
    return first <= int(period) <= last


def quarter_label(period: str) -> str:
    """'2026-Q2' -> '2Q 2026' (MOM style)."""
    m = _Q.match(period)
    return f"{m.group(2)}Q {m.group(1)}" if m else period
