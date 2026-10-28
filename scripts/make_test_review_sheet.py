"""Build, and later score, the human review sheet for held-out answers (spec requirement 6).

`python scripts/make_test_review_sheet.py`          writes eval/HUMAN_REVIEW_TEST.md (10 held-out answers, blank)
`python scripts/make_test_review_sheet.py --score`  reads the ticked sheet; prints human vs automated results

Ten of the 15 held-out cases are drawn with the project seed: one per case type first, then random fill. The answer shown is the
first of the three runs in eval/results/E8T_test.json (the reported run). Automated scores are not shown on the sheet. Nothing is
ticked by this script. Reviewing is read-only: it must never lead to a held-out case or label being edited."""

import json
import random
import re
import sys
from collections import Counter, defaultdict

from policy_agent.eval.checks import load
from policy_agent.eval.models import EvalCase
from policy_agent.ingest.paths import ROOT
from policy_agent.retrieval.corpus import load_chunks

SEED = 20261027
N_ITEMS = 10
RESULT = ROOT / "eval" / "results" / "E8T_test.json"
OUT = ROOT / "eval" / "HUMAN_REVIEW_TEST.md"
KEY = ROOT / "eval" / "calibration" / "test_review_items.json"
MAX_QUOTE = 300
CRITERIA = [
    (
        "C1",
        "Right behaviour",
        "The answer did what the question needed: answered it, asked a clarifying question, said the data does not cover it, "
        "reported a conflict, or refused. (Judge this from the question and the reference note, not from the answer's own claims.)",
    ),
    (
        "C2",
        "Facts correct",
        "Every number and statement in the answer is true to the quoted source text and to the reference note. "
        "Statements marked as model inference are reasonable. Nothing is invented.",
    ),
    (
        "C3",
        "Citations support the claims",
        "Each claim's quoted passage really says what the claim says, for the right period and the right group "
        "(overall, resident or citizen; seasonally adjusted or not). A claim from a calculation may cite a tool call instead. If the answer makes no claims (for example a refusal or a clarifying question), tick Yes.",
    ),
    (
        "C4",
        "Honest about limits",
        "Basis, units, preliminary or revised status and missing data are stated where they matter, and confidence is not "
        "higher than the evidence allows. No unsafe or out-of-scope content.",
    ),
]
OPTIONS = ("Yes", "Partly", "No")


def pick(cases: list[EvalCase]) -> list[str]:
    rng = random.Random(SEED)
    by_type: dict[str, list[str]] = defaultdict(list)
    for c in sorted(cases, key=lambda c: c.id):
        by_type[c.case_type].append(c.id)
    chosen = [rng.choice(ids) for _, ids in sorted(by_type.items())]
    rest = sorted(c.id for c in cases if c.id not in chosen)
    chosen += rng.sample(rest, N_ITEMS - len(chosen))
    rng.shuffle(chosen)
    return chosen


def build() -> None:
    cases = {c.id: c for c in load("eval_cases.jsonl", EvalCase) if c.split == "test"}
    runs = {}
    for r in json.loads(RESULT.read_text())["runs"]:
        runs.setdefault(r["case_id"], r)
    texts = {c["chunk_id"]: c for c in load_chunks()}
    ids = pick(list(cases.values()))
    key, parts = {}, []
    for n, cid in enumerate(ids, start=1):
        c, o = cases[cid], runs[cid]["output"]
        a = o["answer"] or {}
        item = f"H{n:02d}"
        key[item] = {"case_id": cid, "case_type": c.case_type}
        lines = [
            f"### {item}",
            "",
            f"**Question** (role: {c.user_role}): {c.question}",
            "",
            f"**Reference note** (what a correct answer needs): {c.gold_answer}",
            "",
        ]
        if c.conflict_values:
            lines += [
                "Values the answer should surface: "
                + "; ".join(f"{v.value} ({v.label}{', latest' if v.latest else ''})" for v in c.conflict_values),
                "",
            ]
        lines += [
            f"**System answer** (status: `{o['status']}`, confidence: {a.get('confidence', '-')})",
            "",
            f"> {a.get('summary', '')}",
            "",
        ]
        if a.get("clarifying_question"):
            lines += [f"Clarifying question asked: *{a['clarifying_question']}*", ""]
        for i, cl in enumerate(a.get("claims", []), start=1):
            lines.append(f"- Claim {i} ({cl['kind']}): {cl['text']}")
            for ct in cl.get("citations", []):
                ch = texts.get(ct["chunk_id"])
                where = f"{ch['doc_type']}, {ch['pub_date']}" if ch else "unknown chunk"
                lines.append(f'  - cited ({where}): "{ct["quote"][:MAX_QUOTE]}"')
            if cl.get("tool_call_ids"):
                lines.append(
                    f"  - from tool call(s): {', '.join(cl['tool_call_ids'])} (not shown here; check against the reference note)"
                )
        for k, cf in enumerate(a.get("conflicts", []), start=1):
            lines.append(
                f"- Conflict {k}: {cf['description']} | values: {', '.join(cf['values'])} | sources: {', '.join(cf['sources'])}"
            )
        if a.get("limitations"):
            lines += ["", "Limitations stated: " + " | ".join(a["limitations"])]
        lines.append("")
        for code, name, _ in CRITERIA:
            lines.append(f"- **{code} {name}:** " + "  ".join(f"[ ] {opt}" for opt in OPTIONS))
        lines += ["- Notes (what was wrong, or anything unclear):", "", "---", ""]
        parts.append("\n".join(lines))
    KEY.parent.mkdir(parents=True, exist_ok=True)
    KEY.write_text(json.dumps(key, indent=1) + "\n")
    rubric = "\n".join(f"- **{c} {n}.** {d}" for c, n, d in CRITERIA)
    head = f"""# Human review of held-out answers

**Status: NOT REVIEWED.** Every box below is empty. A person must tick them; no tool or model fills this sheet.

## What this is

Ten of the 15 held-out (`test`) cases, one run each (the reported run of the final agent). The automated scores are hidden so they do not
influence you. Chosen with seed {SEED}: one case of each type first, then random fill. The sheet is for **reading and judging only**:
do not edit any case, label or prompt because of what you see (that would leak the held-out set into the design).

## How to review

1. Read the question and the **reference note** (the expected answer, written before any system existed).
2. Read the system answer and the quoted passages. You do not need labour-market expertise: compare what the answer says with the quoted
   text and the reference note. If a claim cannot be checked from them, tick **Partly** and say so in the notes.
3. For each of the four criteria below tick exactly one box: **Yes** (fully), **Partly** (minor or uncheckable problems), **No** (clearly wrong).
4. Fill in the reviewer block, then run `make test-review-score`.

{rubric}

## Reviewer

- Name or role (for example "project owner" or "colleague, no labour-data background"):
- Labour-market background (none / some / expert):
- Date:
- Time spent:
- Was anything shown to you besides this sheet (for example the automated scores)? (yes/no):

---

"""
    OUT.write_text(head + "\n".join(parts))
    print("wrote", OUT.relative_to(ROOT), "with", len(ids), "items; key in", KEY.relative_to(ROOT))


def score() -> int:
    text = OUT.read_text()
    key = json.loads(KEY.read_text())
    res = {r["case_id"]: r for r in json.loads(RESULT.read_text())["runs"][::-1]}  # first run of each case wins
    marks: dict[str, dict[str, str]] = {}
    for item, body in re.findall(r"### (H\d\d)\n(.*?)(?=\n### H|\Z)", text, flags=re.S):
        for code, line in re.findall(r"\*\*(C\d) [^*]+:\*\* (.*)", body):
            ticked = [o for o in OPTIONS if re.search(rf"\[[xX]\] {o}\b", line)]
            if len(ticked) == 1:
                marks.setdefault(item, {})[code] = ticked[0]
    done = [i for i in key if len(marks.get(i, {})) == len(CRITERIA)]
    print(f"{len(done)} of {len(key)} items fully reviewed")
    if len(done) < len(key):
        print("not reviewed yet:", ", ".join(i for i in key if i not in done))
        return 1
    print("\nHuman result (10 held-out answers, one reviewer; too few for any interval):")
    for code, name, _ in CRITERIA:
        c = Counter(marks[i][code] for i in done)
        print(f"  {code} {name:<32} Yes {c['Yes']}  Partly {c['Partly']}  No {c['No']}")
    print("\nAgainst the automated scores for the same runs:")
    for i in done:
        cid = key[i]["case_id"]
        s = res[cid]["scores"]
        auto = {k: s.get(k) for k in ("status_match", "citation_correct", "groundedness")}
        flag = (
            " <-- disagrees"
            if (marks[i]["C1"] == "No" and auto["status_match"] == 1)
            or (marks[i]["C1"] == "Yes" and auto["status_match"] == 0)
            else ""
        )
        print(
            f"  {i} {cid} ({key[i]['case_type']}): human C1 {marks[i]['C1']}, C2 {marks[i]['C2']}, C3 {marks[i]['C3']} | automated {auto}{flag}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(score() if "--score" in sys.argv else (build() or 0))
