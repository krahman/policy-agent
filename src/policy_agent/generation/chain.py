"""Validated single-pass chain (E5/E6): R5 retrieval, prompt, structured Answer, V1-V6, one repair, then downgrade."""

import hashlib
import json
import os
import re
import time
from functools import lru_cache
from typing import Any, Literal

import tiktoken
import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import LengthFinishReasonError
from pydantic import SecretStr

from policy_agent.generation.schema import Answer, Citation, Claim, ConflictNote
from policy_agent.generation.validate import Violation, downgrade, parse, validate
from policy_agent.ingest.paths import ROOT
from policy_agent.retrieval.corpus import load_chunks
from policy_agent.retrieval.hybrid import RERANK_USD_PER_SEARCH, get_hybrid

PROMPT_FILE = ROOT / "prompts" / "answer_v1.yaml"
FEWSHOT_FILE = ROOT / "eval" / "data" / "fewshot_pool.jsonl"
FEWSHOT_IDS = ("S1", "S3", "S5")  # answered, abstained, conflict (PRD §8.4); clarification is taught by the rules
EVIDENCE_TOKEN_BUDGET = 3500  # per-section budget enforced in code (PRD §8.4)
_ENC = tiktoken.get_encoding("cl100k_base")


def load_prompt() -> dict:
    raw = PROMPT_FILE.read_text()
    p = yaml.safe_load(raw)
    p["sha256_12"] = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return p


def format_evidence(hits, budget: int = EVIDENCE_TOKEN_BUDGET) -> tuple[str, list[dict]]:
    """Evidence blocks in re-rank order; stops adding blocks once the token budget would be exceeded."""
    blocks: list[str] = []
    kept: list[dict] = []
    used = 0
    for h in hits:
        c = h.chunk
        block = (
            f'<untrusted_evidence chunk_id="{c["chunk_id"]}" source_id="{c["source_id"]}" type="{c["doc_type"]}" '
            f'date="{c["pub_date"]}">\n{c["text"]}\n</untrusted_evidence>'
        )
        n = len(_ENC.encode(block))
        if kept and used + n > budget:
            break
        blocks.append(block)
        kept.append({"chunk_id": c["chunk_id"], "source_id": c["source_id"], "text": c["text"]})
        used += n
    return "\n\n".join(blocks), kept


@lru_cache(maxsize=1)
def fewshot_text() -> str:
    """Worked examples built from the pool and real chunk text, so every quote is verbatim (tested against V1-V6)."""
    by_id = {c["chunk_id"]: c for c in load_chunks()}
    pool = {r["id"]: r for r in map(json.loads, FEWSHOT_FILE.read_text().splitlines())}
    parts = []
    for sid in FEWSHOT_IDS:
        r = pool[sid]
        chunks = [by_id[i] for i in r["chunk_ids"]]
        ev = "\n".join(
            f'<untrusted_evidence chunk_id="{c["chunk_id"]}" source_id="{c["source_id"]}">\n'
            f"{c['text']}\n</untrusted_evidence>"
            for c in chunks
        )
        ans = example_answer(r, chunks).model_dump_json(exclude_defaults=True)
        parts.append(f"Question: {r['question']}\nEvidence:\n{ev or '(nothing relevant)'}\nAnswer:\n{ans}")
    return "\n\n".join(parts)


def _quote(text: str, answer: str) -> str:
    """A verbatim 200-character window around the first figure of `answer` that the chunk contains."""
    for tok in re.findall(r"\d[\d,]*(?:\.\d+)?", answer):
        i = text.find(tok)
        if i >= 0:
            return text[max(0, i - 80) : max(0, i - 80) + 200]
    return text[:200]


def example_answer(r: dict, chunks: list[dict]) -> Answer:
    cites = [
        Citation(source_id=c["source_id"], chunk_id=c["chunk_id"], quote=_quote(c["text"], r["answer"])) for c in chunks
    ]
    if r["status"] == "answered":
        return Answer(status="answered", summary=r["answer"], confidence="high",
                      claims=[Claim(text=r["answer"], kind="statistical_finding", citations=cites)])  # fmt: skip
    if r["status"] == "conflict_reported":
        return Answer(
            status="conflict_reported", summary=r["answer"], confidence="medium",
            claims=[Claim(text=r["answer"], kind="source_fact", citations=cites)],
            conflicts=[ConflictNote(description=r["answer"], values=[], sources=[c["source_id"] for c in chunks])],
        )  # fmt: skip
    return Answer(status="abstained", summary=r["answer"], confidence="high", limitations=[r["answer"]])


@lru_cache(maxsize=8)
def _llm(model: str, max_tokens: int) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
        max_completion_tokens=max_tokens,
    )


def make_target(
    model: str,
    embedding: str,
    k: int = 5,
    max_tokens: int = 1500,
    retriever: str = "r5",
    repair: bool = True,
    structured_output: Literal["function_calling", "json_mode", "json_schema"] = "json_schema",
):
    prompt = load_prompt()
    # json_schema, not function_calling: claude-sonnet-5.5 rejects the forced tool_choice that function_calling sends
    structured = _llm(model, max_tokens).with_structured_output(Answer, method=structured_output, include_raw=True)
    system = SystemMessage(content=prompt["system"].replace("{examples}", fewshot_text()))

    def call(messages: list, usage: dict) -> tuple[Answer | None, list[Violation], Any]:
        try:
            res = structured.invoke(messages)
        except (
            LengthFinishReasonError
        ):  # the answer hit max_tokens: treat as a schema failure so the retry asks for less
            return None, [Violation("V1", "output was cut off at the token limit; give a shorter answer")], None
        um = getattr(res["raw"], "usage_metadata", None) or {}
        usage["input_tokens"] += um.get("input_tokens", 0)
        usage["output_tokens"] += um.get("output_tokens", 0)
        if res["parsed"] is None:
            return None, [Violation("V1", f"schema does not parse: {str(res['parsing_error'])[:200]}")], res["raw"]
        parsed, v1 = parse(res["parsed"])
        return parsed, v1, res["raw"]

    def run(inputs: dict) -> dict:
        t0 = time.perf_counter()
        role = inputs.get("user_role", "analyst_public")
        h = get_hybrid(role, retriever, embedding)
        before = h.reranker.usage.searches if h.reranker else 0
        hits = h.search(inputs["question"], 10)
        evidence, kept = format_evidence(hits[:k])
        ev_ids = {e["chunk_id"] for e in kept}
        usage: dict = {"model": model, "input_tokens": 0, "output_tokens": 0}
        usage["extra_cost_usd"] = ((h.reranker.usage.searches - before) * RERANK_USD_PER_SEARCH) if h.reranker else 0.0
        human = HumanMessage(content=prompt["human"].format(question=inputs["question"], evidence=evidence))
        out: dict[str, Any] = {
            "retrieved": [x.chunk["chunk_id"] for x in hits], "evidence": kept, "usage": usage, "error": None,
            "schema_valid": False, "validation": {"first_pass": [], "repaired": False, "downgraded": False},
        }  # fmt: skip
        try:
            ans, viol, raw = call([system, human], usage)
            out["schema_valid"] = ans is not None  # parsed on the first try, before any repair
            if ans is not None:
                viol += validate(ans, role, ev_ids)
            out["validation"]["first_pass"] = [str(v) for v in viol]
            if viol and repair:
                fix = HumanMessage(content=prompt["repair"].format(violations="\n".join(f"- {v}" for v in viol)))
                prev = raw if isinstance(raw, AIMessage) else AIMessage(content=ans.model_dump_json() if ans else "")
                ans2, viol2, _ = call([system, human, prev, fix], usage)
                if ans2 is not None:
                    viol2 += validate(ans2, role, ev_ids)
                out["validation"]["repaired"] = not viol2
                ans, viol = ans2, viol2
            if viol:
                ans = downgrade(ans, viol)
                out["validation"]["downgraded"] = True
                out["validation"]["final"] = [str(v) for v in viol]
            assert ans is not None
            cites = [c for cl in ans.claims for c in cl.citations]
            out |= {"status": ans.status, "text": ans.text(), "answer": ans.model_dump(),
                    "citations": [{"chunk_id": c.chunk_id, "quote": c.quote} for c in cites]}  # fmt: skip
        except Exception as e:  # noqa: BLE001 - a run records failures, it does not crash the experiment
            out |= {"status": "abstained", "text": "", "citations": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
        out["latency_ms"] = (time.perf_counter() - t0) * 1000
        return out

    return run, prompt
