"""Typed relation parser (M1.5).

Two surfaces produce a typed relation:

1. Frontmatter ``relations:`` list — already structured. Each item must be a
   mapping with at least ``type`` and either ``target_id`` (ULID) or ``target``
   (a wikilink string like ``[[Page Name]]`` or a bare title).
2. Inline annotations in the body — ``supports::`` / ``contradicts::`` /
   ``uses::`` / ``supersedes:: [[Page Name]]``.

The parser does not resolve titles to ULIDs by itself: that's the compile
step's job, since it owns the page → ULID lookup table. The parser returns
``RawRelation`` rows with the raw target text; the caller resolves them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from lyra.ids import is_ulid

ALLOWED_TYPES: frozenset[str] = frozenset(
    {"supports", "contradicts", "uses", "supersedes", "depends_on", "caused", "fixed"}
)

INLINE_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?P<type>[a-z_]+)::\s+(?P<target>.+?)\s*$",
    re.MULTILINE,
)
WIKILINK_RE = re.compile(r"\[\[(?P<title>[^\]|]+)(?:\|[^\]]*)?\]\]")


@dataclass(frozen=True)
class RawRelation:
    """Pre-resolution relation. ``target_id`` is set if the target is already a ULID."""

    type: str
    target_id: str | None
    target_title: str | None
    confidence: float | None = None
    origin: str = "inline"  # "inline" | "frontmatter"


def parse_inline(body: str) -> list[RawRelation]:
    out: list[RawRelation] = []
    for match in INLINE_RE.finditer(body):
        rel_type = match.group("type")
        if rel_type not in ALLOWED_TYPES:
            continue
        raw_target = match.group("target").strip()
        rel = _classify_target(rel_type, raw_target, origin="inline")
        if rel is not None:
            out.append(rel)
    return out


def parse_frontmatter(items: Iterable[dict] | None) -> list[RawRelation]:
    out: list[RawRelation] = []
    if not items:
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        rel_type = str(item.get("type", "")).strip()
        if rel_type not in ALLOWED_TYPES:
            continue
        target_id = item.get("target_id")
        target = item.get("target")
        confidence = item.get("confidence")
        if target_id and is_ulid(str(target_id)):
            out.append(
                RawRelation(
                    type=rel_type,
                    target_id=str(target_id),
                    target_title=None,
                    confidence=_safe_float(confidence),
                    origin="frontmatter",
                )
            )
        elif target:
            wikilink = WIKILINK_RE.search(str(target))
            title = wikilink.group("title").strip() if wikilink else str(target).strip()
            out.append(
                RawRelation(
                    type=rel_type,
                    target_id=None,
                    target_title=title,
                    confidence=_safe_float(confidence),
                    origin="frontmatter",
                )
            )
    return out


def parse_document(frontmatter: dict, body: str) -> list[RawRelation]:
    """Parse both surfaces and return the merged list, deduplicated by (type, target)."""
    rels = parse_frontmatter(frontmatter.get("relations"))
    rels.extend(parse_inline(body))
    seen: set[tuple[str, str]] = set()
    deduped: list[RawRelation] = []
    for rel in rels:
        key = (rel.type, rel.target_id or rel.target_title or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rel)
    return deduped


def _classify_target(rel_type: str, raw_target: str, *, origin: str) -> RawRelation | None:
    wikilink = WIKILINK_RE.search(raw_target)
    if wikilink:
        title = wikilink.group("title").strip()
        return RawRelation(
            type=rel_type,
            target_id=None,
            target_title=title,
            origin=origin,
        )
    if is_ulid(raw_target):
        return RawRelation(
            type=rel_type,
            target_id=raw_target,
            target_title=None,
            origin=origin,
        )
    # Bare title fallback (no wikilink, not a ULID). Allow but require lookup.
    return RawRelation(
        type=rel_type,
        target_id=None,
        target_title=raw_target.strip(),
        origin=origin,
    )


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
