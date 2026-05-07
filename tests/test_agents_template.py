"""Tests for ``src/lyra/templates/AGENTS.md`` (M1.9.1)."""

from __future__ import annotations

from importlib import resources


def _agents_content() -> str:
    return (
        resources.files("lyra.templates")
        .joinpath("AGENTS.md")
        .read_text(encoding="utf-8")
    )


def test_agents_md_is_nonempty() -> None:
    content = _agents_content()
    assert len(content.strip()) > 0, "AGENTS.md must not be empty"


def test_agents_md_starts_with_heading() -> None:
    content = _agents_content()
    assert content.startswith("#"), "AGENTS.md must start with a markdown heading"


def test_agents_md_mentions_lyra_brief() -> None:
    content = _agents_content()
    assert "lyra brief" in content, "AGENTS.md must instruct agents to run 'lyra brief'"


def test_agents_md_has_memory_tiers() -> None:
    content = _agents_content()
    assert "Memory tiers" in content or "memory tier" in content.lower(), (
        "AGENTS.md must document memory tiers"
    )


def test_agents_md_has_frontmatter_schema() -> None:
    content = _agents_content()
    assert "Frontmatter" in content or "frontmatter" in content.lower(), (
        "AGENTS.md must document frontmatter schema"
    )
