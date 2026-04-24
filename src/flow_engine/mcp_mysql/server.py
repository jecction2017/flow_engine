"""MCP stdio server: read + DML MySQL tools in one process."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from flow_engine.mcp_mysql.dml_tools import register_dml_tools
from flow_engine.mcp_mysql.read_tools import register_read_tools

mcp = FastMCP(
    "flow-engine-mysql",
    instructions=(
        "MySQL access for the configured database (DATABASE_URL or MYSQL_*): "
        "select_execute and schema_info for reads; dml_execute for a single INSERT/UPDATE/DELETE. "
        "Set MYSQL_READ_DISABLE=1 to refuse read tools; MYSQL_DML_DISABLE=1 to refuse dml_execute."
    ),
)
register_read_tools(mcp)
register_dml_tools(mcp)


def main() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv()
    mcp.run()


if __name__ == "__main__":
    main()
