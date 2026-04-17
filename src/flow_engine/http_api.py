"""Shim: ``python -m flow_engine.http_api`` and setuptools entrypoint ``flow-api``."""

from __future__ import annotations

from flow_engine.api.http_api import app, create_app, main

__all__ = ["app", "create_app", "main"]

if __name__ == "__main__":
    main()
