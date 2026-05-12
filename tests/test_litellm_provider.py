"""Tests for M3.5 — LiteLLM provider for entity extraction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from lyra.extract.llm import _parse_response, _resolve_model, extract_with_llm


# ---------------------------------------------------------------------------
# _resolve_model
# ---------------------------------------------------------------------------

def test_resolve_model_with_explicit_model_no_prefix() -> None:
    assert _resolve_model("openai", "gpt-4o") == "openai/gpt-4o"


def test_resolve_model_with_explicit_model_already_prefixed() -> None:
    assert _resolve_model("openai", "openai/gpt-4o") == "openai/gpt-4o"


def test_resolve_model_provider_only_returns_default() -> None:
    result = _resolve_model("openai", "")
    assert result.startswith("openai/")


def test_resolve_model_anthropic_default() -> None:
    result = _resolve_model("anthropic", "")
    assert "anthropic" in result


def test_resolve_model_empty_provider_empty_model() -> None:
    result = _resolve_model("", "")
    assert result  # some default


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

def test_parse_response_valid() -> None:
    items = [
        {"entity_type": "library", "name": "litellm", "aliases": [], "attributes": {}},
        {"entity_type": "project", "name": "lyra", "aliases": ["lyra-memory"], "attributes": {"version": "0.1"}},
    ]
    result = _parse_response(items)
    assert len(result) == 2
    names = {e.name for e in result}
    assert "litellm" in names
    assert "lyra" in names


def test_parse_response_unknown_entity_type_skipped() -> None:
    items = [{"entity_type": "alien", "name": "foo"}]
    result = _parse_response(items)
    assert result == []


def test_parse_response_missing_name_skipped() -> None:
    items = [{"entity_type": "library", "name": ""}]
    result = _parse_response(items)
    assert result == []


def test_parse_response_non_dict_items_skipped() -> None:
    result = _parse_response(["not-a-dict", 42])
    assert result == []


def test_parse_response_confidence_is_high() -> None:
    items = [{"entity_type": "concept", "name": "BM25"}]
    result = _parse_response(items)
    assert result[0].confidence >= 0.85


# ---------------------------------------------------------------------------
# extract_with_llm — litellm not installed → fallback to heuristic
# ---------------------------------------------------------------------------

def test_extract_with_llm_falls_back_when_litellm_missing() -> None:
    body = "entity::library requests\n"
    with patch.dict("sys.modules", {"litellm": None}):
        result = extract_with_llm(body, provider="openai", model="gpt-4o-mini")
    # Falls back to heuristic; should still find 'requests'
    assert isinstance(result, list)
    assert any(e.name == "requests" for e in result)


# ---------------------------------------------------------------------------
# extract_with_llm — successful LiteLLM response
# ---------------------------------------------------------------------------

def _make_mock_response(entities_json: list) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = json.dumps({"entities": entities_json})
    return resp


def test_extract_with_llm_parses_valid_response() -> None:
    entities_payload = [
        {"entity_type": "library", "name": "httpx", "aliases": [], "attributes": {}},
    ]
    mock_litellm = MagicMock()
    mock_litellm.completion.return_value = _make_mock_response(entities_payload)

    with patch.dict("sys.modules", {"litellm": mock_litellm}):
        result = extract_with_llm("some body", provider="openai", model="gpt-4o-mini")

    assert any(e.name == "httpx" for e in result)


def test_extract_with_llm_falls_back_on_json_error() -> None:
    mock_litellm = MagicMock()
    bad_resp = MagicMock()
    bad_resp.choices[0].message.content = "not json at all"
    mock_litellm.completion.return_value = bad_resp

    with patch.dict("sys.modules", {"litellm": mock_litellm}):
        # Should not raise; falls back to heuristic
        result = extract_with_llm("entity::concept BM25\n", provider="openai")

    assert isinstance(result, list)


def test_extract_with_llm_falls_back_on_network_error() -> None:
    mock_litellm = MagicMock()
    mock_litellm.completion.side_effect = ConnectionError("unreachable")

    with patch.dict("sys.modules", {"litellm": mock_litellm}):
        result = extract_with_llm("entity::library pyyaml\n", provider="openai")

    assert isinstance(result, list)
    # Heuristic fallback should still extract the inline annotation
    assert any(e.name == "pyyaml" for e in result)


def test_extract_with_llm_strips_markdown_code_fence() -> None:
    entities_payload = [{"entity_type": "library", "name": "requests"}]
    mock_litellm = MagicMock()
    fenced = f"```json\n{json.dumps({'entities': entities_payload})}\n```"
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = fenced
    mock_litellm.completion.return_value = mock_resp

    with patch.dict("sys.modules", {"litellm": mock_litellm}):
        result = extract_with_llm("some body", provider="anthropic")

    assert any(e.name == "requests" for e in result)


# ---------------------------------------------------------------------------
# config integration: ExtractionConfig
# ---------------------------------------------------------------------------

def test_extraction_config_defaults_empty() -> None:
    from lyra.config import ExtractionConfig
    cfg = ExtractionConfig()
    assert cfg.provider == ""
    assert cfg.model == ""
    assert cfg.endpoint == ""
    assert cfg.extra == {}


def test_extraction_config_from_dict() -> None:
    from lyra.config import ExtractionConfig
    cfg = ExtractionConfig.from_dict({"provider": "anthropic", "model": "claude-haiku-4-5-20251001"})
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-haiku-4-5-20251001"


def test_extraction_config_to_dict_omits_empty_fields() -> None:
    from lyra.config import ExtractionConfig
    cfg = ExtractionConfig()
    assert cfg.to_dict() == {}


def test_extraction_config_to_dict_includes_set_fields() -> None:
    from lyra.config import ExtractionConfig
    cfg = ExtractionConfig(provider="openai", model="gpt-4o")
    d = cfg.to_dict()
    assert d["provider"] == "openai"
    assert d["model"] == "gpt-4o"


def test_config_round_trips_extraction_section() -> None:
    from lyra.config import Config, ExtractionConfig
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        vault = Path(td) / "vault"
        vault.mkdir()
        cfg = Config.default(vault)
        cfg.extraction = ExtractionConfig(provider="ollama", model="llama3")
        data = cfg.to_dict()

        # Verify extraction section present
        assert "extraction" in data
        assert data["extraction"]["llm"]["provider"] == "ollama"

        # Round-trip: from_dict must restore extraction
        cfg2 = Config.from_dict(data)
        assert cfg2.extraction.provider == "ollama"
        assert cfg2.extraction.model == "llama3"
