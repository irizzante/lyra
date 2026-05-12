"""Tests for ``lyra install`` (M1.9.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lyra.install import install, HOOK_ENTRY_SENTINEL


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    return tmp_path / ".claude"


def test_install_skill_creates_skill_md(claude_dir: Path) -> None:
    report = install(skill=True, hook=False, claude_dir=claude_dir)

    assert len(report.copied) == 1
    skill_path = claude_dir / "skills" / "lyra" / "SKILL.md"
    assert skill_path.exists()
    assert skill_path in report.copied
    content = skill_path.read_text(encoding="utf-8")
    assert "description:" in content
    assert "lyra" in content.lower()


def test_install_hook_creates_mjs(claude_dir: Path) -> None:
    report = install(skill=False, hook=True, no_inject=True, claude_dir=claude_dir)

    hook_path = claude_dir / "hooks" / "lyra" / "session-start.mjs"
    assert hook_path.exists()
    assert hook_path in report.copied
    assert "lyra" in hook_path.read_text(encoding="utf-8")


def test_install_hook_patches_settings_json(claude_dir: Path) -> None:
    report = install(skill=False, hook=True, no_inject=False, claude_dir=claude_dir)

    settings_path = claude_dir / "settings.json"
    assert settings_path.exists()
    assert settings_path in report.patched

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    session_start = data["hooks"]["SessionStart"]
    commands = [
        h.get("command", "")
        for group in session_start
        for h in group.get("hooks", [])
    ]
    assert any(HOOK_ENTRY_SENTINEL in cmd for cmd in commands)


def test_install_hook_no_inject_skips_settings(claude_dir: Path) -> None:
    report = install(skill=False, hook=True, no_inject=True, claude_dir=claude_dir)

    settings_path = claude_dir / "settings.json"
    assert not settings_path.exists()
    assert not report.patched


def test_install_hook_idempotent_settings(claude_dir: Path) -> None:
    install(skill=False, hook=True, no_inject=False, claude_dir=claude_dir)
    report2 = install(skill=False, hook=True, no_inject=False, claude_dir=claude_dir)

    settings_path = claude_dir / "settings.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    session_start = data["hooks"]["SessionStart"]

    sentinel_count = sum(
        1
        for group in session_start
        for h in group.get("hooks", [])
        if HOOK_ENTRY_SENTINEL in h.get("command", "")
    )
    assert sentinel_count == 1
    assert settings_path in report2.skipped


def test_install_both_skill_and_hook(claude_dir: Path) -> None:
    report = install(skill=True, hook=True, no_inject=True, claude_dir=claude_dir)

    assert (claude_dir / "skills" / "lyra" / "SKILL.md").exists()
    assert (claude_dir / "hooks" / "lyra" / "session-start.mjs").exists()
    assert (claude_dir / "hooks" / "lyra" / "session-end.mjs").exists()
    assert len(report.copied) == 3


def test_install_invalid_scope_raises() -> None:
    with pytest.raises(ValueError, match="scope"):
        install(scope="global")


def test_install_preserves_existing_settings(claude_dir: Path, tmp_path: Path) -> None:
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({"model": "claude-opus-4-7"}), encoding="utf-8")

    install(skill=False, hook=True, no_inject=False, claude_dir=claude_dir)

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data.get("model") == "claude-opus-4-7"
    assert "hooks" in data
