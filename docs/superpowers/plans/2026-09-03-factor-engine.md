# M1 Factor Engine Implementation Plan

> Apply testing-first implementation and focused task review. Work directly in the user-specified non-Git project; preserve a checksummed baseline source snapshot. Use subagents for independently bounded implementation/review where useful, as directed by the subagent-driven-development skill.

**Goal:** Complete FR-001 with eight real-data factor reports and an auditable registry.

**Architecture:** A causal expression engine consumes sealed canonical panels; statistical diagnostics and Qlib portfolios feed a common report and validation-only decision policy. SQLite retains every completed or failed trial.

**Tech Stack:** Existing quant Python, pandas/numpy/scipy, Qlib, SQLite, matplotlib. No new downloads or dependencies.

**Spec:** ../specs/2026-09-03-factor-engine-design.md

## Global constraints

Preserve M0; no vendor edits, no invented exposures, no negative lag, no sign fitting on test, no incomplete horizon labels. Decision gates and cost conventions are fixed in the spec. Record null and reason when data cannot support a diagnostic.

## Tasks

- [x] T1: Freeze M0 source/hashes. Add `factors/expressions.py`, `factors/data.py`, `configs/factors/m1.json` and `tests/test_factor_core.py`. Test hand-derived lag/rolling values, future-perturbation invariance, no-eval whitelist, membership mask, full-horizon split purging and cross-sectional processing before implementing. Interfaces: `FactorDefinition`, `Expression.evaluate(fields)`, `FactorData`, `load_factor_data(root, baseline_config)`, `forward_labels(data, horizon, segment)`.
- [x] T2: Add `factors/analytics.py`, `tests/test_factor_analytics.py`. Test hand-computed correlation, sample count, constant/all-null handling, exposure null semantics, validation-only disposition. Interfaces: `daily_ic(scores, labels, min_pairs=30)`, `summarize_ic(daily)`, `correlation_matrix(factors, min_pairs=30)`, `decide_factor(validation, rules, missing_exposures, corr_existing_pool)`.
- [x] T3: Add `factors/portfolio.py`, `tests/test_factor_portfolio.py`. Implement `run_portfolios(scores, start, end, backtest_config, output, expected_dates)` returning Top10/20 dictionaries and `portfolio_metrics(report)`; characterize actual Qlib next-day score timing using an isolated synthetic provider, and test independent cost/NAV arithmetic. Qlib must already be initialized by caller. No BaoStock/network access.
- [x] T4: Add `factors/registry.py`, `tests/test_factor_registry.py`. Implement versioned SQLite registration, append-only report/error recording and pool lookup; test rejected/error trials survive repeated runs, changed definitions cannot overwrite old versions, and nullable fields serialize legally.
- [x] T5: Add `factors/engine.py`, `factors/report.py`, CLI and PowerShell launcher. Integrate panels, expressions, diagnostics, portfolio, registry and strict JSON/source provenance. Public API `evaluate_factor` and batch config. Run the eight factors on the real snapshot and verify outputs against saved inputs.
- [x] T6: Focused code review, fix material findings, run full tests and artifact/registry acceptance, confirm baseline snapshot hashes. Update README with real results and reproducible commands.

## Progress / decisions

- Scope follows the reference's explicit M1 checklist; M2 decomposition and marginal contribution remain future work.
- Baseline is a non-Git directory: immutable source copy and hashes replace the suggested git commit/tag.
- Existing data cannot support size/industry PIT exposure. FORWARD candidates require this follow-up; failed validation rules still produce REJECT.

- Fix review passed: execution eligibility on limit days, gross absolute return, pending-trial failure persistence, frozen canonical identity, source snapshots before computation. 122 tests passed.
- First trial batch was stopped for review fixes; second encountered Windows Polars `unknown feature flag: sse3` in a Qlib worker. Both retain per-factor FAILED history. Final run uses one Qlib data kernel; research formulas and costs are unchanged.

## Accepted run

`20260903T064735970067Z` completed with exit 0 / PASS. Eight reports: five REJECT, three FORWARD, no KEEP. Independent saved-output verification passed 3,360 sampled RankIC comparisons, 45,915 raw-label cells across three source stocks, and 21,744 portfolio-day records. Report/SQLite/source hashes agree; 16 earlier interrupted/failed trials are retained. Fresh final suite: 122 passed (three upstream Qlib deprecation warnings). Vendor working tree clean and M0 source/artifact checks passed.
