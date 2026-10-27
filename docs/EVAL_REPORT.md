# Evaluation report (draft)

Sections are added as each step lands; the final report is assembled in Step 10 (PRD §12). Numbers in generated blocks come
straight from `eval/results/*.json`; do not edit them by hand (`python scripts/make_baseline_report.py`).

## 1. Dataset design and status

36 end-to-end cases (21 dev, 15 test), 26 retrieval cases and 12 red-team cases; see [`eval/README.md`](../eval/README.md) for the
case mix, matching rules and review status. Only the `dev` split has been used so far. The `test` split has not been run.

<!-- baselines:start -->
## 2. Baselines (Step 4, `dev` split)

Run on v1 of the datasets, corpus fingerprint `82fdf97cbf39`, pricing retrieved 2026-10-27. Code state when run: commit `0906006`.

### 2.1 Configurations

| Id | What | Dataset (dev) | Runs |
|---|---|---|---|
| E0 | BM25 over structure-aware chunks (C2), no LLM; retrieval metrics only | `policy-retrieval-v1` | 15 |
| B0 | BM25's best passage returned verbatim as the answer; never abstains | `policy-eval-v1` | 21 |
| B1 | Single-pass RAG: dense top-5 (`openai/text-embedding-3-small`), one prompt (`b1_single_pass@1.0.0`), model `anthropic/claude-haiku-5.5`, temperature 0, structured output, no tools | `policy-eval-v1` | 63 (21 cases x 3 repetitions) |
| B2 | Rule-based lookup in the statistics store; cannot read prose or compute | `policy-eval-v1` | 21 |

### 2.2 Results

Mean (number of scored runs). A metric counts only the runs where it applies, so the counts differ.

| Metric | B0 | B1 | B2 |
|---|---|---|---|
| status_match | 0.62 (21) | 0.51 (63) | 0.48 (21) |
| numeric_exact | 0.27 (11) | 0.45 (33) | 0.55 (11) |
| must_contain_numbers | 0.40 (7) | 0.62 (21) | 0.29 (7) |
| citation_exists | 1.00 (15) | 0.94 (45) | 0.53 (15) |
| citation_correct | 0.07 (15) | 0.13 (45) | 0.40 (15) |
| injection_followed (lower is better) | 1.00 (1) | 0.00 (3) | 0.00 (1) |
| schema_valid | n/a | 0.97 (63) | n/a |
| hit@5 (answer-bearing chunk in top 5) | 0.53 (15) | 0.13 (45) | 0.40 (15) |
| recall@5 | 0.30 (15) | 0.09 (45) | 0.33 (15) |
| MRR@10 | 0.23 (15) | 0.10 (45) | 0.40 (15) |
| nDCG@10 | 0.27 (15) | 0.10 (45) | 0.33 (15) |
| latency p50 / p95 (ms) | 22.3 / 224.4 | 3523 / 5381 | 0.0 / 166.9 |
| est. cost per run (USD) | 0.0 | 0.000659 | 0.0 |

E0 (retrieval dataset, 15 questions with gold evidence): hit@5 0.53, recall@5 0.30, MRR@10 0.23, nDCG@10 0.27. PRD targets for the final system: recall@5 at least 0.85, MRR@10 at least 0.70.

`status_match` by case type:

| Case type | B0 | B1 | B2 |
|---|---|---|---|
| factual | 1.00 | 0.80 | 1.00 |
| multi_step | 1.00 | 0.00 | 0.00 |
| calculation | 1.00 | 0.22 | 0.00 |
| unanswerable | 0.00 | 1.00 | 0.33 |
| ambiguous | 0.00 | 0.00 | 1.00 |
| conflicting | 0.00 | 0.50 | 0.00 |
| adversarial | 0.50 | 1.00 | 1.00 |

Experiments in LangSmith: [E0](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/9684ae3a-ba63-417b-ae21-25235a99325d) (`E0-ed45f083`), [B0](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/4445ef49-19a8-4530-ae08-a3ea77ebb352) (`B0-134114ca`), [B1](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/0618842d-8747-4699-a31e-bd73efef90c2) (`B1-9f806feb`), [B2](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/b81bef21-397c-42ec-922f-9c8e681ada18) (`B2-24705c84`).

<!-- baselines:end -->

### 2.3 What the baselines show

1. **Retrieval is the bottleneck, and neither retriever is close to the target.** On the same 15 dev questions with gold evidence, BM25
   puts an answer-bearing chunk in the top 5 for 53% and the dense retriever for 13%; the PRD target for recall@5 is 0.85. This is not an
   indexing bug: querying with a chunk's own text returns that chunk at rank 1 in 25 of 25 sampled cases. The dense results for an easy
   question ("resident SA unemployment rate in 2Q 2025") are the right card at rank 1 followed by near-identical cards for the wrong
   residency, quarter or adjustment, which is the sibling-card problem from EDA finding 5.
2. **The two retrievers fail in different places.** BM25 ranks the answer first or second for F03, F05 and M05 where dense ranks it 10th,
   11th and 45th; dense ranks it first for C04 and 5th for F02 where BM25 ranks it 5th and misses entirely. That complementarity is the case
   for hybrid retrieval with re-ranking and metadata filters in Step 5 (H1). It is a pattern in 15 questions, not yet a measured result.
3. **B1's wrong answers are mostly retrieval failures.** Where B1 scores 0 on `hit@5` it usually abstains or answers from the wrong
   evidence. Run-to-run variation is small but not zero: across the 3 repetitions, `status_match` differed for one case (K03) and the
   status itself for K03 and M01, each in one of three runs, where the model returned output that did not fit the schema. This run cannot
   separate retrieval error from generation error; an oracle-evidence variant (gold chunks as context) would, and is worth running before
   drawing conclusions about the model in Step 6.
4. **B1 behaves safely but is not helpful.** It abstains on all three unanswerable cases and on the permission case (D03), never emits the
   injection canary (0 of 3), and keeps the structured schema 61 of 63 times (the two failures were one run each of M01 and K03). It never asks a clarifying
   question (A02 and A03 do not get `status_match`), gets none of the four multi-step cases right on status, and answers K03 with a wrong number
   (the run does not show whether retrieval or arithmetic caused it).
5. **B2 shows what determinism buys and where it stops.** For single-value lookups (F02, F03, F05, F06) it is correct with a verified
   citation to the right stat card; it also passes `numeric_exact` on C03 and D02, which are not lookups it actually reasons about; it scores zero on calculations, multi-step and conflict cases, and cannot read prose.
6. **B0 is the floor.** Because it answers every question, its `status_match` of 0.62 is just the share of dev cases that expect an answer
   (13 of 21); that metric alone cannot rank systems. Its `numeric_exact` of 0.27 is the chance that the top passage happens to hold the
   number.
7. **Cost and latency are well inside the targets for B1:** about $0.00066 per run, p50 3.5 s and p95 5.4 s against targets of 8 s and 20 s.
   Embedding the corpus once cost a fraction of a cent and is cached.

### 2.4 Caveats on these numbers

- **Small sample.** 21 dev cases, 15 with gold evidence; no confidence intervals yet (PRD §12.2). Treat differences as directional.
- **Single re-run.** The runs are tied to commit `0906006`. An earlier run on uncommitted code differed slightly for B1 (status_match 0.52 vs 0.51, schema failures on A03 vs M01 and K03), which shows how much one repeat moves the numbers.
- **`numeric_exact` can pass for the wrong reason.** It checks that the gold number appears among the numbers in the answer. B1 passed it on
  F03 with `hit@5` of 0, so the number came from somewhere other than the gold card. It also cannot tell whether a number is used
  correctly. The groundedness judge (Step 6) and `citation_correct` are the checks for that.
- **A high `citation_exists` (B0 1.00, B1 0.94; B1's misses are the two schema-failed runs) only means the quotes were copied from the evidence given.** It says nothing about whether the evidence
  supports the claim; `citation_correct` (a grade-2 chunk was cited) is the stricter measure and is low for B1 (0.13) because of
  retrieval.
- **`injection_followed` for B0 is a false alarm in spirit.** B0 pastes the memo chunk that contains the canary string, so the canary
  appears in its output; it did not obey an instruction. The metric is a deterministic proxy and reports "canary emitted".
- **B2's retrieval metrics describe its lookup, not a ranking:** it "retrieves" at most the one stat card it cites.
- **Not yet implemented:** the LLM-judge evaluators (groundedness, answer relevance, conflict framing), prose-term checks in
  `must_contain`, and `must_not_endorse`. Their cases currently get only the deterministic checks.
- **Test split untouched.** Nothing here was run on `test`.

### 2.5 Reproduce

```bash
make ingest evalset sync-datasets   # processed data and the LangSmith datasets
make baselines                       # E0, B0, B2, B1 on dev -> LangSmith + eval/results/*.json
python scripts/make_baseline_report.py   # refresh the generated tables above
```
