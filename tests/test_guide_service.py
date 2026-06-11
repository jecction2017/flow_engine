"""Tests for docs/guide service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flow_engine.guide import service as guide_service
from flow_engine.guide.service import (
    GuideNotFoundError,
    GuidePathError,
    build_guide_tree,
    read_guide_doc,
    search_guide_docs,
)


@pytest.fixture()
def guide_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "docs" / "guide"
    root.mkdir(parents=True)

    (root / "_meta.json").write_text(
        json.dumps({"title": "帮助文档", "order": 0}),
        encoding="utf-8",
    )
    (root / "index.md").write_text("# 帮助首页\n\n欢迎。", encoding="utf-8")

    alpha = root / "alpha"
    alpha.mkdir()
    (alpha / "_meta.json").write_text(
        json.dumps(
            {
                "title": "Alpha 章节",
                "order": 1,
                "entries": {"first.md": {"title": "第一篇", "order": 2}, "index.md": {"title": "Alpha 概述", "order": 1}},
            }
        ),
        encoding="utf-8",
    )
    (alpha / "index.md").write_text("# Alpha 概述\n\n概述内容。", encoding="utf-8")
    (alpha / "first.md").write_text("# 第一篇\n\n部署相关内容在这里。", encoding="utf-8")

    monkeypatch.setattr(guide_service, "guide_root", lambda: root)
    return root


def test_build_guide_tree_orders_children(guide_tree: Path) -> None:
    tree = build_guide_tree()
    assert tree["root"] == "guide"
    children = tree["children"]
    assert len(children) == 2
    alpha = next(c for c in children if c["name"] == "alpha")
    assert alpha["kind"] == "dir"
    assert alpha["title"] == "Alpha 章节"
    doc_titles = [c["title"] for c in alpha["children"] if c["kind"] == "doc"]
    assert doc_titles[0] == "Alpha 概述"
    assert doc_titles[1] == "第一篇"


def test_read_guide_doc_index_and_nested(guide_tree: Path) -> None:
    doc = read_guide_doc("index")
    assert doc["title"] == "帮助首页"
    assert "欢迎" in doc["content"]

    nested = read_guide_doc("alpha/first")
    assert nested["title"] == "第一篇"
    assert "部署" in nested["content"]


def test_read_guide_doc_resolves_directory_index(guide_tree: Path) -> None:
    doc = read_guide_doc("alpha")
    assert doc["path"] == "alpha"
    assert doc["title"] == "Alpha 概述"
    assert "概述内容" in doc["content"]


def test_read_guide_doc_rejects_traversal(guide_tree: Path) -> None:
    with pytest.raises(GuidePathError):
        read_guide_doc("../secrets")
    with pytest.raises(GuideNotFoundError):
        read_guide_doc("missing-page")


def test_search_matches_title_and_body(guide_tree: Path) -> None:
    assert search_guide_docs("a") == []
    hits = search_guide_docs("部署")
    assert len(hits) == 1
    assert hits[0]["path"] == "alpha/first"
    assert "部署" in hits[0]["snippet"]

    title_hits = search_guide_docs("帮助首页")
    assert any(h["path"] == "index" for h in title_hits)
