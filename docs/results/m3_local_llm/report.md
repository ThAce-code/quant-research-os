# M3.1–M3.3 and M3.5: real model research loop and advisory review

The bounded engineering pipeline completed real generation, three feedback rounds,
restart, screening, once-only rolling model increment and opposing advisory reviews.
The sole screen-admitted generated candidate finished **NO_GO**. This is an
engineering acceptance, not independent-alpha or full-paper reproduction evidence.

## Runtime and preserved failures

The pre-existing Gemma-4-E4B-it Q4_0 weights ran through local llama.cpp build
10282 (`a035a8887`) at loopback port 18341. No weights were downloaded. The model
file digest and exact runtime arguments are in `runtime_identity.json`. Startup,
actual inference, status and owned-process shutdown were verified; the temporary
service is stopped. Health alone was not treated as inference acceptance.

Four separately frozen finite campaigns consumed **7 generation calls, 6,305
reported output tokens and 14 proposal attempts** in total. The first two produced
only invalid DSL/metadata. V3 evaluated one candidate (REJECT, RankIC −0.02463029)
and retained three invalid attempts, including omitted input fields. Its model
description incorrectly called canonical close-to-previous-close `returns` an
intraday return. That original record is retained with this limitation.

The schema transport fixed JSON structure without relaxing the local AST checker.
Implementation `6ae15dc` then made new-call field/operator metadata come from the
frozen canonical catalog and actual expression. It preserves raw model text,
formula, direction and rationale; it does not establish rationale correctness.
Old calls were not retrospectively repaired. V4 was frozen in `3ffe8f4` before
new generation. New equations remain adaptive historical exploration; none of
these format campaigns replaces a failed study with a confirmatory result.

## Three-round V4

The fixed budget was six proposals/evaluations, three calls, 6,144 reserved output
tokens, three rounds and one final model run. V4 used all six proposal/evaluation
slots and three calls (3,092 reported output tokens). Parents are selected by ID,
not performance. Screen runs are `20260907T042723123686Z`,
`20260907T042811623931Z`, `20260907T042901973993Z`.

| Proposal | Round / parents | Exact formula | Direction | RankIC | Screen |
|---|---|---|---|---|---|
| 18 | 0 / none | `returns / (turnover - TsRank(turnover, 5))` | −1 | −0.02024661 | REJECT |
| 19 | 0 / none | `(close - vwap) / (volume + 1)` | −1 | 0.01407725 | FORWARD |
| 20 | 1 / 18,19 | `Abs(returns) / (turnover - TsRank(turnover, 5))` | −1 | −0.00076453 | REJECT |
| 21 | 1 / 18,19 | `Abs(close - vwap) / (volume + 1)` | −1 | −0.01024047 | REJECT |
| 22 | 2 / 20,21 | `Abs(returns) / Mean(turnover, 10)` | −1 | −0.01828827 | REJECT |
| 23 | 2 / 20,21 | `Abs(close - vwap) / Abs(returns)` | −1 | −0.00095010 | REJECT |

Reopening the persistent ledger and invoking the identical loop returned
SEARCH_COMPLETE with an unchanged snapshot: zero extra calls/evaluations. Both
negative parent outcomes reached the third round. The fixed final selection rule
admitted only proposal 19; no threshold, sign or formula was edited afterward.

## Full model and independent checks

Model run `20260907T043013673204Z` performed 12 LightGBM fits over six annual
folds, 246,003 prediction rows and three matched-cost portfolios over 1,359 days.
The primary ADD comparison had RankIC increment **0.00180469**, interval
**[−0.00100578, 0.00470562]**, q **0.11294353**. Mean daily net increment was
−0.0001724092, or **−4.103338%** under the frozen 238-day arithmetic annualization.
Only one of five complete years was positive. Final decision: **NO_GO**.

Direct canonical formula replay checked 2,125,728 raw cells and 300 sampled daily
RankIC observations across all six candidates, plus registry and snapshot hashes.
The third-round verifier initially multiplied the VWAP numerator before division;
near-zero return denominators amplified floating-point order differences. Matching
the canonical arithmetic order fixed the verifier; tolerances and research results
were unchanged. `verify_generated.py` records the final explicit formulas.

The separate model verifier replayed 360 saved-model predictions, all BASE/ADD
daily RankIC values, annual net increments and gate decisions, checked 46 source
snapshots and 29 artifacts, and matched the numerical registry. Bootstrap/q was
reused, not independently resampled; no fill-level replay or capacity claim.

## Advisory review and delivery

Implementation `32cf325` produced two real local-model reviews with separate
supportive/critical roles, a fixed two-call budget and 765 reported output tokens.
Evidence IDs and source/registry identity were checked. All three research
database hashes stayed unchanged; repeating the review made no additional call.
The critical review explicitly reports the model NO_GO. Both outputs are largely
summaries, with limited deep economic criticism. Two roles on one model are not
independent experts, and cited prose is not automatically fact-checked or empowered
to change numerical admissions. Raw reviews are in `auditor/state.json`.

Final regression: **251 passed, 5 existing warnings, 28.99 seconds**. The explicit
abort path additionally covers unresolved calls, provider overrun and a completed
response stranded by a concurrent proposal-budget race, preserving all charges
and raw responses. These failure cases are isolated tests, not fake production
factors. Final M1/M3 registry count is 40 and M2 is 33 (73 total); no new KEEP.
M0 identity and M2 NO_GO remain unchanged; 2021–2025 remain sealed.
