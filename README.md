# Quant Research OS

A股量化研究项目：BaoStock数据、Qlib基线、单因子引擎与M2价值因子探索。

**给Web端GPT的阅读入口：[项目研究上下文](docs/PROJECT_CONTEXT.md)。** 公开报告和验收摘要见 [docs/results](docs/results)，运行环境及数据恢复限制见 [环境说明](docs/environment.md)。

## M0：第一个 BaoStock 实验

复刻《A股量化论文》中已完成的 Qlib smoke test：历史 CSI300 → Alpha158 → LightGBM → IC/Rank IC → Top50/drop5 含成本回测。使用真实 BaoStock 数据。

已完成运行 `20260902T145556871363Z`：测试期871个交易日，IC 0.04943、Rank IC 0.05182、含成本超额年化9.82%、超额IR 1.1676。年化沿用Qlib的238日算术口径。[完整报告](docs/results/m0/report.md)包含数据缺口与比较限制；[独立验收](docs/results/m0/final_verification.json)记录指标重算和覆盖检查。18项测试通过。

在项目目录执行（自动使用现有 `quant` Conda 环境）：

```powershell
.\run-baseline.ps1
```

首次会下载约13年的历史成分、行情和复权因子。原始响应按请求内容缓存并记录SHA256，可中断后用相同命令继续。下载全部完成后仅重跑模型：

```powershell
.\run-baseline.ps1 -SkipDownload
```

本地下载采用单会话锁；同一时间只运行一个 BaoStock 数据准备任务，避免服务端登录互相干扰。完成下载后会从原始响应逐文件重建并核对规范行情，封存所有 Parquet 校验和；复跑若发现配置或数据变化会停止。

行情请求限制单次读取60秒、整个响应90秒，网络/会话错误最多重试3次；耗尽后保留缓存并明确失败。完整源数据错误不会被替换为空结果。

也可在已激活的 `quant` 环境运行 `python scripts/run_baseline.py`。测试：`python -m pytest tests -q`。

产物在 `experiments/baostock_alpha158_csi300_2008_2020/<UTC run id>/`；`latest.json` 只指向成功的实验。查看 `report.md`、`performance.png` 和 `metrics.json`。每次运行有独立 `status.json`，失败写明实际阶段与错误。

实验配置：`configs/experiments/baostock_alpha158.json`。原始响应：`data/raw/baostock/`；规范行情：`data/canonical/`；本实验独立Qlib行情：`data/qlib/`；MLflow：`experiments/mlruns/`。不覆盖 `~/.qlib` demo行情或修改vendor源码。

实验对齐2008–2014训练、2015–2016验证、2017–2020年7月测试。末端标签清理、复权/量价口径、历史成分限制及统一涨跌停近似见实验报告和 `docs/superpowers/specs/2026-09-02-baostock-baseline-design.md`。这是数据及研究管线基线，不是对某篇因子论文全部实验的复现。

## M1：Factor Research Engine

已完成真实数据运行 `20260903T064735970067Z`：[M1汇总报告](docs/results/m1/report.md)。8个因子中5个REJECT、3个FORWARD、0个KEEP；FORWARD的测试期含成本超额收益均为负，仍缺行业/市值与已有池核验。122项测试和[独立产物验收](docs/results/m1/final_verification.json)通过。Windows环境采用单进程Qlib数据读取。

M0已固定为 `BL-CN-CSI300-A158-LGBM-001`，源码快照及产物SHA256在 `baselines/`。M1使用同一封存数据，运行前后验证M0未改变。

```powershell
.\run-factors.ps1                 # 八个预设因子
.\run-factors.ps1 -Factor MOM_20  # 单因子
```

无需重新下载数据。配置位于 `configs/factors/m1.json`；完整报告、图表和日度CSV写入 `experiments/factor_engine/m1_factor_engine_v1/<run_id>/`，`latest.json`只指向成功批次。因子定义、拒绝原因、执行失败和历史试验保存在 `data/factor_registry.sqlite`。

Python接口（`PYTHONPATH=src`）：

```python
from quant_research.factors.engine import evaluate_factor
from quant_research.factors.expressions import FactorDefinition

report = evaluate_factor("MOM_20", universe="csi300", horizon=5)
candidate = FactorDefinition(
    name="MOM_10", family="momentum", expression="close / Ref(close,10) - 1",
    hypothesis="十日趋势具有延续性", direction=1,
)
report = evaluate_factor(candidate)
print(report.status, report.artifact_directory)
```

因子表达式支持算术、Ref/Delta、Mean/Std/Min/Max、Rank/TsRank、Abs/Log；正数Ref表示过去，负数未来引用被拒绝。窗口要求完整观测；信号在收盘后可用，最早下一交易日收盘执行。`TURNOVER_CHANGE_20`明确取5日/20日平均换手率之比减1。修改同名因子的定义必须递增version。

每份FactorReport包含IC/RankIC/ICIR、1/2/5/10/20日标签衰减、分年/市场状态稳定性、波动/换手暴露、因子相关性，以及Qlib Top30/60含成本组合。多空仅作假想横截面标签差，未模拟融券。行业和市值缺少历史时点数据时为null；通过验证集收益门槛的因子仍需完成缺失检查，状态为FORWARD。所有筛选仅依据验证集，测试集用于诊断。

复用测试命令 `python -m pytest tests -q`。设计和口径详见 `docs/superpowers/specs/2026-09-03-factor-engine-design.md`。Alpha158解剖、基本面、中性化、聚类和边际贡献属于M2。

## M2：本轮研究已收束，结论NO_GO

完整Alpha158地图、有限因子族研究、条件诊断和滚动模型增量研究已完成；没有候选通过联合准入，没有确认独立Alpha。24次滚动拟合和6组连续含成本组合的结论为NO_GO。

原726只历史CSI300股票的财务范围已通过来源明确的BaoStock完整历史与东方财富补充交付，五字段面板完成原始源独立重放。替代源存在财务修订，采用保守可用时间并保留缺失；这不是完整历史版本PIT或全市场研究。

2021–2023资格和2024–2025锁箱按事前条件保持未打开：没有执行、没有通过。原BaoStock限制未确认解除，缺失响应没有被伪造为成功。

- [唯一当前状态](docs/PROJECT_CONTEXT.md)
- [逐项完成审计](docs/M2_COMPLETION_AUDIT.json)
- [模型结果](docs/results/m2_rolling/report.md)
- [完整范围数据与覆盖](docs/results/m2_alternate_history/report.md)
- [替代源口径修正](docs/M2_ALTERNATE_SOURCE_AUDIT.md)
- [研究收束路线](docs/M2_ROADMAP.md)

旧结果全部保留，历史FORWARD不代表当前准入。原始数据、完整面板、模型和SQLite留在本地。
