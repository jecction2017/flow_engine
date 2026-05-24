"""Worker policy helpers: ``target_workers`` (legacy ``min_workers`` read compat)."""

from __future__ import annotations

from typing import Any

_VALID_TYPES = frozenset({"single_active", "multi_active"})


def target_workers_from_policy(wp: dict[str, Any] | None) -> int:
    """Return target worker count from policy JSON (legacy ``min_workers`` accepted)."""
    raw = wp if isinstance(wp, dict) else {}
    if "target_workers" in raw:
        try:
            return max(1, int(raw["target_workers"]))
        except (TypeError, ValueError):
            return 1
    if "min_workers" in raw:
        try:
            return max(1, int(raw["min_workers"]))
        except (TypeError, ValueError):
            return 1
    return 1


def policy_type_from_policy(wp: dict[str, Any] | None) -> str:
    raw = wp if isinstance(wp, dict) else {}
    t = str(raw.get("type") or "single_active").strip()
    return t if t in _VALID_TYPES else "single_active"


def normalize_worker_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Canonical worker_policy for persist and API responses; drops legacy ``min_workers``."""
    wp = dict(raw) if isinstance(raw, dict) else {}
    wp_type = policy_type_from_policy(wp)
    wp["type"] = wp_type
    wp["target_workers"] = target_workers_from_policy(wp)
    wp.pop("min_workers", None)
    if "max_restarts" not in wp:
        wp["max_restarts"] = 3
    if "restart_backoff_s" not in wp:
        wp["restart_backoff_s"] = 15
    return wp


def reject_legacy_min_workers_key(raw: dict[str, Any] | None) -> None:
    """Raise ValueError if request body still uses renamed field."""
    if isinstance(raw, dict) and "min_workers" in raw:
        raise ValueError("min_workers renamed to target_workers")
