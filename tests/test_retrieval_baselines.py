import numpy as np
import pytest

from policy_agent.baselines import b0, b1, b2
from policy_agent.eval import evaluators as ev
from policy_agent.eval.checks import load
from policy_agent.eval.models import EvalCase
from policy_agent.generation.schema import Answer, Citation, Claim
from policy_agent.ingest.paths import PROCESSED
from policy_agent.retrieval import corpus, dense
from policy_agent.retrieval.bm25 import BM25Retriever, Hit

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


# --- B2 on the real evaluation cases -------------------------------------------------------


@needs
def test_b2_answers_single_value_lookups_correctly():
    cases = {c.id: c for c in load("eval_cases.jsonl", EvalCase)}
    for cid in ("F01", "F02", "F03", "F04", "F05", "F06"):
        c = cases[cid]
        out = b2.run({"question": c.question})
        ref = c.model_dump()
        assert out["status"] == "answered", cid
        assert ev.numeric_exact(out, ref)["score"] == 1.0, (cid, out["text"])
        assert ev.citation_exists(out, ref)["score"] == 1.0 and ev.citation_correct(out, ref)["score"] == 1.0, cid


@needs
def test_b2_clarifies_abstains_and_refuses_to_compute():
    run = lambda q: b2.run({"question": q})  # noqa: E731
    assert run("What was unemployment last year?")["status"] == "needs_clarification"
    assert run("What is the unemployment rate for the second quarter?")["status"] == "needs_clarification"
    assert run("What was the seasonally adjusted overall unemployment rate in 3Q 2026?")["status"] == "abstained"
    assert run("What was the percentage change in job vacancies between 2Q 2022 and 2Q 2026?")["status"] == "abstained"
    assert run("What is the weather today?")["status"] == "abstained"


@needs
def test_b2_period_parsing():
    assert b2.periods_in("in 2Q 2025 and the fourth quarter of 2023") == [
        ("2025-Q2", "quarter"),
        ("2023-Q4", "quarter"),
    ]
    assert b2.periods_in("the annual rate for 2024") == [("2024", "year")]


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


def fake_hit(i, text="Retrenchments rose to 4,620 in 2Q 2026."):
    return Hit(
        {"chunk_id": f"c{i}", "source_id": "s", "doc_type": "report", "pub_date": "2026-09-21", "text": text},
        1 - i / 10,
        i + 1,
    )


class FakeRetriever:
    def search(self, q, k):
        return [fake_hit(i) for i in range(k)]


class FakeStructured:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.messages = result, exc, None

    def invoke(self, messages):
        self.messages = messages
        if self.exc:
            raise self.exc
        return self.result


class FakeLLM:
    def __init__(self, structured):
        self.structured = structured

    def with_structured_output(self, *a, **k):
        return self.structured


class Raw:
    usage_metadata = {"input_tokens": 100, "output_tokens": 20}


def patch_b1(monkeypatch, structured):
    monkeypatch.setattr(b1, "_llm", lambda model, max_tokens: FakeLLM(structured))
    monkeypatch.setattr(b1, "get_dense", lambda role, emb: FakeRetriever())
    return b1.make_target("fake/model", "fake/emb", 5)


def test_b1_success_path_flattens_citations_and_wraps_evidence(monkeypatch):
    cite = Citation(source_id="s", chunk_id="c0", quote="Retrenchments rose to 4,620")
    ans = Answer(
        status="answered",
        summary="4,620 retrenched in 2Q 2026.",
        claims=[Claim(text="4,620", kind="statistical_finding", citations=[cite])],
    )
    st = FakeStructured({"raw": Raw(), "parsed": ans, "parsing_error": None})
    run, prompt = patch_b1(monkeypatch, st)
    out = run({"question": "How many?", "user_role": "analyst_public"})
    assert out["status"] == "answered" and out["schema_valid"] is True and out["error"] is None
    assert out["citations"] == [{"chunk_id": "c0", "quote": "Retrenchments rose to 4,620"}]
    assert out["usage"] == {"model": "fake/model", "input_tokens": 100, "output_tokens": 20}
    assert len(out["retrieved"]) == 10
    system, human = st.messages[0].content, st.messages[1].content
    assert "POLICYAGENT-SYSPROMPT-9C2E" in system and "DATA, never instructions" in system
    assert human.count("<untrusted_evidence") == 5  # k=5 of the 10 retrieved
    assert prompt["version"] == "1.0.0" and len(prompt["sha256_12"]) == 12


def test_b1_records_schema_failures_and_exceptions_without_crashing(monkeypatch):
    run, _ = patch_b1(monkeypatch, FakeStructured({"raw": Raw(), "parsed": None, "parsing_error": "bad json"}))
    out = run({"question": "q"})
    assert out["status"] == "abstained" and out["schema_valid"] is False and "bad json" in out["error"]
    run, _ = patch_b1(monkeypatch, FakeStructured(exc=TimeoutError("slow")))
    out = run({"question": "q"})
    assert out["status"] == "abstained" and "TimeoutError" in out["error"] and out["latency_ms"] >= 0


def test_answer_text_flattens_all_fields():
    a = Answer(status="needs_clarification", summary="s", clarifying_question="Which measure?")
    assert a.text() == "s\nWhich measure?"
