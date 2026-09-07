# M3 daily and fundamental input contract

`configs/m3/data_contract_v1.json` is the explicit boundary for existing data.
Every new campaign evaluation binds its exact SHA256 before reserving numerical
work. The screen and model stages verify that binding and share the same loader.
Different contract bindings cannot be silently combined across screens. Original
daily-only batches without a binding remain readable and retain their identities;
PIT fields cannot enter such a legacy batch.

| DSL field | Existing source field | Interpretation |
|---|---|---|
| pit_roe | roeAvg | Vendor reporting-period ROE |
| pit_net_margin | npMargin | Net profit / operating revenue ratio |
| pit_earnings_growth | YOYNI | Year-over-year net income growth |
| pit_asset_growth | YOYAsset | Year-over-year total asset growth |
| pit_equity_growth | YOYEquity | Year-over-year equity growth |
| pit_cashflow_margin | CFOToOR | Operating cash flow / operating revenue |

These ratios are transferred without rescaling. Do not sum quarterly ratios or
label them as reconstructed TTM measures. Daily open/high/low/close, volume,
turnover, returns and VWAP retain the existing canonical definitions. Unknown
event, text, order-flow or alternative fields fail the DSL/contract boundary.

The first five fields reuse the independently verified full-history M2 panels
`20260906T134337933185Z`: 987 BaoStock symbol/method histories and 465 whole-history
Eastmoney substitutions, with explicit source assignment. CFOToOR reuses
`20260906T072711741731Z`. The contract pins each panel, its source artifact
manifest, independent verification and applicable source-assignment evidence.

All panels require publication strictly before the signal date, latest-fiscal-
period priority, at most 400 calendar days since availability and 550 days since
fiscal period end. The already-built source panels implement this selection;
the M3 adapter verifies identity and reindexes without filling. No acquisition,
new historical reconstruction, source substitution or date guessing happens here.

BaoStock retains original publication alignment with unknown revisions.
Eastmoney uses conservative maximum notice/update times across formula
dependencies and cannot recover historical versions. Missing current values or
unknown dependencies remain missing. No claim of full-vintage PIT follows from
this engineering contract.

**Fields are independently available latest reports. They are not guaranteed to
refer to the same fiscal period.** Mixed-field formulas must explicitly account
for this limitation; the adapter does not silently reconcile reporting periods.
If an economic hypothesis requires same-period accounting arithmetic, a separately
specified alignment adapter is required before treating that arithmetic as such.

The common input report records units, availability/revision rules, source hashes,
finite coverage and lack of cross-field fiscal alignment. Inputs are checked again
before numerical outcomes are registered. Protected dates are rejected in the
contract before market loading and in the actual panel axes after identity checks.

For finite runtime acceptance, `configs/m3/pit_equity_v1.json` fixes a new
negative-equity-growth hypothesis. Its direction comes from a proposed capital-
discipline mechanism before local evaluation; it is not an exact paper factor or
a retuning of the closed asset-growth hypothesis. The single-candidate budget is
in `campaign_pit_equity_v1.json`. Outcomes are historical exploratory evidence,
and only the unchanged screen can admit a model run.

Run `scripts/verify_m3_inputs.py` to check all six source panels, unchanged daily
fields and cutoff invariance against local sealed data. This verifies input
transfer; the separately pinned original data audits supply publication-selection
evidence. Vendor historical revision accuracy remains unverified.
