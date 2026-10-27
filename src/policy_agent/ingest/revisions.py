"""Extract headline retrenchment counts from MOM advance releases for revision analysis (EDA 2)."""

import json
import re

import pandas as pd

from policy_agent.ingest.paths import PROCESSED
from policy_agent.ingest.periods import quarter_label

_NUM = r"(\d{1,3}(?:,\d{3})+|\d{3,6})"


def _patterns(label: str) -> list[re.Pattern]:
    q = re.escape(label)
    return [
        # "(3,100)" / "at 3,500" after a statement about the target quarter
        re.compile(rf"retrenchments?[^.]{{0,80}}?\b{q}\s*\({_NUM}\)", re.I),
        re.compile(rf"retrenchments?[^.]{{0,60}}?(?:at|to)\s+{_NUM}\s+in\s+{q}", re.I),
        re.compile(rf"retrenchments?[^.]{{0,60}}?\bin\s+{q}\s*(?:\(|was|were|at)?\s*{_NUM}", re.I),
        re.compile(rf"{_NUM}\s*\(or [\d.]+ retrenched per 1,000 employees\)\s+were retrenched in\s+{q}", re.I),
        re.compile(rf"\b{q}[^.]{{0,40}}?retrench[^.]{{0,40}}?{_NUM}", re.I),
    ]


def extract_retrenchments(text: str, period: str) -> int | None:
    """Return the retrenchment count reported for `period` ('2025-Q3') in `text`, if one is stated."""
    label = quarter_label(period)
    for pat in _patterns(label):
        if m := pat.search(text):
            return int(m.group(1).replace(",", ""))
    return None


def revision_table() -> pd.DataFrame:
    """Per quarter: advance-release count, quarterly-report count, and the latest dataset value."""
    chunks = [json.loads(line) for line in (PROCESSED / "chunks.jsonl").read_text().splitlines()]
    docs: dict[tuple[str, str], str] = {}
    for c in chunks:
        if c["doc_type"] in ("advance", "quarterly_report") and c["reference_period"]:
            docs.setdefault((c["reference_period"], c["doc_type"]), "")
            docs[(c["reference_period"], c["doc_type"])] += " " + c["text"]
    stats = pd.read_parquet(PROCESSED / "stats.parquet")
    latest = stats[(stats.source_id == "retrenched_q")].set_index("period").value
    rows = []
    for period in sorted({p for p, _ in docs}):
        adv = extract_retrenchments(docs.get((period, "advance"), ""), period)
        rep = extract_retrenchments(docs.get((period, "quarterly_report"), ""), period)
        rows.append({"period": period, "advance": adv, "report": rep, "latest_dataset": latest.get(period)})
    df = pd.DataFrame(rows)
    df["revision_adv_to_latest"] = df.latest_dataset - df.advance
    return df
