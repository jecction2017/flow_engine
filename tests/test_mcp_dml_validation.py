from __future__ import annotations

import pytest

from flow_engine.mcp_mysql.dml_validation import validate_dml_statement


@pytest.mark.parametrize(
    "sql,expect_ok",
    [
        ("INSERT INTO users (email, password_hash) VALUES ('a@b.c','x')", True),
        ("UPDATE users SET display_name = 'x' WHERE id = 1", True),
        ("DELETE FROM users WHERE id = 99", True),
        ("  insert into t (a) values (1)  ", True),
        ("SELECT * FROM users", False),
        ("DROP TABLE users", False),
        ("INSERT INTO t VALUES (1); DELETE FROM t", False),
        ("UPDATE users SET x = 1 -- hack", False),
        ("", False),
    ],
)
def validate_dml_statement_cases(sql: str, expect_ok: bool) -> None:
    ok, err = validate_dml_statement(sql)
    assert ok == expect_ok, err


def test_literal_hides_drop_keyword() -> None:
    ok, _ = validate_dml_statement(
        "INSERT INTO users (email, password_hash) VALUES ('evil@x.com', 'drop table')"
    )
    assert ok
