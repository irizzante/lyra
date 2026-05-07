"""M2 — McpMemorySource: graceful read-only adapter for mcp-memory-service."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from lyra import __version__
from lyra.sources.base import Capabilities, Health, Result, Source
from lyra.sources.agentmemory import _normalise

_TIMEOUT = 2.0


class McpMemorySource(Source):
    """Read-only adapter for mcp-memory-service.

    Degrades gracefully when the service is not reachable.
    """

    name = "mcp_memory"

    def __init__(
        self, host: str = "localhost", port: int = 3001, **kwargs: Any
    ) -> None:
        self.host = host
        self.port = port
        self._base = f"http://{host}:{port}"

    def query(
        self, q: str, k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[Result]:
        try:
            payload = json.dumps({"q": q, "k": k}).encode()
            req = urllib.request.Request(
                f"{self._base}/query",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())
            return _normalise(data, source=self.name)
        except Exception:
            return []

    def list_recent(self, window: str = "7d") -> list[Result]:
        try:
            url = f"{self._base}/recent?window={window}"
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())
            return _normalise(data, source=self.name)
        except Exception:
            return []

    def health(self) -> Health:
        try:
            with urllib.request.urlopen(
                f"{self._base}/health", timeout=_TIMEOUT
            ) as resp:
                detail = json.loads(resp.read())
            return Health(ok=True, message="reachable", detail=detail)
        except Exception as exc:
            return Health(ok=False, message="unavailable", detail={"error": str(exc)})

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
