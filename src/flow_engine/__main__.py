"""CLI: python -m flow_engine path/to/flow.yaml"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from flow_engine.engine.loader import load_flow_from_yaml
from flow_engine.engine.orchestrator import FlowRuntime


async def _amain(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python -m flow_engine <flow.yaml>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    flow = load_flow_from_yaml(path)
    rt = FlowRuntime(flow)
    res = await rt.run()
    print("state:", res.state.value)
    if res.message:
        print("message:", res.message)
    print("global context:")
    print(json.dumps(res.context.global_ns, indent=2, default=str))
    return 0 if res.state.value in ("COMPLETED", "TERMINATED") else 1


def main() -> None:
    raise SystemExit(asyncio.run(_amain(sys.argv)))


if __name__ == "__main__":
    main()
