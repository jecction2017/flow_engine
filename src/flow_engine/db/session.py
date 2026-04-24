from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from flow_engine.db.config import get_database_url


def get_engine(*, echo: bool = False) -> Engine:
    return create_engine(get_database_url(), echo=echo, pool_pre_ping=True)
