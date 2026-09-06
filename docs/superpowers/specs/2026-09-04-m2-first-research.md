# M2 infrastructure v1 and first value-factor research

This batch is an exploratory historical study, not an independent alpha confirmation.
The authoritative preregistration is `configs/factors/m2_first.json`; it is copied
and hashed with all executing Python sources before downloading any new data.

## First batch

- Historical CSI300 membership and execution data come from the frozen M0 snapshot.
- Data window December 2014 through December 2016; evaluate 2015 and 2016 jointly
  and individually. These dates have already been observed during M0/M1 research.
- Exactly three positive-orientation candidates: BP=1/pbMRQ, EP=1/peTTM,
  SP=1/psTTM. Nonpositive denominators are excluded, not flipped or winsorized
  into positive values. Daily vendor valuations lag one trading day with no fill.
- Raw and industry/size residualized versions give six primary hypotheses at h=5.
  The h=20 report is diagnostic only. No formula/window selection from results.
- Industry uses month-end historical snapshots, no earlier than the next trading
  day after the requested snapshot date, max age 62 calendar days. updateDate
  cannot exceed the requested date. This is a delayed monthly proxy, not complete
  industry event history or independently established publication-time data.
- Size = log(raw close * raw volume / (turn percent / 100)); require turn >=0.01%
  and <=100%, positive raw price/volume and active observation. This estimates
  circulating capitalization, not strict free-float capitalization. Quarterly
  liqaShare comparisons are diagnostics because shares can change between reports.
- Quarterly pubDate-constrained joining is implemented and verified on 3 real
  stocks for 2014-2016. It is not a full-market quarterly factor dataset. Same-day
  reports are unavailable; stale values and newly missing values remain missing.
  Older fiscal periods cannot replace newer published periods. Unknown historical
  vendor revisions remain an explicit limitation for every factor.
- Cross-sectional clipping and z-score use M1 rules. Neutralization regresses on
  intercept, standardized log size and industry dummies with one reference group;
  groups with fewer than five usable stocks are excluded. Orthogonality is a
  calculation check, not evidence of alpha. Portfolio exposures may differ.

## Portfolio and inference

- Reuse verified Qlib Top30/Top60, next-close execution, exact M0 fees and uniform
  9.5% limit approximation. No short-execution claim. Report double explicit fees
  as sensitivity; no calibrated market-impact/capacity claim.
- Reference: negative 20-day return volatility, residualized by the same process.
  Each of three blends is fixed at 25% neutral candidate, 75% reference. Reference
  and blend use the same candidate-available universe and cross-sectional scaling.
- Date-block bootstrap: circular blocks 20 trading dates, 2000 draws, seed 42;
  confidence intervals for means and centered one-sided positive-mean p-values.
  BH adjustment covers all six primary IC hypotheses. Three paired portfolio
  increment tests form a separately disclosed secondary family.
- Historical screen: coverage >=70%, RankIC >=0.01, primary q<=0.10, positive
  top60 net excess and positive RankIC in both years. Passing means FORWARD only.
  Increment evidence additionally requires lower paired CI>0, secondary q<=0.10
  and annual increase >=1 percentage point. No KEEP in this historical pilot.
- Dedicated append-only `data/m2_factor_registry.sqlite` avoids admitting pilot
  controls into the M1 KEEP pool. All controls are identified explicitly.

## Acceptance and remaining M2 work

Raw requests, source snapshot, processed panels, report dates, label boundaries,
daily IC, costs, statistical calculations and registry parity must be auditable.
Failures retain a run directory and error. latest points only to successful runs.
M0 code/artifacts and Qlib data hashes are checked; sources/data are checked again
at completion. Time leakage, missing data and neutralization tests must pass.

Full quarterly data, Alpha158 decomposition, clustering, rolling model add/drop
experiments, independent qualification and lockbox are subsequent M2 deliverables.
2021 onward is not accessed in this first batch. Engineering PASS does not mean
all M2 research capabilities are complete or any independent alpha was found.
