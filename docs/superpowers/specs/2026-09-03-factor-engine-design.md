# M1 / FR-001 Factor Research Engine

Source: user-requested M1 in ChatGPT conversation `6a95a920-96f0-83e8-bf97-ec53ae940952`.

Deliver a working `evaluate_factor(factor, universe='csi300', horizon=5, experiment=...)` API and batch CLI. Calculate eight preregistered, interpretable factors on the sealed BaoStock snapshot, evaluate them and preserve successful, rejected and failed trials in SQLite. Do not tune or rerun the M0 LightGBM baseline. Preserve its code and artifact hashes under permanent ID `BL-CN-CSI300-A158-LGBM-001`.

## Calculation and timing contract

- Wide date-by-instrument panels on the exchange calendar; backward-adjusted OHLC, inversely adjusted volume, original turnover percentage divided by 100. Suspended/zero-volume prices are missing, with no forward/backward fill. Rolling operations require complete windows.
- Declarative expressions use whitelisted fields/operators and bounded nonnegative historical lags (`Ref(close,20)` means 20 trading days ago). No Python eval, attributes, arbitrary calls or negative/future lag. Factor definitions carry version, hypothesis, source and fixed orientation.
- Eight seeds: MOM_20, MOM_60, REV_5, VOL_20, TURNOVER_MEAN_20, TURNOVER_CHANGE_20, VOLUME_RATIO_5_20, PRICE_POSITION_60. Direction is fixed before evaluation. VOL and the three turnover/volume factors use negative orientation; momentum/reversal/position use positive orientation.
- Apply exact historical membership on each signal date; cross-sectionally clip at 1%/99%, z-score, do not impute missing observations. All calculations are available after close t; earliest execution is close t+1.
- h-day label = adjusted close[t+1+h]/close[t+1]-1. Entry/exit must be tradable, including the frozen Qlib uniform 9.5% limit on exported float32 change. Observable prices/scores on limit days remain available; endpoint execution uses a separate eligibility panel. Purge labels whose exits cross the end of train/valid/test, separately for each h in 1,2,5,10,20. Do not shorten horizons to use incomplete tails.
- No assumption that vendor historical snapshots prove original publication-time availability. Verify the existing sealed data; expose this PIT limitation in all reports.

## Evaluation contract

- Per split: daily Pearson/Spearman IC, mean/std/ICIR/positive ratio/coverage, decay for all horizons, yearly and regime stability. Regimes are known-at-t trailing60-day benchmark return >5% bull, <-5% bear, otherwise sideways.
- ICIR is unannualized. Daily cross-sectional correlations use pairwise complete observations (minimum 30). Correlation matrices are averages of daily Spearman correlations, separately by split.
- Exposures include volatility and turnover. Historical size and industry are unavailable in M0 and must be JSON null with explicit missing-data reasons, never zero or current classifications. M1 does not download or infer them. A factor cannot receive KEEP while required exposures are missing.
- Top10%/20% portfolios use Qlib TopkDropoutStrategy, topk=30/60 and n_drop=topk, on validation and test periods, prior-day scores and the same M0 fees, limit threshold, execution price and initial capital. Actual fills/holdings follow Qlib. These are ranking portfolios, not the baseline Top50/drop5 model.
- Long-short is an explicitly hypothetical gross cross-sectional top-minus-bottom forward-label spread. No assertion of A-share short availability, net return or executability; no overlapping-horizon CAGR.
- Portfolio metrics include gross/net absolute and excess returns, turnover/cost, arithmetic annual excess/IR/drawdown (238 days), compound net return/CAGR/NAV drawdown. Validate date coverage and finite returns/positive costs on trading days.
- Research disposition is determined only from validation: coverage >=70%, >=100 IC days, oriented RankIC >=0.01, positive RankIC ratio >=50%, Top20% net excess >0. Failed gates -> REJECT. High absolute correlation >=0.90 with an existing KEEP pool -> REJECT. Otherwise unresolved size/industry exposures or empty reference pool -> FORWARD. KEEP means research-pool admission, not trading approval. Test performance never changes direction or status.
- Store rejected trials and execution errors. Alpha158 decomposition, neutralization, fundamental factors, clustering and marginal contribution belong to M2; agent generation belongs to M3.

## Artifacts / acceptance

Immutable run folder with frozen definitions/config/source hashes/data identity, raw/processed factor values and labels, daily IC, decay/stability/exposure/correlation, Qlib daily portfolio CSVs, unified FactorReport JSON, Chinese Markdown report and diagnostic plots. SQLite factors/evaluations preserve versions and append trials; missing numbers are SQL NULL/JSON null. RUNNING becomes PASS only after files and registry succeed; failures record FAILED and the error.

Tests must catch future access, future-data sensitivity, membership leakage, split label leakage, wrong IC and cost accounting, test-driven selection and lost rejection/error history. Run all eight factors on real cached data, check reports and registry, and verify the frozen M0 hashes remain unchanged. No root git repository exists; use a source snapshot rather than initialize/git-tag the workspace or modify vendor.

Reference: https://qlib.readthedocs.io/en/latest/component/strategy.html
