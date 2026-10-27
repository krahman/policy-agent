"""Structured answer schema (PRD §8.2). Programmatic validation rules V1 to V6 are added in Step 6."""

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    quote: str = Field(max_length=300, description="Verbatim span copied from the cited chunk")


class Claim(BaseModel):
    text: str
    kind: Literal["source_fact", "statistical_finding", "model_inference"]
    citations: list[Citation] = []
    tool_call_ids: list[str] = []  # required for statistical_finding once tools exist (Step 8)


class ConflictNote(BaseModel):
    description: str
    values: list[str] = []
    sources: list[str] = []


class Answer(BaseModel):
    status: Literal["answered", "abstained", "needs_clarification", "conflict_reported", "refused"]
    summary: str
    claims: list[Claim] = []
    conflicts: list[ConflictNote] = []
    clarifying_question: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    limitations: list[str] = []

    def text(self) -> str:
        """Flat text used by the deterministic evaluators."""
        parts = [self.summary, *[c.text for c in self.claims], *[n.description for n in self.conflicts]]
        if self.clarifying_question:
            parts.append(self.clarifying_question)
        return "\n".join(p for p in parts if p)
