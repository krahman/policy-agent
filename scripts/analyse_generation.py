"""Step 6 analysis: E5 (model A) vs E6 (model B) with case-level bootstrap CIs (repetitions averaged within a case, cases
resampled together for both systems), the H2 groundedness ratio, validation statistics and cost/latency.

Usage: python scripts/analyse_generation.py [--write]   (--write refreshes the block in docs/EVAL_REPORT.md)
"""

import argparse
import json
import re
from collections import Counter, defaultdict

import numpy as np

from policy_agent.ingest.paths import ROOT

SEED, N_BOOT = 20261027, 10_000
START, END = "<!-- generation:start -->", "<!-- generation:end -->"
METRICS = ["status_match", "numeric_exact", "must_contain_numbers", "groundedness", "answer_relevance", "citation_exists",
           "citation_correct", "conflict_handling", "injection_followed", "schema_valid"]  # fmt: skip


def load(cid: str) -> dict:
    return json.loads((ROOT / "eval" / "results" / f"{cid}_dev.json").read_text())


def per_case(res: dict, metric: str) -> dict[str, float]:
    """Mean over repetitions, one value per case; cases where the metric does not apply are absent."""
    acc = defaultdict(list)
    for r in res["runs"]:
        v = r["scores"].get(metric)
        if isinstance(v, int | float):
            acc[r["case_id"]].append(float(v))
    return {c: float(np.mean(v)) for c, v in acc.items()}


def boot(a: dict, b: dict | None = None, ratio: bool = False):
    cases = sorted(set(a) & set(b)) if b is not None else sorted(a)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(cases), size=(N_BOOT, len(cases)))
    x = np.array([a[c] for c in cases])
    if b is None:
        m = x[idx].mean(axis=1)
        return float(x.mean()), np.percentile(m, 2.5), np.percentile(m, 97.5), len(cases)
    y = np.array([b[c] for c in cases])
    if ratio:
        stat = y[idx].mean(axis=1) / np.where(x[idx].mean(axis=1) == 0, np.nan, x[idx].mean(axis=1))
        pt = y.mean() / x.mean() if x.mean() else float("nan")
    else:
        stat, pt = (y[idx] - x[idx]).mean(axis=1), float((y - x).mean())
    return pt, np.nanpercentile(stat, 2.5), np.nanpercentile(stat, 97.5), len(cases)


def build() -> str:
    ra, rb = load("E5"), load("E6")
    ma, mb = ra["config"]["params"]["model"], rb["config"]["params"]["model"]
    L = [f"Dev split, 21 cases x 3 repetitions. A = `{ma}`, B = `{mb}`. Both use R5 retrieval (voyage-4), prompt "
         f"`{ra['metadata']['prompt']}`, V1-V6 with one repair. Judge: `{ra['metadata'].get('judge_model')}` "
         f"(prompt {ra['metadata'].get('judge_prompt_sha256_12')}). Cells: mean over cases [95% bootstrap CI], n = cases where the metric applies.", "",
         "| Metric | A | B | B - A [95% CI] |", "|---|---|---|---|"]  # fmt: skip
    for m in METRICS:
        a, b = per_case(ra, m), per_case(rb, m)
        if not a or not b:
            continue
        pa, la, ha, na = boot(a)
        pb, lb, hb, nb = boot(b)
        d, ld, hd, nd = boot(a, b)
        L.append(
            f"| {m} | {pa:.2f} [{la:.2f}, {ha:.2f}] (n={na}) | {pb:.2f} [{lb:.2f}, {hb:.2f}] (n={nb}) | {d:+.2f} [{ld:+.2f}, {hd:+.2f}] |"
        )
    ga, gb = per_case(ra, "groundedness"), per_case(rb, "groundedness")
    if ga and gb:
        r, lo, hi, n = boot(ga, gb, ratio=True)
        L += ["", f"**H2 test:** groundedness B/A = {r:.2f} [{lo:.2f}, {hi:.2f}] over {n} cases that both answered. "
              "H2 holds if the ratio is at least 0.90 (the interval's lower end is the safer reading)."]  # fmt: skip
    L += ["", "| | A | B |", "|---|---|---|"]
    for name, f in (("latency p50 / p95 (s)", lambda r: f"{r['latency_ms']['p50'] / 1000:.1f} / {r['latency_ms']['p95'] / 1000:.1f}"),
                    ("cost per run (USD, retrieval + generation)", lambda r: f"{r['cost_usd']['mean_per_run']:.4f}"),
                    ("judge cost for the experiment (USD)", lambda r: f"{r.get('judge', {}).get('cost_usd', 0):.3f}")):  # fmt: skip
        L.append(f"| {name} | {f(ra)} | {f(rb)} |")
    L += ["", "Output validation on the first pass (all 63 runs per model):", "", "| | A | B |", "|---|---|---|"]
    stats = {}
    for tag, res in (("A", ra), ("B", rb)):
        v = [r["output"]["validation"] for r in res["runs"] if r.get("output")]
        rules = Counter(x.split(":")[0] for d in v for x in d["first_pass"])
        stats[tag] = {"n": len(v), "any": sum(bool(d["first_pass"]) for d in v), "repaired": sum(d["repaired"] for d in v),
                      "down": sum(d["downgraded"] for d in v), "rules": rules}  # fmt: skip
    for label, key in (("runs with at least one violation", "any"), ("repaired by the single retry", "repaired"),
                       ("downgraded to abstained after the retry", "down")):  # fmt: skip
        L.append(f"| {label} | {stats['A'][key]} / {stats['A']['n']} | {stats['B'][key]} / {stats['B']['n']} |")
    for rule in sorted(set(stats["A"]["rules"]) | set(stats["B"]["rules"])):
        L.append(f"| first-pass violations of {rule} | {stats['A']['rules'][rule]} | {stats['B']['rules'][rule]} |")
    L += ["", "`status_match` by case type (mean over runs):", "", "| Case type | A | B |", "|---|---|---|"]
    for t in sorted(ra["by_case_type"]):
        va, vb = (res["by_case_type"].get(t, {}).get("status_match", {}).get("mean", float("nan")) for res in (ra, rb))
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
