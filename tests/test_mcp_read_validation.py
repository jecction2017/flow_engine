from __future__ import annotations

import pytest

from flow_engine.mcp_mysql.read_validation import (
    sanitize_schema_keyword,
    validate_schema_table_name,
    validate_select_statement,
)


@pytest.mark.parametrize(
    "sql,expect_ok",
    [
        ("SELECT * FROM users LIMIT 10", True),
        ("  select id from users where id = 1  ", True),
        ("INSERT INTO t VALUES (1)", False),
        ("DROP TABLE users", False),
        ("SELECT * FROM t; DELETE FROM t", False),
        ("SELECT * FROM t -- x", False),
        ("", False),
        ("UPDATE users SET x = 1", False),
    ],
)
def test_validate_select_statement(sql: str, expect_ok: bool) -> None:
    ok, err = validate_select_statement(sql)
    assert ok == expect_ok, err


def test_select_literal_hides_forbidden_keyword() -> None:
    ok, _ = validate_select_statement("SELECT 'into outfile' AS x")
    assert ok


@pytest.mark.parametrize(
    "name,expect_ok",
    [
        ("users", True),
        ("User_01", True),
        ("bad-name", False),
        ("", False),
    ],
)
def test_validate_schema_table_name(name: str, expect_ok: bool) -> None:
    ok, err = validate_schema_table_name(name)
    assert ok == expect_ok, err


def test_sanitize_schema_keyword() -> None:
    k, err = sanitize_schema_keyword("user")
    assert err is None and k == "user"
    _, err2 = sanitize_schema_keyword("x;--")
    assert err2 is not None
