"""M1.6 — qmd-backed BM25/FTS5 + vector index over the canonical wiki.

qmd manages a global collection registry. This module registers a collection
named ``lyra-wiki`` pointing at ``<vault>/wiki/`` and shells out to qmd
subcommands for build and search. The graph projection is a separate concern
(see ``graph_projection.py``).

Design
------
- The vault is the source of truth. The index is derived and rebuildable.
- qmd handles BM25/FTS5 + vector embeddings + reranking.
- Index lives outside the vault (managed by qmd) so it never pollutes the
  markdown source of truth.
- ``build()`` is idempotent: re-running updates an existing collection.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INDEX_HOME = Path.home() / "lyra" / "index"
COLLECTION_NAME = "lyra-wiki"

# qmd search output: "qmd://col/rel_path:line #hash"
_HIT_LINE_RE = re.compile(r"^qmd://\S+")


@dataclass
class QmdIndexConfig:
    vault_path: Path
    index_path: Path = DEFAULT_INDEX_HOME / "karpathy_wiki"  # kept for API compat
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    token_budget: int = 2000
    collection_name: str = COLLECTION_NAME


def build(config: QmdIndexConfig, *, embed: bool = True) -> None:
    """Register the wiki as a qmd collection and rebuild the indexes.

    Idempotent: if the collection already exists it is updated in place.
    Pass ``embed=False`` to skip vector embedding (faster, BM25-only).
    """
    wiki_path = config.vault_path / "wiki"
    if not wiki_path.exists():
        raise FileNotFoundError(f"wiki/ directory not found: {wiki_path}")

    _ensure_collection(config.collection_name, wiki_path)
    _run_qmd(["qmd", "update"], check=True)
    if embed:
        _run_qmd(["qmd", "embed"], check=False)  # non-fatal if embeddings unavailable


def _ensure_collection(name: str, wiki_path: Path) -> None:
    existing = _list_collections()
    if name not in existing:
        _run_qmd(["qmd", "collection", "add", name, str(wiki_path)], check=True)


def _list_collections() -> set[str]:
    result = _run_qmd(["qmd", "collection", "list"], check=False)
    names: set[str] = set()
    for line in (result.stdout or "").splitlines():
        # Line format: "  <name> (qmd://<name>/)" or "<name> (qmd://<name>/)"
        m = re.match(r"^\s*(\S+)\s+\(qmd://", line)
        if m:
            names.add(m.group(1))
    return names


def search(
    config: QmdIndexConfig,
    query: str,
    k: int = 10,
    filters: dict[str, str] | None = None,
) -> list[dict]:
    """BM25/FTS5 search via qmd. Returns normalised hit dicts.

    Shape: ``{id, source, title, snippet, score, file_path, last_seen}``.
    ``id`` and ``last_seen`` are resolved from frontmatter after hit collection.
    """
    result = _run_qmd(
        ["qmd", "search", query, "-n", str(k * 2), "-c", config.collection_name],
        check=False,
    )
    hits = _parse_hits(result.stdout or "", config)
    return hits[:k]


def incremental(config: QmdIndexConfig, since: float | None = None) -> None:
    """Re-index updated files. qmd update handles mtimes internally."""
    _run_qmd(["qmd", "update"], check=True)


def health(config: QmdIndexConfig) -> dict[str, object]:
    """Liveness check: verify collection exists and has indexed files."""
    result = _run_qmd(["qmd", "collection", "list"], check=False)
    output = result.stdout or ""
    collection_found = config.collection_name in output
    file_count = 0
    for line in output.splitlines():
        if config.collection_name in line:
            m = re.search(r"Files:\s*(\d+)", line)
            if m:
                file_count = int(m.group(1))
    return {
        "index_exists": collection_found,
        "vault_exists": (config.vault_path / "wiki").exists(),
        "collection_name": config.collection_name,
        "file_count": file_count,
    }


def _parse_hits(text: str, config: QmdIndexConfig) -> list[dict]:
    from lyra import markdown as md

    wiki_root = config.vault_path / "wiki"
    hits: list[dict] = []

    title_re = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)
    score_re = re.compile(r"^Score:\s*([\d.]+)%", re.MULTILINE)
    snippet_re = re.compile(r"^@@[^\n]*\n(.*?)(?=\nqmd://|\Z)", re.DOTALL | re.MULTILINE)
    hit_re = re.compile(
        r"^qmd://(?P<col>[^/]+)/(?P<rel>[^\s:]+):(?P<line>\d+)\s+#\w+",
        re.MULTILINE,
    )

    blocks = re.split(r"\n(?=qmd://)", text.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = hit_re.match(block)
        if not m:
            continue
        rel_path = m.group("rel")
        m_title = title_re.search(block)
        m_score = score_re.search(block)
        m_snip = snippet_re.search(block)

        title = m_title.group(1).strip() if m_title else rel_path
        score = float(m_score.group(1)) / 100.0 if m_score else 0.0
        snippet = m_snip.group(1).strip() if m_snip else ""

        abs_path = wiki_root / rel_path
        page_id, last_seen = "", ""
        if abs_path.exists():
            try:
                doc = md.read(abs_path)
                page_id = str(doc.frontmatter.get("id") or "")
                last_seen = str(doc.frontmatter.get("last_confirmed") or "")
                if not title or title == rel_path:
                    title = str(doc.frontmatter.get("title") or title)
            except Exception:  # noqa: BLE001
                pass

        hits.append({
            "id": page_id,
            "source": config.collection_name,
            "title": title,
            "snippet": snippet,
            "score": score,
            "file_path": str(abs_path),
            "last_seen": last_seen,
            "citations": [rel_path],
        })
    return hits


def _run_qmd(cmd: list[str], *, check: bool) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=check,
        )
    except subprocess.CalledProcessError:
        raise
    except Exception as exc:
        if check:
            raise RuntimeError(f"qmd command failed: {cmd}") from exc
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(exc))
