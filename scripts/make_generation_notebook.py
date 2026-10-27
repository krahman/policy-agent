"""Build and execute notebooks/04_generation.ipynb: evidence blocks, the structured answer and the V1-V6 checks, offline.
No model calls: the answers are written by hand to trigger each rule. Run: uv run python scripts/make_generation_notebook.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _notebook import build, code, md  # noqa: E402

cells = [
    md("""# 04 · Generation and output validation

How an answer is produced and, more importantly, how a bad one is caught. The language model writes a structured `Answer`; a program then checks it
against six rules (V1 to V6). Nothing in this notebook calls a model: the answers below are written by hand to trigger each rule, on a real chunk.

1. The evidence the model sees
2. The structured answer
3. A good answer passes
4. Each rule fails on a crafted bad answer
5. Repair, then downgrade
6. Haiku against Sonnet, from the saved runs"""),
    code("""import json

import pandas as pd
import yaml
from IPython.display import display

from policy_agent.eval.checks import load
from policy_agent.eval.models import EvalCase
from policy_agent.generation.chain import format_evidence
from policy_agent.generation.schema import Answer
from policy_agent.generation.validate import downgrade, parse, validate
from policy_agent.ingest.paths import ROOT
from policy_agent.retrieval.corpus import load_chunks

pd.set_option("display.width", 170)
pd.set_option("display.max_colwidth", 100)
by_id = {c["chunk_id"]: c for c in load_chunks()}
case = {c.id: c for c in load("eval_cases.jsonl", EvalCase)}["F02"]
gold_id = next(k for k, g in case.gold_chunk_ids.items() if g == 2)
chunk = by_id[gold_id]
print(case.question)"""),
    md(
        "## 1. The evidence the model sees\nRetrieved chunks are wrapped in `<untrusted_evidence>` tags with their id, source and date. The prompt tells the model these blocks are data, never instructions."
    ),
    code("""class _Hit:
    def __init__(self, c):
        self.chunk = c

text, kept = format_evidence([_Hit(chunk)])
print(text)
system = yaml.safe_load((ROOT / "prompts" / "agent_v1.yaml").read_text())["synth"]["system"]
print("\\n--- first rules of the system prompt ---")
print("\\n".join(system.splitlines()[:9]))"""),
    md(
        "## 2. The structured answer\nThe model must return JSON matching this schema (enforced with a JSON schema in the request, then re-checked locally). Every claim carries citations: a chunk id plus a quote copied character for character."
    ),
    code("""print(json.dumps(Answer.model_json_schema()["properties"]["status"], indent=1))
good = Answer.model_validate({
    "status": "answered",
    "summary": "The overall seasonally adjusted unemployment rate in 4Q 2023 was 2%.",
    "claims": [{"text": "Overall unemployment rate, seasonally adjusted, 4Q 2023: 2%.", "kind": "source_fact",
                "citations": [{"source_id": chunk["source_id"], "chunk_id": gold_id, "quote": chunk["text"][:90]}]}],
    "confidence": "high",
})
print(good.model_dump_json(indent=1)[:900])"""),
    md(
        "## 3. A good answer passes\n`validate` returns the list of violated rules. An empty list means the answer may be shown."
    ),
    code("""print("chunk text:", chunk["text"][:160])
print("violations:", validate(good, evidence_ids={gold_id}))"""),
    md("""## 4. Each rule fails on a crafted bad answer

| Rule | What it enforces |
|---|---|
| V1 | the output parses against the schema |
| V2 | every quote appears verbatim in the cited chunk the model was shown |
| V3 | every number in a claim or the summary appears in a cited quote or a tool result (computed values may be rounded, published figures may not) |
| V4 | a `statistical_finding` points at a tool call that really happened |
| V5 | an answered result has claims, and every claim is sourced |
| V6 | no chunk the caller's role may not read is cited |

A crafted answer can trip more than one rule (removing a citation also leaves a number unsupported, for example); the table lists everything that fires."""),
    code("""def variant(**changes):
    d = good.model_dump()
    d.update(changes)
    return Answer.model_validate(d)

cite = good.claims[0].citations[0].model_dump()
internal_id = next(c["chunk_id"] for c in by_id.values() if c["access_level"] == "internal")
bad = {
    "V1 broken output": None,
    "V2 invented quote": variant(claims=[{**good.claims[0].model_dump(), "citations": [{**cite, "quote": "The unemployment rate was 2.4% in the fourth quarter of 2023."}]}]),
    "V3 wrong number in summary": variant(summary="The overall seasonally adjusted unemployment rate in 4Q 2023 was 2.4%."),
    "V4 statistic without a tool call": variant(claims=[{**good.claims[0].model_dump(), "kind": "statistical_finding", "tool_call_ids": ["call_that_never_ran"]}]),
    "V5 claim without citation": variant(claims=[{**good.claims[0].model_dump(), "citations": []}]),
    "V6 restricted chunk cited": variant(claims=[{**good.claims[0].model_dump(), "citations": [{"source_id": by_id[internal_id]["source_id"], "chunk_id": internal_id, "quote": by_id[internal_id]["text"][:60]}]}]),
}
rows = []
for name, ans in bad.items():
    if ans is None:
        parsed, v = parse({"status": "maybe"})
    else:
        v = validate(ans, role="analyst_public", evidence_ids={gold_id, internal_id}, tool_outputs={}, tools_available=True)
    rows.append({"crafted answer": name, "violations": "; ".join(str(x) for x in v) or "none"})
display(pd.DataFrame(rows).set_index("crafted answer"))"""),
    code("""# A computed value may be quoted rounded, a published figure may not.
tool = {"call_1": '{"pct_change": -44.96063, "from": 127000, "to": 69900}'}
for text in ("Vacancies fell 45.0% (127,000 to 69,900).", "Vacancies fell 44.96% (127,000 to 69,900).", "Vacancies fell 46% (127,000 to 69,900)."):
    a = variant(status="answered", summary=text, claims=[{"text": text, "kind": "statistical_finding", "tool_call_ids": ["call_1"]}])
    print(f"{'ok ' if not validate(a, tool_outputs=tool, tools_available=True) else 'REJECTED'}  {text}")"""),
    md(
        "## 5. Repair, then downgrade\nA failed answer is sent back once with the list of violations. If the second try also fails, the system never shows it: `downgrade` replaces it with an honest abstention that names the failed rules."
    ),
    code("""violations = validate(bad["V3 wrong number in summary"], evidence_ids={gold_id})
print("sent back to the model for one repair:\\n  " + "\\n  ".join(str(v) for v in violations))
final = downgrade(None, violations)
print("\\nif the repair also fails:", final.status, "|", final.summary, "|", final.limitations)"""),
    md(
        "## 6. Haiku against Sonnet, from the saved dev runs\nThe same single-pass chain with two models (E6 Haiku 5.5, E5 Sonnet 5.5), 21 dev cases times 3 runs. Judged by a different model family."
    ),
    code("""R = ROOT / "eval" / "results"
rows = {}
for name, cid in (("Haiku 5.5 (E6)", "E6"), ("Sonnet 5.5 (E5)", "E5")):
    d = json.loads((R / f"{cid}_dev.json").read_text())
    o = d["overall"]
    rows[name] = {m: round(o[m]["mean"], 2) for m in ("status_match", "groundedness", "citation_correct", "must_contain_numbers", "schema_valid")} | {
        "cost per run $": round(d["cost_usd"]["mean_per_run"], 4),
        "p50 latency s": round(d["latency_ms"]["p50"] / 1000, 1),
    }
display(pd.DataFrame(rows).T)
print("Sonnet is better on citations and required numbers, at about 23 times the cost, so Haiku 5.5 is the default. The comparison was on the dev split only.")"""),
]

build("04_generation.ipynb", cells)
