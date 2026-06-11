# 默认抑制行为

## 概述

在 **debug** 与 **shadow** 模式下，系统内置默认规则对以下 **builtin category** 执行 `SUPPRESS`：

- `integration`
- `db_read`
- `db_write`
- `mq_publish`

**production** 模式下系统内置默认列表为空（不额外抑制）。

试运行、节点调试、测试中心均由服务端锁定 **RunMode.DEBUG**，因此默认抑制上述类别，除非被更高优先级规则 `allow`。

---

## 不受默认抑制的类别

以下 category 在 debug 下**默认允许**执行：

- `dictionary` — 如 `dict_get`
- `lookup` — 如 `lookup_query`
- `runtime`、`demo`、`user`、`system` — 如 `resolve`、`log_*`、`cache_*`、`flow_jump`

---

## 被抑制时的输出

函数体不执行，直接返回 builtin 注册的 `suppress_result`。示例：

**HTTP（integration）**

```json
{
  "success": false,
  "error_code": "SUPPRESSED",
  "error_msg": "integration suppressed",
  "meta": {"_suppressed": true}
}
```

**Kafka（integration）**

```json
{
  "ok": false,
  "error": {"code": "SUPPRESSED", "message": "integration suppressed"},
  "_suppressed": true
}
```

脚本应检查这些标记，区分「策略抑制」与「真实业务失败」。

---

## 如何放行

在更高优先级层添加 `allow` 规则，例如试运行 **本次附加策略**：

```json
[{"builtin_category": "integration", "action": "allow"}]
```

---

## 相关文档

- [副作用 builtin](side-effects.md)
- [规则 JSON](policy-rules-json.md)
- [各层优先级](layer-priority.md)
