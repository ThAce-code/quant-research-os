# Quant Research OS：项目研究上下文

状态核对日期：2026-09-06。本文件是唯一当前状态入口，CONTEXT.md只保留指针；旧聊天和旧失败run不代表当前状态。

**本轮冻结范围内的M2已收束，结论NO_GO：没有确认独立Alpha，KEEP池为0。** 原范围数据交付已通过授权的替代来源完成并独立验收。资格期和锁箱按事前准入条件未进入，不能称测试已执行或通过。见[逐项完成审计](M2_COMPLETION_AUDIT.json)。

## M2统一阶段状态

| 编号 | 当前状态 | 结论与证据范围 |
|---|---|---|
| M2.0 研究基础设施 | 完成 | PIT/as-of、暴露、统计、费用、来源与append-only registry |
| M2.1 Value pilot | 完成 | 六个主假设；旧BP FORWARD只是历史筛选记录 |
| M2.2 Existing Alpha Map | 完成 | 完整158表达式、156达覆盖、123代表；20-PC保留77.7% |
| M2.3 Fundamental families | 本轮有限研究与数据交付完成 | 五个经济机制研究；726只股票五字段面板，来源明确且保留缺失，不是完整历史版本PIT |
| M2.4 Independence test | 完成既定诊断 | 相关、条件残差、含成本加入；未确认独立增量 |
| M2.5 Model increment | 完成，NO_GO | 修正后24次滚动拟合、6组连续配对组合及独立重放 |
| M2.6 Qualification | 无准入分支关闭，未执行 | 上游没有GO候选，2021–2023未通过、未打开 |
| M2.7 Lockbox | 无准入分支关闭，未执行 | 无资格通过者，2024–2025继续封存 |

这里的完成指已约定的有限研究和条件决策树，不代表穷尽所有因子族、取得全市场数据或找到可交易Alpha。M0冻结、M1关闭扩展；M3.0已获用户授权，正在执行确定性论文接入首批；M3整体尚未完成。

## 有效滚动模型结果

有效输入run `20260906T092519215478Z`；模型run `20260906T092732142566Z`。2015–2020按年度扩展训练、前一年验证、两个交易日标签清洗。四组输入为完整Alpha158、加入BP、加入现金流、加入两者；同股票、标签、seed 42和M0费用，无参数搜索。采用M0一日持有标签，不能与五日单因子门槛混淆。

| variant      |   rank_ic_increment |        q | net_annual_increment   |   positive_full_years | decision   |
|:-------------|--------------------:|---------:|:-----------------------|----------------------:|:-----------|
| ADD_BP       |          0.00111902 | 0.371064 | -1.53%                 |                     1 | NO_GO      |
| ADD_CASHFLOW |         -0.00108983 | 0.825087 | -8.76%                 |                     0 | NO_GO      |
| ADD_BOTH     |          0.00222005 | 0.178411 | -4.85%                 |                     0 | NO_GO      |

三个主比较统一BH，全部未通过冻结的联合GO门槛。[模型协议](M2_ROLLING_PROTOCOL.md)、[报告](results/m2_rolling/report.md)、[独立验收](results/m2_rolling/independent_verification.json)。独立重放2,424个预测、抽查200个RankIC日、检查24个训练边界与全部预测行的因果股票范围，一致。

分类过渡文本“金融业”最初漏排，发现后只修正分类实现，重跑同一协议。旧输入/模型/保护期记录 `20260906T090208399969Z`、`20260906T090722431779Z`、`20260906T092315233266Z`保留但作废，不作为最终结论。[修正记录](M2_INDUSTRY_CORRECTION.md)。有效输入的2015+分数与原补充批次完全一致。


## 完整范围数据交付与限制

研究范围是2008–2020年7月历史CSI300的726只股票，不是全A股。原财务计划20,260个股票季度、两个接口共40,520项，已逐项核销。

987个股票/接口的完整历史继续使用BaoStock；465个不完整历史整体使用AKShare源接口的东方财富重建，涉及233只股票。另取10只对照股票，合计213页、24,069条原始报表。各序列来源单独记录，未逐季度拼接或伪装成BaoStock缓存。

有效数据run `20260906T134337933185Z`，独立验收从原始源重算112,405条事件、11,111,430个五字段逐日单元，并从规范数据重建成员范围。[数据报告](results/m2_alternate_history/report.md)、[独立验收](results/m2_alternate_history/independent_verification.json)、[来源表](results/m2_alternate_history/source_assignment.csv)。现金流此前已独立核验2,222,286个单元，完整采集未变。

替代源大样本核对发现真实口径与修订问题：金融净利率须使用完整金融收入；重组公司旧报告数值可能被之后的比较数据重述。已修正金融分母，并对替代源主面板使用所有依赖NOTICE_DATE与UPDATE_DATE的最大值，严格晚于该时间才可使用。未知版本时间或未齐备依赖保持缺失，不能把新值回填原公告日。[口径审计](M2_ALTERNATE_SOURCE_AUDIT.md)、[冻结及修正规则](M2_ALTERNATE_SOURCE_PROTOCOL.md)。

这一保守处理不能恢复旧版本，整体ROE逐年覆盖约69%–81%，详见[五字段覆盖表](results/m2_alternate_history/coverage.csv)。BaoStock完整历史仍保留原公告对齐、修订未知假设；两个来源的时间假设不同。跨源诊断存在巨大差异，不能沿用小样本17/17吻合来声称全量等价；替代面板没有被用来重测或挽救失败因子。

12条1900年占位日期记录已隔离，均在原计划及必要依赖之外。所有字段仍按最新财报期优先、400/550日年龄限制处理，最新缺失不回填旧值。覆盖缺口和供应商版本局限是本次交付的真实边界，并非全部单元有值。

BaoStock原失败run `20260906T090008112664Z`及8,354个缺失响应保持原状；它的访问限制没有被确认解除，也未证实是临时IP封禁。本地保护文件仍阻止该接口自动续采。替代来源完成数据交付不等于恢复BaoStock访问。[历史失败与保全报告](results/m2_history_blocked/report.md)。

旧行业分类按当期完整文字保留，不用未来类别回填；金融保险业、金融业与J66–J69排除。早期中性化共同覆盖仅约43.7%–55.2%，未为覆盖修改分组或阈值。市值为流通市值代理，成本及涨跌停为M0近似，未证明容量或实盘执行。

## 固定研究结论与记录

Value pilot六项中仅BP中性化历史FORWARD（RankIC约0.033、含成本超额年化12.79%），低波配对增量区间跨零；该旧结果不能外推到本次更长非金融样本。BP最新模型准入已REJECT，原历史记录保留。[Value报告](results/m2/report.md)。

ROE、净利润增长、低资产增长首轮RankIC约0.0069、-0.0015、0.0051，均REJECT；现金流质量和20日非流动性补充约0.0058、0.0061，均REJECT。没有翻方向、换窗口或放松阈值救回。[四族筛选](results/m2_family_screen/report.md)、[补充筛选](results/m2_supplementary_screen/report.md)、[可比性诊断](results/m2_comparability/report.md)。

补充条件诊断是在滚动结果后发起的证据补齐，复用2015拟合20-PC在2016检验，不改变任何准入。压缩参考只保留77.7%方差，正残差仍可能含技术信息；完整158非线性参照由滚动实验检验。[条件报告](results/m2_conditional_completion/report.md)、[含成本加入/删除及固定组合诊断](results/m2_rolling/diagnostics.json)。

现有registry追加了5项失败筛选和2项模型准入拒绝，7条回读一致，原26条历史试验保留，KEEP池为0。[登记验收](results/m2_registry_closure/verification.json)。


## 完成审计与保留样本

本轮必需交付与验证已完成，无待执行的上游合格候选。M2.6/M2.7是事前协议的无准入退出，分别保留[资格记录](results/m2_protected_gate/qualification.json)和[锁箱记录](results/m2_protected_gate/lockbox.json)，executed=false、passed=false、0数据请求。2015–2016已观察、2017–2020已消耗，不能称新鲜OOS。

回归：`158 passed, 5 warnings in 80.68s`；M0源代码、原实验产物和数据身份核对未变。公开196份来源证据已核对SHA256，详见[sources.json](results/sources.json)。完整数据、模型、SQLite和原始报表留在本地。

## M3.0 当前批次

2026-09-06按网页端修正意见推进，以RD-Agent(Q)研究对象/执行接口为主参考。确定性论文接入首批已运行并归档；M3整体尚未完成，LLM生成与自动优化尚未开启。

协议提交`9f8eb30`，实现提交`11101ff`，有效run `20260906T145830964860Z`。见[协议](M3_PROTOCOL.md)、[首批报告](results/m3_paper_pilot/report.md)、[结果](results/m3_paper_pilot/results.json)与[独立重放](results/m3_paper_pilot/independent_verification.json)。

- ResearchHypothesis五类来源、字段/算子/方向/时序证据，映射现有FactorDefinition和DSL；新增批内AST去重及读取市场数据前的保护期配置限制。
- 首批《101 Formulaic Alphas》方程(3)与Alpha#101，均为PAPER_RECONSTRUCTED：公开公式迁移至CSI300和次日收盘执行，不能称复现原论文收益。
- 固定正方向、中性化五日RankIC分别-0.029408、-0.022580，BH q均1.0，两个年度均负，均REJECT。未翻方向、调窗口或阈值。2016条件诊断复用冻结20-PC，仍不是独立Alpha证明。
- 假设→定义→运行→结果来源链已归档，原SQLite追加两项拒绝。M2冻结的33项历史试验保留；项目现35项，KEEP仍为0。
- 708,576个原始因子单元直接从canonical重算；100个日期RankIC、两条registry记录和38份源快照校验通过。回归171 passed、5项已有warnings。

当前完成的是M3.0的确定性接入、历史筛选、条件诊断和拒绝分支。两个候选未达到初筛门槛，含成本/滚动模型没有执行，记录NOT_RUN_SCREEN_REJECT。通用合格候选的后续费用/模型接口现已实现（下文），跨批去重和生成层仍待完成；不能把拒绝分支验收写成完整M3完成。

下一批需用真正通过初筛的新候选验证费用/模型整条分支，再做有预算的M3.1生成。M3.2只在research split反馈优化，M3.3再做轨迹记忆/演化。2021–2025继续封存，旧M2 NO_GO不变。

### M3.0 合格候选接口补齐

`m3/increment.py`和`configs/m3/increment.json`已实现：核验screen及registry→共同样本→完整158 BASE/逐项ADD→M2年度滚动和清洗→同费用组合/固定blend→模型门槛→追加registry。原M2代码及参数未改；最多3个survivors、24次拟合和7组组合。`run_m3.py --resume-screen`支持从既有screen续接，不重复筛选。

有效CLI准入run `20260907T010954850339Z`（UTC，用户当地仍9月6日）返回NO_ENTRY：0行情加载、0拟合、0组合，两个拒绝保持。见[准入记录](results/m3_increment_admission/report.md)。19项针对性测试通过，含小规模真实LightGBM拟合及共同样本/标签清洗检查。

验证边界：尚无真正合格候选，所以完整规模的滚动模型/组合分支尚未实测。接口实现、拒绝分支端到端验证、合格分支真实研究验证是三个不同状态。2021+从未因此开启。首批报告和旧源码快照保留原状。
