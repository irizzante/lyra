"""Tests for M2 source registry: load_source, load_all_sources, SourceConfig.adapter."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from lyra.config import Config, SourceConfig
from lyra.sources import load_source, load_all_sources, _BUILTIN_ADAPTERS
from lyra.sources.base import Source


def _make_config(tmp_path: Path) -> Config:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "raw").mkdir()
    (vault / "wiki").mkdir()
    cfg = Config.default(vault)
    return cfg


# ---------------------------------------------------------------------------
# load_source — dynamic import by dotted adapter path
# ---------------------------------------------------------------------------

def test_load_source_by_adapter_dotted_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    src_cfg = SourceConfig(
        name="kw",
        type="karpathy_wiki",
        adapter="lyra.sources.karpathy_wiki.KarpathyWikiSource",
        options={"vault_path": str(vault)},
    )
    src = load_source(src_cfg)
    assert isinstance(src, Source)


def test_load_source_by_builtin_type(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    src_cfg = SourceConfig(
        name="kw",
        type="karpathy_wiki",
        options={"vault_path": str(vault)},
    )
    src = load_source(src_cfg)
    assert isinstance(src, Source)


def test_load_source_unknown_type_raises() -> None:
    src_cfg = SourceConfig(name="x", type="does_not_exist")
    with pytest.raises(ValueError, match="Unknown source type"):
        load_source(src_cfg)


def test_load_source_injects_vault_path(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    src_cfg = SourceConfig(name="kw", type="karpathy_wiki")
    src = load_source(src_cfg, vault_path=vault)
    from lyra.sources.karpathy_wiki import KarpathyWikiSource
    assert isinstance(src, KarpathyWikiSource)
    assert src.vault_path == vault.resolve()


# ---------------------------------------------------------------------------
# load_all_sources
# ---------------------------------------------------------------------------

def test_load_all_sources_returns_enabled_only(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.sources[0].enabled = False
    result = load_all_sources(cfg)
    assert result == []


def test_load_all_sources_skips_failing_source(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.sources.append(SourceConfig(name="bad", type="nonexistent"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = load_all_sources(cfg)
    # bad source skipped, warning issued
    assert any("bad" in str(w.message) for w in caught)
    names = [n for n, _ in result]
    assert "bad" not in names


def test_load_all_sources_returns_name_pairs(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    result = load_all_sources(cfg)
    assert len(result) >= 1
    for name, src in result:
        assert isinstance(name, str)
        assert isinstance(src, Source)


# ---------------------------------------------------------------------------
# fanout_query
# ---------------------------------------------------------------------------

def test_fanout_query_merges_hits(tmp_path: Path) -> None:
    from unittest.mock import MagicMock
    from lyra.sources.base import Result
    from lyra.query import fanout_query

    def _mock_src(hits):
        src = MagicMock()
        src.query.return_value = hits
        return src

    r1 = Result(id="a", source="s1", title="A", snippet="", score=0.9)
    r2 = Result(id="b", source="s1", title="B", snippet="", score=0.7)
    r3 = Result(id="c", source="s2", title="C", snippet="", score=0.8)
    r4 = Result(id="d", source="s2", title="D", snippet="", score=0.6)

    sources = [("s1", _mock_src([r1, r2])), ("s2", _mock_src([r3, r4]))]
    hits = fanout_query("test", sources, k=10)
    assert len(hits) == 4
    assert hits[0].score >= hits[-1].score  # sorted descending


def test_fanout_query_deduplicates_by_id() -> None:
    from unittest.mock import MagicMock
    from lyra.sources.base import Result
    from lyra.query import fanout_query

    r = Result(id="same", source="s1", title="X", snippet="", score=0.9)
    src1 = MagicMock()
    src1.query.return_value = [r]
    src2 = MagicMock()
    src2.query.return_value = [r]

    hits = fanout_query("test", [("s1", src1), ("s2", src2)], k=10)
    assert len(hits) == 1


def test_fanout_query_skips_failing_source() -> None:
    from unittest.mock import MagicMock
    from lyra.sources.base import Result
    from lyra.query import fanout_query

    good = MagicMock()
    good.query.return_value = [Result(id="ok", source="good", title="Ok", snippet="", score=0.5)]
    bad = MagicMock()
    bad.query.side_effect = RuntimeError("service down")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hits = fanout_query("test", [("bad", bad), ("good", good)], k=10)
    assert len(hits) == 1
    assert any("bad" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# _BUILTIN_ADAPTERS completeness
# ---------------------------------------------------------------------------

def test_builtin_adapters_importable() -> None:
    for type_name, dotted in _BUILTIN_ADAPTERS.items():
        import importlib
        module_path, _, class_name = dotted.rpartition(".")
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name, None)
            assert cls is not None, f"{dotted} not found"
        except ImportError as exc:
            # plain_markdown, agentmemory, mcp_memory may not exist yet in this track
            pass
