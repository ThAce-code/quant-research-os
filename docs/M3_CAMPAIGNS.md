# Persistent M3 research campaigns

The campaign ledger records attempts and budgets; the existing factor registries
record numerical research results. A proposal marked ACCEPTED is valid input for
calculation, not a successful alpha. Candidate metadata and campaign budgets are
immutable. Invalid and duplicate proposals consume proposal slots. Failed or
uncertain model calls retain their call and reserved output-token charge.

Use the `quant` Python environment from the repository root:

```powershell
python scripts/m3.py create configs/m3/campaign_paper34.json
python scripts/m3.py import m3_paper34_v1 configs/m3/paper34.json --source-type PAPER_RECONSTRUCTED
python scripts/m3.py status m3_paper34_v1
python scripts/m3.py evaluate m3_paper34_v1 PROPOSAL_ID
python scripts/m3.py memory m3_paper34_v1 --query volatility
```

`PROPOSAL_ID` is the integer printed by import, not a fixed example identifier.
Recreating the same campaign checks its original specification without resetting
budgets. Existing M1/M3 and M2 definitions seed expression deduplication. Legacy M2
descriptive formulas that are not executable DSL are reported as unsupported;
this is not a claim of exhaustive economic or algebraic deduplication.

The fixed Alpha34 campaign selects one published formula before evaluation for
its supported daily fields and operators. Its source is [101 Formulaic Alphas,
Appendix A, Alpha#34](https://arxiv.org/pdf/1601.00991v3), page 10. The two previous
pilot factors stay rejected; they are not changed or reevaluated. Formula, sign,
windows, reconstruction differences and interpretation are in `paper34.json`.
This study has no LLM calls or adaptive rounds. A separate zero-evaluation
`campaign_dedup_check.json` exercises the old pilot's duplicate rejection only.

## Generation and refinement

For a newly frozen campaign with positive call/token/round budgets, configure an
actual model and run `generate CAMPAIGN ENDPOINT_JSON BRIEF_FILE`. The endpoint
example is a template, not evidence of an installed service. Supported protocols
are Ollama `/api/chat` and a compatible `/v1/chat/completions` endpoint. Remote
endpoints require HTTPS. Credentials are read only from the named environment
variable; do not put a key in a configuration or source URL.

`refine CAMPAIGN ENDPOINT_JSON BRIEF_FILE PARENT_ID [PARENT_ID]` creates a mutation
or crossover in the next round. All parents must have completed research results
in the same campaign. Their expressions and exact ledger feedback are passed to
the model; rejected parents are preserved. Refinement cannot reset budgets.
`memory` uses deterministic lexical matching, keeps negative outcomes, and does
not rank records by profit. Only completed, in-period research records enter it.

`loop CAMPAIGN ENDPOINT_JSON BRIEF_FILE` runs the bounded generation/screen/refine
cycle. Its model endpoint, brief, schema and deterministic parent-selection policy
are bound on first invocation. In each later round it chooses at most the first
two evaluated proposals from the preceding round, by ID. It does not rank parents
by profit. Completed model responses are replayed without new requests. A reserved
or failed execution stops the loop for evidence-based recovery, without retries.
The loop has passed both controlled failure tests and a real three-round local-model
campaign with six evaluated candidates and a full survivor model NO_GO.

All adaptive feedback is exploratory. A per-batch BH q-value is not correction
for an entire adaptive campaign and is not independent confirmation. A selected
model's q-value also does not erase prior adaptive selection. No automatic
protected-period promotion follows from these historical outcomes.

## Freeze and model stage

New campaigns may set `max_model_runs: 1` before any work. The default is zero;
old stored specifications retain that default and cannot acquire extra budget by
reopening them with a changed configuration. One model run means one frozen
selection of up to three candidates, with the existing maximum 24 fits and seven
matched portfolios. A terminal failure still consumes the reservation.

```powershell
python scripts/m3.py freeze CAMPAIGN PROPOSAL_ID [PROPOSAL_ID ...]
python scripts/m3.py model CAMPAIGN
```

Freeze rechecks numerical screening admission and saves all proposal attempts,
evaluations, failed calls, original budgets, loop policy and protocol hashes.
Outstanding or unmaterialized calls must be resolved first. Freeze ends
generation and screening; selected definitions and protocols cannot change.
An empty selection follows NO_ENTRY with no model execution. Candidates from
different rounds can enter the same matched-model run; each retains its own
verified screen lineage, and colliding factor names are rejected before loading
market data. Failed model runs cannot be silently restarted.

`attach-model CAMPAIGN RUN_DIRECTORY PROPOSAL_ID ...` recovers a completed model
run after attachment failure. Artifacts and numerical registry results must match
the exact frozen selection and protocols. Model-stage outcomes are immutable and
appear in memory alongside their original screen outcomes. `latest_decision`
therefore exposes a later model NO_GO even when the screen was FORWARD.

For a model run already executed under the earlier standalone protocol,
`attach-model ... --legacy` only imports its verified evidence. It grants no new
model budget and labels its origin LEGACY_VERIFIED_IMPORT, rather than pretending
that the earlier execution used the new controller reservation. Alpha34 uses this
explicit migration path; its original protocol and negative result stay fixed.

## Recovery

- `recover-call CAMPAIGN TICKET` imports the saved completed response atomically.
  Replaying it returns the original proposals and performs no HTTP request.
- An uncertain RESERVED call is not automatically retried or refunded. Inspect
  the provider outcome; unknown outcome remains unknown.
- Evaluation freezes the exact input before atomically reserving all selected
  proposals. An input file without reservations indicates execution was not
  admitted. Reserved evaluations are never silently rerun.
- `attach-screen CAMPAIGN SCREEN_DIRECTORY PROPOSAL_ID ...` attaches an already
  completed run after a controller interruption. Batch and protocol must match
  the frozen input; reports must match the numerical registry and artifact hashes.
  Identical attachment is replayable; replacing an outcome is forbidden.
- Failed numerical runs and their reservations remain visible. Investigate them
  before designing a new attempt; a restart is not a new budget.

Real runtime evidence and preserved invalid-only attempts are in
[the local-model report](results/m3_local_llm/report.md). Protocol-server fixtures
remain labelled separately from those actual inference and numerical runs.

## External search exports

`import-search CAMPAIGN SOURCE ASSET MANIFEST ANNOTATIONS --round 0` accepts
`alphasage` native pool JSON or `alphaforge` expression CSV. The manifest pins
revision, asset SHA256, all generation/feedback periods and protected-access
declaration. Annotations select at most three exact zero-based rows and fix their
hypotheses, economic interpretations and directions. Examples are
`configs/m3/alphasage_annotations_v1.json` and `alphaforge_annotations_v1.json`.

The importer does not use exported rewards or weights to set local signs or
promote candidates. Unsupported formulas become budgeted INVALID proposals;
accepted formulas enter the same `evaluate → freeze → model` flow. Repeat import
is another attempted proposal subject to deduplication/budget, not a resume call.
The two published campaigns are already frozen; do not repeat their evaluations.

Use the separate search venv for `scripts/run_m3_searcher.py`, which executes
pinned upstream networks and optimizers on bounded canonical tensors. Use the
quant Python environment for common CLI imports and numerical screening. Native
training/search outcomes and local admission outcomes are distinct; both are
retained in [the integration report](results/m3_searchers/report.md).

## Daily and PIT inputs

New evaluations bind `configs/m3/data_contract_v1.json` before reserving work.
The screen and survivor model stages verify that same contract; different input
contracts cannot be silently pooled across screens. Existing daily-only batches
without a contract remain legacy-compatible. A PIT expression without a frozen
contract fails before market loading. See [field definitions and limits](M3_DATA_CONTRACT.md).

## Local structured model endpoint

`endpoint_local_gemma.json` uses ordinary JSON-mode chat completions;
`endpoint_local_gemma_schema.json` explicitly requests schema-constrained chat
completions from a supporting server. The schema is saved with each call request.
It constrains required metadata and lowercase field keys, while local AST and
field-map validation still decide whether a proposal is calculable. Server JSON
success never bypasses those checks. Unsupported providers fail as recorded
attempts instead of silently falling back to another protocol.


New generated requests freeze an authoritative calculation catalog. The adapter
extracts fields/operators from the validated DSL and fills their exact metadata;
it preserves raw model declarations, formula and direction. Model rationale is
still unverified. Earlier calls without that policy retain their old metadata.

`audit CAMPAIGN ENDPOINT.json` performs two budgeted opposing advisory reviews of
a completed frozen campaign. Numerical databases are read-only, evidence IDs are
validated and failed/uncertain attempts stop without retries. A pair of model roles
is not independent numerical validation. `abort CAMPAIGN --reason TEXT` explicitly
closes an unrecoverable open/overrun search after its worker stops, preserving all
raw responses and reservations, including a response that cannot fit remaining
proposal slots. It is not a successful numerical freeze. See [operations](M3_OPERATIONS.md).
