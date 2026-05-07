"""Tests for M3.3 — compile pipeline entity extraction integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.compile_pipeline import compile_vault
from lyra.ids import is_ulid
from lyra.ingest import ingest
from lyra.markdown import read
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def _make_research(vault: Path, tmp_path: Path, body: str, name: str = "note.md") -> str:
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    return ingest(str(src), vault_path=vault, kind="research").raw_id


# ---------------------------------------------------------------------------
# Heuristic always runs
# ---------------------------------------------------------------------------

def test_compile_vault_extracts_entities_via_heuristic(vault: Path, tmp_path: Path) -> None:
    body = (
        "# My Note\n\n"
        "entity::library requests\n\n"
        "We use `src/lyra/compile_pipeline.py` heavily.\n"
    )
    _make_research(vault, tmp_path, body)

    report = compile_vault(vault)
    assert not report.errors
    assert report.entities_upserted > 0


def test_entity_pages_created_in_correct_subdir(vault: Path, tmp_path: Path) -> None:
    body = "# Note\n\nentity::library pyyaml\n"
    _make_research(vault, tmp_path, body)

    compile_vault(vault)

    lib_dir = vault / "wiki" / "entities" / "library"
    pages = list(lib_dir.glob("*.md"))
    assert pages, "library entity page must be created"
    doc = read(pages[0])
    assert doc.frontmatter.get("type") == "entity"
    assert doc.frontmatter.get("entity_type") == "library"
    assert is_ulid(str(doc.frontmatter.get("id")))


def test_entity_page_tracks_source_page_id(vault: Path, tmp_path: Path) -> None:
    body = "# Note\n\nentity::concept BM25\n"
    _make_research(vault, tmp_path, body)

    report = compile_vault(vault)
    assert report.promoted

    src_id = str(read(report.promoted[0]).frontmatter.get("id"))
    concept_dir = vault / "wiki" / "entities" / "concept"
    pages = list(concept_dir.glob("*.md"))
    assert pages
    doc = read(pages[0])
    mentioned_by = doc.frontmatter.get("mentioned_by") or []
    assert src_id in mentioned_by


def test_entity_pages_deduplicated_across_two_sources(vault: Path, tmp_path: Path) -> None:
    body1 = "# Note 1\n\nentity::library requests\n"
    body2 = "# Note 2\n\nentity::library requests\n"
    _make_research(vault, tmp_path, body1, "note1.md")
    _make_research(vault, tmp_path, body2, "note2.md")

    compile_vault(vault)

    lib_dir = vault / "wiki" / "entities" / "library"
    pages = list(lib_dir.glob("*.md"))
    req_pages = [p for p in pages if read(p).frontmatter.get("title") == "requests"]
    assert len(req_pages) == 1, "same entity across two sources must produce one entity page"


def test_compile_vault_idempotent_with_entities(vault: Path, tmp_path: Path) -> None:
    body = "# Note\n\nentity::project lyra\n"
    _make_research(vault, tmp_path, body)

    compile_vault(vault)
    compile_vault(vault)

    proj_dir = vault / "wiki" / "entities" / "project"
    pages = list(proj_dir.glob("*.md"))
    assert len(pages) == 1, "second compile must not duplicate entity pages"


# ---------------------------------------------------------------------------
# LiteLLM fallback (no provider configured → heuristic only)
# ---------------------------------------------------------------------------

def test_compile_vault_no_provider_uses_heuristic(vault: Path, tmp_path: Path) -> None:
    body = "# Note\n\nimport json\n\nSome text.\n"
    _make_research(vault, tmp_path, body)

    # No extraction_provider passed → heuristic only, must not raise
    report = compile_vault(vault, extraction_provider="")
    assert not report.errors


def test_compile_vault_with_unreachable_provider_falls_back(
    vault: Path, tmp_path: Path
) -> None:
    body = "# Note\n\nentity::library litellm\n"
    _make_research(vault, tmp_path, body)

    # Non-existent provider should fall back gracefully (no crash)
    report = compile_vault(
        vault,
        extraction_provider="openai",
        extraction_model="gpt-4o-mini",
    )
    # The heuristic should still have extracted the inline entity
    assert report.entities_upserted >= 1
