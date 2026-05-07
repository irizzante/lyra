"""Sketch: SQLite graph projection of typed relations from canonical wiki.

The wiki body uses two reference layers:

1. Obsidian wikilinks ``[[Page Name]]`` — filename-based, for human navigation.
2. Lyra typed relations (``relations:`` frontmatter and inline ``supports::`` /
   ``contradicts::`` / ``uses::`` / ``supersedes::`` annotations) — ULID-based,
   for the durable graph projection.

This module owns layer 2. The wikilink layer is Obsidian's concern.

Schema
------
Edges keyed by ``target_id`` ULID, never by filename, so renames do not break
the graph. Compile resolves ``[[Page Name]]`` to the target ULID at promotion
time and writes the resolved edge into this projection.

```sql
CREATE TABLE IF NOT EXISTS pages (
    id          TEXT PRIMARY KEY,        -- ULID
    title       TEXT NOT NULL,
    type        TEXT NOT NULL,
    confidence  REAL,
    last_seen   TEXT,
    file_path   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    src_id      TEXT NOT NULL REFERENCES pages(id),
    type        TEXT NOT NULL,           -- supports | contradicts | uses | supersedes | ...
    dst_id      TEXT NOT NULL REFERENCES pages(id),
    confidence  REAL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (src_id, type, dst_id)
);

CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
```

Status: M1.6 sketch. Real population happens at compile time once the relation
parser (M1.5) is wired in.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GRAPH_PATH = Path.home() / "lyra" / "index" / "karpathy_wiki" / "graph.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    type        TEXT NOT NULL,
    confidence  REAL,
    last_seen   TEXT,
    file_path   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    src_id      TEXT NOT NULL REFERENCES pages(id),
    type        TEXT NOT NULL,
    dst_id      TEXT NOT NULL REFERENCES pages(id),
    confidence  REAL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (src_id, type, dst_id)
);

CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
"""


@dataclass
class GraphProjectionConfig:
    db_path: Path = DEFAULT_GRAPH_PATH


def open_db(config: GraphProjectionConfig) -> sqlite3.Connection:
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def neighbours(
    conn: sqlite3.Connection,
    page_id: str,
    edge_types: tuple[str, ...] | None = None,
    direction: str = "out",
) -> list[tuple[str, str, str, float | None]]:
    """One-hop neighbours of ``page_id``.

    Returns rows of ``(src_id, type, dst_id, confidence)``. ``direction`` is
    ``out`` (outbound), ``in`` (inbound), or ``both``. M1.7 hybrid retrieval
    composes one-hop traversal on top of BM25/FTS5 + vector hits.
    """
    where = []
    params: list[object] = []
    if direction in ("out", "both"):
        where.append("src_id = ?")
        params.append(page_id)
    if direction in ("in", "both"):
        where.append("dst_id = ?")
        params.append(page_id)
    if not where:
        raise ValueError(f"unknown direction: {direction!r}")

    sql = f"SELECT src_id, type, dst_id, confidence FROM edges WHERE {' OR '.join(where)}"
    if edge_types:
        placeholders = ",".join("?" * len(edge_types))
        sql += f" AND type IN ({placeholders})"
        params.extend(edge_types)

    cur = conn.execute(sql, params)
    return list(cur.fetchall())


def upsert_from_vault(vault_path: Path, conn: sqlite3.Connection) -> tuple[int, int]:
    """Populate pages and edges tables from compiled wiki frontmatter.

    Walks ``wiki/sources/*.md``, reads ``id``, ``title``, ``type``,
    ``confidence``, ``last_confirmed``, ``relations``, and upserts into the
    graph projection. Returns ``(pages_upserted, edges_upserted)``.

    Idempotent: re-running refreshes ``last_seen`` and merges new edges.
    """
    from lyra import markdown as md

    wiki_root = vault_path / "wiki"
    if not wiki_root.exists():
        return 0, 0

    today = __import__("datetime").date.today().isoformat()
    pages_n = 0
    edges_n = 0

    for path in wiki_root.rglob("*.md"):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        try:
            doc = md.read(path)
        except Exception:  # noqa: BLE001
            continue

        page_id = doc.frontmatter.get("id")
        if not page_id:
            continue

        title = str(doc.frontmatter.get("title") or path.stem)
        page_type = str(doc.frontmatter.get("type") or "source")
        confidence = doc.frontmatter.get("confidence")
        last_confirmed = str(doc.frontmatter.get("last_confirmed") or today)
        file_path = str(path)

        conn.execute(
            """
            INSERT INTO pages (id, title, type, confidence, last_seen, file_path)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title      = excluded.title,
                confidence = excluded.confidence,
                last_seen  = excluded.last_seen,
                file_path  = excluded.file_path
            """,
            (page_id, title, page_type, confidence, last_confirmed, file_path),
        )
        pages_n += 1

        rels = doc.frontmatter.get("relations") or []
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            dst_id = rel.get("target_id")
            if not dst_id:
                continue
            rel_type = str(rel.get("type") or "relates")
            rel_conf = rel.get("confidence")
            conn.execute(
                """
                INSERT INTO edges (src_id, type, dst_id, confidence, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(src_id, type, dst_id) DO UPDATE SET
                    confidence = excluded.confidence
                """,
                (page_id, rel_type, dst_id, rel_conf, today),
            )
            edges_n += 1

    conn.commit()
    return pages_n, edges_n
