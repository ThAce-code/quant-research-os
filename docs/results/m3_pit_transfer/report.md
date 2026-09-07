# M3.6: daily and existing PIT inputs through a common contract

The shared input boundary is implemented and verified. The fixed new
low-equity-growth candidate reached the real common screen and was **REJECT**.
Its campaign froze an empty selection and returned **NO_ENTRY**, zero fits and
zero portfolios. Input engineering completion is not independent-alpha evidence.

Implementation: `0bda91d`. Hypothesis/budget freeze: `97250a9`.
Screen: `20260907T040438553259Z`. Contract SHA256:
`d1dee6c8ecf2b834738832080fce4f710705a7a04fa68937ebfa763ad4c65db3`.

The contract binds eight existing daily fields and six publication-aligned fields:
ROE, net margin, earnings growth, asset growth, equity growth and cashflow margin.
Each panel is pinned to its source manifest and independent verification, with
unit, availability, missing-value and revision rules. Initial screening and model
increment use the same loader and check input identity before registration.
Unknown sources are rejected, and PIT expressions require an explicit contract.

All 13,333,716 original fundamental panel cells transferred exactly. Reindexing
onto the canonical calendar introduces only missing values outside the source
range. The eight daily fields remain exactly unchanged. Each PIT field passed
cutoff-invariance checks. These checks preserve the earlier source audits; they
do not independently rediscover financial revision truth or reconcile different
fields' fiscal periods. See [the contract and limitations](../../M3_DATA_CONTRACT.md).

The one predeclared hypothesis ranks lower YOYEquity positively (fixed direction
−1); it is not a retuning of the closed asset-growth experiment. The 2015–2016
five-day RankIC was −0.0005678293, q 0.5257371314. Yearly RankIC was +0.0078143
and −0.0089148. There was no sign/window/threshold change and no additional
candidate after observing this result.

Independent screen verification compared 354,288 raw cells against the pinned
PIT source panel, sampled 50 daily RankIC values, checked the registry result and
47 source snapshots. Bootstrap/q was not independently resampled; this rejected
candidate did not execute a financial-input survivor model experiment.

At this batch's close, M1/M3 had 32 evaluations and M2 had 33 (65 total), with no
new KEEP. Subsequent LLM campaigns may add separate records. The old M2 NO_GO
and all protected-period seals remain unchanged. Regression before runtime:
240 passed, 5 existing warnings; later schema-transport tests are a separate batch.

## Evidence files

`verification.json` checks the complete field transfer; `input_report.json`
records source identities and semantics. `screen/` contains the exact batch,
numerical results, data-input report, lineage and independent verification.
`campaign_final.json` and `model_admission.json` document the frozen no-entry
branch. Full source panels, raw data and SQLite remain local.
