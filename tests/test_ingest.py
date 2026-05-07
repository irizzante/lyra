"""Tests for ``lyra ingest`` (M1.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.ids import is_ulid
from lyra.ingest import ingest
from lyra.markdown import read
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def test_ingest_local_markdown_research(vault: Path, tmp_path: Path) -> None:
    src = tmp_path / "note.md"
    src.write_text("# Hello\n\nA short research note.\n", encoding="utf-8")

    result = ingest(str(src), vault_path=vault, kind="research")
    assert result.kind == "research"
    assert is_ulid(result.raw_id)
    assert result.asset_path is None
    assert result.record_path.parent == vault / "raw"  # ADR-6: flat raw/

    doc = read(result.record_path)
    assert doc.frontmatter["raw_id"] == result.raw_id
    assert doc.frontmatter["kind"] == "research"
    assert doc.frontmatter["source"].endswith("note.md")
    assert "ingested_at" in doc.frontmatter
    assert "content_type" in doc.frontmatter
    assert "Hello" in doc.body


def test_ingest_local_binary_routes_to_assets_with_wrapper(vault: Path, tmp_path: Path) -> None:
    src = tmp_path / "image.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    result = ingest(str(src), vault_path=vault, kind="clip", title="Logo")
    assert result.asset_path is not None
    assert result.asset_path.parent == vault / "raw" / "assets"
    assert result.kind == "clip"

    doc = read(result.record_path)
    assert doc.frontmatter["asset"].startswith("raw/assets/")
    assert doc.frontmatter["title"] == "Logo"
    assert "Binary asset" in doc.body


def test_ingest_rejects_unknown_kind(vault: Path, tmp_path: Path) -> None:
    src = tmp_path / "note.md"
    src.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError):
        ingest(str(src), vault_path=vault, kind="weird")


def test_ingest_missing_source(vault: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest(str(tmp_path / "missing.md"), vault_path=vault)
