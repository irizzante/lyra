"""Smoke tests for ``lyra init``: vault layout creation, config write, and idempotence."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra import config as cfg_mod
from lyra.cli import main
from lyra.vault import RAW_SUBDIRS, WIKI_ROOT_FILES, WIKI_SUBDIRS, ensure_layout


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect ``~/lyra/config.yaml`` into ``tmp_path`` for the test."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(cfg_mod, "CONFIG_HOME", fake_home / "lyra")
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", fake_home / "lyra" / "config.yaml")
    return fake_home


def test_ensure_layout_creates_full_tree(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    layout = ensure_layout(vault)

    for sub in RAW_SUBDIRS:
        assert (vault / "raw" / sub).is_dir()
    for sub in WIKI_SUBDIRS:
        assert (vault / "wiki" / sub).is_dir()
    for filename in WIKI_ROOT_FILES:
        assert (vault / "wiki" / filename).is_file()

    # AGENTS.md must come from the packaged template, not be empty.
    agents_md = (vault / "wiki" / "AGENTS.md").read_text(encoding="utf-8")
    assert "lyra brief" in agents_md
    assert layout["created"]


def test_ensure_layout_idempotent_and_preserves_user_edits(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    ensure_layout(vault)

    user_text = "# my notes\nuser-authored content"
    (vault / "wiki" / "AGENTS.md").write_text(user_text, encoding="utf-8")

    layout = ensure_layout(vault)

    # Re-running must not overwrite user edits.
    assert (vault / "wiki" / "AGENTS.md").read_text(encoding="utf-8") == user_text
    # Second run should mostly hit "skipped" since everything exists.
    assert layout["skipped"]


def test_cli_init_writes_config(tmp_path: Path, isolated_home: Path) -> None:
    vault = tmp_path / "vault"
    rc = main(["init", str(vault)])
    assert rc == 0

    config_path = cfg_mod.CONFIG_PATH
    assert config_path.is_file()

    loaded = cfg_mod.load(config_path)
    assert loaded.vault_path == vault.resolve()
    assert loaded.schema_version == cfg_mod.SCHEMA_VERSION
    assert any(s.name == "karpathy_wiki" for s in loaded.sources)


def test_cli_init_rejects_unwritable_parent(tmp_path: Path, isolated_home: Path) -> None:
    """A non-existent grandparent should not crash; mkdir(parents=True) handles it."""
    vault = tmp_path / "deeper" / "nested" / "vault"
    rc = main(["init", str(vault)])
    assert rc == 0
    assert vault.is_dir()
