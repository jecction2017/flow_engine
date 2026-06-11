"""HTTP API tests for /api/guide/*."""

from __future__ import annotations

from fastapi.testclient import TestClient


def client() -> TestClient:
    from flow_engine.api.http_api import create_app

    return TestClient(create_app())


def test_guide_tree_and_doc_and_search() -> None:
    c = client()
    tree = c.get("/api/guide/tree")
    assert tree.status_code == 200
    body = tree.json()
    assert body["root"] == "guide"
    assert len(body["children"]) >= 10

    doc = c.get("/api/guide/doc", params={"path": "index"})
    assert doc.status_code == 200
    assert "帮助文档" in doc.json()["title"]

    section = c.get("/api/guide/doc", params={"path": "overview"})
    assert section.status_code == 200
    assert section.json()["path"] == "overview"

    started = c.get("/api/guide/doc", params={"path": "getting-started"})
    assert started.status_code == 200
    assert started.json()["path"] == "getting-started"

    bad = c.get("/api/guide/doc", params={"path": "../etc/passwd"})
    assert bad.status_code in (400, 404)

    search = c.get("/api/guide/search", params={"q": "试运行"})
    assert search.status_code == 200
    results = search.json()["results"]
    assert len(results) >= 1

    short = c.get("/api/guide/search", params={"q": "a"})
    assert short.status_code == 200
    assert short.json()["results"] == []
