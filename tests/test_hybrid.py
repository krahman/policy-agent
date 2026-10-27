import httpx

from policy_agent.retrieval import hybrid
from policy_agent.retrieval.bm25 import Hit
from policy_agent.retrieval.hybrid import Reranker, allowed_by_period, periods_in, rrf


def hit(cid: str, rank: int) -> Hit:
    return Hit({"chunk_id": cid, "text": cid}, 0.0, rank)


def test_rrf_rewards_agreement_and_is_deterministic():
    a = [hit("x", 1), hit("y", 2), hit("z", 3)]
    b = [hit("y", 1), hit("w", 2), hit("x", 3)]
    fused = rrf([a, b])
    assert [h.chunk["chunk_id"] for h in fused][:2] == ["y", "x"]  # present in both lists
    assert [h.rank for h in fused] == list(range(1, len(fused) + 1))
    assert [h.chunk["chunk_id"] for h in rrf([a, b])] == [h.chunk["chunk_id"] for h in fused]


def test_rrf_ties_break_by_chunk_id():
    fused = rrf([[hit("b", 1)], [hit("a", 1)]])
    assert [h.chunk["chunk_id"] for h in fused] == ["a", "b"]


def test_periods_in():
    assert periods_in("unemployment in 2Q 2025?") == {"2025-Q2"}
    assert periods_in("What was it in Q3 2024") == {"2024-Q3"}
    assert periods_in("citizen rate in September 2025") == {"2025-Q3"}
    assert periods_in("from 2Q 2022 to 2Q 2026") == {"2022-Q2", "2026-Q2"}  # the bare years are inside the quarters
    assert periods_in("annual average for 2024") == {"2024", "2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"}
    assert periods_in("the latest quarter") == set()


def test_filter_never_drops_undated_chunks():
    ps = {"2025-Q2"}
    assert allowed_by_period({"reference_period": "2025-Q2"}, ps)
    assert not allowed_by_period({"reference_period": "2024-Q2"}, ps)
    for undated in (None, "None", ""):
        assert allowed_by_period({"reference_period": undated}, ps)
    assert allowed_by_period({"reference_period": "2024-Q2"}, set())  # no period in question => no filter


def test_reranker_orders_by_score_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid, "RERANK_CACHE", tmp_path / "rr.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        req = httpx.Request("POST", url)
        return httpx.Response(200, request=req, json={"results": [
            {"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.9}]})  # fmt: skip

    monkeypatch.setattr(hybrid.httpx, "post", fake_post)
    rr = Reranker()
    out = rr.rerank("q", [hit("a", 1), hit("b", 2)])
    assert [h.chunk["chunk_id"] for h in out] == ["b", "a"]
    rr.rerank("q", [hit("a", 1), hit("b", 2)])
    assert len(calls) == 1 and rr.usage.searches == 1 and rr.usage.cache_hits == 1
    assert len(Reranker().cache) == 1  # persisted to disk


def test_period_groups_one_group_per_named_period():
    from policy_agent.retrieval.hybrid import period_groups

    assert period_groups("from 2Q 2022 to 2Q 2026") == [{"2022-Q2"}, {"2026-Q2"}]
    assert period_groups("annual average for 2024") == [{"2024", "2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"}]
    assert period_groups("in September 2025") == [{"2025-Q3"}] and period_groups("the latest quarter") == []
