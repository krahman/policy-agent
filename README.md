# Policy Research Agent

An evidence-grounded research assistant for the **Singapore labour market**. It will answer analytical questions about unemployment, employment change, retrenchments, job vacancies and wages from official MOM statistics and reports, return passage-level citations, do arithmetic with deterministic tools, and abstain when the evidence is insufficient, ambiguous or conflicting.

The full plan, hypotheses and experiment design are in [`docs/PRD_Policy_Research_Agent.md`](docs/PRD_Policy_Research_Agent.md). The task is defined in [`docs/Tech Challenge - GenAI Engineer v1.0.pdf`](docs/Tech%20Challenge%20-%20GenAI%20Engineer%20v1.0.pdf).

## Status

| Step | Scope | State |
|---|---|---|
| 0 | Scaffold, tooling, traced hello-world | Done |
| 1 | Corpus selection, provenance, synthetic memos, datasheet | Done |
| 2 | Ingestion, cleaning, stat cards, DuckDB store, EDA | Done |
| 3 | Evaluation set: 36 cases, retrieval labels, red-team set, leakage check, LangSmith datasets | Done (open review items in `eval/README.md`) |
| 4 | Baselines: BM25 (B0/E0), single-pass RAG (B1), table lookup (B2), deterministic evaluators, experiment runner | Done; results in `docs/EVAL_REPORT.md` |
| 5 | Retrieval experiments E1-E4d: BM25, dense (2 embeddings), hybrid RRF, + re-rank, + period filter, with bootstrap CIs | Done; `docs/EVAL_REPORT.md` section 3 (LangSmith traces missing: monthly limit) |
| 6 | Generation: validated chain (V1-V6, one repair), LLM judges, E5 (sonnet) vs E6 (haiku) | Done; `docs/EVAL_REPORT.md` section 4. Judge calibration needs your labels (`eval/CALIBRATION.md`) |
| 7 | MCP server (2 tools, 2 resources, 1 prompt, read-only), validating client with allow-list, protocol demo with negative cases | Done; `make mcp-demo`, `docs/CONCEPTS.md` |
| 8 to 11 | LangGraph agent, red-teaming, final evaluation, demo | Not started |

There is **no question-answering interface yet**. What exists today is the data pipeline, the evaluation set, their tests and the exploratory analysis. Sample queries, evaluation results and the architecture diagram will be added as those steps land.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12) and `make`.

```bash
uv sync
cp .env.example .env   # then fill in the keys below
make test
```

| Variable | Used for |
|---|---|
| `OPENROUTER_API_KEY` | All LLM calls, through OpenRouter's OpenAI-compatible API (`provider/model` slugs) |
| `OPENROUTER_MODEL` | Optional default model slug (default `anthropic/claude-haiku-5.5`) |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` | Tracing and experiments |

`.env` is git-ignored. Check the keys with `make hello`, which makes one traced call (it appears in the LangSmith project `policy-agent-dev`).

## Build the data

Raw files are **not committed**: `data/raw/` is git-ignored apart from `manifest.json`, because MOM's website terms for reuse have not been verified. They are fetched by script and checked against the manifest.

```bash
make fetch    # download raw data per config/corpus.json, rewrite data/raw/manifest.json
make ingest   # build data/processed/{stats.parquet, stats.duckdb, chunks.jsonl, quality_report.json}
make eda      # re-execute notebooks/02_eda.ipynb
```

`make ingest` is deterministic; a test builds twice and compares hashes. After `make fetch`, expect lines marked `CHANGED` for MOM pages: their raw HTML is not byte-stable, so `chunks.jsonl` records a hash of the extracted text instead.

### What is in the corpus

Window: **Q3 2021 to Q2 2026**, retrieved 2026-10-27.

| Source | Content |
|---|---|
| data.gov.sg (21 datasets, MOM and SingStat) | Unemployment rate and unemployed persons by residency (quarterly and annual), long-term unemployment, resident unemployment by age, retrenchments, job vacancies (including by industry), vacancy-to-unemployed ratio |
| mom.gov.sg (46 pages) | Labour Market Advance Releases and Reports, Labour Force in Singapore advance releases, three parliamentary replies, one explainer |
| Synthetic memos (7) | Labelled `synthetic=true`: two quote superseded advance figures, one holds an injection canary, two are `internal` |

Three MOM publications could not be found and are recorded as unresolved (3Q 2022 Advance Release, 3Q 2024 Report, 1Q 2026 Report). `employment_change` exists only in report text. Sources, licences, known quality issues and exclusions are in [`docs/DATASHEET.md`](docs/DATASHEET.md).

## Repository layout

```
config/corpus.json            # source of truth for data/raw and the scope window
data/raw/                     # fetched files (git-ignored) + manifest.json (hashes, licences)
data/synthetic/memos/         # synthetic analyst memos + README with ground truth
data/processed/               # built outputs (git-ignored)
docs/                         # PRD, challenge brief, DATASHEET.md
notebooks/02_eda.ipynb        # exploratory analysis (executed)
scripts/fetch_raw.py          # download and verify raw data
scripts/make_eda_notebook.py  # regenerate the notebook
scripts/sync_datasets.py      # upload evaluation datasets to LangSmith
scripts/run_experiment.py     # run a config over a dataset split (LangSmith or --local)
src/policy_agent/ingest/      # periods, structured loaders, schema, HTML parsing, chunking, stat cards, build
src/policy_agent/eval/        # evaluation cases, corpus lookups, validation and leakage checks, evaluators
src/policy_agent/retrieval/   # BM25, dense, hybrid (RRF), re-rank and period filter (role filter applied before ranking)
src/policy_agent/baselines/   # B0, B1, B2
src/policy_agent/generation/  # Answer schema
prompts/                      # versioned prompts
config/experiments/           # one YAML per experiment; config/pricing.yaml (model prices with date and source)
eval/                         # evaluation datasets (JSONL) and their README
src/policy_agent/llm.py       # OpenRouter chat-model factory
tests/                        # pytest suite
```

## Make targets

| Target | Does |
|---|---|
| `make sync` | `uv sync --frozen` |
| `make test` | pytest (integration tests excluded by default) |
| `make lint` | ruff and mypy |
| `make fmt` | ruff format and autofix |
| `make hello` | one traced LLM call |
| `make fetch`, `make ingest`, `make eda` | data pipeline, see above |
| `make evalset`, `make check-eval`, `make sync-datasets` | build, validate and upload the evaluation set (see [`eval/README.md`](eval/README.md)) |
| `make mcp-demo`, `make mcp-notebook` | print the MCP lifecycle and 8 negative cases; rebuild the discovery notebook |
| `make generation`, `make calibration-sheet`, `make calibrate` | run E6/E5 (haiku/sonnet) with LLM judges; build the blind judge-labelling sheet; compare judge with your ticks |
| `make retrieval` | run E1-E4d on the dev split and refresh the bootstrap-CI tables in `docs/EVAL_REPORT.md` |
| `make baselines`, `make pricing` | run E0/B0/B2/B1 on the dev split (LangSmith + `eval/results/`); refresh model prices from OpenRouter |

Tests that need the raw data are skipped if `data/raw/` has not been fetched.

## Findings so far

From the exploratory analysis (`notebooks/02_eda.ipynb`):

1. **Which unemployment rate?** Resident is 0.7 to 1.0 percentage points above overall, so an unqualified "unemployment" figure is ambiguous. Questions must name the measure or trigger a clarification.
2. **Advance figures get revised.** In 13 quarters where the advance release states a retrenchment count, the final figure was higher in 10 (largest revision +290). Conflicts must show both values with dates.
3. **Dividing vacancies by unemployed persons does not reproduce the published vacancy-to-unemployed ratio** (2Q 2026: 1.48 published, 0.87 computed; the published denominator is undocumented). The agent should quote the published figure rather than substitute its own division.
4. **Suppressed cells exist.** 12.9% of in-window retrenchment-by-industry cells are suppressed in the source; such questions must abstain rather than impute.
5. **Keyword overlap is weak.** Questions share a median 50% of their content words with their gold stat card, and cards for the three residency measures differ by one word, so retrieval needs metadata filters and structured lookup as well as text matching.

## Limitations

- Only baselines exist (BM25, a single-pass RAG chain, a table lookup); there is no hybrid retrieval, agent or MCP server yet, so nothing here is a finished question-answering system.
- The 36 evaluation cases were drafted with AI assistance and are not yet human-reviewed; see [`eval/README.md`](eval/README.md).
- Revision analysis covers 13 of 20 quarters, extracted by regex and checked by hand; treat it as directional.
- MOM pages carry no HTML data tables, so annex tables are not available; numbers come from the data.gov.sg series or prose.
- Licences: data.gov.sg datasets are assumed to fall under the Singapore Open Data Licence (the catalogue has no per-dataset licence field); MOM page reuse terms are unverified.

## Responsible use

- Public and synthetic data only. Synthetic memos are marked as such in their metadata and text and are not official documents.
- Do not upload confidential or personal data. The data.gov.sg catalogue metadata lists officials' contact emails; the pipeline never reads them and they should not be sent to any external service.
- The assistant is intended to inform analysts, not to make or recommend policy. Output is not a substitute for checking the cited MOM source.
