"""Agent runtime: one long-lived MCP connection, per-question graphs, fault injection, a synchronous `ask` (PRD §9.5).

The MCP connection lives in a dedicated event-loop thread so that many questions reuse one server process (starting
it costs about a second). Each question gets its own graph, search context and tool set, so concurrent runs do not
share limitations or spend."""

import asyncio
import threading
import time
import uuid
from contextlib import suppress
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import SecretStr

from policy_agent import mcp_client as mc
from policy_agent.graph.build import build_graph
from policy_agent.graph.nodes import Deps
from policy_agent.graph.state import RECURSION_LIMIT
from policy_agent.retrieval.dense import DEFAULT_EMBEDDING
from policy_agent.tools import calculator_tool, make_search_corpus
from policy_agent.tools.mcp_tools import load_stats_tools
from policy_agent.tools.search_corpus import SearchContext

DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
FAULTS = {"dense_down", "mcp_down", "mcp_timeout", "mcp_malformed", "mcp_poison"}


def make_llm(model: str, max_tokens: int = 3000, http_client: httpx.AsyncClient | None = None) -> ChatOpenAI:
    import os

    return ChatOpenAI(
        http_async_client=http_client,  # own client per runtime: the shared default one is bound to the first event loop
        model=model,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
        max_completion_tokens=max_tokens,
    )


class AgentRuntime:
    def __init__(
        self, model: str = DEFAULT_MODEL, embedding: str = DEFAULT_EMBEDDING, faults: set[str] | frozenset[str] = frozenset(),
        max_tokens: int = 3000, llm: Any = None,
    ):  # fmt: skip
        unknown = set(faults) - FAULTS
        if unknown:
            raise ValueError(f"unknown fault flags {sorted(unknown)}; choose from {sorted(FAULTS)}")
        self.model, self.embedding, self.faults = model, embedding, frozenset(faults)
        self._http = httpx.AsyncClient(timeout=120)
        self.llm = llm or make_llm(model, max_tokens, self._http)
        self.saver = MemorySaver()
        self.mcp_tools: dict[str, BaseTool] = {}
        self.mcp_ok = False
        self.mcp_error: str | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="agent-loop")
        self._closing = False

    # ---- lifecycle ---------------------------------------------------------------------------------------------------
    def start(self) -> "AgentRuntime":
        self._thread.start()
        self._reset = asyncio.run_coroutine_threadsafe(self._init_events(), self._loop).result()
        asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        asyncio.run_coroutine_threadsafe(self._wait_ready(), self._loop).result(timeout=60)
        return self

    async def _init_events(self) -> asyncio.Event:
        self._ready: asyncio.Future = self._loop.create_future()
        self._stop = asyncio.Event()
        return asyncio.Event()

    async def _wait_ready(self) -> None:
        await asyncio.shield(self._ready)

    async def _serve(self) -> None:
        """Hold one connection in one task (the SDK's task groups must be entered and left by the same task)."""
        while not self._closing:
            allow = mc.load_allow_list()
            env: dict[str, str] = {}
            if "mcp_down" in self.faults:
                allow["servers"]["stats"]["command"] = "/nonexistent/python"
            if "mcp_timeout" in self.faults:
                env |= {"MCP_FAULT": "slow", "MCP_TIMEOUT_S": "1"}
            if "mcp_malformed" in self.faults:
                env["MCP_FAULT"] = "malformed"
            if "mcp_poison" in self.faults:
                env["MCP_POISON"] = "1"
            try:
                async with mc.connect("stats", allow, env) as conn:
                    self.mcp_tools = {t.name: t for t in await load_stats_tools(conn)}
                    self.mcp_ok, self.mcp_error = True, None
                    self._signal_ready()
                    await self._wait_for_reset_or_stop()  # leaving the block closes the connection and the server
            except mc.McpClientError as e:
                self.mcp_ok, self.mcp_tools, self.mcp_error = False, {}, str(e)
                self._signal_ready()
                await self._wait_for_reset_or_stop()

    def _signal_ready(self) -> None:
        if not self._ready.done():
            self._ready.set_result(True)

    async def _wait_for_reset_or_stop(self) -> None:
        reset_wait = asyncio.ensure_future(self._reset.wait())
        stop_wait = asyncio.ensure_future(self._stop.wait())
        await asyncio.wait({reset_wait, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
        for t in (reset_wait, stop_wait):
            t.cancel()
        self._reset.clear()

    async def reconnect(self) -> None:
        self._ready = self._loop.create_future()
        self._reset.set()
        await asyncio.wait_for(asyncio.shield(self._ready), timeout=30)

    def close(self) -> None:
        self._closing = True

        async def stop():
            self._stop.set()
            self._reset.set()

        with suppress(Exception):
            asyncio.run_coroutine_threadsafe(stop(), self._loop).result(timeout=10)
        with suppress(Exception):
            asyncio.run_coroutine_threadsafe(self._http.aclose(), self._loop).result(timeout=5)
        time.sleep(0.2)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    # ---- asking ------------------------------------------------------------------------------------------------------
    def _make(self) -> tuple[Any, Deps, SearchContext]:
        ctx = SearchContext(embedding=self.embedding, faults=self.faults)
        tools: dict[str, BaseTool] = {
            "search_corpus": make_search_corpus(ctx),
            "calculator": calculator_tool,
            **self.mcp_tools,
        }
        deps = Deps(llm=self.llm, tools=tools, search_ctx=ctx, reconnect=self._reconnect_and_refresh(tools),
                    mcp_available=self.mcp_ok)  # fmt: skip
        return build_graph(deps, self.saver), deps, ctx

    def _reconnect_and_refresh(self, tools: dict):
        async def go() -> None:
            await self.reconnect()
            for k in ("query_statistic", "compute_change"):
                tools.pop(k, None)
            tools.update(self.mcp_tools)

        return go

    async def _ask(self, question: str, role: str, want_report: bool, thread_id: str) -> dict:
        graph, deps, ctx = self._make()
        t0 = time.perf_counter()
        state = await graph.ainvoke(
            {
                "question": question,
                "user_role": role,
                "want_report": want_report,
                "usage": {},
                "log": [],
                "messages": [],
            },
            {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT},
        )
        return to_outputs(state, time.perf_counter() - t0, ctx, self.model, deps.mcp_available, thread_id)

    def ask(
        self, question: str, role: str = "analyst_public", want_report: bool = False, thread_id: str | None = None
    ) -> dict:
        tid = thread_id or uuid.uuid4().hex
        fut = asyncio.run_coroutine_threadsafe(self._ask(question, role, want_report, tid), self._loop)
        return fut.result(timeout=120)

    def confirm_report(self, thread_id: str, approve: bool) -> dict:
        """Resume a run that is paused at the save-report interrupt."""

        async def go():
            graph, _, _ = self._make()
            return await graph.ainvoke(
                Command(resume={"approve": approve}),
                {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT},
            )  # noqa: E501

        state = asyncio.run_coroutine_threadsafe(go(), self._loop).result(timeout=60)
        return state.get("report") or {}

    def __enter__(self) -> "AgentRuntime":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


def to_outputs(state: dict, seconds: float, ctx: SearchContext, model: str, mcp_ok: bool, thread_id: str = "") -> dict:
    """Flatten the final graph state into the dict the evaluators and the CLI read."""
    answer = {k: v for k, v in (state.get("answer") or {}).items() if k != "downgraded"}
    cites = [c for cl in answer.get("claims", []) for c in cl.get("citations", [])]
    ev = sorted(state.get("evidence", []), key=lambda e: -e.get("score", 0))
    usage = state.get("usage", {})
    return {
        "status": answer.get("status", "abstained"), "answer": answer or None, "text": _text(answer),
        "citations": [{"chunk_id": c["chunk_id"], "quote": c["quote"]} for c in cites],
        "retrieved": [e["chunk_id"] for e in ev][:10], "evidence": [{"chunk_id": e["chunk_id"], "text": e["text"]} for e in ev],
        "usage": {"model": model, "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
                  "extra_cost_usd": ctx.rerank_cost},  # fmt: skip
        "latency_ms": seconds * 1000, "error": None, "schema_valid": state.get("schema_valid_first"),
        "validation": {"first_pass": state.get("first_pass_violations") or [], "repaired": bool(state.get("repairs")) and not (state.get("answer") or {}).get("downgraded") and not state.get("violations"),  # noqa: E501
                       "downgraded": bool((state.get("answer") or {}).get("downgraded"))},  # fmt: skip
        "agent": {
            "route": state.get("route"), "steps": state.get("step", 0), "llm_calls": usage.get("llm_calls", 0),
            "tools": [r["tool"] for r in state.get("tool_results", [])],
            "tool_status": [r["status"] for r in state.get("tool_results", [])],
            "tool_latency_ms": [round(r["latency_ms"]) for r in state.get("tool_results", [])],
            "stop_reason": state.get("stop_reason"), "errors": state.get("errors", []), "limitations": answer.get("limitations", []),
            "log": state.get("log", []), "mcp_available": mcp_ok, "report": state.get("report"),
            "interrupted": bool(state.get("__interrupt__")), "thread_id": thread_id,
        },
    }  # fmt: skip


def _text(answer: dict) -> str:
    if not answer:
        return ""
    parts = [answer.get("summary", ""), *[c["text"] for c in answer.get("claims", [])],
             *[n["description"] for n in answer.get("conflicts", [])], answer.get("clarifying_question") or ""]  # fmt: skip
    return "\n".join(p for p in parts if p)
