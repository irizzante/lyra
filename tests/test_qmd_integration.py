"""Mocked integration tests for qmd search/vsearch CLI invocation (M1.6/M1.7)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lyra.index.qmd_index import QmdIndexConfig, search, COLLECTION_NAME
from lyra.query import hybrid_query, _run_qmd_search, _parse_qmd_output


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    wiki = tmp_path / "vault" / "wiki"
    wiki.mkdir(parents=True)
    return tmp_path / "vault"


@pytest.fixture
def qmd_cfg(vault: Path) -> QmdIndexConfig:
    return QmdIndexConfig(vault_path=vault)


# ---------------------------------------------------------------------------
# Sample qmd output (format as of qmd 2.1.0)
# ---------------------------------------------------------------------------

_SAMPLE_OUTPUT = """\
qmd://lyra-wiki/sources/attention.md:1 #abc123
Title: Attention Mechanism
Score: 87.42%
@@ context
Attention allows models to focus on relevant tokens.

qmd://lyra-wiki/concepts/transformer.md:1 #def456
Title: Transformer Architecture
Score: 72.10%
@@ context
Transformers use self-attention in every layer.
"""


# ---------------------------------------------------------------------------
# _parse_qmd_output / _parse_hits
# ---------------------------------------------------------------------------


def test_parse_qmd_output_returns_hits(vault: Path) -> None:
    hits = _parse_qmd_output(_SAMPLE_OUTPUT, wiki_root=vault / "wiki")
    assert len(hits) == 2


def test_parse_qmd_output_titles(vault: Path) -> None:
    hits = _parse_qmd_output(_SAMPLE_OUTPUT, wiki_root=vault / "wiki")
    titles = [h.title for h in hits]
    assert "Attention Mechanism" in titles
    assert "Transformer Architecture" in titles


def test_parse_qmd_output_scores(vault: Path) -> None:
    hits = _parse_qmd_output(_SAMPLE_OUTPUT, wiki_root=vault / "wiki")
    scores = {h.title: h.score for h in hits}
    assert abs(scores["Attention Mechanism"] - 0.8742) < 0.001
    assert abs(scores["Transformer Architecture"] - 0.7210) < 0.001


def test_parse_qmd_output_snippets(vault: Path) -> None:
    hits = _parse_qmd_output(_SAMPLE_OUTPUT, wiki_root=vault / "wiki")
    attention = next(h for h in hits if "Attention" in h.title)
    assert "relevant tokens" in attention.snippet


def test_parse_qmd_output_empty(vault: Path) -> None:
    hits = _parse_qmd_output("", wiki_root=vault / "wiki")
    assert hits == []


def test_parse_qmd_output_malformed_skipped(vault: Path) -> None:
    bad = "not a qmd:// line\nrandom text"
    hits = _parse_qmd_output(bad, wiki_root=vault / "wiki")
    assert hits == []


# ---------------------------------------------------------------------------
# search() uses -n and -c flags
# ---------------------------------------------------------------------------


def _make_proc(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_search_passes_n_flag(qmd_cfg: QmdIndexConfig) -> None:
    with patch("lyra.index.qmd_index._run_qmd") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        search(qmd_cfg, "attention", k=5)
        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd
        assert "--limit" not in cmd


def test_search_passes_collection_flag(qmd_cfg: QmdIndexConfig) -> None:
    with patch("lyra.index.qmd_index._run_qmd") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        search(qmd_cfg, "attention", k=5)
        cmd = mock_run.call_args[0][0]
        assert "-c" in cmd
        assert COLLECTION_NAME in cmd


def test_search_n_value_is_2k(qmd_cfg: QmdIndexConfig) -> None:
    with patch("lyra.index.qmd_index._run_qmd") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        search(qmd_cfg, "attention", k=7)
        cmd = mock_run.call_args[0][0]
        n_idx = cmd.index("-n")
        assert cmd[n_idx + 1] == "14"  # k * 2


def test_search_returns_at_most_k(qmd_cfg: QmdIndexConfig) -> None:
    with patch("lyra.index.qmd_index._run_qmd") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        hits = search(qmd_cfg, "attention", k=1)
        assert len(hits) == 1


# ---------------------------------------------------------------------------
# hybrid_query() via _run_qmd_search
# ---------------------------------------------------------------------------


def test_run_qmd_search_bm25_uses_search_cmd(vault: Path) -> None:
    with patch("lyra.query.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        _run_qmd_search("attention", k=5, vector=False, wiki_root=vault / "wiki")
        cmd = mock_run.call_args[0][0]
        assert cmd[1] == "search"
        assert "-n" in cmd
        assert "--limit" not in cmd


def test_run_qmd_search_vector_uses_vsearch_cmd(vault: Path) -> None:
    with patch("lyra.query.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        _run_qmd_search("attention", k=5, vector=True, wiki_root=vault / "wiki")
        cmd = mock_run.call_args[0][0]
        assert cmd[1] == "vsearch"


def test_run_qmd_search_passes_collection_flag(vault: Path) -> None:
    with patch("lyra.query.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        _run_qmd_search("attention", k=5, vector=False, wiki_root=vault / "wiki")
        cmd = mock_run.call_args[0][0]
        assert "-c" in cmd
        assert COLLECTION_NAME in cmd


def test_hybrid_query_returns_empty_on_qmd_failure(vault: Path) -> None:
    with patch("lyra.query.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc("", returncode=1)
        hits = hybrid_query("attention", vault, k=5, use_vector=False)
        assert hits == []


def test_hybrid_query_returns_hits_on_success(vault: Path) -> None:
    with patch("lyra.query.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc(_SAMPLE_OUTPUT)
        hits = hybrid_query("attention", vault, k=5, use_vector=False)
        assert len(hits) == 2
        assert hits[0].score >= hits[-1].score  # descending order
