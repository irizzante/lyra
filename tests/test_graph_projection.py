"""Tests for M1.6 — graph projection: upsert_from_vault + neighbours."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lyra.index.graph_projection import (
    GraphProjectionConfig,
    open_db,
    neighbours,
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
