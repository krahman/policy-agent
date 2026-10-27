# F05 dev gold-label decision — 2026-10-27

Decision: F05 should expect `conflict_reported`, with `conflict_kind = preliminary_vs_final`, under the existing corpus-wide conflict policy. Its preferred gold value remains 4,620 persons.

Evidence checked independently of model success frequency:

- `45cc33c13de6b35e`: 31 July 2026 Advance Release reports 4,500 retrenchments for 2Q 2026.
- `92817f76bd4a51c1`: the same release explicitly calls 2Q 2026 data preliminary.
- `ff14cfc3440c8f63`: 21 September 2026 report gives 4,620; the quarterly dataset agrees.

Required answer: the preliminary estimate was 4,500; the later report and dataset give 4,620, which is preferred. Identify the preliminary-versus-later relationship without inventing why the estimate changed. Calling the figures an unexplained unresolved conflict is insufficient under this policy, even though the particular reason for the change is not supplied.

The old note that the report and dataset agree is true but incomplete: it omits another authoritative source available to retrieval. This decision follows the same rule as C01/C02/C04; it is not justified merely by every run choosing conflict status.

This is a post-results correction to a dev label. Preserve original E5/E6 outputs and scores, identify the corrected dataset version, update the builder and gold evidence/quotes/conflict values together, regenerate and validate, then re-score the saved outputs under the corrected labels before deciding whether fresh runs are necessary. Report original and corrected comparisons separately; never overwrite historical results or count them as independent runs. Keep F05 in the factual category if category counts must stay fixed; expected status and case type are separate fields.

Scope of this decision: records the approved target label; does not change the builder, generated case, or any test definition. Implementation and re-evaluation remain pending. Because C04 test output has appeared in the calibration sheet, its definition must remain frozen.
