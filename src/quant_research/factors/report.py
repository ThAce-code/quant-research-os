"""Chinese research artifacts generated entirely from saved evaluation outputs."""
from pathlib import Path

import numpy as np
import pandas as pd


def fmt(value, percent=False):
    if value is None or not np.isfinite(value): return '缺失'
    return f'{value:.2%}' if percent else f'{value:.4f}'


def write_factor_report(directory, report):
    directory=Path(directory)
    factor, splits = report['factor'], report['splits']
    lines=[f"# {factor['name']} / M1 因子报告",'',
           f"研究状态：**{report['status']}**。依据：`{', '.join(report['reasons'])}`。",'',
           f"表达式：`{factor['expression']}`；预先固定方向：{factor['direction']:+d}；族：{factor['family']}。",
           f"假设：{factor['hypothesis']}。",'',
           '正向分数代表更看好。方向在运行前指定，未根据验证或测试结果翻转。', '',
           '## 预测能力与覆盖', '',
           '| 样本 | IC | ICIR | RankIC | RankICIR | RankIC为正比例 | 因子覆盖 | 有效IC天数 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,s in splits.items():
        p=s['primary']
        lines.append(f"| {name} | {fmt(p['ic'])} | {fmt(p['icir'])} | {fmt(p['rank_ic'])} | {fmt(p['rank_icir'])} | {fmt(p['positive_rank_ic_ratio'],True)} | {fmt(s['coverage'],True)} | {p['days']} |")
    h=report['config']['horizon']
    lines += ['',f'主标签为{h}个交易日持有期：close[t+1+{h}]/close[t+1]-1。ICIR未年化；IC为各交易日横截面相关性的平均值。',
              '覆盖率为可用因子股票日数/历史成分股票日数。停牌、预热不足和缺价不填充。标签进出端点排除停牌及按本次9.5%限制不能成交的日期；涨跌停日的可观测因子分数仍保留。各持有期按对应集合结束日剔除越界标签，因此长周期有效样本更少。',
              '', '## 衰减（测试集）', '', '| 持有期 | IC | RankIC | ICIR | 天数 | 最后可用信号日 |', '|---|---:|---:|---:|---:|---|']
    for horizon,s in splits['test']['decay'].items():
        lines.append(f"| {horizon}日 | {fmt(s['ic'])} | {fmt(s['rank_ic'])} | {fmt(s['icir'])} | {s['days']} | {s['last_usable_signal_date']} |")
    lines += ['', '这里是不同持有期的预测表现，不是改变因子滞后后的半衰期估计。', '',
              '## 稳定性（测试集）', '', '| 分组 | RankIC | RankICIR | 有效天数 |', '|---|---:|---:|---:|']
    for group in ['stability_year','stability_regime']:
        for key,s in splits['test'][group].items():
            lines.append(f"| {key} | {fmt(s['rank_ic'])} | {fmt(s['rank_icir'])} | {s['days']} |")
    lines += ['', '市场状态使用信号日已知的沪深300过去60日涨跌幅：>5%为bull、<-5%为bear，其余为sideways。多日标签重叠，未把这些观察当作独立样本做显著性或多重检验结论。',
              '', '## 暴露与独立性（验证集）', '', '| 暴露 | 日均秩相关 | 状态 |', '|---|---:|---|']
    for name,v in splits['valid']['exposure'].items():
        lines.append(f"| {name} | {fmt(v['value'])} | {v['status']} |")
    lines += ['', 'size/industry缺少封存的历史时点数据，未使用当前行业或市值替代。volatility对应20日收益波动，turnover对应20日平均换手率。',
              f"候选批次最大绝对相关：{fmt(splits['valid']['corr_max'])}；已有KEEP池最大绝对相关：{fmt(splits['valid']['corr_existing_pool'])}。均为验证期每日横截面Spearman相关的均值。空池记缺失。",'',
              '## 组合测试', '', '| 样本/组合 | 毛累计收益 | 净累计收益 | 净复利年化 | 净值最大回撤 | 净超额年化 | 超额IR | 日均双边换手 | 年化成本拖累 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for split in ['valid','test']:
        for name,p in splits[split]['portfolio'].items():
            lines.append(f"| {split}/{name} | {fmt(p['gross_return'],True)} | {fmt(p['net_return'],True)} | {fmt(p['net_cagr'],True)} | {fmt(p['net_mdd'],True)} | {fmt(p['net_excess_annual'],True)} | {fmt(p['net_excess_ir'])} | {fmt(p['mean_turnover'],True)} | {fmt(p['annual_cost_drag'],True)} |")
    spread=splits['test']['long_short']
    lines += ['', 'top10/top20目标持仓为30/60只，每日允许替换全部排名退出的股票，实际成交与持仓由Qlib执行。沿用M0收盘成交、9.5%涨跌限制、买入0.05%/卖出0.15%及最低5元成本，初始资金1亿元。未加入冲击成本、融券或容量模型。',
              '年化均使用238日。超额收益为每日收益之差的算术年化；复利年化来自净值。M1回撤包含初始净值1和初始累计超额0，M0默认回撤的起点处理有所不同。',
              f"另保存假想top20%-bottom20%多空标签差：测试期平均{h}日价差为{fmt(spread['mean_horizon_spread'],True)}。它不模拟融券、费用或连续持仓，未换算成可交易净收益或年化收益。分组先按当天分数确定，缺失标签数量保存在CSV中。",'',
              '## 判定与复现', '',
              '仅验证集参与研究状态判定：覆盖≥70%、有效IC≥100天、RankIC≥0.01、正RankIC比例≥50%、top20含成本超额年化>0。与已有KEEP池绝对相关≥0.90则淘汰；通过收益门槛但缺少必要暴露/池对照则FORWARD。KEEP只表示研究池候选。',
              '运行PASS表示管线验收通过；REJECT表示该预设方向未通过研究规则。失败试验保留在SQLite，不把测试集结果用于修改方向或门槛。',
              'BaoStock历史成分与复权使用当前下载的历史快照；代码时序检查通过不能证明供应商历史从未修订。',
              f"运行ID：`{report['run_id']}`；因子ID：`{factor['factor_id']}`。完整定义、指标与原因见同目录`report.json`。",'',
              '![净值与衰减](diagnostics.png)', '']
    (directory/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for key in ['top10','top20']:
        daily=pd.read_csv(directory/'test'/f'{key}_daily.csv',index_col=0,parse_dates=True)
        axes[0].plot(daily.index,(1+daily['return']-daily.cost).cumprod(),label=key)
    axes[0].plot(daily.index,(1+daily.bench).cumprod(),label='CSI300',color='grey')
    axes[0].set_title('Test: NAV after costs');axes[0].legend();axes[0].grid(alpha=.2)
    decay=splits['test']['decay']
    for metric in ['ic','rank_ic']:
        axes[1].plot([int(k) for k in decay],[v[metric] for v in decay.values()],marker='o',label=metric)
    axes[1].axhline(0,color='grey',linewidth=.8);axes[1].set_title('Test: forward horizon');axes[1].legend();axes[1].grid(alpha=.2)
    fig.suptitle(factor['name']+' / fixed direction '+str(factor['direction']))
    fig.tight_layout();fig.savefig(directory/'diagnostics.png',dpi=150);plt.close(fig)


def write_run_report(output,reports,errors,correlation):
    output=Path(output)
    lines=['# M1 Factor Research Engine', '',
           f'完成{len(reports)}个因子评估；执行失败{len(errors)}个。使用封存BaoStock历史沪深300数据，固定训练2008–2014、验证2015–2016、测试2017–2020年7月。', '',
           '| 因子 | 方向 | 验证RankIC | 验证净超额年化 | 测试RankIC | 测试净超额年化 | 测试净值回撤 | 研究状态 |',
           '|---|---:|---:|---:|---:|---:|---:|---|']
    rows=[]
    for r in reports:
        f=r['factor'];v=r['splits']['valid'];t=r['splits']['test'];p=t['portfolio']['top20']
        lines.append(f"| [{f['name']}]({f['name']}/report.md) | {f['direction']:+d} | {fmt(v['primary']['rank_ic'])} | {fmt(v['portfolio']['top20']['net_excess_annual'],True)} | {fmt(t['primary']['rank_ic'])} | {fmt(p['net_excess_annual'],True)} | {fmt(p['net_mdd'],True)} | {r['status']} |")
        rows.append({'factor':f['name'],'direction':f['direction'],'valid_rank_ic':v['primary']['rank_ic'],
                     'valid_net_excess_annual':v['portfolio']['top20']['net_excess_annual'],'test_rank_ic':t['primary']['rank_ic'],
                     'test_net_excess_annual':p['net_excess_annual'],'test_net_mdd':p['net_mdd'],'status':r['status'],'reasons':';'.join(r['reasons'])})
    pd.DataFrame(rows).to_csv(output/'summary.csv',index=False)
    horizon=reports[0]['config']['horizon'] if reports else None
    lines += ['', f'组合列统一使用top20（目标60只）的含成本结果；RankIC使用预先固定方向和{horizon}日主标签。完整报告包含1/2/5/10/20日衰减、年份/市场状态稳定性、暴露、相关性、top10/top20回测及假想多空标签差。',
              '', '研究状态由验证集硬规则决定。所有正负结果和失败试验保存在`data/factor_registry.sqlite`。行业/市值缺失为null；通过验证但这些检查未完成的候选为FORWARD。测试集多次研究后只能视为诊断样本，不能视为未触碰的最终留出集。',
              '', '年化采用238日；超额为算术口径，账户收益与回撤为净值口径。多日标签重叠，表中无显著性或多重试验校正后的优胜结论。M0 Top50/drop5模型基线与本次单因子top30/60日度排名组合用途不同。',
              '', '## 验证集候选相关性', '', '![验证集相关矩阵](correlation.png)', '',
              '## 复跑', '', '```powershell', "Set-Location 'F:\\workspace\\finance\\quant-research-os'", '.\\run-factors.ps1', '```', '',
              '单因子：`.\\run-factors.ps1 -Factor MOM_20`。新试验写入独立目录，已有试验不会覆盖。', '',
              '接口示例（项目根目录，Python配置`PYTHONPATH=src`）：', '', '```python',
              'from quant_research.factors.engine import evaluate_factor',
              'report = evaluate_factor("MOM_20", universe="csi300", horizon=5)',
              'print(report.status, report.artifact_directory)', '```', '',
              'M0永久ID：`BL-CN-CSI300-A158-LGBM-001`；原始源码和产物校验和在`baselines/`。每次M1运行前后验证原基线未改动。', '',
              '数据时点检查不等于证明供应商历史未被事后修订。M2的Alpha158解剖、基本面、行业中性化和边际贡献尚未纳入本阶段。', '',
              '执行依据：[Qlib组合策略文档](https://qlib.readthedocs.io/en/latest/component/strategy.html)。', '']
    if errors: lines += ['## 执行失败', '', *[f"- {e['factor']}: {e['error']}" for e in errors]]
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,8))
    im=ax.imshow(correlation.to_numpy(dtype=float),vmin=-1,vmax=1,cmap='RdBu_r')
    ax.set_xticks(range(len(correlation)),correlation.columns,rotation=45,ha='right')
    ax.set_yticks(range(len(correlation)),correlation.index)
    for i in range(len(correlation)):
        for j in range(len(correlation)):
            ax.text(j,i,fmt(correlation.iloc[i,j]),ha='center',va='center',fontsize=8)
    ax.set_title('Validation: mean daily Spearman correlation');fig.colorbar(im,ax=ax)
    fig.tight_layout();fig.savefig(output/'correlation.png',dpi=150);plt.close(fig)
