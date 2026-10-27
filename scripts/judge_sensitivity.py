"""Automatic sensitivity check for the groundedness judge (no human needed): alter one number in every numeric claim of
E5/E6 and see whether the judge notices. A judge that still says "supported" is blind to wrong numbers.

Usage: python scripts/judge_sensitivity.py
"""

import json

from dotenv import load_dotenv

from policy_agent.eval import judges
from policy_agent.eval.judges import perturb
from policy_agent.ingest.paths import ROOT


def main() -> None:
    load_dotenv(ROOT / ".env")
    orig_ok, alt_rejected, n = 0, 0, 0
    misses = []
    for exp in ("E5", "E6"):
        res = json.loads((ROOT / "eval" / "results" / f"{exp}_dev.json").read_text())
        seen = set()
        for r in res["runs"]:
            out = r.get("output")
            if not out or out["status"] not in ("answered", "conflict_reported") or r["case_id"] in seen:
                continue
            seen.add(r["case_id"])
            for cl in out["answer"]["claims"]:
                alt = perturb(cl["text"]) if cl["kind"] != "model_inference" else None
                if not alt:
                    continue
                v0, v1 = judges.judge_claims([cl])[0], judges.judge_claims([{**cl, "text": alt}])[0]
                n += 1
                orig_ok += v0.supported
                alt_rejected += not v1.supported
                if v1.supported:
                    misses.append((exp, r["case_id"], cl["text"][:70], alt[:70]))
    res = {"claims_tested": n, "originals_judged_supported": orig_ok, "altered_judged_unsupported": alt_rejected,
           "judge_model": judges.JUDGE_MODEL, "missed_examples": misses[:6]}  # fmt: skip
    (ROOT / "eval" / "calibration").mkdir(exist_ok=True)
    (ROOT / "eval" / "calibration" / "sensitivity.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
