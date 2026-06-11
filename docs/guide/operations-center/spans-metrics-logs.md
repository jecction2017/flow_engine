# 链路、指标与日志

## 概述

每次部署运行或测试运行结束后，可在 **运行中心 → 运行记录** 打开详情，通过 **Spans**、**指标**、**日志** 三个面板分析耗时、错误与业务输出。测试中心的用例运行也复用同一套可观测模型。

---

## 如何打开

1. 运行中心 → **运行记录**（或部署详情 → 最近运行）
2. 点击目标 run 进入详情
3. 切换 **Spans** / **指标** / **日志** 标签页

---

## Spans（调用链路）

Spans 以树形结构展示流程执行的调用层次：

| 信息 | 说明 |
|------|------|
| 节点 id / name | 对应流程中的节点 |
| 状态 | SUCCESS / FAILED / SKIPPED 等 |
| 耗时 | 节点 wall time |
| 父子关系 | loop 迭代、subflow 子树嵌套展示 |

### 使用技巧

- 找**最慢节点**：按耗时排序或展开时间线
- 找**失败点**：FAILED 节点展开查看错误信息与堆栈
- **跳转到日志**：选中 Span 可过滤关联日志

### Span 详情 API

`GET /api/spans/{id}` 与 `GET /api/spans/{id}/children` 供界面钻取；测试运行与部署运行共用。

---

## 指标（Metrics）

指标面板汇总本次 run 的量化摘要，例如：

- 各节点执行次数与成功率
- 集成调用耗时分布（HTTP、Kafka 等）
- 自定义业务指标（脚本或引擎上报）

具体指标项取决于流程内容与集成调用。用于 SLA 监控与性能回归对比。

---

## 日志（Logs）

日志来自：

- 脚本 `log`、`log_info`、`log_warn`、`log_error`、`log_debug`
- 引擎与集成层结构化日志（含 `correlation_id`）

### 筛选

- 按**日志级别**过滤
- 按**节点**或 Span 关联过滤
- 搜索关键词（界面支持时）

### correlation_id

同一 run 内所有日志与集成调用共享 `correlation_id`，便于与外部系统（网关、Kafka）日志关联排查。

---

## 测试运行 vs 部署运行

| | 测试运行 | 部署运行 |
|---|----------|----------|
| 入口 | 测试中心 | 运行中心 |
| Spans | 有 | 有 |
| verdict | 有断言评估 | 无 |
| RunMode | 固定 debug | production / shadow |

---

## 排查流程建议

```
运行失败
  → Spans 定位 FAILED 节点
  → 该节点日志看脚本 fail() 或异常
  → 集成节点检查是否 SUPPRESSED（debug）或 HTTP/ES 错误码
  → 对比 Profile 配置与数据字典
```

---

## 相关文档

- [监控运行记录](monitor-runs.md)
- [失败报告](../flow-studio/failure-reports.md)
- [故障排查](troubleshooting.md)
