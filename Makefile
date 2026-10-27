.PHONY: sync test lint fmt hello ingest eda fetch evalset check-eval sync-datasets review-sheet baselines retrieval generation calibration-sheet calibrate mcp-demo mcp-notebook agent-demo agent redteam final rescore pricing

sync:
	uv sync --frozen

test:
	uv run pytest

lint:
	uv run ruff check . && uv run mypy src

fmt:
	uv run ruff format . && uv run ruff check --fix .

# Step 0 exit check: one traced call visible in LangSmith project policy-agent-dev
hello:
	uv run python -m policy_agent.hello

# Step 2: rebuild processed data (stats.parquet, stats.duckdb, chunks.jsonl, quality_report.json)
ingest:
	uv run python -m policy_agent.ingest.build

# Re-run the EDA notebook
eda:
	uv run python scripts/make_eda_notebook.py

# Re-download raw data and verify against the manifest
fetch:
	uv run python scripts/fetch_raw.py

# Step 3: build the evaluation datasets from the processed corpus, then validate them
evalset:
	uv run python -m policy_agent.eval.build

check-eval:
	uv run python -m policy_agent.eval.checks

# Push datasets to LangSmith (needs LANGSMITH_API_KEY)
sync-datasets:
	uv run python scripts/sync_datasets.py

# Human review sheet for the evaluation cases (refuses to overwrite ticked boxes; --force to override)
review-sheet:
	uv run python -m policy_agent.eval.review --update

# UPLOAD=--no-upload scores locally and writes eval/results/ only (no LangSmith traces, no quota use).
# Run `make baselines UPLOAD=` (empty) only for runs you want in the LangSmith comparison view.
UPLOAD ?= --no-upload

# Step 4: baselines on the dev split (results go to LangSmith and eval/results/). Needs OPENROUTER and LANGSMITH keys.
baselines:
	for e in E0 B0 B2 B1; do uv run python scripts/run_experiment.py $$e $(UPLOAD); done

# Step 5: retrieval experiments E1-E4d on the dev split, then bootstrap-CI analysis into docs/EVAL_REPORT.md
retrieval:
	for e in E1 E2 E2b E3 E3b E4 E4b E4c E4d; do uv run python scripts/run_experiment.py $$e $(UPLOAD); done
	uv run python scripts/analyse_retrieval.py --write

# Step 6: validated chain with two models (E5 sonnet, E6 haiku) and LLM judges, dev split, 3 repetitions each
generation:
	for e in E6 E5; do uv run python scripts/run_experiment.py $$e $(UPLOAD); done

# Blind human-labelling sheet for the judge, then compare the judge with your ticks (agreement and Cohen's kappa)
calibration-sheet:
	uv run python scripts/make_calibration_sheet.py E5
calibrate:
	uv run python scripts/calibrate_judge.py

# Step 7: MCP server protocol demo (raw JSON-RPC lifecycle + negative cases) and the discovery notebook
mcp-demo:
	uv run python scripts/mcp_protocol_demo.py
mcp-notebook:
	uv run python scripts/make_mcp_notebook.py

# Step 8: the 10 demo scenarios against the live agent; E7 (agent) on dev, then the H3 analysis
agent-demo:
	LANGSMITH_TRACING=false uv run python scripts/demo_scenarios.py
agent:
	uv run python scripts/run_experiment.py E7 $(UPLOAD)
	uv run python scripts/analyse_agent.py --write

# Step 9: policy-redteam-v1 against the agent (3 reps), and the offline guardrail tests
redteam:
	LANGSMITH_TRACING=false uv run python scripts/run_redteam.py --reps 3
	uv run pytest -q tests/test_guardrails.py

# Step 10 (spends credit; each run is checked against your balance first). Order matters: dev re-run of the frozen config,
# then the single held-out test run of agent, chain and retriever, then the red team, then the analysis.
final:
	uv run python scripts/run_experiment.py E7b --no-upload
	uv run python scripts/run_experiment.py E7T --no-upload --allow-test
	uv run python scripts/run_experiment.py E6T --no-upload --allow-test
	uv run python scripts/run_experiment.py E4dT --no-upload --allow-test
	LANGSMITH_TRACING=false uv run python scripts/run_redteam.py --reps 3 --out redteam_agent_final
	uv run python scripts/analyse_final.py --write

# Re-score saved E5-E7 outputs under the corrected labels (v1.1); originals are not touched
rescore:
	uv run python scripts/rescore_labels.py --write

# Refresh config/pricing.yaml from OpenRouter (records the date)
pricing:
	uv run python scripts/fetch_pricing.py anthropic/claude-haiku-5.5 anthropic/claude-sonnet-5.5 --embeddings openai/text-embedding-3-small voyageai/voyage-4
