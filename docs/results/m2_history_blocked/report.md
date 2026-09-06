# M2历史财务离线保全

{
  "status": "PARTIAL_BLOCKED",
  "network_calls": 0,
  "planned_requests": 40520,
  "verified_cached_requests": 32166,
  "missing_requests": 8354,
  "complete_symbol_methods": 987,
  "total_symbol_methods": 1452,
  "data_complete": false,
  "provider_error": "10001011",
  "source_failed_run": "20260906T090008112664Z",
  "interpretation": "Known incomplete symbol-method histories are entirely withheld; no old-value resurrection or completeness claim"
}

BaoStock明确拒绝访问后停止网络请求。缺失请求不是字段本身为空；任何缺少季度响应的股票/接口历史整体不进入保全面板，避免未知新公告被旧数据替代。已验证缓存可以在服务恢复后复用，但本报告不代表完整数据验收。缺失清单见missing_requests.csv。M2整体目标仍未完成。
