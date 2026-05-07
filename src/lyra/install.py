"""M1.9.3 — unified lyra install.

Copies the packaged SessionStart hook and/or SKILL.md into the Claude Code
target directory (~/.claude/ for user scope, .claude/ for project scope) and
optionally patches settings.json to wire the SessionStart hook.

Claude Code settings.json hook entry format::

    {
      "hooks": {
        "SessionStart": [
          {"hooks": [{"type": "command", "command": "node <path>"}]}
        ]
      }
    }
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

HOOK_ENTRY_SENTINEL = "lyra/session-start.mjs"


class InstallReport:
    __slots__ = ("copied", "skipped", "patched")

    def __init__(self) -> None:
        self.copied: list[Path] = []
        self.skipped: list[Path] = []
        self.patched: list[Path] = []


def install(
    *,
    hook: bool = True,
    skill: bool = True,
    scope: str = "user",
    no_inject: bool = False,
    claude_dir: Path | None = None,
) -> InstallReport:
    """Install Lyra hook and/or skill into the Claude Code target directory.

    Args:
        hook:       Copy the SessionStart hook.
        skill:      Copy SKILL.md to skills/lyra/.
        scope:      "user" → ~/.claude/; "project" → .claude/ in cwd.
        no_inject:  Copy files but skip settings.json patching.
        claude_dir: Override target directory (for testing).
    """
    if scope not in {"user", "project"}:
        raise ValueError(f"scope must be 'user' or 'project', got {scope!r}")

    target = claude_dir or (
        Path.home() / ".claude" if scope == "user" else Path.cwd() / ".claude"
    )
    target.mkdir(parents=True, exist_ok=True)

    report = InstallReport()
    tmpl = resources.files("lyra.templates")

    if skill:
        dest = target / "skills" / "lyra" / "SKILL.md"
        _copy_template(tmpl, "SKILL.md", dest, report)

    if hook:
        hook_dest = target / "hooks" / "lyra" / "session-start.mjs"
        _copy_template(tmpl, "session-start.mjs", hook_dest, report)

        if not no_inject:
            settings_path = target / "settings.json"
            _patch_settings(settings_path, hook_dest, report)

    return report


def _copy_template(tmpl_pkg, name: str, dest: Path, report: InstallReport) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = tmpl_pkg.joinpath(name).read_bytes()
    dest.write_bytes(content)
    report.copied.append(dest)


def _patch_settings(settings_path: Path, hook_path: Path, report: InstallReport) -> None:
    """Add the SessionStart hook entry to settings.json if not already present."""
    data: dict = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    hooks = data.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])

    command = f"node {hook_path}"
    if _hook_entry_present(session_start):
        report.skipped.append(settings_path)
        return

    session_start.append({"hooks": [{"type": "command", "command": command}]})
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    report.patched.append(settings_path)


def _hook_entry_present(session_start: list) -> bool:
    for group in session_start:
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks", []):
            if isinstance(h, dict) and HOOK_ENTRY_SENTINEL in h.get("command", ""):
                return True
    return False
