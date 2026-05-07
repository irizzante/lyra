"""M1.3.3 — Pre-existing vault smoke test.

Verifies that ``lyra init`` over a vault that already contains user-authored
markdown and Task notes:
  - Does NOT overwrite any existing user files
  - Does NOT overwrite an existing AGENTS.md
  - Does NOT delete pre-existing wiki/ pages
  - Adds the Lyra layout (raw/, wiki/ subdirs) without disrupting existing content
  - Pre-existing pages remain readable after init
  - Pre-existing Tasks/ notes remain intact
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.vault import ensure_layout
from lyra import markdown as md


@pytest.fixture
def pre_existing_vault(tmp_path: Path) -> Path:
    """A vault with user-authored content already present."""
    vault = tmp_path / "vault"

    # User has pre-existing wiki pages
    (vault / "wiki" / "sources").mkdir(parents=True)
    user_wiki_page = vault / "wiki" / "sources" / "user-concept.md"
    user_wiki_page.write_text(
        "---\nid: USER-ID-001\ntitle: User Concept\ntype: source\n---\n# User Concept\n\nUser-authored content that must not be overwritten.\n",
        encoding="utf-8",
    )

    # User has a custom AGENTS.md
    (vault / "wiki").mkdir(exist_ok=True)
    custom_agents = vault / "wiki" / "AGENTS.md"
    custom_agents.write_text(
        "# My Custom Agents\n\nThis file must not be overwritten by lyra init.\n",
        encoding="utf-8",
    )

    # User has Task notes
    (vault / "Tasks").mkdir(parents=True)
    task_note = vault / "Tasks" / "T-001-my-task.md"
    task_note.write_text(
        "---\ntask_id: T-001\ntitle: My existing task\nstatus: in_progress\n---\n# My existing task\n",
        encoding="utf-8",
    )

    # User has some raw/ files already (e.g., manually placed research)
    (vault / "raw").mkdir(parents=True)
    user_raw = vault / "raw" / "my-note.md"
    user_raw.write_text(
        "---\nraw_id: USER-RAW-001\nkind: research\ntitle: Manual note\n---\nContent.\n",
        encoding="utf-8",
    )

    return vault


def test_init_does_not_overwrite_user_wiki_page(pre_existing_vault: Path) -> None:
    user_page = pre_existing_vault / "wiki" / "sources" / "user-concept.md"
    original = user_page.read_text(encoding="utf-8")

    ensure_layout(pre_existing_vault)

    assert user_page.read_text(encoding="utf-8") == original


def test_init_does_not_overwrite_custom_agents_md(pre_existing_vault: Path) -> None:
    agents_path = pre_existing_vault / "wiki" / "AGENTS.md"
    original = agents_path.read_text(encoding="utf-8")

    ensure_layout(pre_existing_vault)

    content = agents_path.read_text(encoding="utf-8")
    assert content == original
    assert "My Custom Agents" in content


def test_init_does_not_touch_task_notes(pre_existing_vault: Path) -> None:
    task_path = pre_existing_vault / "Tasks" / "T-001-my-task.md"
    original = task_path.read_text(encoding="utf-8")

    ensure_layout(pre_existing_vault)

    assert task_path.read_text(encoding="utf-8") == original


def test_init_does_not_touch_existing_raw_files(pre_existing_vault: Path) -> None:
    raw_path = pre_existing_vault / "raw" / "my-note.md"
    original = raw_path.read_text(encoding="utf-8")

    ensure_layout(pre_existing_vault)

    assert raw_path.read_text(encoding="utf-8") == original


def test_init_creates_missing_wiki_subdirs(pre_existing_vault: Path) -> None:
    ensure_layout(pre_existing_vault)

    for sub in ("concepts", "connections", "procedures", "synthesis", "qa", "meta"):
        assert (pre_existing_vault / "wiki" / sub).exists(), f"missing wiki/{sub}"


def test_init_creates_raw_assets_subdir(pre_existing_vault: Path) -> None:
    ensure_layout(pre_existing_vault)
    assert (pre_existing_vault / "raw" / "assets").exists()


def test_init_does_not_create_raw_organisational_subdirs(pre_existing_vault: Path) -> None:
    ensure_layout(pre_existing_vault)
    for bad_sub in ("research", "clips", "sessions"):
        assert not (pre_existing_vault / "raw" / bad_sub).exists(), (
            f"ADR-6 violation: raw/{bad_sub} must not be created"
        )


def test_pre_existing_pages_remain_readable_after_init(pre_existing_vault: Path) -> None:
    ensure_layout(pre_existing_vault)
    page = pre_existing_vault / "wiki" / "sources" / "user-concept.md"
    doc = md.read(page)
    assert doc.frontmatter.get("id") == "USER-ID-001"
    assert "User-authored content" in doc.body


def test_init_idempotent_on_pre_existing_vault(pre_existing_vault: Path) -> None:
    """Running init twice must not corrupt anything."""
    agents_before = (pre_existing_vault / "wiki" / "AGENTS.md").read_text(encoding="utf-8")
    page_before = (pre_existing_vault / "wiki" / "sources" / "user-concept.md").read_text(encoding="utf-8")

    ensure_layout(pre_existing_vault)
    ensure_layout(pre_existing_vault)

    assert (pre_existing_vault / "wiki" / "AGENTS.md").read_text(encoding="utf-8") == agents_before
    assert (pre_existing_vault / "wiki" / "sources" / "user-concept.md").read_text(encoding="utf-8") == page_before
