#!/usr/bin/env python3
"""Create placeholder guide markdown files (idempotent)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs" / "guide"

STUBS: dict[str, list[str]] = {
    "getting-started": [
        "index.md",
        "install-and-access.md",
        "first-trial-run.md",
        "first-script-and-debug.md",
        "first-deployment.md",
        "first-test-plan.md",
    ],
    "flow-studio": [
        "index.md",
        "read-flow-topology.md",
        "trial-run.md",
        "failure-reports.md",
        "flow-versioning.md",
        "node-types.md",
        "execution-strategies.md",
        "boundaries-and-context.md",
        "hooks-on-error-and-cache.md",
        "node-debug.md",
    ],
    "capability-center": [
        "index.md",
        "scripts-in-flows.md",
        "user-scripts.md",
        "python-builtins.md",
        "internal-starlib.md",
        "script-debug.md",
    ],
    "scripting": [
        "index.md",
        "quick-start.md",
        "syntax-essentials.md",
        "builtins-overview.md",
        "load-and-modules.md",
        "context-and-flow-control.md",
    ],
    "scripting/recipes": [
        "soc-alert-handling.md",
        "http-and-lookup.md",
    ],
    "capability-policy": [
        "index.md",
        "why-calls-are-suppressed.md",
        "side-effects.md",
        "default-behavior.md",
        "policy-rules-json.md",
        "layer-priority.md",
        "trial-debug-and-test.md",
        "deployment-and-run-modes.md",
        "faq.md",
    ],
    "test-center": [
        "index.md",
        "plans-and-batches.md",
        "acceptance-and-results.md",
        "assertions.md",
        "mock-and-replay.md",
        "context-mapping.md",
    ],
    "operations-center": [
        "index.md",
        "deployments.md",
        "scheduling.md",
        "subscription-kafka.md",
        "workers.md",
        "monitor-runs.md",
        "spans-metrics-logs.md",
        "troubleshooting.md",
    ],
    "profiles": [
        "index.md",
        "profile-basics.md",
        "system-capability-policy.md",
        "profile-management.md",
    ],
    "data-dictionary": [
        "index.md",
        "what-is-data-dictionary.md",
        "module-tree-and-yaml.md",
        "profile-overlays.md",
        "secrets.md",
    ],
    "lookup": [
        "index.md",
        "tables-and-rows.md",
        "test-data-with-test-center.md",
        "namespace-and-schema.md",
        "lookup-in-scripts.md",
    ],
    "integrations": [
        "index.md",
        "http.md",
        "kafka.md",
        "elasticsearch.md",
        "metric-feature.md",
    ],
    "faq": [
        "index.md",
        "trial-run.md",
        "deployment.md",
        "scripting.md",
        "capability-policy.md",
        "test-assertions.md",
    ],
}

META: dict[str, dict] = {
    "getting-started": {"title": "快速上手", "order": 20},
    "flow-studio": {"title": "Flow Studio", "order": 30},
    "capability-center": {"title": "能力与脚本", "order": 40},
    "scripting": {"title": "Starlark 脚本", "order": 50},
    "capability-policy": {"title": "能力策略", "order": 60},
    "test-center": {"title": "测试中心", "order": 70},
    "operations-center": {"title": "运行中心", "order": 80},
    "profiles": {"title": "环境配置", "order": 90},
    "data-dictionary": {"title": "数据字典", "order": 100},
    "lookup": {"title": "Lookup", "order": 110},
    "integrations": {"title": "集成能力", "order": 120},
    "faq": {"title": "常见问题", "order": 130},
}


def title_from_filename(name: str) -> str:
    stem = name.removesuffix(".md")
    if stem == "index":
        return "概述"
    return stem.replace("-", " ").replace("_", " ")


def main() -> None:
    import json

    for section, files in STUBS.items():
        dir_path = ROOT / section
        dir_path.mkdir(parents=True, exist_ok=True)
        meta = META.get(section.split("/")[0], {"title": section, "order": 999})
        meta_path = dir_path / "_meta.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for fname in files:
            path = dir_path / fname
            if path.exists():
                continue
            title = title_from_filename(fname)
            path.write_text(
                f"# {title}\n\n## 概述\n\n（内容待补充）\n",
                encoding="utf-8",
            )
            print(f"created {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
