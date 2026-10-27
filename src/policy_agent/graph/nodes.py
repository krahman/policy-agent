"""Graph nodes (PRD §9.3). `Deps` carries the model, tools and per-run side channels; nodes are closures over it."""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt
from openai import LengthFinishReasonError
from pydantic import BaseModel, Field

from policy_agent.generation.schema import Answer
from policy_agent.generation.validate import Violation, downgrade, validate
from policy_agent.graph import guard
from policy_agent.graph.state import (
    MAX_CALLS_PER_ROUND,
    MAX_REPAIRS,
    MAX_STEPS,
    MAX_TOOL_RETRIES,
    MIN_EVIDENCE_SCORE,
    WALL_CLOCK_S,
    AgentState,
)
from policy_agent.ingest.paths import ROOT
from policy_agent.mcp_client import ClientErrorCode, McpClientError
from policy_agent.retrieval.corpus import load_chunks
from policy_agent.retrieval.hybrid import period_groups
from policy_agent.tools import render_markdown, report_path, write_report
from policy_agent.tools.mcp_tools import stat_card_ids, unwrap
from policy_agent.tools.search_corpus import CURRENT_ROLE

PROMPTS = yaml.safe_load((ROOT / "prompts" / "agent_v1.yaml").read_text())
EVIDENCE_CHARS = 14000  # prompt budget for evidence plus tool output (about 3,500 tokens)
STATS_TOOLS = ("query_statistic", "compute_change", "read_stats_resource")
_CHANGE_WORDS = re.compile(r"\b(change|changed|increase|increased|decrease|decreased|rise|rose|risen|fall|fell|fallen|grew|growth|"
                           r"difference|compare|compared|versus|vs|percent|percentage|year-on-year|yoy)\b", re.I)  # fmt: skip


class Route(BaseModel):
    route: Literal["answerable", "ambiguous", "out_of_scope", "unsafe"]
    needs_numbers: bool = False
    plan: list[str] = Field(default_factory=list, max_length=4)
    clarifying_question: str | None = None
    reason: str = ""


@dataclass
class Deps:
    llm: Any  # ChatOpenAI
    tools: dict[str, Any]  # name -> LangChain tool
    search_ctx: Any  # SearchContext: limitations noted while tools run, re-rank spend
    reconnect: Any = None  # async callable that re-establishes the MCP connection
    mcp_available: bool = True


def _usage(msg: Any) -> dict:
    um = getattr(msg, "usage_metadata", None) or {}
    return {"input_tokens": um.get("input_tokens", 0), "output_tokens": um.get("output_tokens", 0), "llm_calls": 1}


def _dedupe(xs: list[str]) -> list[str]:
    return list(dict.fromkeys(xs))


def _elapsed(state: AgentState) -> float:
    return time.monotonic() - state.get("started", time.monotonic())


def _structured(deps: Deps, schema: Any, messages: list):
    return deps.llm.with_structured_output(schema, method="json_schema", include_raw=True).ainvoke(messages)


def _merge_evidence(old: list[dict], new: list[dict]) -> list[dict]:
    best = {e["chunk_id"]: e for e in old}
    for e in new:
        if e["chunk_id"] not in best or e.get("score", 0) > best[e["chunk_id"]].get("score", 0):
            best[e["chunk_id"]] = e
    return sorted(best.values(), key=lambda e: (-e.get("score", 0), e["chunk_id"]))


def _missing_periods(state: AgentState) -> set[str]:
    """Periods the question names that no evidence or tool result covers yet (deterministic, no model)."""
    covered = {e["reference_period"] for e in state["evidence"] if e.get("reference_period") not in (None, "None", "")}
    for r in state["tool_results"]:
        if r["status"] == "ok" and r.get("data"):
            covered |= {row["period"] for row in r["data"].get("rows", [])}
    return {
        sorted(g)[0] if len(g) == 1 else sorted(g)[0][:4] for g in period_groups(state["question"]) if not g & covered
    }


def _needs_calc(state: AgentState) -> bool:
    """A question that compares two named periods needs a computed change, not a model's mental arithmetic."""
    return len(period_groups(state["question"])) >= 2 and bool(_CHANGE_WORDS.search(state["question"]))


def _calc_done(state: AgentState) -> bool:
    return any(r["status"] == "ok" and r["tool"] in ("compute_change", "calculator") for r in state["tool_results"])


def _cards_for(rows: list[dict]) -> list[dict]:
    """The stat-card chunks behind query_statistic rows, so a tool result can be cited like any other chunk."""
    by = {c["chunk_id"]: c for c in load_chunks()}
    out = []
    keep = rows if len(rows) <= 12 else rows[:6] + rows[-6:]  # a range query: always keep both ends
    for cid in stat_card_ids(keep):
        c = by.get(cid)
        if c:
            out.append({
                "chunk_id": cid, "source_id": c["source_id"], "doc_type": "stat_card", "pub_date": c["pub_date"],
                "reference_period": c.get("reference_period"), "text": c["text"], "score": 1.0, "mode": "tool",
            })  # fmt: skip
    return out


def _evidence_text(state: AgentState) -> str:
    parts, used = [], 0
    for r in (r for r in state["tool_results"] if r["status"] == "ok"):  # tool results first: they carry the call ids
        block = f'<untrusted_tool_output tool="{r["tool"]}" tool_call_id="{r["id"]}">\n{r["output"]}\n</untrusted_tool_output>'
        parts.append(block)
        used += len(block)
    for e in state["evidence"]:
        block = (
            f'<untrusted_evidence chunk_id="{e["chunk_id"]}" source_id="{e["source_id"]}" type="{e["doc_type"]}" '
            f'date="{e.get("pub_date")}">\n{e["text"]}\n</untrusted_evidence>'
        )
        if used + len(block) > EVIDENCE_CHARS and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts) or "(no evidence was found)"


def _finalise(ans: Answer, state: AgentState, deps: Deps) -> dict:
    if guard.output_leak(ans.model_dump()):  # tripwire: never emit a leaked marker, whatever produced it
        ans = Answer(
            status="refused", summary="I can't provide that response.", confidence="high",
            limitations=["Output blocked: it contained an internal marker (possible prompt leak or followed injection)."],
        )  # fmt: skip
    d = ans.model_dump()
    notes = state.get("limitations", []) + deps.search_ctx.limitations
    d["limitations"] = _dedupe(d["limitations"] + notes)
    if notes and d["status"] in ("answered", "conflict_reported") and d["confidence"] == "high":
        d["confidence"] = "medium"  # incomplete evidence or a degraded path: never claim high confidence
    return d


async def _run_tool(deps: Deps, call: dict, retries: dict) -> tuple[dict, ToolMessage, list[dict]]:
    """Run one tool call. Unknown tool names are refused; transient failures are retried with backoff (PRD §9.5)."""
    name, args, cid = call["name"], call["args"], call["id"]
    t0 = time.perf_counter()
    tool = deps.tools.get(name)
    status, output, data, evidence = "error", "", None, []
    if tool is None:
        output = f"Error: unknown tool {name!r}."
    while tool is not None:
        try:
            msg = await tool.ainvoke({"name": name, "args": args, "id": cid, "type": "tool_call"})
            text = (
                msg.content
                if isinstance(msg.content, str)
                else "".join(c.get("text", "") for c in msg.content if isinstance(c, dict))
            )
            status, output = "ok", text
            if name == "search_corpus":
                evidence = list(msg.artifact or [])
            elif name in STATS_TOOLS:
                data = unwrap(text)
                if name == "query_statistic" and data:
                    evidence = _cards_for(data.get("rows", []))
            break
        except Exception as e:  # noqa: BLE001 - a tool failure is information for the agent, never a crash
            err = e if isinstance(e, McpClientError) else None
            transient = err is not None and (
                err.code in (ClientErrorCode.SERVER_UNAVAILABLE, ClientErrorCode.TIMEOUT)
                or err.server_code == "TIMEOUT"
            )
            output = f"Error: {err.message if err else type(e).__name__}"
            if transient and retries.get(name, 0) < MAX_TOOL_RETRIES:
                retries[name] = retries.get(name, 0) + 1
                await asyncio.sleep(0.3 * 2 ** (retries[name] - 1))
                if err is not None and err.code is ClientErrorCode.SERVER_UNAVAILABLE and deps.reconnect:
                    await deps.reconnect()
                continue
            break
    result = {
        "id": cid, "tool": name, "args": args, "output": output, "status": status, "data": data,
        "latency_ms": (time.perf_counter() - t0) * 1000, "retries": retries.get(name, 0),
    }  # fmt: skip
    return (
        result,
        ToolMessage(content=output[:6000], tool_call_id=cid, status="success" if status == "ok" else "error"),
        evidence,
    )


def make_nodes(deps: Deps) -> dict:
    async def guard_input(state: AgentState) -> dict:
        hit = guard.check(state["question"])
        return {
            "route": "unsafe" if hit else None, "route_info": {"guard": hit} if hit else {}, "step": 0, "retries": {},
            "errors": [], "repairs": 0, "limitations": [], "evidence": [], "tool_results": [], "violations": [],
            "started": time.monotonic(), "log": [f"guard_input: {'blocked (' + hit + ')' if hit else 'ok'}"],
        }  # fmt: skip

    async def route(state: AgentState) -> dict:
        p = PROMPTS["route"]
        msgs = [SystemMessage(content=p["system"]), HumanMessage(content=p["human"].format(question=state["question"]))]
        res = await _structured(deps, Route, msgs)
        r = res["parsed"] or Route(
            route="answerable", plan=["search_corpus"], reason="router output unreadable; defaulted"
        )
        brief = f"Question: {state['question']}\nPlan: {'; '.join(r.plan) or 'search_corpus'}"
        return {
            "route": r.route, "route_info": r.model_dump(), "plan": r.plan, "usage": _usage(res["raw"]),
            "messages": [HumanMessage(content=brief)], "log": [f"route: {r.route} | numbers={r.needs_numbers} | plan={r.plan}"],
        }  # fmt: skip

    async def plan(state: AgentState) -> dict:
        note = "The evidence so far is not enough."
        if missing := _missing_periods(state):
            note += f" It does not yet cover: {', '.join(sorted(missing))}."
        if _needs_calc(state) and not _calc_done(state):
            note += " The change between the periods must be computed with compute_change (pass the query_id of a range query)."
        if failed := [r for r in state["tool_results"] if r["status"] == "error"][-2:]:
            note += " Failed calls: " + "; ".join(f"{r['tool']}: {r['output'][:120]}" for r in failed) + "."
        note += " Call the tools again for what is missing, with different arguments if a call failed."
        return {"messages": [HumanMessage(content=note)], "log": [f"plan: replan ({note[:110]})"]}

    async def act(state: AgentState) -> dict:
        bound = deps.llm.bind_tools(list(deps.tools.values()))
        ai: AIMessage = await bound.ainvoke([SystemMessage(content=PROMPTS["act"]["system"]), *state["messages"]])
        out: dict = {"step": state["step"] + 1, "usage": _usage(ai), "messages": [ai]}
        calls = list(ai.tool_calls)
        if not calls:
            return out | {"log": [f"act: step {state['step'] + 1}, no tool calls"]}
        CURRENT_ROLE.set(state.get("user_role", "analyst_public"))
        retries = dict(state["retries"])
        results, tool_msgs, new_evidence, errors = [], [], [], []
        for call in calls[:MAX_CALLS_PER_ROUND]:
            r, msg, ev = await _run_tool(deps, dict(call), retries)
            results.append(r)
            tool_msgs.append(msg)
            new_evidence += ev
            if r["status"] == "error":
                errors.append(f"{r['tool']}: {r['output'][:160]}")
        for call in calls[MAX_CALLS_PER_ROUND:]:  # every tool_call needs a reply message
            tool_msgs.append(
                ToolMessage(content="Error: too many tool calls in one round.", tool_call_id=call["id"], status="error")
            )
        summary = ", ".join(f"{r['tool']}[{r['status']},{r['latency_ms']:.0f}ms]" for r in results)
        return out | {
            "tool_results": state["tool_results"] + results, "messages": [ai, *tool_msgs], "retries": retries,
            "evidence": _merge_evidence(state["evidence"], new_evidence), "errors": state["errors"] + errors,
            "log": [f"act: step {state['step'] + 1}: {summary}"],
        }  # fmt: skip

    async def assess(state: AgentState) -> dict:
        """Deterministic sufficiency check: evidence present, every named period covered, progress, budgets."""
        good = [e for e in state["evidence"] if e.get("score", 1.0) >= MIN_EVIDENCE_SCORE]
        ok_stats = [
            r for r in state["tool_results"] if r["status"] == "ok" and r["tool"] in (*STATS_TOOLS, "calculator")
        ]
        has = bool(good or ok_stats)
        missing = _missing_periods(state)
        size = len(state["evidence"]) + len(ok_stats)  # an empty search result is not progress
        calc_missing = _needs_calc(state) and not _calc_done(state) and deps.mcp_available
        if has and not missing and not calc_missing:
            reason, nxt = "sufficient", "synthesize"
        elif _elapsed(state) > WALL_CLOCK_S:
            reason, nxt = "wall-clock budget used", "synthesize" if has else "abstain"
        elif state["step"] >= MAX_STEPS:
            reason, nxt = "step limit reached", "synthesize" if has else "abstain"
        elif size <= state.get("size", -1):  # the last round added neither evidence nor a tool result
            reason, nxt = "no progress in the last round", "synthesize" if has else "abstain"
        else:
            what = sorted(missing) or ("a computed change" if calc_missing else "evidence")
            reason, nxt = f"insufficient (missing {what})", "plan"
        lim: list[str] = []
        if missing and nxt != "plan":
            lim.append(f"No evidence was found for: {', '.join(sorted(missing))}.")
        if any(r["status"] == "error" and r["tool"] in STATS_TOOLS for r in state["tool_results"]):
            lim.append(
                "The statistics server did not respond correctly, so published figures may come from text passages only."
            )
        if not deps.mcp_available:
            lim.append("The statistics server is unavailable; figures come from text passages only.")
        return {
            "stop_reason": reason, "size": size, "next_node": nxt, "limitations": _dedupe(state["limitations"] + lim),
            "log": [f"assess: {reason} -> {nxt}"],
        }  # fmt: skip

    async def synthesize(state: AgentState) -> dict:
        p = PROMPTS["synth"]
        notes = "; ".join(_dedupe(state["limitations"] + deps.search_ctx.limitations)) or "none"
        msgs: list = [
            SystemMessage(content=p["system"]),
            HumanMessage(
                content=p["human"].format(question=state["question"], notes=notes, evidence=_evidence_text(state))
            ),
        ]
        if state["violations"]:  # repair attempt: show the model its own answer and the checker's complaints
            if state.get("answer_raw"):
                msgs.append(AIMessage(content=state["answer_raw"]))
            msgs.append(
                HumanMessage(content=p["repair"].format(violations="\n".join(f"- {v}" for v in state["violations"])))
            )
        first = state["repairs"] == 0
        try:
            res = await _structured(deps, Answer, msgs)
        except LengthFinishReasonError:
            upd: dict = {"answer": None, "violations": ["V1: output was cut off at the token limit; give a shorter answer"],
                         "usage": {"llm_calls": 1}, "log": ["synthesize: truncated"]}  # fmt: skip
            return upd | ({"schema_valid_first": False} if first else {})
        ans = res["parsed"]
        upd = {"usage": _usage(res["raw"]), "log": [f"synthesize: {'ok' if ans else 'unparseable'}"]}
        if first:
            upd["schema_valid_first"] = ans is not None
        if ans is None:
            return upd | {
                "answer": None,
                "violations": [f"V1: schema does not parse: {str(res['parsing_error'])[:160]}"],
            }
        return upd | {"answer": ans.model_dump(), "answer_raw": ans.model_dump_json(), "violations": []}

    async def validate_node(state: AgentState) -> dict:
        ans: Answer | None = Answer.model_validate(state["answer"]) if state.get("answer") else None
        if ans is None:
            viol = [Violation("V1", v.split(": ", 1)[-1]) for v in state["violations"]] or [
                Violation("V1", "no answer produced")
            ]
        else:
            ev_ids = {e["chunk_id"] for e in state["evidence"]}
            outputs = {r["id"]: r["output"] for r in state["tool_results"] if r["status"] == "ok"}
            viol = validate(
                ans, state.get("user_role", "analyst_public"), ev_ids, outputs, tools_available=deps.mcp_available
            )
        upd: dict = {"log": [f"validate: {'pass' if not viol else ', '.join(sorted({v.rule for v in viol}))}"]}
        if "first_pass_violations" not in state:
            upd["first_pass_violations"] = [str(v) for v in viol]
        if not viol:
            assert ans is not None
            return upd | {"violations": [], "answer": _finalise(ans, state, deps)}
        if state["repairs"] < MAX_REPAIRS:
            return upd | {"violations": [str(v) for v in viol], "repairs": state["repairs"] + 1}
        return upd | {
            "violations": [str(v) for v in viol], "stop_reason": "validation failed after repair",
            "answer": _finalise(downgrade(ans, viol), state, deps) | {"downgraded": True},
        }  # fmt: skip

    async def clarify(state: AgentState) -> dict:
        q = state["route_info"].get("clarifying_question") or "Which measure, group and period do you mean?"
        a = Answer(
            status="needs_clarification",
            summary="I need one detail before I can answer.",
            clarifying_question=q,
            confidence="high",
        )
        return {"answer": _finalise(a, state, deps), "stop_reason": "clarification needed", "log": ["clarify"]}

    async def abstain(state: AgentState) -> dict:
        why = (
            state["route_info"].get("reason") or state.get("stop_reason") or "The evidence needed is not in the corpus."
        )
        lim = _dedupe(state.get("limitations", []) + deps.search_ctx.limitations)
        a = Answer(status="abstained", summary=f"I can't answer this from the available data. {why}".strip(), confidence="high",
                   limitations=lim or ["Nothing in the corpus (2021-Q3 to 2026-Q2) supports an answer."])  # fmt: skip
        return {
            "answer": _finalise(a, state, deps),
            "stop_reason": state.get("stop_reason") or "out of scope",
            "log": ["abstain"],
        }

    async def refuse(state: AgentState) -> dict:
        kind = state["route_info"].get("guard") or "injection"
        a = Answer(status="refused", summary=guard.REFUSAL.get(kind, guard.REFUSAL["injection"]), confidence="high",
                   limitations=[f"Request blocked by the input guard ({kind})."])  # fmt: skip
        return {"answer": _finalise(a, state, deps), "stop_reason": f"guard: {kind}", "log": [f"refuse ({kind})"]}

    async def report(state: AgentState) -> dict:
        """Render the brief, then pause for the user's confirmation before anything is written (PRD §9.6)."""
        assert state["answer"] is not None
        answer = {k: v for k, v in state["answer"].items() if k != "downgraded"}
        md, path = render_markdown(answer, state["question"]), report_path(answer)
        decision = interrupt({"action": "save_report", "path": str(path.relative_to(ROOT)), "preview": md[:600]})
        if isinstance(decision, dict) and decision.get("approve"):
            written = write_report(path, md)
            return {
                "report": {"saved": True, "path": str(written.relative_to(ROOT))},
                "log": [f"report: saved {written.name}"],
            }
        return {"report": {"saved": False, "path": None}, "log": ["report: not saved (not approved)"]}

    return {
        "guard_input": guard_input, "route": route, "plan": plan, "act": act, "assess": assess, "synthesize": synthesize,
        "validate": validate_node, "clarify": clarify, "abstain": abstain, "refuse": refuse, "report": report,
    }  # fmt: skip
