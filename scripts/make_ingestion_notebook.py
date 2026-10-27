"""Build and execute notebooks/01_ingestion.ipynb: the data preparation pipeline shown step by step on the real data.
Needs data/raw (make fetch) and data/processed (make ingest). Run: uv run python scripts/make_ingestion_notebook.py"""

from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# 01 · Data preparation: ingestion, cleaning and quality checks

How the corpus is built from public sources, with every step shown on the real data: provenance and licences, the raw files, the tidy
statistics table and its schema, the cleaning decisions, the data-quality checks, and how MOM web pages become chunks.
The same code runs in `make ingest` (`policy_agent.ingest.build`); this notebook calls it step by step.

| Step | Input | Output |
|---|---|---|
| Fetch | `config/corpus.json` | `data/raw/` plus `manifest.json` (hash, licence, URL, fetch time per file) |
| Structured load | 21 data.gov.sg CSVs | one tidy table, checked against a pandera schema (`stats.parquet`, `stats.duckdb`) |
| Documents | 46 MOM HTML pages, 7 synthetic memos | blocks, then structure-aware chunks of at most 400 tokens |
| Stat cards | tidy table | one short sentence per published figure, so text retrieval can find numbers |
| Quality | all of the above | `quality_report.json` |

Scope window: **2021-Q3 to 2026-Q2**; data retrieved 2026-10-27."""),
    code("""import hashlib
import json

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display

from policy_agent.ingest.paths import CORPUS, PROCESSED, RAW, SCOPE_FROM, SCOPE_TO

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)
print("scope window:", SCOPE_FROM, "to", SCOPE_TO)"""),
    md(
        "## 1. Provenance and licences\nEvery downloaded file is listed in a manifest with its source URL, licence key, SHA-256 and fetch time. The manifest is the only part of `data/raw/` that is committed."
    ),
    code("""manifest = pd.DataFrame(json.loads((RAW / "manifest.json").read_text()))
summary = manifest.groupby(["source", "licence"]).agg(
    files=("key", "count"), megabytes=("bytes", lambda s: round(s.sum() / 1e6, 2)), last_fetched=("fetched_at", "max")
)
display(summary)
print("Licence keys:")
for k, v in CORPUS["licences"].items():
    print(f"  {k}: {v}")

bad = [r.path for r in manifest.itertuples() if hashlib.sha256((RAW / r.path).read_bytes()).hexdigest() != r.sha256]
print(f"\\nfiles whose content no longer matches the manifest hash: {len(bad)} of {len(manifest)}")"""),
    md(
        "## 2. Structured data: raw to tidy\nThe 21 data.gov.sg datasets arrive in different shapes (wide tables, `-` for suppressed cells, quarter labels in several formats). One loader per layout turns them into a single tidy table."
    ),
    code("""raw = pd.read_csv(RAW / "datagov" / "job_vacancy_by_industry_q.csv", dtype=str, encoding="utf-8-sig")
print("raw file as downloaded:", raw.shape)
display(raw.iloc[:4, :6])
print("suppressed cells ('-') in this file:", int((raw == "-").sum().sum()))"""),
    code("""from policy_agent.ingest.structured import load_structured

tidy = load_structured()
print("tidy table:", tidy.shape)
display(tidy.sample(6, random_state=0))
by_ind = tidy.groupby("indicator").agg(
    rows=("value", "size"), sources=("source_id", "nunique"), first=("period", "min"), last=("period", "max"), unit=("unit", "first")
)
display(by_ind)"""),
    md(
        "## 3. Schema validation\nThe tidy table must satisfy a pandera schema: allowed indicators, residency groups and seasonal-adjustment tags, period format matching the period type, percentages not above 100, no duplicate keys, and a null value only where a suppressed industry cell is documented."
    ),
    code("""import pandera.pandas as pa

from policy_agent.ingest.schema import STATS_SCHEMA

STATS_SCHEMA.validate(tidy)
print("the real table passes the schema")

pct = tidy[tidy.unit == "%"].head(2).copy()
cases = {
    "a percentage of 130": pct.assign(value=[130.0, pct.value.iloc[1]]),
    "a duplicated row": pd.concat([tidy.head(1), tidy.head(1)]),
    "a quarter label with the wrong format": tidy.head(1).assign(period_type="quarter", period="2025Q9"),
}
for name, bad_frame in cases.items():
    try:
        STATS_SCHEMA.validate(bad_frame, lazy=True)
        print(f"NOT CAUGHT: {name}")
    except pa.errors.SchemaErrors as e:
        print(f"rejected: {name} -> {e.failure_cases['check'].iloc[0]}")"""),
    md("""## 4. Cleaning and transformation decisions

| Decision | Why |
|---|---|
| Quarter labels in three formats (`2026-Q2`, `2026-06`, `20262Q`) become `YYYY-Qn` | one join key across datasets |
| Seasonal adjustment is **tagged from what the dataset states**: `sa`, `nsa`, or `unspecified` | annual rates, long-term unemployment and vacancy counts do not say, and the system must not guess |
| `-` markers become missing values, and **no stat card is made for them** | a suppressed cell must lead to an abstention, not an imputed figure |
| Industry aggregates are checked against the sum of their components | catches mis-parsed or double-counted rows |
| `in_window` flags rows inside 2021-Q3 to 2026-Q2 | the evaluation and the agent use the window; earlier history stays in the store |
| Units are explicit (`%`, `persons`, `ratio`) | percentage points and percent are different quantities |"""),
    code("""from policy_agent.ingest.periods import to_quarter

print({raw_label: to_quarter(raw_label) for raw_label in ["2026-Q2", "2026-06", "20262Q"]})
print()
display(tidy.seasonal_adjustment.value_counts().rename("rows").to_frame())
print("rows with a missing value:", int(tidy.value.isna().sum()), "| all are suppressed industry cells:", bool(tidy[tidy.value.isna()].industry.notna().all()))"""),
    md("## 5. Data-quality checks\n`make ingest` writes a quality report. The checks that matter for answer quality:"),
    code("""report = json.loads((PROCESSED / "quality_report.json").read_text())
ro = report["industry_rollup_checks"]
rows = [
    ("rows in the statistics table", report["stats_rows"]),
    ("rows inside the scope window", report["in_window_rows"]),
    ("missing values, in window", report["null_values"]["in_window"]),
    ("SingStat SA cross-check: rows compared / mismatches", f"{report['singstat_cross_check']['compared']} / {report['singstat_cross_check']['mismatches']}"),
    ("industry roll-ups within rounding: comparable / ok", f"{sum(v['comparable'] for v in ro.values())} / {sum(v['within_tolerance'] for v in ro.values())}"),
    ("text chunks", report["text_chunks"]),
    ("empty chunks", report["empty_chunks"]),
    ("garbage chunks (mostly symbols)", len(report["garbage_chunks"])),
    ("lowest HTML extraction coverage", report["extraction_coverage"]["min"]),
    ("near-duplicate chunks removed (repeated MOM footers)", len(report["near_duplicates_removed"])),
    ("chunk ids unique", report["chunk_ids_unique"]),
]
display(pd.DataFrame(rows, columns=["check", "result"]).set_index("check"))"""),
    md(
        "## 6. Unstructured data: HTML page to blocks to chunks\nMOM pages are parsed into headings, paragraphs and tables; the text is chunked on its own structure (sections first, paragraphs packed up to 400 tokens, tables kept whole) and every chunk gets a stable id."
    ),
    code("""from policy_agent.ingest.chunking import chunk_document
from policy_agent.ingest.documents import extraction_coverage, parse_mom_html

page = next((RAW / "mom").glob("*labour-market-report-second-quarter-2026*.html"))
html = page.read_text(encoding="utf-8", errors="ignore")
doc = parse_mom_html(html, page.stem)
print(doc.title, "|", doc.pub_date)
print(f"html {len(html):,} characters -> extracted text {len(doc.text):,} characters | extraction coverage {extraction_coverage(html, doc):.2f}")
display(pd.Series([b.kind for b in doc.blocks]).value_counts().rename("blocks").to_frame())
print("first paragraph:", next(b.text for b in doc.blocks if b.kind == "para")[:300], "...")"""),
    code("""chunks = chunk_document(doc)
tokens = pd.Series([c.tokens for c in chunks])
print(f"{len(chunks)} chunks | tokens: min {tokens.min()}, median {int(tokens.median())}, max {tokens.max()} (limit 400)")
for c in chunks[2:4]:
    print(f"\\n[{c.chunk_id}] section '{c.section}', {c.tokens} tokens:\\n{c.text[:350]} ...")

again = [c.chunk_id for c in chunk_document(parse_mom_html(html, page.stem))]
print("\\nchunk ids are identical when the page is processed again:", again == [c.chunk_id for c in chunks])"""),
    md(
        "## 7. What goes into the index\nText chunks and stat cards share one schema. Metadata drives retrieval filters: document type, reference period, residency, release type and `access_level` (two synthetic memos are `internal`)."
    ),
    code("""index = pd.read_json(PROCESSED / "chunks.jsonl", lines=True, dtype=False)
display(index.groupby(["doc_type", "access_level"]).agg(chunks=("chunk_id", "count"), median_tokens=("tokens", "median")))
print("synthetic chunks:", int(index.synthetic.astype(str).eq("True").sum()), "| columns:", ", ".join(index.columns))
card = index[index.doc_type == "stat_card"].iloc[0]
print("\\nexample stat card:", card.text)

text_tokens = index[index.doc_type != "stat_card"].tokens
plt.figure(figsize=(6, 2.6))
plt.hist(text_tokens, bins=30, color="#4C78A8")
plt.xlabel("tokens per text chunk")
plt.ylabel("chunks")
plt.title("Chunk sizes (structure-aware, at most 400 tokens)")
plt.tight_layout()
plt.show()"""),
    code("""import duckdb

con = duckdb.connect(str(PROCESSED / "stats.duckdb"), read_only=True)
display(con.sql("SELECT indicator, residency, seasonal_adjustment, period, value, unit FROM stats_window WHERE indicator = 'unemployment_rate' AND period = '2026-Q2' ORDER BY residency, seasonal_adjustment").df())
con.close()"""),
    md("""## Known gaps (details in `docs/DATASHEET.md`)

- Three MOM publications could not be found (3Q 2022 Advance Release, 3Q 2024 Report, 1Q 2026 Report) and are recorded as unresolved.
- MOM pages carry no HTML data tables, so annex tables are unavailable; numbers come from the data.gov.sg series or from prose.
- 12.9% of in-window retrenchment-by-industry cells are suppressed in the source; the system abstains on them.
- MOM page reuse terms are unverified, so raw files are not committed (they are fetched by script and checked against the manifest).
- The seasonal-adjustment basis of annual rates is not stated by the sources and stays `unspecified`."""),
]

nb = nbf.v4.new_notebook(
    cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}}
)
ExecutePreprocessor(timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).preprocess(
    nb, {"metadata": {"path": str(ROOT)}}
)
out = ROOT / "notebooks" / "01_ingestion.ipynb"
nbf.write(nb, out)
print("wrote", out.relative_to(ROOT))
