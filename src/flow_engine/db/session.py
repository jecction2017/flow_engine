from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from flow_engine.db.config import get_database_url

# 全局单例 Engine（懒初始化），避免每次 db_session() 重建连接池
_engine: Engine | None = None


def get_engine(*, echo: bool = False) -> Engine:
    """Return the singleton SQLAlchemy engine (lazy-initialized).

    pool_pre_ping   每次 checkout 前 ping，自动剔除断开的连接。
    pool_recycle    3600s 强制回收连接，避开 MySQL 默认 8h 超时断链。
    """
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            echo=echo,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Yield a transactional :class:`Session`.

    - 正常退出：自动 COMMIT
    - 异常退出：自动 ROLLBACK，重新抛出异常

    Usage::

        with db_session() as s:
            row = s.get(FeFlow, flow_pk)
            s.add(FeFlow(flow_code="my-flow", ...))
    """
    with Session(get_engine()) as session:
        with session.begin():
            yield session
