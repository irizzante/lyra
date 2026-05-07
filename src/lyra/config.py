"""Runtime config for Lyra.

Config lives at ``~/lyra/config.yaml`` and stores the absolute vault path plus
the list of enabled sources. The canonical default source is ``karpathy_wiki``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_HOME = Path.home() / "lyra"
CONFIG_PATH = CONFIG_HOME / "config.yaml"
SCHEMA_VERSION = 1


@dataclass
class SourceConfig:
    name: str
    type: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)
    adapter: str = ""  # dotted class path e.g. lyra.sources.plain_markdown.PlainMarkdownSource


@dataclass
class AutoSupersessionWeights:
    recency: float = 0.5
    authority: float = 0.3
    support: float = 0.2


@dataclass
class AutoSupersessionConfig:
    enabled: bool = True
    weights: AutoSupersessionWeights = field(default_factory=AutoSupersessionWeights)
    threshold: float = 0.2


@dataclass
class Config:
    vault_path: Path
    sources: list[SourceConfig] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    auto_supersession: AutoSupersessionConfig = field(default_factory=AutoSupersessionConfig)

    @classmethod
    def default(cls, vault_path: Path) -> Config:
        return cls(
            vault_path=vault_path.resolve(),
            sources=[
                SourceConfig(
                    name="karpathy_wiki",
                    type="karpathy_wiki",
                    options={"vault_path": str(vault_path.resolve())},
                )
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["vault_path"] = str(self.vault_path)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        sources = [SourceConfig(**s) for s in data.get("sources", [])]
        as_data = data.get("auto_supersession") or {}
        w_data = as_data.get("weights") or {}
        auto_supersession = AutoSupersessionConfig(
            enabled=as_data.get("enabled", True),
            weights=AutoSupersessionWeights(
                recency=w_data.get("recency", 0.5),
                authority=w_data.get("authority", 0.3),
                support=w_data.get("support", 0.2),
            ),
            threshold=as_data.get("threshold", 0.2),
        )
        return cls(
            vault_path=Path(data["vault_path"]),
            sources=sources,
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            auto_supersession=auto_supersession,
        )


def load(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        raise FileNotFoundError(
            f"Lyra config not found at {path}. Run `lyra init <vault>` to create it."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config.from_dict(data)


def save(config: Config, path: Path = CONFIG_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config.to_dict(), fh, sort_keys=False)
    return path
