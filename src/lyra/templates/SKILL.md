---
description: Lyra — local-first memory orchestrator. Use when the user wants to ingest knowledge into the wiki, query it, check recent work, manage supersession/contradictions, or view the session brief. Also use when the user asks about vault layout, AGENTS.md, or lyra CLI commands.
---

# Lyra Memory Orchestrator

Lyra manages a local Obsidian vault as a structured, typed knowledge store aligned with the Karpathy LLM Wiki v2 four-tier consolidation model (working → episodic → semantic → procedural).

## Core commands

```bash
lyra brief                         # token-budgeted session preamble — run first
lyra query "<question>"            # hybrid search (BM25 + vector + graph) with citations
lyra ingest <path|url> [--as research|clip|session] [--title "…"]
lyra compile                       # promote raw/ → wiki/
lyra status                        # vault + index health
lyra lint                          # orphans, broken supersessions, contradictions
lyra file "<question>"             # query + file answer to wiki/qa/
lyra install [--hook] [--skill] [--scope user|project] [--no-inject]
```

## Memory tiers (path = tier)

| Tier | Path | What lives here |
|------|------|-----------------|
| Working | `raw/<ulid>-<slug>.md` | Raw ingest: research, clips, sessions |
| Episodic | `wiki/sessions/` | Compressed session summaries |
| Semantic | `wiki/sources/`, `wiki/concepts/`, `wiki/connections/`, `wiki/synthesis/` | Promoted, cross-source knowledge |
| Procedural | `wiki/procedures/` | Workflows (M2+) |
| Q&A | `wiki/qa/` | Filed answers from `lyra file` |

`raw/` is flat. Only `raw/assets/` is a sub-directory (binaries).

## Ingest rules

```bash
lyra ingest paper.pdf --as research --title "Attention Is All You Need"
lyra ingest https://example.com/doc --as clip
lyra ingest session-dump.md --as session
```

`kind:` frontmatter discriminates type, not the file path.

## Relation annotations (inline in raw body)

```markdown
supports:: [[Page Title]]
contradicts:: [[Page Title]]
uses:: [[Page Title]]
supersedes:: [[Page Title]]
depends_on:: [[Page Title]]
```

Relations are resolved to ULIDs at `lyra compile` time.

## Supersession and contradiction (ADR-8)

Old ≠ stale. Staleness requires **explicit supersession**:

```yaml
# new page
supersedes: [<old-ulid>]

# old page (set by lint or manual)
superseded_by: <new-ulid>
```

Conflicting pages without resolution → `contradicts: [<other-ulid>]`. Run `lyra lint` to surface them.

## Raw promotion workflow

When the brief shows `📋 N raw pages pending promotion`, after a successful `lyra ingest`, or on user request, promote pending raw pages using in-session entity extraction:

1. Run `lyra brief` to confirm which raw pages are pending (or check the brief already shown at session start).
2. For each pending raw page (found in `raw/` with a `raw_id` not yet in any `wiki/**/*.md` `sources:` list):
   a. Read the raw page content.
   b. Extract entities using the prompt template below.
   c. Call `lyra compile --raw-id <raw_id> --entities '<json>'`.

This skips the LiteLLM call and applies entities deterministically (ADR-9 imperative mode).

### Entity extraction prompt template

Use this prompt verbatim, substituting `{content}` and `{kind}`:

```
Extract entities from the following {kind} note.

Return a JSON array of entity objects. Each object must have:
- "entity_type": one of "person", "project", "library", "concept", "file", "decision"
- "name": canonical name (string, required)
- "aliases": list of alternative names/abbreviations (optional)
- "attributes": object with any extra key-value metadata (optional)

Only include entities clearly mentioned or implied in the text.
Return an empty array [] if no entities are found.
Return only the JSON array, no explanation.

--- NOTE ({kind}) ---
{content}
--- END ---
```

Where:
- `{kind}` is the raw page `kind` frontmatter value: `research`, `clip`, or `session`
- `{content}` is the full body text of the raw page

### Entity JSON schema

The JSON passed to `--entities` must be a list of objects. Each object:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `entity_type` | string | yes | One of: `concept`, `decision`, `file`, `library`, `person`, `project` |
| `name` | string | yes | Canonical name, non-empty |
| `aliases` | list of strings | no | Alternative names or abbreviations |
| `attributes` | object | no | Free-form key-value metadata |

Example:

```json
[
  {
    "entity_type": "person",
    "name": "Andrej Karpathy",
    "aliases": ["karpathy"],
    "attributes": {"role": "researcher", "org": "OpenAI"}
  },
  {
    "entity_type": "library",
    "name": "PyTorch",
    "aliases": ["torch"],
    "attributes": {}
  },
  {
    "entity_type": "concept",
    "name": "attention mechanism"
  }
]
```

Relations between pages are expressed as inline annotations in the raw body (see Relation annotations above), not in the entity JSON.

## Install Lyra hooks + skill into Claude Code

```bash
lyra install --hook --skill           # user-scope (~/.claude/)
lyra install --hook --scope project   # project-scope (.claude/)
lyra install --skill --no-inject      # copy skill only, skip settings patch
```

`--hook` wires the `SessionStart` hook so `lyra brief` is prepended automatically.
`--skill` deploys this `SKILL.md` to the target `.claude/skills/lyra/` directory.

## Configuration

Vault path and sources live in `~/lyra/config.yaml`. Initialise with:

```bash
lyra init <vault-path>
```
