# M3.0 deterministic paper admission — 2026-09-06

User authorization: proceed according to the latest web GPT correction. This
supersedes the previous no-M3 scope statement, not the frozen M2 decisions.

## Architecture and source audit

Primary reference: [R&D-Agent-Quant v2](https://arxiv.org/abs/2505.15155v2),
specification → synthesis → implementation → validation → analysis. Reviewed
[official proposal interfaces](https://github.com/microsoft/RD-Agent/blob/main/rdagent/core/proposal.py).
Here a validated ResearchHypothesis becomes the existing FactorDefinition;
existing M1/M2 functions own execution and numerical judgments. This is a local
adapter inspired by that boundary, not an installation or reproduction of RD-Agent.
AlphaAgent informs explicit hypothesis/formula correspondence and bounded ASTs.
Current deduplication is normalized AST equality within a batch, not a claim of
semantic similarity, algebraic equivalence, or economic independence.

The first asset is [101 Formulaic Alphas v3](https://arxiv.org/abs/1601.00991v3):
Section 2 equation (3), PDF page 4; Appendix A Alpha#101, page 15, with direction
and delay-1 discussion on page 4. Both have explicit formula, operators, fields,
positive direction and timing, require only public OHLC, and fit the unchanged DSL.
They were selected for specification clarity before seeing project results.
The original proprietary performance dataset is not needed to calculate them.

Formula expressions are preserved under signal-date relabeling. The study is
PAPER_RECONSTRUCTED: CSI300, canonical adjusted prices, execution at next close,
five-day labels and industry/size neutralization differ from original evaluation.
Alpha#101 retains literal 0.001 in canonical adjusted-price units. Do not claim
original performance reproduction or equate that epsilon across price conventions.
No formula, direction, threshold, window or candidate addition may change on feedback.

## Frozen first batch and decision tree

`configs/m3/paper_pilot.json` is authoritative, two primary hypotheses, each with
one industry/size-neutralized variant. Original expressions, locators, fields,
operators, timing, rationale, direction evidence and deviations are mandatory.
Source types: PAPER_EXACT, PAPER_RECONSTRUCTED, PAPER_INSPIRED, LLM_GENERATED,
HUMAN_GENERATED. PAPER_EXACT cannot carry undeclared reconstruction differences.
No LLM generation or automatic refinement runs in M3.0.

Reuse the numerical screen from `m2_family_screen.json` (hash pinned in batch):
2015–2016 already-observed history; five-day labels, min 30 pairs, coverage >=70%
in each year, mean RankIC >=0.01, positive RankIC each year, block length 20,
2,000 resamples, seed 42, BH q <=0.10 across exactly these TWO new primary tests.
Previous M2 candidates are not retested or pooled into this separate test budget.
2016 technical conditional diagnostics reuse the exact 2015-fitted 20-PC basis;
77.7% retained variance does not cover all Alpha158 information.

REJECT terminates a candidate's admission; matched-cost and rolling-model stages
are explicitly NOT_RUN_SCREEN_REJECT. FORWARD means only IC_SCREEN_PASS and leaves
cost/model stages PENDING_PROTOCOL; this first adapter does not yet automate those
survivor stages. It must never generate KEEP or claim independent alpha.
This is an explicit M3.0 screening-adapter boundary, not completion of all M3.

## Firewall and acceptance

Research uses the frozen M0 canonical snapshot, verifies its data identity and
source artifacts, rejects 2021+ configuration before observations are loaded.
Qualification and lockbox remain sealed; no protected outcomes enter feedback.
The pilot predates/overlaps paper publication and already observed project history,
so results are integration/historical evidence, never fresh prospective OOS.

Acceptance: validated hypothesis → unchanged DSL → M2 numerical screen and
conditional diagnostic → decision → existing append-only registry, with source,
batch and data hashes and report links. Invalid inputs fail before market loading;
execution errors retain failed run records. Raw data and panels stay local.
Published evidence includes result JSON, lineage and a compact report.

## Subsequent batches

M3.1 bounded AlphaAgent-style candidate generation; M3.2 research-only feedback
refinement; M3.3 trajectory memory/evolution; later AlphaForge/AlphaSAGE generators
and TradingAgents review. Define budgets and provenance before each new batch.
Complete survivor cost/model integration before using generation at scale.

## Follow-on implementation: survivor routing

The original first-run snapshot above remains immutable. The subsequent adapter
implements the previously pending survivor interface in `m3/increment.py`, with
`configs/m3/increment.json` pinning the M2 numerical protocol and the original
full-history feature/control cache. It recomputes the initial screen decision and
matches it to the append-only registry before admitting any candidate. A rejected
batch exits NO_ENTRY before reading market data or training models.

Each surviving candidate is added separately to Alpha158; BASE and all ADD models
share the intersection of available neutralized candidate observations in historical
nonfinancial CSI300. Original failed BP/CASHFLOW observations do not constrain this
intersection. Numerical training settings, annual folds, purge, fees and GO thresholds
remain as in M2; BH covers only the predeclared surviving ADD comparisons. Maximum
three survivors means 24 fits and seven continuous portfolios. No combined-factor
search. Removing the single added candidate gives the identical BASE comparison;
fixed 75/25 rank blends are costed diagnostics only, never selected by their returns.

These model labels are one-day M0 returns, distinct from five-day initial screening.
Model-period nonfinancial universe is explicitly different from initial screening;
all model arms use the same sample. Historical GO still means FORWARD pending separate
qualification admission, not KEEP. This command never opens qualification/lockbox.

Run `python scripts/run_m3.py` for screen plus conditional routing, or
`python scripts/run_m3.py --resume-screen experiments/m3/<run_id>` to resume without
repeating candidate tests. `--screen-only` preserves the standalone screening entry.

Verification of this interface includes a small real LightGBM BASE/ADD fit and
sample/purge tests. The actual first paper batch produces NO_ENTRY; the complete
survivor model/backtest branch has not yet been exercised on a genuine admitted
candidate. Keep this runtime limitation distinct from implemented interfaces.
