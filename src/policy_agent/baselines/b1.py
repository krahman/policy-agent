"""B1: single-pass RAG chain. Dense top-k -> one prompt -> structured Answer. No tools, no retries, no validation."""

import hashlib
import os
import time
from functools import lru_cache
from typing import Any

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr, ValidationError

from policy_agent.generation.schema import Answer
from policy_agent.ingest.paths import ROOT
from policy_agent.retrieval.dense import DEFAULT_EMBEDDING, get_dense

DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
PROMPT_FILE = ROOT / "prompts" / "b1_v1.yaml"


def load_prompt() -> dict:
    raw = PROMPT_FILE.read_text()
    p = yaml.safe_load(raw)
    p["sha256_12"] = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return p


def format_evidence(hits) -> str:
    blocks = []
    for h in hits:
        c = h.chunk
        blocks.append(
            f'<untrusted_evidence chunk_id="{c["chunk_id"]}" source_id="{c["source_id"]}" type="{c["doc_type"]}" '
            f'date="{c["pub_date"]}">\n{c["text"]}\n</untrusted_evidence>'
        )
    return "\n\n".join(blocks)


@lru_cache(maxsize=4)
def _llm(model: str, max_tokens: int) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
        max_completion_tokens=max_tokens,
    )


def make_target(model: str = DEFAULT_MODEL, embedding: str = DEFAULT_EMBEDDING, k: int = 5, max_tokens: int = 1500):
    prompt = load_prompt()
    structured = _llm(model, max_tokens).with_structured_output(Answer, method="function_calling", include_raw=True)

    def run(inputs: dict) -> dict:
        t0 = time.perf_counter()
        role = inputs.get("user_role", "analyst_public")
        retriever = get_dense(role, embedding)
        hits = retriever.search(inputs["question"], 10)
        messages = [
            SystemMessage(content=prompt["system"]),
            HumanMessage(
                content=prompt["human"].format(question=inputs["question"], evidence=format_evidence(hits[:k]))
            ),
        ]
        out: dict[str, Any] = {
            "retrieved": [h.chunk["chunk_id"] for h in hits],
            "citations": [], "usage": {"model": model}, "schema_valid": False, "error": None,
        }  # fmt: skip
        try:
            res = structured.invoke(messages)
            raw, parsed, perr = res["raw"], res["parsed"], res["parsing_error"]
            um = getattr(raw, "usage_metadata", None) or {}
            out["usage"] |= {"input_tokens": um.get("input_tokens", 0), "output_tokens": um.get("output_tokens", 0)}
            if parsed is None:
                out |= {"status": "abstained", "text": "", "error": f"schema: {perr}"}
            else:
                ans: Answer = parsed
                cites = [c for cl in ans.claims for c in cl.citations]
                out |= {
                    "status": ans.status, "text": ans.text(), "schema_valid": True,
                    "citations": [{"chunk_id": c.chunk_id, "quote": c.quote} for c in cites],
                    "answer": ans.model_dump(),
                }  # fmt: skip
        except (ValidationError, Exception) as e:  # noqa: BLE001 - a baseline records failures, it does not crash
            out |= {"status": "abstained", "text": "", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        out["latency_ms"] = (time.perf_counter() - t0) * 1000
        return out

    return run, prompt
