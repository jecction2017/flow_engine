# 试运行、调试与测试中的策略

## 概述

用户脚本调试、节点调试、流程试运行均为临时执行：默认抑制副作用。在对应页面的 **本次附加策略** 折叠区可追加规则：

- 添加 `ALLOW` 放行某个 builtin（建议仅指向沙箱/测试环境）
- 添加 `REDIRECT` 并提供 `redirect_params`

## 示例脚本

```python
r = http_call("user_service", "health")
{"probe": r}

# 在临时调试入口默认会被抑制（SUPPRESS），输出里会有 _suppressed=true
# 如需联调沙箱：在页面「本次附加策略」里加 allow 或 redirect
```

## 测试中心

测试运行固定为调试模式，默认抑制副作用：

- **测试方案 · 默认附加策略** — 保存到方案；新建批次未单独配置时继承
- **测试批次 · 附加策略** — 仅该批次；覆盖方案默认

建议：与沙箱联调相关的通用规则放在方案默认；批次里只做临时加减。

## 相关文档

- [规则 JSON](policy-rules-json.md)
- [测试中心断言](../test-center/assertions.md)
