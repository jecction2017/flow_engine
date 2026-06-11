# 密钥

## 概述

敏感值在 **密钥管理** 中维护，数据字典 YAML 用 `secret://<name>` 引用。运行时由 `secrets/service.resolve_secret_references` 在连接器绑定等场景解密；**界面不可查看明文**。

---

## secret:// 格式（代码校验）

须匹配正则（`secrets/reference.py`）：

```
secret://<name>
```

其中 `<name>` 须满足：`^[a-z][a-z0-9_-]{0,63}$`

- **小写字母开头**
- 仅含小写字母、数字、`_`、`-`
- 长度 1–64

✅ `secret://kafka_pwd`、`secret://iam_client_id`  
❌ `secret://Kafka_Pwd`（大写）、`secret://`（无名）

---

## 操作步骤

1. **数据字典** Tab → **密钥管理**
2. 创建密钥，**name** 与 YAML 中 `secret://` 后的名称一致
3. 填写明文值并保存（加密存储）
4. 在模块 YAML 引用：

```yaml
auth:
  password: secret://kafka_pwd
  client_secret: secret://iam_client_secret
```

5. 保存字典模块；对应 Profile 下连接器绑定时自动解析

---

## 运行时行为

- 字典树中 `secret://` **保持字面量**（`data_dict` 不替换）
- HTTP/Kafka 等 registry 绑定时 `resolve_secret_references` 解密
- Starlark 脚本**无**直接读取密钥的 builtin

密钥按 **Profile** 隔离（`fe_secret` 表）。

---

## 相关文档

- [模块树与 YAML](module-tree-and-yaml.md)
- [HTTP 集成](../integrations/http.md)
