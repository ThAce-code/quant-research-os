# Quant Research OS：项目研究上下文

状态核对日期：2026-09-06。本文件是唯一当前状态入口；CONTEXT.md只保留指针。不要沿用旧聊天的完成表或主观百分比。

**M2整体仍未完成：历史盈利/成长采集被BaoStock明确拒绝，错误10001011“黑名单用户，请与管理员联系”。** 当前已停止网络请求，保全缓存；不能为了收尾删掉剩余数据任务。有效滚动模型已完成并得出NO_GO，没有独立Alpha、KEEP池为0。

## M2统一阶段状态

| 编号 | 状态 | 完成范围与剩余 |
|---|---|---|
| M2.0 研究基础设施 | 完成 | PIT/as-of、暴露、统计、费用、现有append-only registry；新增明确拒绝停止保护 |
| M2.1 Value pilot | 完成 | 六个主假设，旧BP FORWARD仅是历史筛选记录 |
| M2.2 Existing Alpha Map | 完成 | 158表达式、156达覆盖、123代表；20-PC只保留77.7% |
| M2.3 Fundamental families | 部分完成、外部阻塞 | 五个经济机制的有限研究已做；盈利/成长全历史还缺8,354个响应，完整逐值验收未完成 |
| M2.4 Independence test | 完成既定诊断、未确认增量 | 条件残差、同样本相关、75/25含成本加入组合；后验诊断不能用于准入 |
| M2.5 Model increment | 完成，NO_GO | 修正后24次滚动base/add/drop、6组连续配对回测，独立重放通过 |
| M2.6 Qualification | 准入分支关闭，未执行 | 没有历史GO候选，2021–2023未打开、未通过 |
| M2.7 Lockbox | 准入分支关闭，未执行 | 2024–2025继续封存，没有资格通过者 |

M0基线冻结，M1关闭扩展；M3没有启动。用户要求完成全部M2任务的目标尚未实现，不能将部分数据保全或NO_GO替代剩余任务。

## 有效滚动模型结果

有效输入run `20260906T092519215478Z`；模型run `20260906T092732142566Z`。2015–2020按年度扩展训练、前一年验证、两个交易日标签清洗。四组输入为完整Alpha158、加入BP、加入现金流、加入两者；同股票、标签、seed 42和M0费用，无参数搜索。采用M0一日持有标签，不能与五日单因子门槛混淆。

| variant      |   rank_ic_increment |        q | net_annual_increment   |   positive_full_years | decision   |
|:-------------|--------------------:|---------:|:-----------------------|----------------------:|:-----------|
| ADD_BP       |          0.00111902 | 0.371064 | -1.53%                 |                     1 | NO_GO      |
| ADD_CASHFLOW |         -0.00108983 | 0.825087 | -8.76%                 |                     0 | NO_GO      |
| ADD_BOTH     |          0.00222005 | 0.178411 | -4.85%                 |                     0 | NO_GO      |

三个主比较统一BH，全部未通过冻结的联合GO门槛。[模型协议](M2_ROLLING_PROTOCOL.md)、[报告](results/m2_rolling/report.md)、[独立验收](results/m2_rolling/independent_verification.json)。独立重放2,424个预测、抽查200个RankIC日、检查24个训练边界与全部预测行的因果股票范围，一致。

分类过渡文本“金融业”最初漏排，发现后只修正分类实现，重跑同一协议。旧输入/模型/保护期记录 `20260906T090208399969Z`、`20260906T090722431779Z`、`20260906T092315233266Z`保留但作废，不作为最终结论。[修正记录](M2_INDUSTRY_CORRECTION.md)。有效输入的2015+分数与原补充批次完全一致。

## 数据完整性与阻塞

范围是2008–2020年7月历史CSI300的726只股票，不是全A股市场。现金流20,260请求已完成，原始19,762条记录中295条截止后公告排除，2,222,286个面板单元独立核验通过。

盈利/成长完整计划40,520个请求；失败run `20260906T090008112664Z`。离线核对确认现有32,166个响应缓存及哈希，仍缺8,354个请求。完整历史的股票/接口组合为987/1,452。这不是完整数据PASS；缺少任何季度响应的股票/接口历史整体不进入保全面板，避免未知公告被旧值替代。[失败记录](results/m2_history_blocked/collection_failure.json)、[保全报告](results/m2_history_blocked/report.md)、[缺口汇总](results/m2_history_blocked/missing_summary.csv)。精确缺失清单保存在本地`experiments/m2/m2_history_cache_audit_v1/20260906T095714683879Z/missing_requests.csv`。

本地`data/baostock_access_restriction.json`记录明确拒绝，续采入口在网络连接前停止。只有服务端解除限制的证据，或合规提供缺失原始缓存，才能恢复完整数据任务；不能换IP/账号绕过。没有推断具体封禁原因或解除时间。[服务恢复说明](BAOSTOCK_ACCESS_RESTRICTION.md)。

旧行业识别已恢复，金融保险业、金融业与J66–J69排除；保留完整旧分组，不用未来类别回填。但早期共同中性化覆盖约43.7%–55.2%，没有为覆盖合并行业或改最小5只规则。[输入覆盖](results/m2_model_inputs/coverage.csv)。pubDate严格早于信号、400/550日有效期和财报期优先仍沿用原规则；供应商修订未知，不是完整历史版本PIT；比率不是自行重建TTM。规模为流通市值代理，成本和涨跌停是M0近似，未证明容量或实盘执行。

## 固定研究结论与记录

Value pilot六项中仅BP中性化历史FORWARD（RankIC约0.033、含成本超额年化12.79%），低波配对增量区间跨零；该旧结果不能外推到本次更长非金融样本。BP最新模型准入已REJECT，原历史记录保留。[Value报告](results/m2/report.md)。

ROE、净利润增长、低资产增长首轮RankIC约0.0069、-0.0015、0.0051，均REJECT；现金流质量和20日非流动性补充约0.0058、0.0061，均REJECT。没有翻方向、换窗口或放松阈值救回。[四族筛选](results/m2_family_screen/report.md)、[补充筛选](results/m2_supplementary_screen/report.md)、[可比性诊断](results/m2_comparability/report.md)。

补充条件诊断是在滚动结果后发起的证据补齐，复用2015拟合20-PC在2016检验，不改变任何准入。压缩参考只保留77.7%方差，正残差仍可能含技术信息；完整158非线性参照由滚动实验检验。[条件报告](results/m2_conditional_completion/report.md)、[含成本加入/删除及固定组合诊断](results/m2_rolling/diagnostics.json)。

现有registry追加了5项失败筛选和2项模型准入拒绝，7条回读一致，原26条历史试验保留，KEEP池为0。[登记验收](results/m2_registry_closure/verification.json)。

## 未完成任务与保留样本

1. BaoStock访问恢复或缺失源数据到位后，补齐原40,520请求清单，不缩小股票/年份/字段范围。
2. 生成完整五字段面板，完成独立逐值核验和覆盖报告。
3. 再进行整体M2完成审计、更新上下文；当前不得宣布整体完成。

2015–2016已观察，2017–2020已消耗，不能称新鲜OOS。没有历史GO候选，故[资格记录](results/m2_protected_gate/qualification.json)和[锁箱记录](results/m2_protected_gate/lockbox.json)均executed=false、passed=false、0请求。这是预先冻结决策树的无准入分支，不是假装完成独立测试；也不豁免上述尚未完成的数据工作。

回归：`154 passed, 5 warnings in 21.47s`。M0数据身份未变。公开报告是小型精确副本，179份来源文件已核对哈希；原始数据、完整面板、模型、SQLite留在本地。来源run和SHA256见[sources.json](results/sources.json)。
