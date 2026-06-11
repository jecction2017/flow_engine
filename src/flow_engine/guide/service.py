"""Scan, read, and search Markdown help under ``docs/guide/``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flow_engine._repo_root import repo_root

META_FILENAME = "_meta.json"
MIN_SEARCH_LEN = 2
SNIPPET_RADIUS = 60


class GuideError(Exception):
    """Base error for guide operations."""


class GuideNotFoundError(GuideError):
    """Document or path not found."""


class GuidePathError(GuideError):
    """Invalid or unsafe path."""


def guide_root() -> Path:
    return repo_root() / "docs" / "guide"


def _normalize_rel_path(path: str) -> str:
    raw = path.strip().replace("\\", "/").strip("/")
    if not raw:
        return "index"
    if raw.endswith(".md"):
        raw = raw[: -len(".md")]
    if ".." in raw.split("/"):
        raise GuidePathError(f"Invalid guide path: {path!r}")
    return raw


def _is_under_root(candidate: Path, root: Path) -> bool:
    return str(candidate).startswith(str(root))


def _resolve_md_path(rel_path: str) -> tuple[Path, str]:
    """Resolve API path to a markdown file and canonical doc id (matches tree paths)."""
    normalized = _normalize_rel_path(rel_path)
    root = guide_root().resolve()

    # Strip trailing /index from explicit requests like overview/index
    if normalized.endswith("/index"):
        normalized = normalized[: -len("/index")] or "index"

    candidates: list[tuple[str, Path]] = []
    if normalized == "index":
        candidates.append(("index", root / "index.md"))
    else:
        candidates.append((normalized, root / f"{normalized}.md"))
        candidates.append((normalized, root / normalized / "index.md"))

    for canonical, raw in candidates:
        resolved = raw.resolve()
        if not _is_under_root(resolved, root):
            raise GuidePathError(f"Path escapes guide root: {rel_path!r}")
        if resolved.is_file():
            return resolved, canonical

    raise GuideNotFoundError(f"Guide document not found: {rel_path}")


def _load_meta(dir_path: Path) -> dict[str, Any]:
    meta_path = dir_path / META_FILENAME
    if not meta_path.is_file():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuideError(f"Invalid {meta_path}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _humanize_name(name: str) -> str:
    stem = name.removesuffix(".md")
    if stem == "index":
        return "概述"
    return stem.replace("-", " ").replace("_", " ").title()


def _title_from_content(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _read_title(file_path: Path, meta_entry: dict[str, Any] | None) -> str:
    if meta_entry and isinstance(meta_entry.get("title"), str) and meta_entry["title"].strip():
        return meta_entry["title"].strip()
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return _humanize_name(file_path.name)
    from_md = _title_from_content(text)
    return from_md or _humanize_name(file_path.name)


def _entry_order(name: str, meta_entry: dict[str, Any] | None) -> tuple[int, str]:
    if meta_entry and isinstance(meta_entry.get("order"), int):
        return (meta_entry["order"], name)
    if name == "index.md":
        return (-1, name)
    return (0, name)


@dataclass(frozen=True)
class _DocRef:
    rel_path: str
    title: str
    file_path: Path


def _collect_docs(root: Path, dir_path: Path, prefix: str) -> list[_DocRef]:
    meta = _load_meta(dir_path)
    entries_meta = meta.get("entries") if isinstance(meta.get("entries"), dict) else {}

    docs: list[_DocRef] = []
    for child in sorted(dir_path.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file() and child.suffix.lower() == ".md":
            rel = f"{prefix}/{child.stem}" if prefix else child.stem
            if child.stem == "index" and not prefix:
                rel = "index"
            elif child.stem == "index":
                rel = prefix or "index"
            entry_meta = entries_meta.get(child.name)
            if not isinstance(entry_meta, dict):
                entry_meta = None
            docs.append(
                _DocRef(
                    rel_path=rel,
                    title=_read_title(child, entry_meta),
                    file_path=child,
                )
            )
    return docs


def _sort_dir_children(names: list[str], meta: dict[str, Any]) -> list[str]:
    entries_meta = meta.get("entries") if isinstance(meta.get("entries"), dict) else {}

    def sort_key(name: str) -> tuple[int, str]:
        entry = entries_meta.get(name)
        if isinstance(entry, dict) and isinstance(entry.get("order"), int):
            return (entry["order"], name)
        if name == "index.md":
            return (-1, name)
        return (0, name)

    return sorted(names, key=sort_key)


def _build_tree_node(dir_path: Path, prefix: str) -> dict[str, Any]:
    meta = _load_meta(dir_path)
    dir_title = meta.get("title") if isinstance(meta.get("title"), str) else _humanize_name(dir_path.name)
    dir_order = meta.get("order") if isinstance(meta.get("order"), int) else 0

    children: list[dict[str, Any]] = []

    subdirs: list[Path] = []
    files: list[Path] = []
    for child in dir_path.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir():
            subdirs.append(child)
        elif child.is_file() and child.suffix.lower() == ".md":
            files.append(child)

    entries_meta = meta.get("entries") if isinstance(meta.get("entries"), dict) else {}

    for sub in sorted(subdirs, key=lambda p: (
        (entries_meta.get(p.name) or {}).get("order", 0) if isinstance(entries_meta.get(p.name), dict) else 0,
        p.name.lower(),
    )):
        sub_meta = entries_meta.get(sub.name)
        sub_order = sub_meta.get("order", 0) if isinstance(sub_meta, dict) and isinstance(sub_meta.get("order"), int) else 0
        sub_prefix = f"{prefix}/{sub.name}" if prefix else sub.name
        node = _build_tree_node(sub, sub_prefix)
        node["order"] = sub_order
        children.append(node)

    for fname in _sort_dir_children([f.name for f in files], meta):
        file_path = dir_path / fname
        rel = f"{prefix}/{file_path.stem}" if prefix else file_path.stem
        if file_path.stem == "index":
            rel = prefix or "index"
        entry_meta = entries_meta.get(fname)
        if not isinstance(entry_meta, dict):
            entry_meta = None
        children.append(
            {
                "kind": "doc",
                "name": file_path.stem,
                "title": _read_title(file_path, entry_meta),
                "path": rel,
                "order": _entry_order(fname, entry_meta)[0],
            }
        )

    children.sort(key=lambda n: (n.get("order", 0), n.get("title", "")))

    node_path = prefix or ""
    return {
        "kind": "dir",
        "name": dir_path.name,
        "title": dir_title,
        "path": node_path,
        "order": dir_order,
        "children": children,
    }


def build_guide_tree() -> dict[str, Any]:
    root = guide_root()
    if not root.is_dir():
        raise GuideError(f"Guide root not found: {root}")
    tree = _build_tree_node(root, "")
    return {"root": "guide", "children": tree.get("children", [])}


def _all_doc_refs() -> list[_DocRef]:
    root = guide_root()
    if not root.is_dir():
        return []

    refs: list[_DocRef] = []

    def walk(dir_path: Path, prefix: str) -> None:
        refs.extend(_collect_docs(root, dir_path, prefix))
        for child in sorted(dir_path.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                sub_prefix = f"{prefix}/{child.name}" if prefix else child.name
                walk(child, sub_prefix)

    walk(root, "")
    # Deduplicate by rel_path
    seen: set[str] = set()
    unique: list[_DocRef] = []
    for ref in refs:
        if ref.rel_path not in seen:
            seen.add(ref.rel_path)
            unique.append(ref)
    return unique


def _breadcrumb(rel_path: str, title: str) -> str:
    parts = rel_path.split("/")
    if not parts or parts == ["index"]:
        return title
    # Build from path segments using humanized names
    crumbs = [_humanize_name(p) for p in parts[:-1]]
    crumbs.append(title)
    return " / ".join(crumbs)


def read_guide_doc(rel_path: str) -> dict[str, Any]:
    try:
        md_path, canonical = _resolve_md_path(rel_path)
    except GuidePathError:
        raise
    except GuideNotFoundError:
        raise

    content = md_path.read_text(encoding="utf-8")
    title = _title_from_content(content) or _humanize_name(md_path.name)
    return {
        "path": canonical,
        "title": title,
        "content": content,
    }


def _make_snippet(content: str, query: str) -> str:
    lower_content = content.lower()
    lower_query = query.lower()
    idx = lower_content.find(lower_query)
    if idx < 0:
        excerpt = content[: SNIPPET_RADIUS * 2].replace("\n", " ")
        return excerpt + ("…" if len(content) > len(excerpt) else "")

    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(content), idx + len(query) + SNIPPET_RADIUS)
    snippet = content[start:end].replace("\n", " ")
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{snippet}{suffix}"


def _search_score(title: str, content: str, query: str) -> tuple[int, int]:
    q = query.lower()
    title_lower = title.lower()
    content_lower = content.lower()
    if q in title_lower:
        title_score = 0
    else:
        title_score = 1
    pos = content_lower.find(q)
    body_score = pos if pos >= 0 else 10_000
    return (title_score, body_score)


def search_guide_docs(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    q = query.strip()
    if len(q) < MIN_SEARCH_LEN:
        return []

    limit = max(1, min(limit, 100))
    hits: list[tuple[tuple[int, int], dict[str, Any]]] = []

    for ref in _all_doc_refs():
        try:
            content = ref.file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if q.lower() not in content.lower() and q.lower() not in ref.title.lower():
            continue
        score = _search_score(ref.title, content, q)
        hits.append(
            (
                score,
                {
                    "path": ref.rel_path,
                    "title": ref.title,
                    "breadcrumb": _breadcrumb(ref.rel_path, ref.title),
                    "snippet": _make_snippet(content, q),
                },
            )
        )

    hits.sort(key=lambda item: (item[0], item[1]["title"].lower()))
    return [item[1] for item in hits[:limit]]
