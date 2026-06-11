# 试运行流程

## 概述

Flow Studio 右侧 **试运行** 面板发起单次调试执行。服务端**强制** `RunMode.DEBUG`（`http_api.RunFlowBody` 注释与 `RunOptions` 实现）。

---

## 操作步骤

1. 打开目标流程，**保存草稿**
2. 点击 **试运行**
3. 选择 **Profile**、**超时**（`timeout_sec`，默认 30s，最大 600s）
4. 可选：
   - **初始上下文 JSON** — 见下方 merge 说明
   - **runtime_patch** — 数据字典运行时补丁
   - **数据字典 YAML 覆盖** — 临时覆盖模块
   - **本次附加策略** — `capability_policy` 规则列表
5. 运行 → 查看时间线与日志

---

## 初始上下文与 merge

| merge | 行为 |
|-------|------|
| `false`（**默认**） | 请求体 `initial_context` **替换**流程文档中的 `initial_context` |
| `true` | 先取流程 `initial_context`，再被请求体覆盖（浅合并） |

界面若提供「与流程初始上下文合并」选项，对应 `merge=true`。未填 `initial_context` 时使用流程定义中的值。

---

## 能力策略合并（试运行）

试运行请求的 `capability_policy` 写入 `RunOptions.deployment_capability_policy`，与 Profile 的 debug 段 `system_capability_policy`、系统 debug 默认拼接。见 [各层优先级](../capability-policy/layer-priority.md)。

---

## 结果说明

集成类 builtin 默认 SUPPRESS；`dict_get`、`lookup_query` 正常可用。

---

## 相关文档

- [第一次试运行](../getting-started/first-trial-run.md)
- [失败报告](failure-reports.md)
- [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)
