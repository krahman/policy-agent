import numpy as np
import pytest

from policy_agent.baselines import b0
from policy_agent.eval import evaluators as ev
from policy_agent.generation.schema import Answer
from policy_agent.ingest.paths import PROCESSED
from policy_agent.retrieval import corpus, dense
from policy_agent.retrieval.bm25 import BM25Retriever

HAS = (PROCESSED / "chunks.jsonl").exists() and (PROCESSED / "stats.parquet").exists()
needs = pytest.mark.skipif(not HAS, reason="run `make ingest` first")


def test_tokenizer_joins_thousands_separators():
    assert corpus.tokenize("4,620 in 2Q 2026 (2.0%)") == ["4620", "in", "2q", "2026", "2.0"]
    assert corpus.tokenize("1,234,567") == ["1234567"]


@needs
def test_role_filter_is_applied_before_ranking():
    public = {c["chunk_id"] for c in corpus.visible_chunks("analyst_public")}
    internal = {c["chunk_id"] for c in corpus.visible_chunks("analyst_internal")}
    restricted = {c["chunk_id"] for c in corpus.load_chunks() if c["access_level"] == "internal"}
    assert restricted and not (restricted & public) and restricted <= internal
    q = "internal planning memo deadline sector deep-dive decision end of October"
    assert not ({h.chunk["chunk_id"] for h in BM25Retriever("analyst_public").search(q, 50)} & restricted)
    assert {h.chunk["chunk_id"] for h in BM25Retriever("analyst_internal").search(q, 3)} & restricted
    with pytest.raises(ValueError):
        corpus.visible_chunks("anonymous")


@needs
def test_bm25_is_deterministic_and_ranked():
    r = BM25Retriever("analyst_public")
    a, b = r.search("retrenchments 2Q 2026", 10), r.search("retrenchments 2Q 2026", 10)
    assert [h.chunk["chunk_id"] for h in a] == [h.chunk["chunk_id"] for h in b]
    assert [h.rank for h in a] == list(range(1, 11))
    assert all(a[i].score >= a[i + 1].score for i in range(9))


@needs
def test_b0_returns_its_best_passage_with_the_output_contract():
    out = b0.run({"question": "How many employees were retrenched in 2Q 2026?", "user_role": "analyst_public"})
    assert out["status"] == "answered" and out["usage"] is None and out["latency_ms"] >= 0
    assert len(out["retrieved"]) == 10 and out["citations"][0]["chunk_id"] == out["retrieved"][0]
    assert ev.citation_exists(out, {"expected_status": "answered"})["score"] == 1.0


# --- dense retrieval and B1 without the network ---------------------------------------------


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        return [[float("alpha" in t), float("beta" in t), 1.0] for t in texts]


def test_embedding_cache_avoids_repeat_calls(tmp_path, monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr(dense, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(dense, "embedder", lambda model: fake)
    c1 = dense.EmbeddingCache("m/x")
    c1.path = tmp_path / "m__x.jsonl"
    a = c1.embed(["alpha one", "beta two"])
    assert fake.calls == 1 and a.shape == (2, 3)
    c1.embed(["alpha one"])
    assert fake.calls == 1  # served from memory
    c2 = dense.EmbeddingCache("m/x")
    c2.path = tmp_path / "m__x.jsonl"
    c2.vecs = {}
    c2.vecs.update({__import__("json").loads(line)["k"]: 1 for line in c1.path.read_text().splitlines()})
    assert len(c2.vecs) == 2  # persisted to disk


def test_dense_ranking_uses_cosine(monkeypatch):
    class Stub(dense.DenseRetriever):
        def __init__(self):
            self.chunks = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
            self.matrix = dense._normalise(np.array([[1.0, 0], [0.8, 0.6], [0, 1.0]], dtype=np.float32))

            class C:
                def embed(self, texts, stats=None):
                    return np.array([[1.0, 0.0]], dtype=np.float32)

            self.cache = C()

    hits = Stub().search("q", 3)
    assert [h.chunk["chunk_id"] for h in hits] == ["a", "b", "c"] and hits[0].score == pytest.approx(1.0)


class Raw:
    usage_metadata = {"input_tokens": 100, "output_tokens": 20}


def test_answer_text_flattens_all_fields():
    a = Answer(status="needs_clarification", summary="s", clarifying_question="Which measure?")
    assert a.text() == "s\nWhich measure?"
