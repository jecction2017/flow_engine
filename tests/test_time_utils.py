from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flow_engine.time_utils import utc_isoformat


def test_utc_isoformat_treats_naive_datetime_as_utc() -> None:
    assert utc_isoformat(datetime(2026, 5, 8, 10, 3, 4, 123000)) == "2026-05-08T10:03:04.123000Z"


def test_utc_isoformat_converts_aware_datetime_to_utc() -> None:
    tz = timezone(timedelta(hours=8))

    assert utc_isoformat(datetime(2026, 5, 8, 18, 3, 4, tzinfo=tz)) == "2026-05-08T10:03:04Z"
