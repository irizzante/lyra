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
from dataclasses import dataclass, field
from pathlib import Path

from lyra import markdown as md
from lyra.index.graph_projection import GraphProjectionConfig, open_db, traverse

# Pattern for qmd search/vsearch text output
_HIT_RE = re.compile(
    r"^qmd://(?P<collection>[^/]+)/(?P<rel_path>[^\s:]+):(?P<line>\d+)\s+#\w+",
    re.MULTILINE,
)
_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)
_SCORE_RE = re.compile(r"^Score:\s*([\d.]+)%", re.MULTILINE)
_SNIPPET_RE = re.compile(r"^@@[^\n]*\n(.*?)(?=\nqmd://|\Z)", re.DOTALL | re.MULTILINE)

COLLECTION_NAME = "lyra-wiki"
RRF_K = 60


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


def fanout_query(
    query: str,
    sources: list,  # list[tuple[str, Source]]
    *,
    k: int = 10,
) -> list[QueryHit]:
    """Fan-out query across external Source adapters, merge results.

    Each source's ``query()`` result is normalised to QueryHit and merged
    by id (deduplication). Sources that raise are skipped with a warning.
    """
    import warnings
    from lyra.sources.base import Result

    merged: dict[str, QueryHit] = {}

    for name, src in sources:
        try:
            results: list[Result] = src.query(query, k=k)
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Source {name!r} failed during query: {exc}", stacklevel=2)
            continue
        for i, r in enumerate(results):
            hit_id = r.id or f"{name}:{i}"
            if hit_id in merged:
                continue
            merged[hit_id] = QueryHit(
                id=hit_id,
                source=r.source or name,
                title=r.title,
                snippet=r.snippet,
                score=r.score,
                file_path="",
                last_seen=r.last_seen.isoformat() if r.last_seen else "",
                citations=r.citations,
            )

    return sorted(merged.values(), key=lambda h: h.score, reverse=True)[:k]


def hybrid_query(
    query: str,
    vault_path: Path,
    *,
    k: int = 10,
    graph_config: GraphProjectionConfig | None = None,
    use_vector: bool = True,
    extra_sources: list | None = None,
    max_hops: int = 2,
) -> list[QueryHit]:
    """Run hybrid BM25/vector/graph query over the wiki.

    Three retrieval streams — BM25, vector, and multi-hop graph traversal —
    are fused with Reciprocal Rank Fusion (k=60).  Returns up to ``k`` hits
    ordered by descending RRF score.
    """
    wiki_root = vault_path / "wiki"

    bm25_hits = _run_qmd_search(query, k=k * 2, vector=False, wiki_root=wiki_root)
    vector_hits: list[QueryHit] = []
    if use_vector:
        try:
            vector_hits = _run_qmd_search(query, k=k * 2, vector=True, wiki_root=wiki_root)
        except Exception:  # noqa: BLE001
            pass

    extra_hits: list[QueryHit] = []
    if extra_sources:
        extra_hits = fanout_query(query, extra_sources, k=k)

    graph_hits: list[QueryHit] = []
    try:
        cfg = graph_config or GraphProjectionConfig()
        if cfg.db_path.exists():
            conn = open_db(cfg)
            try:
                graph_hits = _expand_graph(
                    bm25_hits + vector_hits, conn, vault_path, k=k, max_hops=max_hops
                )
            finally:
                conn.close()
    except Exception:  # noqa: BLE001
        pass

    streams = [s for s in [bm25_hits, vector_hits, graph_hits, extra_hits] if s]
    if not streams:
        return []

    return sorted(_rrf_merge(streams), key=lambda h: h.score, reverse=True)[:k]


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


def _rrf_merge(streams: list[list[QueryHit]]) -> list[QueryHit]:
    """Reciprocal Rank Fusion (k=60) over arbitrary ranked streams.

    Each stream contributes ``1 / (RRF_K + rank + 1)`` per document (rank is
    0-indexed).  Documents are keyed by ``file_path`` when non-empty, else by
    ``id``.  First-seen hit data is kept; scores accumulate across streams.
    """
    scores: dict[str, float] = {}
    by_key: dict[str, QueryHit] = {}

    for stream in streams:
        for rank, hit in enumerate(stream):
            key = hit.file_path or hit.id
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            if key not in by_key:
                by_key[key] = hit

    result = []
    for key, score in scores.items():
        h = by_key[key]
        result.append(
            QueryHit(
                id=h.id,
                source=h.source,
                title=h.title,
                snippet=h.snippet,
                score=score,
                file_path=h.file_path,
                last_seen=h.last_seen,
                citations=h.citations,
                via_graph=h.via_graph,
            )
        )
    return result


def _merge_hits(
    bm25: list[QueryHit],
    vector: list[QueryHit],
    *,
    vault_path: Path,  # kept for API compatibility
    **_kwargs: object,
) -> list[QueryHit]:
    """RRF fusion of BM25 and vector hit lists (k=60)."""
    return _rrf_merge([bm25, vector])


def _expand_graph(
    hits: list[QueryHit],
    conn,
    vault_path: Path,
    k: int,
    max_hops: int = 2,
) -> list[QueryHit]:
    """Multi-hop BFS graph expansion; returns a ranked stream for RRF fusion.

    Traverses up to ``max_hops`` from the top-k seed hits using the
    ``traverse()`` recursive CTE.  Returns only nodes not already in the seed
    set, sorted by descending graph score so the list can be fed directly into
    ``_rrf_merge`` as an independent ranked stream.
    """
    wiki_root = vault_path / "wiki"
    start_ids = [h.id for h in hits[:k] if h.id]
    if not start_ids:
        return []

    try:
        reachable = traverse(conn, start_ids, max_hops=max_hops)
    except Exception:  # noqa: BLE001
        return []

    seed_scores = {h.id: h.score for h in hits if h.id}
    existing_ids = {h.id for h in hits}
    existing_paths = {h.file_path for h in hits}
    best_seed = max(seed_scores.values(), default=0.3)

    graph_hits: list[QueryHit] = []
    for page_id, hop_dist in reachable:
        if hop_dist == 0 or page_id in existing_ids:
            continue
        page_path = _find_page_by_id(wiki_root, page_id)
        if not page_path or str(page_path) in existing_paths:
            continue
        graph_score = best_seed / (1.0 + hop_dist)
        try:
            doc = md.read(page_path)
            n_title = str(doc.frontmatter.get("title") or page_path.stem)
            n_last = str(doc.frontmatter.get("last_confirmed") or "")
        except Exception:  # noqa: BLE001
            n_title = page_path.stem
            n_last = ""
        graph_hits.append(
            QueryHit(
                id=page_id,
                source=COLLECTION_NAME,
                title=n_title,
                snippet=f"[graph hop={hop_dist}]",
                score=graph_score,
                file_path=str(page_path),
                last_seen=n_last,
                citations=[str(page_path.relative_to(wiki_root))],
                via_graph=True,
            )
        )
        existing_ids.add(page_id)
        existing_paths.add(str(page_path))

    return sorted(graph_hits, key=lambda h: h.score, reverse=True)


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
