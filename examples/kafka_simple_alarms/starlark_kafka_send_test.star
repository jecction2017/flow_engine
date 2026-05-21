# 测试中心脚本：向 simple_alarms 发送一条告警（验证 kafka_send）
# producer_id: local.simple_alarms.demo_producer

PRODUCER = "local.simple_alarms.demo_producer"

payload = {
    "id": "2026040199",
    "activity_level": "low",
    "activity_feature": "app_type_01",
}

sent = kafka_send(PRODUCER, payload, "2026040199", None, None)

{
    "send_ok": "ok" in sent and sent["ok"],
    "result": sent,
}
