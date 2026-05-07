# Project Constitution

This file captures stable project-wide context that applies across all features. It is optional and does not participate in the approval workflow.

## Project Summary

`Lyra` is a local-first, vendor-agnostic memory orchestrator for AI coding work. It operates over one or more memory **sources** through a uniform plugin contract; the bundled `Karpathy Wiki V2` is the canonical default source and the only source required for V1. External sources (agentmemory, mcp-memory-service, plain markdown trees, MCP memory servers) plug in as additional read-paths in later milestones. **Sinks** — the inverse contract that lets Lyra write back into external sources — are deferred to M5. V1 captures session context, compiles raw inputs into markdown with typed relations and confidence/supersession metadata, and serves hybrid retrieval (BM25/FTS5 + vector + graph) through a small public CLI that hides qmd and the graph projection. Inspired by Karpathy's LLM Wiki, Rohit's LLM Wiki v2, and agentmemory's runtime patterns, scoped around a markdown-first canonical model.

## Tech Stack

- Python 3.11+ (Lyra core: CLI, sources, indexer, compile, query, lint)
- TypeScript / JavaScript (Claude Code SessionStart hook; OpenCode session reader is implemented in Python via SQLite)
- Markdown + YAML frontmatter for canonical wiki storage
- qmd for local BM25/FTS5 + vector retrieval (with embedding + reranker)
- SQLite for the graph projection of typed relations
- ULID for durable page identity
- uv for Python dependency management

## Conventions

- Feature specs live under `.walden/specs/`
- Canonical knowledge for the bundled Karpathy Wiki V2 source is an external Obsidian vault chosen at `lyra init` time
- Raw inputs live under `<vault>/raw/{sessions,research,clips,assets}`
- Compiled wiki content lives under `<vault>/wiki/{concepts,connections,sources,procedures,synthesis,qa,meta}`
- Startup navigation files live at `<vault>/wiki/{AGENTS.md,index.md,log.md}`
- Runtime config lives at `~/lyra/config.yaml` and stores the absolute vault path plus enabled sources
- Lyra Python package lives under `src/lyra/` (src layout); CLI entry point is the binary `lyra`
- Source adapters live under `src/lyra/sources/<name>.py`; the canonical built-in is `karpathy_wiki.py`
- Index and graph projection code lives under `src/lyra/index/`
- Hook adapters live under `hooks/<agent>/`; only `claude-code` ships in V1
- Page identity is a ULID stored in frontmatter `id:`; filenames are slug-derived for human readability; cross-page typed relations resolve by ULID, prose wikilinks resolve by filename
- All dates in ISO-8601 (`YYYY-MM-DD`)
- All file names in kebab-case
- Distribution is a plain GitHub repo with `lyra init`; no persistent runtime skill

## Sanity Checks

```bash
uv run lyra status
uv run lyra lint --structural-only
uv run pytest -q
```

## Key Files

- `src/lyra/cli.py` — Lyra CLI entry point (init, ingest, compile, query, brief, status, lint, source)
- `src/lyra/config.py` — runtime config schema and load/save for `~/lyra/config.yaml`
- `src/lyra/vault.py` — vault layout creation and discovery
- `src/lyra/sources/base.py` — Source plugin contract
- `src/lyra/sources/karpathy_wiki.py` — built-in canonical source
- `src/lyra/sources/opencode_session.py` — OpenCode session reader (filesystem-based, reads `~/.local/share/opencode/opencode.db`)
- `src/lyra/index/qmd_index.py` — BM25/FTS5 + vector index via qmd
- `src/lyra/index/graph_projection.py` — SQLite typed-relation graph projection
- `src/lyra/templates/AGENTS.md` — canonical runtime instructions deployed by `lyra init`
- `hooks/claude-code/session-start.ts` — Claude Code SessionStart hook for live brief injection
- `pyproject.toml` — Python package metadata, dependencies, CLI entry point
- `README.md` — human-facing quick start and setup instructions

## Hard Rules

- Source adapters must be read-only in V1; sinks (write-back) are deferred to M5
- Hooks must be vendor-agnostic in shape; each agent gets its own adapter implementing the same brief-injection contract
- No proprietary LLM API keys required for core functionality
- All canonical wiki content is plain markdown; binary assets live under `raw/assets/` and are referenced from markdown
- qmd must be pre-configured with the local embedding model and reranker selected for the install
- Runtime must discover the vault through `~/lyra/config.yaml`, not by assuming the current working directory is the vault
- Lyra CLI is the public interface; direct qmd invocation, graph SQL queries, and source-specific APIs are internal implementation details
- V1 must not require agentmemory, iii-engine, or an always-on memory server
- Page identity (ULID `id:`) is durable and never reused; filenames may change but ULIDs do not
- The user must retain full control over what gets written to the canonical vault
