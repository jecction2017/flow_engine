"""Structured runtime failure reports (who / when / what / how).

One universal schema for task nodes, hooks, flow-level errors, and
prepare/runtime faults. Human-readable text is derived for ``error``
columns; the dict form is persisted as ``failure_detail`` JSON.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Starlark diagnostics: `` --> task.star:2:3``
_STARLARK_LOC_RE = re.compile(
    r"^\s*-->\s+([^:\s]+):(\d+):(\d+)\s*$", re.MULTILINE
)


class FailureCategory(str, Enum):
    """Stable machine category for filtering and metrics."""

    TASK_STARLARK_SCRIPT = "task_starlark_script"
    TASK_OUTPUT_MAPPING = "task_output_mapping"
    TASK_TIMEOUT = "task_timeout"
    TASK_HOOK = "task_hook"
    LOOP_STARLARK_SCRIPT = "loop_starlark_script"
    LOOP_TIMEOUT = "loop_timeout"
    FLOW_HOOK = "flow_hook"
    FLOW_UNRESOLVED_JUMP = "flow_unresolved_jump"
    FLOW_EXECUTION = "flow_execution"
    FLOW_PREPARE = "flow_prepare"
    NODE_RETRY_EXHAUSTED = "node_retry_exhausted"


CATEGORY_LABEL_ZH: dict[FailureCategory, str] = {
    FailureCategory.TASK_STARLARK_SCRIPT: "任务节点 Starlark 脚本执行异常",
    FailureCategory.TASK_OUTPUT_MAPPING: "任务节点输出映射异常",
    FailureCategory.TASK_TIMEOUT: "任务节点执行超时",
    FailureCategory.TASK_HOOK: "任务节点钩子脚本异常",
    FailureCategory.LOOP_STARLARK_SCRIPT: "循环节点 Starlark 脚本执行异常",
    FailureCategory.LOOP_TIMEOUT: "循环节点执行超时",
    FailureCategory.FLOW_HOOK: "流程钩子脚本异常",
    FailureCategory.FLOW_UNRESOLVED_JUMP: "流程跳转目标未解析",
    FailureCategory.FLOW_EXECUTION: "流程运行异常",
    FailureCategory.FLOW_PREPARE: "流程准备异常",
    FailureCategory.NODE_RETRY_EXHAUSTED: "任务节点重试耗尽",
}


PHASE_LABEL_ZH: dict[str, str] = {
    "task_script": "任务脚本",
    "output_mapping": "输出映射",
    "pre_exec": "执行前钩子 (pre_exec)",
    "post_exec": "执行后钩子 (post_exec)",
    "on_error": "错误钩子 (on_error)",
    "on_start": "流程启动钩子 (on_start)",
    "on_complete": "流程完成钩子 (on_complete)",
    "on_failure": "流程失败钩子 (on_failure)",
    "loop_body": "循环体",
    "flow": "流程",
}


@dataclass
class FailureReport:
    """Structured failure: who / when / what / how."""

    category: str
    category_label: str
    occurred_at: str
    summary: str
    node_id: str | None = None
    node_name: str | None = None
    phase: str | None = None
    phase_label: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    source_file: str | None = None
    line: int | None = None
    column: int | None = None
    detail: str | None = None
    script_excerpt: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    cause_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FailureReport | None:
        if not data or not isinstance(data, dict):
            return None
        return cls(
            category=str(data.get("category") or FailureCategory.FLOW_EXECUTION.value),
            category_label=str(data.get("category_label") or ""),
            occurred_at=str(data.get("occurred_at") or ""),
            summary=str(data.get("summary") or ""),
            node_id=data.get("node_id"),
            node_name=data.get("node_name"),
            phase=data.get("phase"),
            phase_label=data.get("phase_label"),
            exception_type=data.get("exception_type"),
            exception_message=data.get("exception_message"),
            source_file=data.get("source_file"),
            line=data.get("line") if data.get("line") is not None else None,
            column=data.get("column") if data.get("column") is not None else None,
            detail=data.get("detail"),
            script_excerpt=data.get("script_excerpt"),
            context=dict(data.get("context") or {}),
            cause_chain=list(data.get("cause_chain") or []),
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _category_label(category: FailureCategory) -> str:
    return CATEGORY_LABEL_ZH.get(category, category.value)


def _phase_label(phase: str | None) -> str | None:
    if not phase:
        return None
    return PHASE_LABEL_ZH.get(phase, phase)


def _parse_starlark_location(detail: str) -> tuple[str | None, int | None, int | None]:
    m = _STARLARK_LOC_RE.search(detail)
    if not m:
        return None, None, None
    try:
        return m.group(1), int(m.group(2)), int(m.group(3))
    except (TypeError, ValueError):
        return m.group(1), None, None


def _cause_chain(exc: BaseException) -> list[str]:
    chain: list[str] = []
    cur: BaseException | None = exc
    while cur is not None and len(chain) < 8:
        chain.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or cur.__context__
    return chain


def _script_excerpt(script: str | None, line: int | None, *, radius: int = 2) -> str | None:
    if not script or not script.strip():
        return None
    lines = script.splitlines()
    if not lines:
        return None
    if line is None or line < 1:
        shown = lines[: min(12, len(lines))]
        body = "\n".join(f"{i + 1:4d} | {ln}" for i, ln in enumerate(shown))
        if len(lines) > len(shown):
            body += f"\n     | ... ({len(lines) - len(shown)} more lines)"
        return body
    idx = line - 1
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    parts: list[str] = []
    for i in range(start, end):
        mark = ">>>" if i == idx else "   "
        parts.append(f"{mark} {i + 1:4d} | {lines[i]}")
    return "\n".join(parts)


def failure_report_from_exception(
    exc: BaseException,
    *,
    category: FailureCategory,
    node_id: str | None = None,
    node_name: str | None = None,
    phase: str | None = None,
    summary: str | None = None,
    script: str | None = None,
    context: dict[str, Any] | None = None,
) -> FailureReport:
    """Build a report from any exception (reuses embedded report when present)."""
    from flow_engine.engine.exceptions import FlowEngineError

    if isinstance(exc, FlowEngineError):
        embedded = getattr(exc, "report", None)
        if embedded is not None:
            return embedded

    detail = str(exc).strip()
    source_file, line, column = None, None, None
    if category in (
        FailureCategory.TASK_STARLARK_SCRIPT,
        FailureCategory.LOOP_STARLARK_SCRIPT,
        FailureCategory.TASK_HOOK,
        FailureCategory.FLOW_HOOK,
    ):
        source_file, line, column = _parse_starlark_location(detail)

    summ = (summary or "").strip() or _first_line(detail) or type(exc).__name__
    return FailureReport(
        category=category.value,
        category_label=_category_label(category),
        occurred_at=utc_now_iso(),
        summary=summ,
        node_id=node_id,
        node_name=node_name,
        phase=phase,
        phase_label=_phase_label(phase),
        exception_type=type(exc).__name__,
        exception_message=detail or None,
        source_file=source_file,
        line=line,
        column=column,
        detail=detail or None,
        script_excerpt=_script_excerpt(script, line),
        context=dict(context or {}),
        cause_chain=_cause_chain(exc),
    )


def failure_report_for_output_mapping(
    *,
    node_id: str,
    node_name: str,
    missing_key: str,
    context_path: str,
    result_keys: list[str] | None = None,
) -> FailureReport:
    summary = f"任务结果缺少输出键 {missing_key!r}"
    ctx: dict[str, Any] = {
        "missing_key": missing_key,
        "context_path": context_path,
    }
    if result_keys is not None:
        ctx["result_keys"] = result_keys
    detail_lines = [
        f"输出映射：Starlark 结果键 {missing_key!r} → 上下文 {context_path!r}",
    ]
    if result_keys is not None:
        detail_lines.append(f"任务结果现有键：{', '.join(result_keys) or '(空)'}")
    return FailureReport(
        category=FailureCategory.TASK_OUTPUT_MAPPING.value,
        category_label=_category_label(FailureCategory.TASK_OUTPUT_MAPPING),
        occurred_at=utc_now_iso(),
        summary=summary,
        node_id=node_id,
        node_name=node_name,
        phase="output_mapping",
        phase_label=_phase_label("output_mapping"),
        exception_type="KeyError",
        exception_message=missing_key,
        detail="\n".join(detail_lines),
        context=ctx,
    )


def failure_report_for_prepare(
    exc: BaseException,
    *,
    flow_code: str | None = None,
    ver_no: int | None = None,
) -> FailureReport:
    ctx: dict[str, Any] = {}
    if flow_code:
        ctx["flow_code"] = flow_code
    if ver_no is not None:
        ctx["ver_no"] = ver_no
    return failure_report_from_exception(
        exc,
        category=FailureCategory.FLOW_PREPARE,
        phase="flow",
        context=ctx,
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return text.strip()


def format_failure_text(
    report: FailureReport | dict[str, Any] | None,
    *,
    include_script: bool = True,
) -> str:
    """Multi-line human-readable report for run/span error columns."""
    if report is None:
        return ""
    if isinstance(report, dict):
        parsed = FailureReport.from_dict(report)
        if parsed is None:
            return ""
        report = parsed

    lines: list[str] = [
        f"【分类】{report.category_label or report.category}",
        f"【时间】{report.occurred_at}",
    ]
    who_parts: list[str] = []
    if report.node_id:
        who_parts.append(f"节点ID: {report.node_id}")
    if report.node_name and report.node_name != report.node_id:
        who_parts.append(f"显示名: {report.node_name}")
    if who_parts:
        lines.append(f"【节点】{' · '.join(who_parts)}")
    if report.phase_label or report.phase:
        lines.append(f"【阶段】{report.phase_label or report.phase}")
    lines.append(f"【摘要】{report.summary}")

    if report.context:
        ctx_lines = []
        for k, v in report.context.items():
            if v is None:
                continue
            if isinstance(v, list):
                ctx_lines.append(f"  {k}: {', '.join(str(x) for x in v)}")
            else:
                ctx_lines.append(f"  {k}: {v}")
        if ctx_lines:
            lines.append("【上下文】")
            lines.extend(ctx_lines)

    if report.exception_type:
        loc = ""
        if report.source_file and report.line:
            col = f":{report.column}" if report.column else ""
            loc = f" ({report.source_file}:{report.line}{col})"
        lines.append(
            f"【异常】{report.exception_type}{loc}"
            + (f": {report.exception_message}" if report.exception_message else "")
        )

    if report.detail and report.detail != report.summary:
        lines.append("【详情】")
        lines.append(report.detail)

    if include_script and report.script_excerpt:
        lines.append("【脚本摘录】")
        lines.append(report.script_excerpt)

    if report.cause_chain and len(report.cause_chain) > 1:
        lines.append("【因果链】")
        for i, item in enumerate(report.cause_chain, 1):
            lines.append(f"  {i}. {item}")

    return "\n".join(lines)


def format_failure_summary_line(report: FailureReport | dict[str, Any] | None) -> str:
    """Compact one-line summary for span rows and list cells."""
    if report is None:
        return ""
    if isinstance(report, dict):
        parsed = FailureReport.from_dict(report)
        if parsed is None:
            return ""
        report = parsed
    parts = [report.category_label or report.category]
    if report.node_id:
        label = report.node_name or report.node_id
        parts.append(f"节点 {label}")
    parts.append(report.summary)
    return " | ".join(parts)


def failure_text_from_run_result(
    *,
    message: str | None,
    failure_report: dict[str, Any] | None,
    failed_node_ids: list[str] | None = None,
    state_value: str = "FAILED",
) -> str:
    """Resolve run-level error text from structured + legacy fields."""
    if failure_report:
        return format_failure_text(failure_report)
    msg = (message or "").strip()
    if msg and "FlowState." not in msg:
        return msg
    if failed_node_ids:
        return f"Flow failed at node(s): {', '.join(failed_node_ids)}"
    return state_value
