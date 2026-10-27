.PHONY: sync test lint fmt hello ingest eda fetch evalset check-eval sync-datasets review-sheet

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
