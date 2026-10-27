"""Spend guard: check the OpenRouter credit balance before a paid run and refuse to start one that cannot finish.

The balance comes from OpenRouter's /credits endpoint (total credit minus total usage). A run is allowed only if its
estimated cost, times a safety factor, plus a reserve fits in what is left. Estimates come from earlier recorded runs
of the same kind, so they are rough; the guard is a seat belt, not an accountant."""

import json
import os
import urllib.request

from policy_agent.ingest.paths import ROOT

RESERVE_USD = float(os.getenv("BUDGET_RESERVE_USD", "0.20"))  # always left untouched
SAFETY = 1.5  # estimates are rough; allow 50% over


class BudgetError(RuntimeError):
    pass


def remaining_usd() -> float:
    req = urllib.request.Request(
        os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/") + "/credits",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https endpoint
        d = json.load(r)["data"]
    return float(d["total_credits"]) - float(d["total_usage"])


def estimate_from_history(prefix: str, n_runs: int, default_per_run: float) -> float:
    """Mean recorded cost per run (system plus judge) of the latest results file whose name starts with `prefix`."""
    files = sorted((ROOT / "eval" / "results").glob(f"{prefix}*_dev.json"))
    for f in reversed(files):
        d = json.loads(f.read_text())
        runs = d.get("n_runs") or len(d.get("runs", []))
        if runs and d.get("cost_usd"):
            per = (d["cost_usd"]["total"] + (d.get("judge") or {}).get("cost_usd", 0.0)) / runs
            return per * n_runs
    return default_per_run * n_runs


def check(estimated_usd: float, label: str, remaining: float | None = None) -> float:
    """Raise BudgetError unless the run fits. Returns the remaining balance."""
    left = remaining_usd() if remaining is None else remaining
    need = estimated_usd * SAFETY + RESERVE_USD
    if left < need:
        raise BudgetError(
            f"{label}: estimated ${estimated_usd:.2f} (x{SAFETY} margin + ${RESERVE_USD:.2f} reserve = ${need:.2f}) "
            f"but only ${left:.2f} of credit is left. Not started. Use a smaller run, or --skip-budget-check to override."  # noqa: E501
        )
    return left
