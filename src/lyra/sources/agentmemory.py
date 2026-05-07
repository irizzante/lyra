"""M2 — AgentmemorySource: graceful read-only adapter for agentmemory service."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from lyra import __version__
from lyra.sources.base import Capabilities, Health, Result, Source

_TIMEOUT = 2.0


class AgentmemorySource(Source):
    """Read-only adapter for the agentmemory MCP service.

    Degrades gracefully: all methods return empty / unavailable when the
    service is not reachable. No exceptions propagate to callers.
    """

    name = "agentmemory"

    def __init__(
        self, host: str = "localhost", port: int = 3000, **kwargs: Any
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


def _normalise(data: Any, *, source: str) -> list[Result]:
    if not isinstance(data, list):
        data = data.get("results", []) if isinstance(data, dict) else []
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        results.append(
            Result(
                id=str(item.get("id", "")),
                source=source,
                title=str(item.get("title", item.get("id", ""))),
                snippet=str(item.get("snippet", item.get("content", ""))[:400]),
                score=float(item.get("score", 0.0)),
            )
        )
    return results
