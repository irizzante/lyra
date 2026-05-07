"""M1.2 — raw ingest (ADR-6: flat raw/).

Writes canonical raw records flat under ``raw/<ulid>-<slug>.md``.  ``kind:``
frontmatter (research|clip|session) discriminates type; there are no
organisational subdirectories.  Binary media goes under ``raw/assets/`` (the
only technical subdir) and is referenced from a markdown wrapper.

A raw record carries provenance frontmatter:

```yaml
raw_id: <ULID>
kind: research | clip
source: <local path or URL>
ingested_at: <ISO 8601>
content_type: <mime>
title: <derived>
asset: <relative path under raw/assets/>   # only when wrapping a binary asset
```

URL fetch is HTTP/HTTPS via stdlib ``urllib`` to avoid an extra dep. Binary
content types route to assets; text/markdown becomes the body of the wrapper.
"""

from __future__ import annotations

import mimetypes
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from lyra.ids import new_ulid
from lyra.markdown import Document, slug, write

TEXT_PREFIXES = ("text/",)
TEXT_TYPES = {
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
}


@dataclass
class IngestResult:
    raw_id: str
    record_path: Path
    asset_path: Path | None
    kind: str


def ingest(
    target: str,
    *,
    vault_path: Path,
    kind: str = "research",
    title: str | None = None,
) -> IngestResult:
    if kind not in {"research", "clip"}:
        raise ValueError(f"unsupported kind: {kind!r}; expected 'research' or 'clip'")

    if _looks_like_url(target):
        payload, content_type, derived_title = _fetch_url(target)
        source_label = target
    else:
        path = Path(target).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"ingest source not found: {path}")
        payload = path.read_bytes()
        content_type = (
            mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        derived_title = path.stem
        source_label = str(path)

    final_title = title or derived_title or "untitled"
    raw_id = new_ulid()
    stem = f"{raw_id}-{slug(final_title)}"
    is_text = _is_text_content(content_type)

    raw_root = vault_path / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    asset_path: Path | None = None
    body: str
    if is_text:
        body = payload.decode("utf-8", errors="replace")
    else:
        asset_dir = raw_root / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        ext = mimetypes.guess_extension(content_type) or ""
        asset_path = asset_dir / f"{stem}{ext}"
        asset_path.write_bytes(payload)
        body = (
            f"Binary asset stored at `{asset_path.relative_to(vault_path)}`.\n"
            f"\nContent type: `{content_type}`.\n"
        )

    frontmatter: dict = {
        "raw_id": raw_id,
        "kind": kind,
        "source": source_label,
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content_type": content_type,
        "title": final_title,
    }
    if asset_path is not None:
        frontmatter["asset"] = str(asset_path.relative_to(vault_path))

    record_path = raw_root / f"{stem}.md"
    write(record_path, Document(frontmatter=frontmatter, body=body))

    return IngestResult(
        raw_id=raw_id,
        record_path=record_path,
        asset_path=asset_path,
        kind=kind,
    )


def _looks_like_url(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _fetch_url(url: str) -> tuple[bytes, str, str]:
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 — explicit user input
        payload = resp.read()
        content_type = resp.headers.get_content_type() or "application/octet-stream"
        title = _title_from_url(url)
    return payload, content_type, title


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    last = (parsed.path.rstrip("/").rsplit("/", 1)[-1]) or parsed.netloc
    return last or "untitled"


def _is_text_content(content_type: str) -> bool:
    if content_type in TEXT_TYPES:
        return True
    return any(content_type.startswith(prefix) for prefix in TEXT_PREFIXES)
