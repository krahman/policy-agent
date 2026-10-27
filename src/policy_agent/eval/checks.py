"""Validation of the evaluation set against the corpus, and few-shot leakage control (PRD §2.7)."""

import json
import re
from collections import Counter

from policy_agent.eval.corpus import Corpus
from policy_agent.eval.models import EvalCase, FewShot, RedteamCase, RetrievalCase
from policy_agent.ingest.paths import ROOT

DATA = ROOT / "eval" / "data"
EXPECTED_COUNTS = {
    "factual": 8, "multi_step": 7, "calculation": 5, "unanswerable": 5,
    "ambiguous": 3, "conflicting": 4, "adversarial": 4,
}  # fmt: skip
JACCARD_LIMIT = 0.6  # PRD §2.7: >0.6 Jaccard on 5-grams flags a case
_NUM = re.compile(r"\d[\d,]*\.?\d*")


def load(path, model):
    return [model.model_validate_json(line) for line in (DATA / path).read_text().splitlines()]


def numbers(text: str) -> set[float]:
    out = set()
    for tok in _NUM.findall(text):
        try:
            out.add(float(tok.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    return out


def has_number(text: str, value: float, tol: float = 0.0) -> bool:
    return any(abs(n - value) <= max(tol, 1e-9) for n in numbers(text))


def ngrams(text: str, n: int = 5) -> set[tuple[str, ...]]:
    w = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(w[i : i + n]) for i in range(max(len(w) - n + 1, 1))}


def jaccard(a: str, b: str, n: int = 5) -> float:
    x, y = ngrams(a, n), ngrams(b, n)
    return len(x & y) / max(len(x | y), 1)


def validate(corpus: Corpus | None = None) -> list[str]:
    """Return a list of problems (empty means the set is consistent with the corpus)."""
    C = corpus or Corpus()
    cases = load("eval_cases.jsonl", EvalCase)
    retrieval = load("retrieval_cases.jsonl", RetrievalCase)
    redteam = load("redteam_cases.jsonl", RedteamCase)
    errs: list[str] = []

    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        errs.append("duplicate case ids")
    counts = Counter(c.case_type for c in cases)
    if dict(counts) != EXPECTED_COUNTS:
        errs.append(f"case-type counts {dict(counts)} != {EXPECTED_COUNTS}")
    if len(cases) < 30:
        errs.append("fewer than 30 cases (challenge minimum)")
    for t, n in counts.items():
        dev = sum(1 for c in cases if c.case_type == t and c.split == "dev")
        if dev != round(n * 0.6):
            errs.append(f"{t}: {dev} dev of {n} is not a stratified 60/40 split")
    if any(c.split is None for c in cases):
        errs.append("case without a split")

    internal = {c["chunk_id"] for c in C.chunks if c["access_level"] == "internal"}
    canaries = ("CANARY", "POLICYAGENT")
    # text an injection payload may legitimately contain is excluded; everything else public must not
    public_text = " ".join(
        c["text"] for c in C.chunks if c["access_level"] == "public" and not any(k in c["text"] for k in canaries)
    )
    for c in cases:
        for cid, grade in c.gold_chunk_ids.items():
            if cid not in C.chunk_by_id:
                errs.append(f"{c.id}: gold chunk {cid} not in chunks.jsonl")
                continue
            if grade not in (1, 2):
                errs.append(f"{c.id}: grade {grade} not in (1, 2)")
            if c.user_role == "analyst_public" and cid in internal:
                errs.append(f"{c.id}: public-role case cites internal chunk {cid}")
        if c.gold_chunk_ids and 2 not in c.gold_chunk_ids.values():
            errs.append(f"{c.id}: no grade-2 chunk")
        gold_text = " ".join(C.chunk_by_id[i]["text"] for i in c.gold_chunk_ids if i in C.chunk_by_id)
        for q in c.gold_quotes:
            src = " ".join(ch["text"] for ch in C.chunks if ch["source_id"] == q.source_id)
            if q.quote not in src:
                errs.append(f"{c.id}: quote not found in {q.source_id}: {q.quote!r}")
            elif q.quote not in gold_text:
                errs.append(f"{c.id}: quote's chunk is not in gold_chunk_ids: {q.quote!r}")
        # a gold number copied from evidence must appear in it; computed values (calculation) are exempt
        if (
            c.gold_value is not None
            and c.case_type != "calculation"
            and not has_number(gold_text, c.gold_value, c.tolerance)
        ):
            errs.append(f"{c.id}: gold_value {c.gold_value} not found in gold evidence")
        for cv in c.conflict_values:
            src = " ".join(ch["text"] for ch in C.chunks if ch["source_id"] == cv.source_id)
            if not has_number(src, cv.value, c.tolerance):
                errs.append(f"{c.id}: conflict value {cv.value} not found in {cv.source_id}")
        for token in c.must_contain:
            if numbers(token) and not has_number(gold_text, min(numbers(token)), c.tolerance):
                errs.append(f"{c.id}: must_contain {token!r} not in gold evidence")
        if c.case_type == "conflicting" and sum(v.latest for v in c.conflict_values) != 1:
            errs.append(f"{c.id}: exactly one conflict value must be latest")

    # the leak tests only mean something if the forbidden text really is restricted
    for item in [*cases, *redteam]:
        if item.user_role != "analyst_public":
            continue
        for bad in item.must_not_contain:
            if bad.startswith(canaries):
                continue  # canaries live in the injected chunk by design; they must not reach the answer
            if bad in public_text:
                errs.append(f"{item.id}: must_not_contain {bad!r} also appears in public chunks (test would be unfair)")
    for item in [*cases, *redteam]:
        for bad in item.must_not_contain:
            if bad == "end of October" and "end of October" not in " ".join(C.chunk_by_id[i]["text"] for i in internal):
                errs.append(f"{item.id}: the restricted phrase is not in any internal chunk")
    for rc in retrieval:
        for cid in rc.relevance:
            if cid not in C.chunk_by_id:
                errs.append(f"retrieval {rc.id}: unknown chunk {cid}")
    if {r.id for r in retrieval} != {c.id for c in cases if c.gold_chunk_ids}:
        errs.append("retrieval dataset does not cover exactly the cases with gold chunks")
    for r in redteam:
        if r.kind == "qa" and not r.question.strip():
            errs.append(f"{r.id}: empty question")
    return errs


def leakage_report(corpus: Corpus | None = None) -> dict:
    """Few-shot pool vs evaluation set: question overlap, shared evidence chunks, shared answer values."""
    cases = load("eval_cases.jsonl", EvalCase)
    pool = load("fewshot_pool.jsonl", FewShot)
    eval_chunks = {cid for c in cases for cid in c.gold_chunk_ids}
    eval_numbers = set().union(*(numbers(c.gold_answer) for c in cases))
    eval_numbers |= {c.gold_value for c in cases if c.gold_value is not None}
    flags = []
    max_j = 0.0
    for fs in pool:
        for c in cases:
            j = jaccard(fs.question, c.question)
            max_j = max(max_j, j)
            if j > JACCARD_LIMIT:
                flags.append({"fewshot": fs.id, "case": c.id, "kind": "question_overlap", "jaccard": round(j, 3)})
        for cid in set(fs.chunk_ids) & eval_chunks:
            flags.append({"fewshot": fs.id, "kind": "shared_chunk", "chunk_id": cid})
        # trivially small numbers (years, counts of 1-2) are not answer values
        shared = {n for n in numbers(fs.answer) & eval_numbers if n >= 10 and not 1990 <= n <= 2030}
        shared |= {n for n in numbers(fs.answer) & eval_numbers if n < 10 and n != int(n)}
        for n in sorted(shared):
            flags.append({"fewshot": fs.id, "kind": "shared_value", "value": n})
    within = max((jaccard(a.question, b.question), a.id, b.id) for i, a in enumerate(cases) for b in cases[i + 1 :])
    return {
        "fewshot_examples": len(pool),
        "eval_cases": len(cases),
        "jaccard_limit": JACCARD_LIMIT,
        "max_fewshot_vs_eval_jaccard": round(max_j, 3),
        "max_eval_vs_eval_jaccard": {"jaccard": round(within[0], 3), "pair": [within[1], within[2]]},
        "flags": flags,
        "clean": not flags,
    }


if __name__ == "__main__":
    problems = validate()
    report = leakage_report()
    (DATA / "leakage_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))
    print("validation problems:", len(problems))
    for p in problems:
        print(" -", p)
    raise SystemExit(1 if problems or not report["clean"] else 0)
