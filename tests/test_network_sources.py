"""Tests for AgentmemorySource and McpMemorySource (M2) — no live service required."""

from __future__ import annotations

from lyra.sources.agentmemory import AgentmemorySource
from lyra.sources.mcp_memory import McpMemorySource

# Use ports that are guaranteed to be closed.
_DEAD_AM_PORT = 19999
_DEAD_MCP_PORT = 19998


# ---------------------------------------------------------------------------
# AgentmemorySource
# ---------------------------------------------------------------------------

def test_agentmemory_health_unavailable() -> None:
    src = AgentmemorySource(port=_DEAD_AM_PORT)
    h = src.health()
    assert h.ok is False
    assert "unavailable" in h.message


def test_agentmemory_query_unavailable_returns_empty() -> None:
    src = AgentmemorySource(port=_DEAD_AM_PORT)
    assert src.query("anything") == []


def test_agentmemory_list_recent_unavailable_returns_empty() -> None:
    src = AgentmemorySource(port=_DEAD_AM_PORT)
    assert src.list_recent() == []


def test_agentmemory_capabilities() -> None:
    src = AgentmemorySource(port=_DEAD_AM_PORT)
    caps = src.capabilities()
    assert caps.supports_query is True
    assert caps.supports_list_recent is True
    assert caps.read_only is True
    assert caps.name == "agentmemory"


# ---------------------------------------------------------------------------
# McpMemorySource
# ---------------------------------------------------------------------------

def test_mcpmemory_health_unavailable() -> None:
    src = McpMemorySource(port=_DEAD_MCP_PORT)
    h = src.health()
    assert h.ok is False
    assert "unavailable" in h.message


def test_mcpmemory_query_unavailable_returns_empty() -> None:
    src = McpMemorySource(port=_DEAD_MCP_PORT)
    assert src.query("anything") == []


def test_mcpmemory_list_recent_unavailable_returns_empty() -> None:
    src = McpMemorySource(port=_DEAD_MCP_PORT)
    assert src.list_recent() == []


def test_mcpmemory_capabilities() -> None:
    src = McpMemorySource(port=_DEAD_MCP_PORT)
    caps = src.capabilities()
    assert caps.supports_query is True
    assert caps.read_only is True
    assert caps.name == "mcp_memory"


# ---------------------------------------------------------------------------
# Both sources
# ---------------------------------------------------------------------------

def test_both_sources_no_exceptions_when_down() -> None:
    for src in [AgentmemorySource(port=_DEAD_AM_PORT), McpMemorySource(port=_DEAD_MCP_PORT)]:
        assert src.query("test") == []
        assert src.list_recent() == []
        assert src.health().ok is False
