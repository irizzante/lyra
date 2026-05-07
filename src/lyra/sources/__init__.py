"""Source plugin contract and built-in adapters."""

from __future__ import annotations

import importlib
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lyra.config import Config, SourceConfig
    from lyra.sources.base import Source

_BUILTIN_ADAPTERS: dict[str, str] = {
    "karpathy_wiki": "lyra.sources.karpathy_wiki.KarpathyWikiSource",
    "obsidian_tasks": "lyra.sources.obsidian_tasks.ObsidianTasksSource",
    "plain_markdown": "lyra.sources.plain_markdown.PlainMarkdownSource",
    "agentmemory": "lyra.sources.agentmemory.AgentmemorySource",
    "mcp_memory": "lyra.sources.mcp_memory.McpMemorySource",
}


def load_source(source_cfg: SourceConfig, vault_path: Any = None) -> Source:
    """Dynamically instantiate a source adapter from a SourceConfig entry."""
    from pathlib import Path

    adapter_path = source_cfg.adapter or _BUILTIN_ADAPTERS.get(source_cfg.type, "")
    if not adapter_path:
        raise ValueError(
            f"Unknown source type {source_cfg.type!r}. "
            "Set 'adapter' to a dotted class path."
        )
    module_path, _, class_name = adapter_path.rpartition(".")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    kwargs: dict[str, Any] = dict(source_cfg.options)
    if vault_path is not None and source_cfg.type in ("karpathy_wiki", "obsidian_tasks"):
        kwargs.setdefault("vault_path", Path(vault_path))
    # Coerce any vault_path string to Path (options are stored as strings in YAML).
    if "vault_path" in kwargs:
        kwargs["vault_path"] = Path(kwargs["vault_path"])

    return cls(**kwargs)


def load_all_sources(
    config: Config, vault_path: Any = None
) -> list[tuple[str, Source]]:
    """Return [(name, source)] for all enabled sources in config."""
    vp = vault_path or config.vault_path
    result: list[tuple[str, Source]] = []
    for src_cfg in config.sources:
        if not src_cfg.enabled:
            continue
        try:
            result.append((src_cfg.name, load_source(src_cfg, vault_path=vp)))
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Failed to load source {src_cfg.name!r}: {exc}", stacklevel=2)
    return result
