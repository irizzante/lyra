"""Tests for M3.1 — entity page schema and vault layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.ids import is_ulid
from lyra.markdown import read
from lyra.vault import ENTITY_TYPES, ensure_layout
from lyra.compile_pipeline import compile_page
from lyra.ingest import ingest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def test_ensure_layout_creates_entity_dirs(vault: Path) -> None:
    for et in ENTITY_TYPES:
        assert (vault / "wiki" / "entities" / et).is_dir(), f"missing wiki/entities/{et}/"


def test_entity_types_constant_covers_required_types() -> None:
    required = {"person", "project", "library", "concept", "file", "decision"}
    assert required <= set(ENTITY_TYPES)


# ---------------------------------------------------------------------------
# Entity page schema
# ---------------------------------------------------------------------------

def _make_raw(vault: Path, tmp_path: Path, body: str, name: str = "note.md") -> str:
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    return ingest(str(src), vault_path=vault, kind="research").raw_id


def _upsert_entity_and_get_page(vault: Path, tmp_path: Path, entities_json: str) -> Path:
    raw_id = _make_raw(vault, tmp_path, "# Test\n\nbody.\n")
    compile_page(raw_id, vault, entities_json=entities_json)
    entity_pages = list((vault / "wiki" / "entities").rglob("*.md"))
    assert entity_pages, "no entity pages created"
    return entity_pages[0]


def test_entity_page_has_required_frontmatter(vault: Path, tmp_path: Path) -> None:
    page = _upsert_entity_and_get_page(
        vault, tmp_path,
        '[{"entity_type": "library", "name": "litellm", "aliases": [], "attributes": {}}]',
    )
    doc = read(page)
    fm = doc.frontmatter
    assert is_ulid(str(fm.get("id"))), "id must be a ULID"
    assert fm.get("type") == "entity"
    assert fm.get("entity_type") == "library"
    assert fm.get("title") == "litellm"
    assert isinstance(fm.get("aliases"), list)
    assert isinstance(fm.get("attributes"), dict)
    assert "created" in fm
    assert "last_confirmed" in fm


def test_entity_page_lives_under_entity_type_dir(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# T\n\nbody.\n")
    compile_page(
        raw_id, vault,
        entities_json='[{"entity_type": "person", "name": "Alice", "aliases": [], "attributes": {}}]',
    )
    person_dir = vault / "wiki" / "entities" / "person"
    pages = list(person_dir.glob("*.md"))
    assert len(pages) == 1
    doc = read(pages[0])
    assert doc.frontmatter.get("title") == "Alice"


def test_entity_page_has_ulid_prefixed_filename(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# T\n\nbody.\n")
    compile_page(
        raw_id, vault,
        entities_json='[{"entity_type": "project", "name": "MyProj", "aliases": [], "attributes": {}}]',
    )
    project_dir = vault / "wiki" / "entities" / "project"
    pages = list(project_dir.glob("*.md"))
    assert pages
    stem_parts = pages[0].stem.split("-", 1)
    assert is_ulid(stem_parts[0]), "filename must start with ULID"


def test_entity_page_upsert_idempotent(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# T\n\nbody.\n")
    entities_json = '[{"entity_type": "concept", "name": "BM25", "aliases": [], "attributes": {}}]'
    compile_page(raw_id, vault, entities_json=entities_json)
    compile_page(raw_id, vault, entities_json=entities_json)
    concept_dir = vault / "wiki" / "entities" / "concept"
    pages = list(concept_dir.glob("*.md"))
    assert len(pages) == 1, "idempotent: must not create duplicate entity pages"


def test_entity_page_merges_aliases_on_second_upsert(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# T\n\nbody.\n")
    compile_page(
        raw_id, vault,
        entities_json='[{"entity_type": "library", "name": "pyyaml", "aliases": ["PyYAML"], "attributes": {}}]',
    )
    raw_id2 = _make_raw(vault, tmp_path, "# T2\n\nbody2.\n", "note2.md")
    compile_page(
        raw_id2, vault,
        entities_json='[{"entity_type": "library", "name": "pyyaml", "aliases": ["yaml"], "attributes": {}}]',
    )
    lib_dir = vault / "wiki" / "entities" / "library"
    pages = list(lib_dir.glob("*.md"))
    assert len(pages) == 1
    doc = read(pages[0])
    aliases = doc.frontmatter.get("aliases") or []
    assert "PyYAML" in aliases
    assert "yaml" in aliases
