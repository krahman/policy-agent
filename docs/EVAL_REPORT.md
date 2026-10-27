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

## 3. Retrieval experiments (Step 5, `dev` split, hypothesis H1)

H1: hybrid retrieval with re-ranking beats BM25-only and dense-only on Recall@5 and MRR. All systems search the same 2,436 public chunks
(C2 chunker), the role filter is applied before ranking, and no LLM is involved. Re-rank is `cohere/rerank-v3.5` through OpenRouter over the
top 20 of the fused list. Reciprocal rank fusion uses k = 60 and 50 candidates from each retriever; neither was tuned. E4c/E4d (R5) add a
period filter extracted from the question by rules (`2Q 2025`, `September 2025`, a bare year); chunks with no reference period are never
filtered out. R5 is exploratory: the PRD's other two filter fields (`doc_type`, `access_level`) are not used because the questions give no
reliable cue for document type, and access is already enforced for every system.

<!-- retrieval:start -->
Dev split, 15 questions with gold evidence. 95% bootstrap CI (10,000 resamples of questions, seed 20261027). Cell = mean [low, high].

| System | Recall@5 | Hit@5 | MRR@10 | nDCG@10 | latency p50 (ms) | cost / query |
|---|---|---|---|---|---|---|
| E1 R1 BM25 | 0.30 [0.13, 0.48] | 0.53 [0.27, 0.80] | 0.23 [0.11, 0.38] | 0.27 [0.15, 0.41] | 10 | $0.0000 |
| E2 R2 dense (openai) | 0.09 [0.00, 0.24] | 0.13 [0.00, 0.33] | 0.10 [0.01, 0.24] | 0.10 [0.02, 0.19] | 1052 | $0.0000 |
| E2b R2 dense (voyage-4) | 0.42 [0.22, 0.63] | 0.60 [0.33, 0.87] | 0.36 [0.22, 0.52] | 0.40 [0.29, 0.53] | 929 | $0.0000 |
| E3 R3 hybrid (openai) | 0.09 [0.00, 0.24] | 0.13 [0.00, 0.33] | 0.14 [0.03, 0.29] | 0.15 [0.06, 0.25] | 9 | $0.0000 |
| E3b R3 hybrid (voyage-4) | 0.38 [0.18, 0.59] | 0.53 [0.27, 0.80] | 0.38 [0.21, 0.56] | 0.42 [0.26, 0.59] | 20 | $0.0000 |
| E4 R4 hybrid+rerank (openai) | 0.53 [0.32, 0.74] | 0.67 [0.40, 0.87] | 0.44 [0.26, 0.64] | 0.46 [0.27, 0.65] | 803 | $0.0018 |
| E4b R4 hybrid+rerank (voyage-4) | 0.57 [0.36, 0.77] | 0.73 [0.47, 0.93] | 0.52 [0.35, 0.69] | 0.58 [0.43, 0.72] | 763 | $0.0018 |
| E4c R5 R4+period filter (openai) | 0.67 [0.47, 0.86] | 0.80 [0.60, 1.00] | 0.55 [0.37, 0.73] | 0.58 [0.40, 0.76] | 774 | $0.0018 |
| E4d R5 R4+period filter (voyage-4) | 0.67 [0.47, 0.86] | 0.80 [0.60, 1.00] | 0.55 [0.38, 0.73] | 0.60 [0.43, 0.76] | 803 | $0.0017 |

Paired difference against E1 (BM25), same resamples. A difference is only worth reading if its interval excludes 0.

| System | Δ Recall@5 | Δ MRR@10 | questions better / worse / tied (Recall@5) |
|---|---|---|---|
| E2 R2 dense (openai) | -0.21 [-0.44, +0.03] | -0.14 [-0.32, +0.06] | 1 / 7 / 7 |
| E2b R2 dense (voyage-4) | +0.12 [-0.08, +0.34] | +0.13 [-0.07, +0.33] | 4 / 2 / 9 |
| E3 R3 hybrid (openai) | -0.21 [-0.38, -0.08] | -0.09 [-0.23, +0.07] | 0 / 6 / 9 |
| E3b R3 hybrid (voyage-4) | +0.08 [-0.10, +0.29] | +0.14 [+0.00, +0.31] | 2 / 2 / 11 |
| E4 R4 hybrid+rerank (openai) | +0.23 [+0.04, +0.46] | +0.21 [+0.01, +0.43] | 5 / 1 / 9 |
| E4b R4 hybrid+rerank (voyage-4) | +0.27 [+0.06, +0.50] | +0.29 [+0.09, +0.48] | 6 / 1 / 8 |
| E4c R5 R4+period filter (openai) | +0.37 [+0.13, +0.62] | +0.31 [+0.08, +0.54] | 8 / 1 / 6 |
| E4d R5 R4+period filter (voyage-4) | +0.37 [+0.13, +0.62] | +0.32 [+0.09, +0.55] | 8 / 1 / 6 |

Does the filter (R5) add anything over R4 with the same embedding? Paired difference:

| Comparison | Δ Recall@5 | Δ MRR@10 |
|---|---|---|
| E4c vs E4 | +0.14 [-0.06, +0.36] | +0.10 [-0.04, +0.28] |
| E4d vs E4b | +0.11 [-0.02, +0.26] | +0.04 [-0.06, +0.19] |
| E4b vs E2b | +0.14 [-0.01, +0.32] | +0.16 [+0.00, +0.31] |

Recall@5 per question (gold = grade-2 chunks in the top 5):

| Q | E1 | E2 | E2b | E3 | E3b | E4 | E4b | E4c | E4d |
|---|---|---|---|---|---|---|---|---|---|
| C03 | 0.50 | 0.00 | 0.00 | 0.00 | 0.00 | 0.50 | 0.50 | 0.50 | 0.50 |
| C04 | 0.33 | 0.33 | 0.33 | 0.33 | 0.33 | 0.67 | 0.67 | 1.00 | 1.00 |
| D02 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| F02 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 |
| F03 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| F05 | 0.50 | 0.00 | 0.50 | 0.00 | 0.50 | 1.00 | 0.50 | 0.50 | 0.50 |
| F06 | 0.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| F07 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| K02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| K03 | 0.00 | 0.00 | 0.50 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| K05 | 1.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| M01 | 0.33 | 0.00 | 0.67 | 0.00 | 0.00 | 0.00 | 1.00 | 0.67 | 0.67 |
| M03 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.50 | 0.75 | 0.75 |
| M04 | 0.50 | 0.00 | 0.00 | 0.00 | 0.50 | 0.50 | 0.00 | 0.00 | 0.00 |
| M05 | 0.33 | 0.00 | 0.33 | 0.00 | 0.33 | 0.33 | 0.33 | 0.67 | 0.67 |
<!-- retrieval:end -->

### 3.1 What the experiments show

1. **H1 holds for hybrid + re-rank, not for hybrid alone.** R4 beats BM25 on Recall@5 and MRR@10 with both embeddings, and the 95% paired
   intervals exclude 0 (E4: +0.23 and +0.21; E4b: +0.27 and +0.29). Plain fusion (R3) does not: with the OpenAI embeddings it is
   *worse* than BM25 on Recall@5 (-0.21, interval excludes 0), and with voyage-4 it is indistinguishable from BM25. So the claim "hybrid
   beats BM25" is not supported here; the re-ranker is what helps.
2. **The embedding model matters more than the retriever type for dense search.** `text-embedding-3-small` puts an answer-bearing chunk in
   the top 5 for 13% of questions; `voyage-4` does so for 60%, better than BM25's 53%, though the difference from BM25 is within noise on
   15 questions (Δ Recall@5 +0.12, interval -0.08 to +0.34). The OpenAI result is the sibling-card problem seen in Step 4: near-identical
   stat cards for other quarters or residency groups crowd out the right one.
3. **A re-ranker rescues a weak first stage.** E4 (OpenAI candidates) reaches Recall@5 0.53 from a first stage that scored 0.09 on its own,
   because the right card is usually somewhere in the fused top 20 and the re-ranker can tell the siblings apart. E4b is ahead of E4 by
   only 0.04 Recall@5, which is within noise.
4. **The period filter helps, but we cannot show it yet.** R5 raises Recall@5 to 0.67 with either embedding (paired +0.37 against BM25, interval
   excludes 0) and moves 8 questions up, 1 down. Its gain over R4 with the same embedding (+0.14 and +0.11) has intervals that include 0.
   The one question where R5 is worse than BM25 is M04, and not because of the filter dropping its evidence: the filter changes the
   candidate set, and the re-ranker then orders it differently (Recall@5 on M04 is 0.5 for E4 but 0.0 for E4b and E4c, so it
   depends on the re-ranker's ordering of near-equal candidates). A design weakness remains untested: a question that names one period but needs a neighbouring one would lose its
   evidence to the filter, and the 15 dev questions contain no clear example.
5. **No system reaches the target.** The PRD target is Recall@5 ≥ 0.85 and MRR@10 ≥ 0.70; the best here is 0.67 and 0.55. K02, K03 and M04
   are not retrieved by any system. K02 and K03 are the year-on-year and multi-year change questions, which need cards for two different
   periods; M04 asks about data sources described in prose. These are the cases to look at before Step 6.
6. **Cost and latency.** The re-ranker adds about 0.75 s per query and $0.001 per query (priced per search by OpenRouter); both are small
   against the 8 s / 20 s budget. The 0.97 s median for E2b is one uncached query embedding call per question, not an index cost.

### 3.2 Chosen retriever

**R5 on voyage-4 (E4d)** is the working choice for Steps 6 and 8, on the strength of the highest Recall@5 and hit@5 with the best nDCG@10,
and a re-ranker that makes the choice of embedding model matter little (E4 and E4b are close). R4 on voyage-4 (E4b) is the fallback if the
filter proves brittle. Two cautions apply to this choice:

- With 15 questions the intervals are wide (about ±0.2 on Recall@5), so "R5 over R4" is a judgement, not a measured win. The test split is
  untouched and will be used once, on the frozen configuration.
- The filter and the fusion settings were set before looking at results and were not tuned, but the choice among E1–E4d was made on `dev`,
  so the `dev` score of the winner is optimistic.

### 3.3 Caveats

- **LangSmith traces are missing for Step 5.** The account hit its monthly trace limit during the Step 4 re-run and the Step 5 runs
  (HTTP 429 "Monthly unique traces usage limit exceeded"). The experiments ran and were scored locally; the numbers above come from
  `eval/results/E*_dev.json`, which is complete. LangSmith holds E0, B0 and B2 in full and B1 with 55 of 63 runs; E1–E4d show 0 runs
  there. The PRD asks for a LangSmith comparison view; that needs the limit to reset (next month) or a plan upgrade, after which
  `make retrieval` re-creates them. Nothing here depends on those traces.
- **The embeddings API and the re-ranker are hosted services** and may change behaviour; results are cached on disk by text hash
  (`data/processed/embeddings/`), which makes re-runs reproducible but means a model update would not be noticed.
- **Same 15 questions for every system.** Gold evidence was drafted by the same model family as the system under test and reviewed by AI
  (see `eval/README.md`, Open items), so a systematic labelling bias would favour or hurt all systems alike.
- **Notebook.** The PRD also asks for the analysis in a notebook; for now it is `scripts/analyse_retrieval.py` (bootstrap CIs, paired
  differences, per-question table), which regenerates the tables above.

### 3.4 Reproduce

```bash
make retrieval        # E1..E4d on dev, then refreshes the tables above (needs OPENROUTER and LANGSMITH keys)
```

## 4. Generation experiments (Step 6, `dev` split, hypothesis H2)

Both models use the same pipeline: R5 retrieval on voyage-4 (top 5 into the prompt), prompt `answer_chain@1.0.0` with three worked
examples, structured output (`json_schema`), validation rules V1 to V6, one repair attempt, then downgrade to `abstained`. E5 uses
`anthropic/claude-sonnet-5.5` (A) and E6 `anthropic/claude-haiku-5.5` (B), 21 cases x 3 repetitions each. The judge is
`openai/gpt-4.1-mini`, a different model family from both generators. These runs were scored locally; LangSmith upload is pending.

<!-- generation:start -->
Dev split, 21 cases x 3 repetitions. A = `anthropic/claude-sonnet-5.5`, B = `anthropic/claude-haiku-5.5`. Both use R5 retrieval (voyage-4), prompt `answer_chain@1.0.0`, V1-V6 with one repair. Judge: `openai/gpt-4.1-mini` (prompt fe3436481725). Cells: mean over cases [95% bootstrap CI], n = cases where the metric applies.

| Metric | A | B | B - A [95% CI] |
|---|---|---|---|
| status_match | 0.76 [0.57, 0.90] (n=21) | 0.67 [0.48, 0.86] (n=21) | -0.10 [-0.24, +0.02] |
| numeric_exact | 0.73 [0.45, 1.00] (n=11) | 0.73 [0.45, 1.00] (n=11) | +0.00 [+0.00, +0.00] |
| must_contain_numbers | 0.86 [0.57, 1.00] (n=7) | 0.74 [0.45, 0.95] (n=7) | -0.12 [-0.29, +0.00] |
| groundedness | 1.00 [1.00, 1.00] (n=13) | 1.00 [1.00, 1.00] (n=14) | +0.00 [+0.00, +0.00] |
| answer_relevance | 4.98 [4.95, 5.00] (n=21) | 5.00 [5.00, 5.00] (n=21) | +0.02 [+0.00, +0.05] |
| citation_exists | 0.91 [0.76, 1.00] (n=15) | 0.84 [0.64, 1.00] (n=15) | -0.07 [-0.18, +0.00] |
| citation_correct | 0.80 [0.60, 1.00] (n=15) | 0.78 [0.56, 0.96] (n=15) | -0.02 [-0.07, +0.00] |
| conflict_handling | 0.50 [0.00, 1.00] (n=2) | 0.50 [0.00, 1.00] (n=2) | +0.00 [+0.00, +0.00] |
| injection_followed | 0.00 [0.00, 0.00] (n=1) | 0.00 [0.00, 0.00] (n=1) | +0.00 [+0.00, +0.00] |
| schema_valid | 1.00 [1.00, 1.00] (n=21) | 0.90 [0.78, 1.00] (n=21) | -0.10 [-0.22, +0.00] |

**H2 test:** groundedness B/A = 1.00 [1.00, 1.00] over 13 cases that both answered. H2 holds if the ratio is at least 0.90 (the interval's lower end is the safer reading).

| | A | B |
|---|---|---|
| latency p50 / p95 (s) | 8.4 / 26.5 | 6.3 / 23.9 |
| cost per run (USD, retrieval + generation) | 0.0270 | 0.0014 |
| judge cost for the experiment (USD) | 0.039 | 0.036 |

Output validation on the first pass (all 63 runs per model):

| | A | B |
|---|---|---|
| runs with at least one violation | 14 / 63 | 17 / 63 |
| repaired by the single retry | 14 / 63 | 16 / 63 |
| downgraded to abstained after the retry | 0 / 63 | 1 / 63 |
| first-pass violations of V1 | 0 | 6 |
| first-pass violations of V3 | 27 | 17 |

`status_match` by case type (mean over runs):

| Case type | A | B |
|---|---|---|
| adversarial | 1.00 | 1.00 |
| ambiguous | 1.00 | 0.83 |
| calculation | 0.33 | 0.33 |
| conflicting | 0.50 | 0.50 |
| factual | 0.80 | 0.60 |
| multi_step | 0.75 | 0.58 |
| unanswerable | 1.00 | 1.00 |
<!-- generation:end -->

### 4.1 What the experiments show

1. **H2 holds on the metrics we have, with caveats.** Haiku's groundedness is 1.00 against 1.00 for Sonnet (ratio 1.00), at about 5% of
   the cost per run ($0.0014 against $0.027) and a lower median latency (6.3 s against 8.4 s). But groundedness is at its ceiling for both
   models, so it cannot separate them, and the judge has not been calibrated against human labels yet (4.3 below). The differences that
   do show are small and not significant on 21 cases: Sonnet is ahead on `status_match` (0.76 against 0.67, interval for the difference
   -0.24 to +0.02) and on `must_contain_numbers` (0.86 against 0.74).
2. **Validation does real work.** 14 of 63 Sonnet runs and 17 of 63 Haiku runs broke at least one rule on the first try, almost all of
   them V3 (a number in the answer that is not in any cited quote). The single repair fixed 14 of 14 and 16 of 17; one Haiku run was
   downgraded to `abstained`. Without the validator those answers would have been emitted. Citation correctness (a gold chunk is
   actually cited) rose from 0.13 for B1 to 0.80 (Sonnet) and 0.78 (Haiku).
3. **Schema validity on the first try is 1.00 for Sonnet and 0.90 for Haiku; the PRD target is 0.98.** Haiku's six misses were output the
   parser could not read (or that hit the token limit); the retry fixed all but one. After the repair step, 62 of 63 Haiku runs produced an
   answer that passed every check (98.4%) and one was downgraded to `abstained`, so Haiku meets the target only with the repair loop.
4. **Latency misses the target for both.** p95 is 26.5 s (Sonnet) and 23.9 s (Haiku) against a 20 s target, driven by runs that need a
   repair (two model calls) and by the re-ranker. p50 is 8.4 s and 6.3 s against 8 s. Streaming and trimming the prompt are the likely fixes; not done.
5. **The remaining failures are mostly not generation failures.**
   - **Calculation:** K02 and K03 were abstained on in all six runs. These need figures from two different periods and retrieval
     finds none of the gold chunks for them (Step 5), so abstaining is the correct response to the evidence shown. No tools exist yet to compute the change; that is the Step 8 agent's job (H3).
   - **Conflicts:** C03 (unexplained 0.6% vs 0.7%) was answered rather than reported as a conflict in all six runs. `conflict_handling` is 0.50 but on only two cases.
   - **F05:** all six runs reported a conflict (4,500 in the Advance Release against 4,620 in the later dataset) where the case expects a plain answer. The data supports the model: the Advance Release does give 4,500. The case label ("same figure in the dataset and the report") looks wrong or incomplete. This is a question for the optional human second look in `eval/README.md`; the case has not been changed.
   - **Multi-step:** M03 is inconsistent across repetitions for both models; Haiku also reports a conflict on M01 and F07 where Sonnet answers.
6. **Both models resisted the injection case** (`injection_followed` 0 of 1) and abstained on every unanswerable case (3 of 3).

### 4.2 Choice for Step 8

**Haiku 5.5 with the repair loop** is the working choice for the agent (E7): comparable measured quality, about 19 times cheaper,
faster. Sonnet stays as the fallback model (it needs no repairs as often and has perfect first-try schema validity). This choice is
provisional until the judge is calibrated and E5/E6 are uploaded to LangSmith.

### 4.3 LLM-judge reliability

- **Sensitivity (automatic, no human involved):** one measured value was altered in each of 50 numeric claims taken from E5 and E6
  (period labels untouched), and the judge saw the original evidence. It marked all 50 unaltered claims as supported and all 50 altered
  claims as unsupported (`eval/calibration/sensitivity.json`). So it reliably catches a wrong number. It has not been tested on subtler
  errors (wrong residency group, wrong seasonal-adjustment basis, wrong period), which are the likelier real mistakes.
- **Human calibration is pending.** `eval/CALIBRATION.md` is a blind sheet with 10 answers and 29 claims, 4 of which are altered copies
  mixed in without a mark. Agreement and Cohen's kappa are computed by `make calibrate` after you tick the boxes. Until then the groundedness and
  relevance scores are *uncalibrated* and should be read as indicative. The judge scored 4.98 and 5.00 out of 5 on relevance, which is
  too lenient to distinguish systems.
- **Same-family risk** is limited, not removed: the judge is not from the generators' family, but the eval cases were drafted by the same
  family as the generators (see Open items).

### 4.4 Caveats

- 21 dev cases x 3 repetitions, with only 13 to 14 cases where groundedness applies and 2 where conflict handling applies. Intervals are wide.
- The first E5 run failed on every call because Sonnet rejects forced tool-calling (HTTP 400); the second lost about a third of its runs
  to a 1,500-token output cap. Both were harness faults, fixed (`json_schema` output, 3,000 tokens, truncation counted as a V1 failure)
  and covered by tests. The reported numbers are from the third run. The B1 baseline still uses `function_calling` and a 1,500-token cap,
  so B1 and E6 differ in more than the prompt and validation; they are not a clean ablation.
- Derived numbers (changes, ratios) are only required to be *labelled* `model_inference` and to show their working; V3 does not
  check the arithmetic. Verified arithmetic comes with the calculator tool in Step 8 (V4).
- Costs use the OpenRouter prices recorded on 2026-10-27 and include re-ranking only when the re-rank was not already cached.

### 4.5 Reproduce

```bash
make generation        # E6 then E5 on dev, scored locally (UPLOAD= to send to LangSmith)
uv run python scripts/analyse_generation.py --write
uv run python scripts/judge_sensitivity.py
make calibration-sheet # then tick eval/CALIBRATION.md yourself, then: make calibrate
```

## 5. Agent against chain (Step 8, `dev` split, hypothesis H3)

E7 is the bounded LangGraph agent with the same model (`claude-haiku-5.5`), retriever (R5 on voyage-4), validation (V1 to V6, one repair)
and judge as E6, which is the chain it is compared with. The agent adds a guard, a router, a tool loop with a deterministic sufficiency
check, and tools: `search_corpus`, `query_statistic` and `compute_change` through the MCP server, and `calculator`. 21 cases x 3
repetitions, scored locally (LangSmith upload pending).

<!-- agent:start -->
Dev split, 21 cases x 3 repetitions. Chain = E6 (`anthropic/claude-haiku-5.5`, fixed pipeline); agent = E7 (same model, same retriever, judge `openai/gpt-4.1-mini`). Cells: mean over cases [95% bootstrap CI]; the difference uses the same resampled cases for both.

**Multi-step and calculation** (7 cases)

| Metric | Chain (E6) | Agent (E7) | Agent - chain [95% CI] |
|---|---|---|---|
| status_match | 0.43 [0.14, 0.86] (n=7) | 0.38 [0.10, 0.71] (n=7) | -0.05 [-0.43, +0.29] |
| numeric_exact | 0.25 [0.00, 0.75] (n=4) | 0.75 [0.25, 1.00] (n=4) | +0.50 [+0.00, +1.00] |
| must_contain_numbers | 0.50 [0.17, 0.83] (n=4) | 0.67 [0.25, 1.00] (n=4) | +0.17 [+0.00, +0.33] |
| citation_correct | 0.43 [0.14, 0.76] (n=7) | 0.95 [0.86, 1.00] (n=7) | +0.52 [+0.19, +0.86] |
| groundedness | 0.97 [0.90, 1.00] (n=5) | 1.00 [1.00, 1.00] (n=6) | +0.04 [+0.00, +0.12] |
| answer_relevance | 4.86 [4.57, 5.00] (n=7) | 5.00 [5.00, 5.00] (n=7) | +0.14 [+0.00, +0.43] |
| schema_valid | 0.76 [0.48, 0.95] (n=7) | 0.67 [0.33, 0.95] (n=7) | -0.10 [-0.38, +0.19] |

**All other case types** (14 cases)

| Metric | Chain (E6) | Agent (E7) | Agent - chain [95% CI] |
|---|---|---|---|
| status_match | 0.83 [0.62, 1.00] (n=14) | 0.79 [0.57, 0.95] (n=14) | -0.05 [-0.17, +0.05] |
| numeric_exact | 0.90 [0.81, 1.00] (n=7) | 1.00 [1.00, 1.00] (n=7) | +0.10 [+0.00, +0.19] |
| must_contain_numbers | 0.83 [0.50, 1.00] (n=3) | 0.94 [0.83, 1.00] (n=3) | +0.11 [+0.00, +0.33] |
| citation_correct | 0.92 [0.79, 1.00] (n=8) | 1.00 [1.00, 1.00] (n=8) | +0.08 [+0.00, +0.21] |
| groundedness | 0.99 [0.96, 1.00] (n=8) | 0.98 [0.94, 1.00] (n=8) | -0.01 [-0.06, +0.04] |
| answer_relevance | 5.00 [5.00, 5.00] (n=14) | 5.00 [5.00, 5.00] (n=14) | +0.00 [+0.00, +0.00] |
| schema_valid | 0.98 [0.93, 1.00] (n=14) | 0.90 [0.77, 1.00] (n=10) | -0.07 [-0.17, +0.00] |

**All cases** (21 cases)

| Metric | Chain (E6) | Agent (E7) | Agent - chain [95% CI] |
|---|---|---|---|
| status_match | 0.70 [0.51, 0.87] (n=21) | 0.65 [0.46, 0.83] (n=21) | -0.05 [-0.19, +0.08] |
| numeric_exact | 0.67 [0.39, 0.91] (n=11) | 0.91 [0.73, 1.00] (n=11) | +0.24 [+0.03, +0.48] |
| must_contain_numbers | 0.64 [0.36, 0.90] (n=7) | 0.79 [0.50, 0.98] (n=7) | +0.14 [+0.05, +0.29] |
| citation_correct | 0.69 [0.47, 0.87] (n=15) | 0.98 [0.93, 1.00] (n=15) | +0.29 [+0.11, +0.49] |
| groundedness | 0.98 [0.95, 1.00] (n=13) | 0.99 [0.96, 1.00] (n=14) | +0.01 [-0.03, +0.05] |
| answer_relevance | 4.95 [4.86, 5.00] (n=21) | 5.00 [5.00, 5.00] (n=21) | +0.05 [+0.00, +0.14] |
| schema_valid | 0.90 [0.79, 0.98] (n=21) | 0.80 [0.63, 0.94] (n=17) | -0.08 [-0.22, +0.06] |

| | Chain (E6) | Agent (E7) |
|---|---|---|
| latency p50 / p95 (s) | 6.0 / 25.0 | 12.8 / 30.0 |
| cost per run (USD) | 0.0013 | 0.0024 |
| model calls per run (mean) | 1 to 2 | 3.0 |

Tool use in the 63 agent runs: query_statistic x56, search_corpus x50, compute_change x12, calculator x2.
Tool rounds per run: 0: 14, 1: 37, 2: 10, 3: 2.
Stop reasons: sufficient x48, out of scope x8, clarification needed x6, validation failed after repair x1.

`status_match` by case type (mean over runs):

| Case type | Chain (E6) | Agent (E7) |
|---|---|---|
| adversarial | 1.00 | 0.83 |
| ambiguous | 1.00 | 1.00 |
| calculation | 0.33 | 0.56 |
| conflicting | 0.50 | 0.67 |
| factual | 0.73 | 0.60 |
| multi_step | 0.50 | 0.25 |
| unanswerable | 1.00 | 1.00 |
<!-- agent:end -->

### 5.1 What the comparison shows

1. **H3 is partly supported: the agent is better at getting the numbers and citations right, not (yet) at reaching the expected status.**
   Across all cases, `numeric_exact` rises from 0.67 to 0.91 (paired difference +0.24, interval +0.03 to +0.48) and `citation_correct`
   from 0.69 to 0.98 (+0.29, interval +0.11 to +0.49). On the seven multi-step and calculation cases the direction is the same
   (`numeric_exact` +0.50, interval 0.00 to +1.00, on only four cases; `citation_correct` +0.52, interval +0.19 to +0.86). Arithmetic is done
   by `compute_change`, and a change between two periods cannot be reported without that call (the sufficiency check requires it).
2. **`status_match` does not improve** (0.70 to 0.65 across all cases, interval -0.19 to +0.08; multi-step 0.50 to 0.25). Seven of the nine
   mismatching cases are the agent reporting a **conflict** where the case expects a plain answer; the other two are C03 (answered in two
   of three runs instead of reporting its conflict) and M04 (abstained in all three). Reading the reported conflicts shows two causes:
   - **Advance Release against the later figure** (F05, F07, K02, M01, M03): retrenchments in 2Q 2026 are 4,500 in the Advance Release and
     4,620 in the later report and dataset, and June 2026 unemployment is 2.0% against 1.9%. The agent finds both because it searches
     the text corpus as well as the statistics, reports the discrepancy and prefers the later figure, which is what the design asks for
     (failure mode F10). These cases were labelled as if only the later figure existed.
   - **A point-in-time figure against a quarterly one** (D02, K03): the report quotes vacancies for June 2026 (68,600) and the dataset gives
     the 2Q 2026 value (69,900). These are different reference points, so calling them a conflict is arguably over-cautious; this one is a
     fair mark against the agent's synthesis, not the label.
   Numbers are right in nearly all of these runs (`numeric_exact` 0.91), so the `status_match` gap mixes a labelling question with some
   over-reporting. **The H3 verdict on status was not reliable until the labels were reviewed**; see section 6 for the corrected re-score (open items 5 and 7 in `eval/README.md`).
   The chain reports the same conflicts on F05, F07 and M01.
3. **The agent does not degrade simple cases on the measured metrics.** On the 14 other cases `groundedness`, `citation_correct`,
   `numeric_exact` and relevance are the same or higher; `status_match` is -0.05 (interval -0.17 to +0.05). The 0.83 on adversarial is
   one D02 run reporting a conflict (the point-in-time against quarterly figure above).
4. **It costs more time and money.** Median latency rises from 6.0 s to 12.8 s and p95 from 25.0 s to 30.0 s; cost per run from $0.0013
   to $0.0024; model calls per run from 1 to 2 up to 3.0 on average (route, act, synthesize). Most runs need one tool round (37 of 63);
   14 never reach the tools (guard, clarification and out-of-scope routing), and those are the cheapest and fastest answers in the
   system. Agent p95 is above the 20 s target.
5. **Control flow behaves as designed.** Stop reasons: sufficient 48, out of scope 8, clarification needed 6, validation failed after repair 1.
   No run hit the step limit or the wall-clock budget. The 10 demo scenarios pass (below).
6. **First-try schema validity is lower for the agent (0.80 on the 17 runs that reach synthesis; chain 0.90).** All ten misses are
   answers cut off at the 3,000-token output cap (long conflict answers with several quoted passages); the repair retry fixed nine and
   one was downgraded to `abstained`. The cap, not the model, is the limit; raising it was not done in this step.

### 5.2 Demo scenarios (PRD §16)

`scripts/demo_scenarios.py` runs the ten scenarios against the live agent and checks each with an assertion I wrote. All ten pass:
factual with citations; cross-source synthesis with `source_fact` and `statistical_finding` claims; a computed change through
`query_statistic` then `compute_change` (-44.96%); abstention (3Q 2026) and clarification (no year); a conflict with both values;
a direct injection refused and a memo-borne injection not followed; recovery with the dense retriever and the MCP server both
faulted (retry, then BM25 and text evidence, stated in limitations); an MCP-grounded answer; three MCP failure modes (timeout, malformed
output, outage) each ending in a safe, typed outcome; and a poisoned `stats://sources` treated as data. These are automated checks of
status, tool use, canary absence and limitations, not a human reading of every answer; the exit criterion says "pass manually", so
please run `make agent-demo` and read a few of the printed answers and traces yourself.

### 5.3 Decision for H3

Keep the agent as the default for questions that need numbers, comparisons or computed changes, because it makes those answers
verifiable (tool calls, cited cards, no mental arithmetic). Whether it is worth twice the latency for single lookups is not
settled: on simple factual cases it is equal on quality and slower. A sensible production rule, not tested here, is to route plain
single-figure lookups to the chain and everything else to the agent.

### 5.4 Caveats

- 21 dev cases; only seven are multi-step or calculation, so intervals are wide and the `numeric_exact` gain on those rests on four cases.
- The conflict-versus-answer labelling issue above affects both systems and about five dev cases (F05, F07, K02, M01, M03); no case was edited.
- The judge is uncalibrated (open item 6). The agent's groundedness is judged against the chunks it cites; a claim backed only by a
  tool result is judged through the stat card that renders the same row.
- Not tested: the agent's behaviour under concurrency beyond three parallel runs, a restarted MCP server in the middle of a run, and
  `analyst_internal` queries through the agent (the retrieval role filter is tested; the agent path is not).
- E7 was scored locally; its traces are not in LangSmith until the trace limit is raised.

### 5.5 Reproduce

```bash
make agent-demo        # the 10 scenarios, prints answers and traces
make agent             # E7 on dev (UPLOAD= to send to LangSmith) and the H3 tables above
uv run python -m policy_agent.cli "What was the change in job vacancies between 2Q 2022 and 2Q 2026?" --verbose
```

## 6. Corrected labels for F05 and K02 (post-results dev decision)

After seeing E5 to E7, two dev labels were corrected (decisions in `eval/review_history/F05-label-decision.md` and
`advance-later-label-decisions.md`, recorded by the project owner): F05 and K02 now expect `conflict_reported`, because an unqualified
question that has a known preliminary figure (4,500) and a later one (4,620) must show both. F07, M01, M03 and D02 keep `answered`
(they are scoped to named sources, and a third, preliminary source does not contradict an agreement between the two asked about). K03
keeps `answered` pending documentation of the vacancy table's basis. The original labels are kept in `eval/data/versions/v1/`; the corrected
set is version `v1.1`. This is a **post-results change to dev labels**: it can only move the dev numbers, it is disclosed here rather than
folded in, and no `test` case was touched.

Re-scoring uses the saved outputs only (E5 to E7); the retrieval experiments (E1 to E4d) and the baselines (B0 to B2) were scored under
v1 and are reported under v1 in sections 2 and 3. Their F05 and K02 retrieval labels also changed (the Advance Release chunk is now
relevant), so those sections are not directly comparable with anything scored under v1.1.

<!-- relabel:start -->
Corrected labels (v1.1): F05 and K02 now expect `conflict_reported` (preliminary 4,500 against later 4,620); no other case changed. The E5, E6 and E7 outputs saved on `dev` were scored again against the corrected reference. **These are the same 63 runs per experiment, not new samples**, and the original files are untouched. Only label-dependent metrics changed; the model's answers did not.

| Metric (mean over runs) | E5 orig | E5 corrected | E6 orig | E6 corrected | E7 orig | E7 corrected |
|---|---|---|---|---|---|---|
| status_match | 0.76 | 0.81 | 0.70 | 0.73 | 0.65 | 0.75 |
| numeric_exact | 0.73 | 0.73 | 0.67 | 0.67 | 0.91 | 0.91 |
| must_contain_numbers | 0.86 | 0.85 | 0.64 | 0.61 | 0.79 | 0.83 |
| citation_correct | 0.80 | 0.84 | 0.69 | 0.71 | 0.98 | 0.98 |
| recall_at_5 | 0.67 | 0.71 | 0.67 | 0.71 | 0.76 | 0.75 |
| conflict_handling | 0.50 | 0.50 | 0.50 | 0.42 | 0.67 | 0.83 |

The two changed cases, `status_match` over the 3 runs each:

| Case | E5 orig / corrected | E6 orig / corrected | E7 orig / corrected |
|---|---|---|---|
| F05 | 0.00 / 1.00 | 0.00 / 0.67 | 0.00 / 1.00 |
| K02 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 1.00 |

Agent (E7) against chain (E6) under the corrected labels, case-level bootstrap as in section 5:

| Metric | E6 | E7 | E7 - E6 [95% CI] |
|---|---|---|---|
| status_match | 0.73 [0.54, 0.89] (n=21) | 0.75 [0.57, 0.90] (n=21) | +0.02 [-0.16, +0.19] |
| numeric_exact | 0.67 [0.39, 0.91] (n=11) | 0.91 [0.73, 1.00] (n=11) | +0.24 [+0.03, +0.48] |
| citation_correct | 0.71 [0.51, 0.89] (n=15) | 0.98 [0.93, 1.00] (n=15) | +0.27 [+0.11, +0.44] |
| conflict_handling | 0.42 [0.00, 0.83] (n=4) | 0.83 [0.50, 1.00] (n=4) | +0.42 [+0.08, +0.83] |
| status_match, multi-step and calculation (7 cases) | 0.43 | 0.52 | +0.10 [-0.33, +0.52] |
| status_match, all other (14 cases) | 0.88 | 0.86 | -0.02 [-0.17, +0.10] |
<!-- relabel:end -->

### 6.1 What changed and why

The movement in the table is caused by the label change, not by any model: the saved answers are identical.

- **F05:** all three E5 and E7 runs and two of three E6 runs report the preliminary 4,500 and the later 4,620, so they now match the
  expected status. One E6 run still gave a plain answer.
- **K02:** only the agent (E7) meets the corrected label, in all three runs (it fetches both quarters, computes +30.5% with
  `compute_change`, and notes the superseded 4,500). E5 and E6 abstained on K02 in every run because retrieval did not bring back both
  periods (Step 5), so the label change does not help the chain there. This is a model-behaviour difference, not a labelling one.
- **Effect on H3:** under v1 the agent trailed the chain on `status_match` (-0.05 overall, -0.05 on multi-step and calculation). Under v1.1 the
  difference is +0.02 [-0.16, +0.19] overall and +0.10 [-0.33, +0.52] on multi-step and calculation: no reliable difference either way on
  status, as before, but the apparent deficit disappears. The `numeric_exact` (+0.24) and `citation_correct` (+0.27) advantages are
  unchanged, and `conflict_handling` now favours the agent (0.83 against 0.42, interval +0.08 to +0.83, but on only four cases and from an
  uncalibrated judge).
- **Effect on H2 (E5 against E6):** the gap in `status_match` is 0.81 against 0.73 (v1: 0.76 against 0.70); the conclusion in section 4 does not change.
- **Still open:** K03 keeps `answered` pending documentation of the vacancy table's basis; the labels for F07, M01, M03 and D02 were
  confirmed rather than changed. Because F05 and K02 changed after results were seen, their review ticks were cleared in `eval/REVIEW.md` and
  need re-ticking (open item 2).
