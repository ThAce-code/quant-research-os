# M3 campaign controller and full survivor research run

The fixed Alpha34 candidate passed historical screening and then failed the
unchanged model increment gate: **NO_GO**. This completes a real survivor branch
through the research kernel. It does not establish independent alpha or complete
the full M3.x engineering series.

Protocol commit: `8660b7c`; campaign implementation: `9f43183`; attachment repair:
`5d60a8b`. Screen: `20260907T025821527769Z`. Full model run:
`20260907T030012969333Z`.

The formula was reconstructed from [101 Formulaic Alphas, Appendix A, Alpha#34](https://arxiv.org/pdf/1601.00991v3),
page 10, before observing this candidate's local result. The original windows and
positive direction were fixed, with local field, standard-deviation and rank
semantics explicitly declared. It is not a reproduction of the proprietary
paper universe or its reported returns. The previous two pilot formulas were
re-imported only in a zero-evaluation duplicate check and both were rejected as
duplicates against the old registry.

| Evidence | Result |
|---|---|
| Five-day screening RankIC, 2015–2016 | 0.0112799503 |
| Screening BH q (one fixed candidate) | 0.0034982509 |
| 2016 technical conditional residual RankIC | 0.0040853735; diagnostic only |
| Model RankIC increment | 0.0002597898 |
| Model increment q | 0.4262868566 |
| Mean cost-adjusted annual increment | −3.010958995% (238-day arithmetic convention) |
| Positive full years among 2015–2019 | 2 of 5 |
| Model decision | NO_GO |

BASE used all 158 technical features; ADD used the identical rows plus Alpha34.
Six expanding-window annual folds, 2015 through July 2020, produced 12 real
LightGBM fits and 242,757 prediction rows. Three full, matched 1,359-day portfolios
were executed with the frozen costs: BASE, ADD and the fixed 75/25 diagnostic
blend. No formula, seed, model parameter, threshold or blend weight was optimized.

The independent verifier replayed 360 predictions from all 12 saved models,
recalculated all 1,359 daily RankICs for each model, recalculated annual net
increments from the three portfolio reports, checked shared samples and fold
boundaries, and matched the final numerical registry record. It verified 41
source snapshots and 28 artifact hashes. Bootstrap intervals/q were read from
the saved experiment rather than independently resampled. There was no
fill-by-fill execution or live capacity validation.

The first controller attachment stopped after numerical screening had already
succeeded because the archived protocol was pretty-printed and its bytes no
longer matched the original config. The repair verifies the original source
snapshot hash and parsed content. `attach-screen` recovered the existing run
without rescreening. Repeating attachment and memory retrieval was deterministic;
the production registry count stayed 28. The M2 registry remains 33, so the two
registries now contain 61 evaluation records. No KEEP was added.

The source cache remains the already-observed research history; no qualification
or lockbox data was opened. Historical FORWARD is preserved in the screen record,
and the later NO_GO appears in the model record. Current campaign memory exposes
screen feedback; automatic aggregation of model outcomes and adaptive campaign
freeze/admission remain outstanding M3.x controller work. Real LLM service
acceptance, multi-round operation, external generator runs, research auditor and
fundamental-panel adapters remain outstanding.

Public files here are small reports and ledger snapshots. Full panels, models,
SQLite files and raw market data remain local. Reproduce verification with:

```powershell
python scripts/verify_m3_increment_run.py experiments/m3_increment/20260907T030012969333Z --output experiments/m3_campaigns/acceptance_v1/increment_verification.json
```
