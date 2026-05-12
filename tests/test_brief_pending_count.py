"""Tests for M3.10 — brief raw-pending count section."""

from __future__ import annotations

from pathlib import Path

from lyra import markdown as md
from lyra.brief import generate_brief
from lyra.ids import new_ulid


def _write_raw(raw_dir: Path, raw_id: str, kind: str = "research") -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    md.write(
        raw_dir / f"{raw_id}.md",
        md.Document(
            frontmatter={"raw_id": raw_id, "kind": kind, "title": f"Raw {raw_id}"},
            body="Body text.",
        ),
    )


def _write_wiki_source(sources_dir: Path, sources: list[str]) -> None:
    sources_dir.mkdir(parents=True, exist_ok=True)
    page_id = new_ulid()
    md.write(
        sources_dir / f"{page_id}.md",
        md.Document(
            frontmatter={
                "id": page_id,
                "type": "source",
                "title": f"Wiki {page_id}",
                "sources": sources,
                "confidence": 0.5,
                "created": "2026-01-01",
                "last_confirmed": "2026-01-01",
                "supersedes": [],
                "superseded_by": None,
                "relations": [],
            },
            body=f"# Wiki {page_id}\n",
        ),
    )


def test_brief_no_raw_dir(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    brief = generate_brief(vault)
    assert "📋" not in brief
    assert "pending promotion" not in brief


def test_brief_zero_pending_no_raw_files(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    brief = generate_brief(vault)
    assert "📋" not in brief


def test_brief_three_pending(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    raw_dir = vault / "raw"
    for _ in range(3):
        _write_raw(raw_dir, new_ulid())
    brief = generate_brief(vault)
    assert "📋 3 raw pages pending promotion" in brief


def test_brief_promoted_page_excluded(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    raw_dir = vault / "raw"
    sources_dir = vault / "wiki" / "sources"

    promoted_id = new_ulid()
    pending_id1 = new_ulid()
    pending_id2 = new_ulid()

    _write_raw(raw_dir, promoted_id)
    _write_raw(raw_dir, pending_id1)
    _write_raw(raw_dir, pending_id2)
    _write_wiki_source(sources_dir, [promoted_id])

    brief = generate_brief(vault)
    assert "📋 2 raw pages pending promotion" in brief


def test_brief_all_promoted_no_notice(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    raw_dir = vault / "raw"
    sources_dir = vault / "wiki" / "sources"

    raw_id1 = new_ulid()
    raw_id2 = new_ulid()
    _write_raw(raw_dir, raw_id1)
    _write_raw(raw_dir, raw_id2)
    _write_wiki_source(sources_dir, [raw_id1, raw_id2])

    brief = generate_brief(vault)
    assert "📋" not in brief
    assert "pending promotion" not in brief
