.PHONY: sync test lint fmt hello

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
