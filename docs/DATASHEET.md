# Datasheet: Singapore Labour Market Corpus

Datasheet for the corpus used by the Evidence-Grounded Policy Research Assistant (PRD §5). Retrieval date for all sources: **2026-10-27**. Scope window (frozen at Step 1): **Q3 2021 to Q2 2026**. Raw files are reproducible from `config/corpus.json` with `scripts/fetch_raw.py`; `data/raw/manifest.json` records the path, SHA-256, size, URL, licence and fetch time of every file.

## 1. Motivation

| Question | Answer |
|---|---|
| Purpose | Test a cited, abstention-capable research assistant on Singapore labour statistics, with natural cross-source checks and revision conflicts. |
| Why this domain | One agency (MOM) publishes both machine-readable tables and narrative reports, and revises advance figures in later reports. |
| Personal or confidential data | None. All official figures are aggregates. Synthetic memos are labelled and contain no personal data. |

## 2. Composition

### 2.1 Structured statistics (data.gov.sg, 21 datasets)

Each dataset has a CSV and a `.meta.json` (the catalogue record). Publisher: Ministry of Manpower, except where noted.

| Key | Indicator | Grain | Columns | Coverage (full file) |
|---|---|---|---|---|
| `unemp_rate_{overall,resident,citizen}_q` | `unemployment_rate` | quarter | `period` (`YYYY-MM`, quarter-end month), `residential_status`, `seasonally_adj_unemp_rate`, `non_seasonally_adj_unemp_rate` | 1992-03 to 2026-06 |
| `unemp_rate_{overall,resident,citizen}_a` | `unemployment_rate` | year | `year`, `residential_status`, `unemployment_rate` | 1992 to 2025 |
| `singstat_unemp_rate_sa_q` | `unemployment_rate` (SA) | quarter | Wide: `DataSeries` plus one column per quarter (`20262Q`, newest first); 3 series (total, resident, citizen) | 1992 Q1 to 2026 Q2 (SingStat-hosted) |
| `unemployed_{overall,resident,citizen}_q` | `unemployed_persons` | quarter | `period`, `residential_status`, `seasonally_adj_unemp`, `non_seasonally_adj_unemp` | 1992-03 to 2026-06 |
| `ltu_rate_resident_a`, `ltu_number_resident_a` | `long_term_unemployment_rate` (+ level) | year | `year`, `residential_status`, `ltu_rate` / `long_term_unemployed` | 1992 to 2025 |
| `unemp_rate_resident_by_age_hqa_sex_a` | `unemployment_rate` by `age_group` | year | `year`, `sex`, `age`, `highest_qualification_attained`, `nsa_unemployment_rate` | 2010 to 2025 |
| `retrenched_q`, `retrenched_a` | `retrenchments` | quarter / year | `quarter` or `year`, `retrench` | 1998 to 2026-Q2 / 2025 |
| `retrenched_by_industry_q` | `retrenchments` by `industry` | quarter | `quarter`, `industry`, `retrench` | 1998-Q1 to 2026-Q2 |
| `job_vacancy_q`, `job_vacancy_a` | `job_vacancies` | quarter / year | `quarter` or `year`, `job_vacancy` | 1998 to 2026-Q2 / 2025 |
| `job_vacancy_by_industry_q` | `job_vacancies` by `industry` | quarter | `quarter`, `industry`, `job_vacancy` | 1998-Q1 to 2026-Q2 |
| `vacancy_unemployed_ratio_q`, `_a` | `vacancy_to_unemployed_ratio` | quarter / year | `quarter` or `year`, `jv_to_ue` | 1998 to 2026-Q2 / 2025 |

Files contain full history; the scope window is applied in Step 2, not by trimming raw files.

### 2.2 Unstructured reports (mom.gov.sg, 46 HTML pages)

| Series | Pages | Window coverage |
|---|---|---|
| Labour Market Advance Release | One per quarter | 3Q 2021 to 2Q 2026, except **3Q 2022** (not found) |
| Labour Market Report | One per quarter | 3Q 2021 to 2Q 2026, except **3Q 2024** and **1Q 2026** (not found). 4Q 2021 and 2Q 2022 are MOM "Statement on Labour Market Developments" pages, the revised-release counterpart for those quarters |
| Labour Force in Singapore (advance release) | 2021 to 2025 | Annual; this is the advance release, not the full annual report |
| Other | 3 Parliamentary Question answers (2023, 2025, 2026), 1 explainer ("Understanding Singapore labour market statistics", 2024) | Context for definitions and youth/long-term unemployment |

All pages are HTML; no PDFs were needed, so the PDF loader and `pdfplumber` path in PRD §5.2 are unused. `employment_change` exists **only** in this text (see §6).

### 2.3 Synthetic analyst memos (`data/synthetic/memos/`, 7 files)

Labelled `synthetic=true`, with a visible banner. Two are `access_level=internal`; one contains an embedded injection string with canary `CANARY-7F3A-OVERRIDE`; two quote superseded advance-release figures. Test purposes and ground truth are in `data/synthetic/README.md`.

## 3. Collection and provenance

| Source | How obtained | Identifier recorded |
|---|---|---|
| data.gov.sg | `poll-download` API for the CSV and the v2 metadata endpoint, via `scripts/fetch_raw.py` | `dataset_id`, catalogue `lastUpdatedAt` in the `.meta.json` |
| mom.gov.sg | Direct page fetch of URLs from the MOM newsroom sitemap (`--discover`) | URL, final URL after redirects, page title |
| Synthetic memos | Written by the project author with Claude assistance; figures copied from the real sources above | `source_id: synth-memo-NN` |

Fetches use an honest `User-Agent` (`policy-agent-data-fetch/0.1`), paced requests and backoff on 429/5xx.

## 4. Licences and usage constraints

| Source | Licence | Constraint |
|---|---|---|
| data.gov.sg datasets | Singapore Open Data Licence v1.0 (recorded as `sg_odl`) | The catalogue metadata has **no per-dataset licence field**, so this rests on the site-wide data.gov.sg terms. Re-confirm on each dataset page before redistribution |
| MOM web pages | MOM website terms of use (`mom_terms`) | Reuse terms not individually verified. **Raw files are not committed**; `data/raw/*` is git-ignored except the manifest, and the corpus is rebuilt by script |
| Synthetic memos | Project-authored | Committed to the repo; not official documents |

## 5. Preprocessing

Implemented in `src/policy_agent/ingest/` and run with `make ingest` (`python -m policy_agent.ingest.build`). Outputs go to `data/processed/` (git-ignored, rebuilt deterministically; a test builds twice and compares hashes).

| Output | Content |
|---|---|
| `stats.parquet`, `stats.duckdb` | 12,418 tidy rows (2,204 inside the window; view `stats_window`). Columns: `indicator, residency, age_group, industry, industry_level, sex, qualification, seasonal_adjustment, period, period_type, value, unit, source_id, dataset_id, release_type, release_date, in_window` |
| `chunks.jsonl` | 2,438 chunks: 342 prose (MOM pages and memos) and 2,096 stat cards, each with `chunk_id, source_id, title, publisher, pub_date, reference_period, page, section, doc_type, release_type, synthetic, access_level` |
| `quality_report.json` | Counts and the checks below |

| Stage | What is done |
|---|---|
| Periods | One canonical form: quarters `YYYY-Qn`, years `YYYY`; converted from `YYYY-MM` (quarter-end month), `YYYY-Qn` and SingStat `20262Q`. A year is `in_window` only if fully inside Q3 2021 to Q2 2026 (2022 to 2025) |
| Seasonal adjustment | `sa` / `nsa` from column names; annual figures are `nsa` (averages of quarterly NSA data); the vacancy ratio is `sa` (stated by the dataset); retrenchment and vacancy levels are `unspecified` because the datasets do not say |
| Missing `-` | Converted to null, never zero. Nulls get no stat card, so such questions must abstain |
| Units | `%`, `persons`, `ratio`; counts are persons, not thousands |
| SingStat SA series | Not loaded as data (it duplicates the MOM SA columns); used only as a cross-check |
| Catalogue metadata | Only `lastUpdatedAt` is read; `contactEmails` is never loaded |
| MOM HTML | Article container extracted; footnote markers, scripts, share widgets removed; `<br>`-separated and `<p>` layouts both flattened; short bold lines become section headings; tables kept whole. A content hash is taken on the extracted text (`content_sha256`) |
| Chunking | Structure-aware: never crosses a section, packs paragraphs to at most 400 tokens (`cl100k_base`), tables stand alone. `chunk_id = sha1(source_id | page | char_start)[:16]` |
| Stat cards | One chunk per in-window row with a value, using the PRD template |
| Schema (pandera) | Enumerated indicators, residency, seasonal adjustment and units; non-negative values; percentages at most 100; period format matches `period_type`; no duplicate keys; null values only in the industry series |

Quality checks and their results on the final build:

| Check | Result |
|---|---|
| SingStat SA vs MOM SA unemployment rates | 414 comparisons, 0 mismatches |
| Industry roll-ups (aggregate = sum of components, within the published rounding unit) | 3 roll-ups x 2 series: every comparable period agrees (105 comparable periods in total) |
| Empty chunks / non-alphanumeric ratio above 35% | 0 / 0 |
| Text extraction coverage (extracted vs naive page text) | At least 99.95% on every MOM page |
| Near-duplicate prose chunks (5-gram Jaccard at least 0.8) | 12 repeated "For More Information" footers removed (first occurrence kept) |
| Reference period present on every report and advance release | Yes |

## 6. Known quality issues

| # | Issue | Evidence | Handling |
|---|---|---|---|
| 1 | Raw MOM HTML is not byte-stable | The same page fetched twice has equal length but different bytes; all 30 pages from the first fetch hash differently | **Handled:** `content_sha256` is computed on extracted text. The manifest HTML hash is a fetch record, not an integrity guarantee |
| 2 | Missing values encoded as `-` | `retrenched_by_industry_q`: 605 of 4,700 rows (108 of 840 inside the window); `job_vacancy_by_industry_q`: 23 rows (none inside the window) | Null with a documented reason; the answerer must abstain rather than impute |
| 3 | Industry labels mix hierarchy levels and classification vintages | 68 labels per file (42 inside the window), e.g. "accommodation" alongside "accommodation and food services", and "hotels and restaurants" in older years. All values are rounded (vacancies to the nearest 100, retrenchments to the nearest 10, verified) | `industry_level` marks 3 verified aggregates and their components; all other labels are `unverified`. Never sum across industries; allow rounding-sized differences |
| 4 | Three period encodings | `YYYY-MM`, `YYYY-Qn`, and `20262Q` | Normalise in Step 2; validate with period-continuity checks |
| 5 | Quarterly dataset vs report differ for one headline | MOM 3Q 2025 Report: resident unemployment 2.8% in September 2025; quarterly dataset `2025-09` SA: 2.9%. Overall (2.0) and citizen (3.1) agree | Possible monthly vs quarterly basis (unconfirmed). Keep both, record basis, use in conflict cases |
| 6 | Advance figures are later revised | 2Q 2024 retrenchments 3,100 → 3,270; 3Q 2025 retrenchments 3,500 → 3,670; 3Q 2025 employment growth +24,800 → +25,100; 3Q 2025 citizen unemployment 3.0% → 3.1% | Tag `release_type` and `release_date`; prefer the latest, show both |
| 7 | `employment_change` has no structured dataset | Absent from the data.gov.sg MOM catalogue | Extract from report text; tag `source_type=report_text`; cannot be queried through DuckDB |
| 8 | Advance Releases omit some breakdowns | Pages state resident and non-resident quarterly employment change is not published in the advance release | Questions needing those figures route to the Report |
| 9 | Catalogue metadata contains named officials' contact emails | `contactEmails` in every `.meta.json` | Do not index, trace or upload `.meta.json`; strip `contactEmails` before any LLM or LangSmith call |
| 10 | Pages may change after retrieval | MOM pages are live | Content is pinned to the 2026-10-27 retrieval; recorded `fetched_at` per file |
| 11 | **The published vacancy-to-unemployed ratio cannot be recomputed** | 2Q 2026: published 1.48, but vacancies / unemployed persons = 0.87; mean absolute difference 0.71 over the window; implied denominator is 54 to 69% of unemployed persons; the dataset gives no definition and MOM text refers to "jobseekers" | Quote the published series only; never derive the ratio; note the undocumented denominator in `limitations`. See EDA finding 3 |
| 12 | Annex tables are not in the page HTML | The pages contain no HTML data tables (only the explainer has two); where the annex lives was not investigated | Numbers come from DuckDB or prose; annex tables are out of reach |

## 7. Exclusions

| Excluded | Reason |
|---|---|
| World Bank / ILO-modelled unemployment (2 JSON files) | Different definition from MOM's; not a PRD source; risk of being cited as an MOM figure |
| MOM pages from 2020 (5 files) | Outside the scope window |
| `mom-2026-0921-labour-market-report-2q-2026` | The URL is the "Release of 1H2026 WSH Report", not the labour market report; the correct page is `…report-second-quarter-2026` |
| Parliamentary Q&A and press items outside the window | Not needed for the evaluation set |

## 8. Unresolved gaps

| Gap | Impact |
|---|---|
| 3Q 2022 Advance Release, 3Q 2024 Report, 1Q 2026 Report not in the MOM newsroom sitemap | The revision pair for those quarters cannot be built; evaluation cases must not depend on them. Candidates: manual search, or treat as genuine "not in corpus" unanswerable cases |
| Full annual "Labour Force in Singapore" report not obtained | Only the advance release is available, which narrows annual age and education commentary |

## 9. Uses and limits

| Intended | Not intended |
|---|---|
| Evaluating retrieval, citation and abstention behaviour; demonstrating deterministic calculation over official aggregates | Policy recommendations; any figure beyond 2026-06; granularity MOM does not publish (district, nationality of foreign workers) |

## 10. Maintenance

The corpus is static during evaluation. To refresh: update `config/corpus.json`, run `python scripts/fetch_raw.py`, review `CHANGED` lines, bump the scope window, and re-run the full evaluation (PRD §19 change-detection plan).
