# Metric Feature 通用流水线契约

本文说明在线编排场景里，特征计算应遵循的**通用六阶段**约定。  
业务逻辑一律放在「场景数据字典 + `user://` 用户脚本」里，**不要写进 flow_engine 核心代码**。

## 六阶段分别做什么

| 阶段 | 英文名 | 干什么 |
|------|--------|--------|
| 1 | `fetch` | 从外部拉原始数据（ES、DB、MQ 等） |
| 2 | `normalize` | 把原始记录洗成统一的 `DataSet.rows` 行格式 |
| 3 | `enrich` | 按 key 关联基线/字典等 side 数据（如 URL 基线） |
| 4 | `metric` | 按 `MetricPlan` 做分组聚合，算出指标 |
| 5 | `feature` | 用表达式 DSL 从指标派生特征 |
| 6 | `rule` | 执行规则 DSL，输出结构化命中 `RuleMatch` |
| 7（可选） | `render` | 业务侧把命中结果转成文案/报告（与计算解耦） |

## 核心数据结构（运行时）

- **DataSet**：标准输入，一行一条记录
- **MetricPlan**：分组字段 + 指标定义（count/sum/ratio 等）
- **FeaturePlan**：基于指标写表达式，得到特征
- **RuleDefinition**：对指标/特征做条件判断
- **PipelineOutput**：输出 = 快照列表 + 规则命中列表

## 核心 vs 业务：谁写啥

**核心（metric_feature）负责：**

- 阶段语义、通用算子（如 `freq_map_count`、`co_occur`）
- `metric_feature_pipeline` 等 builtin

**业务方负责：**

- 数据字典：`metric_feature.scenarios.<场景名>` 下的 metric/feature/rule 配置
- `user://` 脚本：normalize、enrich、render
- 阈值、规则文案、URL 一致性等业务判断

## 性能约定（通用，不含业务）

- **禁止**把频次 map 展开成重复 list（例如 `{GET:10000}` 不要变成 1 万个 `GET`）
- 用带权行（`weight_field`）和 map 类聚合算子
- 大流量尽量合并节点，少在流程里拷贝超大中间对象
