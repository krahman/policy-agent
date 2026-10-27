"""Retrieval comparison: Recall@5, hit@5, MRR@10 and nDCG@10 per retriever with 95% bootstrap CIs over questions, and the paired
difference against BM25, on the dev split and again on the held-out test split. Reads eval/results/E*_dev.json and E*T_test.json.

Usage: python scripts/analyse_retrieval.py [--write]   (--write refreshes the block in docs/EVAL_REPORT.md)"""

import argparse
import json
import re

import numpy as np

from policy_agent.ingest.paths import ROOT

SEED, N_BOOT = 20261027, 10_000
METRICS = ["recall_at_5", "hit_at_5", "mrr_at_10", "ndcg_at_10"]
SYSTEMS = [("E1", "BM25 (R1)"), ("E2b", "Dense, voyage-4 (R2)"), ("E4b", "Hybrid + re-rank (R4)"),
           ("E4d", "Hybrid + re-rank + period filter (R5, chosen)")]  # fmt: skip
START, END = "<!-- retrieval:start -->", "<!-- retrieval:end -->"


def load(split: str) -> dict[str, dict]:
    out = {}
    for cid, _ in SYSTEMS:
        f = ROOT / "eval" / "results" / (f"{cid}_dev.json" if split == "dev" else f"{cid}T_test.json")
        if f.exists():
            d = json.loads(f.read_text())
            out[cid] = {r["case_id"]: r["scores"] for r in d["runs"]} | {"_meta": d}
    return out


def ci(x: np.ndarray, idx: np.ndarray) -> tuple[float, float, float]:
    means = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def table(split: str) -> list[str]:
    res = load(split)
    cases = sorted(k for k in res["E1"] if k != "_meta")
    idx = np.random.default_rng(SEED).integers(0, len(cases), size=(N_BOOT, len(cases)))  # same resamples: paired
    vec = lambda cid, m: np.array([res[cid][c][m] for c in cases], dtype=float)  # noqa: E731
    L = [f"**{split} split**, {len(cases)} questions with gold evidence. Cell = mean [95% CI]; the last two columns are the paired difference "
         "against BM25 (a difference is only worth reading if its interval excludes 0).", "",
         "| System | Recall@5 | Hit@5 | MRR@10 | nDCG@10 | Δ Recall@5 vs BM25 | Δ MRR@10 vs BM25 |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for cid, label in SYSTEMS:
        if cid not in res:
            continue
        cells = [f"{m:.2f} [{lo:.2f}, {hi:.2f}]" for m_ in METRICS for m, lo, hi in [ci(vec(cid, m_), idx)]]
        d = [ci(vec(cid, m_) - vec("E1", m_), idx) for m_ in ("recall_at_5", "mrr_at_10")]
        dc = ["" if cid == "E1" else f"{m:+.2f} [{lo:+.2f}, {hi:+.2f}]" for m, lo, hi in d]
        L.append(f"| {label} | " + " | ".join(cells) + " | " + " | ".join(dc) + " |")
    return L + [""]


def build() -> str:
    return "\n".join(table("dev") + table("test"))


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
