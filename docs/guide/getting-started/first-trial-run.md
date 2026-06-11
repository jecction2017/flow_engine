# 第一次试运行

## 概述

在 Flow Studio 中对已保存的流程发起一次受控执行，查看节点时间线与日志，验证流程是否按预期运行。这是每个新流程的**第一步验证**。

---

## 前置条件

- API 与 Web 已启动（见 [安装与访问](install-and-access.md)）
- 已在 Flow Studio 打开或创建目标流程
- 流程中至少有一个 task 节点且脚本可执行

---

## 操作步骤

1. **保存草稿** — 确保最新修改已保存
2. 点击 **试运行** 打开右侧面板
3. 选择 **Profile**（通常选 `default` 或你的开发环境）
4. 可选：填写 **初始上下文 JSON**，例如：
   ```json
   {"message": "hello", "count": 3}
   ```
5. 设置 **超时**（建议首次 60–120 秒）
6. 点击 **运行**
7. 在 **节点执行时间线** 查看状态：
   - 绿色/成功 — 节点完成
   - 红色/失败 — 展开查看失败报告与日志
8. 点击节点展开 **日志抽屉**，查看 `log_info` 等输出

---

## 结果说明

| 节点状态 | 含义 |
|----------|------|
| SUCCESS / COMPLETED | 正常完成 |
| FAILED | 脚本或引擎错误，看失败报告 |
| SKIPPED | 被 condition 跳过 |

试运行固定 **debug 模式**，HTTP 等副作用可能被抑制 — 见 [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)。

---

## 下一步

| 若… | 则… |
|-----|-----|
| 脚本语法报错 | 阅读 [基础语法](../scripting/syntax-essentials.md) |
| 需要测 HTTP | 配置 [本次附加策略](../flow-studio/trial-run.md) 或先写 Mock |
| 流程正确 | [提交版本](../flow-studio/flow-versioning.md) → [第一次测试](first-test-plan.md) |
| 要看拓扑含义 | [读懂流程拓扑](../flow-studio/read-flow-topology.md) |

---

## 相关文档

- [试运行详解](../flow-studio/trial-run.md)
- [失败报告](../flow-studio/failure-reports.md)
- [读懂流程拓扑](../flow-studio/read-flow-topology.md)
