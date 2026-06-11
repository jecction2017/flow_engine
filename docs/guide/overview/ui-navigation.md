# 界面与文档对照

## 主界面 Tab 与文档章节

主界面顶部 8 个 Tab 与帮助文档章节的对应关系：

| 主界面 Tab | 主要功能 | 文档章节 |
|------------|----------|----------|
| **Flow Studio** | 流程设计、节点编辑、试运行、版本管理 | [flow-studio](../flow-studio/index.md) |
| **运行中心** | 部署管理、运行记录、工作节点 | [operations-center](../operations-center/index.md) |
| **测试中心** | 测试方案、批次运行、断言与 Mock | [test-center](../test-center/index.md) |
| **能力与脚本** | 用户脚本 CRUD、Python/Starlark 内置浏览 | [capability-center](../capability-center/index.md) + [scripting](../scripting/index.md) |
| **环境配置** | Profile 管理、各模式能力策略 | [profiles](../profiles/index.md) |
| **数据字典** | YAML 模块树编辑、密钥管理 | [data-dictionary](../data-dictionary/index.md) |
| **Lookup** | 命名空间、schema、行数据、导入导出 | [lookup](../lookup/index.md) |
| **帮助文档** | 本站点（左侧目录 + 全文搜索） | 当前页面 |

---

## Flow Studio 布局

三栏结构：

| 区域 | 内容 |
|------|------|
| **左侧** | 流程选择器、节点拓扑树（搜索、添加 task/loop/subflow） |
| **中间** | 流程元数据编辑器（选中根节点）或节点编辑器（选中子节点） |
| **右侧** | 试运行面板（节点时间线、日志、失败报告） |

辅助面板：节点调试抽屉、YAML 导入/导出。

---

## 运行中心子 Tab

| 子 Tab | 内容 |
|--------|------|
| **部署管理** | 创建/编辑/启停部署，查看 Kafka 订阅消息 |
| **运行记录** | 部署运行与测试运行的历史，钻取 Spans/指标/日志 |
| **工作节点** | Worker 心跳、状态、分配情况 |

---

## 测试中心布局

| 区域 | 内容 |
|------|------|
| **方案列表** | 测试方案 CRUD、复制、运行 |
| **方案编辑** | 流程绑定、lookup 命名空间、context_mapping、assertions、mock_config |
| **批次与结果** | 批次运行、逐用例 verdict、失败详情 |

---

## 能力与脚本分段

| 分段 | 内容 |
|------|------|
| **用户脚本** | 模块/脚本 CRUD、调试面板 |
| **Python 内置** | 注册表浏览、参数签名、副作用标记（编辑器自动补全来源） |
| **Starlark 内置** | 只读 `internal://` 库浏览 |

---

## 跨模块专题

以下主题横跨多个 Tab，有独立文档章节：

| 专题 | 文档 | 何时查阅 |
|------|------|----------|
| **能力策略** | [capability-policy](../capability-policy/index.md) | 调试时 HTTP 没发出、测试要 Mock 集成调用 |
| **集成** | [integrations](../integrations/index.md) | 配置 HTTP/Kafka/ES、编写集成脚本 |
| **脚本语法** | [scripting](../scripting/index.md) | Starlark 语法约束、load 模块、流程控制 |
| **常见问题** | [faq](../faq/index.md) | 按主题快速排查 |

---

## 帮助文档站内导航

- **左侧目录**：与 `docs/guide/` 文件夹结构一致，`_meta.json` 控制排序与标题。
- **顶部搜索框**：跨章节全文检索（至少 2 个字符），结果含标题、面包屑与摘要片段。
- **文内链接**：点击跳转到同站其它章节（相对路径 `.md` 链接）。

---

## 相关文档

- [平台简介](what-is-flow-engine.md)
- [核心概念](core-concepts.md)
