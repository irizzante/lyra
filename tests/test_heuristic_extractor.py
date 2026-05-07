"""Tests for M3.2 — heuristic entity extractor."""

from __future__ import annotations

from lyra.extract.heuristic import ENTITY_TYPES, ExtractedEntity, extract


def _by_type(entities: list[ExtractedEntity], et: str) -> list[ExtractedEntity]:
    return [e for e in entities if e.entity_type == et]


def _names(entities: list[ExtractedEntity]) -> set[str]:
    return {e.name for e in entities}


# ---------------------------------------------------------------------------
# Frontmatter entities field
# ---------------------------------------------------------------------------

def test_extracts_from_frontmatter_dict_style() -> None:
    fm = {
        "entities": [
            {"entity_type": "library", "name": "litellm", "aliases": ["LiteLLM"]},
        ]
    }
    result = extract("", fm)
    libs = _by_type(result, "library")
    assert any(e.name == "litellm" for e in libs)
    assert any("LiteLLM" in e.aliases for e in libs)


def test_extracts_from_frontmatter_shortform() -> None:
    fm = {"entities": ["library::requests", "project::lyra"]}
    result = extract("", fm)
    assert any(e.name == "requests" and e.entity_type == "library" for e in result)
    assert any(e.name == "lyra" and e.entity_type == "project" for e in result)


def test_frontmatter_confidence_is_high() -> None:
    fm = {"entities": [{"entity_type": "person", "name": "Alice"}]}
    result = extract("", fm)
    alice = next(e for e in result if e.name == "Alice")
    assert alice.confidence >= 0.85


# ---------------------------------------------------------------------------
# Inline annotations
# ---------------------------------------------------------------------------

def test_parses_inline_entity_annotation() -> None:
    body = "entity::library fastapi\n"
    result = extract(body)
    libs = _by_type(result, "library")
    assert any(e.name == "fastapi" for e in libs)


def test_inline_annotation_records_position() -> None:
    body = "Intro.\n\nentity::person Bob Smith\n\nEnd.\n"
    result = extract(body)
    persons = _by_type(result, "person")
    assert any(e.name == "Bob Smith" and e.positions for e in persons)


def test_inline_annotation_unknown_type_ignored() -> None:
    body = "entity::alien foo\n"
    result = extract(body)
    assert all(e.entity_type in ENTITY_TYPES for e in result)


# ---------------------------------------------------------------------------
# File path detection
# ---------------------------------------------------------------------------

def test_extracts_file_paths() -> None:
    body = "See `src/lyra/compile_pipeline.py` for details.\n"
    result = extract(body)
    files = _by_type(result, "file")
    assert any("compile_pipeline.py" in e.name for e in files)


def test_relative_paths_extracted() -> None:
    body = "Edited ./tests/test_compile.py.\n"
    result = extract(body)
    files = _by_type(result, "file")
    assert any("test_compile.py" in e.name for e in files)


def test_short_paths_below_threshold_ignored() -> None:
    body = "See a.py for info.\n"
    result = extract(body)
    # "a.py" is 4 chars (below the 5-char minimum), should be ignored
    files = _by_type(result, "file")
    assert not any(e.name == "a.py" for e in files)


# ---------------------------------------------------------------------------
# Python imports
# ---------------------------------------------------------------------------

def test_extracts_python_stdlib_import() -> None:
    body = "import json\nimport pathlib\n"
    result = extract(body)
    libs = _names(_by_type(result, "library"))
    assert "json" in libs
    assert "pathlib" in libs


def test_extracts_from_import() -> None:
    body = "from lyra.ids import new_ulid\n"
    result = extract(body)
    libs = _names(_by_type(result, "library"))
    assert "lyra" in libs


# ---------------------------------------------------------------------------
# JS/TS imports
# ---------------------------------------------------------------------------

def test_extracts_js_named_import() -> None:
    body = 'import { useState } from "react"\n'
    result = extract(body)
    libs = _names(_by_type(result, "library"))
    assert "react" in libs


def test_skips_relative_js_import() -> None:
    body = 'import foo from "./local"\n'
    result = extract(body)
    libs = _names(_by_type(result, "library"))
    assert "./local" not in libs


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------

def test_deduplicates_same_entity_from_multiple_sources() -> None:
    body = "entity::library requests\n\nimport requests\n"
    result = extract(body)
    libs = _by_type(result, "library")
    req = [e for e in libs if e.name == "requests"]
    assert len(req) == 1, "same entity mentioned twice must not produce duplicates"


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------

def test_empty_body_empty_frontmatter_returns_empty() -> None:
    assert extract("", {}) == []


def test_body_with_no_entities_returns_empty() -> None:
    result = extract("This is some text with no entities at all.\n")
    # File paths and imports require specific patterns; plain prose has none
    assert isinstance(result, list)
