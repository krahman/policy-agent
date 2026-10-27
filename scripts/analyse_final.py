"""Step 10 analysis: frozen agent against the chain on the held-out split, with CIs, paired tests, strata and an error taxonomy.

Usage: python scripts/analyse_final.py [--agent E7T --chain E6T --split test] [--write]
Dry run on development data: python scripts/analyse_final.py --agent E7b --chain E6 --split dev
--write refreshes the block in docs/EVAL_REPORT.md (only meaningful for the test split)."""

import argparse
import importlib.util
import itertools
import json
import math
import re
from collections import Counter, defaultdict

import numpy as np

from policy_agent.eval.checks import load
from policy_agent.eval.models import EvalCase
from policy_agent.ingest.paths import ROOT

_spec = importlib.util.spec_from_file_location("analyse_generation", ROOT / "scripts" / "analyse_generation.py")
ag = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(ag)  # type: ignore[union-attr]

START, END = "<!-- final:start -->", "<!-- final:end -->"
METRICS = ["status_match", "numeric_exact", "must_contain_numbers", "citation_correct", "groundedness", "conflict_handling",
           "schema_valid", "injection_followed"]  # fmt: skip


def read(cid: str, split: str) -> dict:
    return json.loads((ROOT / "eval" / "results" / f"{cid}_{split}.json").read_text())


def mcnemar_exact(a: dict, b: dict) -> tuple[int, int, float]:
    """Per-case success = majority of that case's runs. Returns (a only, b only, two-sided exact p)."""
    cases = sorted(set(a) & set(b))
    n01 = sum(1 for c in cases if a[c] < 0.5 <= b[c])
    n10 = sum(1 for c in cases if b[c] < 0.5 <= a[c])
    n = n01 + n10
    if n == 0:
        return n10, n01, 1.0
    k = min(n01, n10)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)
    return n10, n01, p


def signed_rank_exact(d: np.ndarray) -> float:
    """Two-sided Wilcoxon signed-rank p by enumerating sign flips (exact for up to 20 non-zero differences)."""
    d = d[np.abs(d) > 1e-12]
    n = len(d)
    if n == 0:
        return 1.0
    if n > 20:  # normal approximation
        ranks = np.argsort(np.argsort(np.abs(d))) + 1.0
        w = ranks[d > 0].sum()
        mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
        return math.erfc(abs(w - mu) / sd / math.sqrt(2))
    order = np.argsort(np.abs(d))
    ranks = np.empty(n)
    absd = np.abs(d)[order]
    i = 0
    while i < n:  # average ranks for ties
        j = i
        while j + 1 < n and absd[j + 1] == absd[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    obs = ranks[d > 0].sum()
    mean = ranks.sum() / 2
    extreme = total = 0
    for signs in itertools.product((0, 1), repeat=n):
        w = sum(r for s, r in zip(signs, ranks, strict=True) if s)
        total += 1
        extreme += abs(w - mean) >= abs(obs - mean) - 1e-9
    return extreme / total


def taxonomy(res: dict, cases: dict[str, EvalCase]) -> tuple[Counter, dict[str, list[str]]]:
    """Why did each failed run fail? One label per run, first match wins. Failed = wrong status or wrong number."""
    kinds: Counter = Counter()
    where: dict[str, list[str]] = defaultdict(list)
    for r in res["runs"]:
        s = r["scores"]
        if s.get("status_match") != 0.0 and s.get("numeric_exact") != 0.0:
            continue
        c, out = cases[r["case_id"]], r.get("output") or {}
        got, want = out.get("status", r.get("status")), c.expected_status
        gold2 = {k for k, g in c.gold_chunk_ids.items() if g == 2}
        agent = out.get("agent") or {}
        if (out.get("validation") or {}).get("downgraded"):
            k = "validation downgrade (answer rejected by V1-V6 after one repair)"
        elif "error" in (agent.get("tool_status") or []):
            k = "tool failure"
        elif want in ("answered", "conflict_reported") and gold2 and not (gold2 & set(out.get("retrieved") or [])):
            k = "retrieval miss (no gold chunk reached the model)"
        elif want == "answered" and got == "conflict_reported":
            k = "over-reported a conflict"
        elif want == "conflict_reported" and got != "conflict_reported":
            k = "missed the expected conflict"
        elif want in ("answered", "conflict_reported") and got in ("abstained", "needs_clarification"):
            k = "abstained or asked when an answer was expected"
        elif want in ("abstained", "needs_clarification", "refused") and got != want:
            k = "answered or mis-routed when a non-answer was expected"
        elif s.get("numeric_exact") == 0.0:
            k = "wrong or missing number despite evidence"
        else:
            k = "other"
        kinds[k] += 1
        where[k].append(r["case_id"])
    return kinds, {k: sorted(set(v)) for k, v in where.items()}


def build(agent_id: str, chain_id: str, split: str) -> str:
    a, c = read(agent_id, split), read(chain_id, split)
    cases = {x.id: x for x in load("eval_cases.jsonl", EvalCase)}
    L = [f"Held-out `{split}` split, 15 cases x 3 repetitions each. Agent = {agent_id} (`{a['config']['params']['model']}`, frozen configuration, git "
         f"`{a['metadata'].get('git_sha')}`{' (dirty)' if a['metadata'].get('git_dirty') else ''}); chain = {chain_id}, same model and retriever. Judge: "
         f"`{a['metadata'].get('judge_model')}`. Labels version {a['metadata'].get('dataset_version')}. Cells: mean over cases [95% bootstrap CI].", "",
         "| Metric | Agent | Chain | Agent - chain [95% CI] | Wilcoxon p | McNemar (agent only / chain only, p) |", "|---|---|---|---|---|---|"]  # fmt: skip
    for m in METRICS:
        pa, pc = ag.per_case(a, m), ag.per_case(c, m)
        if len(pa) < 2 or len(pc) < 2:
            continue
        ma, la, ha, na = ag.boot(pa)
        mc, lc, hc, nc = ag.boot(pc)
        d, ld, hd, nd = ag.boot(pc, pa)  # agent minus chain
        both = sorted(set(pa) & set(pc))
        diffs = np.array([pa[k] - pc[k] for k in both])
        wp = signed_rank_exact(diffs)
        binary = m in ("status_match", "schema_valid", "injection_followed")
        mc_cell = "n/a"
        if binary:
            only_a, only_c, p = mcnemar_exact(pa, pc)
            mc_cell = f"{only_a} / {only_c}, p={p:.2f}"
        L.append(f"| {m} | {ma:.2f} [{la:.2f}, {ha:.2f}] (n={na}) | {mc:.2f} [{lc:.2f}, {hc:.2f}] (n={nc}) | {d:+.2f} [{ld:+.2f}, {hd:+.2f}] | {wp:.2f} | {mc_cell} |")  # fmt: skip
    L += ["", "| | Agent | Chain |", "|---|---|---|",
          f"| latency p50 / p95 (s) | {a['latency_ms']['p50'] / 1000:.1f} / {a['latency_ms']['p95'] / 1000:.1f} | {c['latency_ms']['p50'] / 1000:.1f} / {c['latency_ms']['p95'] / 1000:.1f} |",  # noqa: E501
          f"| cost per run (USD) | {a['cost_usd']['mean_per_run']:.4f} | {c['cost_usd']['mean_per_run']:.4f} |", "",
          "`status_match` and `numeric_exact` by case type (mean over runs):", "", "| Case type | Agent status | Chain status | Agent number | Chain number |", "|---|---|---|---|---|"]  # fmt: skip
    for t in sorted(a["by_case_type"]):

        def g(res, m, t=t):
            v = res["by_case_type"].get(t, {}).get(m, {}).get("mean")
            return "n/a" if v is None else f"{v:.2f}"

        L.append(
            f"| {t} | {g(a, 'status_match')} | {g(c, 'status_match')} | {g(a, 'numeric_exact')} | {g(c, 'numeric_exact')} |"
        )
    for name, res in ((f"Agent ({agent_id})", a), (f"Chain ({chain_id})", c)):
        kinds, where = taxonomy(res, cases)
        L += [
            "",
            f"**Error taxonomy, {name}** ({sum(kinds.values())} failed runs of {res['n_runs']}):",
            "",
            "| Failure mode | Runs | Cases |",
            "|---|---|---|",
        ]
        for k, v in kinds.most_common():
            L.append(f"| {k} | {v} | {', '.join(where[k])} |")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="E7T")
    ap.add_argument("--chain", default="E6T")
    ap.add_argument("--split", default="test")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    text = build(args.agent, args.chain, args.split)
    if args.write:
        p = ROOT / "docs" / "EVAL_REPORT.md"
        s = p.read_text()
        assert START in s and END in s, "markers missing in docs/EVAL_REPORT.md"
        p.write_text(re.sub(f"{START}.*?{END}", lambda _: f"{START}\n{text}\n{END}", s, flags=re.S))
        print("updated docs/EVAL_REPORT.md")
    print(text)


if __name__ == "__main__":
    main()
