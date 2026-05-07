"""ULID identity helpers for canonical pages and raw records."""

from __future__ import annotations

from ulid import ULID


def new_ulid() -> str:
    """Generate a fresh canonical ULID string."""
    return str(ULID())


def is_ulid(candidate: str) -> bool:
    """Return True if ``candidate`` is a syntactically valid ULID."""
    try:
        ULID.from_str(candidate)
    except (ValueError, TypeError):
        return False
    return True
