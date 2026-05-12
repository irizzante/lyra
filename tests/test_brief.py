"""Tests for M1.8 — lyra brief generation."""

from __future__ import annotations

from pathlib import Path


from lyra.brief import generate_brief
from lyra import markdown as md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "wiki" / "sources").mkdir(parents=True)
    (vault / "wiki").mkdir(exist_ok=True)
    (vault / "raw").mkdir(parents=True, exist_ok=True)
    return vault


def _add_log(vault: Path, entries: list[str]) -> None:
    log = vault / "wiki" / "log.md"
    log.write_text("\n".join(entries) + "\n", encoding="utf-8")


def _add_page(vault: Path, filename: str, title: str, last_confirmed: str, confidence: float = 0.5) -> None:
    path = vault / "wiki" / "sources" / filename
    md.write(path, md.Document(
        frontmatter={
            "id": f"ULID-{filename}",
            "title": title,
            "type": "source",
            "confidence": confidence,
            "last_confirmed": last_confirmed,
        },
        body=f"# {title}\n\nContent.",
    ))


def _add_session(vault: Path, title: str, time_created: str, session_id: str) -> None:
    path = vault / "raw" / f"ses-{session_id}.md"
    md.write(path, md.Document(
        frontmatter={
            "raw_id": f"RAW-{session_id}",
            "kind": "session",
            "source": "opencode",
            "session_id": session_id,
            "session_title": title,
            "time_created": time_created,
        },
        body=f"# {title}\n",
    ))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_brief_returns_string(tmp_path):
    vault = _make_vault(tmp_path)
    brief = generate_brief(vault)
    assert isinstance(brief, str)
    assert len(brief) > 0


def test_brief_contains_vault_path(tmp_path):
    vault = _make_vault(tmp_path)
    brief = generate_brief(vault)
    assert str(vault) in brief


def test_brief_contains_date(tmp_path):
    import datetime
    vault = _make_vault(tmp_path)
    brief = generate_brief(vault)
    today = datetime.date.today().isoformat()
    assert today in brief


def test_brief_includes_recent_activity(tmp_path):
    vault = _make_vault(tmp_path)
    _add_log(vault, [
        "- 2026-05-01 — promoted=3 updated=0 skipped=0 errors=0",
        "- 2026-05-06 — promoted=1 updated=2 skipped=0 errors=0",
    ])
    brief = generate_brief(vault)
    assert "promoted=1" in brief


def test_brief_includes_recent_sessions(tmp_path):
    vault = _make_vault(tmp_path)
    _add_session(vault, "My Session Alpha", "2026-05-06T10:00:00+00:00", "ses001")
    brief = generate_brief(vault)
    assert "My Session Alpha" in brief


def test_brief_includes_top_pages(tmp_path):
    vault = _make_vault(tmp_path)
    _add_page(vault, "transformers.md", "Transformers Architecture", "2026-05-05", 0.9)
    _add_page(vault, "attention.md", "Attention Mechanism", "2026-05-04", 0.7)
    brief = generate_brief(vault)
    assert "Transformers Architecture" in brief


def test_brief_includes_usage_hint(tmp_path):
    vault = _make_vault(tmp_path)
    brief = generate_brief(vault)
    assert "lyra query" in brief


def test_brief_respects_budget(tmp_path):
    vault = _make_vault(tmp_path)
    _add_log(vault, [f"- 2026-05-0{i} — entry {i}" for i in range(1, 9)])
    for i in range(20):
        _add_page(vault, f"page{i}.md", f"Page Title {i}", f"2026-05-0{i % 9 + 1}")
    _add_session(vault, "Long Session", "2026-05-06T00:00:00+00:00", "ses_x")

    brief = generate_brief(vault, char_budget=500)
    assert len(brief) <= 600  # some slack for rounding, but well within 2x budget


def test_brief_no_log_no_crash(tmp_path):
    vault = _make_vault(tmp_path)
    brief = generate_brief(vault)
    assert "Lyra brief" in brief


def test_brief_no_sessions_no_crash(tmp_path):
    vault = _make_vault(tmp_path)
    _add_log(vault, ["- 2026-05-06 — promoted=1 updated=0 skipped=0 errors=0"])
    brief = generate_brief(vault)
    assert "Recent activity" in brief


def test_brief_top_pages_sorted_by_date(tmp_path):
    vault = _make_vault(tmp_path)
    _add_page(vault, "old.md", "Old Page", "2026-01-01")
    _add_page(vault, "new.md", "New Page", "2026-05-06")
    brief = generate_brief(vault)
    new_pos = brief.find("New Page")
    old_pos = brief.find("Old Page")
    assert new_pos < old_pos


def test_brief_includes_active_tasks(tmp_path):
    vault = _make_vault(tmp_path)
    tasks_dir = vault / "Tasks"
    tasks_dir.mkdir()
    md.write(tasks_dir / "T-001.md", md.Document(
        frontmatter={"task_id": "T-001", "title": "Implement feature X", "status": "in_progress"},
        body="Working on it.",
    ))
    brief = generate_brief(vault)
    assert "Active tasks" in brief
    assert "Implement feature X" in brief


def test_brief_active_tasks_excludes_done(tmp_path):
    vault = _make_vault(tmp_path)
    tasks_dir = vault / "Tasks"
    tasks_dir.mkdir()
    md.write(tasks_dir / "T-done.md", md.Document(
        frontmatter={"task_id": "T-done", "title": "Done task", "status": "done"},
        body="Finished.",
    ))
    brief = generate_brief(vault)
    assert "Done task" not in brief


def test_brief_tiered_cap_truncates_tail_items(tmp_path):
    vault = _make_vault(tmp_path)
    for i in range(6):
        _add_page(
            vault, f"p{i}.md",
            "A" * 200,  # long title
            f"2026-05-0{i + 1}",
        )
    brief = generate_brief(vault)
    section_start = brief.find("## Knowledge base")
    assert section_start != -1
    section = brief[section_start:]
    items = [ln for ln in section.splitlines() if ln.startswith("- ")]
    # Top 3 items get full summary (may include the long title); tail items (4+) capped at 120
    for item in items[3:]:
        assert "A" * 121 not in item, f"tail item exceeds 120-char cap: {item}"
