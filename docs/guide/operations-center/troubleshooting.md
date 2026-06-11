# 排障清单

| 现象 | 建议 |
|------|------|
| 试运行 HTTP 无真实请求 | 调试模式抑制副作用；配置 [本次附加策略](../capability-policy/trial-debug-and-test.md) |
| 部署无运行记录 | 检查 Worker 是否在线、调度是否启用 |
| 节点 FAILED | 查看失败报告与节点日志 |
| 测试 verdict fail | 查看断言明细与 `global_ns` 路径 |

## 相关文档

- [失败报告](../flow-studio/failure-reports.md)
