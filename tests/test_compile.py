"""Tests for ``lyra compile`` (M1.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.compile_pipeline import compile_vault
from lyra.ids import is_ulid
from lyra.ingest import ingest
from lyra.markdown import read
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def _make_research(vault: Path, tmp_path: Path, name: str, body: str) -> str:
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    return ingest(str(src), vault_path=vault, kind="research").raw_id


def test_compile_promotes_research_into_wiki_sources(vault: Path, tmp_path: Path) -> None:
    raw_id = _make_research(vault, tmp_path, "note.md", "# A note\n\nbody.\n")

    report = compile_vault(vault)
    assert len(report.promoted) == 1
    assert not report.errors

    page = report.promoted[0]
    assert page.parent == vault / "wiki" / "sources"

    doc = read(page)
    assert is_ulid(doc.frontmatter["id"])
    assert doc.frontmatter["type"] == "source"
    assert raw_id in doc.frontmatter["sources"]
    assert doc.frontmatter["confidence"] == 0.5
    assert "created" in doc.frontmatter
    assert "last_confirmed" in doc.frontmatter


def test_compile_idempotent_updates_last_confirmed(vault: Path, tmp_path: Path) -> None:
    _make_research(vault, tmp_path, "note.md", "# Note\n\nbody.\n")

    first = compile_vault(vault)
    assert len(first.promoted) == 1
    page_path = first.promoted[0]

    second = compile_vault(vault)
    assert len(second.promoted) == 0
    assert len(second.updated) == 1
    assert second.updated[0] == page_path


def test_compile_resolves_inline_supports_to_target_id(vault: Path, tmp_path: Path) -> None:
    # First note becomes a wiki page with title "Foundation".
    foundation_src = tmp_path / "foundation.md"
    foundation_src.write_text("# Foundation\n\ncore claim.\n", encoding="utf-8")
    ingest(str(foundation_src), vault_path=vault, kind="research", title="Foundation")
    compile_vault(vault)

    # Second note references the first via inline relation.
    follow_src = tmp_path / "follow.md"
    follow_src.write_text(
        "# Follow-up\n\nsupports:: [[Foundation]]\n\nMore prose.\n", encoding="utf-8"
    )
    ingest(str(follow_src), vault_path=vault, kind="research", title="Follow-up")

    report = compile_vault(vault)
    follow_page = next(p for p in report.promoted if "follow" in p.name)
    doc = read(follow_page)
    rels = doc.frontmatter["relations"]
    assert any(
        r.get("type") == "supports" and is_ulid(str(r.get("target_id", "")))
        for r in rels
    )


def test_compile_two_pass_resolves_cross_page_in_single_run(
    vault: Path, tmp_path: Path
) -> None:
    """Pass 2 resolves a relation whose target is promoted in the same compile."""
    foundation_src = tmp_path / "foundation.md"
    foundation_src.write_text("# Foundation\n\ncore.\n", encoding="utf-8")
    follow_src = tmp_path / "follow.md"
    follow_src.write_text(
        "# Follow-up\n\nsupports:: [[Foundation]]\n", encoding="utf-8"
    )
    ingest(str(foundation_src), vault_path=vault, kind="research", title="Foundation")
    ingest(str(follow_src), vault_path=vault, kind="research", title="Follow-up")

    report = compile_vault(vault)
    assert len(report.promoted) == 2

    follow_page = next(p for p in report.promoted if "follow" in p.name)
    doc = read(follow_page)
    rels = doc.frontmatter["relations"]
    supports_rels = [r for r in rels if r.get("type") == "supports"]
    assert supports_rels, "expected a 'supports' relation to be present"
    assert all(is_ulid(str(r.get("target_id", ""))) for r in supports_rels), (
        f"expected target_id ULID, got: {supports_rels}"
    )
    assert all("target" not in r for r in supports_rels), (
        "unresolved target should be replaced after pass 2"
    )


def test_compile_writes_index_and_log(vault: Path, tmp_path: Path) -> None:
    _make_research(vault, tmp_path, "note.md", "# Note\n\nbody.\n")
    compile_vault(vault)

    index = (vault / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "Wiki Index" in index
    assert "sources/" in index

    log = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "promoted=1" in log
