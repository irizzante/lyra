"""M1.11 — ObsidianTasksSource: read-only Source over <vault>/Tasks/*.md.

Exposes Obsidian task notes as a Lyra Source.  obsidian-manager MCP remains
the canonical writer; this source is strictly read-only.

V1 uses direct markdown parsing (no qmd dependency).  A separate qmd collection
``lyra-tasks`` for BM25/vector retrieval is planned for M2+.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from lyra import __version__
from lyra.markdown import read as md_read
from lyra.sources.base import Capabilities, Health, Result, Source

TASKS_SUBDIR = "Tasks"

_WINDOW_RE = re.compile(r"^(?P<n>\d+)(?P<unit>[dhw])$")
_UNIT_DAYS = {"d": 1, "h": 1 / 24, "w": 7}


def _parse_window(window: str) -> timedelta:
    m = _WINDOW_RE.match(window.strip())
    if not m:
        raise ValueError(f"unrecognised window format: {window!r} (expected e.g. '7d', '24h', '2w')")
    n = int(m.group("n"))
    unit = m.group("unit")
    return timedelta(days=n * _UNIT_DAYS[unit])


class ObsidianTasksSource(Source):
    """Read-only source over ``<vault>/Tasks/*.md``.

    obsidian-manager MCP is the canonical writer.  This source provides
    read-only query + list_recent access for ``lyra brief`` fan-out.
    """

    name = "obsidian_tasks"

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path.resolve()
        self.tasks_dir = self.vault_path / TASKS_SUBDIR

    # ------------------------------------------------------------------
    # Source protocol
    # ------------------------------------------------------------------

    def query(
        self, q: str, k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[Result]:
        """Substring search over task title + body."""
        tokens = q.lower().split()
        hits: list[tuple[float, Result]] = []

        for path in sorted(self.tasks_dir.glob("*.md")):
            try:
                doc = md_read(path)
            except Exception:  # noqa: BLE001
                continue

            title = str(doc.frontmatter.get("title") or path.stem)
            status = str(doc.frontmatter.get("status") or "")
            body = doc.body or ""
            text = f"{title} {status} {body}".lower()

            if filters:
                status_filter = filters.get("status")
                if status_filter and status != str(status_filter):
                    continue

            score = sum(1.0 for t in tokens if t in text) / max(len(tokens), 1)
            if score == 0.0:
                continue

            task_id = str(doc.frontmatter.get("task_id") or path.stem)
            snippet = _make_snippet(body, tokens)
            hits.append(
                (
                    score,
                    Result(
                        id=task_id,
                        source=self.name,
                        title=title,
                        snippet=snippet,
                        score=score,
                        citations=[str(path)],
                        last_seen=_mtime(path),
                    ),
                )
            )

        hits.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in hits[:k]]

    def list_recent(self, window: str = "7d") -> list[Result]:
        """Return tasks modified within ``window``."""
        cutoff = datetime.now(tz=timezone.utc) - _parse_window(window)
        results: list[Result] = []

        for path in sorted(self.tasks_dir.glob("*.md")):
            mtime = _mtime(path)
            if mtime is None or mtime < cutoff:
                continue
            try:
                doc = md_read(path)
            except Exception:  # noqa: BLE001
                continue

            title = str(doc.frontmatter.get("title") or path.stem)
            task_id = str(doc.frontmatter.get("task_id") or path.stem)
            status = str(doc.frontmatter.get("status") or "")
            snippet = f"[{status}] {(doc.body or '').strip()[:120]}"

            results.append(
                Result(
                    id=task_id,
                    source=self.name,
                    title=title,
                    snippet=snippet,
                    score=1.0,
                    citations=[str(path)],
                    last_seen=mtime,
                )
            )

        results.sort(key=lambda r: r.last_seen or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return results

    def health(self) -> Health:
        if not self.vault_path.exists():
            return Health(ok=False, message=f"vault path missing: {self.vault_path}")
        if not self.tasks_dir.exists():
            return Health(
                ok=False,
                message=f"Tasks/ directory missing: {self.tasks_dir}",
                detail={"tasks_dir": str(self.tasks_dir)},
            )
        task_files = list(self.tasks_dir.glob("*.md"))
        return Health(
            ok=True,
            detail={
                "tasks_dir": str(self.tasks_dir),
                "task_count": len(task_files),
                "checked_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=self.name,
            version=__version__,
            supports_query=True,
            supports_list_recent=True,
            supports_graph=False,
            supports_vector=False,
            read_only=True,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _make_snippet(body: str, tokens: list[str]) -> str:
    """Return a ~120-char excerpt around the first token match."""
    lower = body.lower()
    for token in tokens:
        pos = lower.find(token)
        if pos != -1:
            start = max(0, pos - 40)
            end = min(len(body), pos + 80)
            excerpt = body[start:end].strip()
            return (excerpt[:120] + "…") if len(excerpt) > 120 else excerpt
    return body[:120].strip()
