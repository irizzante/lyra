"""Tests for the Source protocol contract (M1.11.1).

Verifies that:
- Source is a runtime-checkable Protocol
- KarpathyWikiSource implements it
- ObsidianTasksSource implements it
- Both expose the four required methods: query, list_recent, health, capabilities
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.sources.base import Capabilities, Health, Result, Source
from lyra.sources.karpathy_wiki import KarpathyWikiSource
from lyra.sources.obsidian_tasks import ObsidianTasksSource


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    (v / "wiki").mkdir()
    (v / "Tasks").mkdir()
    return v


# ---------------------------------------------------------------------------
# Protocol structural checks
# ---------------------------------------------------------------------------


def test_source_is_runtime_checkable() -> None:
    """Source must be @runtime_checkable so isinstance() works."""
    from lyra.sources.base import Source
    assert hasattr(Source, "__protocol_attrs__") or hasattr(Source, "_is_protocol")


def test_karpathy_wiki_source_is_source(vault: Path) -> None:
    src = KarpathyWikiSource(vault)
    assert isinstance(src, Source)


def test_obsidian_tasks_source_is_source(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    assert isinstance(src, Source)


# ---------------------------------------------------------------------------
# KarpathyWikiSource contract
# ---------------------------------------------------------------------------


def test_karpathy_wiki_query_returns_list(vault: Path) -> None:
    src = KarpathyWikiSource(vault)
    result = src.query("anything")
    assert isinstance(result, list)


def test_karpathy_wiki_list_recent_returns_list(vault: Path) -> None:
    src = KarpathyWikiSource(vault)
    result = src.list_recent("7d")
    assert isinstance(result, list)


def test_karpathy_wiki_health_returns_health(vault: Path) -> None:
    src = KarpathyWikiSource(vault)
    h = src.health()
    assert isinstance(h, Health)
    assert isinstance(h.ok, bool)


def test_karpathy_wiki_capabilities_returns_capabilities(vault: Path) -> None:
    src = KarpathyWikiSource(vault)
    caps = src.capabilities()
    assert isinstance(caps, Capabilities)
    assert caps.name == "karpathy_wiki"
    assert caps.read_only is True


# ---------------------------------------------------------------------------
# ObsidianTasksSource contract
# ---------------------------------------------------------------------------


def test_obsidian_tasks_query_returns_list(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    result = src.query("anything")
    assert isinstance(result, list)


def test_obsidian_tasks_list_recent_returns_list(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    result = src.list_recent("7d")
    assert isinstance(result, list)


def test_obsidian_tasks_health_returns_health(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    h = src.health()
    assert isinstance(h, Health)
    assert isinstance(h.ok, bool)


def test_obsidian_tasks_capabilities_returns_capabilities(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    caps = src.capabilities()
    assert isinstance(caps, Capabilities)
    assert caps.name == "obsidian_tasks"
    assert caps.read_only is True


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


def test_result_has_required_fields() -> None:
    r = Result(
        id="ID001",
        source="test",
        title="Test Result",
        snippet="some text",
        score=0.8,
    )
    assert r.id == "ID001"
    assert r.source == "test"
    assert r.score == 0.8
    assert r.citations == []
    assert r.last_seen is None
