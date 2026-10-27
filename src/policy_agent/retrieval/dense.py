"""Dense retriever: hosted embeddings through OpenRouter, cached on disk by (model, text hash)."""

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from policy_agent.ingest.paths import PROCESSED
from policy_agent.retrieval.bm25 import Hit
from policy_agent.retrieval.corpus import visible_chunks

DEFAULT_EMBEDDING = "openai/text-embedding-3-small"
CACHE_DIR = PROCESSED / "embeddings"
BATCH = 128


def embedder(model: str = DEFAULT_EMBEDDING) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=model,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        check_embedding_ctx_length=False,  # send raw strings, not OpenAI token ids
    )


def _key(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


@dataclass
class EmbeddingStats:
    requested: int = 0
    cache_hits: int = 0
    tokens_estimate: int = 0


class EmbeddingCache:
    """JSONL cache: one file per model, so experiments do not re-pay embedding cost (PRD §7.2)."""

    def __init__(self, model: str):
        self.model = model
        self.path = CACHE_DIR / (model.replace("/", "__") + ".jsonl")
        self.vecs: dict[str, list[float]] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                row = json.loads(line)
                self.vecs[row["k"]] = row["v"]

    def embed(self, texts: list[str], stats: EmbeddingStats | None = None) -> np.ndarray:
        stats = stats or EmbeddingStats()
        missing = sorted({t for t in texts if _key(t) not in self.vecs}, key=_key)
        stats.requested += len(texts)
        stats.cache_hits += len(texts) - len([t for t in texts if t in set(missing)])
        if missing:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            emb = embedder(self.model)
            with open(self.path, "a") as f:
                for i in range(0, len(missing), BATCH):
                    batch = missing[i : i + BATCH]
                    for t, v in zip(batch, emb.embed_documents(batch), strict=True):
                        self.vecs[_key(t)] = v
                        f.write(json.dumps({"k": _key(t), "v": v}) + "\n")
                    stats.tokens_estimate += sum(len(t) // 4 for t in batch)
        return np.array([self.vecs[_key(t)] for t in texts], dtype=np.float32)


def _normalise(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12, None)


class DenseRetriever:
    """Cosine similarity on L2-normalised vectors (inner product)."""

    def __init__(self, role: str = "analyst_public", model: str = DEFAULT_EMBEDDING):
        self.model = model
        self.chunks = visible_chunks(role)
        self.cache = EmbeddingCache(model)
        self.stats = EmbeddingStats()
        self.matrix = _normalise(self.cache.embed([c["text"] for c in self.chunks], self.stats))

    def search(self, query: str, k: int = 10) -> list[Hit]:
        q = _normalise(self.cache.embed([query]))[0]
        scores = self.matrix @ q
        order = np.argsort(-scores, kind="stable")[:k]
        return [Hit(self.chunks[i], float(scores[i]), r + 1) for r, i in enumerate(order)]


@lru_cache(maxsize=8)
def get_dense(role: str, model: str = DEFAULT_EMBEDDING) -> DenseRetriever:
    return DenseRetriever(role, model)
