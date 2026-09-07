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

All adaptive feedback is exploratory. A per-batch BH q-value is not correction
for an entire adaptive campaign and is not independent confirmation. The current
campaign CLI stops at historical screening; it does not automatically promote
adaptive search output into the rolling model or protected periods. Campaign-wide
freeze and model-admission integration remain part of the full M3.x delivery.

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

Runtime acceptance of real LLM generation and a multi-round loop remains pending.
Protocol-server fixtures verify HTTP serialization and error handling only.
