# M3.4: genuine external generators and common-engine admission

**Engineering acceptance passed for bounded AlphaSAGE/AlphaForge generation,
export translation, real candidate import and numerical screening. All three
screened candidates were REJECT; both campaigns froze empty and returned
NO_ENTRY with zero model fits and zero portfolios.** This is not a full-paper
performance reproduction or evidence of independent alpha.

Implementation/protocol: `640fad7` (canonical VWAP), `be2b4d4` (adapters and
fixed import campaigns). The single generation configuration was saved before
each generator ran; import rows, signs and evaluation/model budgets were committed
before local screening. No generator was rerun to obtain better formulas.

| Source | Generation run | Actual algorithm execution | Export/import |
|---|---|---|---|
| AlphaSAGE | `20260907T033952178556Z` | Native GNN encoder, GFlowNet loss/sampling/pool; 64 trajectories, 8 optimizer updates | 5 native pool expressions; fixed first 3 attempted, 1 accepted and 2 unsupported/invalid |
| AlphaForge | `20260907T034031298675Z` | Native predictor/DCGAN/masker and losses; 140 initial proposals, 3 predictor epochs, 3 generator epochs | Both post-training export rows accepted; no score-based sign selection |

Both use the pinned official revisions in [upstream interfaces](../../M3_UPSTREAM_INTERFACES.md).
The CPU driver supplies sealed canonical tensors to native StockData objects,
bypassing network loaders; it bounds the native training instead of replacing it
with another search algorithm. AlphaForge retains its native best-weight reload
(the best generator checkpoint was epoch 0), and its native empty-score warnings
remain in the log. Thus training executed, but no claim of a successfully improved
generator follows. AlphaSAGE retains its upstream scheduler warning. Neither
upstream checkout was modified.

Generation dates: 2010–2012; diagnostic/logging dates: 2013. With lookback and
label padding, consumed tensors span 2009-08-06–2013-02-21 and
2012-08-07–2014-02-19 respectively. All 726 historical CSI300 symbols are
represented with historical membership masking and missing observations. These
are not current-constituent backtests. Research data access remains before 2021.

## Numerical translation and data identity

- Both exporters are parsed as CSV/JSON and a restrictive AST; no incoming code
  evaluation or pickle loading. AlphaForge's actual infix spelling is supported.
- Arithmetic, inverse, absolute value and a subset of historical windows map to
  local operators. Rank/TsRank, Log, higher moments and other unaligned operators
  fail explicitly. In particular Log(0) differs inside nested formulas, and
  zero-lag upstream Delta has incompatible slicing. Constant-only panel operations
  are rejected. Unsupported attempts consume proposal budget and stay in lineage.
- Each upstream was checked on 13 controlled numerical cases with ties, zeros,
  negative values and NaNs. Every supported export row was additionally replayed
  on actual training and diagnostic tensors against native implementations:
  AlphaSAGE rows 0/3/4, AlphaForge rows 0/1. Missingness matches and values satisfy
  rtol/atol 2e-5. This is finite numerical coverage, not a proof of every possible
  expression or singular intermediate value.
- VWAP is canonical CNY amount / raw shares × price-adjustment factor. Zero
  volume, suspended rows and missing amount remain missing. An independent raw
  calculation checked 2,282,544 cells (1,133,458 finite). All seven previous
  factor fields, membership, execution eligibility and benchmark match the
  pre-extension implementation exactly; the frozen M0 identity was verified.

## Fixed local screen

| Candidate | Exported score meaning | 2015–2016 RankIC | q | Verdict |
|---|---|---:|---:|---|
| SAGE_EXPORT_ROW0 | −2 − adjusted high | −0.0153607634 | 0.985507 | REJECT |
| FORGE_EXPORT_ROW0 | 1 / (−0.01 × adjusted VWAP) | 0.0079059206 | 0.258871 | REJECT |
| FORGE_EXPORT_ROW1 | 2 − ((adjusted VWAP + 10) − 30) | −0.0156041754 | 0.986007 | REJECT |

All directions are +1, fixed before local screening. Native absolute-IC rewards
and pool weights do not establish that sign. These price-level formulas have
weak economic interpretation and sensitivity to adjustment conventions. We did
not simplify, invert, replace or tune them after observing their outcomes.

Screen runs: `20260907T034802617924Z` and `20260907T034848603170Z`.
Independent replay directly from canonical bars checked 1,062,864 raw factor
cells, sampled 150 daily RankIC values, matched three registry entries, and
verified 45 source snapshots in each run. Bootstrap/q was not independently
resampled. Conditional diagnostics remain partial technical-reference diagnostics.
No candidate qualified for the model stage; this batch therefore supplies no new
model-increment performance evidence.

The common M1/M3 registry now has 31 evaluations; the separate M2 registry has
33, total 64. No new KEEP. The old M2 NO_GO, previous paper results and
2021–2025 seals are unchanged. Regression: **233 passed, 5 existing warnings**.

## Reproduction and limits

Use `scripts/run_m3_searcher.py SOURCE` with the isolated search environment and
`configs/m3/searcher_integration.json`. Re-running is a new search attempt and
must receive a new research budget; reproducing engineering does not authorize
replacing the frozen campaigns. Native source hashes, driver bytes, runtime,
input contract, raw export, logs, adapter replay, ledger and screen evidence are
published in the source subdirectories. Models/tensors stay local.

`scripts/verify_m3_searcher.py GENERATION_RUN` performs native/local replay;
`scripts/verify_m3.py SCREEN_RUN` verifies these fixed raw formulas and sampled
IC; `scripts/verify_m3_vwap.py` compares the legacy data implementation and raw VWAP.
The runtime overlays pinned CPU packages onto the existing quant environment;
[runtime_overlay.txt](runtime_overlay.txt) is the overlay, not a standalone full
environment lock. Exported manifest periods alone are producer declarations;
local run and replay evidence is what supports this batch's acceptance.

M3.4's bounded adapter requirement is now verified. Full M3.x remains incomplete:
real LLM generation/multi-round children, the research auditor, and a shared PIT
fundamental-data contract still require delivery and runtime evidence.
