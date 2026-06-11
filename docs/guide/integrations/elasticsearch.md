# Elasticsearch 集成

## 概述

脚本通过 ES 内置函数查询 Elasticsearch，连接信息在数据字典 `middleware.elasticsearch` 配置。所有 ES builtin 的 `side_effects` 为 `network`（读取类）或相应写入类，受能力策略约束。

---

## 可用内置函数

| 函数 | 说明 |
|------|------|
| `es_search` | 执行搜索查询 |
| `es_mget` | 批量按 ID 获取文档 |
| `es_count` | 计数查询 |
| `es_scroll` | 滚动查询大量数据 |

完整参数签名见 **能力与脚本 → Python 内置**，搜索 `es_` 前缀。

---

## 数据字典配置

```yaml
middleware:
  elasticsearch:
    instances:
      main:
        hosts: ["https://es.example.com:9200"]
        auth:
          username: elastic
          password: secret://es_password
        default_index: logs-*
        protection:
          max_in_flight: 8
          max_rps: 50
```

具体 YAML 结构以数据字典模块模板为准；保存后对该 Profile 生效。

---

## 脚本示例

```python
def search_logs():
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"level": "ERROR"}},
                    {"range": {"@timestamp": {"gte": "now-1h"}}}
                ]
            }
        },
        "size": 100
    }
    r = es_search("main", query)
    if not r.get("ok"):
        fail("es_search failed: " + str(r.get("error")))
    hits = r.get("data", {}).get("hits", [])
    return {"error_count": len(hits), "hits": hits}

search_logs()
```

> 实际函数签名（实例名、索引参数位置）以注册表为准；上例为示意结构。

---

## 返回值

统一 envelope 风格，通常包含：

- `ok` / `success` — 是否成功
- `data` — 查询结果体
- `error` — 失败时的错误信息
- `meta` — 耗时、correlation_id 等

被抑制时返回占位结果，含 `_suppressed` 标记。

---

## 使用建议

1. **大结果集**用 `es_scroll` 分批拉取，避免单次 `size` 过大
2. **生产查询**在 deployment production 模式下执行，debug 下默认不发出真实请求
3. **索引与权限**在 ES 侧配置好；数据字典只管理连接
4. 复杂聚合逻辑可结合 `metric_feature_*` 管道（见 [指标特征流水线](metric-feature.md)）

---

## 相关文档

- [模块树与 YAML](../data-dictionary/module-tree-and-yaml.md)
- [调用为何被抑制](../capability-policy/why-calls-are-suppressed.md)
- [Python 内置](../capability-center/python-builtins.md)
