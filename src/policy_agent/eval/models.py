"""Schemas for the three evaluation datasets (PRD §11.2, §12.1)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

CaseType = Literal["factual", "multi_step", "calculation", "unanswerable", "ambiguous", "conflicting", "adversarial"]
Status = Literal["answered", "abstained", "needs_clarification", "conflict_reported", "refused"]
Role = Literal["analyst_public", "analyst_internal"]
Tool = Literal["search_corpus", "query_statistic", "compute_change", "calculator"]
ConflictKind = Literal["preliminary_vs_final", "unexplained_discrepancy"]


class Quote(BaseModel):
    source_id: str
    quote: str = Field(min_length=3, max_length=300)  # verbatim span; lets labels survive re-chunking


class ConflictValue(BaseModel):
    value: float
    source_id: str
    label: str  # e.g. "advance release 2024-07-31"
    latest: bool = False


class EvalCase(BaseModel):
    id: str
    question: str
    user_role: Role = "analyst_public"
    case_type: CaseType
    expected_status: Status
    gold_answer: str
    gold_value: float | None = None
    unit: str | None = None
    tolerance: float = 0.0  # absolute tolerance on gold_value (numeric_exact evaluator)
    gold_chunk_ids: dict[str, int] = {}  # chunk_id -> graded relevance (2 = contains the answer, 1 = context)
    gold_quotes: list[Quote] = []
    conflict_values: list[ConflictValue] = []
    must_contain: list[str] = []  # numbers compared by value, prose terms judged semantically
    must_not_contain: list[str] = []  # exact match: canaries and restricted text only
    must_not_endorse: list[str] = []  # claims the answer must not assert; judged semantically
    conflict_kind: ConflictKind | None = None  # what the conflict judge may require the answer to say
    clarify_must_cover: list[str] = []  # what the clarifying question must address (others optional)
    requires_tools: list[Tool] = []
    notes: str = ""
    author: str
    created_at: str
    split: Literal["dev", "test"] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "EvalCase":
        answerable = self.expected_status in ("answered", "conflict_reported")
        if answerable and not self.gold_chunk_ids:
            raise ValueError(f"{self.id}: answerable case needs gold_chunk_ids")
        if not answerable and self.gold_value is not None:
            raise ValueError(f"{self.id}: non-answer cases cannot carry gold_value")
        if self.expected_status == "conflict_reported" and len(self.conflict_values) < 2:
            raise ValueError(f"{self.id}: conflict case needs at least two conflict_values")
        if self.expected_status == "conflict_reported" and self.conflict_kind is None:
            raise ValueError(f"{self.id}: conflict case needs conflict_kind")
        if self.expected_status == "needs_clarification" and not self.clarify_must_cover:
            raise ValueError(f"{self.id}: clarification case needs clarify_must_cover")
        if self.gold_value is not None and self.unit is None:
            raise ValueError(f"{self.id}: gold_value needs a unit")
        return self


class RetrievalCase(BaseModel):
    id: str
    question: str
    user_role: Role = "analyst_public"
    relevance: dict[str, int]  # chunk_id -> graded relevance
    split: Literal["dev", "test"]


class RedteamCase(BaseModel):
    id: str
    threat: str
    question: str
    user_role: Role = "analyst_public"
    expected_status: Status | Literal["not_followed"]
    must_contain: list[str] = []
    must_not_contain: list[str] = []
    must_not_endorse: list[str] = []
    requires: list[str] = []  # components that must exist before the case can run (e.g. "mcp")
    kind: Literal["qa", "config_test"] = "qa"
    notes: str = ""


class FewShot(BaseModel):
    id: str
    question: str
    status: Status
    answer: str
    chunk_ids: list[str] = []
