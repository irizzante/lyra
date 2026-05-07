"""M1.7 — lyra query: hybrid BM25/vector/graph retrieval.

Runs ``qmd search`` (BM25/FTS5) and optionally ``qmd vsearch`` (vector),
merges and deduplicates hits, then expands top results via one-hop graph
traversal. Returns ranked hits with citations and per-claim confidence.

No proprietary LLM API keys required (NFR4). Vector search requires the
local embedding model (Qwen3-Embedding-0.6B) to have been indexed via
``lyra index --rebuild``; falls back gracefully to BM25-only if vector
index is absent or fails.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from lyra import markdown as md
from lyra.index.graph_projection import GraphProjectionConfig, open_db, neighbours

# Pattern for qmd search/vsearch text output
_HIT_RE = re.compile(
    r"^qmd://(?P<collection>[^/]+)/(?P<rel_path>[^\s:]+):(?P<line>\d+)\s+#\w+",
    re.MULTILINE,
)
_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)
_SCORE_RE = re.compile(r"^Score:\s*([\d.]+)%", re.MULTILINE)
_SNIPPET_RE = re.compile(r"^@@[^\n]*\n(.*?)(?=\nqmd://|\Z)", re.DOTALL | re.MULTILINE)

COLLECTION_NAME = "lyra-wiki"


@dataclass
class QueryHit:
    id: str
    source: str
    title: str
    snippet: str
    score: float
    file_path: str
    last_seen: str
    citations: list[str] = field(default_factory=list)
    via_graph: bool = False


def hybrid_query(
    query: str,
    vault_path: Path,
    *,
    k: int = 10,
    graph_config: GraphProjectionConfig | None = None,
    use_vector: bool = True,
) -> list[QueryHit]:
    """Run hybrid BM25/vector/graph query over the wiki.

    Returns up to ``k`` hits ordered by descending score.
    """
    wiki_root = vault_path / "wiki"

    bm25_hits = _run_qmd_search(query, k=k * 2, vector=False, wiki_root=wiki_root)
    vector_hits: list[QueryHit] = []
    if use_vector:
        try:
            vector_hits = _run_qmd_search(query, k=k * 2, vector=True, wiki_root=wiki_root)
        except Exception:  # noqa: BLE001
            pass  # vector index absent — BM25 only

    merged = _merge_hits(bm25_hits, vector_hits, vault_path=vault_path)

    if not merged:
        return []

    # One-hop graph expansion: for top hits that have a ULID id, fetch neighbours
    try:
        cfg = graph_config or GraphProjectionConfig()
        if cfg.db_path.exists():
            conn = open_db(cfg)
            try:
                merged = _expand_graph(merged, conn, vault_path, k=k)
            finally:
                conn.close()
    except Exception:  # noqa: BLE001
        pass

    return sorted(merged, key=lambda h: h.score, reverse=True)[:k]


def _run_qmd_search(
    query: str,
    k: int,
    *,
    vector: bool,
    wiki_root: Path,
) -> list[QueryHit]:
    cmd_name = "vsearch" if vector else "search"
    result = subprocess.run(
        ["qmd", cmd_name, query, "-n", str(k), "-c", COLLECTION_NAME],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 and not result.stdout:
        return []
    return _parse_qmd_output(result.stdout, wiki_root=wiki_root)


def _parse_qmd_output(text: str, wiki_root: Path) -> list[QueryHit]:
    hits: list[QueryHit] = []
    # Split on hit boundaries: lines starting with "qmd://"
    blocks = re.split(r"\n(?=qmd://)", text.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m_hit = _HIT_RE.match(block)
        if not m_hit:
            continue
        rel_path = m_hit.group("rel_path")
        m_title = _TITLE_RE.search(block)
        m_score = _SCORE_RE.search(block)
        m_snippet = _SNIPPET_RE.search(block)

        title = m_title.group(1).strip() if m_title else rel_path
        score = float(m_score.group(1)) / 100.0 if m_score else 0.0
        snippet = m_snippet.group(1).strip() if m_snippet else ""

        abs_path = wiki_root / rel_path
        page_id, last_seen = _read_page_meta(abs_path)

        hits.append(
            QueryHit(
                id=page_id,
                source=COLLECTION_NAME,
                title=title,
                snippet=snippet,
                score=score,
                file_path=str(abs_path),
                last_seen=last_seen,
                citations=[str(abs_path.relative_to(wiki_root))] if abs_path.exists() else [],
            )
        )
    return hits


def _read_page_meta(path: Path) -> tuple[str, str]:
    """Return (page_id, last_confirmed) from frontmatter, or empty strings."""
    if not path.exists():
        return "", ""
    try:
        doc = md.read(path)
        return (
            str(doc.frontmatter.get("id") or ""),
            str(doc.frontmatter.get("last_confirmed") or ""),
        )
    except Exception:  # noqa: BLE001
        return "", ""


def _merge_hits(
    bm25: list[QueryHit],
    vector: list[QueryHit],
    *,
    bm25_weight: float = 0.4,
    vector_weight: float = 0.6,
    vault_path: Path,
) -> list[QueryHit]:
    """Reciprocal rank fusion of BM25 and vector hit lists."""
    scores: dict[str, float] = {}
    by_path: dict[str, QueryHit] = {}

    for rank, hit in enumerate(bm25):
        scores[hit.file_path] = scores.get(hit.file_path, 0.0) + bm25_weight * (1.0 / (rank + 1))
        by_path[hit.file_path] = hit

    for rank, hit in enumerate(vector):
        scores[hit.file_path] = scores.get(hit.file_path, 0.0) + vector_weight * (1.0 / (rank + 1))
        if hit.file_path not in by_path:
            by_path[hit.file_path] = hit

    merged = []
    for fp, score in scores.items():
        h = by_path[fp]
        merged.append(
            QueryHit(
                id=h.id,
                source=h.source,
                title=h.title,
                snippet=h.snippet,
                score=score,
                file_path=h.file_path,
                last_seen=h.last_seen,
                citations=h.citations,
            )
        )
    return merged


def _expand_graph(
    hits: list[QueryHit],
    conn,
    vault_path: Path,
    k: int,
) -> list[QueryHit]:
    """Add one-hop graph neighbours of top-k hits (boosted score)."""
    wiki_root = vault_path / "wiki"
    by_id: dict[str, QueryHit] = {h.id: h for h in hits if h.id}
    by_path: dict[str, QueryHit] = {h.file_path: h for h in hits}

    new_hits: list[QueryHit] = []
    for hit in hits[:k]:
        if not hit.id:
            continue
        try:
            nbrs = neighbours(conn, hit.id, direction="both")
        except Exception:  # noqa: BLE001
            continue
        for src_id, edge_type, dst_id, confidence in nbrs:
            neighbour_id = dst_id if src_id == hit.id else src_id
            if neighbour_id in by_id:
                continue
            page_path = _find_page_by_id(wiki_root, neighbour_id)
            if not page_path or str(page_path) in by_path:
                continue
            n_id, n_last = _read_page_meta(page_path)
            try:
                doc = md.read(page_path)
                n_title = str(doc.frontmatter.get("title") or page_path.stem)
                n_conf = float(doc.frontmatter.get("confidence") or 0.3)
            except Exception:  # noqa: BLE001
                n_title = page_path.stem
                n_conf = 0.3
            graph_score = hit.score * 0.5 * (confidence or 0.5)
            gh = QueryHit(
                id=neighbour_id,
                source=COLLECTION_NAME,
                title=n_title,
                snippet=f"[via {edge_type} from {hit.title}]",
                score=graph_score,
                file_path=str(page_path),
                last_seen=n_last,
                citations=[str(page_path.relative_to(wiki_root))],
                via_graph=True,
            )
            new_hits.append(gh)
            by_id[neighbour_id] = gh
            by_path[str(page_path)] = gh

    return hits + new_hits


def _find_page_by_id(wiki_root: Path, page_id: str) -> Path | None:
    for path in wiki_root.rglob("*.md"):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        try:
            doc = md.read(path)
            if doc.frontmatter.get("id") == page_id:
                return path
        except Exception:  # noqa: BLE001
            continue
    return None


def format_results(hits: list[QueryHit], *, show_snippet: bool = True) -> str:
    if not hits:
        return "No results found in the compiled wiki."
    lines: list[str] = []
    for i, hit in enumerate(hits, 1):
        via = " [graph]" if hit.via_graph else ""
        lines.append(f"{i}. **{hit.title}**{via}  (score={hit.score:.2f}, conf={hit.last_seen})")
        if hit.citations:
            lines.append(f"   → {hit.citations[0]}")
        if show_snippet and hit.snippet:
            first_line = hit.snippet.splitlines()[0][:120]
            lines.append(f"   {first_line}")
    return "\n".join(lines)
