"""DML MCP tool (INSERT / UPDATE / DELETE)."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from flow_engine.mcp_mysql.dml_validation import validate_dml_statement


def _dml_disabled() -> bool:
    v = os.environ.get("MYSQL_DML_DISABLE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def register_dml_tools(app: FastMCP) -> None:
    @app.tool(
        name="dml_execute",
        description=(
            "Run exactly one INSERT, UPDATE, or DELETE on MySQL. Returns JSON with rowcount and optional lastrowid. "
            "Not for SELECT/DDL. Disabled when env MYSQL_DML_DISABLE=1."
        ),
        annotations=ToolAnnotations(
            title="Execute DML",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    def dml_execute(statement: str) -> str:
        if _dml_disabled():
            return json.dumps({"ok": False, "error": "MYSQL_DML_DISABLE is set; DML MCP is disabled."})

        ok, err = validate_dml_statement(statement)
        if not ok:
            return json.dumps({"ok": False, "error": err})

        try:
            from sqlalchemy import text
            from flow_engine.db.session import get_engine
        except ImportError as e:
            return json.dumps({"ok": False, "error": f"Missing dependencies: {e}"})

        engine = get_engine()
        stmt = statement.strip()
        if stmt.endswith(";"):
            stmt = stmt[:-1].rstrip()

        try:
            with engine.begin() as conn:
                result = conn.execute(text(stmt))
                payload: dict = {"ok": True, "rowcount": result.rowcount}
                if result.lastrowid is not None:
                    payload["lastrowid"] = int(result.lastrowid)
                return json.dumps(payload, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
