# External searcher integration evidence

These official upstream checkouts are pinned locally. Bounded native generation,
export import, numerical replay and common-engine screening have now passed
acceptance; all screened candidates were rejected. See the [run report](results/m3_searchers/report.md).
Dependencies are installed in a separate CPU venv; the original quant environment
was not modified. The earlier inspection findings below remain relevant to
reproduction and do not imply that native default datasets/splits may be used.

| Project | Official repository | Inspected revision | Export interface |
|---|---|---|---|
| AlphaSAGE | [BerkinChen/AlphaSAGE](https://github.com/BerkinChen/AlphaSAGE) | `517467a34909512a92d6e3139df54891957560de` | `train_gfn.py:GFNLogger.save_checkpoint` writes pool JSON through `pool.to_dict()` |
| AlphaForge | [dulyHao/AlphaForge](https://github.com/dulyHao/AlphaForge) | `d0cfc27df23c60f271bc885fd43027b86b787746` | `gan/utils/builder.py` writes CSV exports as well as internal pickle builders |

AlphaSAGE's paper links the first repository directly. AlphaForge's README and
AlphaSAGE's combination instructions identify the second project. The local
copies are `vendor/alphasage` and `vendor/alphaforge` and are excluded from Git.

Important implementation findings:

- Read CSV/JSON expressions as data; do not unpickle arbitrary incoming assets or
  use Python `eval` to parse upstream expressions. Upstream operator semantics
  must be checked individually before translating to the local DSL.
- AlphaForge's documented default train-end 2020 uses 2021 validation and 2022
  testing. Those defaults cannot run in the current research campaign. A bounded
  upstream execution must explicitly confine every split and logging evaluation
  to research history and use the existing local provider.
- AlphaSAGE's `GFNLogger` evaluates test data while logging. Restricting training
  dates alone is insufficient; its test_data must also satisfy the research scope.
- AlphaSAGE's pyproject pins Linux CUDA 12.1 wheels despite this Windows host.
  An isolated compatible environment or an explicitly verified equivalent runtime
  is required. This is a discovered dependency issue, not completed integration.

The accepted evidence now includes actual native CSV/JSON assets, source hashes,
data/time contracts, exact execution driver, controlled and canonical numerical
replay, ledger imports and independent screen verification. AlphaSAGE generated
five pool expressions in 64 episodes; AlphaForge generated two post-training
expressions in one bounded native predictor/generator round. This verifies
integration, not the full training budget, alpha zoo, portfolio construction or
returns reported in either paper.

The runtime is `data/m3_search_env/Scripts/python.exe`, created from the existing
quant Python 3.12 environment with `venv --system-site-packages`. Its local overlay
includes torch 2.4.1+cpu, torchgfn 1.2.1, torch-geometric 2.6.1,
stable-baselines3/sb3-contrib 2.7.0 and tensorboard 2.20.0. Exact overlay versions
are in `docs/results/m3_searchers/runtime_overlay.txt`. Native warnings are kept
in logs, not suppressed or presented as a successful model improvement.
