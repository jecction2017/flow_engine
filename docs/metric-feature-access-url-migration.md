# Access URL 场景迁移方案（完整实施版）

本文给出 `src/flow_engine/biz/old_code.py` 到 `metric_feature` 通用流水线的可执行迁移方案，
覆盖“高性能 + 多场景 + 复杂规则计算”的落地要求。

## 一、落地文件

| 用途 | 路径 |
|------|------|
| 低内存流程编排 | `examples/example_11_access_url_metric_feature_pipeline.yaml` |
| 数据归一化脚本 | `examples/user_scripts/access_url/normalize.star` |
| 场景 DSL（detail/subject） | `examples/data_dict/metric_feature_access_url_scenarios.yaml` |
| 核心服务自适应优化 | `src/flow_engine/metric_feature/service.py` |

## 二、迁移模型（old_code -> 通用契约）

### 1) 原子指标层（normalize + enrich）

`normalize.star` 不再展开频次字典为重复 list，而是直接产出计数字段，并接入 side 查询结果：

- 状态码类：`status_2xx_count` / `status_4xx_count` / `status_500_count` / `status_401_403_count` 等
- 方法类：`post_count` / `put_delete_count` / `get_post_mix`
- 安全类：`fake_xff_count` / `is_jalor_url` / `is_external_ai` / `is_intranet_ai`
- 基线类：`latest_7d_resp_size_avg` / `url_baseline_2h` / `baseline_top_method_post` / `baseline_status_500_common`
- 爬取类：`is_batch_crawl_url`
- 一致性类：`is_alarm_url_consistent`（URL/domain/app_id 三层一致性）

side 查询输入：

- `t_url_info`：URL 侧历史基线与 app_id/top method/status
- `t_int_ip_info`：DMZ IP 集合，用于 fake xff 排除

说明：本脚本默认 `*_freq_dict` 已是对象类型（dict）。若上游仍是 JSON 字符串，请在 fetch 侧先做结构化。

### 2) 特征层（feature_dsl）

由原子指标派生复合特征：

- `is_status_jump_like`
- `is_status_pressure_like`
- `is_high_post_with_5xx_like`
- `is_method_conflict_like`
- `is_fake_xff_like`
- `is_resp_spike_like`
- `is_hotter_than_baseline_like`
- `is_alarm_url_consistent_like`

### 3) 规则层（rule_dsl）

detail + subject 两套场景各自定义规则，规则命名保持业务语义并输出结构化命中：

- detail 侧：`detail_*`（URL 粒度）
- subject 侧：`subject_*`（主体粒度）

## 三、性能优化策略（已实施）

原则：性能优化仅在场景脚本与场景 DSL 层完成，不入侵 `metric_feature` 通用核心，
确保在线页面仍可继续自定义业务数据处理与规则。

### 1) 编排层减少全局大对象

`example_11` 已改为单节点串联（fetch -> side query enrich -> normalize -> pipeline）：

- 不再把 `es_data` 与中间 dataset 反复写入全局
- 全局仅导出结构化 `findings`
- 使用单 dataset，分别跑 detail / subject 两套字典，避免重复构建两份大数据集
- 导出 `scroll_truncated` / `scroll_pages_fetched` 供调用方识别截断风险
- 主查询增加告警主体过滤（与旧逻辑一致），并对 ES 拉数做 `_source` 字段裁剪

### 2) 核心计算层自适应裁剪

`run_pipeline(... optimize_dataset="auto")` 通过 `_select_dataset_for_compute` 自动判断是否需要字段裁剪：

- 大数据量（20w/50w）且字段裁剪收益不明显时，跳过二次复制，降低内存峰值
- 裁剪收益明显时，保留 `compact_dataset_for_plan` 的吞吐优势

## 四、和 old_code 对齐范围

### 已覆盖的核心数据计算能力

- 状态码组合判定（4xx/5xx/401/403/404/413/429/421）
- 高 POST + 5xx 联动（含 baseline top method/status 排除）
- 伪造 XFF 统计（补齐 172.16~31 且支持 DMZ 排除）
- 回包长度相对 7d 基线偏离
- URL 请求量相对 2h 基线偏离
- 批量爬取 URL 模式检测
- jalor / external_ai / intranet_ai 访问标记（含 external_ai 非三环细分）
- URL 一致性判定（URL/domain/app_id 三层一致性）
- 响应长度异常 URL 分类排除（media/streaming/static/cc）

### 暂未完全等价（需要二期增强）

- 旧代码中的 URL 多样性排序策略（`duplicate_domain_count` / `duplicate_domain_crawler`）
- 部分复合阈值的精细优先级（跨规则共享上下文）

## 五、明确边界：不迁移文案渲染

本期迁移范围严格限定为“数据处理与规则计算”，不迁移实现文案渲染相关能力：

- 不提供 `render` 阶段脚本
- 不输出旧版 `abnormal_desc` 风格文本
- 只输出结构化命中结果（`findings` / `matches`）
- 文案渲染如有需求，后续由独立业务层实现，不进入 metric_feature 迁移交付

## 六、验收建议

1. 用旧告警样本跑新流程，抽样比对结构化命中（规则 id、主体、URL、分值）。
2. 对 10w/30w/50w 做压测，记录 P50/P95 与峰值内存。
3. 针对“暂未完全等价”项做二期补齐（建议先补 URL 一致性与 DMZ 排除）。
