"""M2 — PlainMarkdownSource: read-only adapter over any markdown directory tree."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from lyra import __version__
from lyra.sources.base import Capabilities, Health, Result, Source


class PlainMarkdownSource(Source):
    """Read-only source adapter over an arbitrary markdown directory tree.

    Does not require a qmd index to be built — degrades to filesystem-only
    listing when the index is absent.
    """

    name = "plain_markdown"

    def __init__(
        self,
        root: str | Path,
        collection: str = "plain-markdown",
        **kwargs: Any,
    ) -> None:
        self.root = Path(root).resolve()
        self.collection = collection

    def query(
        self, q: str, k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[Result]:
        """Search the markdown tree via qmd; returns [] if index absent."""
        import subprocess

        if not self.root.exists():
            return []
        try:
            proc = subprocess.run(
                ["qmd", "search", "-n", str(k), "-c", self.collection, q],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return []
            return _parse_qmd_output(proc.stdout, source=self.name)
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return []

    def list_recent(self, window: str = "7d") -> list[Result]:
        """Return recently modified .md files sorted by mtime descending."""
        if not self.root.exists():
            return []
        files = sorted(
            self.root.rglob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
        results = []
        for path in files:
            try:
                stat = path.stat()
                results.append(
                    Result(
                        id=str(path.relative_to(self.root)),
                        source=self.name,
                        title=path.stem,
                        snippet=_first_line(path),
                        score=0.0,
                        last_seen=datetime.fromtimestamp(stat.st_mtime),
                    )
                )
            except Exception:
                continue
        return results

    def health(self) -> Health:
        root_exists = self.root.exists()
        if not root_exists:
            return Health(ok=False, message=f"root not found: {self.root}")
        count = sum(1 for _ in self.root.rglob("*.md"))
        return Health(
            ok=True,
            detail={
                "root": str(self.root),
                "collection": self.collection,
                "file_count": count,
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


def _first_line(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:200]
    except Exception:
        pass
    return ""


def _parse_qmd_output(text: str, *, source: str) -> list[Result]:
    """Minimal parser for qmd search text output."""
    results: list[Result] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("id:"):
            if current:
                results.append(_to_result(current, source))
            current = {"id": line[3:].strip()}
        elif ":" in line and current:
            key, _, val = line.partition(":")
            current[key.strip()] = val.strip()
    if current:
        results.append(_to_result(current, source))
    return results


def _to_result(d: dict[str, str], source: str) -> Result:
    return Result(
        id=d.get("id", ""),
        source=source,
        title=d.get("title", d.get("id", "")),
        snippet=d.get("snippet", ""),
        score=float(d.get("score", 0.0)),
    )
