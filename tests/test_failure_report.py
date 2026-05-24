"""Structured failure report formatting."""

from __future__ import annotations

import starlark as sl

from flow_engine.engine.failure_report import (
    FailureCategory,
    failure_report_for_output_mapping,
    failure_report_from_exception,
    format_failure_text,
)


def test_starlark_error_includes_line_and_excerpt() -> None:
    script = 'x = 1\ny = undef.foo\n'
    try:
        mod = sl.Module()
        ast = sl.parse("task.star", script)
        sl.eval(mod, ast, sl.Globals.standard())
    except sl.StarlarkError as e:
        report = failure_report_from_exception(
            e,
            category=FailureCategory.TASK_STARLARK_SCRIPT,
            node_id="task_a",
            node_name="告警处理",
            phase="task_script",
            script=script,
        )
    else:
        raise AssertionError("expected StarlarkError")

    text = format_failure_text(report)
    assert "任务节点 Starlark 脚本执行异常" in text
    assert "task_a" in text
    assert "告警处理" in text
    assert "task_script" in report.phase or "任务脚本" in (report.phase_label or "")
    assert report.line == 2
    assert report.script_excerpt is not None
    assert "undef" in report.script_excerpt


def test_output_mapping_report() -> None:
    report = failure_report_for_output_mapping(
        node_id="map_out",
        node_name="输出映射",
        missing_key="alarm_id",
        context_path="$.global.alarm_id",
        result_keys=["ok"],
    )
    text = format_failure_text(report)
    assert "输出映射" in text
    assert "alarm_id" in text
    assert "map_out" in text
