# M3 model-path engineering integration

Successful run: `20260907T022607184842Z`. ENGINEERING_ONLY.

Executed the same numerical `evaluate_models` path used by admitted candidates:
matched cached Alpha158 rows plus a fixed-seed random candidate → real LightGBM
BASE/ADD fits → real Qlib BASE/ADD/fixed-blend portfolios → cost-adjusted differences
and the existing GO gate → isolated SQLite serialization and read-back.

2 fits, 3 portfolios, 12,217 prediction rows, 57 backtest days (2015 Q1).
All portfolios have nonnegative and nonzero total transaction costs. Net return
difference was replayed from exported daily reports. The synthetic ADD has NO_GO.
Neither that result nor the deliberately random candidate is a research discovery.
The production factor registry remained identical (26 records); M2 uses a separate
registry (33 records). No research candidate was promoted or added by this test.

The first attempt used 150 alphabetically selected symbols. Industry grouping left
insufficient matched data and correctly raised the row gate. Its FAIL record is
retained. The second attempt used full historical symbol coverage with the same seed,
period and row thresholds; no research result guided a candidate modification.

Limits: a single short fold, five boosting rounds, reduced portfolio size, and an
engineering random candidate. This validates numerical integration, not six annual
folds at production settings, genuine screen admission, predictive alpha, capacity,
or qualification/lockbox. Both protected periods remain unopened. No fake passing
screen was introduced. The shared core cannot write to the research registry.

A separate implementation fix moves baseline/source validation before successful
model-result registration. Existing M0/M2 numerical definitions remain unchanged.
Regression: 175 passed, 5 existing warnings in 17.57s.
