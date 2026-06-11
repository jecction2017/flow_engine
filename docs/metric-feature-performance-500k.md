# Metric Feature 50 万级数据性能设计

面向 ES 等场景一次拉取约 **50 万条** 时的通用性能方案，目标是在不牺牲“在线自定义业务处理逻辑与规则 DSL”的前提下，稳定降低 CPU/内存与尾延迟。

## 0. 设计边界（必须满足）

- 不把业务判断硬编码进 `metric_feature` 通用核心。
- 保持在线页面的自定义能力：业务脚本、场景字典、规则 DSL 语义不变。
- 性能能力以下沉“运行机制”实现，不改变用户表达层（DSL）模型。

## 1. 当前瓶颈画像（50w 典型）

- `es_scroll` 当前是“分页拉取 + 内存汇总”，不是流式消费。
- 场景脚本常见痛点：
  - 大列表反复拼接（高拷贝）。
  - side 查询与主数据同批在内存聚合。
- 计算阶段仍是“全量行入内存 -> 分组聚合 -> 规则”，50w 上限易受机器规格影响。

## 2. P0（立即落地，低风险）

### 2.1 fetch

- 使用 `es_scroll`，每页 **5k~10k**，并校验 `_scroll_truncated`。
- 对主查询与 side 查询启用 `_source` 字段裁剪，避免无效字段传输。
- 明确配置 `max_scroll_pages`：按 `目标条数 / 每页大小` 计算安全余量。

### 2.2 normalize（脚本层）

- 保持频次字段 map 形态，禁止展开重复 list。
- 使用 append 风格构建列表，避免 `a = a + [x]` 的重复拷贝。
- 统一输出带权行（`weight_field`）并避免构建重复 dataset 副本。

### 2.3 compute

- 维持 `optimize_dataset="auto"`，在大数据量时避免无收益二次复制。
- 优先使用 Polars 快路径支持的指标算子。

## 3. P1（核心收益阶段：分批聚合 + 共享扫描）

P1 的目标是把“全量驻留”改成“可合并状态”，将 50w 计算从“内存主导”转为“CPU 主导可控”。

### 3.1 分批聚合（引擎机制增强，业务无感）

新增引擎内聚合状态接口（示意）：

- `start_aggregate(metric_plan)`：初始化聚合状态
- `accumulate_rows(state, rows_chunk)`：增量累计一批 rows
- `merge_state(state_a, state_b)`：可并行合并
- `finalize_snapshots(state, feature_plan, rules)`：产出快照与命中

业务层仍传 `MetricPlan/FeaturePlan/RuleDefinition`，DSL 不变。

### 3.2 多场景共享扫描

同一份 rows 同时服务 `detail` / `subject` 场景：

- 一次遍历，维护多套 group_by 聚合状态
- 避免 dataset 被重复扫描与重复分组

### 3.3 兼容策略

- 保留现有 `run_pipeline` 全量模式作为默认兼容路径。
- 新增可选运行模式（例如 `compute_mode="streaming"`），灰度开启。

## 4. P2（可选增强）

- 将高频场景 normalize/enrich 下沉为 Python builtin（替代脚本热点循环）。
- 支持 side 查询结果缓存（短 TTL），降低重复网络开销。
- 对超大高基数字段引入近似聚合策略（需业务显式启用）。

## 5. 编排建议（不侵入业务表达）

- 流程节点最小化：`fetch -> enrich -> normalize -> pipeline`。
- 中间大对象不写入全局，只输出最终结构化结果与诊断字段。
- 文案渲染与计算解耦，不进入性能关键路径。

## 6. 验收口径（SLO）

### 6.1 指标分层

- `compute-only`（不含 ES 网络）：
  - 10w / 30w / 50w 各跑 3 次，关注 P50/P95。
- `end-to-end`（含查询）：
  - 同样规模下记录总耗时、峰值内存、截断率。

### 6.2 建议目标

- `compute-only`：50w P95 <= 5s（当前阶段目标）
- `end-to-end`：按环境网络条件单独设目标，不与 compute 混算

## 7. 实施顺序建议

1. P0 全量完成并作为基线版本。  
2. 落地 P1 的聚合状态接口（先单场景，再多场景共享扫描）。  
3. 灰度开启 streaming 模式，对比全量模式结果一致性与性能收益。  
4. 达标后再考虑 P2 下沉与缓存优化。
