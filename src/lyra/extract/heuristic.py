"""M3.2 — Heuristic entity extractor (deterministic baseline).

Parses entities from a raw page body and frontmatter using four strategies:
1. Declarative frontmatter ``entities: [...]`` list
2. Inline ``entity::<type> <name>`` annotations in the body
3. Regex patterns for file paths (``src/foo.py``, ``./bar.ts``, etc.)
4. Python / JS-TS import statements → library entities

No LLM call is made here.  Returns ``list[ExtractedEntity]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ENTITY_TYPES = frozenset({"concept", "decision", "file", "library", "person", "project"})

# entity::<type> <name>  — inline annotation (rest of line is the name)
_INLINE_RE = re.compile(r"entity::(?P<type>\w+)\s+(?P<name>[^\n]+)")

# file paths: src/foo.py, ./bar/baz.ts, /abs/path/to/file.go, etc.
_FILEPATH_RE = re.compile(
    r"(?:^|[\s(`'\"])"
    r"(?P<path>(?:\.{0,2}/)?[\w./\-]+\.(?:py|ts|js|tsx|jsx|rs|go|java|rb|sh|yaml|yml|json|toml|md))"
)

# Python: import foo / from foo.bar import baz
_PY_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(?P<name>[\w.]+)", re.MULTILINE)

# JS/TS: import ... from 'pkg' / require('pkg')  (skip relative paths)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from|require)\s+['"](?P<name>[^'"@./][^'"]*?)['"]"""
)


@dataclass
class ExtractedEntity:
    entity_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    positions: list[int] = field(default_factory=list)
    confidence: float = 0.8


def extract(body: str, frontmatter: dict | None = None) -> list[ExtractedEntity]:
    """Extract entities from *body* text and optional *frontmatter* dict."""
    entities: dict[tuple[str, str], ExtractedEntity] = {}

    _from_frontmatter(frontmatter or {}, entities)
    _from_inline_annotations(body, entities)
    _from_file_paths(body, entities)
    _from_imports(body, entities)

    return list(entities.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _key(entity_type: str, name: str) -> tuple[str, str]:
    return (entity_type.lower().strip(), name.strip().lower())


def _upsert(
    entities: dict[tuple[str, str], ExtractedEntity],
    entity_type: str,
    name: str,
    alias: str | None = None,
    attributes: dict | None = None,
    position: int | None = None,
    confidence: float = 0.8,
) -> None:
    entity_type = entity_type.lower().strip()
    name = name.strip()
    if not name or entity_type not in ENTITY_TYPES:
        return
    k = _key(entity_type, name)
    if k not in entities:
        entities[k] = ExtractedEntity(entity_type=entity_type, name=name, confidence=confidence)
    e = entities[k]
    if alias and alias not in e.aliases and alias != name:
        e.aliases.append(alias)
    if attributes:
        e.attributes.update(attributes)
    if position is not None and position not in e.positions:
        e.positions.append(position)


def _from_frontmatter(fm: dict, entities: dict[tuple[str, str], ExtractedEntity]) -> None:
    raw_list = fm.get("entities")
    if not raw_list or not isinstance(raw_list, list):
        return
    for item in raw_list:
        if isinstance(item, str):
            if "::" in item:
                et, _, nm = item.partition("::")
                _upsert(entities, et.strip(), nm.strip(), confidence=0.9)
        elif isinstance(item, dict):
            et = str(item.get("entity_type") or item.get("type") or "")
            nm = str(item.get("name") or "")
            aliases = item.get("aliases") or []
            attrs = {
                k: v for k, v in item.items()
                if k not in ("type", "entity_type", "name", "aliases")
            }
            _upsert(entities, et, nm, attributes=attrs, confidence=0.9)
            for a in aliases:
                if isinstance(a, str):
                    _upsert(entities, et, nm, alias=a, confidence=0.9)


def _from_inline_annotations(body: str, entities: dict[tuple[str, str], ExtractedEntity]) -> None:
    for m in _INLINE_RE.finditer(body):
        et = m.group("type")
        nm = m.group("name").strip()
        _upsert(entities, et, nm, position=m.start(), confidence=0.85)


def _from_file_paths(body: str, entities: dict[tuple[str, str], ExtractedEntity]) -> None:
    for m in _FILEPATH_RE.finditer(body):
        path = m.group("path").strip()
        if len(path) < 5:
            continue
        _upsert(entities, "file", path, position=m.start(), confidence=0.7)


def _from_imports(body: str, entities: dict[tuple[str, str], ExtractedEntity]) -> None:
    for m in _PY_IMPORT_RE.finditer(body):
        nm = m.group("name").strip()
        if not nm:
            continue
        top = nm.split(".")[0]
        _upsert(entities, "library", top, position=m.start(), confidence=0.65)

    for m in _JS_IMPORT_RE.finditer(body):
        nm = m.group("name").strip()
        if nm:
            _upsert(entities, "library", nm, position=m.start(), confidence=0.65)
