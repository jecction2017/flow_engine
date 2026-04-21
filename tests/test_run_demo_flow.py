from flow_engine.runner.managed_runner import run_managed
import asyncio

asyncio.run(run_managed(flow_id="demo_flow", channel="latest", instance_id="test_demo_flow", initial_context = {
    
  "alarms": [
    {
      "id": "2026040101",
      "activity_level": "low",
      "activity_feature": "app_type_01"
    },
    {
      "id": "2026040102",
      "activity_level": "medium",
      "activity_feature": "app_type_01"
    },
    {
      "id": "2026040103",
      "activity_level": "high",
      "activity_feature": "app_type_01"
    },
    {
      "id": "2026040104",
      "activity_level": "low",
      "activity_feature": "app_type_02"
    }
  ]

}))