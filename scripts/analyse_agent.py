"""Agent against chain on the dev split (hypothesis H3), paired by case, split into the groups H3 names: multi-step and
calculation (where an agent should win) and the rest (where it must not lose). Three systems with the same model and retriever:
chain E6, agent with a router E7, simplified agent E8 (the final design).

Usage: python scripts/analyse_agent.py [--write]   (--write refreshes the block in docs/EVAL_REPORT.md)"""

import argparse
import importlib.util
import re
from collections import Counter

import numpy as np

from policy_agent.ingest.paths import ROOT

_spec = importlib.util.spec_from_file_location("analyse_generation", ROOT / "scripts" / "analyse_generation.py")
ag = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(ag)  # type: ignore[union-attr]

START, END = "<!-- agent:start -->", "<!-- agent:end -->"
HARD = {"multi_step", "calculation"}
METRICS = ["status_match", "numeric_exact", "citation_correct", "groundedness", "schema_valid"]


def cell(res: dict, metric: str, ids: set[str]) -> str:
    d = {c: v for c, v in ag.per_case(res, metric).items() if c in ids}
    if len(d) < 2:
        return "n/a"
    m, lo, hi, n = ag.boot(d)
    return f"{m:.2f} [{lo:.2f}, {hi:.2f}] (n={n})"


def diff(a: dict, b: dict, metric: str, ids: set[str]) -> str:
    x = {c: v for c, v in ag.per_case(a, metric).items() if c in ids}
    y = {c: v for c, v in ag.per_case(b, metric).items() if c in ids}
    if len(x) < 2 or len(y) < 2:
        return "n/a"
    d, lo, hi, _ = ag.boot(x, y)
    return f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]"


def build() -> str:
    chain, router, simple = ag.load("E6"), ag.load("E7"), ag.load("E8")
    types = {r["case_id"]: r["case_type"] for r in simple["runs"]}
    hard = {c for c, t in types.items() if t in HARD}
    groups = (
        ("Multi-step and calculation", hard),
        ("All other case types", set(types) - hard),
        ("All cases", set(types)),
    )
    L = [f"Dev split, 21 cases x 3 repetitions, model `{simple['config']['params']['model']}` and retriever R5 in all three systems. Cells: mean over "
         "cases [95% bootstrap CI]; differences use the same resampled cases. E6 is the fixed chain, E7 the agent with a separate router step "
         "(first design), E8 the simplified agent without it (final design).", ""]  # fmt: skip
    for label, ids in groups:
        L += [f"**{label}** ({len(ids)} cases)", "", "| Metric | Chain E6 | Agent E7 (router) | Agent E8 (simplified) | E8 - E6 | E8 - E7 |", "|---|---|---|---|---|---|"]  # fmt: skip
        for m in METRICS:
            L.append(f"| {m} | {cell(chain, m, ids)} | {cell(router, m, ids)} | {cell(simple, m, ids)} | {diff(chain, simple, m, ids)} | {diff(router, simple, m, ids)} |")  # fmt: skip
        L.append("")
    L += ["| | Chain E6 | Agent E7 | Agent E8 |", "|---|---|---|---|",
          "| latency p50 / p95 (s) | " + " | ".join(f"{r['latency_ms']['p50'] / 1000:.1f} / {r['latency_ms']['p95'] / 1000:.1f}" for r in (chain, router, simple)) + " |",  # noqa: E501
          "| cost per run (USD) | " + " | ".join(f"{r['cost_usd']['mean_per_run']:.4f}" for r in (chain, router, simple)) + " |"]  # fmt: skip
    for name, res in (("E7", router), ("E8", simple)):
        runs = [r["output"]["agent"] for r in res["runs"] if r.get("output") and r["output"].get("agent")]
        calls = np.array([r["llm_calls"] for r in runs])
        L += ["", f"{name}: {calls.mean():.1f} model calls per run on average; tools used: "
              + ", ".join(f"{k} x{v}" for k, v in Counter(t for r in runs for t in r["tools"]).most_common())
              + "; stop reasons: " + ", ".join(f"{k} x{v}" for k, v in Counter(str(r["stop_reason"]).split(" (")[0] for r in runs).most_common(5)) + "."]  # fmt: skip
    L += [
        "",
        "`status_match` by case type (mean over runs):",
        "",
        "| Case type | Chain E6 | Agent E7 | Agent E8 |",
        "|---|---|---|---|",
    ]
    for t in sorted(simple["by_case_type"]):
        v = [
            r["by_case_type"].get(t, {}).get("status_match", {}).get("mean", float("nan"))
            for r in (chain, router, simple)
        ]
        L.append(f"| {t} | {v[0]:.2f} | {v[1]:.2f} | {v[2]:.2f} |")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    text = build()
    if ap.parse_args().write:
        p = ROOT / "docs" / "EVAL_REPORT.md"
        s = p.read_text()
        assert START in s and END in s, "markers missing in docs/EVAL_REPORT.md"
        p.write_text(re.sub(f"{START}.*?{END}", lambda _: f"{START}\n{text}\n{END}", s, flags=re.S))
        print("updated docs/EVAL_REPORT.md")
    else:
        print(text)


if __name__ == "__main__":
    main()
