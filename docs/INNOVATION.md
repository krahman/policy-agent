# Section 2: how I would improve, monitor, secure and scale this

Everything below is grounded in the measured results in `docs/EVAL_REPORT.md`. Where I propose something that was not built or measured, I say so.

## 1. A quality improvement loop driven by the error taxonomy

The held-out error analysis (EVAL_REPORT section 9) names the next fixes, in order of the failed runs they explain:

| Failure mode (held-out split) | Targeted fix | Metric that must move |
|---|---|---|
| The agent reports a real preliminary-versus-later difference (5 of 8 failed runs: K04, M07) where the case expects a plain answer; the same situation was relabelled to require a conflict on dev (F05, K02) | Write one policy for when a preliminary figure must be shown, into the prompt and the labels together | Conflict over-reporting and conflict handling (0.80 or better) on a new held-out set; fewer label disputes |
| Retrieval Recall@5 0.64, MRR 0.60 (target 0.85 and 0.70) | Query rewriting (expand "2Q 2026" and indicator synonyms), tuned fusion weights, table-aware chunking for numeric cards. I tried none of these | Recall@5 and MRR on a fresh retrieval set; then numeric accuracy |
| Cautious abstention or a rejected answer on false-premise and multi-step questions (D04, M07: 3 runs) | Let the answer state "the premise is false, the figure is X" explicitly; check why validation rejected M07 | False abstention (0.09 now) staying at or below 0.10 as the case count grows |
| Latency: median 10.0 s, p95 24.4 s | Run independent searches in parallel; one `act` round for plain lookups | Median 8 s and p95 20 s without losing citation correctness |

**Gate every change** with an experiment against the frozen cases and against a **new held-out set**: the current `test` split has been used three times, so reusing it would reward tuning to it. Add cases in the weakest strata first (calculation, conflicting, unanswerable): with 15 test cases no paired comparison reached p < 0.05.

## 2. Change detection

MOM publishes on a predictable cycle: an Advance Release, then a quarterly report, then an annual report, and figures are revised between them (in 10 of 13 quarters the later retrenchment count was higher). A scheduled job on each release would refetch the sources (`make fetch` already verifies hashes against a manifest), rebuild the processed data and index (`make ingest`), flag every statistic whose value changed, and re-run the evaluation suite. The same trigger should fire when a model or embedding version changes, because hosted models change without notice. Monitor from sampled production traces: the distribution of re-rank scores, the abstention and clarification rates, judge scores, and the topics users ask about, to catch drift. None of this is built; the data and evaluation pieces it needs are.

## 3. Trust features

Typed claims (source fact, statistical finding, model inference), verbatim quotes checked against the cited chunk, tool-call ids for computed numbers, confidence labels, and an explicit conflict list naming both values with dates are in the system today. To add: one-click feedback on each claim feeding a human annotation queue; reviewer sign-off before an answer is used in a published brief; and showing the judge's per-claim verdicts to the reviewer. The human review that exists is thin (one labeller on 29 claims for the judge; no review of held-out answers), so the first investment would be a second reviewer and agreement statistics.

## 4. Security and governance

A government deployment would need what the prototype only gestures at. Run model endpoints and any tracing service inside the network, because questions and passages currently go to third-party providers through OpenRouter. Enforce document-level access control at retrieval using authenticated identities: today the role is supplied by the caller and is **not authenticated**, the largest gap in the prototype. Keep an immutable audit log of question, evidence ids, model and prompt versions and answer. Treat the MCP server as a separate privilege domain: signed allow-list configs, authentication and per-tool scopes if it moves from stdio to HTTP. Manage third-party model risk by contract review and data-residency controls, and measure an open-weight model served inside the network against the same evaluation suite before any switch, so the quality gap is known rather than guessed. The red team found no followed injection in 36 runs, but that is a small sample of obvious attacks; a standing adversarial test set, run on every change, is the control that scales.

## 5. Latency and cost

Measured on the held-out split: 2 to 3 model calls and about 10 s median (24 s p95) per question at about $0.0025. Levers, in the order I would try them: run independent searches in parallel and use one `act` round for plain lookups; skip the re-ranker when the first-stage score is already decisive (it costs $0.001 per search and about 0.75 s); cache responses keyed on question and corpus version; and use a larger model only for synthesis if the evidence justifies it (on dev, Sonnet was within 2% on groundedness but better on citation correctness, +0.13, at about 23 times the cost, so the answer is not obvious). Routing plain single-figure lookups to the fixed chain is **not** supported by the data: on the held-out factual cases the chain scored 0.78 against the agent's 1.00. Prompt caching was not used. These are proposals; only the cost and latency measurements are results.

## 6. The first two priorities, with how I would measure them

1. **Retrieval quality (Recall@5 0.64 to 0.85, MRR 0.60 to 0.70).** It is the largest gap against any target and the cause behind many downstream misses. Re-ranking and metadata filtering were built and helped (+0.23 to +0.37 over BM25 on dev, +0.24 to +0.27 on test) but not enough. Measure Recall@5 and MRR@10 on a fresh retrieval set with paired intervals, then numeric accuracy on the questions that depend on it.
2. **A feedback and weekly human-review loop, measuring groundedness on the reviewed sample.** The automated judge was calibrated on only 29 claims, so the most valuable evidence is more human labels on real questions. Success: the judge-versus-human agreement stays at or above kappa 0.6 on the weekly sample, and the share of answers flagged by reviewers falls over four weeks.
