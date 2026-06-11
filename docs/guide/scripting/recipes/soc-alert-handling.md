# SOC 告警处置模板

## 概述

示例：读取告警信息，查询 IOC，输出等级与处置建议。可直接在任务节点中改写。

## 示例

```python
# 告警输入（来自调试上下文）
alert = ctx_global.get("alert", {})
sev = alert.get("severity", "LOW")
ioc = alert.get("dest_ip", "")

# 查询 IOC 情报（lookup 命名空间按环境调整）
rows = lookup_query("cee", {"ioc": ioc})
hit = rows[0] if rows else {}
intel_level = hit.get("level", "unknown")

# 处置建议
if sev == "HIGH" or intel_level in ["malicious", "high"]:
    action = "escalate_and_block"
    priority = "P1"
else:
    action = "observe"
    priority = "P3"

{
    "ioc": ioc,
    "severity": sev,
    "intel_level": intel_level,
    "priority": priority,
    "action": action
}
```

## 调试上下文示例

```json
{
  "alert": {
    "severity": "HIGH",
    "src_ip": "1.2.3.4",
    "dest_ip": "198.51.100.7"
  }
}
```
