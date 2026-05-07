"""Tests for ``skills/lyra/SKILL.md`` template (M1.9.4)."""

from __future__ import annotations

from importlib import resources


def _skill_content() -> str:
    return (
        resources.files("lyra.templates")
        .joinpath("SKILL.md")
        .read_text(encoding="utf-8")
    )


def test_skill_has_frontmatter_description() -> None:
    content = _skill_content()
    assert content.startswith("---"), "SKILL.md must open with YAML frontmatter"
    assert "description:" in content


def test_skill_frontmatter_mentions_lyra() -> None:
    content = _skill_content()
    front_end = content.index("---", 3)
    frontmatter = content[:front_end]
    assert "lyra" in frontmatter.lower()


def test_skill_has_core_commands_section() -> None:
    content = _skill_content()
    assert "lyra brief" in content
    assert "lyra query" in content
    assert "lyra ingest" in content
    assert "lyra compile" in content


def test_skill_documents_install_command() -> None:
    content = _skill_content()
    assert "lyra install" in content
    assert "--hook" in content
    assert "--skill" in content


def test_skill_documents_memory_tiers() -> None:
    content = _skill_content()
    assert "raw/" in content
    assert "wiki/sessions" in content
    assert "wiki/sources" in content


def test_skill_documents_relation_annotations() -> None:
    content = _skill_content()
    assert "supports::" in content
    assert "contradicts::" in content
    assert "supersedes::" in content
