"""Judge evaluators with the model call replaced; checks applicability and score arithmetic only."""

from policy_agent.eval import judges
from policy_agent.eval.judges import Grounding, Relevance, Verdict
from policy_agent.retrieval.corpus import load_chunks

CH = load_chunks()[0]
OUT = {"status": "answered", "citations": [{"chunk_id": CH["chunk_id"], "quote": "q"}],
       "answer": {"status": "answered", "summary": "s", "claims": [{"kind": "source_fact", "text": "c"}]}}  # fmt: skip


def test_groundedness_is_the_supported_fraction(monkeypatch):
    out = {"status": "answered", "answer": {"claims": [
        {"kind": "source_fact", "text": "a", "citations": [{"chunk_id": CH["chunk_id"], "quote": "q"}]},
        {"kind": "source_fact", "text": "b", "citations": []}]}}  # fmt: skip
    monkeypatch.setattr(judges, "ask", lambda schema, s, h, model=None: Grounding(verdicts=[
        Verdict(claim=1, supported=True), Verdict(claim=2, supported=False)]))  # fmt: skip
    r = judges.groundedness({"question": "q"}, out, {})
    assert r["score"] == 0.5 and "[2]" in r["comment"]


def test_missing_verdict_counts_as_unsupported(monkeypatch):
    monkeypatch.setattr(judges, "ask", lambda *a, **k: Grounding(verdicts=[Verdict(claim=1, supported=True)]))
    claims = [{"kind": "source_fact", "text": "a", "citations": []}] * 2
    assert [v.supported for v in judges.judge_claims(claims)] == [True, False]


def test_groundedness_not_applicable_without_an_answer(monkeypatch):
    monkeypatch.setattr(judges, "ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no judge call expected")))
    assert judges.groundedness({"question": "q"}, {"status": "abstained", "citations": []}, {})["value"] == "n/a"
    assert judges.groundedness({"question": "q"}, {"status": "answered", "citations": []}, {})["value"] == "n/a"


def test_conflict_handling_only_for_conflict_cases(monkeypatch):
    monkeypatch.setattr(judges, "ask", lambda *a, **k: judges.ConflictVerdict(passed=True))
    assert judges.conflict_handling({"question": "q"}, OUT, {"expected_status": "answered"})["value"] == "n/a"
    assert judges.conflict_handling({"question": "q"}, OUT, {"expected_status": "conflict_reported"})["score"] == 1.0


def test_relevance_score_passthrough(monkeypatch):
    monkeypatch.setattr(judges, "ask", lambda *a, **k: Relevance(score=4, reason="r"))
    assert judges.answer_relevance({"question": "q"}, OUT, {})["score"] == 4.0


def test_judge_model_differs_from_generators():
    assert not judges.JUDGE_MODEL.startswith("anthropic/")  # cross-family judge (PRD §8.1)


def test_perturb_changes_a_value_but_not_period_labels():
    assert judges.perturb("The rate was 2.8% in 2Q 2025.") == "The rate was 3.1% in 2Q 2025."
    assert judges.perturb("There were 4,620 retrenchments in 2Q 2026.") == "There were 5,082 retrenchments in 2Q 2026."
    assert judges.perturb("In 2Q 2026 and 2025 nothing is stated.") is None


def test_perturb_ignores_a_year_followed_by_a_comma():
    assert judges.perturb("For December 2025, the ratio was 0.5") == "For December 2025, the ratio was 0.8"
