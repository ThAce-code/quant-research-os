# BaoStock baseline implementation plan

**Goal:** Run the referenced Alpha158 + LightGBM CSI300 experiment on BaoStock data.

**Architecture:** Cache source responses, validate canonical daily data, export to an isolated Qlib directory, run the unchanged model and explicitly documented timing safeguards. Keep all artifacts under this project.

**Tech Stack:** Existing quant Conda environment, BaoStock 0.9.3, pandas, pyarrow, Qlib, LightGBM.

**Spec:** ../specs/2026-09-02-baostock-baseline-design.md

## Constraints

No demo prices, no current-membership historical backfill, no fabricated market metrics, no vendor edits. This directory has no parent Git repository; preserve vendor repositories and do not initialize or commit them.

## Tasks

- [x] Data integrity: tests/test_data.py tests canonical conversion, duplicate rejection, as-of factor application, suspension and historical membership. Implement src/quant_research/canonical.py and baostock_data.py. Run `python -m pytest tests/test_data.py -q` before and after implementation.
- [x] Qlib bridge: test native float32/calendar alignment, volume/price conservation and membership re-entry in tests/test_qlib_export.py. Implement qlib_export.py. Run `python -m pytest tests/test_qlib_export.py -q` before and after implementation.
- [x] Experiment: config defines original model and portfolio settings. Test label-boundary purge in tests/test_baseline.py; implement baseline.py and scripts/run_baseline.py. Run focused tests then `python scripts/run_baseline.py` with real data.
- [x] Validate: inspect saved prediction dates, daily backtest, IC and cost metrics, persist a Chinese report with assumptions and exact rerun command. Record actual completed stages and failures.

## Completion evidence

Run `20260902T145556871363Z` completed with process exit 0 and `status.json` PASS. Download and raw-to-canonical audit completed for 4,518 source requests and 1,176,379 price rows. All 18 tests passed; vendor Qlib working tree remained clean.

`final_verification.json` independently recomputes signal and net excess metrics from saved predictions, labels and daily returns. Test coverage is 871 days and 261,297 predictions. The three missing expected member rows are SH600005 on 2017-02-15 through 2017-02-17; source bars end on 2017-02-14. No out-of-universe predictions were present. These source gaps are disclosed in the report.
