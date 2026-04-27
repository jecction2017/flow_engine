"""Shared pytest fixtures: in-memory SQLite DB for all tests.

每个测试函数独享一个全新的 SQLite :memory: 数据库，
通过 monkeypatch 覆盖 flow_engine.db.session._engine，
保证各 store 的单例缓存在每个 test 结束后失效。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.pool import StaticPool

import flow_engine.db.session as _session_mod
import flow_engine.lookup.lookup_store as _lookup_mod
import flow_engine.stores.data_dict as _data_dict_mod
import flow_engine.stores.profile_store as _profile_mod
from flow_engine.db.models import Base


def _patch_sqlite_type_compiler() -> None:
    """Register MySQL-specific type visitors on the SQLite type compiler
    so that create_all() works with the MySQL-dialect model column types.

    只需注册一次（模块级调用）。

    关键说明：
      - BIGINT → INTEGER：SQLite 仅对 INTEGER PRIMARY KEY 自动赋 ROWID，
        BIGINT PRIMARY KEY 无此行为，会导致 NOT NULL 约束失败。
      - TINYINT / MEDIUMTEXT → SQLite 无此类型，需 fallback。
    """
    SQLiteTypeCompiler.visit_BIGINT = lambda self, type_, **kw: "INTEGER"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_TINYINT"):
        SQLiteTypeCompiler.visit_TINYINT = lambda self, type_, **kw: "SMALLINT"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_MEDIUMTEXT"):
        SQLiteTypeCompiler.visit_MEDIUMTEXT = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_DATETIME"):
        SQLiteTypeCompiler.visit_DATETIME = lambda self, type_, **kw: "DATETIME"  # type: ignore[attr-defined]


# 在 conftest 模块加载时立即注册，确保在任何 create_all() 之前生效
_patch_sqlite_type_compiler()


def _create_sqlite_tables(engine) -> None:
    """Create tables with SQLite-compatible DDL.

    MySQL server defaults like DEFAULT CURRENT_TIMESTAMP(3) are invalid in SQLite.
    We temporarily clear them (relying on Python-side ``default=_utcnow`` instead)
    and restore afterwards so production metadata is unaffected.
    """
    cleared: list[tuple] = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.server_default is not None:
                arg = getattr(col.server_default, "arg", None)
                if arg is not None and "CURRENT_TIMESTAMP" in str(arg):
                    cleared.append((table.name, col.name, col.server_default))
                    col.server_default = None
    try:
        Base.metadata.create_all(engine)
    finally:
        for tname, cname, sd in cleared:
            Base.metadata.tables[tname].columns[cname].server_default = sd


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide an isolated in-memory SQLite database for each test.

    - Patches session._engine so all db_session() calls use SQLite.
    - Creates all fe_* tables via Base.metadata.create_all.
    - Invalidates all store singletons so each test starts clean.
    """
    # StaticPool: 所有线程共享同一个 SQLite 连接对象（:memory: DB 只在单一连接内存在）
    # check_same_thread=False: 允许 FastAPI TestClient 工作线程访问同一连接
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_sqlite_tables(engine)

    # Override the global engine singleton
    monkeypatch.setattr(_session_mod, "_engine", engine)

    # Invalidate store singletons (they hold a reference to the old state)
    _data_dict_mod._store_cache = None
    _profile_mod._store_cache = None
    _lookup_mod._store_cache = None

    import flow_engine.starlark_sdk.user_script_store as _uss_mod
    _uss_mod._store_cache = None

    # Eagerly initialize GlobalProfileStore so that 'default' profile row
    # exists in fe_env_profile before any test touches the data dict or lookup.
    _profile_mod.store()

    yield

    engine.dispose()
