"""Tests for ``lyra lint`` (M1.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.ids import new_ulid
from lyra.lint import lint_vault
from lyra import markdown as md
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def _raw(vault: Path, raw_id: str, kind: str = "research", title: str = "Test") -> Path:
    path = vault / "raw" / f"{raw_id}-test.md"
    md.write(path, md.Document(
        frontmatter={"raw_id": raw_id, "kind": kind, "title": title},
        body="content",
    ))
    return path


def _wiki_page(
    vault: Path,
    page_id: str,
    title: str,
    sources: list[str],
    *,
    supersedes: list[str] | None = None,
    superseded_by: str | None = None,
    contradicts: list[str] | None = None,
    relations: list[dict] | None = None,
    confidence: float = 0.5,
) -> Path:
    from datetime import date
    path = vault / "wiki" / "sources" / f"{md.slug(title)}.md"
    md.write(path, md.Document(
        frontmatter={
            "id": page_id,
            "title": title,
            "type": "source",
            "sources": sources,
            "confidence": confidence,
            "created": date.today().isoformat(),
            "last_confirmed": date.today().isoformat(),
            "supersedes": supersedes or [],
            "superseded_by": superseded_by,
            "contradicts": contradicts or [],
            "relations": relations or [],
        },
        body=f"# {title}",
    ))
    return path


# ------------------------------------------------------------------
# Clean vault
# ------------------------------------------------------------------

def test_lint_clean_vault_returns_ok(vault: Path) -> None:
    raw_id = new_ulid()
    page_id = new_ulid()
    _raw(vault, raw_id)
    _wiki_page(vault, page_id, "Foundation", [raw_id])
    report = lint_vault(vault)
    assert report.ok


# ------------------------------------------------------------------
# ORPHAN_RAW
# ------------------------------------------------------------------

def test_lint_detects_orphan_raw(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id, kind="research")
    report = lint_vault(vault)
    orphans = report.by_kind("ORPHAN_RAW")
    assert len(orphans) == 1
    assert raw_id in orphans[0].detail["raw_id"]


def test_lint_session_raw_not_flagged_as_orphan(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id, kind="session")
    report = lint_vault(vault)
    assert not report.by_kind("ORPHAN_RAW")


# ------------------------------------------------------------------
# MISSING_FM
# ------------------------------------------------------------------

def test_lint_detects_missing_frontmatter(vault: Path) -> None:
    page_path = vault / "wiki" / "sources" / "incomplete.md"
    md.write(page_path, md.Document(
        frontmatter={"id": new_ulid(), "title": "Incomplete"},
        body="missing required fields",
    ))
    report = lint_vault(vault)
    fm_issues = report.by_kind("MISSING_FM")
    assert len(fm_issues) == 1
    assert "sources" in fm_issues[0].detail["missing_fields"]


# ------------------------------------------------------------------
# BROKEN_SUPER
# ------------------------------------------------------------------

def test_lint_detects_broken_supersedes(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id)
    nonexistent_id = new_ulid()
    page_id = new_ulid()
    _wiki_page(vault, page_id, "New Page", [raw_id], supersedes=[nonexistent_id])
    report = lint_vault(vault)
    broken = report.by_kind("BROKEN_SUPER")
    assert len(broken) >= 1
    assert broken[0].detail["target_id"] == nonexistent_id


def test_lint_detects_broken_superseded_by(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id)
    nonexistent_id = new_ulid()
    page_id = new_ulid()
    _wiki_page(vault, page_id, "Old Page", [raw_id], superseded_by=nonexistent_id)
    report = lint_vault(vault)
    broken = report.by_kind("BROKEN_SUPER")
    assert len(broken) >= 1


def test_lint_valid_supersession_no_issue(vault: Path) -> None:
    raw_a = new_ulid()
    raw_b = new_ulid()
    _raw(vault, raw_a)
    _raw(vault, raw_b)
    id_old = new_ulid()
    id_new = new_ulid()
    _wiki_page(vault, id_old, "Old Concept", [raw_a], superseded_by=id_new)
    _wiki_page(vault, id_new, "New Concept", [raw_b], supersedes=[id_old])
    report = lint_vault(vault)
    assert not report.by_kind("BROKEN_SUPER")


# ------------------------------------------------------------------
# CONTRADICTION
# ------------------------------------------------------------------

def test_lint_detects_contradiction_without_supersession(vault: Path) -> None:
    raw_a = new_ulid()
    raw_b = new_ulid()
    _raw(vault, raw_a)
    _raw(vault, raw_b)
    id_a = new_ulid()
    id_b = new_ulid()
    _wiki_page(vault, id_a, "Claim A", [raw_a], contradicts=[id_b])
    _wiki_page(vault, id_b, "Claim B", [raw_b])
    report = lint_vault(vault)
    contras = report.by_kind("CONTRADICTION")
    assert len(contras) >= 1


def test_lint_contradiction_with_supersession_no_issue(vault: Path) -> None:
    raw_a = new_ulid()
    raw_b = new_ulid()
    _raw(vault, raw_a)
    _raw(vault, raw_b)
    id_old = new_ulid()
    id_new = new_ulid()
    _wiki_page(vault, id_old, "Old Claim", [raw_a], contradicts=[id_new], superseded_by=id_new)
    _wiki_page(vault, id_new, "New Claim", [raw_b], supersedes=[id_old])
    report = lint_vault(vault)
    assert not report.by_kind("CONTRADICTION")


# ------------------------------------------------------------------
# DANGLING_REL
# ------------------------------------------------------------------

def test_lint_detects_dangling_relation(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id)
    page_id = new_ulid()
    ghost_id = new_ulid()
    _wiki_page(vault, page_id, "Page", [raw_id], relations=[
        {"type": "supports", "target_id": ghost_id}
    ])
    report = lint_vault(vault)
    dangling = report.by_kind("DANGLING_REL")
    assert len(dangling) == 1
    assert dangling[0].detail["relation"]["target_id"] == ghost_id


def test_lint_structural_only_skips_dangling(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id)
    page_id = new_ulid()
    ghost_id = new_ulid()
    _wiki_page(vault, page_id, "Page", [raw_id], relations=[
        {"type": "supports", "target_id": ghost_id}
    ])
    report = lint_vault(vault, structural_only=True)
    assert not report.by_kind("DANGLING_REL")


# ------------------------------------------------------------------
# report.by_kind
# ------------------------------------------------------------------

def test_lint_by_kind_filters_correctly(vault: Path) -> None:
    raw_id = new_ulid()
    _raw(vault, raw_id)
    report = lint_vault(vault)
    assert isinstance(report.by_kind("ORPHAN_RAW"), list)
