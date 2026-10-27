# Open items

One list of everything that is not finished, who can finish it, and where the detail lives. Last updated 2026-10-28 (after Step 11).
Items already settled are listed at the end so they are not asked again.

## A. Needs a person

| # | Item | Why it matters | Blocks | Detail in |
|---|---|---|---|---|
| A1 | **Tick `eval/HUMAN_REVIEW_TEST.md`**, then run `uv run python scripts/compare_test_review.py` (15 held-out answers, blind) | The PRD requires human review of the held-out results; until it is done, held-out quality rests on automated checks and one calibrated judge | Calling Step 10 complete | `eval/README.md` item 9; EVAL_REPORT 8.7 |
| A2 | **Domain-expert look at the definition-sensitive cases** (C01 to C04, M03, M06, A01, A02, U02 to U04) | The cases were drafted by an AI model and reviewed in an AI-assisted process; nobody with labour-market expertise has checked them | Trusting any case-level result | `eval/README.md` item 1; SYSTEM_CARD 6 |
| A3 | **Confirm the re-ticks.** F05 and K02 (label v1.1) were re-ticked in `eval/REVIEW.md` by an AI tool (Codex) on 2026-10-28; C02, C03, F03, M03 and M06 still show "changed after your review" | AI ticks are not human review | Nothing in the code | `eval/README.md` items 2, 5, 7 |
| A4 | **Verify how MOM computes annual averages** (seasonally adjusted or not) from an authoritative source | The corpus tags annual rates `unspecified`; an unverified claim says MOM now uses seasonally adjusted inputs | The wording of F03, M06 and C03 | `eval/README.md` item 3 |
| A5 | **Obtain the vacancy table's basis and vintage documentation** | K03 and D02 involve a report figure (June) against a dataset figure (quarter); without the documentation the model's "conflict" cannot be judged right or wrong | Extending K03's accepted statuses (frozen for this evaluation) | `eval/README.md` item 7; review_history |
| A6 | A **second reviewer** for held-out and calibration labels | One labeller means no inter-rater agreement can be reported | Agreement statistics | EVAL_REPORT 8.7; INNOVATION 3 |

## B. Engineering that is known but not applied (the held-out result is frozen)

Applying these changes the system after its test result was seen, so any new claim needs a new held-out set (EVAL_REPORT 8.5).

| # | Item | Evidence | Expected effect |
|---|---|---|---|
| B1 | Add employment change and population segments to the router's scope; decide "out of scope" only after one search finds nothing | C02, U02; false abstention 0.27 | Target 0.10 or less |
| B2 | Require `compute_change` from the router's `needs_numbers` flag plus two named periods, not a word list | K04; calculation accuracy 0.50 | Target 0.95 |
| B3 | Write the policy for preliminary-versus-later figures into the prompt and the labels together | M07, R06, F05, K02 | Fewer label disputes |
| B4 | Cut model calls (merge router and plan, parallel searches, trim evidence) | p50 10.3 s, p95 27.1 s | Toward 8 s and 20 s |
| B5 | Evaluate Sonnet on `test` | H2 is unconfirmed on held-out data; Sonnet was better on citations (+0.11) on dev | Needs about $1.3 of credit |
| B6 | Retrieval work toward 0.85 Recall@5 (query rewriting, table-aware chunking, fusion weights) | Recall@5 0.64, MRR 0.60 | The largest remaining gap |
| B7 | More cases per weak type (calculation, conflicting, unanswerable) and a fresh held-out set | 15 test cases: no paired test reached p < 0.05 | A comparison that can separate systems |

## C. Infrastructure and process

| # | Item | Status | Detail in |
|---|---|---|---|
| C1 | **LangSmith:** raise the monthly trace limit, then run `make sync-datasets` (v1.1 datasets) and re-run the experiments with `UPLOAD=` empty to get comparison views and links | Everything was scored locally; the report has no experiment links, so the Step 10 exit criterion "with experiment links" is unmet | EVAL_REPORT 3.3, 8.7; README Limitations |
| C2 | **Fresh `git clone` and `make reproduce`** on a clean machine | Verified on a clean copy of the working tree without keys; a real clone after the final commit is the actual exit check | PRD Step 11 |
| C3 | **Timed dry run of the demo** (`docs/DEMO_SCRIPT.md`) | Not done; needs about $0.10 of credit | DEMO_SCRIPT |
| C4 | OpenRouter credit | About $1.85 left; the spend guard refuses runs that would not fit | `src/policy_agent/budget.py` |
| C5 | Run metadata records `dataset_version` as `v1` even for v1.1 runs (a constant was not updated) | Cosmetic for `test` (v1 and v1.1 are identical there); would matter for new dev runs | EVAL_REPORT 8 |
| C6 | Red-team acceptance rules v1.1 (R05, R06, R08) are implemented in the harness and reported next to the original rules; the source cases are unchanged | Done as designed; listed so nobody expects the case files to change | `eval/README.md` item 8 |

## D. Known security gaps (not tested or not built)

Paraphrased and non-English injections; instructions hidden in real MOM web pages; poisoned tool descriptions; **role spoofing (the role is supplied by the caller, not authenticated)**; exfiltration through tool arguments; abuse at volume; the redaction heuristic is easy to evade; a compromised server returning wrong but well-formed data. Detail: SYSTEM_CARD 5, EVAL_REPORT 7.3, INNOVATION 4.

## E. Settled (recorded, do not re-ask)

- Judge calibration labelled by the project owner: groundedness agreement 100% on 29 claims; the relevance judge is too lenient and is not used to rank (`eval/README.md` item 6).
- F05, K02, R05, R06, R08 and K03 label decisions are recorded in `eval/review_history/` and implemented where applicable (v1.1 labels; red-team rules; K03 frozen as `answered`).
- No `test` case was edited; the label correction touched only `dev` cases and is versioned.
- MCP server, validating client, agent, red-team pass, guardrail tests, system card and architecture documents exist and are tested.
