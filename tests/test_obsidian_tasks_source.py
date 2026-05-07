"""Tests for ObsidianTasksSource (M1.11)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lyra.sources.base import Source
from lyra.sources.obsidian_tasks import ObsidianTasksSource


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    tasks_dir = tmp_path / "Tasks"
    tasks_dir.mkdir()
    return tmp_path


def _write_task(tasks_dir: Path, name: str, frontmatter: dict, body: str = "") -> Path:
    from lyra.markdown import Document, write
    path = tasks_dir / name
    write(path, Document(frontmatter=frontmatter, body=body))
    return path


def test_implements_source_protocol(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    assert isinstance(src, Source)


def test_health_ok_when_tasks_dir_exists(vault: Path) -> None:
    src = ObsidianTasksSource(vault)
    h = src.health()
    assert h.ok
    assert "task_count" in h.detail


def test_health_missing_tasks_dir(tmp_path: Path) -> None:
    src = ObsidianTasksSource(tmp_path / "no-vault")
    h = src.health()
    assert not h.ok


def test_health_missing_vault(tmp_path: Path) -> None:
    src = ObsidianTasksSource(tmp_path / "nonexistent")
    h = src.health()
    assert not h.ok


def test_capabilities_read_only(vault: Path) -> None:
    caps = ObsidianTasksSource(vault).capabilities()
    assert caps.read_only is True
    assert caps.name == "obsidian_tasks"


def test_query_finds_matching_task(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    _write_task(
        tasks_dir,
        "T-001-refactor.md",
        {"task_id": "T-001", "title": "Refactor auth module", "status": "in_progress"},
        body="We need to refactor the auth module to use JWT.",
    )
    _write_task(
        tasks_dir,
        "T-002-docs.md",
        {"task_id": "T-002", "title": "Write documentation", "status": "todo"},
        body="Update the README with new install instructions.",
    )

    src = ObsidianTasksSource(vault)
    results = src.query("auth refactor")
    assert len(results) >= 1
    assert results[0].id == "T-001"
    assert results[0].score > 0


def test_query_returns_empty_on_no_match(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    _write_task(tasks_dir, "T-001.md", {"title": "Hello"}, body="World")
    src = ObsidianTasksSource(vault)
    assert src.query("completely unrelated xyzzy") == []


def test_query_respects_k(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    for i in range(5):
        _write_task(
            tasks_dir,
            f"T-{i:03d}.md",
            {"task_id": f"T-{i:03d}", "title": f"Task {i}"},
            body="common keyword alpha",
        )
    src = ObsidianTasksSource(vault)
    results = src.query("alpha", k=3)
    assert len(results) <= 3


def test_query_filter_by_status(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    _write_task(tasks_dir, "T-001.md", {"task_id": "T-001", "title": "done task", "status": "done"}, body="alpha")
    _write_task(tasks_dir, "T-002.md", {"task_id": "T-002", "title": "open task", "status": "in_progress"}, body="alpha")

    src = ObsidianTasksSource(vault)
    results = src.query("alpha", filters={"status": "done"})
    assert all(r.id == "T-001" for r in results)


def test_list_recent_returns_recent_files(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    _write_task(tasks_dir, "T-001.md", {"task_id": "T-001", "title": "Recent task"}, body="body")

    src = ObsidianTasksSource(vault)
    results = src.list_recent(window="1d")
    assert len(results) >= 1
    assert any(r.id == "T-001" for r in results)


def test_list_recent_excludes_old_files(vault: Path, tmp_path: Path) -> None:
    tasks_dir = vault / "Tasks"
    old_path = tasks_dir / "T-old.md"
    _write_task(tasks_dir, "T-old.md", {"task_id": "T-old", "title": "Old task"}, body="old")
    import os
    old_time = time.time() - 86400 * 30  # 30 days ago
    os.utime(old_path, (old_time, old_time))

    src = ObsidianTasksSource(vault)
    results = src.list_recent(window="7d")
    assert all(r.id != "T-old" for r in results)


def test_list_recent_sorted_newest_first(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    import os
    for i, delay in enumerate([10, 5, 1]):
        path = _write_task(tasks_dir, f"T-{i:03d}.md", {"task_id": f"T-{i:03d}", "title": f"Task {i}"})
        t = time.time() - delay
        os.utime(path, (t, t))

    src = ObsidianTasksSource(vault)
    results = src.list_recent(window="1d")
    assert len(results) == 3
    mtimes = [r.last_seen for r in results]
    assert mtimes == sorted(mtimes, reverse=True)


def test_health_reports_task_count(vault: Path) -> None:
    tasks_dir = vault / "Tasks"
    _write_task(tasks_dir, "T-001.md", {"title": "One"})
    _write_task(tasks_dir, "T-002.md", {"title": "Two"})

    h = ObsidianTasksSource(vault).health()
    assert h.detail["task_count"] == 2
