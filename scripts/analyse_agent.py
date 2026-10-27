"""Step 8 analysis (H3): the agent (E7) against the chain with the same model (E6), paired by case, split into the case
groups H3 names: multi-step and calculation (where the agent should win) and the rest (where it must not lose).

Usage: python scripts/analyse_agent.py [--write]   (--write refreshes the block in docs/EVAL_REPORT.md)
"""

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
METRICS = [
    "status_match",
    "numeric_exact",
    "must_contain_numbers",
    "citation_correct",
    "groundedness",
    "answer_relevance",
    "schema_valid",
]


def case_types(res: dict) -> dict[str, str]:
    return {r["case_id"]: r["case_type"] for r in res["runs"]}


def table(chain: dict, agent: dict, ids: set[str], label: str) -> list[str]:
    L = [
        f"**{label}** ({len(ids)} cases)",
        "",
        "| Metric | Chain (E6) | Agent (E7) | Agent - chain [95% CI] |",
        "|---|---|---|---|",
    ]
    for m in METRICS:
        a = {c: v for c, v in ag.per_case(chain, m).items() if c in ids}
        b = {c: v for c, v in ag.per_case(agent, m).items() if c in ids}
        if len(a) < 2 or len(b) < 2:
            continue
        pa, la, ha, na = ag.boot(a)
        pb, lb, hb, nb = ag.boot(b)
        d, ld, hd, nd = ag.boot(a, b)
        L.append(
            f"| {m} | {pa:.2f} [{la:.2f}, {ha:.2f}] (n={na}) | {pb:.2f} [{lb:.2f}, {hb:.2f}] (n={nb}) | {d:+.2f} [{ld:+.2f}, {hd:+.2f}] |"
        )
    return L + [""]


def build() -> str:
    chain, agent = ag.load("E6"), ag.load("E7")
    types = case_types(agent)
    hard = {c for c, t in types.items() if t in HARD}
    simple = set(types) - hard
    L = [
        f"Dev split, 21 cases x 3 repetitions. Chain = E6 (`{chain['config']['params']['model']}`, fixed pipeline); agent = E7 (same model, same retriever, "
        f"judge `{agent['metadata'].get('judge_model')}`). Cells: mean over cases [95% bootstrap CI]; the difference uses the same resampled cases for both.",
        "",
    ]
    L += table(chain, agent, hard, "Multi-step and calculation") + table(chain, agent, simple, "All other case types")
    L += table(chain, agent, set(types), "All cases")
    L += ["| | Chain (E6) | Agent (E7) |", "|---|---|---|"]
    for name, f in (("latency p50 / p95 (s)", lambda r: f"{r['latency_ms']['p50'] / 1000:.1f} / {r['latency_ms']['p95'] / 1000:.1f}"),
                    ("cost per run (USD)", lambda r: f"{r['cost_usd']['mean_per_run']:.4f}")):  # fmt: skip
        L.append(f"| {name} | {f(chain)} | {f(agent)} |")
    runs = [r["output"]["agent"] for r in agent["runs"] if r.get("output") and r["output"].get("agent")]
    calls = np.array([r["llm_calls"] for r in runs]) if runs else np.array([0])
    steps = Counter(r["steps"] for r in runs)
    L += [f"| model calls per run (mean) | 1 to 2 | {calls.mean():.1f} |", "",
          "Tool use in the 63 agent runs: " + ", ".join(f"{k} x{v}" for k, v in Counter(t for r in runs for t in r["tools"]).most_common()) + ".",
          "Tool rounds per run: " + ", ".join(f"{k}: {v}" for k, v in sorted(steps.items())) + ".",
          "Stop reasons: " + ", ".join(f"{k} x{v}" for k, v in Counter(str(r["stop_reason"]).split(" (")[0] for r in runs).most_common(6)) + ".", "",
          "`status_match` by case type (mean over runs):", "", "| Case type | Chain (E6) | Agent (E7) |", "|---|---|---|"]  # fmt: skip
    for t in sorted(agent["by_case_type"]):
        va, vb = (
            res["by_case_type"].get(t, {}).get("status_match", {}).get("mean", float("nan")) for res in (chain, agent)
        )
        L.append(f"| {t} | {va:.2f} | {vb:.2f} |")
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
