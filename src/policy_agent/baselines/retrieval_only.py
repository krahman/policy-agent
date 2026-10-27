"""Retrieval-only target for E1-E4: runs one retriever and returns the ranked chunk ids. No LLM."""

import time

from policy_agent.retrieval.bm25 import get_bm25
from policy_agent.retrieval.dense import DEFAULT_EMBEDDING, get_dense
from policy_agent.retrieval.hybrid import RERANK_USD_PER_SEARCH, get_hybrid

TOP_K = 10


def make_target(retriever: str, embedding: str = DEFAULT_EMBEDDING, k: int = TOP_K):
    def run(inputs: dict) -> dict:
        role = inputs.get("user_role", "analyst_public")
        t0 = time.perf_counter()
        extra = 0.0
        if retriever == "r1":
            hits = get_bm25(role).search(inputs["question"], k)
        elif retriever == "r2":
            hits = get_dense(role, embedding).search(inputs["question"], k)
        elif retriever in ("r3", "r4", "r5"):
            h = get_hybrid(role, retriever, embedding)
            before = h.reranker.usage.searches if h.reranker else 0
            hits = h.search(inputs["question"], k)
            extra = ((h.reranker.usage.searches - before) * RERANK_USD_PER_SEARCH) if h.reranker else 0.0
        else:
            raise ValueError(f"unknown retriever {retriever!r}")
        return {
            "retrieved": [x.chunk["chunk_id"] for x in hits],
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "usage": {"extra_cost_usd": extra},
        }

    return run
