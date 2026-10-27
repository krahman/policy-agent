"""BM25 retriever (rank_bm25). One index per role, built once; ties broken by chunk_id for determinism."""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from policy_agent.retrieval.corpus import tokenize, visible_chunks


@dataclass(frozen=True)
class Hit:
    chunk: dict
    score: float
    rank: int


class BM25Retriever:
    def __init__(self, role: str = "analyst_public", doc_types: set[str] | None = None):
        chunks = visible_chunks(role)
        if doc_types is not None:
            chunks = [c for c in chunks if c["doc_type"] in doc_types]
        self.chunks = chunks
        self.index = BM25Okapi([tokenize(c["text"]) for c in chunks])

    def search(self, query: str, k: int = 10) -> list[Hit]:
        scores = self.index.get_scores(tokenize(query))
        # stable sort on (-score, position); positions follow the chunk_id order of load_chunks()
        order = np.argsort(-scores, kind="stable")[:k]
        return [Hit(self.chunks[i], float(scores[i]), r + 1) for r, i in enumerate(order)]


@lru_cache(maxsize=4)
def get_bm25(role: str) -> BM25Retriever:
    return BM25Retriever(role)
