"""Chain control flow with a fake model: first-pass validation, one repair, then downgrade. No network."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage

from policy_agent.generation import chain
from policy_agent.generation.schema import Answer, Citation, Claim
from policy_agent.retrieval.bm25 import Hit
from policy_agent.retrieval.corpus import load_chunks

CH = next(c for c in load_chunks() if c["access_level"] == "public" and c["doc_type"] == "stat_card")


class FakeStructured:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def invoke(self, messages):
        self.calls.append(messages)
        a = self.answers.pop(0)
        raw = AIMessage(content="", usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})
        return {"raw": raw, "parsed": a, "parsing_error": None if a is not None else "bad"}


def good():
    q = CH["text"][:100]
    return Answer(status="answered", summary="ok", claims=[Claim(text="x", kind="source_fact",
                  citations=[Citation(source_id=CH["source_id"], chunk_id=CH["chunk_id"], quote=q)])])  # fmt: skip


def bad():
    return Answer(status="answered", summary="ok", claims=[Claim(text="x", kind="source_fact", citations=[])])


def build(monkeypatch, answers, repair=True):
    fake = FakeStructured(answers)
    monkeypatch.setattr(chain, "_llm", lambda *a, **k: SimpleNamespace(with_structured_output=lambda *a, **k: fake))
    hybrid = SimpleNamespace(search=lambda q, k: [Hit(CH, 1.0, 1)], reranker=None)
    monkeypatch.setattr(chain, "get_hybrid", lambda *a, **k: hybrid)
    run, _ = chain.make_target("m", "e", repair=repair)
    return run, fake


def test_valid_first_pass_makes_one_call(monkeypatch):
    run, fake = build(monkeypatch, [good()])
    out = run({"question": "q"})
    assert out["status"] == "answered" and out["schema_valid"] and len(fake.calls) == 1
    assert out["validation"] == {"first_pass": [], "repaired": False, "downgraded": False}
    assert out["usage"]["input_tokens"] == 100


def test_violation_triggers_one_repair_with_the_errors_in_the_prompt(monkeypatch):
    run, fake = build(monkeypatch, [bad(), good()])
    out = run({"question": "q"})
    assert out["status"] == "answered" and len(fake.calls) == 2
    assert out["validation"]["repaired"] and out["validation"]["first_pass"][0].startswith("V5")
    assert "V5" in fake.calls[1][-1].content  # the repair message lists the failed rule
    assert out["usage"]["input_tokens"] == 200  # both calls are counted


def test_failed_repair_downgrades_to_abstained(monkeypatch):
    run, fake = build(monkeypatch, [bad(), bad()])
    out = run({"question": "q"})
    assert out["status"] == "abstained" and out["validation"]["downgraded"] and not out["citations"]
    assert len(fake.calls) == 2  # exactly one repair attempt


def test_unparseable_first_output_counts_against_schema_valid(monkeypatch):
    run, _ = build(monkeypatch, [None, good()])
    out = run({"question": "q"})
    assert out["schema_valid"] is False and out["status"] == "answered" and out["validation"]["repaired"]


def test_evidence_budget_keeps_at_least_one_block():
    hits = [Hit(CH, 1.0, 1), Hit(CH, 0.9, 2)]
    text, kept = chain.format_evidence(hits, budget=1)
    assert len(kept) == 1 and "<untrusted_evidence" in text


def test_chain_does_not_use_forced_tool_calling(monkeypatch):
    """claude-sonnet-5.5 rejects forced tool_choice (HTTP 400), which made every E5 call fail in the first run."""
    seen = {}

    def fake_llm(*a, **k):
        def wso(schema, method=None, include_raw=None):
            seen["method"] = method
            return FakeStructured([])

        return SimpleNamespace(with_structured_output=wso)

    monkeypatch.setattr(chain, "_llm", fake_llm)
    chain.make_target("anthropic/claude-sonnet-5.5", "e")
    assert seen["method"] == "json_schema"


def test_truncated_output_is_repaired_not_a_crash(monkeypatch):
    from openai import LengthFinishReasonError

    class Truncating(FakeStructured):
        def invoke(self, messages):
            if not self.calls:
                self.calls.append(messages)
                raise LengthFinishReasonError(completion=SimpleNamespace(usage=None, choices=[]))
            return super().invoke(messages)

    fake = Truncating([good()])
    monkeypatch.setattr(chain, "_llm", lambda *a, **k: SimpleNamespace(with_structured_output=lambda *a, **k: fake))
    monkeypatch.setattr(
        chain, "get_hybrid", lambda *a, **k: SimpleNamespace(search=lambda q, k: [Hit(CH, 1.0, 1)], reranker=None)
    )
    run, _ = chain.make_target("m", "e")
    out = run({"question": "q"})
    assert out["status"] == "answered" and out["validation"]["repaired"] and out["schema_valid"] is False
    assert "token limit" in out["validation"]["first_pass"][0]
