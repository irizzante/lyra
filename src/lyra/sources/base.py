"""Source plugin contract.

Every memory source plugged into Lyra implements this protocol. V1 ships
``karpathy_wiki`` as the canonical built-in source. Additional sources
(agentmemory, mcp-memory-service, plain markdown trees, MCP memory servers) are
M2+. Sinks (write-back) are deferred to M5 and intentionally excluded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class Result:
    """Normalised hit returned by ``Source.query`` / ``Source.list_recent``."""

    id: str
    source: str
    title: str
    snippet: str
    score: float
    citations: list[str] = field(default_factory=list)
    last_seen: datetime | None = None


@dataclass
class Health:
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Capabilities:
    """Self-declared capabilities of a source."""

    name: str
    version: str
    supports_query: bool = True
    supports_list_recent: bool = True
    supports_graph: bool = False
    supports_vector: bool = False
    read_only: bool = True


@runtime_checkable
class Source(Protocol):
    """Read-only memory source. Sinks (write-back) are out of scope for V1."""

    def query(
        self, q: str, k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[Result]: ...

    def list_recent(self, window: str = "7d") -> list[Result]: ...

    def health(self) -> Health: ...

    def capabilities(self) -> Capabilities: ...
