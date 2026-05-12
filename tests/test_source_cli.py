"""Tests for M2 `lyra source` CLI subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest

from lyra import config as cfg_mod
from lyra.cli import main
from lyra.config import Config


@pytest.fixture
def vault_and_config(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "raw").mkdir()
    (vault / "wiki").mkdir()

    config_home = tmp_path / "lyra"
    config_home.mkdir()
    config_path = config_home / "config.yaml"
    monkeypatch.setattr(cfg_mod, "CONFIG_HOME", config_home)
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", config_path)

    cfg = Config.default(vault)
    cfg_mod.save(cfg, config_path)
    return vault, config_path


def test_source_list_shows_configured_sources(vault_and_config, capsys) -> None:
    rc = main(["source", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "karpathy_wiki" in out


def test_source_add_then_list(vault_and_config, capsys) -> None:
    vault, config_path = vault_and_config
    rc = main([
        "source", "add", "my-notes",
        "--adapter", "lyra.sources.karpathy_wiki.KarpathyWikiSource",
        "--config", f"vault_path={vault}",
    ])
    assert rc == 0

    cfg = cfg_mod.load(config_path)
    names = [s.name for s in cfg.sources]
    assert "my-notes" in names

    capsys.readouterr()
    rc2 = main(["source", "list"])
    assert rc2 == 0
    out = capsys.readouterr().out
    assert "my-notes" in out


def test_source_add_duplicate_fails(vault_and_config, capsys) -> None:
    rc = main([
        "source", "add", "karpathy_wiki",
        "--adapter", "lyra.sources.karpathy_wiki.KarpathyWikiSource",
    ])
    assert rc != 0


def test_source_remove(vault_and_config, capsys) -> None:
    vault, config_path = vault_and_config
    main([
        "source", "add", "tmp-src",
        "--adapter", "lyra.sources.karpathy_wiki.KarpathyWikiSource",
        "--config", f"vault_path={vault}",
    ])
    rc = main(["source", "remove", "tmp-src"])
    assert rc == 0

    cfg = cfg_mod.load(config_path)
    assert not any(s.name == "tmp-src" for s in cfg.sources)


def test_source_remove_nonexistent(vault_and_config, capsys) -> None:
    rc = main(["source", "remove", "does-not-exist"])
    assert rc != 0


def test_source_refresh_all(vault_and_config, capsys) -> None:
    rc = main(["source", "refresh"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "karpathy_wiki" in out


def test_source_refresh_named(vault_and_config, capsys) -> None:
    rc = main(["source", "refresh", "karpathy_wiki"])
    assert rc == 0


def test_status_uses_all_sources(vault_and_config, capsys) -> None:
    rc = main(["status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "karpathy_wiki" in out
