# Research scope and working conventions

- Read `docs/PROJECT_CONTEXT.md` and `docs/M2_ROADMAP.md` before changing research scope.
- M0 is frozen; M1 is closed for feature expansion. Fix demonstrated defects when
  needed, but do not redesign the engine, registry or provenance system without a
  concrete research blocker. Do not modify vendor Qlib source.
- Alpha158 mapping and the first four-family historical screen are complete.
  The three new quarterly formulas failed their frozen screen; do not flip signs
  or retune this batch. Three formulas on two years do not close the economic
  families. Comparability diagnostics are complete; the next two-formula batch
  is frozen in configs/factors/m2_supplementary.json. Its collection and fixed
  historical screen have now run; both supplementary formulas are IC_SCREEN_REJECT.
  Stop adding formulas. Resolve the observed 2008–2012 legacy industry-text
  compatibility gap without future backfill, then freeze a bounded rolling
  model protocol and validate its training coverage before execution.
  BP has priority but is not the only research direction.
  Full-history data and M2 completion gates remain open. Do not start M3 agents,
  dashboards or trading automation as part of this work.
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
