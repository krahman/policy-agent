"""Derive release type, series and reference period for MOM pages from title, URL and date."""

import re

_WORD_Q = {"first": 1, "second": 2, "third": 3, "fourth": 4}


def release_type(title: str, url: str, key: str) -> str:
    t = title.lower()
    if "parliament-questions" in url:
        return "parliamentary_reply"
    if "understanding" in key:
        return "explainer"
    if "in singapore advance release" in t:
        return "annual_advance"
    if "advance release" in t:
        return "advance"
    return "quarterly_report"  # Labour Market Report / Labour Market in nQ / Statement on developments


def series(rtype: str) -> str:
    return {
        "advance": "Labour Market Advance Release",
        "quarterly_report": "Labour Market Report",
        "annual_advance": "Labour Force in Singapore Advance Release",
        "parliamentary_reply": "Parliamentary Reply",
        "explainer": "MOM Explainer",
    }[rtype]


def reference_period(title: str, rtype: str, pub_date: str) -> str | None:
    """'2025-Q3' for quarterly series, '2024' for annual, None for replies and explainers."""
    t = title.lower()
    if rtype in ("parliamentary_reply", "explainer"):
        return None
    if rtype == "annual_advance":
        m = re.search(r"\b(20\d{2})\b", t)
        return m.group(1) if m else pub_date[:4]
    if m := re.search(r"(first|second|third|fourth) quarter (20\d{2})", t):
        return f"{m.group(2)}-Q{_WORD_Q[m.group(1)]}"
    if m := re.search(r"\b([1-4])q ?(20\d{2})", t):
        return f"{m.group(2)}-Q{m.group(1)}"
    if m := re.search(r"\bq([1-4]) (20\d{2})", t):
        return f"{m.group(2)}-Q{m.group(1)}"
    if m := re.search(r"1h ?(20\d{2})", t):
        return f"{m.group(1)}-Q2"  # first-half statement: latest quarter is Q2
    if m := re.search(r"(?:release|report|developments in) (20\d{2})\b", t):
        return f"{m.group(1)}-Q4"  # full-year headline published in Q1 refers to Q4
    return None
