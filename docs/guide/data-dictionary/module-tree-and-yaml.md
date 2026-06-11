# 模块树与 YAML

## 概述

**数据字典**以 YAML **模块树**组织配置：HTTP/Kafka/ES 连接器、应用参数、特性开关等。脚本通过 `dict_get("module.path.key", default)` 读取；集成 builtin 通过模块路径加载连接器实例。

每个 **Profile** 可有独立的字典覆盖；未覆盖时回退到全局默认。

---

## 界面操作

1. 打开 **数据字典** Tab
2. 左侧选择 **Profile**（或全局默认）
3. 左侧模块树选择模块（如 `middleware.http`、`app.config`）
4. 右侧 YAML 编辑器编辑内容
5. **保存** — 立即对该 Profile 生效
6. 可选 **校验/解析** — 确认 YAML 语法与结构

---

## 模块结构约定

模块以点分路径组织，YAML 根键对应顶级模块名：

```yaml
# 模块: app.config
app:
  config:
    batch_size: 100
    feature_flags:
      enable_audit: true

# 模块: middleware.http
middleware:
  http:
    instances:
      main:
        services: { ... }

# 模块: middleware.kafka
middleware:
  kafka:
    instances:
      cluster_a: { ... }

# 模块: middleware.elasticsearch
middleware:
  elasticsearch:
    instances:
      main: { ... }
```

---

## 脚本读取

```python
batch = dict_get("app.config.batch_size", 50)
timeout = dict_get("middleware.http.instances.main.base.request_timeout_sec", 10)
{"batch": batch, "timeout": timeout}
```

`dict_get` 支持点分路径与默认值；路径不存在时返回 `default`。

---

## 密钥引用

敏感值不写明文，使用 `secret://` 引用：

```yaml
auth:
  client_secret: secret://iam_client_secret
  password: secret://kafka_pwd
```

在数据字典 **密钥管理** 中创建密钥 id，保存加密值。详见 [密钥管理](secrets.md)。

---

## Profile 覆盖

| 层级 | 说明 |
|------|------|
| 全局默认 | 所有 Profile 的回退基线 |
| Profile 覆盖 | 仅该环境生效的差异配置 |

合并语义：Profile 模块内容与全局按结构化覆盖合并。见 [环境覆盖](profile-overlays.md)。

---

## 试运行临时覆盖

Flow Studio 试运行面板可填写 **数据字典 YAML 覆盖**，仅影响当次运行，不写入 Profile。适合临时指向 Mock 服务。

---

## 配置检查清单

- [ ] 连接器 `base_url` / `bootstrap_servers` 指向正确环境
- [ ] `secret://` 密钥已在密钥管理创建
- [ ] HTTP service/endpoint 名称与脚本 `http_call` 参数一致
- [ ] Kafka consumer_id / producer_id 与字典命名一致
- [ ] protection 限流参数适合预期 QPS

---

## 相关文档

- [什么是数据字典](what-is-data-dictionary.md)
- [环境覆盖](profile-overlays.md)
- [密钥管理](secrets.md)
- [HTTP 集成](../integrations/http.md)
- [Kafka 集成](../integrations/kafka.md)
