"""Read-side MCP tools (SELECT + schema_info)."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy import text

from flow_engine.mcp_mysql.read_validation import (
    sanitize_schema_keyword,
    validate_schema_table_name,
    validate_select_statement,
)


def _read_disabled() -> bool:
    v = os.environ.get("MYSQL_READ_DISABLE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _max_rows() -> int:
    raw = os.environ.get("MYSQL_READ_MAX_ROWS", "2000").strip()
    try:
        n = int(raw)
    except ValueError:
        return 2000
    return max(1, min(n, 50_000))


def register_read_tools(app: FastMCP) -> None:
    @app.tool(
        name="select_execute",
        description=(
            "Run exactly one SELECT on MySQL. Returns JSON with rows (list of objects), row count, "
            "and optional truncated flag if MYSQL_READ_MAX_ROWS was exceeded. Not for INSERT/UPDATE/DELETE/DDL."
        ),
        annotations=ToolAnnotations(
            title="Execute SELECT",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    def select_execute(query: str) -> str:
        if _read_disabled():
            return json.dumps({"ok": False, "error": "MYSQL_READ_DISABLE is set; read MCP is disabled."})

        ok, err = validate_select_statement(query)
        if not ok:
            return json.dumps({"ok": False, "error": err})

        try:
            from flow_engine.db.session import get_engine
        except ImportError as e:
            return json.dumps({"ok": False, "error": f"Missing dependencies: {e}"})

        engine = get_engine()
        stmt = query.strip()
        if stmt.endswith(";"):
            stmt = stmt[:-1].rstrip()

        cap = _max_rows()
        try:
            with engine.connect() as conn:
                result = conn.execute(text(stmt))
                keys = list(result.keys())
                batch = result.fetchmany(cap + 1)
                truncated = len(batch) > cap
                rows_batch = batch[:cap]
                rows = [dict(zip(keys, row, strict=True)) for row in rows_batch]
                out_rows = [{k: v for k, v in r.items()} for r in rows]
                return json.dumps(
                    {
                        "ok": True,
                        "rowcount": len(out_rows),
                        "truncated": truncated,
                        "rows": out_rows,
                    },
                    default=str,
                )
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @app.tool(
        name="schema_info",
        description=(
            "Inspect database schema: list tables in the current database, filter by optional keyword, "
            "or get column details for one table (table_name). Uses information_schema."
        ),
        annotations=ToolAnnotations(
            title="Database schema",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def schema_info(table_name: str | None = None, keyword: str | None = None) -> str:
        if _read_disabled():
            return json.dumps({"ok": False, "error": "MYSQL_READ_DISABLE is set; read MCP is disabled."})

        if table_name is not None and table_name.strip():
            ok, err = validate_schema_table_name(table_name)
            if not ok:
                return json.dumps({"ok": False, "error": err})
            tname = table_name.strip()
            sql = text(
                """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY,
                       COLUMN_DEFAULT, EXTRA, ORDINAL_POSITION
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
                ORDER BY ORDINAL_POSITION
                """
            )
            try:
                from flow_engine.db.session import get_engine

                with get_engine().connect() as conn:
                    result = conn.execute(sql, {"t": tname})
                    cols = [dict(row._mapping) for row in result]
                if not cols:
                    return json.dumps(
                        {
                            "ok": True,
                            "table": tname,
                            "columns": [],
                            "note": "No columns found (unknown table or empty).",
                        }
                    )
                return json.dumps({"ok": True, "table": tname, "columns": cols}, default=str)
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})

        if keyword is not None and keyword.strip():
            kw, err = sanitize_schema_keyword(keyword)
            if err:
                return json.dumps({"ok": False, "error": err})
            assert kw is not None
            pat = f"%{kw}%"
            sql = text(
                """
                SELECT TABLE_NAME, TABLE_TYPE
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_TYPE = 'BASE TABLE'
                  AND TABLE_NAME LIKE :pat
                ORDER BY TABLE_NAME
                """
            )
            try:
                from flow_engine.db.session import get_engine

                with get_engine().connect() as conn:
                    result = conn.execute(sql, {"pat": pat})
                    tables = [dict(row._mapping) for row in result]
                return json.dumps({"ok": True, "tables": tables}, default=str)
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})

        sql = text(
            """
            SELECT TABLE_NAME, TABLE_TYPE
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """
        )
        try:
            from flow_engine.db.session import get_engine

            with get_engine().connect() as conn:
                result = conn.execute(sql)
                tables = [dict(row._mapping) for row in result]
            return json.dumps({"ok": True, "tables": tables}, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
