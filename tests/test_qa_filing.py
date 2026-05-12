"""Tests for lyra file Q&A filing workflow (M1.12).

Verifies that file_answer():
- Creates wiki/qa/<ulid>-<slug>.md
- Writes type: qa frontmatter with required fields
- Body contains question text
- Each call creates a distinct file
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra.file_cmd import file_answer, FileResult
from lyra.ids import is_ulid
from lyra.markdown import read
from lyra.vault import ensure_layout


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    ensure_layout(v)
    return v


def test_file_answer_creates_qa_file(vault: Path) -> None:
    result = file_answer("What is attention mechanism?", vault, use_vector=False)

    assert isinstance(result, FileResult)
    assert result.qa_path.exists()
    assert result.qa_path.parent == vault / "wiki" / "qa"


def test_file_answer_qa_path_has_ulid_prefix(vault: Path) -> None:
    result = file_answer("What is BM25?", vault, use_vector=False)
    stem = result.qa_path.stem
    assert is_ulid(stem.split("-")[0])
    assert is_ulid(result.qa_id)


def test_file_answer_frontmatter_type_is_qa(vault: Path) -> None:
    result = file_answer("What is a ULID?", vault, use_vector=False)
    doc = read(result.qa_path)
    assert doc.frontmatter["type"] == "qa"


def test_file_answer_frontmatter_required_fields(vault: Path) -> None:
    question = "How does graph expansion work?"
    result = file_answer(question, vault, use_vector=False)
    doc = read(result.qa_path)

    assert doc.frontmatter["id"] == result.qa_id
    assert doc.frontmatter["title"] == question
    assert doc.frontmatter["question"] == question
    assert isinstance(doc.frontmatter["sources"], list)
    assert isinstance(doc.frontmatter["confidence"], float)
    assert "created" in doc.frontmatter
    assert "last_confirmed" in doc.frontmatter


def test_file_answer_body_contains_question(vault: Path) -> None:
    question = "What is supersession in ADR-8?"
    result = file_answer(question, vault, use_vector=False)
    doc = read(result.qa_path)
    assert question in doc.body


def test_file_answer_each_call_creates_unique_file(vault: Path) -> None:
    r1 = file_answer("Repeated question", vault, use_vector=False)
    r2 = file_answer("Repeated question", vault, use_vector=False)
    assert r1.qa_path != r2.qa_path
    assert r1.qa_id != r2.qa_id


def test_file_answer_qa_dir_created_automatically(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    ensure_layout(vault)
    qa_dir = vault / "wiki" / "qa"

    result = file_answer("auto-create test", vault, use_vector=False)

    assert qa_dir.exists()
    assert result.qa_path.exists()


def test_file_answer_result_has_answer_string(vault: Path) -> None:
    result = file_answer("What is Lyra?", vault, use_vector=False)
    assert isinstance(result.answer, str)


def test_file_answer_result_has_source_ids_list(vault: Path) -> None:
    result = file_answer("Any question", vault, use_vector=False)
    assert isinstance(result.source_ids, list)
