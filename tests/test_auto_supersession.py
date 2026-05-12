"""Tests for M3.8 (auto-supersession scoring) and M3.9 (lint score breakdown)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra import markdown as md
from lyra.compile_pipeline import (
    _auto_supersede_pass,
    _recency,
    _authority,
    _inbound_supports,
    score_page,
    CompileReport,
)
from lyra.lint import lint_vault
from lyra.config import AutoSupersessionWeights


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    (vault / "wiki" / "sources").mkdir(parents=True)
    return vault


def _write_wiki(vault: Path, name: str, fm: dict, body: str = "") -> Path:
    path = vault / "wiki" / "sources" / name
    fm_with_path = {**fm}
    doc = md.Document(frontmatter=fm_with_path, body=body)
    md.write(path, doc)
    return path


# ---------------------------------------------------------------------------
# Unit: scoring components
# ---------------------------------------------------------------------------

def test_recency_oldest_is_zero():
    dates = ["2024-01-01", "2024-06-01", "2024-12-01"]
    assert _recency("2024-01-01", dates) == 0.0


def test_recency_newest_is_one():
    dates = ["2024-01-01", "2024-06-01", "2024-12-01"]
    assert _recency("2024-12-01", dates) == 1.0


def test_recency_midpoint():
    dates = ["2024-01-01", "2024-07-02", "2025-01-01"]
    # 2024-07-02 is ~182 days from 2024-01-01, total 366 days → ~0.497
    val = _recency("2024-07-02", dates)
    assert 0.4 < val < 0.6


def test_recency_empty_dates():
    assert _recency("2024-06-01", []) == 0.0


def test_recency_all_same():
    dates = ["2024-06-01", "2024-06-01"]
    assert _recency("2024-06-01", dates) == 1.0


def test_authority_no_sources():
    assert _authority({"sources": []}) == 0.0


def test_authority_five_sources():
    assert _authority({"sources": ["a", "b", "c", "d", "e"]}) == 1.0


def test_authority_caps_at_one():
    assert _authority({"sources": list(range(10))}) == 1.0


def test_authority_two_sources():
    assert _authority({"sources": ["a", "b"]}) == pytest.approx(0.4)


def test_inbound_supports_zero():
    wiki_index = {
        "P1": {"relations": [{"type": "uses", "target_id": "P2"}]},
        "P2": {},
    }
    assert _inbound_supports("P2", wiki_index) == 0.0


def test_inbound_supports_one():
    wiki_index = {
        "P1": {"relations": [{"type": "supports", "target_id": "P2"}]},
        "P2": {},
    }
    assert _inbound_supports("P2", wiki_index) == pytest.approx(0.2)


def test_inbound_supports_caps_at_one():
    wiki_index = {
        f"P{i}": {"relations": [{"type": "supports", "target_id": "TARGET"}]}
        for i in range(10)
    }
    wiki_index["TARGET"] = {}
    assert _inbound_supports("TARGET", wiki_index) == 1.0


def test_score_page_total_bounded():
    w = AutoSupersessionWeights()
    wiki_index = {"P1": {"sources": ["s1", "s2"], "last_confirmed": "2024-06-01"}}
    all_dates = ["2024-01-01", "2024-06-01", "2025-01-01"]
    result = score_page("P1", wiki_index["P1"], wiki_index, all_dates, w)
    assert 0.0 <= result["total"] <= 1.0
    assert "recency" in result
    assert "authority" in result
    assert "support" in result


# ---------------------------------------------------------------------------
# Integration: M3.8 auto-supersession pass
# ---------------------------------------------------------------------------

def test_auto_supersede_winner_gets_supersedes(tmp_path):
    vault = _make_vault(tmp_path)

    # A is newer (higher recency) with more sources → should win
    _write_wiki(vault, "a.md", {
        "id": "ULID_A",
        "title": "A",
        "type": "source",
        "sources": ["r1", "r2", "r3"],
        "confidence": 0.8,
        "created": "2024-01-01",
        "last_confirmed": "2024-12-01",
        "supersedes": [],
        "superseded_by": None,
        "contradicts": ["ULID_B"],
        "relations": [],
    })
    _write_wiki(vault, "b.md", {
        "id": "ULID_B",
        "title": "B",
        "type": "source",
        "sources": [],
        "confidence": 0.3,
        "created": "2024-01-01",
        "last_confirmed": "2024-01-01",
        "supersedes": [],
        "superseded_by": None,
        "contradicts": [],
        "relations": [],
    })

    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])
    _auto_supersede_pass(vault, report)

    assert len(report.supersession_decisions) == 1
    d = report.supersession_decisions[0]
    assert d["winner"] == "ULID_A"
    assert d["loser"] == "ULID_B"
    assert d["diff"] >= 0.2

    # Winner frontmatter updated
    a_doc = md.read(vault / "wiki" / "sources" / "a.md")
    assert "ULID_B" in [str(x) for x in (a_doc.frontmatter.get("supersedes") or [])]

    # Loser frontmatter updated
    b_doc = md.read(vault / "wiki" / "sources" / "b.md")
    assert str(b_doc.frontmatter.get("superseded_by")) == "ULID_A"


def test_auto_supersede_close_scores_not_resolved(tmp_path):
    vault = _make_vault(tmp_path)

    # Both same date, same sources → diff will be 0
    for pid, name in [("ULID_A", "a.md"), ("ULID_B", "b.md")]:
        _write_wiki(vault, name, {
            "id": pid,
            "title": pid,
            "type": "source",
            "sources": ["r1"],
            "confidence": 0.5,
            "created": "2024-06-01",
            "last_confirmed": "2024-06-01",
            "supersedes": [],
            "superseded_by": None,
            "contradicts": ["ULID_B" if pid == "ULID_A" else "ULID_A"],
            "relations": [],
        })

    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])
    _auto_supersede_pass(vault, report)

    assert len(report.supersession_decisions) == 0


def test_auto_supersede_already_superseded_skipped(tmp_path):
    vault = _make_vault(tmp_path)

    # A already explicitly supersedes B — pass should not touch it
    _write_wiki(vault, "a.md", {
        "id": "ULID_A",
        "title": "A",
        "type": "source",
        "sources": ["r1", "r2", "r3"],
        "confidence": 0.9,
        "created": "2024-01-01",
        "last_confirmed": "2024-12-01",
        "supersedes": ["ULID_B"],
        "superseded_by": None,
        "contradicts": ["ULID_B"],
        "relations": [],
    })
    _write_wiki(vault, "b.md", {
        "id": "ULID_B",
        "title": "B",
        "type": "source",
        "sources": [],
        "confidence": 0.2,
        "created": "2024-01-01",
        "last_confirmed": "2024-01-01",
        "supersedes": [],
        "superseded_by": "ULID_A",
        "contradicts": [],
        "relations": [],
    })

    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])
    _auto_supersede_pass(vault, report)

    assert len(report.supersession_decisions) == 0


def test_auto_supersede_pair_seen_only_once(tmp_path):
    vault = _make_vault(tmp_path)

    # Both declare contradicts → same pair, should only be processed once
    _write_wiki(vault, "a.md", {
        "id": "ULID_A", "title": "A", "type": "source",
        "sources": ["r1", "r2", "r3"], "confidence": 0.8,
        "created": "2024-01-01", "last_confirmed": "2024-12-01",
        "supersedes": [], "superseded_by": None,
        "contradicts": ["ULID_B"], "relations": [],
    })
    _write_wiki(vault, "b.md", {
        "id": "ULID_B", "title": "B", "type": "source",
        "sources": [], "confidence": 0.2,
        "created": "2024-01-01", "last_confirmed": "2024-01-01",
        "supersedes": [], "superseded_by": None,
        "contradicts": ["ULID_A"], "relations": [],
    })

    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])
    _auto_supersede_pass(vault, report)

    assert len(report.supersession_decisions) == 1


# ---------------------------------------------------------------------------
# Integration: M3.9 lint score breakdown
# ---------------------------------------------------------------------------

def test_lint_contradiction_has_score_breakdown(tmp_path):
    vault = _make_vault(tmp_path)

    for pid, name, date_str in [
        ("ULID_A", "a.md", "2024-06-01"),
        ("ULID_B", "b.md", "2024-06-01"),
    ]:
        _write_wiki(vault, name, {
            "id": pid, "title": pid, "type": "source",
            "sources": ["r1"], "confidence": 0.5,
            "created": "2024-01-01", "last_confirmed": date_str,
            "supersedes": [], "superseded_by": None,
            "contradicts": ["ULID_B" if pid == "ULID_A" else "ULID_A"],
            "relations": [],
        })

    report = lint_vault(vault)
    contradictions = report.by_kind("CONTRADICTION")
    assert len(contradictions) == 1

    issue = contradictions[0]
    assert "scores" in issue.detail
    assert "diff" in issue.detail
    assert "threshold" in issue.detail
    scores = issue.detail["scores"]
    assert "ULID_A" in scores
    assert "ULID_B" in scores
    for sc in scores.values():
        assert "recency" in sc
        assert "authority" in sc
        assert "support" in sc
        assert "total" in sc


def test_lint_contradiction_deduped(tmp_path):
    vault = _make_vault(tmp_path)

    # Both A and B list each other in contradicts — lint should emit only 1 issue
    for pid, name in [("ULID_A", "a.md"), ("ULID_B", "b.md")]:
        _write_wiki(vault, name, {
            "id": pid, "title": pid, "type": "source",
            "sources": ["r1"], "confidence": 0.5,
            "created": "2024-01-01", "last_confirmed": "2024-06-01",
            "supersedes": [], "superseded_by": None,
            "contradicts": ["ULID_B" if pid == "ULID_A" else "ULID_A"],
            "relations": [],
        })

    report = lint_vault(vault)
    assert len(report.by_kind("CONTRADICTION")) == 1


def test_lint_no_contradiction_after_auto_supersession(tmp_path):
    vault = _make_vault(tmp_path)

    # Auto-supersession already resolved A supersedes B
    _write_wiki(vault, "a.md", {
        "id": "ULID_A", "title": "A", "type": "source",
        "sources": ["r1", "r2"], "confidence": 0.8,
        "created": "2024-01-01", "last_confirmed": "2024-12-01",
        "supersedes": ["ULID_B"], "superseded_by": None,
        "contradicts": ["ULID_B"], "relations": [],
    })
    _write_wiki(vault, "b.md", {
        "id": "ULID_B", "title": "B", "type": "source",
        "sources": [], "confidence": 0.3,
        "created": "2024-01-01", "last_confirmed": "2024-01-01",
        "supersedes": [], "superseded_by": "ULID_A",
        "contradicts": [], "relations": [],
    })

    report = lint_vault(vault)
    assert len(report.by_kind("CONTRADICTION")) == 0
