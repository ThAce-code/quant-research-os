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
- BaoStock's historical 10001011 denial and 8,354 missing responses remain recorded.
  Preserve data/baostock_access_restriction.json as historical evidence. An explicitly
  user-authorized single recovery probe is allowed without prior restoration proof;
  stop on denial and never bypass provider controls. The 2026-09-07 probe succeeded
  for login and one growth query; see docs/results/baostock_probe_20260907/result.json.
  This does not establish event-endpoint availability or sustained bulk capacity.
  Alternate data must never be relabelled as BaoStock.
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

- The user has now authorized the finite R1 empirical study. Follow docs/R1_PROTOCOL.md and the frozen configs/r1 files. R1 may adapt the 20-day label, purging and fixed rebalance schedule in its own modules, reusing existing numerical kernels. M3 engineering remains closed; no new generic framework. R1 cannot open 2021+ samples or trade.

- R1 is now complete with NO_GO; see docs/results/r1/report.md and docs/R1_COMPLETION_AUDIT.json. Preserve its six candidate results, single model-stage budget and source snapshots. Do not spend its four unallocated slots, retune failed candidates or open another research campaign without a new user-authorized definition.

- The user's subsequent "continue" authorizes the proposed event-data feasibility work. R2 starts with the bounded 2015/2016 event audit in configs/r2/event_audit.json, without factor/return evaluation. Check announcement versions and historical availability before defining an event experiment; preserve all R1 results and protected samples.

- The user additionally authorized filling event-data gaps using suitable alternative sources/websites. Archive primary CNINFO notices under configs/r2/announcement_backfill.json for the current 2015/2016 Q1 scope; distinguish index/PDF delivery from verified numeric version chains. BaoStock restoration remains unconfirmed and its restriction record stays intact.

- R2 bounded primary backfill now contains 211 documents; see docs/results/r2_backfill/report.md. This is document delivery, not numerical/event admission or full historical recall. Next work must resolve numeric/period/version checks and event deduplication on existing documents before defining factor tests. Keep qualitative bounds null and source conflicts explicit; do not relabel annual reports, meetings, or date matches as validated quarterly events.

- The user now explicitly authorizes bulk BaoStock acquisition after the successful recovery probe. Follow configs/r2/baostock_event_bulk.json: historical 2015/2016 Q1 member unions and audit sentinels, two event methods, serial requests with spacing, no automatic retries, stop on denial. Preserve historical restriction evidence; do not change old financial panels or open protected samples.

- After user takeover, query 100 returned explicit 10001001 (not logged in), with 99 successful queries intact. The repair in configs/r2/baostock_session_recovery.json supersedes the zero-retry rule ONLY for an empty, explicit 10001001 response: archive the failure, fresh login, at most one replay per failed query and 60 refreshes for this finite batch. Never retry 10001011, failed login, unknown transport outcomes or repeated same-query failures. User retains execution; do not restart background collection/finisher without their instruction.

- The subsequent query-368 failure demonstrated an empty 10002007 receive error and Windows denial when hashing the wrapper's live .resume.lock. The updated recovery policy additionally permits bounded replays of the two explicitly read-only event methods for empty 10002007 (at most twice per query, 15/30-second backoff, 20 receive recoveries within the existing 60 overall cap); server receipt may be unknown, but replay is read-only. Keep original failed attempts. Runtime locks are excluded from manifests; unreadable actual evidence must still fail. Offline repair retains old manifests/source bindings and records the first seal of newly collected responses. User still owns execution.

- User completed the finite BaoStock batch: 690/690 successful queries, 1,087 raw rows, two archived failures/recoveries, final archive and canonical scope verified. See docs/results/r2_baostock_event_bulk/report.md. No further bulk continuation is pending. The 145 forecast and 11 express scope-filtered rows still need original-document numeric/version checks and event-date membership alignment before factor admission. Preserve current collection evidence; do not automatically launch another download or research campaign.

- R2 primary-event ledger batch v1 is complete as a finite data-quality deliverable, not research admission: 28 events from 30 reviewed documents, two verified local revision references, 180 documents still awaiting content review. See docs/results/r2_event_ledger/report.md. The annual-Q1 extractor was corrected for numeric-cell/year concatenation; keep all old extraction evidence immutable and use the new correction table. Next prioritize the 133 BaoStock rows with existing but unvalidated candidate documents; preserve cancellations, source conflicts and incomplete recall. No event-return campaign is authorized by this data audit alone.
