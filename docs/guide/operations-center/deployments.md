# 部署管理

## 概述

在 **运行中心 → 部署管理** 创建与维护部署：把流程**已提交版本**绑定到 Profile、运行模式、调度方式与 Worker 策略，由后台 Worker 拉取执行。**生产环境的真实行为通过部署产生**，而非试运行入口。

---

## 创建部署

### 操作步骤

1. 运行中心 → **部署管理** → **新建部署**
2. 填写基本信息：
   - **名称** — 部署标识
   - **流程** — 选择目标流程
   - **版本** — 必须选择**已提交版本**（V1、V2…），不能选草稿
   - **Profile** — 运行环境（数据字典、lookup、系统能力策略）
   - **运行模式** — `production` 或 `shadow`
3. 配置 **部署附加策略**（`capability_policy`）— 可选，见 [能力策略](../capability-policy/index.md)
4. 配置 **调度** — 见 [调度方式](scheduling.md)
5. 配置 **Worker 策略**：
   - `single_active` — 仅一个 Worker 活跃执行
   - `multi_active` — 多 Worker 可并行（需流程支持）
   - **目标 Worker** — 指定 Worker 列表或留空自动分配
6. 保存

### 启动与停止

- 保存后部署处于配置态；在部署详情页 **启动** 后才开始按调度触发
- **停止** 后不再接收新触发（已在跑的 run 按策略完成或取消）

---

## 运行模式说明

| 模式 | 用途 |
|------|------|
| **production** | 正式生产执行，副作用按策略真实发生 |
| **shadow** | 影子运行，旁路观察、对比，常用于灰度验证 |

两者均非 debug；与试运行的 debug 锁定不同。

---

## 版本约束

| 场景 | 可用版本 |
|------|----------|
| 试运行 | 草稿或已提交版本 |
| 部署 | **仅已提交版本** |
| 测试方案 | 可绑定版本通道（如 latest Vn） |

流程修改后须 **提交新版本**，再在部署中切换版本或创建新部署。

---

## 能力策略合并

部署运行时，能力规则按层合并（高优先级覆盖低优先级）：

1. 节点 `capability_overrides`
2. 部署 `capability_policy`
3. Profile `system_capability_policy`（对应运行模式段）
4. RunMode 默认

详见 [各层优先级](../capability-policy/layer-priority.md)。

---

## 部署详情页

| 面板 | 内容 |
|------|------|
| **概览** | 状态、最近运行、配置摘要 |
| **Kafka 订阅** | 订阅部署的消息消费情况、失败消息 |
| **运行记录** | 该部署触发的历史 run |

---

## 编辑与删除

- **编辑**：可修改调度、Worker 策略、能力策略、Profile（谨慎变更生产环境）
- **删除**：删除前确认无关键运行依赖；进行中的 run 需先停止

---

## 常见问题

**Q: 下拉框没有想要的版本**  
A: 先在 Flow Studio 提交版本；草稿不能直接部署。

**Q: 部署启动后没有运行**  
A: 检查调度配置（cron 表达式、订阅 consumer）、Worker 是否在线、部署是否已启动。

**Q: shadow 和 production 区别**  
A: 主要差在 Profile 中对应模式的系统能力策略与运维用途；具体策略由环境配置决定。

---

## 相关文档

- [第一次部署](../getting-started/first-deployment.md)
- [调度方式](scheduling.md)
- [部署与运行模式](../capability-policy/deployment-and-run-modes.md)
- [Kafka 订阅部署](subscription-kafka.md)
- [工作节点](workers.md)
