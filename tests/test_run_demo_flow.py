from flow_engine.runner.managed_runner import run_managed
import asyncio

asyncio.run(run_managed(flow_id="demo_flow", channel="latest", instance_id="test_demo_flow", initial_context = {
    "alert": {
        "id": "ALT-1",
        "severity": "HIGH",
    }
}))