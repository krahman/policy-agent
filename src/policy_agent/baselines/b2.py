"""B2: deterministic table lookup for single-value questions. Floor for numeric accuracy; no retrieval, no LLM.

A small rule-based parser maps a question to (indicator, residency, adjustment, period). If it cannot, it abstains or
asks for clarification. It cannot compute changes or read prose.
"""

import re
import time
from functools import lru_cache
from typing import Any

import pandas as pd

from policy_agent.ingest.paths import PROCESSED
from policy_agent.ingest.periods import quarter_label
from policy_agent.ingest.stat_cards import card_id
from policy_agent.retrieval.corpus import load_chunks

_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_CHANGE = re.compile(
    r"percentage|change|how many more|difference|compare|versus|between|growth|rise|fall|from .* to ", re.I
)


@lru_cache(maxsize=1)
def _stats() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "stats.parquet")


@lru_cache(maxsize=1)
def _cards() -> dict[str, dict]:
    return {c["chunk_id"]: c for c in load_chunks() if c["doc_type"] == "stat_card"}


def periods_in(q: str) -> list[tuple[str, str]]:
    """[(period, 'quarter'|'year')]; quarters first, then bare years that are not part of a quarter."""
    found = [(f"{m.group(2)}-Q{m.group(1)}", "quarter") for m in re.finditer(r"\b([1-4])Q\s*(20\d{2})\b", q)]
    found += [
        (f"{m.group(2)}-Q{_ORD[m.group(1).lower()]}", "quarter")
        for m in re.finditer(r"\b(first|second|third|fourth) quarter(?: of)?\s*(20\d{2})\b", q, re.I)
    ]
    stripped = re.sub(
        r"\b[1-4]Q\s*20\d{2}\b|\b(?:first|second|third|fourth) quarter(?: of)?\s*20\d{2}\b", " ", q, flags=re.I
    )
    found += [(m.group(1), "year") for m in re.finditer(r"\b(20\d{2})\b", stripped)]
    return found


def parse(q: str) -> dict | str:
    """A lookup spec, or a reason string ('clarify: ...' / 'abstain: ...')."""
    low = q.lower()
    if _CHANGE.search(low):
        return "abstain: needs a calculation or comparison"
    if not any(k in low for k in ("unemploy", "vacanc", "retrench")):
        return "abstain: indicator not recognised"  # off-topic questions never get a clarifying question
    per = periods_in(q)
    if len(per) != 1:
        return "clarify: name exactly one period" if not per else "abstain: more than one period"
    period, ptype = per[0]
    res = next((r for r in ("citizen", "resident", "overall") if r in low), None)
    sa = "sa" if "seasonally adjusted" in low else None
    if "long-term unemployment" in low:
        return {"indicator": "long_term_unemployment_rate", "residency": "resident", "period": period, "ptype": "year"}
    if "vacanc" in low and "ratio" in low:
        return {"indicator": "vacancy_to_unemployed_ratio", "residency": None, "period": period, "ptype": ptype}
    if "vacanc" in low:
        return {"indicator": "job_vacancies", "residency": None, "period": period, "ptype": ptype}
    if "retrench" in low:
        return {"indicator": "retrenchments", "residency": None, "period": period, "ptype": ptype}
    if "unemploy" in low:
        if res is None:
            return "clarify: overall, resident or citizen?"
        ind = (
            "unemployed_persons" if re.search(r"how many|number of", low) and "rate" not in low else "unemployment_rate"
        )
        return {"indicator": ind, "residency": res, "period": period, "ptype": ptype, "sa": sa}
    return "abstain: indicator not recognised"


def lookup(spec: dict) -> pd.Series | None:
    s = _stats()
    m = (s.indicator == spec["indicator"]) & (s.period == spec["period"]) & (s.period_type == spec["ptype"])
    m &= s.industry.isna() & s.age_group.isna()
    if spec.get("residency"):
        m &= s.residency == spec["residency"]
    hit = s[m]
    if spec["indicator"] in ("unemployment_rate", "unemployed_persons") and spec["ptype"] == "quarter":
        hit = hit[hit.seasonal_adjustment == (spec.get("sa") or "sa")]  # quarterly headline is seasonally adjusted
    hit = hit[hit.value.notna()]
    return hit.iloc[0] if len(hit) == 1 else None


def render_value(row: pd.Series) -> str:
    v = f"{row.value:g}%" if row.unit == "%" else (f"{row.value:,.0f}" if row.unit == "persons" else f"{row.value:g}")
    when = quarter_label(row.period) if row.period_type == "quarter" else f"the year {row.period}"
    who = f"{row.residency} " if isinstance(row.residency, str) else ""
    return f"{who}{row.indicator.replace('_', ' ')} for {when}: {v}"


def run(inputs: dict) -> dict:
    t0 = time.perf_counter()
    spec = parse(inputs["question"])
    out: dict[str, Any] = {"citations": [], "retrieved": [], "usage": None, "schema_valid": None, "error": None}
    if isinstance(spec, str):
        status = "needs_clarification" if spec.startswith("clarify") else "abstained"
        out |= {"status": status, "text": spec.split(": ", 1)[1]}
    else:
        row = lookup(spec)
        if row is None:
            out |= {"status": "abstained", "text": "no matching figure in the statistics store"}
        else:
            cid = card_id(row)
            card = _cards().get(cid)  # only in-window rows have a card to cite
            out |= {"status": "answered", "text": render_value(row)}
            if card:
                out |= {"retrieved": [cid], "citations": [{"chunk_id": cid, "quote": card["text"][:120]}]}
    out["latency_ms"] = (time.perf_counter() - t0) * 1000
    return out
