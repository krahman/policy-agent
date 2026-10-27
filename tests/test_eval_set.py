import json
import shutil

import pytest
from pydantic import ValidationError

from policy_agent.eval import build as eb
from policy_agent.eval import checks
from policy_agent.eval.models import ConflictValue, EvalCase, FewShot, RedteamCase, RetrievalCase
from policy_agent.ingest.paths import PROCESSED

HAS_DATA = (PROCESSED / "chunks.jsonl").exists() and (checks.DATA / "eval_cases.jsonl").exists()
needs_data = pytest.mark.skipif(not HAS_DATA, reason="run `make ingest` and `make evalset` first")


def case(**kw):
    base = dict(id="X1", question="q?", case_type="factual", expected_status="answered", gold_answer="a",
                author="t", created_at="2026-01-01")  # fmt: skip
    return EvalCase(**{**base, **kw})


# --- schema rules -----------------------------------------------------------------------


def test_answered_case_needs_gold_chunks():
    with pytest.raises(ValidationError):
        case()
    case(gold_chunk_ids={"abc": 2})


def test_non_answer_cases_cannot_carry_a_value():
    with pytest.raises(ValidationError):
        case(expected_status="abstained", gold_value=1.0, unit="%")


def test_gold_value_needs_unit():
    with pytest.raises(ValidationError):
        case(gold_chunk_ids={"abc": 2}, gold_value=1.0)


def test_conflict_needs_two_values():
    one = [ConflictValue(value=1, source_id="s", label="l", latest=True)]
    with pytest.raises(ValidationError):
        case(
            expected_status="conflict_reported", gold_chunk_ids={"abc": 2}, conflict_values=one, gold_value=1, unit="%"
        )


# --- helpers ---------------------------------------------------------------------------


def test_number_matching_ignores_format():
    assert checks.has_number("a rate of 2% and 75,200 vacancies", 2.0)
    assert checks.has_number("rose to 4,620 (or 2.0)", 4620)
    assert not checks.has_number("rose to 4,620", 4621)


def test_jaccard():
    assert checks.jaccard("what was the rate in 2025 for residents", "what was the rate in 2025 for residents") == 1.0
    assert checks.jaccard("alpha beta gamma delta epsilon zeta", "one two three four five six") == 0.0


# --- the shipped dataset ---------------------------------------------------------------


@needs_data
def test_dataset_is_consistent_with_corpus():
    assert checks.validate() == []


@needs_data
def test_case_mix_and_split():
    cases = checks.load("eval_cases.jsonl", EvalCase)
    assert len(cases) == 36
    from collections import Counter

    assert dict(Counter(c.case_type for c in cases)) == checks.EXPECTED_COUNTS
    assert Counter(c.split for c in cases) == {"dev": 21, "test": 15}


@needs_data
def test_known_gold_values():
    g = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}
    assert g["F05"].gold_value == 4620 and g["F06"].gold_value == 1.58
    assert (g["K01"].gold_value, g["K02"].gold_value, g["K03"].gold_value) == (-0.6, 30.5, -45.0)
    assert (g["K04"].gold_value, g["K05"].gold_value) == (1470, 5.0)
    assert {v.value for v in g["C01"].conflict_values} == {3100, 3270}
    assert {v.value for v in g["C03"].conflict_values} == {0.6, 0.7}  # parliamentary reply vs dataset


@needs_data
def test_every_conflict_marks_one_latest_and_unanswerable_have_no_evidence():
    for c in checks.load("eval_cases.jsonl", EvalCase):
        if c.case_type == "conflicting":
            assert sum(v.latest for v in c.conflict_values) == 1
        if c.case_type in ("unanswerable", "ambiguous"):
            assert not c.gold_chunk_ids and c.gold_value is None


@needs_data
def test_retrieval_dataset_matches_eval_splits():
    cases = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}
    for r in checks.load("retrieval_cases.jsonl", RetrievalCase):
        assert r.split == cases[r.id].split and r.relevance == cases[r.id].gold_chunk_ids


@needs_data
def test_permission_pair_and_injection_canaries():
    red = {r.id: r for r in checks.load("redteam_cases.jsonl", RedteamCase)}
    ev = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}
    assert red["R09"].user_role == "analyst_internal" and red["R09"].must_contain == ["end of October"]
    assert ev["D03"].user_role == "analyst_public" and "end of October" in ev["D03"].must_not_contain
    assert eb.MEMO_CANARY in ev["D02"].must_not_contain and len(red) >= 12


@needs_data
def test_leakage_report_is_clean():
    rep = checks.leakage_report()
    assert rep["clean"] and rep["max_fewshot_vs_eval_jaccard"] < checks.JACCARD_LIMIT


@needs_data
def test_split_is_deterministic():
    a = {c.id: c.split for c in eb.assign_splits(eb.eval_cases())}
    b = {c.id: c.split for c in eb.assign_splits(eb.eval_cases())}
    assert a == b == {c.id: c.split for c in checks.load("eval_cases.jsonl", EvalCase)}


# --- the validator must fail on corrupted data -----------------------------------------


@pytest.fixture
def tampered(tmp_path, monkeypatch):
    for f in checks.DATA.glob("*.jsonl"):
        shutil.copy(f, tmp_path / f.name)
    monkeypatch.setattr(checks, "DATA", tmp_path)
    return tmp_path


def edit(path, case_id, fn):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for r in rows:
        if r["id"] == case_id:
            fn(r)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


@needs_data
def test_validator_catches_unknown_gold_chunk(tampered):
    edit(tampered / "eval_cases.jsonl", "F01", lambda r: r.update(gold_chunk_ids={"deadbeefdeadbeef": 2}))
    assert any("F01" in e and "not in chunks" in e for e in checks.validate())


@needs_data
def test_validator_catches_wrong_gold_value(tampered):
    edit(tampered / "eval_cases.jsonl", "F04", lambda r: r.update(gold_value=99999.0))
    assert any("F04" in e and "gold_value" in e for e in checks.validate())


@needs_data
def test_validator_catches_fabricated_quote(tampered):
    edit(tampered / "eval_cases.jsonl", "F07",
         lambda r: r["gold_quotes"][0].update(quote="a sentence MOM never wrote"))  # fmt: skip
    assert any("F07" in e and "quote not found" in e for e in checks.validate())


@needs_data
def test_validator_catches_bad_split(tampered):
    edit(tampered / "eval_cases.jsonl", "F01", lambda r: r.update(split="test" if r["split"] == "dev" else "dev"))
    assert any("stratified" in e for e in checks.validate())


@needs_data
def test_validator_catches_internal_chunk_in_public_case(tampered):
    internal = next(c["chunk_id"] for c in checks.Corpus().chunks if c["access_level"] == "internal")
    edit(tampered / "eval_cases.jsonl", "F05", lambda r: r["gold_chunk_ids"].update({internal: 2}))
    assert any("F05" in e and "internal chunk" in e for e in checks.validate())


@needs_data
def test_leakage_check_flags_overlap(tampered):
    q = next(c for c in checks.load("eval_cases.jsonl", EvalCase) if c.id == "F01")
    pool = checks.load("fewshot_pool.jsonl", FewShot)
    pool[0] = FewShot(id="S1", question=q.question, status="answered", answer="x")
    (tampered / "fewshot_pool.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pool))
    rep = checks.leakage_report()
    assert not rep["clean"] and any(f["kind"] == "question_overlap" for f in rep["flags"])


@needs_data
def test_leakage_check_flags_shared_chunk_and_value(tampered):
    cases = checks.load("eval_cases.jsonl", EvalCase)
    f05 = next(c for c in cases if c.id == "F05")
    shared = next(iter(f05.gold_chunk_ids))
    pool = checks.load("fewshot_pool.jsonl", FewShot)
    pool[0] = FewShot(id="S1", question="Completely different wording here today", status="answered",
                      answer="The figure was 4,620.", chunk_ids=[shared])  # fmt: skip
    (tampered / "fewshot_pool.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pool))
    kinds = {f["kind"] for f in checks.leakage_report()["flags"]}
    assert {"shared_chunk", "shared_value"} <= kinds


# --- fields added after review round 1 -------------------------------------------------


def test_conflict_and_clarification_need_their_fields():
    one = [
        ConflictValue(value=1, source_id="s", label="a"),
        ConflictValue(value=2, source_id="s", label="b", latest=True),
    ]
    with pytest.raises(ValidationError):
        case(
            expected_status="conflict_reported", gold_chunk_ids={"abc": 2}, conflict_values=one, gold_value=2, unit="%"
        )
    with pytest.raises(ValidationError):
        case(expected_status="needs_clarification")
    case(expected_status="needs_clarification", clarify_must_cover=["measure"])


@needs_data
def test_conflict_kinds_and_clarification_focus():
    g = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}
    assert [g[i].conflict_kind for i in ("C01", "C02", "C04")] == ["preliminary_vs_final"] * 3
    assert g["C03"].conflict_kind == "unexplained_discrepancy"
    assert "revision" not in g["C03"].gold_answer.replace("not a confirmed revision", "")
    assert g["A01"].clarify_must_cover == ["measure"] and g["A03"].clarify_must_cover == ["period"]


@needs_data
def test_no_unsupported_claims_about_what_mom_publishes():
    banned = ("does not publish", "never publish", "has not been published", "not yet published")
    for c in checks.load("eval_cases.jsonl", EvalCase):
        text = f"{c.gold_answer} {c.notes}".lower()
        assert not any(b in text for b in banned), (c.id, text)


@needs_data
def test_claims_are_judged_not_matched_by_substring():
    red = {r.id: r for r in checks.load("redteam_cases.jsonl", RedteamCase)}
    ev = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}
    assert (
        red["R02"].must_not_endorse == ["unemployment is 0%"]
        and "unemployment is 0%" not in red["R02"].must_not_contain
    )
    assert ev["D02"].must_not_endorse and eb.MEMO_CANARY in ev["D02"].must_not_contain
    assert ev["D01"].expected_status == "refused" and "unemployment" not in ev["D01"].question.lower()


# --- review sheet carry-over ------------------------------------------------------------


@needs_data
def test_review_sheet_keeps_work_on_unchanged_cases_and_flags_changed_ones():
    from policy_agent.eval import review

    base = review.render("")
    old = base.replace("- [ ]", "- [x]")
    blocks = review.split_blocks(old)
    # a reviewer note on F02, and a content change to F05 since the sheet was reviewed
    old = old.replace(blocks["F02"], blocks["F02"].replace("Reviewer notes:", "Reviewer notes: looks fine"))
    old = old.replace(blocks["F05"], blocks["F05"].replace("How many employees were retrenched", "OLD WORDING"))
    new = review.split_blocks(review.render(old))
    _, ticks, note = review.parse_block(new["F02"])
    assert all(ticks) and note == "looks fine"
    _, ticks, _ = review.parse_block(new["F01"])
    assert all(ticks)
    _, ticks, _ = review.parse_block(new["F05"])
    assert not any(ticks) and "Changed after your review" in new["F05"]
    assert "Resolution after your review" in new["K03"]


@needs_data
def test_c03_dates_in_text_match_the_data():
    g = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}["C03"]
    label_date = next(v.label for v in g.conflict_values if v.latest).split()[-1]
    assert f"updated {label_date}" in g.gold_answer, (label_date, g.gold_answer)
    pq_date = next(v.label for v in g.conflict_values if not v.latest).split()[-1]
    assert pq_date in g.gold_answer


@needs_data
def test_review_update_is_idempotent_and_keeps_the_changed_marker_until_retick():
    from policy_agent.eval import review

    base = review.render("")
    assert review.render(base) == base  # nothing changed -> identical sheet
    blocks = review.split_blocks(base)
    stale = base.replace(blocks["C03"], blocks["C03"].replace("What was the resident", "OLD What was the resident"))
    first = review.render(stale)
    assert "Changed after your review" in review.split_blocks(first)["C03"]
    second = review.render(first)  # a second update must not drop the marker
    assert "Changed after your review" in review.split_blocks(second)["C03"]
    c03 = review.split_blocks(first)["C03"]
    ticked = first.replace(c03, c03.replace("- [ ]", "- [x]"))
    third = review.split_blocks(review.render(ticked))["C03"]
    assert "Changed after your review" not in third and "- [x]" in third  # re-ticked -> marker cleared


@needs_data
def test_no_case_asserts_an_unstated_seasonal_basis_for_annual_figures():
    g = {c.id: c for c in checks.load("eval_cases.jsonl", EvalCase)}
    assert "seasonally adjusted" not in g["F03"].gold_answer.lower()
    assert "does not state" in g["M06"].gold_answer and "not measured the same way" in g["M06"].gold_answer
    assert "migrant domestic workers" in g["C02"].gold_answer
