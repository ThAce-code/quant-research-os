# Research scope and working conventions

- Read `docs/PROJECT_CONTEXT.md` and `docs/M2_ROADMAP.md` before changing research scope.
- M0 is frozen; M1 is closed for feature expansion. Fix demonstrated defects when
  needed, but do not redesign the engine, registry or provenance system without a
  concrete research blocker. Do not modify vendor Qlib source.
- The frozen finite M2 study is closed with NO_GO. M2.0–M2.5 deliverables are
  complete; qualification and lockbox have closed no-entry records, neither
  executed nor passed. Do not revive rejected formulas or consume protected
  samples without a new explicit research definition. The active user goal authorizes the full M3.x engineering series; follow docs/M3_ROADMAP.md and preserve original pilot protocols. Bounded LLM generation/refinement is authorized for new research campaigns only. Protected-period access and live trading remain outside scope.
- Full original-scope financial delivery uses 987 complete BaoStock symbol-method
  histories and 465 entirely source-labelled Eastmoney histories. See
  docs/M2_ALTERNATE_SOURCE_PROTOCOL.md and docs/M2_ALTERNATE_SOURCE_AUDIT.md.
  Eastmoney primary values require conservative maximum notice/update time;
  missing dependencies or version timestamps stay missing. Cross-source
  announcement-aligned comparisons are diagnostic only, never primary data.
  Existing BaoStock histories retain legacy publication/revision assumptions.
- BaoStock's 10001011 denial and 8,354 missing responses remain recorded. Do not
  clear data/baostock_access_restriction.json or retry that provider without
  restoration evidence. Alternate data must never be relabelled as BaoStock.
- The 2015–2016 pilot and 2017–2020 diagnostics are already observed history.
  Do not call them fresh OOS. Do not access 2021+ qualification/lockbox observations
  through research scripts until candidate definitions and the corresponding
  numerical qualification/lockbox protocol are frozen. Do not adjust a failed
  candidate on the same qualification sample and present the retry as confirmation.
- Preserve original factor directions, hypotheses and thresholds per experiment.
  Record negative results. Engineering PASS, FORWARD, KEEP and independent
  confirmation are different claims. Linear residuals do not establish model alpha.
- Reuse existing data, fees and same-universe paired comparisons. Keep missing
  values and vendor revision uncertainty visible.
- Test changed research behavior and required regression gates; add new checks only
  for a concrete risk. Avoid expanding audit infrastructure as an end in itself.
- Separate commits by topic. Publish small reports/configurations and source-run
  evidence under `docs/results`; keep raw market data, full feature panels, caches,
  credentials and large experiment artifacts out of Git.

- At the end of every batch and whenever scope changes, update
  `docs/PROJECT_CONTEXT.md` before the final response: update date, evidence
  revision/run IDs, completed work, negative findings, verification, remaining
  gaps and next batch. Synchronize `docs/M2_ROADMAP.md` and these instructions
  when the plan changes. `CONTEXT.md` is a stable pointer, not a second status
  copy. Use canonical M2.0–M2.7 numbering; do not rewrite frozen old reports.
