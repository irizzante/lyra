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
