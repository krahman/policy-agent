"""Render tidy rows as short text 'stat card' chunks so text retrieval can find structured facts."""

import hashlib

import pandas as pd

from policy_agent.ingest.paths import CORPUS
from policy_agent.ingest.periods import quarter_label

_NAME = {
    "unemployment_rate": "unemployment rate",
    "unemployed_persons": "number of unemployed persons",
    "long_term_unemployment_rate": "long-term unemployment rate",
    "long_term_unemployed_persons": "number of long-term unemployed persons",
    "retrenchments": "number of retrenched employees",
    "job_vacancies": "number of job vacancies",
    "vacancy_to_unemployed_ratio": "ratio of job vacancies to unemployed persons",
}
_SA = {"sa": " (seasonally adjusted)", "nsa": " (not seasonally adjusted)", "unspecified": ""}
_RETRIEVED = "2026-10-27"  # corpus retrieval date (docs/DATASHEET.md)
_MIN_SCOPE = {d["key"]: d for d in CORPUS["datagov"]}


def _value(v: float, unit: str) -> str:
    if unit == "%":
        return f"{v:g}%"
    if unit == "persons":
        return f"{v:,.0f}"
    return f"{v:g}"


def render(row: pd.Series) -> str:
    when = quarter_label(row.period) if row.period_type == "quarter" else f"the year {row.period}"
    who = f"{row.residency} " if isinstance(row.residency, str) else ""
    extras = []
    if isinstance(row.age_group, str):
        extras.append(f"aged {row.age_group}")
    if isinstance(row.sex, str):
        extras.append(row.sex)
    if isinstance(row.qualification, str):
        extras.append(f"highest qualification {row.qualification}")
    if isinstance(row.industry, str):
        extras.append(f"industry: {row.industry}")
    suffix = f" [{', '.join(extras)}]" if extras else ""
    basis = "annual average, " if row.period_type == "year" and row.unit != "persons" else ""
    return (
        f"Singapore {who}{_NAME[row.indicator]}{_SA[row.seasonal_adjustment]}{suffix}, "
        f"{basis}{when}: {_value(row.value, row.unit)} "
        f"(Source: MOM via data.gov.sg, dataset {row.dataset_id}, retrieved {_RETRIEVED})"
    )


def card_id(row: pd.Series) -> str:
    """Stable id from the row's identity. Missing dimensions are '' so the id does not depend on whether
    the frame came from memory (pd.NA) or from parquet (None)."""
    cols = ("source_id", "residency", "age_group", "industry", "sex", "qualification", "seasonal_adjustment", "period")
    key = "|".join("" if pd.isna(row[c]) else str(row[c]) for c in cols)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def stat_cards(stats: pd.DataFrame) -> list[dict]:
    """One chunk per in-window row with a value (nulls produce no card: no value to cite)."""
    rows = stats[stats.in_window & stats.value.notna()]
    out = []
    for _, r in rows.iterrows():
        out.append(
            {
                "chunk_id": card_id(r),
                "source_id": r.source_id,
                "doc_type": "stat_card",
                "title": f"{_NAME[r.indicator].capitalize()} ({r.source_id})",
                "publisher": "MOM",
                "report_series": "data.gov.sg",
                "pub_date": r.release_date,
                "reference_period": r.period,
                "page": 1,
                "section": "stat card",
                "char_start": 0,
                "synthetic": False,
                "access_level": "public",
                "release_type": r.release_type,
                "indicator": r.indicator,
                "residency": r.residency if isinstance(r.residency, str) else None,
                "text": render(r),
            }
        )
    return out
