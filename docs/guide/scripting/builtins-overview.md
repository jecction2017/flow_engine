# 内置能力概览

## 概述

在 **能力与脚本 → Python 内置** 查看函数说明。常见函数可直接调用，无需 `load`。

## 示例

```python
n = demo_add(3, 4)
timeout = dict_get("app.http.timeout_sec", 10)
order_id = resolve("$.global.order.id")

# 流程控制（LOOP / 同层跳转）
# flow_continue()   # 跳过当前迭代
# flow_break()      # 结束循环
# flow_jump("next_node_id")  # 按节点逻辑 ID 跳转
# flow_terminate()  # 终止本任务（跳过重试）

{"sum": n, "timeout": timeout, "order_id": order_id}
```

## 进阶

输入函数名前缀时，编辑器会自动补全并显示参数签名。完整列表以界面注册表为准。

## 相关文档

- [load 与模块](load-and-modules.md)
- [Python 内置](../capability-center/python-builtins.md)
