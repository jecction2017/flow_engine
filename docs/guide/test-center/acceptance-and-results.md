# 验收与测试结果

## 概述

每条 Lookup 用例运行结束后生成 `verdict=pass/fail`，并附带断言明细。

## 结果说明

- **pass**：流程完成且全部断言通过
- **fail**：流程未完成，或任一条断言失败（查看失败规则 id 与 message）

测试运行固定调试模式，副作用默认抑制 — 见 [试运行与测试中的策略](../capability-policy/trial-debug-and-test.md)。

## 相关文档

- [测试断言](assertions.md)
