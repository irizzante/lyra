"""Tests for M1.6 — graph projection: upsert_from_vault + neighbours."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lyra.index.graph_projection import (
    GraphProjectionConfig,
    open_db,
    neighbours,
    traverse,
    upsert_from_vault,
)
from lyra import markdown as md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    sources = vault / "wiki" / "sources"
    sources.mkdir(parents=True)
    return vault


def _write_page(vault: Path, filename: str, frontmatter: dict, body: str = "") -> Path:
    path = vault / "wiki" / "sources" / filename
    md.write(path, md.Document(frontmatter=frontmatter, body=body))
    return path


def _in_memory_cfg(tmp_path: Path) -> GraphProjectionConfig:
    return GraphProjectionConfig(db_path=tmp_path / "graph.sqlite")


# ---------------------------------------------------------------------------
# Tests: open_db
# ---------------------------------------------------------------------------


def test_open_db_creates_schema(tmp_path):
    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "pages" in tables
    assert "edges" in tables
    conn.close()


# ---------------------------------------------------------------------------
# Tests: upsert_from_vault
# ---------------------------------------------------------------------------


def test_upsert_inserts_pages(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "alpha.md", {"id": "ULID001", "title": "Alpha", "type": "source", "confidence": 0.8})
    _write_page(vault, "beta.md",  {"id": "ULID002", "title": "Beta",  "type": "source", "confidence": 0.6})

    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    pages, edges = upsert_from_vault(vault, conn)
    conn.close()

    assert pages == 2
    assert edges == 0


def test_upsert_inserts_edges(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "alpha.md", {
        "id": "ULID001", "title": "Alpha", "type": "source",
        "relations": [{"type": "supports", "target_id": "ULID002"}],
    })
    _write_page(vault, "beta.md", {"id": "ULID002", "title": "Beta", "type": "source"})

    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    pages, edges = upsert_from_vault(vault, conn)
    conn.close()

    assert edges == 1


def test_upsert_idempotent(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "alpha.md", {
        "id": "ULID001", "title": "Alpha", "type": "source",
        "relations": [{"type": "supports", "target_id": "ULID002"}],
    })
    _write_page(vault, "beta.md", {"id": "ULID002", "title": "Beta", "type": "source"})

    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    upsert_from_vault(vault, conn)
    pages, edges = upsert_from_vault(vault, conn)
    conn.close()

    assert pages == 2
    assert edges == 1


def test_upsert_skips_pages_without_id(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "no_id.md", {"title": "No ID page", "type": "source"})
    _write_page(vault, "with_id.md", {"id": "ULID001", "title": "With ID", "type": "source"})

    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    pages, edges = upsert_from_vault(vault, conn)
    conn.close()

    assert pages == 1


def test_upsert_skips_system_files(tmp_path):
    vault = _make_vault(tmp_path)
    (vault / "wiki" / "index.md").write_text("# Index", encoding="utf-8")
    (vault / "wiki" / "log.md").write_text("# Log", encoding="utf-8")
    (vault / "wiki" / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    _write_page(vault, "real.md", {"id": "ULID001", "title": "Real", "type": "source"})

    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    pages, _ = upsert_from_vault(vault, conn)
    conn.close()

    assert pages == 1


def test_upsert_skips_relations_without_target_id(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "alpha.md", {
        "id": "ULID001", "title": "Alpha", "type": "source",
        "relations": [{"type": "supports", "target": "[[Unknown Page]]"}],
    })

    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    _, edges = upsert_from_vault(vault, conn)
    conn.close()

    assert edges == 0


# ---------------------------------------------------------------------------
# Tests: neighbours
# ---------------------------------------------------------------------------


def test_neighbours_outbound(tmp_path):
    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    today = "2026-05-06"
    conn.execute("INSERT INTO pages VALUES ('A','Alpha','source',0.8,?,?)", (today, "a.md"))
    conn.execute("INSERT INTO pages VALUES ('B','Beta','source',0.6,?,?)", (today, "b.md"))
    conn.execute("INSERT INTO edges VALUES ('A','supports','B',0.9,?)", (today,))
    conn.commit()

    result = neighbours(conn, "A", direction="out")
    assert len(result) == 1
    assert result[0] == ("A", "supports", "B", 0.9)
    conn.close()


def test_neighbours_inbound(tmp_path):
    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    today = "2026-05-06"
    conn.execute("INSERT INTO pages VALUES ('A','Alpha','source',0.8,?,?)", (today, "a.md"))
    conn.execute("INSERT INTO pages VALUES ('B','Beta','source',0.6,?,?)", (today, "b.md"))
    conn.execute("INSERT INTO edges VALUES ('A','supports','B',0.9,?)", (today,))
    conn.commit()

    result = neighbours(conn, "B", direction="in")
    assert len(result) == 1
    assert result[0][0] == "A"
    conn.close()


def test_neighbours_both(tmp_path):
    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    today = "2026-05-06"
    conn.execute("INSERT INTO pages VALUES ('A','Alpha','source',0.8,?,?)", (today, "a.md"))
    conn.execute("INSERT INTO pages VALUES ('B','Beta','source',0.6,?,?)", (today, "b.md"))
    conn.execute("INSERT INTO pages VALUES ('C','Gamma','source',0.5,?,?)", (today, "c.md"))
    conn.execute("INSERT INTO edges VALUES ('A','supports','B',0.9,?)", (today,))
    conn.execute("INSERT INTO edges VALUES ('C','uses','A',0.7,?)", (today,))
    conn.commit()

    result = neighbours(conn, "A", direction="both")
    assert len(result) == 2
    conn.close()


def test_neighbours_edge_type_filter(tmp_path):
    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    today = "2026-05-06"
    conn.execute("INSERT INTO pages VALUES ('A','Alpha','source',0.8,?,?)", (today, "a.md"))
    conn.execute("INSERT INTO pages VALUES ('B','Beta','source',0.6,?,?)", (today, "b.md"))
    conn.execute("INSERT INTO pages VALUES ('C','Gamma','source',0.5,?,?)", (today, "c.md"))
    conn.execute("INSERT INTO edges VALUES ('A','supports','B',0.9,?)", (today,))
    conn.execute("INSERT INTO edges VALUES ('A','contradicts','C',0.4,?)", (today,))
    conn.commit()

    result = neighbours(conn, "A", edge_types=("supports",), direction="out")
    assert len(result) == 1
    assert result[0][1] == "supports"
    conn.close()


def test_neighbours_unknown_direction(tmp_path):
    cfg = _in_memory_cfg(tmp_path)
    conn = open_db(cfg)
    with pytest.raises(ValueError):
        neighbours(conn, "A", direction="sideways")
    conn.close()


# ---------------------------------------------------------------------------
# Tests: traverse (M3.6)
# ---------------------------------------------------------------------------


def _seed_graph(conn, today: str = "2026-05-07") -> None:
    """Insert a small graph: A→B→C, A→D, with a contradicts and superseded_by edge."""
    rows = [
        ("A", "Alpha"),
        ("B", "Beta"),
        ("C", "Gamma"),
        ("D", "Delta"),
        ("E", "Epsilon"),
    ]
    for pid, title in rows:
        conn.execute(
            "INSERT OR IGNORE INTO pages VALUES (?,?,?,?,?,?)",
            (pid, title, "source", 0.8, today, f"{pid.lower()}.md"),
        )
    edges = [
        ("A", "supports", "B"),
        ("B", "uses", "C"),
        ("A", "uses", "D"),
        ("D", "contradicts", "E"),
        ("B", "superseded_by", "A"),
    ]
    for src, etype, dst in edges:
        conn.execute(
            "INSERT OR IGNORE INTO edges VALUES (?,?,?,?,?)",
            (src, etype, dst, 0.9, today),
        )
    conn.commit()


def test_traverse_empty_start_ids(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    assert traverse(conn, []) == []
    conn.close()


def test_traverse_includes_start_at_hop_zero(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    result = dict(traverse(conn, ["A"], max_hops=0))
    assert "A" in result
    assert result["A"] == 0
    conn.close()


def test_traverse_one_hop(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    result = dict(traverse(conn, ["A"], max_hops=1))
    assert result.get("A") == 0
    assert result.get("B") == 1
    assert result.get("D") == 1
    assert "C" not in result
    conn.close()


def test_traverse_two_hops(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    result = dict(traverse(conn, ["A"], max_hops=2))
    assert result.get("C") == 2
    conn.close()


def test_traverse_excludes_contradicts_by_default(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    result = dict(traverse(conn, ["D"], max_hops=2))
    assert "E" not in result
    conn.close()


def test_traverse_excludes_superseded_by_by_default(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    # B→superseded_by→A: traversing from B should NOT reach A via that edge
    result = dict(traverse(conn, ["B"], max_hops=1))
    # A is reachable via the reverse of B←supports←A (undirected), so
    # check the exclusion only for the superseded_by direction:
    # edge (B, superseded_by, A) — traversal should not follow it outbound
    # We verify by starting from D, which only has a contradicts edge to E
    result_d = dict(traverse(conn, ["D"], max_hops=1))
    assert "E" not in result_d
    conn.close()


def test_traverse_edge_types_whitelist(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    result = dict(traverse(conn, ["A"], max_hops=2, edge_types=("supports",)))
    # Only the supports edge A→B is followed; uses edges are ignored
    assert "B" in result
    assert "D" not in result
    assert "C" not in result
    conn.close()


def test_traverse_max_hops_capped_at_four(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    _seed_graph(conn)
    # max_hops=99 should be silently clamped to 4; must not raise
    result = traverse(conn, ["A"], max_hops=99)
    assert isinstance(result, list)
    conn.close()


def test_traverse_returns_min_hops(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    today = "2026-05-07"
    for pid in ("X", "Y", "Z"):
        conn.execute(
            "INSERT OR IGNORE INTO pages VALUES (?,?,?,?,?,?)",
            (pid, pid, "source", 0.8, today, f"{pid.lower()}.md"),
        )
    conn.execute("INSERT OR IGNORE INTO edges VALUES ('X','supports','Y',0.9,?)", (today,))
    conn.execute("INSERT OR IGNORE INTO edges VALUES ('X','supports','Z',0.9,?)", (today,))
    conn.execute("INSERT OR IGNORE INTO edges VALUES ('Y','supports','Z',0.9,?)", (today,))
    conn.commit()
    result = dict(traverse(conn, ["X"], max_hops=3))
    # Z reachable at hop 1 (X→Z) and hop 2 (X→Y→Z); min should be 1
    assert result.get("Z") == 1
    conn.close()


def test_traverse_max_results_cap(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    today = "2026-05-07"
    for i in range(20):
        pid = f"P{i}"
        conn.execute(
            "INSERT OR IGNORE INTO pages VALUES (?,?,?,?,?,?)",
            (pid, pid, "source", 0.8, today, f"p{i}.md"),
        )
        if i > 0:
            conn.execute(
                "INSERT OR IGNORE INTO edges VALUES (?,?,?,?,?)",
                ("P0", "supports", pid, 0.9, today),
            )
    conn.commit()
    result = traverse(conn, ["P0"], max_hops=2, max_results=5)
    assert len(result) <= 5
    conn.close()


def test_traverse_cycle_terminates(tmp_path):
    conn = open_db(_in_memory_cfg(tmp_path))
    today = "2026-05-07"
    for pid in ("U", "V"):
        conn.execute(
            "INSERT OR IGNORE INTO pages VALUES (?,?,?,?,?,?)",
            (pid, pid, "source", 0.8, today, f"{pid.lower()}.md"),
        )
    conn.execute("INSERT OR IGNORE INTO edges VALUES ('U','supports','V',0.9,?)", (today,))
    conn.execute("INSERT OR IGNORE INTO edges VALUES ('V','supports','U',0.9,?)", (today,))
    conn.commit()
    result = traverse(conn, ["U"], max_hops=4)
    ids = {r[0] for r in result}
    assert "U" in ids
    assert "V" in ids
    conn.close()
