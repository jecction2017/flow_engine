"""Timezone helpers shared by API and persistence serializers."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_isoformat(value: datetime | None) -> str | None:
    """Return an ISO-8601 UTC timestamp with an explicit ``Z`` suffix.

    MySQL returns ``DATETIME`` columns as naive ``datetime`` objects even when
    the application wrote UTC values. Treat those naive values as UTC so
    browser clients do not parse them as local wall time.
    """
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
