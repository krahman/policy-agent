# System card: evidence-grounded policy research assistant

Version: prototype, final design (simplified agent), 2026-10-28. This card says what the system is for, what it is not for, what it was tested on,
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

## 4. How well it works

Held-out `test` split (15 cases x 3 runs, final agent; EVAL_REPORT sections 7 and 8). **The held-out split was used three times** (a first agent design, then the final design twice
with identical code), and the final design was chosen from the first design's errors, so these numbers are optimistic. The second execution (clean commit) is shown:

| Measure | Result (95% CI) | PRD target |
|---|---|---|
| Expected status reached (`status_match`) | 0.82 [0.62, 1.00] (plain chain, same model: 0.64) | none set |
| Groundedness (LLM judge, calibrated on 29 claims by one person) | 0.99 [0.97, 1.00] | >= 0.90: met |
| Citation correctness | 0.94 [0.85, 1.00] | >= 0.90: met |
| Numeric exact on calculation cases | 1.00 (6 runs) | >= 0.95: met |
| Correct abstain or clarify on unanswerable and ambiguous | 1.00 (9 runs) | >= 0.85: met |
| False abstention on answerable cases | 0.09 (33 runs) | <= 0.10: met |
| Conflict surfaced and attributed | 1.00 (2 cases) | >= 0.80: met |
| Retrieval Recall@5 / MRR@10 (retriever alone, 11 questions) | 0.64 / 0.60 | 0.85 / 0.70: **not met** |
| Red team: followed injections | **0 of 36 runs** | 0: met |
| Latency p50 / p95 | 10.0 s / 24.4 s | 8 s / 20 s: **not met** |
| Cost per question | about $0.0025 | reported |

The agent is ahead of the plain chain on status, numbers and citations, but with 15 cases the paired exact tests do not reach p < 0.05, so the advantage is **suggestive, not confirmed**. The two identical
executions differed by about 0.04 on status and 0.06 on citations, which is the size of several of the margins above. The two targets that are clearly missed are retrieval and latency.

## 5. Risks and mitigations

| Risk | Mitigation | Evidence | Residual risk |
|---|---|---|---|
| Wrong number stated | Numbers must appear in a cited quote or tool result (V3); arithmetic only through tools | validator tests; held-out numeric_exact 1.00 | A well-formed but wrong figure from a compromised server is not detected by the schema; only provenance fields help |
| Citation does not support the claim | Quote must exist verbatim in the cited chunk (V2); LLM groundedness check | 0 invalid citations accepted by V2 | Judge calibrated on only 29 claims; a real quote can still be misread |
| Confident answer from missing evidence | Deterministic sufficiency check, abstention, period coverage check | demo scenarios 4, 7, 9 | The agent may still answer from partial evidence, and says so in limitations |
| Silently picking one of two sources | Conflict status and `conflicts[]` naming both values | scenario 5 | Which situations count as a conflict is a labelling judgement; the held-out cases K04 and M07 report a real preliminary-versus-later difference where the label expects a plain answer |
| Prompt injection in the question | Input guard (regex), system rules, output validation, output tripwire | red team R01, R02: refused, no marker | Regex guard misses paraphrases and other languages; the later layers carry those |
| Injection in retrieved text or MCP output | Untrusted blocks, redaction of instruction-like text, schema check, allow-list, no secrets sent to the server | R03, R04: 0 followed in 6 runs | The redaction heuristic is easy to evade; the system relies on the model treating blocks as data |
| Internal content shown to a public role | Role filter before retrieval, V6, test cases R08, R09 | R08: no internal text in 3 runs | The role is supplied by the caller and **not authenticated** in this prototype |
| Unsafe tool use (file path, SQL, rogue server) | Path whitelist and confirmation, no SQL tool, calculator without `eval`, MCP allow-list | R10, R11, R12 refused; tests | New tools would need the same review |
| Hung or failing service | Timeouts, retries, fallbacks, hard deadline | demo scenarios 7, 9 | p95 latency above target |
| Personal data in traces | Questions and answers go to LangSmith if tracing is on; no personal data is expected | none | Do not use it with confidential material; PII is only caught by a pattern list |

### Controls checklist

| Control | What is in place | Where |
|---|---|---|
| Least privilege | The statistics server opens DuckDB read-only, takes typed parameters only (no SQL tool) and has no network access. The agent can call only allow-listed MCP servers. The only write is a brief under `reports/`, after explicit approval. | `mcp_server/server.py`, `config/mcp_servers.yaml`, report node |
| Permission-aware retrieval | The role filter is applied before ranking, and rule V6 rejects any answer that cites a chunk the role may not read. | `retrieval/corpus.py`, `generation/validate.py` |
| Secrets | `.env` is git-ignored and `.env.example` holds placeholders only. The MCP server is started with the SDK's minimal environment (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`), so the API key is not passed to it. Keys are never printed or written to results. | `.gitignore`, `mcp_client.py` |
| Logging and audit | Each run keeps a node-by-node log (guard, tool calls with status and latency, validation outcome) in the saved results. The MCP server logs requests to stderr with arguments redacted; the client records the paths of any redacted content. LangSmith tracing is optional and `--no-upload` turns it off. | `graph/runtime.py`, `mcp_server/server.py`, `cli.py` |
| Data minimisation | Public and synthetic data only. Only the top retrieved passages, within a fixed token budget, and the tool results needed are sent to a model. No user identifiers are stored. The catalogue's contact emails are never read. Aggregate statistics only; personal-record requests are refused by the input guard. | `generation/chain.py`, `graph/guard.py` |
| Human oversight | The write action pauses with `interrupt()` for a yes. Answers carry a status, confidence and limitations, and claims are labelled source fact, statistical finding or model inference. | report node, `generation/schema.py` |

Not covered here: authentication of the caller's role, encryption at rest, retention policies for traces, and any regulated or classified setting.

Third-party processing: model calls go through OpenRouter to the model providers (generation, judging, embeddings and re-ranking). Questions,
retrieved passages and tool results leave the machine. Nothing here has been reviewed for a regulated or classified setting.

## 6. Human oversight

- The only consequential action (writing a file) pauses for explicit confirmation and is restricted to `reports/`.
- Low-confidence and degraded-path answers carry lowered confidence and a limitation; they are not labelled "requires review" by code
  beyond that.
- **The evaluation cases have not had a domain-expert human review.** The cases were drafted by an AI model; the review was AI-assisted
  (`eval/README.md`). The project owner labelled the judge calibration sample (29 claims, one labeller). The held-out answers were **not** reviewed by a
  person; their quality rests on automated checks and the judge.

## 7. Known limitations

- Small evaluation set (36 cases, 15 on test); wide intervals; no paired test reached p < 0.05; Sonnet was not run on `test`.
- Labels for two dev cases and the acceptance rules for three red-team cases were revised after results were seen (`eval/LABEL_CHANGES.md`); disclosed, and no `test` case changed.
- Latency and cost: about 2 to 3 model calls per question; median 10 s and p95 24 s, above target.
- Arithmetic is exact only where a tool does it; rounded forms of computed values are accepted.
- Questions in other languages, very long questions, and queries about the future of the data are untested.
- The corpus is a snapshot; a revision after 2026-10-27 would not be seen.

## 8. Reproducibility and change control

Experiment configs are in `config/experiments/`, prompts are versioned in `prompts/`, results are in `eval/results/` with the commit, prompt
hash, corpus fingerprint and label version recorded. Offline guardrail tests: `tests/test_guardrails.py`; red team: `make redteam`.
