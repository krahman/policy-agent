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
| E1 R1 BM25 | 0.30 [0.13, 0.48] | 0.53 [0.27, 0.80] | 0.23 [0.11, 0.38] | 0.27 [0.15, 0.41] | 6 | $0.0000 |
| E2 R2 dense (openai) | 0.09 [0.00, 0.24] | 0.13 [0.00, 0.33] | 0.10 [0.01, 0.24] | 0.10 [0.02, 0.19] | 3 | $0.0000 |
| E2b R2 dense (voyage-4) | 0.42 [0.22, 0.63] | 0.60 [0.33, 0.87] | 0.36 [0.22, 0.52] | 0.40 [0.29, 0.53] | 966 | $0.0000 |
| E3 R3 hybrid (openai) | 0.09 [0.00, 0.24] | 0.13 [0.00, 0.33] | 0.14 [0.03, 0.29] | 0.15 [0.06, 0.25] | 8 | $0.0000 |
| E3b R3 hybrid (voyage-4) | 0.38 [0.18, 0.59] | 0.53 [0.27, 0.80] | 0.38 [0.21, 0.56] | 0.42 [0.26, 0.59] | 14 | $0.0000 |
| E4 R4 hybrid+rerank (openai) | 0.53 [0.32, 0.74] | 0.67 [0.40, 0.87] | 0.44 [0.26, 0.64] | 0.46 [0.27, 0.65] | 763 | $0.0019 |
| E4b R4 hybrid+rerank (voyage-4) | 0.57 [0.36, 0.77] | 0.73 [0.47, 0.93] | 0.52 [0.35, 0.69] | 0.58 [0.43, 0.72] | 810 | $0.0018 |
| E4c R5 R4+period filter (openai) | 0.67 [0.47, 0.86] | 0.80 [0.60, 1.00] | 0.55 [0.37, 0.73] | 0.58 [0.40, 0.76] | 784 | $0.0019 |
| E4d R5 R4+period filter (voyage-4) | 0.67 [0.47, 0.86] | 0.80 [0.60, 1.00] | 0.55 [0.38, 0.73] | 0.60 [0.43, 0.76] | 728 | $0.0019 |

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
