# 能力规则 JSON

## 概述

一条策略由若干条规则（CapabilityRule）组成。匹配时通常先看 `builtin_name`，再看 `builtin_category`，再落到更泛的默认规则。

## 规则结构

```json
{
  "builtin_category": "integration",
  "builtin_name": "http_call",
  "action": "suppress",
  "redirect_params": { "url": "..." }
}
```

- `action`：`suppress` | `allow` | `redirect`
- `redirect_params`：仅 `redirect` 时需要

## 白名单（ALLOW）示例

```json
[
  { "builtin_name": "http_call", "action": "allow" }
]
```

## 重定向（REDIRECT）示例

REDIRECT 不会自动改 URL，只是把 `redirect_params` 注入 builtin 调用上下文；builtin 实现需自行读取并处理。

```json
[
  {
    "builtin_name": "http_call",
    "action": "redirect",
    "redirect_params": { "url": "https://sandbox.example/api" }
  }
]
```

## 相关文档

- [各层优先级](layer-priority.md)
