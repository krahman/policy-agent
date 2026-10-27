"""Compare the owner's ticks in eval/HUMAN_REVIEW_TEST.md with the automated scores (agreement, kappa) and summarise the rubric.

Usage: python scripts/compare_test_review.py"""

import json
import re

from policy_agent.ingest.paths import ROOT

SHEET = ROOT / "eval" / "HUMAN_REVIEW_TEST.md"
ITEMS = ROOT / "eval" / "calibration" / "test_review_items.json"


def kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return None if pe == 1 else (po - pe) / (1 - pe)


def ticks(text: str) -> dict[tuple[str, str], set[int]]:
    out: dict[tuple[str, str], set[int]] = {}
    for line in text.splitlines():
        for m in re.finditer(r"\[([xX ])\][^<\[]*<!--([gcusr]):([^:]+):(\d)-->", line):
            if m[1] in "xX":
                out.setdefault((m[2], m[3]), set()).add(int(m[4]))
    return out


def main() -> None:
    items = json.loads(ITEMS.read_text())["items"]
    t = ticks(SHEET.read_text())

    def one(key: str, item: str) -> int | None:
        v = t.get((key, item), set())
        return next(iter(v)) if len(v) == 1 else None

    res: dict = {"answers": len(items)}
    for key, name in (("g", "grounded"), ("c", "citations_correct"), ("u", "uncertainty_ok"), ("s", "safe")):
        vals = [one(key, i["item"]) for i in items]
        res[name] = {"labelled": sum(v is not None for v in vals), "yes": sum(v == 1 for v in vals)}
    gj, gh, cj, ch = [], [], [], []
    for i in items:
        g, c = one("g", i["item"]), one("c", i["item"])
        if g is not None and i["judge_groundedness"] is not None:
            gj.append(int(i["judge_groundedness"] >= 0.999))
            gh.append(g)
        if c is not None and i["citation_correct"] is not None:
            cj.append(int(i["citation_correct"] >= 0.999))
            ch.append(c)
    res["groundedness_vs_judge"] = {
        "n": len(gj),
        "agreement": sum(x == y for x, y in zip(gj, gh, strict=True)) / len(gj) if gj else None,
        "kappa": kappa(gj, gh),
    }  # noqa: E501
    res["citation_vs_gold_metric"] = {
        "n": len(cj),
        "agreement": sum(x == y for x, y in zip(cj, ch, strict=True)) / len(cj) if cj else None,
        "kappa": kappa(cj, ch),
    }  # noqa: E501
    use = [(one("r", i["item"]), i["judge_relevance"]) for i in items if one("r", i["item"]) and i["judge_relevance"]]
    res["usefulness"] = {"n": len(use), "mean_human": sum(h for h, _ in use) / len(use) if use else None,
                         "mean_judge": sum(j for _, j in use) / len(use) if use else None,
                         "within_one": sum(abs(h - j) <= 1 for h, j in use) / len(use) if use else None}  # fmt: skip
    (ROOT / "eval" / "calibration" / "test_review_result.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    if not any(v["labelled"] for k, v in res.items() if isinstance(v, dict) and "labelled" in v):
        print("\nNo ticks found: tick the boxes in eval/HUMAN_REVIEW_TEST.md first.")


if __name__ == "__main__":
    main()
