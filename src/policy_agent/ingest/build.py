"""Build data/processed/{stats.parquet, stats.duckdb, chunks.jsonl, quality_report.json}."""

import json
import re

import duckdb
import pandas as pd

from policy_agent.ingest import mom_meta
from policy_agent.ingest.chunking import chunk_document
from policy_agent.ingest.documents import Document, extraction_coverage, parse_memo, parse_mom_html
from policy_agent.ingest.paths import PROCESSED, RAW, SYNTHETIC
from policy_agent.ingest.schema import STATS_SCHEMA
from policy_agent.ingest.stat_cards import stat_cards
from policy_agent.ingest.structured import INDUSTRY_ROLLUPS, load_singstat_sa, load_structured

NEAR_DUP_JACCARD = 0.8
ROUNDING = {
    "job_vacancy_by_industry_q": 100,
    "retrenched_by_industry_q": 10,
}  # published rounding unit
GARBAGE_RATIO = 0.35


def mom_documents() -> list[tuple[Document, dict]]:
    manifest = json.loads((RAW / "manifest.json").read_text())
    out = []
    for row in sorted((r for r in manifest if r["source"] == "mom"), key=lambda r: r["key"]):
        html = (RAW / row["path"]).read_text(encoding="utf-8", errors="ignore")
        doc = parse_mom_html(html, row["key"])
        rtype = mom_meta.release_type(doc.title, row["url"], row["key"])
        ref = mom_meta.reference_period(doc.title, rtype, doc.pub_date)
        meta = {
            "publisher": "MOM",
            "report_series": mom_meta.series(rtype),
            "doc_type": rtype,
            "release_type": rtype,
            "reference_period": ref,
            "synthetic": False,
            "access_level": "public",
            "url": row["url"],
            "content_sha256": doc.content_sha256,
            "extraction_coverage": round(extraction_coverage(html, doc), 3),
        }
        out.append((doc, meta))
    return out


def memo_documents() -> list[tuple[Document, dict]]:
    out = []
    for path in sorted(SYNTHETIC.glob("memo_*.md")):
        doc = parse_memo(path.read_text(), path.stem)
        m = doc.meta
        meta = {
            "publisher": "synthetic",
            "report_series": m["report_series"],
            "doc_type": "memo",
            "release_type": "memo",
            "reference_period": m["reference_period"],
            "synthetic": m["synthetic"] == "true",
            "access_level": m["access_level"],
            "url": None,
            "content_sha256": doc.content_sha256,
            "extraction_coverage": 1.0,
        }
        out.append((doc, meta))
    return out


def text_chunks() -> list[dict]:
    rows = []
    for doc, meta in mom_documents() + memo_documents():
        for ch in chunk_document(doc):
            rows.append(
                {
                    "chunk_id": ch.chunk_id,
                    "source_id": doc.source_id,
                    "title": doc.title,
                    "pub_date": doc.pub_date,
                    "page": 1,
                    "section": ch.section,
                    "char_start": ch.char_start,
                    "tokens": ch.tokens,
                    **meta,
                    "text": ch.text,
                }
            )
    return rows


# --- quality checks ----------------------------------------------------------------------


def _shingles(text: str, k: int = 5) -> set[tuple[str, ...]]:
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i : i + k]) for i in range(max(len(w) - k + 1, 1))}


def drop_near_duplicates(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep the first of any near-identical text chunks (repeated MOM footers); stat cards are exempt."""
    kept: list[dict] = []
    removed: list[dict] = []
    sigs: dict[str, set] = {}
    for c in chunks:
        if c["doc_type"] == "stat_card":
            kept.append(c)
            continue
        sh = _shingles(c["text"])
        twin = next(
            (k for k, o in sigs.items() if len(sh & o) / max(len(sh | o), 1) >= NEAR_DUP_JACCARD),
            None,
        )
        if twin:
            removed.append(
                {
                    "chunk_id": c["chunk_id"],
                    "source_id": c["source_id"],
                    "duplicate_of": twin,
                    "section": c["section"],
                }
            )
        else:
            sigs[c["chunk_id"]] = sh
            kept.append(c)
    return kept, removed


def quality_report(stats: pd.DataFrame, chunks: list[dict]) -> dict:
    text = [c for c in chunks if c["doc_type"] != "stat_card"]
    report: dict = {"stats_rows": len(stats), "in_window_rows": int(stats.in_window.sum())}
    nulls = stats[stats.value.isna()]
    report["null_values"] = {"total": len(nulls), "in_window": int(nulls.in_window.sum()),
                             "by_source": nulls.groupby("source_id").size().to_dict()}  # fmt: skip

    # SingStat SA series must equal the MOM seasonally adjusted quarterly rates
    sa = stats[(stats.indicator == "unemployment_rate") & (stats.seasonal_adjustment == "sa")
               & (stats.period_type == "quarter")][["residency", "period", "value"]]  # fmt: skip
    ss = load_singstat_sa()
    merged = sa.merge(ss, on=["residency", "period"], suffixes=("_mom", "_singstat"))
    diff = (merged.value_mom - merged.value_singstat).abs()
    report["singstat_cross_check"] = {
        "compared": len(merged),
        "mismatches": int((diff > 0.05).sum()),
    }

    # Verified industry roll-ups: aggregate == sum of components within the series' rounding unit.
    # Only periods where the aggregate and every component are published are comparable.
    roll = {}
    for src, unit in ROUNDING.items():
        d = stats[(stats.source_id == src) & stats.in_window].pivot(index="period", columns="industry", values="value")
        for parent, parts in INDUSTRY_ROLLUPS.items():
            comparable = d[parent].notna() & d[parts].notna().all(axis=1)
            diff = (d[parent] - d[parts].sum(axis=1)).abs()[comparable]
            roll[f"{src}:{parent}"] = {
                "comparable": int(comparable.sum()),
                "within_tolerance": int((diff <= 1.5 * unit).sum()),
            }
    report["industry_rollup_checks"] = roll

    # Text chunk checks: empty, garbage ratio, near-duplicates
    report["text_chunks"] = len(text)
    report["empty_chunks"] = sum(1 for c in text if not c["text"].strip())
    report["garbage_chunks"] = [
        c["chunk_id"] for c in text
        if 1 - sum(ch.isalnum() or ch.isspace() for ch in c["text"]) / max(len(c["text"]), 1) > GARBAGE_RATIO
    ]  # fmt: skip
    cov = {c["source_id"]: c["extraction_coverage"] for c in text}
    report["extraction_coverage"] = {
        "min": min(cov.values()),
        "below_0.9": sorted(k for k, v in cov.items() if v < 0.9),
    }
    report["chunk_ids_unique"] = len({c["chunk_id"] for c in chunks}) == len(chunks)
    report["missing_reference_period"] = sorted(
        {c["source_id"] for c in text if c["reference_period"] is None
         and c["doc_type"] not in ("parliamentary_reply", "explainer")}
    )  # fmt: skip
    return report


def build() -> dict:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    stats = STATS_SCHEMA.validate(load_structured())
    stats.to_parquet(PROCESSED / "stats.parquet", index=False)

    db = PROCESSED / "stats.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE stats AS SELECT * FROM read_parquet(?)", [str(PROCESSED / "stats.parquet")])
    con.execute("CREATE VIEW stats_window AS SELECT * FROM stats WHERE in_window")
    con.close()

    chunks = text_chunks() + stat_cards(stats)
    chunks.sort(key=lambda c: (c["source_id"], c["char_start"], c["chunk_id"]))
    chunks, removed = drop_near_duplicates(chunks)
    with open(PROCESSED / "chunks.jsonl", "w") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")

    report = quality_report(stats, chunks)
    report["chunks_total"] = len(chunks)
    report["near_duplicates_removed"] = removed
    (PROCESSED / "quality_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
