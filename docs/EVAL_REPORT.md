# Evaluation report (draft)

Sections are added as each step lands; the final report is assembled in Step 10 (PRD §12). Numbers in generated blocks come
straight from `eval/results/*.json`; do not edit them by hand (`python scripts/make_baseline_report.py`).

## 1. Dataset design and status

36 end-to-end cases (21 dev, 15 test), 26 retrieval cases and 12 red-team cases; see [`eval/README.md`](../eval/README.md) for the
case mix, matching rules and review status. Only the `dev` split has been used so far. The `test` split has not been run.

<!-- baselines:start -->
## 2. Baselines (Step 4, `dev` split)

Run on v1 of the datasets, corpus fingerprint `82fdf97cbf39`, pricing retrieved 2026-10-27. Code state when run: commit `7edc331` **plus uncommitted changes** (re-run after committing to tie results to a commit).

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
| status_match | 0.62 (21) | 0.52 (63) | 0.43 (21) |
| numeric_exact | 0.27 (11) | 0.42 (33) | 0.55 (11) |
| must_contain_numbers | 0.40 (7) | 0.64 (21) | 0.29 (7) |
| citation_exists | 1.00 (15) | 1.00 (45) | 0.53 (15) |
| citation_correct | 0.07 (15) | 0.13 (45) | 0.40 (15) |
| injection_followed (lower is better) | 1.00 (1) | 0.00 (3) | 0.00 (1) |
| schema_valid | n/a | 0.98 (63) | n/a |
| hit@5 (answer-bearing chunk in top 5) | 0.53 (15) | 0.13 (45) | 0.40 (15) |
| recall@5 | 0.30 (15) | 0.09 (45) | 0.33 (15) |
| MRR@10 | 0.23 (15) | 0.10 (45) | 0.40 (15) |
| nDCG@10 | 0.27 (15) | 0.10 (45) | 0.33 (15) |
| latency p50 / p95 (ms) | 8.8 / 244.8 | 4224 / 7642 | 0.0 / 153.1 |
| est. cost per run (USD) | 0.0 | 0.000659 | 0.0 |

E0 (retrieval dataset, 15 questions with gold evidence): hit@5 0.53, recall@5 0.30, MRR@10 0.23, nDCG@10 0.27. PRD targets for the final system: recall@5 at least 0.85, MRR@10 at least 0.70.

`status_match` by case type:

| Case type | B0 | B1 | B2 |
|---|---|---|---|
| factual | 1.00 | 0.80 | 1.00 |
| multi_step | 1.00 | 0.00 | 0.00 |
| calculation | 1.00 | 0.33 | 0.00 |
| unanswerable | 0.00 | 1.00 | 0.33 |
| ambiguous | 0.00 | 0.00 | 1.00 |
| conflicting | 0.00 | 0.50 | 0.00 |
| adversarial | 0.50 | 1.00 | 0.50 |

Experiments in LangSmith: [E0](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/f66a97f9-3b09-4a84-b6bf-960d79abe6ce) (`E0-3281b784`), [B0](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/9186304e-311a-4b2d-b56f-406df7770c1f) (`B0-7ceb4af5`), [B1](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/75f3de61-104c-4127-9d69-3b22ea69953e) (`B1-550faf77`), [B2](https://smith.langchain.com/o/0369ebba-0dc5-433f-aa52-05179bd68d33/projects/p/e9862831-c21e-4fb9-8cf0-890c44649045) (`B2-58080501`).

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
   evidence. Run-to-run variation is small: `status_match` was identical across the 3 repetitions for all 21 cases (only A03's status
   varied, between "abstained" and "answered", and both miss the expected clarification). This run cannot
   separate retrieval error from generation error; an oracle-evidence variant (gold chunks as context) would, and is worth running before
   drawing conclusions about the model in Step 6.
4. **B1 behaves safely but is not helpful.** It abstains on all three unanswerable cases and on the permission case (D03), never emits the
   injection canary (0 of 3), and keeps the structured schema 62 of 63 times (the one failure was A03). It never asks a clarifying
   question (A02 and A03 abstain instead), gets none of the four multi-step cases right on status, and answers K03 with a wrong number
   (the run does not show whether retrieval or arithmetic caused it).
5. **B2 shows what determinism buys and where it stops.** For single-value lookups (F02, F03, F05, F06) it is correct with a verified
   citation to the right stat card; it scores zero on calculations, multi-step and conflict cases, and cannot read prose.
6. **B0 is the floor.** Because it answers every question, its `status_match` of 0.62 is just the share of dev cases that expect an answer
   (13 of 21); that metric alone cannot rank systems. Its `numeric_exact` of 0.27 is the chance that the top passage happens to hold the
   number.
7. **Cost and latency are well inside the targets for B1:** about $0.00066 per run, p50 4.2 s and p95 7.6 s against targets of 8 s and 20 s.
   Embedding the corpus once cost a fraction of a cent and is cached.

### 2.4 Caveats on these numbers

- **Small sample.** 21 dev cases, 15 with gold evidence; no confidence intervals yet (PRD §12.2). Treat differences as directional.
- **Uncommitted code.** The runs record `git_dirty`; re-run `make baselines` after committing so each result is tied to a commit.
- **`numeric_exact` can pass for the wrong reason.** It checks that the gold number appears among the numbers in the answer. B1 passed it on
  F03 with `hit@5` of 0, so the number came from somewhere other than the gold card. It also cannot tell whether a number is used
  correctly. The groundedness judge (Step 6) and `citation_correct` are the checks for that.
- **`citation_exists` of 1.00 only means the quotes were copied from the evidence given.** It says nothing about whether the evidence
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
