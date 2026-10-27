.PHONY: sync test lint fmt hello fetch ingest eda evalset check-eval sync-datasets review-sheet retrieval generation agent calibration-sheet calibrate mcp-demo mcp-notebook agent-demo redteam final analyse reproduce pricing

# Setup and checks ----------------------------------------------------------------------------------------------------
sync:
	uv sync --frozen

test:
	uv run pytest

lint:
	uv run ruff check . && uv run mypy src

fmt:
	uv run ruff format . && uv run ruff check --fix .

# One traced model call (appears in the LangSmith project if tracing is on)
hello:
	uv run python -m policy_agent.hello

# Data -------------------------------------------------------------------------------------------------------------------
fetch:        # download the public data per config/corpus.json and verify it against data/raw/manifest.json
	uv run python scripts/fetch_raw.py

ingest:       # build data/processed/{stats.parquet, stats.duckdb, chunks.jsonl, quality_report.json}
	uv run python -m policy_agent.ingest.build

eda:          # re-execute notebooks/02_eda.ipynb
	uv run python scripts/make_eda_notebook.py

# Evaluation set ---------------------------------------------------------------------------------------------------------
evalset:      # build the evaluation, retrieval, red-team and few-shot sets from the processed corpus
	uv run python -m policy_agent.eval.build

check-eval:   # validate them (gold evidence exists, no leakage, canaries are restricted, ...)
	uv run python -m policy_agent.eval.checks

review-sheet: # regenerate eval/REVIEW.md, keeping your ticks
	uv run python -m policy_agent.eval.review --update

sync-datasets: # optional: upload the datasets to LangSmith (needs LANGSMITH_API_KEY)
	uv run python scripts/sync_datasets.py

# Experiments. UPLOAD=--no-upload scores locally and writes eval/results/ only (no LangSmith traces, no quota use);
# run with UPLOAD= (empty) to send a run to LangSmith. Paid runs check your OpenRouter credit first.
UPLOAD ?= --no-upload

retrieval:    # BM25, dense, hybrid + re-rank, and the chosen R5 on the dev split
	for e in E1 E2b E4b E4d; do uv run python scripts/run_experiment.py $$e $(UPLOAD); done

generation:   # the model comparison: chain with Haiku (E6) and Sonnet (E5), judged, 3 repetitions
	for e in E6 E5; do uv run python scripts/run_experiment.py $$e $(UPLOAD); done

agent:        # the router agent (E7) and the simplified agent (E8) on the dev split
	for e in E7 E8; do uv run python scripts/run_experiment.py $$e $(UPLOAD); done

final:        # the held-out test split. Use only once per frozen configuration: needs --allow-test
	for e in E1T E2bT E4bT E4dT E6T E8T; do uv run python scripts/run_experiment.py $$e $(UPLOAD) --allow-test; done

redteam:      # policy-redteam-v1 against the agent (3 repetitions) plus the offline guardrail tests
	LANGSMITH_TRACING=false uv run python scripts/run_redteam.py --reps 3
	uv run pytest -q tests/test_guardrails.py

# Human review of the judge: a blind sheet, then compare the judge with your ticks
calibration-sheet:
	uv run python scripts/make_calibration_sheet.py E5
calibrate:
	uv run python scripts/calibrate_judge.py

# Demos ------------------------------------------------------------------------------------------------------------------
mcp-demo:     # raw MCP JSON-RPC lifecycle over stdio, then the negative cases (no key needed)
	uv run python scripts/mcp_protocol_demo.py

mcp-notebook: # re-execute notebooks/05_mcp_demo.ipynb (capability discovery, a tool call, resources, the ambiguity warning)
	uv run python scripts/make_mcp_notebook.py

agent-demo:   # the 10 demo scenarios on the live agent (needs OPENROUTER_API_KEY)
	LANGSMITH_TRACING=false uv run python scripts/demo_scenarios.py

# Reports ----------------------------------------------------------------------------------------------------------------
analyse:      # rebuild the tables in docs/EVAL_REPORT.md from the saved result files (no key, no spend)
	uv run python scripts/analyse_retrieval.py --write
	uv run python scripts/analyse_generation.py --write
	uv run python scripts/analyse_agent.py --write
	uv run python scripts/analyse_final.py --write

# Fresh clone to a verified project with no API key and no spend (needs network once, for the public data): install, download,
# rebuild the processed data, validate the evaluation set, lint, run the tests, run the MCP demo, rebuild the report tables.
# Anything that calls a model is under "Live runs" in README.md.
reproduce: sync fetch ingest check-eval lint test mcp-demo analyse
	@echo "reproduce: ok"

pricing:      # refresh config/pricing.yaml from OpenRouter (records the date)
	uv run python scripts/fetch_pricing.py anthropic/claude-haiku-5.5 anthropic/claude-sonnet-5.5 openai/gpt-4.1-mini --embeddings openai/text-embedding-3-small voyageai/voyage-4
