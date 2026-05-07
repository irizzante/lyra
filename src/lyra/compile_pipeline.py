"""M1.4 / M3.3 / M3.4 — compile pipeline: raw → wiki/ (ADR-6, ADR-9).

Batch mode (``compile_vault``):
  Iterates ``raw/*.md`` flat and promotes research/clip records into
  ``wiki/sources/``. Additionally runs entity extraction and upserts entity
  pages under ``wiki/entities/<entity_type>/``.

Imperative mode (``compile_page`` — M3.4):
  Single-page compile for use by the Lyra skill inside an agent session.
  ``entities_json`` present → skip provider call (entities pre-extracted).
  ``entities_json`` absent  → same provider logic as batch.

Entity extraction (M3.3, ADR-9):
  - Heuristic baseline always runs (``lyra.extract.heuristic``).
  - If ``extraction.llm.provider`` is configured AND ``--entities`` not passed,
    LiteLLM is called for richer extraction (``lyra.extract.llm``).
  - Results are merged/deduped on ``(entity_type, name)``.
  - Entity pages: ``wiki/entities/<entity_type>/<ulid>-<slug>.md``
  - Graph edges: ``mentions(src_id, entity_id, confidence)`` written to the
    graph DB projection.

Canonical wiki-source frontmatter:
```yaml
id: <ULID>          # durable canonical identity
type: source
sources: [<raw_id>, ...]
confidence: 0.5
created: <ISO 8601 date>
last_confirmed: <ISO 8601 date>
supersedes: []
superseded_by: null
relations: [...]    # resolved at compile
```
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from lyra import markdown as md
from lyra.ids import new_ulid
from lyra.relations import WIKILINK_RE, RawRelation, parse_document
from lyra.index.graph_projection import GraphProjectionConfig, open_db, upsert_from_vault
from lyra.extract.heuristic import ENTITY_TYPES, ExtractedEntity, extract as heuristic_extract

WIKI_SOURCES_DIR = "wiki/sources"
WIKI_ENTITIES_DIR = "wiki/entities"
PROMOTABLE_KINDS = {"research", "clip"}


@dataclass
class CompileReport:
    promoted: list[Path]
    updated: list[Path]
    skipped: list[Path]
    errors: list[tuple[Path, str]]
    supersession_decisions: list[dict] = field(default_factory=list)
    entities_upserted: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_vault(
    vault_path: Path,
    *,
    extraction_provider: str = "",
    extraction_model: str = "",
    extraction_endpoint: str = "",
    extraction_extra: dict | None = None,
) -> CompileReport:
    """Batch compile: all pending raw pages.  Entity extraction runs per page."""
    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])
    raw_root = vault_path / "raw"
    if not raw_root.exists():
        report.errors.append((raw_root, "raw/ does not exist"))
        return report

    title_to_page = _build_title_index(vault_path)
    for raw_path in sorted(raw_root.glob("*.md")):
        try:
            src_id = _promote_one(raw_path, vault_path, title_to_page, report)
            if src_id:
                _extract_and_upsert_entities(
                    raw_path, src_id, vault_path,
                    entities_json=None,
                    provider=extraction_provider,
                    model=extraction_model,
                    endpoint=extraction_endpoint,
                    extra=extraction_extra,
                    report=report,
                )
        except Exception as exc:  # noqa: BLE001
            report.errors.append((raw_path, str(exc)))

    title_to_page = _build_title_index(vault_path)
    _resolve_pending_relations(vault_path, title_to_page)

    # Pass 3: auto-supersession scoring on unresolved contradictions (ADR-11).
    _auto_supersede_pass(vault_path, report)

    _regen_index(vault_path)
    _append_log(vault_path, report)
    _upsert_graph(vault_path)
    return report


# ------------------------------------------------------------------
# M3.8 — Auto-supersession scoring (ADR-11)
# ------------------------------------------------------------------

def score_page(
    page_id: str,
    fm: dict,
    wiki_index: dict[str, dict],
    all_dates: list[str],
    weights: object,
) -> dict:
    """Score a page for auto-supersession. Returns component breakdown + total.

    Components:
      recency   — normalised last_confirmed date (0=oldest, 1=newest)
      authority — normalised source count (cap 5)
      support   — normalised inbound 'supports' edge count (cap 5)
    """
    rec = _recency(str(fm.get("last_confirmed") or ""), all_dates)
    auth = _authority(fm)
    sup = _inbound_supports(page_id, wiki_index)
    total = weights.recency * rec + weights.authority * auth + weights.support * sup
    return {
        "recency": round(rec, 4),
        "authority": round(auth, 4),
        "support": round(sup, 4),
        "total": round(total, 4),
    }


def _recency(date_str: str, all_dates: list[str]) -> float:
    valid = sorted(d for d in all_dates if d)
    if not valid or not date_str:
        return 0.0
    if valid[0] == valid[-1]:
        return 1.0
    if date_str <= valid[0]:
        return 0.0
    if date_str >= valid[-1]:
        return 1.0
    try:
        d = date.fromisoformat(date_str)
        dmin = date.fromisoformat(valid[0])
        dmax = date.fromisoformat(valid[-1])
        return (d - dmin).days / (dmax - dmin).days
    except ValueError:
        return 0.0


def _authority(fm: dict) -> float:
    sources = fm.get("sources") or []
    n = len(sources) if isinstance(sources, list) else 0
    return min(1.0, n / 5.0)


def _inbound_supports(page_id: str, wiki_index: dict[str, dict]) -> float:
    count = sum(
        1
        for fmx in wiki_index.values()
        for rel in (fmx.get("relations") or [])
        if isinstance(rel, dict)
        and rel.get("type") == "supports"
        and str(rel.get("target_id") or "") == page_id
    )
    return min(1.0, count / 5.0)


def _already_superseded(
    page_id: str, target_id: str, fm: dict, wiki_index: dict[str, dict]
) -> bool:
    supersedes = {str(t) for t in (fm.get("supersedes") or [])}
    superseded_by = str(fm.get("superseded_by") or "")
    if target_id in supersedes or superseded_by == target_id:
        return True
    target_fm = wiki_index.get(target_id, {})
    target_supersedes = {str(t) for t in (target_fm.get("supersedes") or [])}
    target_superseded_by = str(target_fm.get("superseded_by") or "")
    return page_id in target_supersedes or target_superseded_by == page_id


def _build_page_index(vault_path: Path) -> dict[str, dict]:
    """page_id → frontmatter+_path for all wiki pages."""
    out: dict[str, dict] = {}
    wiki_root = vault_path / "wiki"
    if not wiki_root.exists():
        return out
    for path in wiki_root.rglob("*.md"):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        try:
            doc = md.read(path)
            page_id = doc.frontmatter.get("id")
            if page_id:
                fm = dict(doc.frontmatter)
                fm["_path"] = path
                out[str(page_id)] = fm
        except Exception:  # noqa: BLE001
            pass
    return out


def _auto_supersede_pass(vault_path: Path, report: CompileReport) -> None:
    """Pass 3 (M3.8/ADR-11): auto-supersession scoring on unresolved contradictions."""
    from lyra import config as cfg_mod

    try:
        cfg = cfg_mod.load(cfg_mod.CONFIG_PATH)
        as_cfg = cfg.auto_supersession
    except Exception:  # noqa: BLE001 — no config → use defaults
        as_cfg = cfg_mod.AutoSupersessionConfig()

    if not as_cfg.enabled:
        return

    wiki_index = _build_page_index(vault_path)
    all_dates = [str(fm.get("last_confirmed") or "") for fm in wiki_index.values()]

    seen: set[frozenset] = set()
    for page_id, fm in wiki_index.items():
        contradicts = [str(t) for t in (fm.get("contradicts") or [])]
        for target_id in contradicts:
            pair: frozenset = frozenset({page_id, target_id})
            if pair in seen:
                continue
            seen.add(pair)

            if _already_superseded(page_id, target_id, fm, wiki_index):
                continue

            target_fm = wiki_index.get(target_id)
            if not target_fm:
                continue

            score_a = score_page(page_id, fm, wiki_index, all_dates, as_cfg.weights)
            score_b = score_page(target_id, target_fm, wiki_index, all_dates, as_cfg.weights)
            diff = abs(score_a["total"] - score_b["total"])

            if diff < as_cfg.threshold:
                continue  # lint will surface with score breakdown

            if score_a["total"] >= score_b["total"]:
                winner_id, winner_path = page_id, fm["_path"]
                loser_id, loser_path = target_id, target_fm["_path"]
                winner_score, loser_score = score_a["total"], score_b["total"]
            else:
                winner_id, winner_path = target_id, target_fm["_path"]
                loser_id, loser_path = page_id, fm["_path"]
                winner_score, loser_score = score_b["total"], score_a["total"]

            w_doc = md.read(winner_path)
            w_sup = [str(x) for x in (w_doc.frontmatter.get("supersedes") or [])]
            if loser_id not in w_sup:
                w_sup.append(loser_id)
                w_doc.frontmatter["supersedes"] = w_sup
                md.write(winner_path, w_doc)

            l_doc = md.read(loser_path)
            l_doc.frontmatter["superseded_by"] = winner_id
            md.write(loser_path, l_doc)

            report.supersession_decisions.append({
                "winner": winner_id,
                "loser": loser_id,
                "winner_score": round(winner_score, 3),
                "loser_score": round(loser_score, 3),
                "diff": round(diff, 3),
                "threshold": as_cfg.threshold,
            })


# ------------------------------------------------------------------
# Promotion helpers
# ------------------------------------------------------------------


def compile_page(
    raw_id: str,
    vault_path: Path,
    *,
    entities_json: str | None = None,
    extraction_provider: str = "",
    extraction_model: str = "",
    extraction_endpoint: str = "",
    extraction_extra: dict | None = None,
) -> CompileReport:
    """Imperative single-page compile (M3.4 — used by the Lyra skill).

    ``entities_json`` present → skip any LLM call; parse and apply entities
    deterministically (idempotent).

    ``entities_json`` absent → apply heuristic extraction plus LiteLLM if
    configured (same logic as batch).

    Raises ``ValueError`` on malformed JSON or unknown entity_type.
    """
    report = CompileReport(promoted=[], updated=[], skipped=[], errors=[])

    raw_root = vault_path / "raw"
    raw_path: Path | None = None
    for candidate in raw_root.glob("*.md"):
        doc = md.read(candidate)
        if doc.frontmatter.get("raw_id") == raw_id:
            raw_path = candidate
            break

    if raw_path is None:
        report.errors.append((raw_root / raw_id, f"raw record {raw_id!r} not found"))
        return report

    # Validate entities_json eagerly so the caller gets a clear error
    if entities_json is not None:
        _validate_entities_json(entities_json)

    title_to_page = _build_title_index(vault_path)
    try:
        src_id = _promote_one(raw_path, vault_path, title_to_page, report)
        if src_id:
            _extract_and_upsert_entities(
                raw_path, src_id, vault_path,
                entities_json=entities_json,
                provider=extraction_provider,
                model=extraction_model,
                endpoint=extraction_endpoint,
                extra=extraction_extra,
                report=report,
            )
    except Exception as exc:  # noqa: BLE001
        report.errors.append((raw_path, str(exc)))

    title_to_page = _build_title_index(vault_path)
    _resolve_pending_relations(vault_path, title_to_page)
    _regen_index(vault_path)
    _append_log(vault_path, report)
    _upsert_graph(vault_path)
    return report


# ---------------------------------------------------------------------------
# Entity extraction + upsert (M3.3)
# ---------------------------------------------------------------------------

def _validate_entities_json(entities_json: str) -> list[dict]:
    """Parse and validate entities JSON.  Raises ValueError on bad input."""
    try:
        parsed = json.loads(entities_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed entities JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"entities JSON must be a list, got {type(parsed).__name__}")

    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"entities[{i}] must be an object, got {type(item).__name__}")
        et = str(item.get("entity_type") or item.get("type") or "")
        nm = str(item.get("name") or "")
        if not et:
            raise ValueError(f"entities[{i}] missing 'entity_type'")
        if et not in ENTITY_TYPES:
            raise ValueError(
                f"entities[{i}] unknown entity_type {et!r}; valid: {sorted(ENTITY_TYPES)}"
            )
        if not nm:
            raise ValueError(f"entities[{i}] missing 'name'")

    return parsed


def _json_to_extracted(parsed: list[dict]) -> list[ExtractedEntity]:
    out: list[ExtractedEntity] = []
    for item in parsed:
        et = str(item.get("entity_type") or item.get("type") or "").lower().strip()
        nm = str(item.get("name") or "").strip()
        aliases = [str(a) for a in (item.get("aliases") or []) if isinstance(a, str)]
        attrs = dict(item.get("attributes") or {})
        out.append(ExtractedEntity(entity_type=et, name=nm, aliases=aliases, attributes=attrs, confidence=0.9))
    return out


def _extract_and_upsert_entities(
    raw_path: Path,
    src_id: str,
    vault_path: Path,
    *,
    entities_json: str | None,
    provider: str,
    model: str,
    endpoint: str,
    extra: dict | None,
    report: CompileReport,
) -> None:
    raw_doc = md.read(raw_path)

    if entities_json is not None:
        # Imperative path: entities pre-extracted, apply deterministically
        parsed = _validate_entities_json(entities_json)
        entities = _json_to_extracted(parsed)
    else:
        # Heuristic baseline always runs
        entities = heuristic_extract(raw_doc.body, raw_doc.frontmatter)

        # LiteLLM path: only if provider is configured
        if provider:
            try:
                from lyra.extract.llm import extract_with_llm  # noqa: PLC0415
                llm_entities = extract_with_llm(
                    raw_doc.body,
                    raw_doc.frontmatter,
                    provider=provider,
                    model=model,
                    endpoint=endpoint,
                    extra=extra or {},
                )
                entities = _merge_entities(entities, llm_entities)
            except Exception as exc:  # noqa: BLE001
                print(f"lyra warning: LLM extraction error ({exc}); using heuristic only", file=sys.stderr)

    for entity in entities:
        try:
            _upsert_entity_page(entity, src_id, vault_path)
            report.entities_upserted += 1
        except Exception as exc:  # noqa: BLE001
            report.errors.append((raw_path, f"entity upsert failed for {entity.name!r}: {exc}"))


def _merge_entities(
    heuristic: list[ExtractedEntity],
    llm: list[ExtractedEntity],
) -> list[ExtractedEntity]:
    """Merge lists, deduping on (entity_type, normalised name).  LLM wins on conflicts."""
    index: dict[tuple[str, str], ExtractedEntity] = {}
    for e in heuristic:
        index[(e.entity_type, e.name.lower())] = e
    for e in llm:
        index[(e.entity_type, e.name.lower())] = e  # LLM overwrites
    return list(index.values())


def _upsert_entity_page(entity: ExtractedEntity, src_id: str, vault_path: Path) -> Path:
    """Create or update an entity page.  Returns the page path."""
    entities_dir = vault_path / WIKI_ENTITIES_DIR / entity.entity_type
    entities_dir.mkdir(parents=True, exist_ok=True)

    # Find existing entity page by (entity_type, name) — case-insensitive match on title
    existing = _find_entity_page(entities_dir, entity.name)
    today = date.today().isoformat()

    if existing is not None:
        doc = md.read(existing)
        doc.frontmatter["last_confirmed"] = today

        # Merge aliases
        current_aliases = list(doc.frontmatter.get("aliases") or [])
        for a in entity.aliases:
            if a not in current_aliases:
                current_aliases.append(a)
        doc.frontmatter["aliases"] = current_aliases

        # Merge attributes
        attrs = dict(doc.frontmatter.get("attributes") or {})
        attrs.update(entity.attributes)
        doc.frontmatter["attributes"] = attrs

        # Track which source pages mention this entity (deduplicated)
        mentioned_by = list(doc.frontmatter.get("mentioned_by") or [])
        if src_id not in mentioned_by:
            mentioned_by.append(src_id)
        doc.frontmatter["mentioned_by"] = mentioned_by

        md.write(existing, doc)
        return existing

    # Create new entity page
    page_id = new_ulid()
    slug = md.slug(entity.name)
    page_path = _disambiguate(entities_dir / f"{page_id}-{slug}.md")

    frontmatter: dict = {
        "id": page_id,
        "title": entity.name,
        "type": "entity",
        "entity_type": entity.entity_type,
        "aliases": entity.aliases,
        "attributes": entity.attributes,
        "created": today,
        "last_confirmed": today,
        "mentioned_by": [src_id],
        "supersedes": [],
        "superseded_by": None,
        "relations": [],
    }
    body = f"# {entity.name}\n\nEntity type: `{entity.entity_type}`\n"
    md.write(page_path, md.Document(frontmatter=frontmatter, body=body))
    return page_path


def _find_entity_page(entities_dir: Path, name: str) -> Path | None:
    """Find an existing entity page by normalised title match."""
    norm = name.strip().lower()
    for path in entities_dir.glob("*.md"):
        doc = md.read(path)
        title = str(doc.frontmatter.get("title") or "")
        aliases = doc.frontmatter.get("aliases") or []
        if title.lower() == norm:
            return path
        if any(str(a).lower() == norm for a in aliases):
            return path
    return None


# ---------------------------------------------------------------------------
# Source page promotion (M1.4 — unchanged logic, now returns src_id)
# ---------------------------------------------------------------------------

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
) -> str | None:
    """Promote a single raw page.  Returns the wiki-page ULID if promoted/updated, else None."""
    raw_doc = md.read(raw_path)
    raw_id = raw_doc.frontmatter.get("raw_id")
    kind = raw_doc.frontmatter.get("kind")
    if not raw_id or kind not in PROMOTABLE_KINDS:
        report.skipped.append(raw_path)
        return None

    title = raw_doc.frontmatter.get("title") or raw_path.stem
    raw_relations = parse_document(raw_doc.frontmatter, raw_doc.body)

    existing = _find_existing(vault_path, raw_id)
    if existing is not None:
        src_id = _update_existing(existing, raw_id, raw_relations, title_to_page, report)
        return src_id

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
    return page_id


def _update_existing(
    page_path: Path,
    raw_id: str,
    raw_relations: list[RawRelation],
    title_to_page: dict[str, dict],
    report: CompileReport,
) -> str:
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
    return str(doc.frontmatter.get("id") or "")


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
    decisions = len(report.supersession_decisions)
    line = (
        f"- {today} — promoted={len(report.promoted)} "
        f"updated={len(report.updated)} skipped={len(report.skipped)} "
        f"errors={len(report.errors)} entities={report.entities_upserted}"
        + (f" auto_superseded={decisions}" if decisions else "")
    )
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing + line + "\n", encoding="utf-8")
