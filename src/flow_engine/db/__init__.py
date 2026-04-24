"""Local MySQL helpers (requires ``pip install -e ".[mysql]"`` for ORM pieces)."""

from __future__ import annotations

from typing import Any

from flow_engine.db.config import get_database_url

__all__ = ["get_database_url", "Base", "get_engine"]


def __getattr__(name: str) -> Any:
    if name == "Base":
        from flow_engine.db.models import Base

        return Base
    if name == "get_engine":
        from flow_engine.db.session import get_engine

        return get_engine
    raise AttributeError(name)
