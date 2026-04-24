from __future__ import annotations


def test_get_database_url_from_env_single(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://a:b@h:99/db")
    from flow_engine.db.config import get_database_url

    assert get_database_url() == "mysql+pymysql://a:b@h:99/db"


def test_get_database_url_from_mysql_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_USER", "u")
    monkeypatch.setenv("MYSQL_PASSWORD", "p@x")
    monkeypatch.setenv("MYSQL_DATABASE", "mydb")
    from flow_engine.db.config import get_database_url

    assert get_database_url() == "mysql+pymysql://u:p%40x@localhost:3307/mydb"
