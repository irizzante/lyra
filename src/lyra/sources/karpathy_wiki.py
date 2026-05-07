"""Built-in canonical Karpathy Wiki V2 source.

The vault is the source of truth. Indexes (qmd BM25/FTS5 + vector) and the
SQLite graph projection are derived and rebuildable from markdown.

Status: M1 stub. Real implementation lands incrementally with M1.4-M1.7.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from lyra import __version__
from lyra.sources.base import Capabilities, Health, Result, Source


class KarpathyWikiSource(Source):
    name = "karpathy_wiki"

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path.resolve()

    def query(
        self, q: str, k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[Result]:
        # M1.7 wires the hybrid retrieval path. Until then this returns nothing.
        return []

    def list_recent(self, window: str = "7d") -> list[Result]:
        return []

    def health(self) -> Health:
        if not self.vault_path.exists():
            return Health(ok=False, message=f"vault path missing: {self.vault_path}")
        if not (self.vault_path / "wiki").exists():
            return Health(
                ok=False,
                message=f"vault layout incomplete: missing {self.vault_path / 'wiki'}",
            )
        return Health(
            ok=True,
            detail={
                "vault_path": str(self.vault_path),
                "checked_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=self.name,
            version=__version__,
            supports_query=True,
            supports_list_recent=True,
            supports_graph=True,
            supports_vector=True,
            read_only=True,
        )
