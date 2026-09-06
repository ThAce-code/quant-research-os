# M2.3 基本面可比性诊断

本批仅诊断2015–2016已观察历史。原三项IC_SCREEN_REJECT不变，不按敏感性结果翻方向或升级。

## 同日财报统计期混用

| method            |   year |   days |   days_multiple_periods |   mean_off_modal_share |
|:------------------|-------:|-------:|------------------------:|-----------------------:|
| query_profit_data |   2015 |    244 |                      96 |              0.0690692 |
| query_profit_data |   2016 |    244 |                      98 |              0.064265  |
| query_growth_data |   2015 |    244 |                      96 |              0.0690692 |
| query_growth_data |   2016 |    244 |                      98 |              0.064265  |

## 金融行业与同报告期敏感性

| candidate        | view                            | variant          |      rank_ic |   days |
|:-----------------|:--------------------------------|:-----------------|-------------:|-------:|
| ROE              | nonfinancial                    | refit            |  0.00991938  |    470 |
| ROE              | nonfinancial                    | original_matched |  0.00759181  |    470 |
| ROE              | nonfinancial_same_fiscal_period | refit            |  0.00939316  |    469 |
| ROE              | nonfinancial_same_fiscal_period | original_matched |  0.00561249  |    469 |
| EARNINGS_GROWTH  | nonfinancial                    | refit            | -0.000824196 |    470 |
| EARNINGS_GROWTH  | nonfinancial                    | original_matched | -0.00250269  |    470 |
| EARNINGS_GROWTH  | nonfinancial_same_fiscal_period | refit            |  0.00367328  |    469 |
| EARNINGS_GROWTH  | nonfinancial_same_fiscal_period | original_matched |  0.000673528 |    469 |
| LOW_ASSET_GROWTH | nonfinancial                    | refit            |  0.00443945  |    470 |
| LOW_ASSET_GROWTH | nonfinancial                    | original_matched |  0.00733551  |    470 |
| LOW_ASSET_GROWTH | nonfinancial_same_fiscal_period | refit            |  0.00686521  |    469 |
| LOW_ASSET_GROWTH | nonfinancial_same_fiscal_period | original_matched |  0.00838308  |    469 |

refit为在预定子样本重新中性化；original_matched为原分数限制到完全相同股票。不同view之间仍不是同样本，不能直接择优。

## 报表口径

茅台2015年供应商netProfit与年报合并净利润一致，而非归母净利润；roeAvg与归母利润/期初期末平均归母权益一致，不能当成加权ROE或TTM ROE。年度npMargin、CFOToOR对照见issuer_crosscheck.json。
来源：[发行人2015年报全文镜像](https://stock.stockstar.com/notice/JC2016032400000505.shtml)、[年报摘要数据镜像](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?CompanyCode=10000351&gather=1&id=2269811)。只有一个公司年度得到交叉核对，不能推定全库无修订。

## 更长研究区间

目标2008–2020年7月；固定3只股票、6个年份、3个接口共99项可用性探针，非空99项。逐年历史成分并集见historical_scope.csv。探针不等于全历史/全股票季度覆盖。
2015–2016为已观察研究区间，2017–2020为已消耗诊断；2021–2023资格与2024–2025锁箱仍保护。

行业名称存在旧供应商编码乱码，使用已有稳定的CSRC行业代码前缀，不改旧分组或封存数据。供应商历史修订未知、样本筛选损耗、财报时间口径和金融业务可比性仍需在扩展实验中显式保留。
