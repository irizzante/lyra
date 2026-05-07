"""Tests verifying that built-in sources implement the Source protocol (M1.11.1)."""

from __future__ import annotations

from lyra.sources.base import Source
from lyra.sources.karpathy_wiki import KarpathyWikiSource
from lyra.sources.obsidian_tasks import ObsidianTasksSource


def test_karpathy_wiki_source_is_source_protocol(tmp_path) -> None:
    src = KarpathyWikiSource(vault_path=tmp_path)
    assert isinstance(src, Source), "KarpathyWikiSource must implement Source protocol"


def test_obsidian_tasks_source_is_source_protocol(tmp_path) -> None:
    src = ObsidianTasksSource(vault_path=tmp_path)
    assert isinstance(src, Source), "ObsidianTasksSource must implement Source protocol"


def test_karpathy_wiki_has_required_methods() -> None:
    for method in ("query", "list_recent", "health", "capabilities"):
        assert hasattr(KarpathyWikiSource, method), (
            f"KarpathyWikiSource missing required method: {method}"
        )


def test_obsidian_tasks_has_required_methods() -> None:
    for method in ("query", "list_recent", "health", "capabilities"):
        assert hasattr(ObsidianTasksSource, method), (
            f"ObsidianTasksSource missing required method: {method}"
        )
