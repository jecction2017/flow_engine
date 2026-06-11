# 指标特征流水线

## 概述

`metric_feature_*` 系列内置函数实现**通用指标/特征计算管道**：从数据集加载、规则评估、流水线编排到结果输出，可在 Starlark 脚本中组合使用，无需为每个业务场景单独开发 builtin。

业务配置（数据源、规则定义、输出契约）放在数据字典与流程脚本中；引擎提供统一的管道原语。

---

## 主要内置函数

| 函数 | 说明 |
|------|------|
| `metric_feature_compute` | 执行特征计算 |
| `rule_eval` | 规则表达式求值 |
| `pipeline` | 编排多步管道 |
| `load_dataset` / `load_rules` / `load_config` | 从字典或上下文加载配置 |
| `pipeline_contract` | 校验管道输入输出契约 |
| `enrich_dataset` | 对数据集追加衍生字段 |

完整列表与参数见 **能力与脚本 → Python 内置**，搜索 `metric_feature` 或 `pipeline`。

---

## 典型用法

```python
def run_pipeline():
    cfg = load_config("metric.feature.alert_pipeline")
    data = resolve("$.global.raw_events")
    result = metric_feature_compute(cfg, data)
    return {"features": result.get("features"), "metrics": result.get("metrics")}

run_pipeline()
```

实际参数结构取决于数据字典中的管道配置与 universal contract 定义。

---

## 配置来源

1. **数据字典**：管道定义、规则集、阈值参数
2. **Lookup 表**：可查找的维度映射、枚举配置
3. **流程上下文**：`resolve("$.global.*")` 传入的原始事件或中间结果

---

## 能力策略

部分 `metric_feature_*` 函数可能触发 `integration` 或 `dictionary` 类副作用（如加载外部数据）。在 debug 模式下按各自 `side_effects` 标记决定是否抑制。试运行时按需配置 allow 规则。

---

## 进阶

管道契约、性能调优与迁移说明见仓库设计文档：

- [metric-feature-universal-contract.md](../../metric-feature-universal-contract.md)

---

## 相关文档

- [模块树与 YAML](../data-dictionary/module-tree-and-yaml.md)
- [内置能力概览](../scripting/builtins-overview.md)
- [Python 内置](../capability-center/python-builtins.md)
