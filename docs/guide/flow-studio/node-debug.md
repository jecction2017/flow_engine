# 节点调试

## 概述

在 Flow Studio 选中 **task 节点** 后，打开 **调试** 抽屉可**单独执行当前节点脚本**，无需跑完整流程。服务端固定 debug 模式，默认抑制副作用类 builtin。

适合：快速验证脚本语法、返回值结构、resolve 路径是否正确。

---

## 操作步骤

1. 选中要调试的 **task** 节点
2. 点击 **调试** 打开抽屉
3. 填写 **调试上下文 JSON** — 模拟 `$.global.*` 数据：
   ```json
   {
     "order": {"id": "O-1", "amount": 99},
     "tenant_id": "t001"
   }
   ```
4. 可选：展开 **本次附加策略**，临时 allow 集成调用
5. 点击 **运行**
6. 查看 **输出 JSON** 与日志

---

## 与试运行的区别

| | 节点调试 | 试运行 |
|---|----------|--------|
| 范围 | 单个 task 脚本 | 完整流程 |
| 上下文 | 手动填写 JSON | 初始上下文 + 流程执行链 |
| loop/subflow | 不涉及 | 完整拓扑 |

节点调试通过后，仍建议 **试运行** 验证节点间数据传递。

---

## 推荐步骤

1. 先返回 `{"ok": True}` 确认管线
2. 用 resolve 读 1～2 个字段
3. 把复杂逻辑包进 `def`
4. 再加 dict_get / lookup_query（不抑制）
5. 最后测 http_call（可能需 allow 策略）

---

## 常见问题

**Q: 输出为空或报错**  
A: 检查末行是否为 dict；语法是否违反方言（顶层 if）。

**Q: resolve 返回 None**  
A: 调试上下文 JSON 路径与脚本 `$.global.xxx` 不一致。

---

## 相关文档

- [脚本调试](../capability-center/script-debug.md)
- [试运行流程](trial-run.md)
- [第一次写脚本](../getting-started/first-script-and-debug.md)
