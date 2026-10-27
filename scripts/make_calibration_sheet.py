"""Build the blind human-labelling sheet used to calibrate the LLM judges (PRD §11.3, Step 6).

Picks 10 `dev` answers from an experiment result file (first repetition of each case), shows the question, the
answer's claims and the full text of the chunks each claim cites, and leaves the judgements to the human.
Judge verdicts are NOT shown in the sheet; they are stored in eval/calibration/items.json for scripts/calibrate_judge.py.

Usage: python scripts/make_calibration_sheet.py [E5]
"""

import json
import random
import sys

from dotenv import load_dotenv

from policy_agent.eval import judges
from policy_agent.eval.judges import perturb
from policy_agent.ingest.paths import ROOT
from policy_agent.retrieval.corpus import load_chunks

SEED = 20261027
N_ITEMS = 10
OUT = ROOT / "eval" / "CALIBRATION.md"
ITEMS = ROOT / "eval" / "calibration" / "items.json"
MAX_EV = 700
N_PERTURBED = 4  # altered copies of real claims, mixed in blind, so the sheet contains known-bad claims too


def main() -> None:
    load_dotenv(ROOT / ".env")
    exp = sys.argv[1] if len(sys.argv) > 1 else "E5"
    res = json.loads((ROOT / "eval" / "results" / f"{exp}_dev.json").read_text())
    cases = {c["id"]: c for c in map(json.loads, (ROOT / "eval/data/eval_cases.jsonl").read_text().splitlines())}
    first: dict[str, dict] = {}
    for r in res["runs"]:
        first.setdefault(r["case_id"], r)
    pool = [r for r in first.values() if r.get("output") and r["output"]["answer"]["claims"]
            and r["output"]["status"] in ("answered", "conflict_reported")]  # fmt: skip
    rng = random.Random(SEED)
    rng.shuffle(pool)
    flagged = []  # make sure the sample is not all easy: include answers where the judge found something unsupported
    for r in pool:
        v = judges.judge_claims(r["output"]["answer"]["claims"])
        flagged.append(any(not x.supported for x in v))
    order = [r for r, f in zip(pool, flagged, strict=True) if f][:4] + [
        r for r, f in zip(pool, flagged, strict=True) if not f
    ]
    picked = sorted({r["case_id"]: r for r in order[:N_ITEMS]}.values(), key=lambda r: r["case_id"])
    by_id = {c["chunk_id"]: c for c in load_chunks()}
    # add altered copies to a few answers (decided here, before any labelling; recorded in items.json)
    n_pert = 0
    for r in picked:
        claims = r["output"]["answer"]["claims"]
        for cl in list(claims):
            alt = perturb(cl["text"]) if n_pert < N_PERTURBED and cl["kind"] != "model_inference" else None
            if alt:
                claims.append({**cl, "text": alt, "perturbed": True})
                n_pert += 1
                break

    lines = [
        "# Judge calibration sheet (blind)", "",
        f"Answers from experiment {exp}. Your labels decide whether the LLM judge's scores can be trusted, so please do",
        "this yourself and tick one box per item; leave a box empty if you cannot tell. The judge's verdicts are hidden on purpose.", "",
        "**For each claim:** is it supported by the evidence shown under it? Check the measure (overall / resident / citizen;",
        "seasonally adjusted or not), the period, and the number. Simple correct arithmetic on numbers in the evidence counts as supported.", "",
        "**For each answer:** how well does it respond to the question? 5 = directly answers (or correctly explains why it cannot,",
        "or asks a precise clarifying question); 3 = partly; 1 = does not address it. Judge responsiveness, not whether you know the number is true.", "",
    ]  # fmt: skip
    items = []
    for n, r in enumerate(picked, 1):
        case, out = cases[r["case_id"]], r["output"]
        item = f"{n:02d}-{r['case_id']}"
        lines += ["---", "", f"## Item {n}: {r['case_id']}", "", f"**Question:** {case['question']}", "",
                  f"**Answer status:** {out['status']}", "", f"**Answer summary:** {out['answer']['summary']}", ""]  # fmt: skip
        verdicts = judges.judge_claims(out["answer"]["claims"])
        for k, cl in enumerate(out["answer"]["claims"], 1):
            lines += [f"### Claim {k} ({cl['kind']})", "", f"> {cl['text']}", "", "Cited evidence:", ""]
            for cid in dict.fromkeys(c["chunk_id"] for c in cl["citations"]):
                lines += (
                    [f"- `{cid}`: {by_id[cid]['text'][:MAX_EV]!r}"] if cid in by_id else [f"- `{cid}`: (unknown chunk)"]
                )
            lines += ["", f"- [ ] supported <!--g:{item}:{k}:1-->", f"- [ ] not supported <!--g:{item}:{k}:0-->", ""]
        lines += ["### Relevance of the whole answer (tick one)", ""]
        lines += [f"- [ ] {s} <!--r:{item}:{s}-->" for s in range(1, 6)] + [""]
        items.append({"item": item, "case_id": r["case_id"], "judge_claims": [v.supported for v in verdicts],
                      "n_claims": len(verdicts),
                      "perturbed": [bool(c.get("perturbed")) for c in out["answer"]["claims"]]})  # fmt: skip
        rel = judges.answer_relevance(
            {"question": case["question"]}, {"status": out["status"], "answer": out["answer"]}, {}
        )
        items[-1]["judge_relevance"] = rel.get("score")
    OUT.write_text("\n".join(lines) + "\n")
    ITEMS.parent.mkdir(exist_ok=True)
    ITEMS.write_text(json.dumps({"experiment": exp, "judge_model": judges.JUDGE_MODEL,
                                 "judge_prompt_sha256_12": judges.prompts()["sha256_12"], "items": items}, indent=1) + "\n")  # fmt: skip
    print(f"wrote {OUT.relative_to(ROOT)} ({len(items)} answers, {sum(i['n_claims'] for i in items)} claims)")


if __name__ == "__main__":
    main()
