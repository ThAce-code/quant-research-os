# M3.x engineering delivery and acceptance

Objective: complete the M3.x engineering series, authorized by the user's active
goal. This is the current implementation roadmap; M3_PROTOCOL.md preserves the
original pilot and model-path protocols. M0 and the closed M2 research outcomes
remain frozen. Research automation does not authorize protected-period tuning,
trade execution or a claim that alpha must be found.

| Stage | Deliverable | Required evidence | Current acceptance |
|---|---|---|---|
| M3.0 | Common hypothesis/candidate adapter, source distinctions, cross-batch deduplication, existing kernel invocation and resumable lineage | Real paper migration plus rejected/failed/survivor engineering paths; persisted restart and duplicate checks | Daily-formula path verified: real Alpha34 admission, 12 full fits, 3 portfolios, final NO_GO; cross-registry duplicate rejection and actual attachment recovery verified |
| M3.1 | Budgeted LLM generation and manual/paper imports through one entry | Real configured model request, structured-response validation, exhausted budget/error tests, at least one bounded research batch | Partial: persisted controller and real paper batch verified; real model request pending |
| M3.2 | Research-only feedback/refinement, fixed campaign budget and immutable children | Real multi-round execution and protected-feedback rejection; all failed proposals retained and multiple-testing family tracked across rounds | Partial: finite loop, family freeze and once-only model stage implemented; real LLM multi-round execution pending; adaptive statistics remain exploratory |
| M3.3 | Searchable trajectory memory, parent-linked mutation/crossover, deterministic resume | Restarted run with recorded lineage; retrieval excluding protected outcomes; lineage and duplicate validation | Partial: real screen/model memory and recovery verified; crossover/restart tested with controlled HTTP/evaluator fixtures; real generated children pending |
| M3.4 | AlphaForge and AlphaSAGE external generator adapters | Verified upstream interfaces/revisions; genuine produced asset imported, unsupported DSL rejected explicitly; no substitute algorithm labelled as upstream | Verified bounded native generation/import/replay and common screening: 3 REJECT, 2 unsupported attempts retained; both frozen NO_ENTRY. Not full-paper training/performance reproduction |
| M3.5 | Research auditor drawing on TradingAgents-style opposing analysis | Structured evidence-based review of a completed run; no power to alter admissions, positions or orders | Pending |
| M3.6 | Multi-source data/candidate boundary | Daily formula inputs and existing PIT fundamental panels through one explicit data contract; field availability/identity tests; unknown event/text/microstructure fields fail rather than fabricated | Partial: canonical daily VWAP added and raw/legacy identity verified; unified PIT fundamental contract pending |
| Delivery | Unified CLI, configuration examples, operational documentation and source evidence | Reproducible generation → evaluation → feedback → archive, failure recovery and regression suite; requirement-by-requirement audit | Pending |

## Scope interpretation

Multi-source includes independently authored hypotheses (paper/human/LLM/search)
and adapters for existing daily market and PIT fundamental data. Event, text,
microstructure and alternative datasets require explicit availability contracts;
they are not silently supplied by changing a source tag. No claim of obtaining
all possible datasets follows from completing M3 engineering. Import adapters must
make unsupported capabilities and dependency errors explicit. AlphaForge/AlphaSAGE
acceptance requires genuine upstream output, not a made-up fixture alone.

## Experiment and operational rules

- Freeze each campaign's hypothesis/evaluation/LLM-call/token/round limits before
  execution. Charge attempts before expensive calls; retain failures and prevent
  restart from resetting budgets. No unlimited retries or auto-funding.
- Record all proposals and rejected duplicates. Canonical expression deduplication
  supplements existing immutable factor IDs; it is not full economic independence.
- Feedback optimization is allowed only for explicitly defined new research
  campaigns. Closed M2 and the original two-factor pilot remain immutable.
- Adaptive search uses research feedback only. Adjusted historical screening is
  exploratory; do not report per-round BH as campaign-wide confirmation. Freeze
  selected candidates and their complete testing budget before model admission.
- Qualification and lockbox are inaccessible to generation, memory, evolution and
  review. Outcome GO/NO_GO is owned by numerical code. Reviewer text is advisory.
- No engineering fixture may add a fake passing observation to production research.
- Separate commits by topic and keep CURRENT acceptance below expectations until
  measured. Update PROJECT_CONTEXT.md and public evidence at each completed batch.

## Initial environment evidence

At implementation start the quant Python environment and frozen Qlib/data are
available. No OPENAI/ANTHROPIC/LLM/OLLAMA/DEEPSEEK environment variable names or
Ollama executable were found in this process. A real inference endpoint still
needs discovery/configuration; this does not block local protocol and controller
implementation and is not evidence that LLM generation works.
