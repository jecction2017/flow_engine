# 测试中心 / 任务节点脚本：从 simple_alarms 有界拉取消息并汇总。
# 执行前请向 topic 写入 JSON（见 README.md）。
# consumer_id 对应 dict.middleware.kafka.yaml 中的 local.simple_alarms.demo_consumer

CONSUMER = "local.simple_alarms.demo_consumer"

# timeout_ms 建议 <= 2000；测试中心 Starlark 总预算默认 5s（FLOW_ENGINE_STARLARK_MAX_EXEC_MS）
recv = kafka_receive(CONSUMER, 10, 2000, None, "earliest")

alarms = []
errors = None
ok = False

if "ok" in recv and recv["ok"]:
    ok = True
    data = recv["data"]
    if "messages" in data:
        for m in data["messages"]:
            val = m["value"]
            alarms = alarms + [val]
else:
    if "error" in recv:
        errors = recv["error"]
    else:
        errors = {"message": "unknown receive failure"}

{
    "receive_ok": ok,
    "alarm_count": len(alarms),
    "alarms": alarms,
    "meta": recv["meta"] if "meta" in recv else {},
    "error": errors,
}
