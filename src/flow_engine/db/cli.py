"""CLI: ``flow-db`` — apply SQLAlchemy models to local MySQL."""

from __future__ import annotations

import argparse
import sys


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _cmd_apply(args: argparse.Namespace) -> int:
    _load_dotenv()
    try:
        import flow_engine.db.models  # noqa: F401 — register models on Base.metadata
        from flow_engine.db.models import Base
        from flow_engine.db.session import get_engine
    except ImportError as e:
        print("Missing mysql extras. Install: pip install -e \".[mysql]\"", file=sys.stderr)
        print(e, file=sys.stderr)
        return 1

    engine = get_engine(echo=args.echo)
    Base.metadata.create_all(bind=engine)
    names = sorted(Base.metadata.tables.keys())
    if names:
        print("Tables ensured:", ", ".join(names))
    else:
        print("No models registered on Base.metadata; add classes in flow_engine/db/models.py")
    return 0


def _cmd_url(_: argparse.Namespace) -> int:
    _load_dotenv()
    from flow_engine.db.config import get_database_url

    try:
        from sqlalchemy.engine.url import make_url
    except ImportError:
        print("Install mysql extras: pip install -e \".[mysql]\"", file=sys.stderr)
        return 1
    print(make_url(get_database_url()).render_as_string(hide_password=True))
    return 0


def _cmd_migrate_data(args: argparse.Namespace) -> int:
    _load_dotenv()
    try:
        from flow_engine.db.migrate_data import migrate_all_data
    except ImportError as e:
        print("Missing mysql extras. Install: pip install -e \".[mysql]\"", file=sys.stderr)
        print(e, file=sys.stderr)
        return 1

    stats = migrate_all_data(args.data_dir)
    ordered_keys = [
        "profiles",
        "dict_modules",
        "flows",
        "flow_versions",
        "flow_drafts",
        "lookup_tables",
        "lookup_rows",
        "user_scripts",
    ]
    print("Data migration completed.")
    for k in ordered_keys:
        if k in stats:
            print(f"  - {k}: {stats[k]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flow-db", description="Local MySQL schema (SQLAlchemy create_all)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_apply = sub.add_parser("apply", help="CREATE TABLE for all models (idempotent for new tables)")
    p_apply.add_argument("--echo", action="store_true", help="Log SQL to stdout")
    p_apply.set_defaults(func=_cmd_apply)

    p_url = sub.add_parser("url", help="Print resolved DB URL with password masked")
    p_url.set_defaults(func=_cmd_url)

    p_migrate = sub.add_parser("migrate-data", help="Migrate local data directory contents to MySQL")
    p_migrate.add_argument(
        "--data-dir",
        default="data",
        help="Path to legacy data directory (default: ./data)",
    )
    p_migrate.set_defaults(func=_cmd_migrate_data)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
