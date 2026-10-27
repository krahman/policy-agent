# System card: evidence-grounded policy research assistant

Version: prototype, as of 2026-10-28 (Step 9). This card says what the system is for, what it is not for, what it was tested on,
and what could still go wrong. Numbers come from `docs/EVAL_REPORT.md`; where evidence is thin the card says so.

## 1. Intended use

A research aid for analysts working on the Singapore labour market. Given a question, it retrieves from a corpus of published MOM
statistics and report pages (2021-Q3 to 2026-Q2), queries the statistics through a read-only server, does arithmetic with tools, and returns a
structured answer: a status (answered, abstained, needs clarification, conflict reported, refused), claims labelled as source fact,
statistical finding or model inference, each with a citation or a tool call, plus limitations and a confidence label. It can render a
Markdown brief and save it, but only after the user confirms.

Intended users: analysts and researchers who will read the cited sources before relying on a figure.

## 2. Out-of-scope use

- Policy recommendations, forecasts, or normative judgements (the system reports and compares published data).
- Any decision about an individual, employer or region smaller than the national tables; personal records of any kind.
- Countries other than Singapore, periods outside 2021-Q3 to 2026-Q2, or live data. The corpus is a snapshot retrieved 2026-10-27.
- Use as an authority without checking the sources. An answer is evidence-linked, not certified.
- Any use with confidential or personal data. Questions and retrieved text are sent to third-party model providers (section 5).

## 3. Data

- **Public:** 21 datasets from data.gov.sg (Singapore Open Data Licence v1.0) and 46 MOM web pages, used under MOM's terms of use. See
  `docs/DATASHEET.md` for provenance, licences, gaps and the known limits of the statistics (for example, the seasonal-adjustment basis of
  annual rates is not stated by the sources and is recorded as `unspecified`).
- **Synthetic:** 7 memos written for this project, two marked internal, used to test permissions and injection. They contain invented
  content and one planted attack string; none of it is real MOM material.
- No personal data is collected or stored. Keys are read from `.env` (git-ignored).

## 4. How well it works (dev split, 21 cases x 3 runs)

| Measure | Result | Where |
|---|---|---|
| Agent: published number matches the expected one (`numeric_exact`) | 0.91 (chain with the same model: 0.67) | EVAL_REPORT section 5 |
| Agent: cited chunk is a gold source (`citation_correct`) | 0.98 (chain: 0.69; BM25 baseline: 0.07) | section 5 |
| Expected status reached (`status_match`), corrected labels | 0.75 (chain 0.73); no reliable difference | section 6 |
| Quoted groundedness, LLM-judged | 0.99, **uncalibrated** | sections 4, 5 |
| Red team: followed injections | **0 of 36 runs** (12 cases x 3) | section 7 |
| Latency, median / 95th percentile | 12.8 s / 30.0 s (target 20 s at p95: **not met**) | section 5 |
| Cost per question | about $0.002 | section 5 |

The `test` split has not been used. Every number above comes from the same 21 development cases that guided the design, so it is
optimistic; treat the figures as directional. The agent configuration was changed after these runs (Step 9 fixes) and must be re-run
in Step 10 before it is reported as final.

## 5. Risks and mitigations

| Risk | Mitigation | Evidence | Residual risk |
|---|---|---|---|
| Wrong number stated | Numbers must appear in a cited quote or tool result (V3); arithmetic only through tools | validator tests; E7 numeric_exact 0.91 | A well-formed but wrong figure from a compromised server is not detected by the schema; only provenance fields help |
| Citation does not support the claim | Quote must exist verbatim in the cited chunk (V2); LLM groundedness check | 0 invalid citations accepted by V2 | Judge uncalibrated; a real quote can still be misread |
| Confident answer from missing evidence | Deterministic sufficiency check, abstention, period coverage check | scenarios 4, 7, 9 | The agent may still answer from partial evidence, and says so in limitations |
| Silently picking one of two sources | Conflict status and `conflicts[]` naming both values | scenario 5 | Which situations count as a conflict is a labelling judgement; five dev cases are disputed (open items 5, 7) |
| Prompt injection in the question | Input guard (regex), router, system rules, output validation, output tripwire | red team R01, R02: refused, no marker | Regex guard misses paraphrases and other languages; the later layers carry those |
| Injection in retrieved text or MCP output | Untrusted blocks, redaction of instruction-like text, schema check, allow-list, no secrets sent to the server | R03, R04: 0 followed in 6 runs | The redaction heuristic is easy to evade; the system relies on the model treating blocks as data |
| Internal content shown to a public role | Role filter before retrieval, V6, test cases R08, R09 | R08: no internal text in 3 runs | The role is supplied by the caller and **not authenticated** in this prototype |
| Unsafe tool use (file path, SQL, rogue server) | Path whitelist and confirmation, no SQL tool, calculator without `eval`, MCP allow-list | R10, R11, R12 refused; tests | New tools would need the same review |
| Hung or failing service | Timeouts, retries, fallbacks, hard deadline | demo scenarios 7, 9 | p95 latency above target |
| Personal data in traces | Questions and answers go to LangSmith if tracing is on; no personal data is expected | none | Do not use it with confidential material; PII is only caught by a pattern list |

Third-party processing: model calls go through OpenRouter to the model providers (generation, judging, embeddings and re-ranking). Questions,
retrieved passages and tool results leave the machine. Nothing here has been reviewed for a regulated or classified setting.

## 6. Human oversight

- The only consequential action (writing a file) pauses for explicit confirmation and is restricted to `reports/`.
- Low-confidence and degraded-path answers carry lowered confidence and a limitation; they are not labelled "requires review" by code
  beyond that.
- **No human has yet reviewed the evaluation cases or the judge.** The cases were drafted by an AI model; the review was AI-assisted
  (`eval/README.md`, open items 1 and 6). Until a person with labour-market knowledge reviews them and labels the calibration sheet,
  quality numbers should not be presented as human-validated.

## 7. Known limitations

- Small evaluation set (36 cases, 21 on dev); wide intervals; no results on `test`.
- Labels for several conflict cases were revised after results were seen (section 6); those changes are disclosed and versioned.
- Latency and cost: about 3 model calls per question; p95 above target.
- Arithmetic is exact only where a tool does it; rounded forms of computed values are accepted.
- Questions in other languages, very long questions, and queries about the future of the data are untested.
- The corpus is a snapshot; a revision after 2026-10-27 would not be seen.

## 8. Reproducibility and change control

Experiment configs are in `config/experiments/`, prompts are versioned in `prompts/`, results are in `eval/results/` with the commit, prompt
hash, corpus fingerprint and label version recorded. Offline guardrail tests: `tests/test_guardrails.py`; red team: `make redteam`.
