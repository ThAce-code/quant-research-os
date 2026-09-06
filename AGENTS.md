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
  Stop adding formulas. Legacy industry-text handling is corrected without
  future backfill. The frozen rolling protocol has completed 24 fits and six
  paired portfolios; corrected run 20260906T092732142566Z is NO_GO and has
  independent prediction replay verification. Conditional diagnostics are done.
  BP has priority but is not the only research direction.
  Full-history profitability/growth data remains incomplete: 8,354 of 40,520
  requests are missing after BaoStock error 10001011 (explicit blacklist).
  Do not waive this task because models are NO_GO. The local guard at
  data/baostock_access_restriction.json stops collection before networking.
  Do not retry BaoStock or bypass the denial without evidence of restored access;
  legitimately supplied missing raw caches can also unblock offline completion.
  The user has now authorized trying AKShare as an independent alternate source.
  Two-stock historical statement reconstruction matches all 17 comparable cached
  values within 1e-6; this is feasibility only. See docs/AKSHARE_FEASIBILITY.md.
  Continue alternate-source coverage/date validation with separate provenance;
  do not label its responses as BaoStock or infer full coverage from this sample.
  Full five-field independent verification and overall M2 completion remain open.
  Qualification and lockbox have recorded no-entry decisions: neither was
  executed or passed. Do not start M3 agents,
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
