# 表与行数据

## 概述

Lookup 以**命名空间（namespace）**为单位组织表格式数据。每个命名空间有 **schema**（字段定义）和 **rows**（行数据）。脚本通过 `lookup_query` 查询；测试中心用命名空间的每一行驱动一条测试用例。

---

## 界面操作

### 选择命名空间

1. 打开 **Lookup** Tab
2. 选择 **Profile**（不同环境可有不同数据）
3. 左侧列表选择或新建命名空间

### 编辑 Schema

在 **Schema** 面板定义字段：

| 属性 | 说明 |
|------|------|
| 字段名 | 列名，查询与映射时使用 |
| 类型 | string / number / boolean / json 等 |
| 必填 | 是否允许空值 |

Schema 变更后需与已有行数据兼容；删字段可能导致历史行缺列。

### 管理行数据

| 操作 | 说明 |
|------|------|
| **新增行** | 表单填写各字段 |
| **编辑行** | 修改字段值 |
| **删除行** | 移除单条记录 |
| **导入** | 支持 JSON / CSV / XLSX |
| **导出** | 导出当前命名空间数据 |

---

## 导入格式

### JSON

```json
[
  {"case_id": "c1", "input": 1, "expected": 2},
  {"case_id": "c2", "input": 5, "expected": 10}
]
```

### CSV

首行为表头，与 schema 字段对应：

```csv
case_id,input,expected
c1,1,2
c2,5,10
```

导入前确认 schema 已定义且列名匹配。

---

## 测试用例行字段

测试中心常用约定字段（非强制）：

| 字段 | 用途 |
|------|------|
| `case_id` | 用例标识 |
| `_expect` 或 `_expect.path` | 行内断言（见 [测试断言](../test-center/assertions.md)） |
| 业务字段 | 经 context_mapping（spread/wrap/rules/script）进入 `global_ns` |

详见 [测试数据与测试中心](test-data-with-test-center.md)、[上下文映射](../test-center/context-mapping.md)。

---

## record_replay 录制表

Mock `record_replay` 模式会把节点输出录制到指定 lookup 命名空间，键由 `key_expr` 计算。可在此查看/清理录制数据。

---

## 最佳实践

1. **测试数据与生产配置分离** — 使用独立命名空间，如 `test_orders` vs `prod_orders`
2. **case_id 唯一** — 便于批次结果定位失败用例
3. **版本化** — 大批量数据用导出文件纳入版本管理
4. **Profile 隔离** — 预发/生产 lookup 数据分 Profile 维护

---

## 相关文档

- [命名空间与 schema](namespace-and-schema.md)
- [脚本中的 lookup_query](lookup-in-scripts.md)
- [测试数据与测试中心](test-data-with-test-center.md)
