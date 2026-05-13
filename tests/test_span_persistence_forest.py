"""Tests for ``span_persistence.list_spans_forest``.

The forest function is the read-side contract for the "执行链路" panel in
both the operations center and the test center. Its job is to return a
well-formed parent-child forest under arbitrary filters and pagination,
so the frontend never has to fabricate orphan roots.

These tests build small handcrafted span trees directly in ``fe_run_span``
(no orchestrator needed) and assert on the invariants:

* Every returned ``parent_span_id`` is null OR present in ``items`` —
  tree integrity holds.
* Child match → ancestors are pulled in automatically.
* ``include_descendants=True`` → parent match additionally pulls the
  entire subtree.
* Result-size caps surface ``truncated`` flags instead of silently
  dropping rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flow_engine.db.models import FeRunSpan
from flow_engine.db.session import db_session
from flow_engine.runner import span_persistence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_span(
    *,
    deploy_run_id: int,
    node_id: str,
    node_type: str = "task",
    parent_span_id: int | None = None,
    span_seq: int = 0,
    status: str = "success",
    started_at: datetime | None = None,
    duration_ms: int | None = 10,
    scope_key: str = "",
) -> int:
    """Insert one span row and return its primary key."""
    row = FeRunSpan(
        deploy_run_id=deploy_run_id,
        flow_code="t",
        node_id=node_id,
        node_type=node_type,
        span_seq=span_seq,
        parent_span_id=parent_span_id,
        scope_key=scope_key,
        started_at=started_at or datetime.now(timezone.utc),
        finished_at=None,
        duration_ms=duration_ms,
        status=status,
        error=None,
        sampled=1,
    )
    with db_session() as s:
        s.add(row)
        s.flush()
        return int(row.id)


def _build_simple_tree(run_id: int) -> dict[str, int]:
    """Build a small 3-level tree (no synthetic flow_root; the run record
    in fe_deploy_run / fe_test_run is the implicit owner):

        root  (a real task node)
        ├── outer_loop  (status=success)
        │   ├── inner_a (status=failed,  scope_key=k1)
        │   └── inner_b (status=success, scope_key=k2)
        └── side_task   (status=success)
    """
    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = _insert_span(
        deploy_run_id=run_id,
        node_id="root",
        node_type="task",
        started_at=base,
    )
    outer = _insert_span(
        deploy_run_id=run_id,
        node_id="outer",
        node_type="task",
        parent_span_id=root,
        span_seq=1,
        started_at=base + timedelta(milliseconds=10),
    )
    inner_a = _insert_span(
        deploy_run_id=run_id,
        node_id="inner_a",
        node_type="task",
        parent_span_id=outer,
        span_seq=2,
        status="failed",
        scope_key="k1",
        started_at=base + timedelta(milliseconds=20),
    )
    inner_b = _insert_span(
        deploy_run_id=run_id,
        node_id="inner_b",
        node_type="task",
        parent_span_id=outer,
        span_seq=3,
        status="success",
        scope_key="k2",
        started_at=base + timedelta(milliseconds=30),
    )
    side = _insert_span(
        deploy_run_id=run_id,
        node_id="side",
        node_type="task",
        parent_span_id=root,
        span_seq=4,
        status="success",
        started_at=base + timedelta(milliseconds=40),
    )
    return {
        "root": root,
        "outer": outer,
        "inner_a": inner_a,
        "inner_b": inner_b,
        "side": side,
    }


def _assert_forest_well_formed(items: list[dict]) -> None:
    """Every non-null parent_span_id must point to another item in ``items``."""
    ids = {int(it["id"]) for it in items}
    for it in items:
        pid = it.get("parent_span_id")
        if pid is None:
            continue
        assert pid in ids, (
            f"orphan span id={it['id']} node={it['node_id']} parent={pid} "
            f"missing from items (forest invariant violated)"
        )


# ---------------------------------------------------------------------------
# No filter: paginate roots, full subtrees
# ---------------------------------------------------------------------------


def test_no_filter_returns_full_run_forest() -> None:
    run_id = 1001
    ids = _build_simple_tree(run_id)

    page = span_persistence.list_spans_forest(deploy_run_id=run_id, limit=50)

    assert page["total_matched"] is None
    assert page["total_roots"] == 1  # one natural root ("root" task node)
    assert page["truncated"] == {"matched": False, "returned": False}
    _assert_forest_well_formed(page["items"])
    returned_ids = {int(it["id"]) for it in page["items"]}
    assert returned_ids == set(ids.values()), "expected the entire tree"


# ---------------------------------------------------------------------------
# Filter on child: ancestors must auto-include
# ---------------------------------------------------------------------------


def test_child_match_pulls_ancestor_chain() -> None:
    """The defining requirement: 子节点命中搜索，必须要带上父节点。"""
    run_id = 1002
    ids = _build_simple_tree(run_id)

    # Filter on the failing leaf only — the response must still carry
    # outer + root so the tree is renderable.
    page = span_persistence.list_spans_forest(
        deploy_run_id=run_id,
        status="failed",
        limit=50,
    )

    assert page["total_matched"] == 1  # only inner_a matches
    assert page["total_roots"] == 1
    _assert_forest_well_formed(page["items"])
    returned = {int(it["id"]) for it in page["items"]}
    # Must contain the match plus its full ancestor chain — and ONLY those
    # (siblings of the match are not pulled when include_descendants is off).
    assert ids["inner_a"] in returned
    assert ids["outer"] in returned
    assert ids["root"] in returned
    assert ids["inner_b"] not in returned
    assert ids["side"] not in returned


# ---------------------------------------------------------------------------
# include_descendants: parent match pulls entire subtree
# ---------------------------------------------------------------------------


def test_include_descendants_pulls_subtree_under_matched_parent() -> None:
    """父节点命中，可选展示其完整子树。"""
    run_id = 1003
    ids = _build_simple_tree(run_id)

    # node_id=outer matches one parent; without descendants, siblings of
    # outer's children (inner_a, inner_b) would be missing from the page.
    page = span_persistence.list_spans_forest(
        deploy_run_id=run_id,
        node_id="outer",
        include_descendants=True,
        limit=50,
    )

    assert page["include_descendants"] is True
    _assert_forest_well_formed(page["items"])
    returned = {int(it["id"]) for it in page["items"]}
    # Subtree under "outer" + ancestor chain.
    assert ids["outer"] in returned
    assert ids["inner_a"] in returned
    assert ids["inner_b"] in returned
    assert ids["root"] in returned
    # "side" is a sibling of outer (not in outer's subtree) → not included.
    assert ids["side"] not in returned

    # And the same query WITHOUT include_descendants must return only the
    # matched parent + ancestors, no children.
    page_no_desc = span_persistence.list_spans_forest(
        deploy_run_id=run_id,
        node_id="outer",
        include_descendants=False,
        limit=50,
    )
    returned_no_desc = {int(it["id"]) for it in page_no_desc["items"]}
    assert ids["outer"] in returned_no_desc
    assert ids["root"] in returned_no_desc
    assert ids["inner_a"] not in returned_no_desc
    assert ids["inner_b"] not in returned_no_desc


# ---------------------------------------------------------------------------
# Pagination by root: each page returns well-formed forest fragments
# ---------------------------------------------------------------------------


def test_paginate_by_root_keeps_subtrees_whole() -> None:
    run_id = 1004
    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Three independent root subtrees (parent_span_id=None) each with one child.
    expected_pairs: list[tuple[int, int]] = []
    for k in range(3):
        root = _insert_span(
            deploy_run_id=run_id,
            node_id=f"root_{k}",
            node_type="task",
            started_at=base + timedelta(seconds=k),
        )
        child = _insert_span(
            deploy_run_id=run_id,
            node_id=f"child_{k}",
            parent_span_id=root,
            span_seq=1,
            started_at=base + timedelta(seconds=k, milliseconds=5),
        )
        expected_pairs.append((root, child))

    page1 = span_persistence.list_spans_forest(deploy_run_id=run_id, limit=2)
    assert page1["total_roots"] == 3
    _assert_forest_well_formed(page1["items"])
    # 2 roots × (root + 1 child) = 4 spans on page 1.
    assert len(page1["items"]) == 4

    page2 = span_persistence.list_spans_forest(
        deploy_run_id=run_id, limit=2, offset=2
    )
    _assert_forest_well_formed(page2["items"])
    # Remaining 1 root × (root + 1 child) = 2 spans on page 2.
    assert len(page2["items"]) == 2

    # No root subtree is split across pages: ids on page 1 ∩ page 2 = ∅.
    ids_p1 = {int(it["id"]) for it in page1["items"]}
    ids_p2 = {int(it["id"]) for it in page2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


# ---------------------------------------------------------------------------
# Matched-set cap surfaces truncated.matched=True
# ---------------------------------------------------------------------------


def test_matched_cap_surfaces_truncated_flag(monkeypatch) -> None:
    run_id = 1005
    # Lower the cap to keep the test fast — we don't need 10K rows to
    # exercise the truncation path.
    monkeypatch.setattr(span_persistence, "_MAX_MATCHED", 3)

    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Root deliberately uses a non-matching status so the filter hits only
    # the leaves; ancestor expansion is what pulls the root back in.
    root = _insert_span(
        deploy_run_id=run_id,
        node_id="root",
        node_type="task",
        status="running",
        started_at=base,
    )
    # 5 children all matching ``status=success`` — exceeds the patched cap of 3.
    for k in range(5):
        _insert_span(
            deploy_run_id=run_id,
            node_id=f"leaf_{k}",
            parent_span_id=root,
            span_seq=k + 1,
            status="success",
            started_at=base + timedelta(milliseconds=10 + k),
        )

    page = span_persistence.list_spans_forest(
        deploy_run_id=run_id,
        status="success",
        limit=50,
    )
    assert page["truncated"]["matched"] is True
    _assert_forest_well_formed(page["items"])
    # The matched set was capped to 3 leaves; their ancestor (root) was
    # then pulled in by ancestor expansion → 4 spans total on this page.
    assert page["total_matched"] == 3
    assert len(page["items"]) == 4
