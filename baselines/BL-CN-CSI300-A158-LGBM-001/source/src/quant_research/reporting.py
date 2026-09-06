"""Human-readable evidence from saved experiment results; no invented results."""
from pathlib import Path
import pandas as pd


def write_report(output, metrics, manifest, segments):
    output = Path(output)
    s, p = metrics['signal'], metrics['portfolio']
    original = {'IC': 0.04745450901971543, 'ICIR': 0.3965188710163858,
                'Rank IC': 0.04963418198968678, 'Rank ICIR': 0.42303017301171414}
    lines = ['# BaoStock 第一个实验复现报告', '',
             '已完成真实 BaoStock 数据 → Canonical Parquet → Qlib → Alpha158 → LightGBM → 信号分析 → Top50/drop5 含成本回测。', '',
             'PASS 表示链路和输出验收通过，不代表达到原demo收益，也不代表实盘策略验收。', '',
             '## 信号结果', '', '| 指标 | 本次 BaoStock | 原对话 Qlib demo |', '|---|---:|---:|']
    lines += [f'| {key} | {s[key]:.6f} | {original[key]:.6f} |' for key in original]
    lines += ['', '## 组合结果', '', '| 指标 | 本次 | 原对话 demo |', '|---|---:|---:|',
              f"| 沪深300基准年化 | {p['benchmark']['annualized_return']:.2%} | 11.36% |",
              f"| 毛超额年化 | {p['excess_gross']['annualized_return']:.2%} | 14.08% |",
              f"| 含成本超额年化 | {p['excess_net']['annualized_return']:.2%} | 9.56% |",
              f"| 含成本超额 IR | {p['excess_net']['information_ratio']:.4f} | 1.1148 |",
              f"| 含成本超额最大回撤 | {p['excess_net']['max_drawdown']:.2%} | -9.55% |",
              f"| 年化交易成本拖累 | {metrics['annualized_cost_drag']:.2%} | 约4.52% |",
              f"| 平均每日双边换手率（Qlib turnover） | {metrics['mean_daily_turnover']:.2%} | 未提供 |",
              '', '上述年化和超额回撤沿用当前 Qlib 的 **238日、算术累计** 定义，不是 CAGR，也不是净值最大回撤。',
              f"另算策略含成本复利年化（238日）为 {p['strategy_net_compound']['annualized_return']:.2%}，净值最大回撤为 {p['strategy_net_compound']['max_drawdown']:.2%}。",
              '', '## 数据与训练', '',
              f"- 历史成分覆盖 {manifest['membership_days']} 个交易日，历史并集 {manifest['instruments']} 只股票，另含沪深300指数。",
              f"- 原始股票/指数行情共 {sum(b['rows'] for b in manifest['bars']):,} 行；每个接口响应保留请求参数、获取时间和 SHA256。",
              f"- 测试期 {metrics['test_days']} 个交易日，预测 {metrics['prediction_rows']:,} 行；LightGBM 最佳迭代 {metrics['best_iteration']} 轮。",
              '- 训练2008–2014，验证2015–2016，测试2017-01-01至2020-07-31。行情预热至2007年9月，尾部延伸至2020-08-05用于标签。',
              '- 标签为 close[t+2]/close[t+1]-1；训练/验证末尾各剔除2个交易日，避免标签跨集合。随机种子42，固定线程和确定性训练。',
              '- 保留原始未复权价格和后复权因子；Qlib价格/成交量反向归一化，保留成交额恒等式。停牌或无量记录不可成交。',
              '- 按每只股票实际成分区间下载行情，保留60个交易日预热及2日标签尾部；测试期曾入选的股票保留至全局数据末日，支持退出成分后的持仓处理。已缓存的完整历史照常复用。',
              '', '## 比较边界', '',
              '- demo指标来自用户引用的历史对话，并非本次重跑官方数据。数据供应商、成分覆盖、停牌处理、训练末端清理和随机种子不同，不能把结果差异全部归因于数据质量。',
              '- BaoStock历史成分是本次下载时数据库中的历史快照；逐交易日查询且拒绝未来updateDate，但不证明数据从未事后修订。',
              '- 保持demo统一9.5%限制及固定费率，以便比较；尚未逐板块/ST/IPO细化交易规则，没有冲击成本或成交容量模型。',
              '- Qlib股票退市或长期缺价的持仓处理不是完整的退市清算模型；缺失价格保留为不可交易，而不杜撰成交。',
              '', '## 产物', '',
              '- `metrics.json`：指标；`effective_config.json`：实际配置与数据分割。',
              '- `predictions.parquet` / `labels.parquet`：可独立核算信号的预测和真实标签。',
              '- `daily_ic.csv` / `annual_ic.csv`：日度和分年信号；`daily_backtest.csv`：收益、基准、成本、换手。',
              '- `model.txt`：LightGBM模型；`provenance.json`：版本与代码/数据校验和。',
              f"- MLflow experiment `{metrics['experiment_id']}`，recorder `{metrics['recorder_id']}`。", '',
              '数据字段和复权依据：[BaoStock复权因子简介](https://www.baostock.com/helpdocs/pdf/BaoStock%E5%A4%8D%E6%9D%83%E5%9B%A0%E5%AD%90%E7%AE%80%E4%BB%8B.pdf)。',
              '实验来源：[A股量化论文](chatgpt-conversation://6a95a920-96f0-83e8-bf97-ec53ae940952)。', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    report = pd.read_csv(output / 'daily_backtest.csv', index_col=0, parse_dates=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(report.index, (1 + report['return'] - report.cost).cumprod(), label='Strategy after costs')
    axes[0].plot(report.index, (1 + report.bench).cumprod(), label='CSI300')
    axes[0].set_ylabel('Compounded NAV')
    axes[0].legend()
    axes[1].plot(report.index, (report['return'] - report.bench).cumsum(), label='Gross excess')
    axes[1].plot(report.index, (report['return'] - report.bench - report.cost).cumsum(), label='Net excess')
    axes[1].set_ylabel('Arithmetic cumulative excess')
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=.2)
    fig.suptitle('BaoStock / CSI300 / Alpha158 + LightGBM / Top50 drop5')
    fig.tight_layout()
    fig.savefig(output / 'performance.png', dpi=160)
    plt.close(fig)
