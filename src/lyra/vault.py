"""Vault layout creation and discovery for the canonical Karpathy Wiki V2 source."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

RAW_SUBDIRS = ("assets",)
WIKI_SUBDIRS = (
    "concepts",
    "connections",
    "sources",
    "procedures",
    "synthesis",
    "qa",
    "meta",
)
WIKI_ROOT_FILES = ("AGENTS.md", "index.md", "log.md")


def ensure_layout(vault_path: Path) -> dict[str, list[Path]]:
    """Create the canonical raw/ and wiki/ layout under ``vault_path``.

    Idempotent: existing directories and user-authored files are preserved.
    Returns a dict of created vs skipped paths so callers can report progress.
    """
    vault_path = vault_path.resolve()
    vault_path.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    skipped: list[Path] = []

    for sub in RAW_SUBDIRS:
        target = vault_path / "raw" / sub
        _mkdir(target, created, skipped)

    for sub in WIKI_SUBDIRS:
        target = vault_path / "wiki" / sub
        _mkdir(target, created, skipped)

    wiki_root = vault_path / "wiki"
    for filename in WIKI_ROOT_FILES:
        target = wiki_root / filename
        if filename == "AGENTS.md":
            _deploy_template(target, "AGENTS.md", created, skipped)
        else:
            _touch(target, created, skipped)

    return {"created": created, "skipped": skipped}


def _mkdir(path: Path, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
    else:
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)


def _touch(path: Path, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    created.append(path)


def _deploy_template(
    target: Path, template_name: str, created: list[Path], skipped: list[Path]
) -> None:
    """Deploy a packaged template to ``target`` only if absent.

    Never overwrites a user-authored file. This protects user edits across
    re-runs of ``lyra init``.
    """
    if target.exists():
        skipped.append(target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        resources.files("lyra.templates").joinpath(template_name).read_text(encoding="utf-8")
    )
    target.write_text(content, encoding="utf-8")
    created.append(target)
