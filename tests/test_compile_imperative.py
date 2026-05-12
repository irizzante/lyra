"""Tests for M3.4 — lyra compile --raw-id --entities imperative mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lyra.compile_pipeline import compile_page
from lyra.ingest import ingest
from lyra.markdown import read
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def _make_raw(vault: Path, tmp_path: Path, body: str, name: str = "note.md") -> str:
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    return ingest(str(src), vault_path=vault, kind="research").raw_id


# ---------------------------------------------------------------------------
# Basic imperative compile
# ---------------------------------------------------------------------------

def test_compile_page_promotes_single_raw(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Hello\n\nbody.\n")

    report = compile_page(raw_id, vault)
    assert len(report.promoted) == 1
    assert not report.errors


def test_compile_page_with_entities_json_creates_entity_pages(
    vault: Path, tmp_path: Path
) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    entities = [{"entity_type": "library", "name": "httpx", "aliases": [], "attributes": {}}]

    report = compile_page(raw_id, vault, entities_json=json.dumps(entities))
    assert not report.errors
    assert report.entities_upserted == 1

    lib_dir = vault / "wiki" / "entities" / "library"
    pages = list(lib_dir.glob("*.md"))
    assert pages
    assert read(pages[0]).frontmatter.get("title") == "httpx"


def test_compile_page_entities_json_skips_llm(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    entities = [{"entity_type": "concept", "name": "RAG", "aliases": ["retrieval-augmented generation"], "attributes": {}}]

    # Passing a bogus provider — should not be called because entities_json is present
    report = compile_page(
        raw_id, vault,
        entities_json=json.dumps(entities),
        extraction_provider="openai",  # would fail if actually called
    )
    assert not report.errors
    assert report.entities_upserted == 1


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

def test_compile_page_idempotent_same_entities(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    entities_json = json.dumps([{"entity_type": "project", "name": "lyra", "aliases": [], "attributes": {}}])

    compile_page(raw_id, vault, entities_json=entities_json)
    compile_page(raw_id, vault, entities_json=entities_json)

    proj_dir = vault / "wiki" / "entities" / "project"
    pages = list(proj_dir.glob("*.md"))
    assert len(pages) == 1, "idempotent: must not create duplicate entity pages"


# ---------------------------------------------------------------------------
# Error handling — unknown raw_id
# ---------------------------------------------------------------------------

def test_compile_page_unknown_raw_id_returns_error(vault: Path, tmp_path: Path) -> None:
    report = compile_page("01NONEXISTENT0000000000000", vault)
    assert report.errors
    assert not report.promoted


# ---------------------------------------------------------------------------
# JSON validation errors
# ---------------------------------------------------------------------------

def test_compile_page_malformed_json_raises(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    with pytest.raises(ValueError, match="malformed"):
        compile_page(raw_id, vault, entities_json="{not valid json")


def test_compile_page_unknown_entity_type_raises(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    bad = json.dumps([{"entity_type": "alien", "name": "foo"}])
    with pytest.raises(ValueError, match="unknown entity_type"):
        compile_page(raw_id, vault, entities_json=bad)


def test_compile_page_missing_name_raises(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    bad = json.dumps([{"entity_type": "library", "name": ""}])
    with pytest.raises(ValueError, match="missing 'name'"):
        compile_page(raw_id, vault, entities_json=bad)


def test_compile_page_not_a_list_raises(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    with pytest.raises(ValueError, match="must be a list"):
        compile_page(raw_id, vault, entities_json='{"entity_type": "library", "name": "x"}')


# ---------------------------------------------------------------------------
# Multi-entity JSON
# ---------------------------------------------------------------------------

def test_compile_page_multiple_entities(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_raw(vault, tmp_path, "# Note\n\nbody.\n")
    entities = [
        {"entity_type": "library", "name": "pyyaml", "aliases": [], "attributes": {}},
        {"entity_type": "person", "name": "Andrej Karpathy", "aliases": ["Karpathy"], "attributes": {}},
        {"entity_type": "project", "name": "nanoGPT", "aliases": [], "attributes": {}},
    ]
    report = compile_page(raw_id, vault, entities_json=json.dumps(entities))
    assert not report.errors
    assert report.entities_upserted == 3
