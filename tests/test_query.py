"""Tests for M1.7 — lyra query: parsing, merging, graph expansion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from lyra.query import (
    QueryHit,
    _parse_qmd_output,
    _merge_hits,
    format_results,
    hybrid_query,
)
from lyra import markdown as md
from lyra.index.graph_projection import GraphProjectionConfig, open_db, upsert_from_vault


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_QMD_OUTPUT = """\
qmd://lyra-wiki/sources/transformers.md:1 #ab1234
Title: Transformers Architecture
Score:  85%

@@ -1,5 @@ (0 before, 10 after)
id: ULID001
title: Transformers Architecture
type: source

qmd://lyra-wiki/sources/attention.md:1 #cd5678
Title: Attention Mechanism
Score:  72%

@@ -1,3 @@ (0 before, 8 after)
id: ULID002
title: Attention Mechanism
type: source

"""


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    sources = vault / "wiki" / "sources"
    sources.mkdir(parents=True)
    return vault


def _write_page(vault: Path, filename: str, page_id: str, title: str) -> Path:
    path = vault / "wiki" / "sources" / filename
    md.write(path, md.Document(
        frontmatter={
            "id": page_id,
            "title": title,
            "type": "source",
            "confidence": 0.7,
            "last_confirmed": "2026-05-06",
        },
        body=f"# {title}\n\nBody.",
    ))
    return path


# ---------------------------------------------------------------------------
# Tests: _parse_qmd_output
# ---------------------------------------------------------------------------


def test_parse_qmd_output_count(tmp_path):
    vault = _make_vault(tmp_path)
    hits = _parse_qmd_output(SAMPLE_QMD_OUTPUT, wiki_root=vault / "wiki")
    assert len(hits) == 2


def test_parse_qmd_output_titles(tmp_path):
    vault = _make_vault(tmp_path)
    hits = _parse_qmd_output(SAMPLE_QMD_OUTPUT, wiki_root=vault / "wiki")
    titles = [h.title for h in hits]
    assert "Transformers Architecture" in titles
    assert "Attention Mechanism" in titles


def test_parse_qmd_output_scores(tmp_path):
    vault = _make_vault(tmp_path)
    hits = _parse_qmd_output(SAMPLE_QMD_OUTPUT, wiki_root=vault / "wiki")
    assert abs(hits[0].score - 0.85) < 0.01
    assert abs(hits[1].score - 0.72) < 0.01


def test_parse_qmd_output_reads_frontmatter(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "transformers.md", "ULID001", "Transformers Architecture")
    hits = _parse_qmd_output(SAMPLE_QMD_OUTPUT, wiki_root=vault / "wiki")
    t_hit = next(h for h in hits if "Transform" in h.title)
    assert t_hit.id == "ULID001"
    assert t_hit.last_seen == "2026-05-06"


def test_parse_qmd_output_empty(tmp_path):
    vault = _make_vault(tmp_path)
    hits = _parse_qmd_output("", wiki_root=vault / "wiki")
    assert hits == []


def test_parse_qmd_output_no_hits(tmp_path):
    vault = _make_vault(tmp_path)
    hits = _parse_qmd_output("No results found.", wiki_root=vault / "wiki")
    assert hits == []


# ---------------------------------------------------------------------------
# Tests: _merge_hits
# ---------------------------------------------------------------------------


def _make_hit(file_path: str, score: float, page_id: str = "") -> QueryHit:
    return QueryHit(
        id=page_id, source="lyra-wiki", title=file_path,
        snippet="", score=score, file_path=file_path,
        last_seen="", citations=[],
    )


def test_merge_hits_deduplicates(tmp_path):
    vault = _make_vault(tmp_path)
    h1 = _make_hit("/wiki/a.md", 0.9)
    h2 = _make_hit("/wiki/a.md", 0.8)
    merged = _merge_hits([h1], [h2], vault_path=vault)
    assert len(merged) == 1


def test_merge_hits_combines_unique(tmp_path):
    vault = _make_vault(tmp_path)
    h1 = _make_hit("/wiki/a.md", 0.9)
    h2 = _make_hit("/wiki/b.md", 0.8)
    merged = _merge_hits([h1], [h2], vault_path=vault)
    assert len(merged) == 2


def test_merge_hits_rrf_boosts_overlap(tmp_path):
    vault = _make_vault(tmp_path)
    shared = _make_hit("/wiki/shared.md", 0.9)
    unique_bm25 = _make_hit("/wiki/bm25.md", 0.5)
    unique_vec = _make_hit("/wiki/vec.md", 0.4)
    merged = _merge_hits([shared, unique_bm25], [shared, unique_vec], vault_path=vault)
    shared_hit = next(h for h in merged if "shared" in h.file_path)
    bm25_hit = next(h for h in merged if "bm25" in h.file_path)
    # Shared appears in both lists → higher RRF score
    assert shared_hit.score > bm25_hit.score


# ---------------------------------------------------------------------------
# Tests: format_results
# ---------------------------------------------------------------------------


def test_format_results_empty():
    assert "No results" in format_results([])


def test_format_results_lists_titles():
    hits = [
        QueryHit(id="U1", source="lyra-wiki", title="Transformers", snippet="...",
                 score=0.85, file_path="/wiki/t.md", last_seen="2026-05-06",
                 citations=["sources/t.md"]),
    ]
    output = format_results(hits)
    assert "Transformers" in output
    assert "sources/t.md" in output


def test_format_results_graph_tag():
    hits = [
        QueryHit(id="U2", source="lyra-wiki", title="Related Page", snippet="",
                 score=0.4, file_path="/wiki/r.md", last_seen="",
                 citations=[], via_graph=True),
    ]
    output = format_results(hits)
    assert "[graph]" in output


# ---------------------------------------------------------------------------
# Tests: hybrid_query (integration with mocked qmd)
# ---------------------------------------------------------------------------


def test_hybrid_query_bm25_only(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "transformers.md", "ULID001", "Transformers Architecture")

    mock_bm25 = MagicMock(spec=subprocess.CompletedProcess)
    mock_bm25.returncode = 0
    mock_bm25.stdout = SAMPLE_QMD_OUTPUT

    mock_vec = MagicMock(spec=subprocess.CompletedProcess)
    mock_vec.returncode = 1
    mock_vec.stdout = ""

    with patch("lyra.query.subprocess.run") as mock_run:
        mock_run.side_effect = [mock_bm25, mock_vec]
        hits = hybrid_query("transformers", vault, k=5, use_vector=False)

    assert len(hits) >= 1


def test_hybrid_query_returns_list(tmp_path):
    vault = _make_vault(tmp_path)

    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = ""

    with patch("lyra.query.subprocess.run", return_value=mock_result):
        hits = hybrid_query("anything", vault, k=5)

    assert isinstance(hits, list)


def test_hybrid_query_graph_expansion(tmp_path):
    vault = _make_vault(tmp_path)
    _write_page(vault, "transformers.md", "ULID001", "Transformers Architecture")
    _write_page(vault, "attention.md", "ULID002", "Attention Mechanism")

    # Populate graph
    cfg = GraphProjectionConfig(db_path=tmp_path / "graph.sqlite")
    conn = open_db(cfg)
    upsert_from_vault(vault, conn)

    # Manually insert an edge
    conn.execute(
        "INSERT INTO edges VALUES ('ULID001','supports','ULID002',0.9,'2026-05-06')"
    )
    conn.commit()
    conn.close()

    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    # Only return ULID001 from search; ULID002 should be found via graph
    mock_result.stdout = """\
qmd://lyra-wiki/sources/transformers.md:1 #ab1234
Title: Transformers Architecture
Score:  80%

@@ -1,2 @@
id: ULID001

"""

    with patch("lyra.query.subprocess.run", return_value=mock_result):
        hits = hybrid_query("transformers", vault, k=10, graph_config=cfg)

    ids = [h.id for h in hits]
    assert "ULID001" in ids
    graph_hits = [h for h in hits if h.via_graph]
    assert any(h.id == "ULID002" for h in graph_hits)
