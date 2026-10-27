"""Re-score saved experiment outputs under corrected labels without touching the originals (eval/README.md, items 5 and 7).

For each experiment, the runs on the cases whose labels changed (F05, K02 in v1.1) are scored again from the saved answers
against the corrected reference. Label-dependent metrics are recomputed; everything else (groundedness, relevance, schema
validity, latency, cost) carries over because the answers are the same. Output: eval/results/<ID>_dev.rescored-v1.1.json.
Nothing is re-run, so these are not new samples. Then --write refreshes the block in docs/EVAL_REPORT.md.

Usage: python scripts/rescore_labels.py [--write]
"""

import argparse
import importlib.util
import json
import re
import sys

from dotenv import load_dotenv

from policy_agent.eval import evaluators as ev
from policy_agent.eval import judges
from policy_agent.generation.schema import Answer
from policy_agent.ingest.paths import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import sync_datasets as sd  # noqa: E402

TAG = "v1.1"
CHANGED = ("F05", "K02")
EXPERIMENTS = ("E5", "E6", "E7")
LABEL_DEPENDENT = {"status_match", "numeric_exact", "must_contain_numbers", "must_not_contain", "injection_followed",
                   "citation_exists", "citation_correct", "recall_at_5", "hit_at_5", "mrr_at_10", "ndcg_at_10"}  # fmt: skip
START, END = "<!-- relabel:start -->", "<!-- relabel:end -->"


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def rescore(exp: str) -> dict:
    runner, ag = _load_module("run_experiment"), _load_module("analyse_generation")
    orig = json.loads((ROOT / "eval" / "results" / f"{exp}_dev.json").read_text())
    refs = {e["metadata"]["case_id"]: e["outputs"] for e in sd.eval_examples()}
    inputs = {e["metadata"]["case_id"]: e["inputs"] for e in sd.eval_examples()}
    runs = []
    for r in orig["runs"]:
        r = json.loads(json.dumps(r))
        o = r.get("output")
        if r["case_id"] in CHANGED and o and o.get("answer"):
            outputs = {"status": o["status"], "answer": o["answer"], "text": Answer.model_validate(o["answer"]).text(),
                       "citations": o["citations"], "retrieved": o.get("retrieved") or [], "error": None}  # fmt: skip
            for fn in ev.ANSWER_EVALUATORS:
                res = (
                    fn(outputs=outputs, reference_outputs=refs[r["case_id"]])
                    if fn.__name__ in LABEL_DEPENDENT
                    else None
                )
                if res:
                    r["scores"][res["key"]] = res.get("score")
            cj = judges.conflict_handling(inputs[r["case_id"]], outputs, refs[r["case_id"]])
            r["scores"]["conflict_handling"] = cj.get("score")
            r["rescored"] = True
        runs.append(r)
    agg = runner.aggregate(runs)
    out = {"experiment": orig["experiment"], "labels_version": TAG, "original_file": f"{exp}_dev.json", "changed_cases": list(CHANGED),
           "note": "Saved outputs re-scored under corrected labels; not new runs.", "config": orig["config"], "metadata": orig["metadata"],
           **{k: agg[k] for k in ("n_runs", "overall", "by_case_type")}, "latency_ms": orig["latency_ms"], "cost_usd": orig["cost_usd"],
           "runs": runs}  # fmt: skip
    (ROOT / "eval" / "results" / f"{exp}_dev.rescored-{TAG}.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, default=str) + "\n"
    )
    return {"orig": orig, "new": out, "ag": ag}


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def build() -> str:
    res = {e: rescore(e) for e in EXPERIMENTS}
    ag = res["E5"]["ag"]
    L = [f"Corrected labels ({TAG}): F05 and K02 now expect `conflict_reported` (preliminary 4,500 against later 4,620); no other case changed. "
         "The E5, E6 and E7 outputs saved on `dev` were scored again against the corrected reference. **These are the same 63 runs per "
         "experiment, not new samples**, and the original files are untouched. Only label-dependent metrics changed; the model's answers did not.", "",
         "| Metric (mean over runs) | E5 orig | E5 corrected | E6 orig | E6 corrected | E7 orig | E7 corrected |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for m in (
        "status_match",
        "numeric_exact",
        "must_contain_numbers",
        "citation_correct",
        "recall_at_5",
        "conflict_handling",
    ):
        cells = []
        for e in EXPERIMENTS:
            cells += [
                pct(res[e]["orig"]["overall"].get(m, {}).get("mean")),
                pct(res[e]["new"]["overall"].get(m, {}).get("mean")),
            ]
        L.append(f"| {m} | " + " | ".join(cells) + " |")
    L += ["", "The two changed cases, `status_match` over the 3 runs each:", "", "| Case | E5 orig / corrected | E6 orig / corrected | E7 orig / corrected |", "|---|---|---|---|"]  # fmt: skip
    for c in CHANGED:
        cells = []
        for e in EXPERIMENTS:

            def mean(r, c=c):
                v = [x["scores"]["status_match"] for x in r["runs"] if x["case_id"] == c]
                return sum(v) / len(v)

            cells.append(f"{mean(res[e]['orig']):.2f} / {mean(res[e]['new']):.2f}")
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    L += ["", "Agent (E7) against chain (E6) under the corrected labels, case-level bootstrap as in section 5:", "",
          "| Metric | E6 | E7 | E7 - E6 [95% CI] |", "|---|---|---|---|"]  # fmt: skip
    for m in ("status_match", "numeric_exact", "citation_correct", "conflict_handling"):
        a, b = ag.per_case(res["E6"]["new"], m), ag.per_case(res["E7"]["new"], m)
        if len(a) < 2 or len(b) < 2:
            continue
        pa, la, ha, na = ag.boot(a)
        pb, lb, hb, nb = ag.boot(b)
        d, ld, hd, _ = ag.boot(a, b)
        L.append(
            f"| {m} | {pa:.2f} [{la:.2f}, {ha:.2f}] (n={na}) | {pb:.2f} [{lb:.2f}, {hb:.2f}] (n={nb}) | {d:+.2f} [{ld:+.2f}, {hd:+.2f}] |"
        )
    hard = {
        c
        for c, t in {r["case_id"]: r["case_type"] for r in res["E7"]["new"]["runs"]}.items()
        if t in ("multi_step", "calculation")
    }
    for label, ids in (
        ("multi-step and calculation", hard),
        ("all other", set(ag.per_case(res["E7"]["new"], "status_match")) - hard),
    ):
        a = {c: v for c, v in ag.per_case(res["E6"]["new"], "status_match").items() if c in ids}
        b = {c: v for c, v in ag.per_case(res["E7"]["new"], "status_match").items() if c in ids}
        d, ld, hd, n = ag.boot(a, b)
        L.append(
            f"| status_match, {label} ({n} cases) | {sum(a.values()) / len(a):.2f} | {sum(b.values()) / len(b):.2f} | {d:+.2f} [{ld:+.2f}, {hd:+.2f}] |"
        )
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    write = ap.parse_args().write
    load_dotenv(ROOT / ".env")
    text = build()
    if write:
        p = ROOT / "docs" / "EVAL_REPORT.md"
        s = p.read_text()
        assert START in s and END in s, "markers missing in docs/EVAL_REPORT.md"
        p.write_text(re.sub(f"{START}.*?{END}", lambda _: f"{START}\n{text}\n{END}", s, flags=re.S))
        print("updated docs/EVAL_REPORT.md")
    print(text)


if __name__ == "__main__":
    main()
