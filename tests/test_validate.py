"""V1-V6 each with a passing and a failing fixture (PRD §14.3)."""

import pytest

from policy_agent.generation.schema import Answer, Citation, Claim
from policy_agent.generation.validate import downgrade, parse, validate
from policy_agent.retrieval.corpus import load_chunks

PUB = next(c for c in load_chunks() if c["access_level"] == "public" and c["doc_type"] == "stat_card")
INTERNAL = next(c for c in load_chunks() if c["access_level"] == "internal")
QUOTE = PUB["text"][
    :120
]  # e.g. "... 3Q 2021: 1,900" is beyond 120 chars for some chunks, so numbers are taken from it below
NUM = "1,900"


def cite(chunk=PUB, quote=None):
    return Citation(source_id=chunk["source_id"], chunk_id=chunk["chunk_id"], quote=quote or chunk["text"][:150])


def answer(**kw):
    base = {
        "status": "answered",
        "summary": "See claim.",
        "claims": [Claim(text="x", kind="source_fact", citations=[cite()])],
    }
    return Answer(**(base | kw))


def rules(a, **kw):
    return {v.rule for v in validate(a, **kw)}


def test_v1_schema():
    ok, v = parse({"status": "answered", "summary": "s"})
    assert ok is not None and not v
    bad, v = parse({"status": "maybe", "summary": "s"})
    assert bad is None and v[0].rule == "V1"


def test_v2_quote_must_be_verbatim_and_chunk_must_exist():
    assert "V2" not in rules(answer())
    wrong = answer(
        claims=[Claim(text="x", kind="source_fact", citations=[cite(quote="this text is not in the chunk at all")])]
    )
    assert "V2" in rules(wrong)
    ghost = Citation(source_id="s", chunk_id="deadbeefdeadbeef", quote="some quote long enough")
    assert "V2" in rules(answer(claims=[Claim(text="x", kind="source_fact", citations=[ghost])]))
    assert "V2" in rules(answer(), evidence_ids={"somethingelse"})  # cited chunk was not in the evidence shown
    short = answer(claims=[Claim(text="x", kind="source_fact", citations=[cite(quote=" a ")])])
    assert "V2" in rules(short)  # a trivial quote would match every chunk


def test_v3_numbers_must_come_from_cited_quotes():
    n = "1,900"
    quote = PUB["text"][PUB["text"].index(n) - 40 : PUB["text"].index(n) + 10]
    claim = Claim(text="1,900 vacancies", kind="statistical_finding", citations=[cite(quote=quote)])
    good = answer(summary="There were 1,900 vacancies.", claims=[claim])
    assert "V3" not in rules(good)
    bad_claim = answer(
        claims=[Claim(text="There were 2,500 vacancies", kind="source_fact", citations=[cite(quote=quote)])]
    )
    assert "V3" in rules(bad_claim)
    assert "V3" in rules(answer(summary="There were 2,500 vacancies."))
    # a computed number is allowed only inside a labelled model_inference claim, and the summary may then repeat it
    inf = answer(
        summary="That is a 45.0% fall.",
        claims=[Claim(text="(69,900-127,000)/127,000 = -45.0%", kind="model_inference", citations=[cite()])],
    )
    assert "V3" not in rules(inf)
    assert "V3" not in rules(
        answer(summary="In 2024 and 2Q 2025 the figure was stated.")
    )  # years and quarters are labels


def test_v4_statistical_finding_needs_tool_call_when_tools_exist():
    a = answer(claims=[Claim(text="x", kind="statistical_finding", citations=[cite()], tool_call_ids=[])])
    assert "V4" not in rules(a)  # no tools in a plain chain
    assert "V4" in rules(a, tools_available=True, tool_outputs={"t1": "42"})
    ok = answer(claims=[Claim(text="x", kind="statistical_finding", citations=[cite()], tool_call_ids=["t1"])])
    assert "V4" not in rules(ok, tools_available=True, tool_outputs={"t1": "42"})
    fake = answer(claims=[Claim(text="x", kind="statistical_finding", citations=[cite()], tool_call_ids=["nope"])])
    assert "V4" in rules(fake, tools_available=True, tool_outputs={"t1": "42"})


def test_v5_answered_needs_a_citation_on_every_claim():
    assert "V5" not in rules(answer())
    assert "V5" in rules(answer(claims=[Claim(text="x", kind="source_fact", citations=[])]))
    assert "V5" in rules(answer(claims=[]))
    assert "V5" not in rules(Answer(status="abstained", summary="No data.", claims=[]))


def test_v6_restricted_chunk_for_role():
    leak = answer(claims=[Claim(text="x", kind="source_fact", citations=[cite(INTERNAL)])])
    assert "V6" in rules(leak, role="analyst_public")
    assert "V6" not in rules(leak, role="analyst_internal")


def test_downgrade_is_a_valid_abstention():
    d = downgrade(None, validate(answer(claims=[]), "analyst_public"))
    assert d.status == "abstained" and not d.claims and "V5" in d.limitations[0]
    assert not validate(d)


@pytest.mark.parametrize("sid", ["S1", "S3", "S5"])
def test_fewshot_examples_pass_the_validator(sid):
    import json

    from policy_agent.generation.chain import FEWSHOT_FILE, example_answer

    by_id = {c["chunk_id"]: c for c in load_chunks()}
    r = {x["id"]: x for x in map(json.loads, FEWSHOT_FILE.read_text().splitlines())}[sid]
    assert not validate(example_answer(r, [by_id[i] for i in r["chunk_ids"]]))


def test_v5_accepts_a_tool_backed_statistical_claim_only_when_tools_exist():
    a = answer(claims=[Claim(text="x", kind="statistical_finding", citations=[], tool_call_ids=["t1"])])
    assert "V5" in rules(a)  # without tools a bare statistical claim is unsourced
    assert "V5" not in rules(a, tools_available=True, tool_outputs={"t1": "42"})
    assert "V5" in rules(
        answer(claims=[Claim(text="x", kind="source_fact", citations=[], tool_call_ids=["t1"])]),
        tools_available=True,
        tool_outputs={"t1": "42"},
    )  # noqa: E501
