"""M1.12 — lyra file: query + file answer back to wiki/qa/.

Runs hybrid retrieval for a question, formats the answer with citations,
and writes a permanent Q&A record to ``wiki/qa/<ulid>-<slug>.md`` with
``type: qa`` frontmatter.  The filed page is queryable in future sessions.

Filed page frontmatter::

    id: <ULID>
    type: qa
    title: <question>
    sources: [<page_id>, ...]   # ULIDs of wiki pages used as evidence
    confidence: <avg hit score>
    created: <ISO 8601 date>
    last_confirmed: <ISO 8601 date>
    question: <verbatim question>
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lyra import markdown as md
from lyra.ids import new_ulid
from lyra.markdown import slug


@dataclass
class FileResult:
    qa_id: str
    qa_path: Path
    answer: str
    source_ids: list[str]


def file_answer(
    question: str,
    vault_path: Path,
    *,
    k: int = 5,
    use_vector: bool = True,
) -> FileResult:
    """Query the wiki and file the answer to wiki/qa/.

    Returns a FileResult with the path of the created Q&A page.
    """
    from lyra.query import hybrid_query, format_results

    hits = hybrid_query(question, vault_path, k=k, use_vector=use_vector)
    answer = format_results(hits, show_snippet=True)

    source_ids = [h.id for h in hits if h.id]
    confidence = sum(h.score for h in hits) / len(hits) if hits else 0.0

    qa_id = new_ulid()
    qa_slug = slug(question)
    qa_dir = vault_path / "wiki" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / f"{qa_id}-{qa_slug}.md"

    today = date.today().isoformat()
    frontmatter: dict = {
        "id": qa_id,
        "type": "qa",
        "title": question,
        "question": question,
        "sources": source_ids,
        "confidence": round(confidence, 4),
        "created": today,
        "last_confirmed": today,
    }

    body = f"# Q: {question}\n\n{answer}\n"
    md.write(qa_path, md.Document(frontmatter=frontmatter, body=body))

    return FileResult(
        qa_id=qa_id,
        qa_path=qa_path,
        answer=answer,
        source_ids=source_ids,
    )
