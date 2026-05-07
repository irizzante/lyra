"""Tests for M1.3 — OpenCode session reader."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from lyra.session.opencode import export_sessions, _known_session_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "opencode.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            parent_id TEXT,
            directory TEXT NOT NULL,
            title TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            model TEXT,
            slug TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '1'
        );
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            role TEXT,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE part (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL REFERENCES message(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL DEFAULT '{}'
        );
        """
    )
    # Insert two sessions
    conn.execute(
        "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("ses_001", "global", None, "/home/ivan/proj", "Test Session 1", 1_700_000_000_000, 1_700_000_001_000, "claude-sonnet-4", "", "1"),
    )
    conn.execute(
        "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("ses_002", "global", None, "/home/ivan/other", "Test Session 2", 1_700_000_100_000, 1_700_000_101_000, None, "", "1"),
    )
    # Messages for ses_001
    conn.execute(
        "INSERT INTO message VALUES (?,?,?,?,?,?)",
        ("msg_001", "ses_001", "user", 1_700_000_000_100, 1_700_000_000_100,
         json.dumps({"role": "user", "summary": "How does the pipeline work?"})),
    )
    conn.execute(
        "INSERT INTO message VALUES (?,?,?,?,?,?)",
        ("msg_002", "ses_001", "assistant", 1_700_000_000_200, 1_700_000_000_200,
         json.dumps({"role": "assistant", "summary": "The pipeline processes data in three stages."})),
    )
    conn.commit()
    conn.close()
    return db_path


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    return vault


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_export_sessions_creates_files(tmp_path):
    db = _make_db(tmp_path)
    vault = _make_vault(tmp_path)

    results = export_sessions(vault, db_path=db)

    assert len(results) == 2
    raw_dir = vault / "raw"
    session_files = [p for p in raw_dir.glob("*.md")]
    assert len(session_files) == 2


def test_export_sessions_frontmatter(tmp_path):
    db = _make_db(tmp_path)
    vault = _make_vault(tmp_path)

    results = export_sessions(vault, db_path=db)

    from lyra import markdown as md

    for r in results:
        doc = md.read(r.record_path)
        assert doc.frontmatter["kind"] == "session"
        assert doc.frontmatter["source"] == "opencode"
        assert doc.frontmatter["session_id"] in ("ses_001", "ses_002")
        assert doc.frontmatter["raw_id"] == r.raw_id


def test_export_sessions_message_body(tmp_path):
    db = _make_db(tmp_path)
    vault = _make_vault(tmp_path)

    results = export_sessions(vault, db_path=db)

    ses001 = next(r for r in results if r.session_id == "ses_001")
    body = ses001.record_path.read_text(encoding="utf-8")
    assert "How does the pipeline work" in body
    assert "three stages" in body


def test_export_sessions_idempotent(tmp_path):
    db = _make_db(tmp_path)
    vault = _make_vault(tmp_path)

    first = export_sessions(vault, db_path=db)
    assert len(first) == 2

    second = export_sessions(vault, db_path=db)
    assert len(second) == 0  # already exported


def test_export_sessions_model_in_frontmatter(tmp_path):
    db = _make_db(tmp_path)
    vault = _make_vault(tmp_path)

    results = export_sessions(vault, db_path=db)
    ses001 = next(r for r in results if r.session_id == "ses_001")

    from lyra import markdown as md

    doc = md.read(ses001.record_path)
    assert doc.frontmatter.get("model") == "claude-sonnet-4"


def test_export_sessions_no_model_omits_key(tmp_path):
    db = _make_db(tmp_path)
    vault = _make_vault(tmp_path)

    results = export_sessions(vault, db_path=db)
    ses002 = next(r for r in results if r.session_id == "ses_002")

    from lyra import markdown as md

    doc = md.read(ses002.record_path)
    assert "model" not in doc.frontmatter


def test_export_sessions_missing_db(tmp_path):
    vault = _make_vault(tmp_path)
    with pytest.raises(FileNotFoundError):
        export_sessions(vault, db_path=tmp_path / "nonexistent.db")


def test_known_session_ids(tmp_path):
    vault = _make_vault(tmp_path)
    db = _make_db(tmp_path)
    export_sessions(vault, db_path=db)

    known = _known_session_ids(vault / "raw")
    assert "ses_001" in known
    assert "ses_002" in known
