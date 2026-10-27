"""Render the Step 4 section of docs/EVAL_REPORT.md from eval/results/*.json (no hand-copied numbers)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = {c: json.loads((ROOT / "eval" / "results" / f"{c}_dev.json").read_text()) for c in ("E0", "B0", "B2", "B1")}


def m(cid: str, key: str, nd: int = 2) -> str:
    v = R[cid]["overall"].get(key)
    return "n/a" if v is None else f"{v['mean']:.{nd}f}"


def n(cid: str, key: str) -> str:
    v = R[cid]["overall"].get(key)
    return "" if v is None else str(v["n"])


def by_type(cid: str, key: str, t: str) -> str:
    v = R[cid]["by_case_type"].get(t, {}).get(key)
    return "n/a" if v is None else f"{v['mean']:.2f}"


def row(label: str, key: str, cids=("B0", "B1", "B2")) -> str:
    cell = lambda c: "n/a" if n(c, key) == "" else f"{m(c, key)} ({n(c, key)})"  # noqa: E731
    return f"| {label} | " + " | ".join(cell(c) for c in cids) + " |"


meta = R["B1"]["metadata"]
lines = [
    "## 2. Baselines (Step 4, `dev` split)",
    "",
    f"Run on {meta['dataset_version']} of the datasets, corpus fingerprint `{meta['corpus_chunks_sha256_12']}`, pricing retrieved "
    f"{meta['pricing_retrieved_at']}. Code state when run: commit `{meta['git_sha']}`"
    + (
        " **plus uncommitted changes** (re-run after committing to tie results to a commit)."
        if meta["git_dirty"]
        else "."
    ),
    "",
    "### 2.1 Configurations",
    "",
    "| Id | What | Dataset (dev) | Runs |",
    "|---|---|---|---|",
    f"| E0 | BM25 over structure-aware chunks (C2), no LLM; retrieval metrics only | `policy-retrieval-v1` | {R['E0']['n_runs']} |",
    f"| B0 | BM25's best passage returned verbatim as the answer; never abstains | `policy-eval-v1` | {R['B0']['n_runs']} |",
    f"| B1 | Single-pass RAG: dense top-5 (`{meta['embedding']}`), one prompt (`{meta['prompt']}`), model `{meta['model']}`, temperature 0, "
    f"structured output, no tools | `policy-eval-v1` | {R['B1']['n_runs']} (21 cases x 3 repetitions) |",
    f"| B2 | Rule-based lookup in the statistics store; cannot read prose or compute | `policy-eval-v1` | {R['B2']['n_runs']} |",
    "",
    "### 2.2 Results",
    "",
    "Mean (number of scored runs). A metric counts only the runs where it applies, so the counts differ.",
    "",
    "| Metric | B0 | B1 | B2 |",
    "|---|---|---|---|",
    row("status_match", "status_match"),
    row("numeric_exact", "numeric_exact"),
    row("must_contain_numbers", "must_contain_numbers"),
    row("citation_exists", "citation_exists"),
    row("citation_correct", "citation_correct"),
    row("injection_followed (lower is better)", "injection_followed"),
    row("schema_valid", "schema_valid"),
    row("hit@5 (answer-bearing chunk in top 5)", "hit_at_5"),
    row("recall@5", "recall_at_5"),
    row("MRR@10", "mrr_at_10"),
    row("nDCG@10", "ndcg_at_10"),
    f"| latency p50 / p95 (ms) | {R['B0']['latency_ms']['p50']} / {R['B0']['latency_ms']['p95']} | {R['B1']['latency_ms']['p50']:.0f} / "
    f"{R['B1']['latency_ms']['p95']:.0f} | {R['B2']['latency_ms']['p50']} / {R['B2']['latency_ms']['p95']} |",
    f"| est. cost per run (USD) | {R['B0']['cost_usd']['mean_per_run']} | {R['B1']['cost_usd']['mean_per_run']} | {R['B2']['cost_usd']['mean_per_run']} |",
    "",
    f"E0 (retrieval dataset, 15 questions with gold evidence): hit@5 {m('E0', 'hit_at_5')}, recall@5 {m('E0', 'recall_at_5')}, "
    f"MRR@10 {m('E0', 'mrr_at_10')}, nDCG@10 {m('E0', 'ndcg_at_10')}. PRD targets for the final system: recall@5 at least 0.85, "
    "MRR@10 at least 0.70.",
    "",
    "`status_match` by case type:",
    "",
    "| Case type | B0 | B1 | B2 |",
    "|---|---|---|---|",
]
types = ["factual", "multi_step", "calculation", "unanswerable", "ambiguous", "conflicting", "adversarial"]
for t in types:
    lines.append(f"| {t} | " + " | ".join(by_type(c, "status_match", t) for c in ("B0", "B1", "B2")) + " |")
lines += [
    "",
    "Experiments in LangSmith: "
    + ", ".join(f"[{c}]({R[c]['url']}) (`{R[c]['experiment']}`)" for c in ("E0", "B0", "B1", "B2"))
    + ".",
    "",
]
section = "\n".join(lines)

path = ROOT / "docs" / "EVAL_REPORT.md"
text = path.read_text() if path.exists() else ""
marker_start, marker_end = "<!-- baselines:start -->", "<!-- baselines:end -->"
block = f"{marker_start}\n{section}\n{marker_end}"
if marker_start in text:
    text = re.sub(re.escape(marker_start) + r".*?" + re.escape(marker_end), lambda _: block, text, flags=re.S)
else:
    text += ("\n" if text else "") + block + "\n"
path.write_text(text)
print("updated", path.relative_to(ROOT))
