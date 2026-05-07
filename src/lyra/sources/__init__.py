"""Source plugin contract and built-in adapters."""

from lyra.sources.agentmemory import AgentmemorySource
from lyra.sources.karpathy_wiki import KarpathyWikiSource
from lyra.sources.mcp_memory import McpMemorySource
from lyra.sources.obsidian_tasks import ObsidianTasksSource
from lyra.sources.plain_markdown import PlainMarkdownSource

__all__ = [
    "AgentmemorySource",
    "KarpathyWikiSource",
    "McpMemorySource",
    "ObsidianTasksSource",
    "PlainMarkdownSource",
]
