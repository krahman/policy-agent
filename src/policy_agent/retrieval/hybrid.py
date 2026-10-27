"""R3 hybrid (BM25 + dense, reciprocal rank fusion), R4 (+ hosted re-rank) and R5 (+ metadata filter). PRD §7.2."""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from policy_agent.ingest.paths import PROCESSED
from policy_agent.retrieval.bm25 import BM25Retriever, Hit
from policy_agent.retrieval.corpus import visible_chunks
from policy_agent.retrieval.dense import DEFAULT_EMBEDDING, DenseRetriever

RRF_K = 60  # the constant from the original RRF paper; not tuned on dev
POOL = 50  # candidates taken from each retriever before fusion
RERANK_MODEL = "cohere/rerank-v3.5"
RERANK_POOL = 20  # PRD §7.2: R3 top-20 go to the re-ranker
RERANK_USD_PER_SEARCH = 0.001  # OpenRouter reports $0.001 per search unit (up to 100 documents)
RERANK_CACHE = PROCESSED / "embeddings" / "rerank_cache.jsonl"


def rrf(rankings: list[list[Hit]], k: int = RRF_K) -> list[Hit]:
    """Reciprocal rank fusion: score(d) = sum 1/(k + rank). Ties broken by chunk_id for determinism."""
    score: dict[str, float] = {}
    chunk: dict[str, dict] = {}
    for ranking in rankings:
        for h in ranking:
            cid = h.chunk["chunk_id"]
            score[cid] = score.get(cid, 0.0) + 1.0 / (k + h.rank)
            chunk[cid] = h.chunk
    order = sorted(score, key=lambda c: (-score[c], c))
    return [Hit(chunk[c], score[c], r + 1) for r, c in enumerate(order)]


# ---- R5: metadata filter extracted from the question (rule-based stand-in for the Step 8 router) ----
_Q = re.compile(r"\b([1-4])Q\s*(20\d\d)\b|\bQ([1-4])\s*(20\d\d)\b", re.I)
_MONTH = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d\d)\b", re.I
)
_YEAR = re.compile(r"\b(20[12]\d)\b")
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]  # fmt: skip


def periods_in(question: str) -> set[str]:
    """Reference periods the question names: '2Q 2025' -> 2025-Q2, 'September 2025' -> 2025-Q3, bare '2024' -> the
    year and its four quarters. Empty set when the question names none (then no filter is applied)."""
    out: set[str] = set()
    spans = []
    for m in _Q.finditer(question):
        q, y = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        out.add(f"{y}-Q{q}")
        spans.append(m.span())
    for m in _MONTH.finditer(question):
        out.add(f"{m.group(2)}-Q{_MONTHS.index(m.group(1).lower()) // 3 + 1}")
        spans.append(m.span())
    for m in _YEAR.finditer(question):
        if not any(a <= m.start() < b for a, b in spans):
            y = m.group(1)
            out |= {y, *(f"{y}-Q{i}" for i in range(1, 5))}
    return out


def period_groups(question: str) -> list[set[str]]:
    """One group per period the question names; a group is satisfied by any member. A quarter is its own group; a bare
    year is satisfied by the year or any of its quarters."""
    groups: list[set[str]] = []
    spans = []
    for m in _Q.finditer(question):
        q, y = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        groups.append({f"{y}-Q{q}"})
        spans.append(m.span())
    for m in _MONTH.finditer(question):
        groups.append({f"{m.group(2)}-Q{_MONTHS.index(m.group(1).lower()) // 3 + 1}"})
        spans.append(m.span())
    for m in _YEAR.finditer(question):
        if not any(a <= m.start() < b for a, b in spans):
            y = m.group(1)
            groups.append({y, *(f"{y}-Q{i}" for i in range(1, 5))})
    return groups


def allowed_by_period(chunk: dict, periods: set[str]) -> bool:
    """Chunks with no reference period (explainers, replies, memos) are never filtered out."""
    rp = chunk.get("reference_period")
    return not periods or rp in (None, "None", "") or rp in periods


@dataclass
class RerankUsage:
    searches: int = 0
    cache_hits: int = 0


@dataclass
class Reranker:
    model: str = RERANK_MODEL
    usage: RerankUsage = field(default_factory=RerankUsage)

    def __post_init__(self):
        self.cache: dict[str, list[float]] = {}
        if RERANK_CACHE.exists():
            for line in RERANK_CACHE.read_text().splitlines():
                row = json.loads(line)
                self.cache[row["k"]] = row["scores"]

    def _key(self, query: str, hits: list[Hit]) -> str:
        ids = "|".join(h.chunk["chunk_id"] for h in hits)
        return hashlib.sha1(f"{self.model}\n{query}\n{ids}".encode()).hexdigest()

    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        key = self._key(query, hits)
        scores = self.cache.get(key)
        if scores is None:
            r = httpx.post(
                os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") + "/rerank",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                json={"model": self.model, "query": query, "documents": [h.chunk["text"] for h in hits],
                      "top_n": len(hits)},
                timeout=30,
            )  # fmt: skip
            r.raise_for_status()
            scores = [0.0] * len(hits)
            for res in r.json()["results"]:
                scores[res["index"]] = res["relevance_score"]
            self.cache[key] = scores
            RERANK_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(RERANK_CACHE, "a") as f:
                f.write(json.dumps({"k": key, "scores": scores}) + "\n")
            self.usage.searches += 1
        else:
            self.usage.cache_hits += 1
        order = sorted(range(len(hits)), key=lambda i: (-scores[i], hits[i].chunk["chunk_id"]))
        return [Hit(hits[i].chunk, scores[i], r + 1) for r, i in enumerate(order)]


class HybridRetriever:
    """mode: 'r3' fusion only, 'r4' fusion + re-rank, 'r5' = r4 with the question-derived period filter applied
    to both candidate lists *before* ranking (access control is already applied by `visible_chunks`)."""

    def __init__(self, role: str = "analyst_public", mode: str = "r3", embedding: str = DEFAULT_EMBEDDING):
        assert mode in ("r3", "r4", "r5")
        self.mode, self.role = mode, role
        self.bm25 = BM25Retriever(role)
        self.dense = DenseRetriever(role, embedding)
        self.reranker = Reranker() if mode in ("r4", "r5") else None
        self.n_visible = len(visible_chunks(role))

    def search(self, query: str, k: int = 10) -> list[Hit]:
        periods = periods_in(query) if self.mode == "r5" else set()

        def keep(hits: list[Hit]) -> list[Hit]:
            kept = [h for h in hits if allowed_by_period(h.chunk, periods)]
            return [Hit(h.chunk, h.score, r + 1) for r, h in enumerate(kept)]

        # with a filter, search deeper so that POOL candidates survive it
        depth = POOL if not periods else self.n_visible
        lists = [keep(self.bm25.search(query, depth))[:POOL], keep(self.dense.search(query, depth))[:POOL]]
        fused = rrf(lists)
        if self.reranker is None:
            return fused[:k]
        return self.reranker.rerank(query, fused[:RERANK_POOL])[:k]


@lru_cache(maxsize=8)
def get_hybrid(role: str, mode: str, embedding: str = DEFAULT_EMBEDDING) -> HybridRetriever:
    return HybridRetriever(role, mode, embedding)
