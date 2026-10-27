"""Step 5 analysis: per-retriever Recall@5 / MRR@10 / nDCG@10 / hit@5 with 95% bootstrap CIs over questions, paired
bootstrap of differences against the BM25 baseline (E1), and a per-question table. Reads eval/results/E*_dev.json.

Usage: python scripts/analyse_retrieval.py [--write]   (--write refreshes the block in docs/EVAL_REPORT.md)
"""

import argparse
import json
import re
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from policy_agent.ingest.paths import ROOT  # noqa: E402

SEED = 20261027
N_BOOT = 10_000
METRICS = ["recall_at_5", "hit_at_5", "mrr_at_10", "ndcg_at_10"]
ORDER = [
    ("E1", "R1 BM25"),
    ("E2", "R2 dense (openai)"),
    ("E2b", "R2 dense (voyage-4)"),
    ("E3", "R3 hybrid (openai)"),
    ("E3b", "R3 hybrid (voyage-4)"),
    ("E4", "R4 hybrid+rerank (openai)"),
    ("E4b", "R4 hybrid+rerank (voyage-4)"),
    ("E4c", "R5 R4+period filter (openai)"),
    ("E4d", "R5 R4+period filter (voyage-4)"),
]
START, END = "<!-- retrieval:start -->", "<!-- retrieval:end -->"


def load() -> dict[str, dict]:
    out = {}
    for cid, _ in ORDER:
        f = ROOT / "eval" / "results" / f"{cid}_dev.json"
        if f.exists():
            d = json.loads(f.read_text())
            out[cid] = {r["case_id"]: r for r in d["runs"]} | {"_meta": d}
    return out


def vec(res: dict, metric: str, cases: list[str]) -> np.ndarray:
    return np.array([res[c]["scores"][metric] for c in cases], dtype=float)


def ci(x: np.ndarray, idx: np.ndarray) -> tuple[float, float, float]:
    means = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def build() -> str:
    res = load()
    cases = sorted(k for k in res["E1"] if k != "_meta")
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(cases), size=(N_BOOT, len(cases)))  # same resamples for every system => paired
    lines = [f"Dev split, {len(cases)} questions with gold evidence. 95% bootstrap CI ({N_BOOT:,} resamples of questions, "
             f"seed {SEED}). Cell = mean [low, high].", "",
             "| System | Recall@5 | Hit@5 | MRR@10 | nDCG@10 | latency p50 (ms) | cost / query |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for cid, label in ORDER:
        if cid not in res:
            continue
        cells = []
        for m in METRICS:
            mean, lo, hi = ci(vec(res[cid], m, cases), idx)
            cells.append(f"{mean:.2f} [{lo:.2f}, {hi:.2f}]")
        meta = res[cid]["_meta"]
        lines.append(f"| {cid} {label} | " + " | ".join(cells) +
                     f" | {meta['latency_ms']['p50']:.0f} | ${meta['cost_usd']['mean_per_run']:.4f} |")  # fmt: skip
    lines += ["", "Paired difference against E1 (BM25), same resamples. A difference is only worth reading if its interval "
              "excludes 0.", "", "| System | Δ Recall@5 | Δ MRR@10 | questions better / worse / tied (Recall@5) |", "|---|---|---|---|"]  # fmt: skip
    base = {m: vec(res["E1"], m, cases) for m in METRICS}
    for cid, label in ORDER[1:]:
        if cid not in res:
            continue
        d = {m: vec(res[cid], m, cases) - base[m] for m in ("recall_at_5", "mrr_at_10")}
        cells = []
        for m in ("recall_at_5", "mrr_at_10"):
            mean, lo, hi = ci(d[m], idx)
            cells.append(f"{mean:+.2f} [{lo:+.2f}, {hi:+.2f}]")
        r = d["recall_at_5"]
        lines.append(
            f"| {cid} {label} | {cells[0]} | {cells[1]} | {(r > 0).sum()} / {(r < 0).sum()} / {(r == 0).sum()} |"
        )
    lines += ["", "Does the filter (R5) add anything over R4 with the same embedding? Paired difference:", "",
              "| Comparison | Δ Recall@5 | Δ MRR@10 |", "|---|---|---|"]  # fmt: skip
    for a_, b_ in (("E4c", "E4"), ("E4d", "E4b"), ("E4b", "E2b")):
        if a_ in res and b_ in res:
            cells = []
            for m in ("recall_at_5", "mrr_at_10"):
                mean, lo, hi = ci(vec(res[a_], m, cases) - vec(res[b_], m, cases), idx)
                cells.append(f"{mean:+.2f} [{lo:+.2f}, {hi:+.2f}]")
            lines.append(f"| {a_} vs {b_} | {cells[0]} | {cells[1]} |")
    lines += ["", "Recall@5 per question (gold = grade-2 chunks in the top 5):", "",
              "| Q | " + " | ".join(c for c, _ in ORDER if c in res) + " |", "|---|" + "---|" * len([1 for c, _ in ORDER if c in res])]  # fmt: skip
    for c in cases:
        lines.append(
            f"| {c} | " + " | ".join(f"{res[k][c]['scores']['recall_at_5']:.2f}" for k, _ in ORDER if k in res) + " |"
        )
    return "\n".join(lines)


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
