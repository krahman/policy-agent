"""B0: BM25 top-k passages returned verbatim, no LLM. Floor for retrieval and for 'is the LLM adding value?'."""

import time

from policy_agent.retrieval.bm25 import get_bm25

TOP_K = 10
ANSWER_K = 1  # the best passage is the 'answer'; more would let a numeric match happen by chance


def run(inputs: dict) -> dict:
    t0 = time.perf_counter()
    hits = get_bm25(inputs.get("user_role", "analyst_public")).search(inputs["question"], TOP_K)
    top = hits[:ANSWER_K]
    return {
        # no abstention logic: a retrieval system always returns its best passages
        "status": "answered",
        "text": "\n\n".join(h.chunk["text"] for h in top),
        "citations": [{"chunk_id": h.chunk["chunk_id"], "quote": h.chunk["text"][:200]} for h in top],
        "retrieved": [h.chunk["chunk_id"] for h in hits],
        "latency_ms": (time.perf_counter() - t0) * 1000,
        "usage": None,
        "schema_valid": None,
        "error": None,
    }
