"""M1.8 — lyra brief: token-budgeted SessionStart preamble (ADR-5).

Generates a compact preamble (default ≤ 4 KB / ~1000 tokens) for injection at
session start.  Sections are added in priority order; lower-priority sections
are dropped when the budget is exhausted.

Per-section tiered cap (ADR-5 R4.AC6-8):
  - Top-3 items per section: ID + summary ≤ 400 chars each
  - Tail items (4+): ID + title ≤ 120 chars each

No LLM required (NFR4). Budget enforced as raw character count.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from lyra import markdown as md

DEFAULT_TOKEN_BUDGET = 4096  # chars (~1 token / 4 chars)
_TOP_ITEM_CAP = 400
_TAIL_ITEM_CAP = 120
_SEP = "\n\n"


def generate_brief(
    vault_path: Path,
    *,
    char_budget: int = DEFAULT_TOKEN_BUDGET,
    recent_sessions: int = 5,
    top_pages: int = 8,
    recent_activity_lines: int = 5,
    active_tasks: int = 5,
) -> str:
    """Return a compact SessionStart preamble from the vault state."""
    sections: list[str] = []
    budget = char_budget

    def _add(block: str) -> bool:
        nonlocal budget
        if block and len(block) <= budget:
            sections.append(block)
            budget -= len(block)
            return True
        return False

    _add(_header(vault_path))
    _add(_active_tasks_section(vault_path, n=active_tasks))
    _add(_recent_activity_section(vault_path, n=recent_activity_lines))
    _add(_recent_sessions_section(vault_path, n=recent_sessions))
    _add(_top_pages_section(vault_path, n=top_pages))
    _add(_usage_hint())

    return _SEP.join(sections)


# ------------------------------------------------------------------
# Sections
# ------------------------------------------------------------------

def _header(vault_path: Path) -> str:
    today = date.today().isoformat()
    return f"# Lyra brief — {today}\n\nVault: `{vault_path}`"


def _active_tasks_section(vault_path: Path, n: int) -> str:
    tasks_dir = vault_path / "Tasks"
    if not tasks_dir.exists():
        return ""

    items: list[tuple[str, str, str]] = []  # (mtime_iso, task_id, summary)
    for path in sorted(tasks_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            doc = md.read(path)
            status = str(doc.frontmatter.get("status") or "")
            if status in {"done", "cancelled"}:
                continue
            task_id = str(doc.frontmatter.get("task_id") or path.stem)
            title = str(doc.frontmatter.get("title") or path.stem)
            mtime = path.stat().st_mtime
            items.append((str(mtime), task_id, title))
        except Exception:  # noqa: BLE001
            continue
        if len(items) >= n:
            break

    if not items:
        return ""

    lines = _tiered_items(
        [(f"{task_id} — {title}", title) for _, task_id, title in items],
        top_cap=_TOP_ITEM_CAP,
        tail_cap=_TAIL_ITEM_CAP,
    )
    return "## Active tasks\n\n" + "\n".join(lines)


def _recent_activity_section(vault_path: Path, n: int) -> str:
    log_path = vault_path / "wiki" / "log.md"
    if not log_path.exists():
        return ""
    text = log_path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("-")]
    last = lines[-n:] if len(lines) > n else lines
    if not last:
        return ""
    return "## Recent activity\n\n" + "\n".join(last)


def _recent_sessions_section(vault_path: Path, n: int) -> str:
    """Read kind=session records from flat raw/."""
    raw_dir = vault_path / "raw"
    if not raw_dir.exists():
        return ""

    sessions: list[tuple[float, str, str]] = []  # (mtime, id, title)
    for path in raw_dir.glob("*.md"):
        try:
            doc = md.read(path)
            if doc.frontmatter.get("kind") != "session":
                continue
            raw_id = str(doc.frontmatter.get("raw_id") or path.stem)
            title = str(
                doc.frontmatter.get("session_title")
                or doc.frontmatter.get("title")
                or path.stem
            )
            sessions.append((path.stat().st_mtime, raw_id, title))
        except Exception:  # noqa: BLE001
            continue

    sessions.sort(reverse=True)
    top = sessions[:n]
    if not top:
        return ""

    lines = _tiered_items(
        [(f"{raw_id} — {title}", title) for _, raw_id, title in top],
        top_cap=_TOP_ITEM_CAP,
        tail_cap=_TAIL_ITEM_CAP,
    )
    return "## Recent sessions\n\n" + "\n".join(lines)


def _top_pages_section(vault_path: Path, n: int) -> str:
    sources_dir = vault_path / "wiki" / "sources"
    if not sources_dir.exists():
        return ""

    pages: list[tuple[str, str, str, float]] = []
    for path in sources_dir.glob("*.md"):
        try:
            doc = md.read(path)
            page_id = str(doc.frontmatter.get("id") or path.stem)
            title = str(doc.frontmatter.get("title") or path.stem)
            last_confirmed = str(doc.frontmatter.get("last_confirmed") or "")
            confidence = doc.frontmatter.get("confidence") or 0.0
            pages.append((last_confirmed, page_id, title, float(confidence)))
        except Exception:  # noqa: BLE001
            continue

    pages.sort(key=lambda x: x[0], reverse=True)
    top = pages[:n]
    if not top:
        return ""

    def _summary(page_id: str, title: str, confidence: float) -> str:
        conf = f" (conf={confidence:.2f})" if confidence else ""
        return f"{page_id} — {title}{conf}"

    lines = _tiered_items(
        [(_summary(pid, title, conf), title) for _, pid, title, conf in top],
        top_cap=_TOP_ITEM_CAP,
        tail_cap=_TAIL_ITEM_CAP,
    )
    return "## Knowledge base (top pages)\n\n" + "\n".join(lines)


def _usage_hint() -> str:
    return (
        "## Lyra CLI\n\n"
        "```\n"
        "lyra query <question>     # hybrid search with citations\n"
        "lyra ingest <path|url>    # add research to raw/\n"
        "lyra compile              # promote raw → wiki/sources/\n"
        "lyra file <question>      # query + file answer to wiki/qa/\n"
        "lyra status               # vault and source health\n"
        "```"
    )


# ------------------------------------------------------------------
# Tiered item formatter
# ------------------------------------------------------------------

def _tiered_items(
    items: list[tuple[str, str]],
    *,
    top_cap: int = _TOP_ITEM_CAP,
    tail_cap: int = _TAIL_ITEM_CAP,
    top_n: int = 3,
) -> list[str]:
    """Format items as bulleted list with tiered char caps.

    Args:
        items:   list of (summary, title) pairs.
        top_cap: char cap for items 0..top_n-1.
        tail_cap: char cap for items top_n+.
        top_n:   number of items that get the larger cap.
    """
    lines: list[str] = []
    for i, (summary, title) in enumerate(items):
        cap = top_cap if i < top_n else tail_cap
        text = summary if i < top_n else title
        if len(text) > cap:
            text = text[: cap - 1] + "…"
        lines.append(f"- {text}")
    return lines
