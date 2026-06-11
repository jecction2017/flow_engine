# Profile 管理

## 概述

**Profile（环境）** 是配置隔离的单元：数据字典覆盖、Lookup 数据、各运行模式的系统能力策略。试运行、测试、部署时选择 Profile，即选择一整套环境配置。

在 **环境配置** Tab 管理 Profile 列表与策略。

---

## 基本操作

### 新增 Profile

1. 环境配置 → **新增 Profile**
2. 输入 **Profile 代码**（如 `staging`、`prod`）与显示名
3. 保存

### 设置默认 Profile

将常用环境设为 **默认 Profile**，试运行等界面默认选中，减少每次手动选择。

### 删除 Profile

删除前确认无部署、测试方案硬编码依赖该 Profile。删除后相关字典与 lookup 数据按系统策略处理（通常一并清理或孤立）。

---

## 系统能力策略

每个 Profile 可分别配置三种运行模式的 **系统能力策略**（`system_capability_policy`）：

| 模式段 | 生效场景 |
|--------|----------|
| **debug** | 试运行、节点调试、脚本调试、测试（服务端均锁定 debug） |
| **shadow** | shadow 模式部署 |
| **production** | production 模式部署 |

### 配置步骤

1. 环境配置 → 选择 Profile
2. 打开 **系统能力策略** 编辑器
3. 选择模式段（debug / shadow / production）
4. 填写规则 JSON 数组
5. 保存

### 示例：生产默认允许 HTTP，调试默认抑制

**debug 段**（可为空，依赖 RunMode 硬编码默认抑制）：

```json
[]
```

**production 段**：

```json
[
  {"builtin_category": "integration", "action": "allow"},
  {"builtin_name": "user_delete", "action": "suppress"}
]
```

规则格式见 [规则 JSON](../capability-policy/policy-rules-json.md)。

---

## Profile 与其它模块的关系

```
Profile
 ├── 数据字典（模块 YAML 覆盖）
 ├── Lookup（命名空间行数据）
 ├── 系统能力策略（debug/shadow/production）
 └── 被引用方：试运行、测试方案、部署（env_profile_code）
```

修改 Profile 的配置**立即影响**后续运行，无需重新提交流程版本（流程定义本身未变）。

---

## 环境规划建议

| Profile | 典型用途 |
|---------|----------|
| `default` / `dev` | 本地开发，字典指向 Mock |
| `staging` | 预发联调，shadow 部署 |
| `prod` | 生产，严格能力策略 |

避免在 production Profile 的 debug 段误配 allow 全量集成（测试入口固定 debug，会读取 debug 段策略 + 硬编码默认）。

---

## 相关文档

- [环境基础](profile-basics.md)
- [系统能力策略](system-capability-policy.md)
- [环境覆盖](../data-dictionary/profile-overlays.md)
- [各层优先级](../capability-policy/layer-priority.md)
