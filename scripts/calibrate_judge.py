"""Compare the LLM judge with the human labels in eval/CALIBRATION.md: agreement and Cohen's kappa (PRD §11.3).

Groundedness is compared per claim (binary). Relevance is compared on the 1-5 scale (exact, within one point).
Unticked boxes are skipped, never guessed. Writes eval/calibration/result.json.

Usage: python scripts/calibrate_judge.py
"""

import json
import re

from policy_agent.ingest.paths import ROOT

SHEET = ROOT / "eval" / "CALIBRATION.md"
ITEMS = ROOT / "eval" / "calibration" / "items.json"
TRUST_KAPPA = 0.6  # conventional threshold for "substantial" agreement; with ~20 claims it is only indicative


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return None if pe == 1 else (po - pe) / (1 - pe)


def read_labels(text: str) -> tuple[dict, dict]:
    g: dict[tuple[str, int], set[int]] = {}
    r: dict[str, set[int]] = {}
    for line in text.splitlines():
        ticked = re.match(r"\s*-\s*\[[xX]\]", line)
        if m := re.search(r"<!--g:([^:]+):(\d+):([01])-->", line):
            if ticked:
                g.setdefault((m[1], int(m[2])), set()).add(int(m[3]))
        elif m := re.search(r"<!--r:([^:]+):([1-5])-->", line):
            if ticked:
                r.setdefault(m[1], set()).add(int(m[2]))
    return g, r


def main() -> None:
    meta = json.loads(ITEMS.read_text())
    g, r = read_labels(SHEET.read_text())
    gj, gh, conflicts, pert = [], [], 0, []
    for it in meta["items"]:
        for k, judged in enumerate(it["judge_claims"], 1):
            vals = g.get((it["item"], k), set())
            if len(vals) == 1:
                gj.append(int(judged))
                gh.append(next(iter(vals)))
                if it.get("perturbed", [])[k - 1 : k] == [True]:
                    pert.append((int(judged), next(iter(vals))))
            elif len(vals) > 1:
                conflicts += 1
    rj, rh = [], []
    for it in meta["items"]:
        vals = r.get(it["item"], set())
        if len(vals) == 1 and it.get("judge_relevance") is not None:
            rj.append(int(it["judge_relevance"]))
            rh.append(next(iter(vals)))
    k = cohen_kappa(gj, gh)
    res = {
        "judge_model": meta["judge_model"], "judge_prompt_sha256_12": meta["judge_prompt_sha256_12"],
        "groundedness": {"claims_labelled": len(gj), "agreement": (sum(x == y for x, y in zip(gj, gh, strict=True)) / len(gj)) if gj else None,
                         "cohen_kappa": k, "human_supported_rate": (sum(gh) / len(gh)) if gh else None,
                         "judge_supported_rate": (sum(gj) / len(gj)) if gj else None, "claims_with_both_boxes_ticked": conflicts,
                         "altered_claims_labelled": len(pert),
                         "altered_claims_judge_rejected": sum(1 for j, _ in pert if j == 0),
                         "altered_claims_human_rejected": sum(1 for _, h in pert if h == 0)},
        "relevance": {"answers_labelled": len(rj), "exact": (sum(x == y for x, y in zip(rj, rh, strict=True)) / len(rj)) if rj else None,
                      "within_one": (sum(abs(x - y) <= 1 for x, y in zip(rj, rh, strict=True)) / len(rj)) if rj else None},
        "trust_threshold_kappa": TRUST_KAPPA,
        "groundedness_trusted": bool(k is not None and k >= TRUST_KAPPA and len(gj) >= 15),
    }  # fmt: skip
    (ROOT / "eval" / "calibration" / "result.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    if not gj:
        print("\nNo claim labels found: tick the boxes in eval/CALIBRATION.md first.")


if __name__ == "__main__":
    main()
