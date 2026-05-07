"""Tests for the typed-relation parser (M1.5)."""

from __future__ import annotations

from lyra.relations import RawRelation, parse_document, parse_frontmatter, parse_inline


def test_inline_supports_with_wikilink() -> None:
    body = "Some prose.\n\nsupports:: [[Decision X]]\n\nMore prose.\n"
    rels = parse_inline(body)
    assert rels == [
        RawRelation(type="supports", target_id=None, target_title="Decision X", origin="inline")
    ]


def test_inline_supersedes_with_ulid() -> None:
    body = "supersedes:: 01HXYZABCDEFGHJKMNPQRSTVW1\n"
    rels = parse_inline(body)
    assert len(rels) == 1
    assert rels[0].type == "supersedes"
    assert rels[0].target_id == "01HXYZABCDEFGHJKMNPQRSTVW1"
    assert rels[0].target_title is None


def test_inline_unknown_type_ignored() -> None:
    body = "fubar:: [[Page]]\nsupports:: [[Real]]\n"
    rels = parse_inline(body)
    assert [r.type for r in rels] == ["supports"]


def test_inline_in_list_item() -> None:
    body = "- supports:: [[Page A]]\n- contradicts:: [[Page B]]\n"
    rels = parse_inline(body)
    assert {(r.type, r.target_title) for r in rels} == {
        ("supports", "Page A"),
        ("contradicts", "Page B"),
    }


def test_frontmatter_with_target_id_and_confidence() -> None:
    items = [
        {"type": "supports", "target_id": "01HXYZABCDEFGHJKMNPQRSTVW1", "confidence": 0.9}
    ]
    rels = parse_frontmatter(items)
    assert rels == [
        RawRelation(
            type="supports",
            target_id="01HXYZABCDEFGHJKMNPQRSTVW1",
            target_title=None,
            confidence=0.9,
            origin="frontmatter",
        )
    ]


def test_frontmatter_with_wikilink_target() -> None:
    items = [{"type": "uses", "target": "[[React]]"}]
    rels = parse_frontmatter(items)
    assert rels == [
        RawRelation(
            type="uses",
            target_id=None,
            target_title="React",
            origin="frontmatter",
        )
    ]


def test_parse_document_dedupes() -> None:
    frontmatter = {"relations": [{"type": "supports", "target": "[[Page A]]"}]}
    body = "supports:: [[Page A]]\n"
    rels = parse_document(frontmatter, body)
    assert len(rels) == 1


def test_parse_document_merges_distinct() -> None:
    frontmatter = {"relations": [{"type": "supports", "target": "[[Page A]]"}]}
    body = "contradicts:: [[Page B]]\n"
    rels = parse_document(frontmatter, body)
    assert {(r.type, r.target_title) for r in rels} == {
        ("supports", "Page A"),
        ("contradicts", "Page B"),
    }
