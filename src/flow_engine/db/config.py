from __future__ import annotations

import os
from urllib.parse import quote_plus


def get_database_url() -> str:
    """Resolve SQLAlchemy URL for local MySQL.

    Precedence:
    1. ``DATABASE_URL`` (e.g. ``mysql+pymysql://user:pass@127.0.0.1:3306/db``)
    2. ``MYSQL_HOST``, ``MYSQL_PORT``, ``MYSQL_USER``, ``MYSQL_PASSWORD``, ``MYSQL_DATABASE``
    """
    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        return url.strip()

    host = os.environ.get("MYSQL_HOST", "127.0.0.1").strip()
    port = os.environ.get("MYSQL_PORT", "3306").strip()
    user = os.environ.get("MYSQL_USER", "root").strip()
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "flow_engine").strip()

    safe_user = quote_plus(user)
    safe_pw = quote_plus(password)
    return f"mysql+pymysql://{safe_user}:{safe_pw}@{host}:{port}/{database}"
