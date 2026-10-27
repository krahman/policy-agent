"""LLM-as-judge evaluators (PRD §11.3): groundedness, answer_relevance, conflict_handling.

The judge is a different model family from the generator. Every call is cached on disk by (model, prompt), so
re-running an experiment or calibrating against a labelled sample does not re-pay or drift."""

import hashlib
import json
import os
import re
import threading
from functools import lru_cache

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from policy_agent.eval.evaluators import na, pricing
from policy_agent.ingest.paths import PROCESSED, ROOT
from policy_agent.retrieval.corpus import load_chunks

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4.1-mini")
PROMPT_FILE = ROOT / "prompts" / "judges_v1.yaml"
CACHE = PROCESSED / "judge_cache.jsonl"
MAX_EVIDENCE_CHARS = 3000
_lock = threading.Lock()
USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cache_hits": 0}


class Verdict(BaseModel):
    claim: int = Field(description="The claim's number as given")
    supported: bool
    note: str = Field(default="", description="One short reason")


class Grounding(BaseModel):
    verdicts: list[Verdict]


class Endorsement(BaseModel):
    endorsed: bool
    reason: str = ""


class Withhold(BaseModel):
    withholds: bool
    reveals: bool = False
    reason: str = ""


class Premise(BaseModel):
    accepted: bool
    reason: str = ""


class Relevance(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str = ""


class ConflictVerdict(BaseModel):
    passed: bool
    reason: str = ""


@lru_cache(maxsize=1)
def prompts() -> dict:
    p = yaml.safe_load(PROMPT_FILE.read_text())
    p["sha256_12"] = hashlib.sha256(PROMPT_FILE.read_bytes()).hexdigest()[:12]
    return p


@lru_cache(maxsize=4)
def _llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
        max_completion_tokens=1500,
    )


@lru_cache(maxsize=1)
def _cache() -> dict[str, dict]:
    rows = {}
    if CACHE.exists():
        for line in CACHE.read_text().splitlines():
            r = json.loads(line)
            rows[r["k"]] = r["v"]
    return rows


def ask(schema: type[BaseModel], system: str, human: str, model: str | None = None):
    model = model or JUDGE_MODEL
    key = hashlib.sha256(f"{model}\n{schema.__name__}\n{system}\n{human}".encode()).hexdigest()
    with _lock:
        hit = _cache().get(key)
    if hit is not None:
        USAGE["cache_hits"] += 1
        return schema.model_validate(hit)
    res = _llm(model).with_structured_output(schema, method="function_calling", include_raw=True).invoke(
        [SystemMessage(content=system), HumanMessage(content=human)]
    )  # fmt: skip
    if res["parsed"] is None:
        raise ValueError(f"judge output did not parse: {res['parsing_error']}")
    um = getattr(res["raw"], "usage_metadata", None) or {}
    with _lock:
        USAGE["input_tokens"] += um.get("input_tokens", 0)
        USAGE["output_tokens"] += um.get("output_tokens", 0)
        USAGE["calls"] += 1
        _cache()[key] = res["parsed"].model_dump()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE, "a") as f:
            f.write(json.dumps({"k": key, "v": res["parsed"].model_dump()}) + "\n")
    return res["parsed"]


def judge_cost_usd() -> float:
    m = pricing()["models"].get(JUDGE_MODEL)
    return (USAGE["input_tokens"] * m["prompt"] + USAGE["output_tokens"] * m["completion"]) if m else 0.0


def claim_block(claims: list[dict]) -> str:
    """Numbered claims, each followed by the full text of the chunks it cites (a quote may be a fragment)."""
    by_id = {c["chunk_id"]: c["text"] for c in load_chunks()}
    parts = []
    for i, cl in enumerate(claims, 1):
        ids = list(dict.fromkeys(c["chunk_id"] for c in cl.get("citations") or []))
        ev = "\n".join(f"[{j}] {by_id[j][:MAX_EVIDENCE_CHARS]}" for j in ids if j in by_id) or "(no citations)"
        parts.append(f"CLAIM {i} ({cl.get('kind')}): {cl['text']}\nCITED EVIDENCE FOR CLAIM {i}:\n{ev}")
    return "\n\n".join(parts)


def answer_for_judge(outputs: dict) -> str:
    a = outputs.get("answer") or {}
    lines = [f"Status: {a.get('status') or outputs.get('status')}", a.get("summary", "")]
    lines += [f"- ({c['kind']}) {c['text']}" for c in a.get("claims", [])]
    lines += [f"- conflict: {n['description']}" for n in a.get("conflicts", [])]
    if a.get("clarifying_question"):
        lines.append(f"Clarifying question: {a['clarifying_question']}")
    lines += [f"- limitation: {x}" for x in a.get("limitations", [])]
    return "\n".join(x for x in lines if x) if a else (outputs.get("text") or "")


def judge_claims(claims: list[dict]) -> list[Verdict]:
    p = prompts()["groundedness"]
    g = ask(Grounding, p["system"], p["human"].format(claims=claim_block(claims)))
    by_n = {v.claim: v for v in g.verdicts}
    return [
        by_n.get(i, Verdict(claim=i, supported=False, note="judge returned no verdict"))
        for i in range(1, len(claims) + 1)
    ]


def groundedness(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Fraction of the answer's claims that its own citations support."""
    claims = (outputs.get("answer") or {}).get("claims") or []
    if outputs.get("status") not in ("answered", "conflict_reported") or not claims:
        return na("groundedness")
    verdicts = judge_claims(claims)
    bad = [v.claim for v in verdicts if not v.supported]
    return {"key": "groundedness", "score": 1 - len(bad) / len(claims),
            "comment": f"{len(claims) - len(bad)}/{len(claims)} supported; unsupported claims: {bad}"}  # fmt: skip


def answer_relevance(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if not outputs.get("status"):
        return na("answer_relevance")
    p = prompts()["relevance"]
    r = ask(Relevance, p["system"], p["human"].format(question=inputs["question"], answer=answer_for_judge(outputs)))
    return {"key": "answer_relevance", "score": float(r.score), "comment": r.reason}


def conflict_handling(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if reference_outputs.get("expected_status") != "conflict_reported":
        return na("conflict_handling")
    exp = {k: reference_outputs.get(k) for k in ("conflict_kind", "conflict_values", "gold_answer")}
    p = prompts()["conflict"]
    v = ask(ConflictVerdict, p["system"], p["human"].format(
        question=inputs["question"], expected=json.dumps(exp, indent=1), answer=answer_for_judge(outputs)))  # fmt: skip
    return {"key": "conflict_handling", "score": 1.0 if v.passed else 0.0, "comment": v.reason}


def perturb(text: str) -> str | None:
    """Change the first measured value in a claim by about 10% (format kept). Period labels (2Q, 2025) are skipped, so
    this tests a wrong *number*, not a wrong period. None if the claim has no such number."""
    for m in re.finditer(r"(?<![\w.])\d(?:[\d,]*\d)?(?:\.\d+)?", text):
        raw = m.group(0)
        after = text[m.end() : m.end() + 1]
        if after in ("Q", "q") or re.fullmatch(r"(19|20)\d\d", raw):
            continue
        v = float(raw.replace(",", ""))
        dec = len(raw.split(".")[1]) if "." in raw else 0
        new = v * 1.1 if v >= 20 else v + (1 if dec == 0 else 3 * 10**-dec)
        out = f"{new:,.{dec}f}" if "," in raw else f"{new:.{dec}f}"
        return text[: m.start()] + out + text[m.end() :]
    return None


def endorses(forbidden: str, outputs: dict) -> Endorsement:
    p = prompts()["endorse"]
    return ask(Endorsement, p["system"], p["human"].format(forbidden=forbidden, answer=answer_for_judge(outputs)))


def accepts_false_premise(question: str, truth: str, outputs: dict) -> Premise:
    p = prompts()["premise"]
    return ask(
        Premise, p["system"], p["human"].format(question=question, truth=truth, answer=answer_for_judge(outputs))
    )


def withholds_restricted(question: str, outputs: dict) -> Withhold:
    p = prompts()["withhold"]
    return ask(Withhold, p["system"], p["human"].format(question=question, answer=answer_for_judge(outputs)))


JUDGE_EVALUATORS = [groundedness, answer_relevance, conflict_handling]
