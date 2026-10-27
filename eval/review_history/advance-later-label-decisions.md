# Dev label decisions: open items 5 and 7 — 2026-10-28

These decisions use question scope and corpus evidence, not the frequency of model statuses. They are post-results dev decisions. They do not change case definitions, generated data, evaluator code, or test cases.

| Case | Decision | Required substance |
|---|---|---|
| F05 | Require `conflict_reported`, `preliminary_vs_final` | Show preliminary 4,500 and later 4,620, prefer 4,620. Reaffirm the existing F05 decision. |
| F07 | Keep `answered`; conflict status is not a substitute | Answer the named report's causal explanation: business reorganisation/restructuring in the stated outward-oriented sectors. The earlier release's count is outside the question, and its restructuring explanation is consistent. |
| K02 | Require `conflict_reported`, `preliminary_vs_final` | Compute the requested year-on-year change using later 4,620 against 3,540: +30.5%. Identify 4,500 as the superseded preliminary 2Q 2026 count. A response listing counts without calculating the percentage is incomplete. Do not require a second percentage based on the preliminary estimate. |
| M01 | Keep `answered`; conflict status is not a substitute | Yes: the named report and dataset match at 3,830 and 4,620. Disagreement with a third, preliminary source does not contradict this agreement. |
| M03 | Keep `answered`; conflict status is not a substitute | Yes: the named report and SA dataset match at overall 1.9%, resident 2.9%, citizen 3.0%. The earlier release's overall 2.0% is optional historical context, not disagreement between the two sources asked about. |
| D02 | Keep `answered`; do not require conflict | Quote the published 1.48 ratio and accurately attribute the requested analyst note. The report also gives 1.48; differing vacancy counts do not constitute disagreement about the ratio. A note may accurately be summarized as saying 69,900 without endorsing it as the report's count. |
| K03 | Keep `answered` as the canonical label; no automatic relabelling | Calculate the change within the dataset series: 127,000 to 69,900, about -45.0% (or a fall of 45.0%). Do not substitute the report's 68,600 without establishing comparable basis/vintage. See the unresolved comparability issue below. |

## Policy rationale

An unqualified current/historical numeric question with known preliminary and later estimates (F05/K02) must disclose their relationship under the project's established conflict policy. A question scoped to a named report or a pair of named sources (F07/M01/M03) is answered within that scope. An accurate optional note on earlier estimates is allowed; it should not turn an agreed comparison into an unresolved conflict. A correct numeric value alone does not make an irrelevant conflict status correct.

Corpus anchors: `45cc33c13de6b35e` gives preliminary 4,500; `92817f76bd4a51c1` explicitly identifies preliminary data; `ff14cfc3440c8f63` gives later 4,620, restructuring causes, and the June rates; `ecdf817788851c9e` gives ratio 1.48 and June vacancy count 68,600. The evaluation gold dataset cards give 4,620 retrenchments, 3,540 for the comparison year, and vacancy counts 127,000 and 69,900.

## D02/K03 comparability issue

The README's suggestion that June-versus-quarterly labelling itself explains 68,600 versus 69,900 is unproven. A quarterly series can consist of quarter-end snapshots; a frequency label is not evidence of a quarterly average. The local vacancy ingestion tags seasonal adjustment `unspecified`. Do not invent an SA/NSA explanation or declare the report obsolete from a retrieval timestamp alone.

K03's dataset-based calculation remains the canonical answer, but an answer that both performs it and documents an actual comparable-source discrepancy should receive a separate semantic adjudication, not be called a hallucination merely for mentioning the report. Before adding `conflict_reported` as an accepted K03 status, obtain the vacancy table's authoritative basis/vintage documentation. This leaves a specific evidence issue open rather than making an unsupported blanket status change. D02's requested ratio and attribution can already be assessed without resolving that vacancy-count issue.

## Implementation and reporting

Label decisions are complete for F05/F07/K02/M01/M03/D02; K03 retains its current label with the narrow comparison question above still open. Update F05 and K02 in the builder, including conflict values, source quotes, preliminary-versus-final framing and tool requirements. Preserve case types and dev/test membership. Regenerate and validate without overwriting review approvals or changing test definitions. Version the corrected labels and retain original E5–E7 outputs/scores. Re-score saved outputs first; fresh runs are needed only for changed system configurations or missing required outputs. Separate changes caused by labels from changes caused by model behavior. No test definition may be edited after results have been seen.

## Pre-test freeze decision — 2026-10-28

K03's scoring label is now settled for this evaluation: retain `answered`, with the existing dataset-series calculation (127,000 to 69,900; a 45.0% fall). Do not add an alternative accepted status after test results are observed. The report-versus-dataset vacancy basis remains an unresolved source-comparability limitation, not a promise to change this frozen scoring rule later. A future resolution belongs in a separately versioned evaluation; it must not be used to revise this run's acceptance criteria. This decision does not establish that the different vacancy counts are or are not comparable.
