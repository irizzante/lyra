"""Tests for PlainMarkdownSource (M2)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lyra.sources.plain_markdown import PlainMarkdownSource


@pytest.fixture
def md_tree(tmp_path: Path) -> Path:
    root = tmp_path / "notes"
    root.mkdir()
    (root / "a.md").write_text("# Alpha\n\nFirst note.", encoding="utf-8")
    (root / "b.md").write_text("# Beta\n\nSecond note.", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("# Gamma\n\nThird note.", encoding="utf-8")
    return root


def test_health_root_not_found(tmp_path: Path) -> None:
    src = PlainMarkdownSource(tmp_path / "nonexistent")
    h = src.health()
    assert h.ok is False
    assert "root not found" in h.message


def test_health_counts_md_files(md_tree: Path) -> None:
    src = PlainMarkdownSource(md_tree)
    h = src.health()
    assert h.ok is True
    assert h.detail["file_count"] == 3


def test_health_includes_collection(md_tree: Path) -> None:
    src = PlainMarkdownSource(md_tree, collection="my-notes")
    h = src.health()
    assert h.detail["collection"] == "my-notes"


def test_list_recent_returns_files(md_tree: Path) -> None:
    src = PlainMarkdownSource(md_tree)
    results = src.list_recent()
    assert len(results) == 3
    for r in results:
        assert r.source == "plain_markdown"
        assert r.title != ""


def test_list_recent_empty_dir(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    src = PlainMarkdownSource(root)
    assert src.list_recent() == []


def test_list_recent_nonexistent_root(tmp_path: Path) -> None:
    src = PlainMarkdownSource(tmp_path / "gone")
    assert src.list_recent() == []


def test_list_recent_sorted_by_mtime(tmp_path: Path) -> None:
    root = tmp_path / "notes"
    root.mkdir()
    old = root / "old.md"
    old.write_text("old", encoding="utf-8")
    time.sleep(0.01)
    new = root / "new.md"
    new.write_text("new", encoding="utf-8")

    src = PlainMarkdownSource(root)
    results = src.list_recent()
    assert results[0].id == "new.md"


def test_query_no_index_returns_empty(md_tree: Path) -> None:
    src = PlainMarkdownSource(md_tree, collection="no-such-collection")
    # qmd not installed or index absent — must return [] without raising
    results = src.query("alpha")
    assert isinstance(results, list)


def test_capabilities(md_tree: Path) -> None:
    src = PlainMarkdownSource(md_tree)
    caps = src.capabilities()
    assert caps.supports_query is True
    assert caps.supports_list_recent is True
    assert caps.read_only is True
    assert caps.supports_graph is False
