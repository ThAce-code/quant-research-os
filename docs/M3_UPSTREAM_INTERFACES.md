# External searcher integration evidence

These official upstream checkouts have been inspected and pinned locally. No
generator training or output import has yet passed acceptance. Their libraries
are not installed into the frozen quant environment merely by cloning them.

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

Next acceptance evidence must include an actual upstream-produced expression
asset, pinned source identity, declared generation data/time scope, translator
semantics and a unified candidate import. A handcrafted pool JSON alone is not
that evidence.
