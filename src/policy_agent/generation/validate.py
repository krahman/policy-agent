"""Programmatic output validation V1-V6 (PRD §8.3). Pure functions: no model calls, no network."""

import re
from dataclasses import dataclass

from pydantic import ValidationError

from policy_agent.eval.evaluators import MIN_QUOTE, _chunk_text, _norm, numbers_in
from policy_agent.generation.schema import Answer
from policy_agent.retrieval.corpus import ROLE_ACCESS, load_chunks

RULES = {
    "V1": "schema parses",
    "V2": "every citation quote is a substring of the cited chunk",
    "V3": "every number in the summary and non-inference claims appears in a cited quote or tool output",
    "V4": "statistical_finding claims reference an existing tool_call_id",
    "V5": "answered / conflict_reported needs at least one claim and a citation on every claim",
    "V6": "no chunk the current role may not read is cited",
}
_YEAR = re.compile(r"^(19|20)\d\d$")


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.message}"


def parse(raw: dict | Answer | None) -> tuple[Answer | None, list[Violation]]:
    """V1."""
    if isinstance(raw, Answer):
        return raw, []
    try:
        return Answer.model_validate(raw), []
    except (ValidationError, TypeError) as e:
        return None, [Violation("V1", f"schema does not parse: {str(e)[:200]}")]


def _is_year(v: float) -> bool:
    return v == int(v) and bool(_YEAR.match(str(int(v))))


def _access(chunk_id: str) -> str | None:
    meta = {c["chunk_id"]: c["access_level"] for c in load_chunks()}
    return meta.get(chunk_id)


def validate(
    answer: Answer,
    role: str = "analyst_public",
    evidence_ids: set[str] | None = None,
    tool_outputs: dict[str, str] | None = None,
    tools_available: bool = False,
) -> list[Violation]:
    """Return every violated rule (V2-V6); V1 is `parse`. `evidence_ids`, when given, are the chunks the model
    was shown: citing anything else is a V2 failure. V4 is only enforced when tools were available to the run."""
    out: list[Violation] = []
    texts = _chunk_text()
    allowed = ROLE_ACCESS[role]
    claim_cites = [(cl, cl.citations) for cl in answer.claims]
    all_cites = [c for _, cs in claim_cites for c in cs]

    for c in all_cites:  # V6 before V2: a restricted chunk is a security finding, not a typo
        level = _access(c.chunk_id)
        if level is not None and level not in allowed:
            out.append(Violation("V6", f"chunk {c.chunk_id} is restricted for role {role}"))
    for c in all_cites:
        if c.chunk_id not in texts:
            out.append(Violation("V2", f"chunk_id {c.chunk_id} does not exist"))
        elif evidence_ids is not None and c.chunk_id not in evidence_ids:
            out.append(Violation("V2", f"chunk {c.chunk_id} was not in the evidence you were given"))
        elif len(_norm(c.quote)) < MIN_QUOTE or _norm(c.quote) not in texts[c.chunk_id]:
            out.append(Violation("V2", f"quote not found verbatim in chunk {c.chunk_id}: {c.quote[:80]!r}"))

    tool_nums = [v for t in (tool_outputs or {}).values() for v in numbers_in(t)]
    inferred = [v for cl in answer.claims if cl.kind == "model_inference" for v in numbers_in(cl.text)]

    def missing(text: str, pool: list[float]) -> list[float]:
        return [
            v for v in numbers_in(text) if not _is_year(v) and not any(abs(abs(v) - abs(s)) < 1e-9 for s in pool)
        ]  # sign is wording: 'fell 1.2' vs '-1.2'

    for cl in answer.claims:
        if cl.kind != "model_inference" and cl.citations:  # derived numbers must be labelled model_inference
            pool = [v for c in cl.citations for v in numbers_in(c.quote)] + tool_nums
            if bad := missing(cl.text, pool):
                out.append(Violation("V3", f"number(s) {bad} in claim {cl.text[:60]!r} are not in its cited quotes"))
    summary_pool = [v for c in all_cites for v in numbers_in(c.quote)] + tool_nums + inferred
    if bad := missing(answer.summary, summary_pool):
        out.append(Violation("V3", f"number(s) {bad} in the summary appear in no cited quote or labelled inference"))

    if tools_available:
        have = set(tool_outputs or {})
        for cl in answer.claims:
            if cl.kind == "statistical_finding" and not (set(cl.tool_call_ids) & have):
                out.append(Violation("V4", f"statistical_finding without an existing tool_call_id: {cl.text[:60]!r}"))

    if answer.status in ("answered", "conflict_reported"):
        if not answer.claims:
            out.append(Violation("V5", f"status {answer.status} with no claims"))
        for cl in answer.claims:
            if not cl.citations:
                out.append(Violation("V5", f"claim without citation: {cl.text[:60]!r}"))
    return out


def downgrade(answer: Answer | None, violations: list[Violation]) -> Answer:
    """After a failed repair: never emit an unvalidated answer (PRD §8.3)."""
    why = "; ".join(sorted({v.rule for v in violations}))
    return Answer(
        status="abstained",
        summary="I could not produce an answer that passes the citation and number checks, so I am not giving one.",
        limitations=[f"Output validation failed ({why})."],
        confidence="low",
    )
