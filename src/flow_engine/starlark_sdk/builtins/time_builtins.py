"""Time-related Python builtins exposed to Starlark."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flow_engine.starlark_sdk.builtin_registry import BuiltinArgSpec, PythonBuiltinSpec, register_builtin

_DEFAULT_LAYOUT = "%Y-%m-%d %H:%M:%S"
_VALID_TS_UNITS = {"s", "ms"}
_VALID_DIFF_OUTPUTS = {"ms", "seconds", "minutes", "hours", "days"}


def _normalize_ts_unit(unit: str) -> str:
    val = (unit or "ms").strip().lower()
    if val not in _VALID_TS_UNITS:
        raise ValueError(f"unsupported time unit: {unit!r}, expected one of {_VALID_TS_UNITS}")
    return val


def _normalize_diff_output(out: str) -> str:
    val = (out or "seconds").strip().lower()
    if val not in _VALID_DIFF_OUTPUTS:
        raise ValueError(f"unsupported diff output: {out!r}, expected one of {_VALID_DIFF_OUTPUTS}")
    return val


_OFFSET_TZ_RE = re.compile(r"^([+-])(\d{2}):?(\d{2})$")


def _timezone_or_raise(name: str) -> tzinfo:
    tz_name = (name or "UTC").strip()
    if tz_name.upper() in {"UTC", "Z"}:
        return UTC
    m = _OFFSET_TZ_RE.match(tz_name)
    if m is not None:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        minutes = int(m.group(3))
        if hours > 23 or minutes > 59:
            raise ValueError(f"invalid timezone offset: {name!r}")
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"invalid timezone: {name!r} (IANA zone unavailable; install tzdata or use UTC/+HH:MM)"
        ) from exc


def _unit_scale(unit: str) -> int:
    return 1 if unit == "s" else 1000


def _coerce_number(value: int | float, arg_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{arg_name} must be a number, got bool")
    try:
        return float(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{arg_name} must be a number, got {type(value).__name__}") from exc


def _dt_from_ts(ts: int | float, unit: str, tz_name: str = "UTC") -> datetime:
    scale = _unit_scale(unit)
    tz = _timezone_or_raise(tz_name)
    seconds = _coerce_number(ts, "ts") / scale
    return datetime.fromtimestamp(seconds, tz=UTC).astimezone(tz)


def _parse_datetime(text: str, layout: str, tz_name: str) -> datetime:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    fmt = layout or _DEFAULT_LAYOUT
    source = text.strip()
    # Support common ISO8601 UTC suffix without forcing users to write +00:00.
    if source.endswith("Z") and ("%z" in fmt or fmt == "iso8601"):
        source = source[:-1] + "+00:00"
    if fmt == "iso8601":
        dt = datetime.fromisoformat(source)
    else:
        dt = datetime.strptime(source, fmt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_timezone_or_raise(tz_name))
    return dt


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/now",
        starlark_name="time_now",
        category="time",
        summary="获取当前 UTC 时间（ISO8601，毫秒精度，Z 后缀）",
        returns="str",
        side_effects="none",
    )
)
def time_now() -> str:
    return _to_iso_z(datetime.now(UTC))


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/now_ts",
        starlark_name="time_now_ts",
        category="time",
        summary="获取当前 UTC 时间戳，支持秒/毫秒",
        signature=(BuiltinArgSpec(name="unit", type="str", required=False),),
        returns="int",
        side_effects="none",
    )
)
def time_now_ts(unit: str = "ms") -> int:
    normalized = _normalize_ts_unit(unit)
    scale = _unit_scale(normalized)
    return int(round(datetime.now(UTC).timestamp() * scale))


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/format",
        starlark_name="time_format",
        category="time",
        summary="将时间戳格式化为目标时区字符串",
        signature=(
            BuiltinArgSpec(name="ts", type="int"),
            BuiltinArgSpec(name="layout", type="str", required=False),
            BuiltinArgSpec(name="tz", type="str", required=False),
            BuiltinArgSpec(name="unit", type="str", required=False),
        ),
        returns="str",
        side_effects="none",
    )
)
def time_format(
    ts: int | float,
    layout: str = _DEFAULT_LAYOUT,
    tz: str = "UTC",
    unit: str = "ms",
) -> str:
    normalized = _normalize_ts_unit(unit)
    dt = _dt_from_ts(ts, normalized, tz_name=tz)
    return dt.strftime(layout or _DEFAULT_LAYOUT)


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/parse",
        starlark_name="time_parse",
        category="time",
        summary="将时间字符串解析为 UTC 时间戳",
        signature=(
            BuiltinArgSpec(name="text", type="str"),
            BuiltinArgSpec(name="layout", type="str", required=False),
            BuiltinArgSpec(name="tz", type="str", required=False),
            BuiltinArgSpec(name="unit", type="str", required=False),
        ),
        returns="int",
        side_effects="none",
    )
)
def time_parse(
    text: str,
    layout: str = _DEFAULT_LAYOUT,
    tz: str = "UTC",
    unit: str = "ms",
) -> int:
    normalized = _normalize_ts_unit(unit)
    dt = _parse_datetime(text, layout or _DEFAULT_LAYOUT, tz)
    scale = _unit_scale(normalized)
    return int(round(dt.astimezone(UTC).timestamp() * scale))


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/convert_tz",
        starlark_name="time_convert_tz",
        category="time",
        summary="在时区之间转换时间字符串",
        signature=(
            BuiltinArgSpec(name="text", type="str"),
            BuiltinArgSpec(name="from_tz", type="str", required=False),
            BuiltinArgSpec(name="to_tz", type="str", required=False),
            BuiltinArgSpec(name="in_layout", type="str", required=False),
            BuiltinArgSpec(name="out_layout", type="str", required=False),
        ),
        returns="str",
        side_effects="none",
    )
)
def time_convert_tz(
    text: str,
    from_tz: str = "UTC",
    to_tz: str = "UTC",
    in_layout: str = _DEFAULT_LAYOUT,
    out_layout: str = _DEFAULT_LAYOUT,
) -> str:
    dt = _parse_datetime(text, in_layout or _DEFAULT_LAYOUT, from_tz)
    to_zone = _timezone_or_raise(to_tz)
    return dt.astimezone(to_zone).strftime(out_layout or _DEFAULT_LAYOUT)


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/add",
        starlark_name="time_add",
        category="time",
        summary="对时间戳执行加减偏移（天/小时/分钟/秒）",
        signature=(
            BuiltinArgSpec(name="ts", type="int"),
            BuiltinArgSpec(name="days", type="int", required=False),
            BuiltinArgSpec(name="hours", type="int", required=False),
            BuiltinArgSpec(name="minutes", type="int", required=False),
            BuiltinArgSpec(name="seconds", type="int", required=False),
            BuiltinArgSpec(name="unit", type="str", required=False),
        ),
        returns="int",
        side_effects="none",
    )
)
def time_add(
    ts: int | float,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
    unit: str = "ms",
) -> int:
    normalized = _normalize_ts_unit(unit)
    dt = _dt_from_ts(ts, normalized, tz_name="UTC")
    shifted = dt + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    scale = _unit_scale(normalized)
    return int(round(shifted.timestamp() * scale))


@register_builtin(
    PythonBuiltinSpec(
        id="python://time/diff",
        starlark_name="time_diff",
        category="time",
        summary="计算两个时间戳差值并按指定单位输出",
        signature=(
            BuiltinArgSpec(name="start_ts", type="int"),
            BuiltinArgSpec(name="end_ts", type="int"),
            BuiltinArgSpec(name="unit", type="str", required=False),
            BuiltinArgSpec(name="out", type="str", required=False),
        ),
        returns="float",
        side_effects="none",
    )
)
def time_diff(
    start_ts: int | float,
    end_ts: int | float,
    unit: str = "ms",
    out: str = "seconds",
) -> float:
    normalized = _normalize_ts_unit(unit)
    target = _normalize_diff_output(out)
    scale = _unit_scale(normalized)
    delta_seconds = (_coerce_number(end_ts, "end_ts") - _coerce_number(start_ts, "start_ts")) / scale
    if target == "ms":
        return delta_seconds * 1000.0
    if target == "seconds":
        return delta_seconds
    if target == "minutes":
        return delta_seconds / 60.0
    if target == "hours":
        return delta_seconds / 3600.0
    return delta_seconds / 86400.0
