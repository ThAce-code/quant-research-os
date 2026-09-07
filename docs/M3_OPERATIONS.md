# Running the delivered M3 research workflow

M3 is a bounded research system with a common numerical evaluator. Completed
campaigns are immutable evidence. Start a **new, explicitly defined** campaign for
a new question; changing a failed campaign ID is not independent confirmation.
The engineering acceptance is summarized in `M3_COMPLETION_AUDIT.json`.

## Environment and local model

Run the CLI in the repository root with the existing `quant` Python environment.
For an already installed llama.cpp and GGUF model, the Windows helper provides
owned-process lifecycle control and a real no-research inference probe:

```powershell
./scripts/m3_local_model.ps1 -Action Start -ServerPath 'PATH_TO_LLAMA_SERVER.exe' -ModelPath 'PATH_TO_GGUF.gguf'
./scripts/m3_local_model.ps1 -Action Status
./scripts/m3_local_model.ps1 -Action Stop
```

The placeholders are local files, not download URLs. The verified configuration
is Gemma-4-E4B-it Q4_0 with llama.cpp build 10282, context 8192, loopback port 18341
and the `m3-gemma4-e4b` alias. Other builds/weights require their own probe; a model
alias alone is not a weight identity. The helper retains logs and ownership under
`data/m3_local_llm`, checks executable/start time before stopping a process, and
refuses to replace an occupied port. Stop the service after research to release GPU
memory. No automatic server or model install is performed.

`configs/m3/endpoint_local_gemma_schema.json` uses this schema-constrained endpoint.
Other providers may use the explicit Ollama or chat-completions configurations;
there is no silent protocol fallback. Credentials, when needed, come from a named
environment variable and are never written into public configurations.

## One new research campaign

1. Define a new economic question and fixed period/proposal/evaluation/call/token/
   round/model budgets in a new campaign JSON. The existing V4 JSON is an example
   of a completed finite campaign, not permission to reset its budget.
2. `python scripts/m3.py create NEW_SPEC.json` freezes the specification and seeds
   cross-registry expression deduplication.
3. Import a reviewed paper/human hypothesis with `import`, a pinned upstream export
   with `import-search`, or run `loop CAMPAIGN ENDPOINT.json BRIEF.txt`. Manual
   `generate`, `evaluate`, `memory` and `refine` remain available.
4. Apply the campaign's predeclared final-selection rule. `freeze CAMPAIGN [IDS]`
   preserves the entire search family and rechecks numerical admission. An empty
   list records no admission. `model CAMPAIGN` executes at most the once-budgeted
   rolling model stage for a nonempty selection.
5. `audit CAMPAIGN ENDPOINT.json` reviews completed frozen evidence from two roles.
   It has two separately recorded inference attempts, opens research databases
   read-only and cannot advance the numerical gate or access protected samples.
6. Archive small configurations/results/lineage and update `PROJECT_CONTEXT.md`.
   Keep market panels, weights, SQLite, credentials and full models local.

For this delivery, new LLM calls derive calculation metadata from the frozen DSL
catalog. Review the **economic rationale** separately: a calculable equation can
still embody a weak or mismatched mechanism. Missing financial data stay missing;
cross-field fiscal-period matching is not silently supplied. See
`M3_DATA_CONTRACT.md` and `M3_CAMPAIGNS.md` for exact data and controller boundaries.

## Recovery and terminal failures

Restart `loop` with the same bound inputs: completed work is replayed without new
inference/evaluation. Use `recover-call`, `attach-screen` or `attach-model` to attach
known completed evidence after an interruption. An uncertain call is never
automatically retried, and saved raw model output never authorizes arbitrary code.

When a search cannot be recovered, first stop its external worker, then run:

```powershell
python scripts/m3.py abort CAMPAIGN --reason 'Worker stopped; exact unresolved condition and evidence location.'
```

This terminal closure retains reservations/raw responses and refunds nothing.
It cannot be presented as a successful freeze or numerical NO_ENTRY. A model run
already frozen uses its failed/reserved record and attachment recovery, not abort.
Auditor failures likewise retain their two-call ceiling and stop on restart;
same-ID retry cannot reset the budget. A separate review ID is a new review budget,
not a correction of the old outcome.

## Verification and limits

Run `python -m pytest tests -q` for the required regression gate. Existing scripts
verify PIT/VWAP transfer, native search exports, fixed screen formulas and complete
survivor model evidence. Public evidence is indexed by `docs/results/sources.json`.
The real generated formulas have a direct replay script in their result folder.

The delivered adapters draw on RD-Agent-style hypotheses, AlphaForge/AlphaSAGE
native search and TradingAgents-style opposing reviews. They do not deploy every
feature of those upstream systems or reproduce their published returns. Review
text is advisory and may be shallow or wrong. Adaptive historical q-values do not
establish campaign-wide confirmation. New event/text/microstructure data, full
financial vintages, protected-period protocols and trading are future separately
defined research/data work. No automatic 2021–2025 access or trade execution exists.
