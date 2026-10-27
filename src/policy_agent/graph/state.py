"""Agent state (PRD §9.2) and the limits that bound a run (PRD §9.3)."""

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

MAX_STEPS = 6  # tool rounds
MAX_TOOL_RETRIES = 2  # per tool, for transient failures
MAX_REPAIRS = 1
WALL_CLOCK_S = 30.0
RECURSION_LIMIT = 25  # LangGraph's hard backstop
MAX_CALLS_PER_ROUND = 4
MIN_EVIDENCE_SCORE = 0.02  # re-rank scores below this are treated as no evidence


def add_usage(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        out[k] = out.get(k, 0) + v
    return out


class AgentState(TypedDict, total=False):
    question: str
    user_role: Literal["analyst_public", "analyst_internal"]
    guard: str | None  # the input rule that blocked the question, if any
    messages: Annotated[list, add_messages]
    evidence: list[dict]  # chunk_id, text, score, source metadata (search passages and stat cards behind tool rows)
    tool_results: list[dict]  # id, tool, args, output, status, latency_ms
    step: int
    retries: dict[str, int]
    errors: list[str]
    repairs: int
    violations: list[str]
    answer: dict | None
    limitations: list[str]
    usage: Annotated[dict, add_usage]
    log: Annotated[list[str], operator.add]
    started: float
    stop_reason: str
    want_report: bool
    report: dict | None
    first_pass_violations: list[str]
    schema_valid_first: bool
    answer_raw: str
    size: int
    next_node: str
    last_calls: int  # tool calls in the latest round; 0 means the model chose to stop
