# Policy Research Agent

Evidence-grounded research assistant for the Singapore labour market. See `docs/PRD_Policy_Research_Agent.md` for the full plan.

## Setup

```bash
uv sync
cp .env.example .env   # fill in keys
make test
make hello             # traced call -> LangSmith project policy-agent-dev
```
