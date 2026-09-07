# R1: finite mechanism-led alpha discovery

Status: protocol frozen before factor/return evaluation. User authorized R1
research after M3 engineering closed. The objective is a bounded empirical answer
about useful incremental factors/combinations, not a guaranteed alpha or paper
trading launch. M0/M2/M3 historical definitions and outcomes remain immutable.

## Data feasibility decisions

The read-only raw-cache audit checked 16,102 profit requests (15,683 records) and
20,260 cashflow requests (19,762 records). There are 15,479 matched fiscal-period
records with both releases no later than 2020-07-31; all but one have the same
publication date. No provider requests or return evaluations occurred in this audit.

An assets-scaled cash surplus cannot be produced from full-scope cached raw amounts.
MBRevenue is present in fewer than half the profit records; netProfit/MBRevenue
often differs materially from npMargin. It is not a reliable shared revenue
denominator. Two draft definitions are charged as data-definition rejections.
Cashflow-to-profit times net margin closely matches CFOToOR for most same-period
records (median absolute difference 4.51e-7); records that fail the frozen algebra
check remain missing. This supports a same-period cash-surplus **ratio proxy**, not
reconstructed original cashflow amounts or proof of original historical vintages.

Strict earnings-surprise/PEAD is not claimed: missing consistent revenue and
expectation inputs led to two predeclared profitability-change hypotheses instead.
No final factor result was used to make this data-definition choice. The tested
families are cash quality, seasonal profitability change, and liquidity-conditioned
price response. Source financial histories remain BaoStock-only and revision
unknown; previously collected Eastmoney subset histories are not mixed into these
financial arithmetic operations. Unavailable BaoStock requests remain absent.

## Fixed research design

`configs/r1/protocol.json`, `candidates.json` and `freeze.json` are authoritative.
There are six numerical candidates, two earlier data-definition rejections and
four unallocated slots, under a maximum 12-attempt budget. No automatic refinement
or additional hypotheses after results. All final directions are fixed positive;
the contrarian sign is already inside the quiet-reversal formula.

Each financial comparison joins the exact same code/fiscal quarter and becomes
usable strictly after the latest required publication. A new partially available
quarter invalidates stale old values. Seasonal differences require the previous
year's same quarter. Age limits are 400 days since availability and 550 days since
current fiscal period. Unknown vendor revisions are not recovered.

The primary target is close(t+21)/close(t+1)-1, with 20 trading days of exposure.
Screening uses already observed 2015–2016. Models use annual 2015–2020 expanding
folds, prior-year validation and 21-date label-reach purging. Both the Alpha158 BASE
and every ADD use the same new 20-day target and common feature-defined universe;
this does not amend the old one-day experiments or call history fresh OOS.

All six candidates receive industry/size-neutralized IC, coverage, per-year and
60-day-block inference diagnostics. The primary screen uses a fixed 12-test BH
family (unused/data-rejected slots contribute p=1). The frozen 20-PC technical
map supplies an explicitly partial conditional diagnostic in 2016; it retains
77.7% representative variance and cannot establish full technical independence.

For combination research, choose the first candidate in each family's fixed order
with >=70% coverage and positive RankIC in both screen years. This predeclared weak-
positive route need not pass standalone significance; it grants model exploration,
not a positive standalone finding. At most three representatives produce all
nonempty subsets versus BASE, at most eight variants/48 fits/eight portfolios.
All primary comparisons share a fixed seven-test BH family. Full-bundle-minus-one
contrasts are diagnostics; no fitted blend weights or return-ranked parent choice.

Holdings are adjusted on a fixed five-trading-day schedule with Top50/drop5 and
the frozen M0 fee/limit/close-execution approximations. No off-schedule signal is
forward-filled into an extra rebalance. The same schedule and universe apply to
every variant. Model parameters are unchanged, 1000 maximum rounds/50 early stop,
seed 42. A model run requires >=100,000 train and >=20,000 validation rows per fold;
otherwise preserve DATA_GATE_FAIL, not a profitability verdict.

Historical GO requires delta RankIC >=0.002, BH q<=0.10, annualized net increment
>=2%, strictly positive net-increment lower interval and four positive complete
years out of 2015–2019. Annualization remains 238-day arithmetic. No admissible
representatives means NO_ENTRY. Exhausted failing comparisons mean NO_GO.
No signs, periods, cutoffs or budgets are adjusted to rescue results.

## Delivery and research limitations

Deliver data/causality verification, all six screens, conditional diagnostics,
eligible subset model/cost comparisons or explicit no-entry/data-gate records,
independent numerical replay, existing-registry lineage, and a final report.
Publish compact evidence and update PROJECT_CONTEXT.md with separate commits.
Raw market/financial panels and full models remain local.

All results remain historical exploratory evidence. Repeated campaigns and current
LLM/paper knowledge are not erased by a new ID. 2021–2025 remain sealed; a historical
GO requires a separate prospective qualification decision. No broker, order,
paper-account connection or live trading is included in R1.

Research references: [Sloan's accrual/cashflow study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2598),
[AlphaAgent hypothesis/formula alignment](https://arxiv.org/abs/2502.16789),
[anomaly transaction costs](https://www.nber.org/papers/w20721).
These motivate hypotheses/design; their published performance is not a local result.
