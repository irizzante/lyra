"""Frontmatter-aware markdown read/write helpers.

YAML frontmatter blocks are delimited by ``---`` on their own line at the top
of the file. We don't depend on python-frontmatter to keep the dep surface
minimal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_FENCE = "---"


@dataclass
class Document:
    frontmatter: dict[str, Any]
    body: str

    def dump(self) -> str:
        if not self.frontmatter:
            return self.body
        rendered = yaml.safe_dump(self.frontmatter, sort_keys=False).rstrip()
        return f"{FRONTMATTER_FENCE}\n{rendered}\n{FRONTMATTER_FENCE}\n\n{self.body.lstrip()}"


def parse(text: str) -> Document:
    if not text.startswith(FRONTMATTER_FENCE + "\n") and not text.startswith(
        FRONTMATTER_FENCE + "\r\n"
    ):
        return Document(frontmatter={}, body=text)

    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return Document(frontmatter={}, body=text)

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == FRONTMATTER_FENCE:
            end = idx
            break
    if end is None:
        return Document(frontmatter={}, body=text)

    frontmatter_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    body = body.lstrip("\n")
    data = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(data, dict):
        data = {}
    return Document(frontmatter=data, body=body)


def read(path: Path) -> Document:
    return parse(path.read_text(encoding="utf-8"))


def write(path: Path, doc: Document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc.dump(), encoding="utf-8")


def slug(value: str, max_len: int = 64) -> str:
    """Reduce a string to a kebab-case slug suitable for a filename stem."""
    cleaned: list[str] = []
    prev_dash = False
    for ch in value.strip().lower():
        if ch.isalnum():
            cleaned.append(ch)
            prev_dash = False
        elif not prev_dash:
            cleaned.append("-")
            prev_dash = True
    out = "".join(cleaned).strip("-")
    if len(out) > max_len:
        out = out[:max_len].rstrip("-")
    return out or "untitled"
