# M2：当前路线与剩余任务

完整状态见[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。**M2整体尚未完成**，BaoStock服务端10001011限制仍存在；AKShare替代源小样本验证已成功，接下来验证整批可用性，不能以较小的数据范围代替原任务。

M2.0–M2.2已完成；M2.3完成五个经济机制的有限研究，但全历史盈利/成长计划仍缺8,354个响应。M2.4完成条件、相关和含成本加入诊断；M2.5已完成修正后的24个滚动模型和6个连续配对回测，全部NO_GO。M2.6/M2.7按事前冻结准入规则未打开，不能称测试已执行或通过。

## 剩余执行顺序

1. 按用户授权推进独立AKShare/东方财富路线，先冻结五字段重建、公告可用时间及来源标记，扩大不同股票/年份的覆盖与交叉验证。见[小样本证据](AKSHARE_FEASIBILITY.md)。BaoStock限制保持，不换出口或账号绕过。
2. 跨源验证通过后，按原历史范围分批构建独立来源面板；32,166个BaoStock缓存保留用于核对，原8,354个缺失响应不因其他来源取数而变成BaoStock已完成。
3. 完成五字段全历史面板与独立逐值验收，再做整体M2完成审计。

修正后的模型仅使用已完整的BP/现金流与原M0 Alpha158，因此有效模型结果不因未完成的盈利/成长数据任务而作废；但模型NO_GO也不能豁免原数据交付。新公式、翻方向和调阈值救回均停止。2021–2023、2024–2025保持封存；M0冻结、M1关闭扩展、M3不启动。

关键证据：[模型](results/m2_rolling/report.md)、[独立重放](results/m2_rolling/independent_verification.json)、[缓存保全](results/m2_history_blocked/report.md)、[机器可读完成审计](M2_COMPLETION_AUDIT.json)。完整模型及下游数值门槛见[M2_ROLLING_PROTOCOL.md](M2_ROLLING_PROTOCOL.md)。
