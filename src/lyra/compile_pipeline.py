"""M1.4 — compile pipeline: raw → wiki/sources/ (ADR-6: flat raw/).

Iterates ``raw/*.md`` flat and promotes records whose ``kind:`` frontmatter is
``research`` or ``clip`` into ``wiki/sources/``.  Sessions (``kind: session``)
are deferred to a later vertical.  Canonical wiki frontmatter:

```yaml
id: <ULID>          # durable canonical identity
type: source
sources: [<raw_id>, ...]
confidence: 0.5     # default for ingested research; refined over time
created: <ISO 8601 date>
last_confirmed: <ISO 8601 date>
supersedes: []
superseded_by: null
relations: [{type, target_id|target, confidence?}, ...]   # resolved at compile
```

Idempotent rebuild: pages already promoted (matched via ``sources`` containing
the raw_id) are updated in place with a refreshed ``last_confirmed``. New
relations are merged; existing typed relations are preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from lyra import markdown as md
from lyra.ids import new_ulid
from lyra.relations import WIKILINK_RE, RawRelation, parse_document
from lyra.index.graph_projection import GraphProjectionConfig, open_db, upsert_from_vault

WIKI_SOURCES_DIR = "wiki/sources"
PROMOTABLE_KINDS = {"research", "clip"}


@dataclass
class CompileReport:
    promoted: list[Path]
    updated: list[Path]
    skipped: list[Path]
    errors: list[tuple[Path, str]]


def compile_vault(vault_path: Path) -> CompileReport:
    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])
    raw_root = vault_path / "raw"
    if not raw_root.exists():
        report.errors.append((raw_root, "raw/ does not exist"))
        return report

    # Pass 1: promote raws into wiki pages. Cross-page relations may stay
    # unresolved (target: "[[Title]]") if the target page is created later in
    # this same run; pass 2 cleans that up.
    title_to_page = _build_title_index(vault_path)
    for raw_path in sorted(raw_root.glob("*.md")):
        try:
            _promote_one(raw_path, vault_path, title_to_page, report)
        except Exception as exc:  # noqa: BLE001 — log and continue
            report.errors.append((raw_path, str(exc)))

    # Pass 2: rebuild title index now that all pages exist, then sweep wiki
    # pages and replace any unresolved `target: "[[Title]]"` with `target_id`.
    title_to_page = _build_title_index(vault_path)
    _resolve_pending_relations(vault_path, title_to_page)

    _regen_index(vault_path)
    _append_log(vault_path, report)
    _upsert_graph(vault_path)
    return report


def _resolve_pending_relations(vault_path: Path, title_to_page: dict[str, dict]) -> None:
    wiki_root = vault_path / "wiki"
    if not wiki_root.exists():
        return
    for path in wiki_root.rglob("*.md"):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        doc = md.read(path)
        rels = doc.frontmatter.get("relations") or []
        if not rels:
            continue
        new_rels: list[dict] = []
        changed = False
        for rel in rels:
            if not isinstance(rel, dict) or rel.get("target_id"):
                new_rels.append(rel)
                continue
            title = _extract_title(rel.get("target"))
            if title and title in title_to_page:
                resolved: dict = {
                    "type": rel.get("type"),
                    "target_id": title_to_page[title]["id"],
                }
                if "confidence" in rel:
                    resolved["confidence"] = rel["confidence"]
                new_rels.append(resolved)
                changed = True
            else:
                new_rels.append(rel)
        if changed:
            doc.frontmatter["relations"] = new_rels
            md.write(path, doc)


def _extract_title(target) -> str | None:
    if not isinstance(target, str):
        return None
    match = WIKILINK_RE.search(target)
    if match:
        return match.group("title").strip()
    stripped = target.strip()
    return stripped or None


def _promote_one(
    raw_path: Path,
    vault_path: Path,
    title_to_page: dict[str, dict],
    report: CompileReport,
) -> None:
    raw_doc = md.read(raw_path)
    raw_id = raw_doc.frontmatter.get("raw_id")
    kind = raw_doc.frontmatter.get("kind")
    if not raw_id or kind not in PROMOTABLE_KINDS:
        report.skipped.append(raw_path)
        return

    title = raw_doc.frontmatter.get("title") or raw_path.stem
    raw_relations = parse_document(raw_doc.frontmatter, raw_doc.body)

    existing = _find_existing(vault_path, raw_id)
    if existing is not None:
        _update_existing(existing, raw_id, raw_relations, title_to_page, report)
        return

    page_id = new_ulid()
    page_slug = md.slug(title)
    page_path = vault_path / WIKI_SOURCES_DIR / f"{page_slug}.md"
    page_path = _disambiguate(page_path)

    today = date.today().isoformat()
    frontmatter: dict = {
        "id": page_id,
        "title": title,
        "type": "source",
        "sources": [raw_id],
        "confidence": 0.5,
        "created": today,
        "last_confirmed": today,
        "supersedes": [],
        "superseded_by": None,
        "relations": _resolve_relations(raw_relations, title_to_page),
    }

    body = _render_body(title, raw_doc, vault_path)
    md.write(page_path, md.Document(frontmatter=frontmatter, body=body))
    report.promoted.append(page_path)


def _update_existing(
    page_path: Path,
    raw_id: str,
    raw_relations: list[RawRelation],
    title_to_page: dict[str, dict],
    report: CompileReport,
) -> None:
    doc = md.read(page_path)
    today = date.today().isoformat()
    doc.frontmatter["last_confirmed"] = today

    sources = doc.frontmatter.get("sources") or []
    if raw_id not in sources:
        sources.append(raw_id)
        doc.frontmatter["sources"] = sources

    merged = _merge_relations(doc.frontmatter.get("relations"), raw_relations, title_to_page)
    doc.frontmatter["relations"] = merged

    md.write(page_path, doc)
    report.updated.append(page_path)


def _resolve_relations(
    raw_relations: Iterable[RawRelation],
    title_to_page: dict[str, dict],
) -> list[dict]:
    out: list[dict] = []
    for rel in raw_relations:
        item: dict = {"type": rel.type}
        if rel.target_id:
            item["target_id"] = rel.target_id
        elif rel.target_title and rel.target_title in title_to_page:
            item["target_id"] = title_to_page[rel.target_title]["id"]
        elif rel.target_title:
            item["target"] = f"[[{rel.target_title}]]"
        if rel.confidence is not None:
            item["confidence"] = rel.confidence
        out.append(item)
    return out


def _merge_relations(
    existing: list | None,
    raw_relations: list[RawRelation],
    title_to_page: dict[str, dict],
) -> list[dict]:
    keyed: dict[tuple[str, str], dict] = {}
    for item in existing or []:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("type", "")),
            str(item.get("target_id") or item.get("target") or ""),
        )
        keyed[key] = item

    for resolved in _resolve_relations(raw_relations, title_to_page):
        key = (
            str(resolved.get("type", "")),
            str(resolved.get("target_id") or resolved.get("target") or ""),
        )
        keyed[key] = {**keyed.get(key, {}), **resolved}

    return list(keyed.values())


def _build_title_index(vault_path: Path) -> dict[str, dict]:
    """Map page title → frontmatter so relation resolution can find ULIDs."""
    out: dict[str, dict] = {}
    wiki_root = vault_path / "wiki"
    if not wiki_root.exists():
        return out
    for path in wiki_root.rglob("*.md"):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        doc = md.read(path)
        title = doc.frontmatter.get("title")
        if title and "id" in doc.frontmatter:
            out[str(title)] = doc.frontmatter
    return out


def _find_existing(vault_path: Path, raw_id: str) -> Path | None:
    sources_root = vault_path / WIKI_SOURCES_DIR
    if not sources_root.exists():
        return None
    for path in sources_root.glob("*.md"):
        doc = md.read(path)
        sources = doc.frontmatter.get("sources") or []
        if raw_id in sources:
            return path
    return None


def _disambiguate(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _render_body(title: str, raw_doc: md.Document, vault_path: Path) -> str:
    source_ref = raw_doc.frontmatter.get("source", "")
    body_excerpt = raw_doc.body.strip()
    if len(body_excerpt) > 4000:
        body_excerpt = body_excerpt[:4000].rstrip() + "\n\n…"
    return (
        f"# {title}\n\n"
        f"> Source: `{source_ref}`\n\n"
        f"{body_excerpt}\n"
    )


def _regen_index(vault_path: Path) -> None:
    wiki_root = vault_path / "wiki"
    pages: list[tuple[str, Path]] = []
    for path in sorted(wiki_root.rglob("*.md")):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        doc = md.read(path)
        title = str(doc.frontmatter.get("title") or path.stem)
        rel = path.relative_to(wiki_root)
        pages.append((title, rel))

    lines = ["# Wiki Index", ""]
    for title, rel in pages:
        lines.append(f"- [{title}]({rel.as_posix()})")
    lines.append("")
    (wiki_root / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _upsert_graph(vault_path: Path) -> None:
    try:
        cfg = GraphProjectionConfig()
        conn = open_db(cfg)
        upsert_from_vault(vault_path, conn)
        conn.close()
    except Exception:  # noqa: BLE001 — graph is derived, never block compile
        pass


def _append_log(vault_path: Path, report: CompileReport) -> None:
    log_path = vault_path / "wiki" / "log.md"
    today = date.today().isoformat()
    line = (
        f"- {today} — promoted={len(report.promoted)} "
        f"updated={len(report.updated)} skipped={len(report.skipped)} "
        f"errors={len(report.errors)}"
    )
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing + line + "\n", encoding="utf-8")
