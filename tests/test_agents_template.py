"""Tests for the canonical AGENTS.md template (M1.9.1 / M1.4.2)."""

from __future__ import annotations

from importlib import resources


def _agents_content() -> str:
    return (
        resources.files("lyra.templates")
        .joinpath("AGENTS.md")
        .read_text(encoding="utf-8")
    )


def test_agents_has_session_start_instruction() -> None:
    content = _agents_content()
    assert "lyra brief" in content, "must instruct agents to call lyra brief at session start"


def test_agents_has_memory_tiers_table() -> None:
    content = _agents_content()
    for tier in ("Working", "Episodic", "Semantic", "Procedural", "Q&A", "Meta"):
        assert tier in content, f"memory tier '{tier}' missing from AGENTS.md"


def test_agents_has_memory_tier_paths() -> None:
    content = _agents_content()
    assert "raw/" in content
    assert "wiki/sessions" in content
    assert "wiki/sources" in content
    assert "wiki/qa" in content
    assert "wiki/meta" in content


def test_agents_has_entity_types_section() -> None:
    content = _agents_content()
    assert "Entity types" in content or "entity types" in content.lower()
    for entity in ("source", "concept", "connection", "synthesis", "session", "qa"):
        assert entity in content, f"entity type '{entity}' missing"


def test_agents_has_frontmatter_schema() -> None:
    content = _agents_content()
    assert "Frontmatter schema" in content or "frontmatter" in content.lower()
    # raw record fields
    assert "raw_id" in content
    assert "kind" in content
    # wiki page fields
    assert "confidence" in content
    assert "supersedes" in content
    assert "superseded_by" in content
    assert "contradicts" in content
    assert "relations" in content


def test_agents_has_relation_taxonomy() -> None:
    content = _agents_content()
    assert "Relation taxonomy" in content or "relation" in content.lower()
    for rel in ("supports", "contradicts", "uses", "supersedes", "depends_on"):
        assert rel in content, f"relation type '{rel}' missing from AGENTS.md"


def test_agents_has_confidence_scale() -> None:
    content = _agents_content()
    assert "Confidence scale" in content or "confidence" in content.lower()
    assert "0.9" in content or "0.7" in content  # scale values present


def test_agents_has_supersession_protocol() -> None:
    content = _agents_content()
    assert "Supersession" in content or "supersession" in content.lower()
    assert "ADR-8" in content


def test_agents_has_ingest_rules() -> None:
    content = _agents_content()
    assert "Ingest rules" in content or "ingest" in content.lower()
    assert "research" in content
    assert "clip" in content
    assert "session" in content


def test_agents_has_qa_conventions() -> None:
    content = _agents_content()
    assert "Q&A" in content or "qa" in content.lower()
    assert "lyra file" in content


def test_agents_has_authoring_rules() -> None:
    content = _agents_content()
    assert "Authoring rules" in content or "authoring" in content.lower()
