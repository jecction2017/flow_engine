"""CLI: poll ``GET /api/test-batches/{id}`` until the batch finishes; exit code reflects outcome.

Exit 0: batch completed, ``error_runs == 0``, and no assertion verdict failures.
Exit 1: HTTP/poll error, batch failed, or any assertion verdict fail count > 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def main() -> None:
    p = argparse.ArgumentParser(description="Wait for a test batch and report pass/fail.")
    p.add_argument("batch_id", type=int, help="fe_flow_test_batch.id")
    p.add_argument(
        "--base-url",
        default=os.environ.get("FLOW_ENGINE_URL", "http://127.0.0.1:8000").rstrip("/"),
        help="API base (default: FLOW_ENGINE_URL or http://127.0.0.1:8000)",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="Seconds between polls (default: 3)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="Max seconds (0 = no limit)",
    )
    args = p.parse_args()
    url = f"{args.base_url}/api/test-batches/{args.batch_id}"
    start = time.monotonic()
    last: dict | None = None
    while True:
        if args.timeout > 0 and (time.monotonic() - start) > args.timeout:
            print("timeout waiting for batch", file=sys.stderr)
            sys.exit(1)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                last = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        status = str(last.get("status") or "")
        if status != "running":
            break
        time.sleep(max(0.5, args.interval))

    assert last is not None
    err = int(last.get("error_runs") or 0)
    summ = last.get("summary") or {}
    vc = summ.get("verdict_counts") or {}
    vfail = int(vc.get("fail") or 0)
    ok = status == "completed" and err == 0 and vfail == 0
    print(json.dumps({"batch_id": args.batch_id, "ok": ok, "detail": last}, indent=2, default=str))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
