"""Tests for ``lyra file`` Q&A filing (M1.12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.file_cmd import file_answer
from lyra.ids import is_ulid
from lyra.markdown import read
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def test_file_answer_creates_qa_file(vault: Path) -> None:
    result = file_answer("What is attention?", vault, use_vector=False)

    assert result.qa_path.exists()
    assert result.qa_path.parent == vault / "wiki" / "qa"
    assert is_ulid(result.qa_id)


def test_file_answer_frontmatter(vault: Path) -> None:
    result = file_answer("How does BM25 work?", vault, use_vector=False)

    doc = read(result.qa_path)
    assert doc.frontmatter["type"] == "qa"
    assert doc.frontmatter["question"] == "How does BM25 work?"
    assert doc.frontmatter["title"] == "How does BM25 work?"
    assert is_ulid(doc.frontmatter["id"])
    assert "created" in doc.frontmatter
    assert "last_confirmed" in doc.frontmatter
    assert isinstance(doc.frontmatter["sources"], list)
    assert isinstance(doc.frontmatter["confidence"], float)


def test_file_answer_body_contains_question(vault: Path) -> None:
    result = file_answer("What is a ULID?", vault, use_vector=False)
    doc = read(result.qa_path)
    assert "What is a ULID?" in doc.body


def test_file_answer_idempotent_creates_new_file(vault: Path) -> None:
    r1 = file_answer("Same question", vault, use_vector=False)
    r2 = file_answer("Same question", vault, use_vector=False)
    assert r1.qa_path != r2.qa_path  # each call creates a new Q&A record
    assert r1.qa_id != r2.qa_id


def test_file_answer_qa_dir_created_if_absent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    ensure_layout(vault)
    qa_dir = vault / "wiki" / "qa"
    assert not qa_dir.exists() or not list(qa_dir.glob("*.md"))

    result = file_answer("test question", vault, use_vector=False)
    assert qa_dir.exists()
    assert result.qa_path.exists()
