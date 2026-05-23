# Kafka 本地联调：`simple_alarms`

适用于本机 Kafka **2.7**，地址 `localhost:9092`，与 flow-engine 统一 Kafka 连接器（`middleware.kafka` + `kafka_receive` / `kafka_send`）。

## 前置

1. 启动 Kafka（Zookeeper + Broker，或 KRaft 模式下的 broker）。
2. flow-engine 安装 Kafka 依赖：

```powershell
cd E:\cursor\flow_engine
pip install aiokafka
# 或: pip install -e ".[integrations]"
```

3. 在**数据字典**中新增模块（运维中心 → 字典配置 → 新建模块）：
   - **module_code**: `middleware.kafka`
   - **内容**: 复制 [`dict.middleware.kafka.yaml`](dict.middleware.kafka.yaml) 全文

---

## 1. Kafka 命令行操作（Windows）

在 PowerShell 中执行（路径按你的安装目录调整）：

```powershell
$KAFKA = "E:\software\kafka\bin\windows"
cd $KAFKA
```

### 创建 Topic

```powershell
.\kafka-topics.bat --create --topic simple_alarms --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

若已存在会报错，可先查看列表：

```powershell
.\kafka-topics.bat --list --bootstrap-server localhost:9092
```

### 发送测试消息（控制台生产者）

每条消息**一行 JSON**（不要换行）：

```powershell
.\kafka-console-producer.bat --bootstrap-server localhost:9092 --topic simple_alarms
```

在 `>` 提示符后粘贴并回车（可发多条）：

```text
{"id": "2026040101", "activity_level": "low", "activity_feature": "app_type_01"}
{"id": "2026040102", "activity_level": "high", "activity_feature": "app_type_02"}
```

`Ctrl+C` 退出生产者。

也可使用本目录脚本批量发送（推荐 Python，更可靠）：

```powershell
cd E:\cursor\flow_engine\examples\kafka_simple_alarms
python send_sample_alarms.py
```

或使用 PowerShell（部分 Kafka 版本需交互输入，失败时请用手动生产者）：

```powershell
.\send_sample_alarms.ps1
```

### 验证消费（控制台消费者）

**新开一个** PowerShell 窗口：

```powershell
cd E:\software\kafka\bin\windows
.\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic simple_alarms --from-beginning --group flow-console-verify
```

应能看到刚才发送的 JSON 行。

---

## 2. 数据字典 ID 对照

| 用途 | ID |
|------|-----|
| 消费（脚本 / 订阅） | `local.simple_alarms.demo_consumer` |
| 生产 | `local.simple_alarms.demo_producer` |

配置文件：[`dict.middleware.kafka.yaml`](dict.middleware.kafka.yaml)

---

## 3. flow-engine 测试方式

### A. 测试中心 — 单节点 Starlark 脚本

1. 确保字典模块 `middleware.kafka` 已保存并 **resolve** 可见。
2. 打开测试中心，粘贴 [`starlark_kafka_receive_test.star`](starlark_kafka_receive_test.star) 内容执行（DEBUG 模式会抑制网络调用，请用 **production** 或关闭 integration 抑制策略）。
3. 执行前先用上文命令向 `simple_alarms` 写入至少一条消息。

### B. 示例流程

导入/加载 [`flow_kafka_simple_alarms.yaml`](flow_kafka_simple_alarms.yaml)，在测试中心对该流程做一次运行（同样需先往 topic 发消息）。

### C. 消息触发部署（可选）

```json
{
  "schema_version": 1,
  "subscription": {
    "consumer_id": "local.simple_alarms.demo_consumer",
    "start_position": "earliest"
  },
  "consumption": {
    "batch_max_records": 10,
    "poll_timeout_ms": 2000
  },
  "dispatch": { "max_in_flight": 4 },
  "parse": {
    "codec": "json",
    "transform": "mapping",
    "mapping": { "mode": "spread" }
  },
  "ingress_policy": { "max_restarts": 3, "restart_backoff_s": 15 }
}
```

消息体会 spread 到 `$.global`，字段 `id`、`activity_level`、`activity_feature` 可直接在流程节点中使用。

---

## 4. 常见问题

| 现象 | 处理 |
|------|------|
| `INTEGRATION_UNAVAILABLE` | `pip install aiokafka`，重启 flow-api / flow-worker |
| `receive` 返回空列表 | 先 `kafka_receive(..., strategy="earliest")` 或确保 topic 有新消息；检查 consumer group 是否已消费过 |
| 连接失败 | 确认 broker 监听 `localhost:9092`，防火墙放行 |
| DEBUG 模式无结果 | integration 类 builtin 在 DEBUG 下可能被抑制，改用 production 测试 |
| `starlark budget timeout` after `kafka_receive` | 测试中心脚本总预算默认 **5s**；`timeout_ms` 不要设太大（建议 1500–2000）。可设环境变量 `FLOW_ENGINE_STARLARK_MAX_EXEC_MS=15000` 后重启 flow-api |
