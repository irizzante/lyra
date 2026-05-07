"""M3.5 — LiteLLM provider for entity extraction (Mode B / standalone batch).

Wraps ``litellm.completion`` with a structured JSON prompt.  Falls back to the
heuristic extractor with a stderr warning when:
- ``litellm`` is not installed (optional dep)
- the configured provider is unreachable
- the response cannot be parsed as JSON

Install: ``pip install 'lyra-memory[extraction]'``
Config:  ``extraction.llm = {provider: openai, model: gpt-4o-mini, endpoint: ...}``
"""

from __future__ import annotations

import json
import sys

from lyra.extract.heuristic import ENTITY_TYPES, ExtractedEntity, extract as heuristic_extract

_PROMPT = """\
Extract entities from the following text.

Return ONLY a JSON object (no prose, no markdown) with this shape:
{{
  "entities": [
    {{"entity_type": "<type>", "name": "<canonical name>", "aliases": [], "attributes": {{}}}}
  ]
}}

Valid entity_type values: {entity_types}

Extract only entities clearly present in the text.

Text:
{text}""".strip()


def extract_with_llm(
    body: str,
    frontmatter: dict | None = None,
    *,
    provider: str = "",
    model: str = "",
    endpoint: str = "",
    extra: dict | None = None,
) -> list[ExtractedEntity]:
    """Call LiteLLM to extract entities; fall back to heuristic on any failure."""
    try:
        import litellm  # noqa: PLC0415
    except ImportError:
        _warn("litellm not installed; falling back to heuristic. Install: pip install 'lyra-memory[extraction]'")
        return heuristic_extract(body, frontmatter)

    model_id = _resolve_model(provider, model)
    prompt = _PROMPT.format(
        entity_types=", ".join(sorted(ENTITY_TYPES)),
        text=body[:6000] if len(body) > 6000 else body,
    )

    kwargs: dict = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
    }
    if endpoint:
        kwargs["api_base"] = endpoint
    if extra:
        kwargs.update({k: v for k, v in extra.items() if k not in kwargs})

    try:
        resp = litellm.completion(**kwargs)
        content = (resp.choices[0].message.content or "").strip()
        # strip optional markdown code fences
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        raw = json.loads(content)
        if not isinstance(raw, dict) or "entities" not in raw:
            raise ValueError(f"unexpected response shape: {list(raw.keys())}")
        return _parse_response(raw["entities"])
    except Exception as exc:  # noqa: BLE001
        _warn(f"LiteLLM extraction failed ({exc}); falling back to heuristic")
        return heuristic_extract(body, frontmatter)


def _resolve_model(provider: str, model: str) -> str:
    if model:
        if provider and "/" not in model:
            return f"{provider}/{model}"
        return model
    defaults = {
        "openai": "openai/gpt-4o-mini",
        "anthropic": "anthropic/claude-haiku-4-5-20251001",
        "ollama": "ollama/llama3",
        "github_copilot": "github_copilot/gpt-4o",
        "azure": "azure/gpt-4o",
        "bedrock": "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        "vertex_ai": "vertex_ai/gemini-1.5-flash",
        "groq": "groq/llama3-8b-8192",
    }
    if provider in defaults:
        return defaults[provider]
    return f"{provider}/gpt-4o-mini" if provider else "gpt-4o-mini"


def _parse_response(items: list) -> list[ExtractedEntity]:
    out: list[ExtractedEntity] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        et = str(item.get("entity_type") or item.get("type") or "").lower().strip()
        nm = str(item.get("name") or "").strip()
        if not et or not nm or et not in ENTITY_TYPES:
            continue
        aliases = [str(a) for a in (item.get("aliases") or []) if isinstance(a, str)]
        attrs = dict(item.get("attributes") or {})
        out.append(
            ExtractedEntity(
                entity_type=et,
                name=nm,
                aliases=aliases,
                attributes=attrs,
                confidence=0.9,
            )
        )
    return out


def _warn(msg: str) -> None:
    print(f"lyra warning: {msg}", file=sys.stderr)
