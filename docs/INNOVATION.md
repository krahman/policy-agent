# Section 2: how I would improve, monitor, secure and scale this

Everything below is grounded in the measured results in `docs/EVAL_REPORT.md`. Where I propose something that was not built or measured, I say so.

## 1. A quality improvement loop driven by the error taxonomy

The held-out error analysis (EVAL_REPORT 8.4) names the next fixes, in order of the runs they explain:

| Failure mode (test split) | Targeted fix | Metric that must move |
|---|---|---|
| Router refuses or clarifies answerable questions (C02, U02): false abstention 0.27 | Add employment change and population segments to the router's scope; let "out of scope" be decided only after one search finds nothing | False abstention 0.27 to at most 0.10 |
| Calculation skipped when the question is phrased "how many more ... than" (K04): numeric accuracy 0.50 on calculation cases | Require `compute_change` whenever the router says numbers are needed and two periods are named, instead of matching a word list | Numeric exact on calculation cases 0.50 to at least 0.95 |
| Right evidence, wrong or missing chunk (retrieval Recall@5 0.64, MRR 0.60) | Query rewriting (expand "2Q 2026" and indicator synonyms), table-aware chunking for numbers, and tuning the fusion weights, none of which I tried | Recall@5 0.64 to 0.85 on a fresh retrieval set |
| Conflict handling disputed (M07, R06, F05, K02) | Write the policy for preliminary-versus-later figures once, into the prompt and the labels together | Fewer label disputes; conflict handling 0.50 to at least 0.80 |

**Gate every change** with an experiment against the frozen cases, and against a **new held-out set** each time: the current `test` split has been seen, so reusing it would reward tuning to it. Cases should be added in the weakest strata first (calculation, conflicting, unanswerable), because 2 to 3 test cases per type is too few to separate systems.

## 2. Change detection

MOM publishes on a predictable cycle: an Advance Release, then a quarterly report, then an annual report. Figures are revised between them (EDA finding 2: in 10 of 13 quarters the later retrenchment count was higher). A scheduled job on each release would: refetch the sources (`make fetch` already verifies hashes against a manifest), rebuild the processed data and index (`make ingest`), flag every statistic whose value changed, and re-run the evaluation suite. The same trigger should fire when a model or embedding version changes, because hosted models change without notice. Monitor from sampled production traces: the distribution of re-rank scores, the abstention and clarification rates, judge scores, and the topics users ask about, to catch drift. None of this is built; the data and eval pieces it needs are.

## 3. Trust features

Typed claims (source fact, statistical finding, model inference), verbatim quotes checked against the cited chunk, tool-call ids for computed numbers, confidence labels, and an explicit conflict panel naming both values with dates are in the system today. To add: one-click feedback on each claim feeding a human annotation queue; reviewer sign-off before an answer is used in a published brief; and showing the judge's per-claim verdicts to the reviewer. The human review that exists is thin (one labeller on 29 claims for the judge; a held-out sheet awaiting one reviewer), so the first investment would be a second reviewer and agreement statistics.

## 4. Security and governance

A government deployment would need what the prototype only gestures at. Run model endpoints and any tracing service inside the network (self-hosted LangSmith), because questions and passages currently go to third-party providers through OpenRouter. Enforce document-level access control at retrieval using authenticated identities: today the role is supplied by the caller and is **not authenticated**, the largest gap in the prototype. Keep an immutable audit log of question, evidence ids, model and prompt versions and answer. Treat the MCP server as a separate privilege domain: signed allow-list configs, authentication and per-tool scopes if it moves from stdio to HTTP. Manage third-party model risk by contract review and data-residency controls, and measure an open-weight model served inside the network against the same evaluation suite before any switch, so the quality gap is known rather than guessed. The red team found no followed injection in 36 runs, but that is a small sample of obvious attacks; a standing adversarial test set, run on every change, is the control that scales.

## 5. Latency and cost

Measured: about 3 model calls and 10 s median (27 s p95) per question at about $0.0025. Levers, in the order I would try them: merge the router and plan steps and run independent searches in parallel (fewer sequential calls); skip the re-ranker when the first-stage score is already decisive (it costs $0.001 per search and about 0.75 s); consider routing plain single-figure lookups to the fixed chain, which was faster and cheaper, and keeping the agent for comparisons and calculations (a hypothesis, not a result: on the held-out factual cases the chain scored 0.78 against the agent's 1.00 on both status and number, so this needs its own test); use a larger model only for synthesis if the evidence justifies it (the dev comparison found groundedness within 2% at about 23 times the cost, but Sonnet was better on citation correctness, +0.11, so the answer is not obvious); and cache responses keyed on question and corpus version. Prompt caching was not used. These are proposals; only the cost and latency measurements are results.

## 6. The first two priorities, with how I would measure them

1. **Fix the router and the calculation trigger, then re-measure on a new held-out set.** These are cheap, specific, and explain most failed held-out runs. Success: false abstention at most 0.10 and calculation numeric accuracy at least 0.95, with intervals that exclude the current values, on at least 10 cases per affected type.
2. **Add a feedback and weekly human-review loop, and measure groundedness on the reviewed sample.** The automated judge was calibrated on only 29 claims, so the most valuable evidence is more human labels on real questions. Success: the judge-versus-human agreement stays at or above kappa 0.6 on the weekly sample, and the share of flagged answers falls over four weeks.

The re-ranking and metadata filtering that the PRD named as a priority were built and measured: they raised Recall@5 over BM25 (+0.23 to +0.37 on dev, +0.24 to +0.27 on test) but not to the 0.85 target, so retrieval quality remains the main open problem after the two steps above.
