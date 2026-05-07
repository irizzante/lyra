"""M1.3 — OpenCode session reader (filesystem-based, post-hoc).

Reads sessions from ``~/.local/share/opencode/opencode.db`` and writes
structured session artifacts flat under ``raw/`` (ADR-6: kind: session).

Session artifact frontmatter:
  raw_id:        <ULID>
  kind:          session
  source:        opencode
  session_id:    <OpenCode session id>
  session_title: <title>
  directory:     <working directory of the session>
  time_created:  <ISO 8601>
  ingested_at:   <ISO 8601>
  content_type:  text/markdown
  model:         <model string, if present>

Body: session title, then each message with role + summary text.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from lyra.ids import new_ulid
from lyra import markdown as md

DEFAULT_OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

# Stop loading message content once body exceeds this many characters.
_BODY_CHAR_LIMIT = 16_000


@dataclass
class ExportResult:
    session_id: str
    raw_id: str
    record_path: Path


def export_sessions(
    vault_path: Path,
    *,
    db_path: Path = DEFAULT_OPENCODE_DB,
    limit: int = 50,
    since_ms: int | None = None,
) -> list[ExportResult]:
    """Export OpenCode sessions that have not yet been written to flat raw/.

    Returns one ``ExportResult`` per newly written session artifact.
    Idempotent: sessions already present in raw/ (matched via ``session_id``
    frontmatter in kind=session records) are skipped.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"OpenCode DB not found: {db_path}")

    raw_dir = vault_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    known = _known_session_ids(raw_dir)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_sessions(conn, limit=limit, since_ms=since_ms)
        results: list[ExportResult] = []
        for row in rows:
            sid = row["id"]
            if sid in known:
                continue
            result = _write_session(conn, row, raw_dir, vault_path)
            results.append(result)
        return results
    finally:
        conn.close()


def _known_session_ids(raw_dir: Path) -> set[str]:
    ids: set[str] = set()
    for path in raw_dir.glob("*.md"):
        doc = md.read(path)
        sid = doc.frontmatter.get("session_id")
        if sid:
            ids.add(str(sid))
    return ids


def _fetch_sessions(
    conn: sqlite3.Connection,
    limit: int,
    since_ms: int | None,
) -> Sequence[sqlite3.Row]:
    sql = "SELECT id, project_id, directory, title, time_created, time_updated, model FROM session"
    params: list[object] = []
    if since_ms is not None:
        sql += " WHERE time_created > ?"
        params.append(since_ms)
    sql += " ORDER BY time_created DESC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def _fetch_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, role, data FROM message WHERE session_id = ? ORDER BY time_created ASC",
        (session_id,),
    ).fetchall()
    # message.data is stored as JSON; extract role and summary
    messages = []
    for row in rows:
        try:
            data = json.loads(row["data"]) if isinstance(row["data"], str) else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        role = data.get("role") or row["role"] or "unknown"
        summary = data.get("summary") or ""
        if not summary:
            # fall back to part content
            summary = _concat_parts(conn, row["id"])
        messages.append({"role": role, "summary": summary})
    return messages


def _concat_parts(conn: sqlite3.Connection, message_id: str) -> str:
    rows = conn.execute(
        "SELECT data FROM part WHERE message_id = ? ORDER BY time_created ASC",
        (message_id,),
    ).fetchall()
    parts: list[str] = []
    for row in rows:
        try:
            data = json.loads(row["data"]) if isinstance(row["data"], str) else {}
        except (json.JSONDecodeError, TypeError):
            continue
        text = _extract_text_from_part(data)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _extract_text_from_part(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    if data.get("type") == "text":
        return str(data.get("text") or "")
    content = data.get("content") or data.get("text") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return "\n".join(t for t in texts if t)
    return ""


def _build_body(session_title: str, messages: list[dict]) -> str:
    lines: list[str] = [f"# {session_title}", ""]
    total = len("\n".join(lines))
    for msg in messages:
        role = msg["role"]
        summary = (msg["summary"] or "").strip()
        if not summary:
            continue
        block = f"**{role}**: {summary}\n"
        if total + len(block) > _BODY_CHAR_LIMIT:
            lines.append("\n*… truncated — body limit reached …*")
            break
        lines.append(block)
        total += len(block)
    return "\n".join(lines)


def _write_session(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    sessions_dir: Path,
    vault_path: Path,
) -> ExportResult:
    sid = row["id"]
    title = row["title"] or sid
    directory = row["directory"] or ""
    model = row["model"] or ""
    time_ms = row["time_created"] or 0

    time_created_iso = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )
    ingested_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    raw_id = new_ulid()
    slug = md.slug(title)
    record_path = sessions_dir / f"{raw_id}-{slug}.md"

    messages = _fetch_messages(conn, sid)
    body = _build_body(title, messages)

    frontmatter: dict = {
        "raw_id": raw_id,
        "kind": "session",
        "source": "opencode",
        "session_id": sid,
        "session_title": title,
        "directory": directory,
        "time_created": time_created_iso,
        "ingested_at": ingested_at,
        "content_type": "text/markdown",
    }
    if model:
        frontmatter["model"] = model

    md.write(record_path, md.Document(frontmatter=frontmatter, body=body))
    return ExportResult(session_id=sid, raw_id=raw_id, record_path=record_path)
