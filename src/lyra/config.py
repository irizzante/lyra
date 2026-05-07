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


@dataclass
class Config:
    vault_path: Path
    sources: list[SourceConfig] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

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
        return cls(
            vault_path=Path(data["vault_path"]),
            sources=sources,
            schema_version=data.get("schema_version", SCHEMA_VERSION),
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
