# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-06

### Added

- `lyra init` — bootstrap vault layout (ADR-6: flat `raw/`, `wiki/` tier dirs, `raw/assets/` only subdir)
- `lyra ingest` — ingest local files or URLs into flat `raw/` as kind=research|clip
- `lyra compile` — promote kind=research|clip raw records to `wiki/sources/`
- `lyra index` — build/refresh BM25/FTS5 + vector index via qmd 2.1.0
- `lyra query` — hybrid BM25/vector/graph search with citations
- `lyra brief` — emit token-budgeted SessionStart preamble (≤4KB, ADR-5 tiered items)
- `lyra session` — export OpenCode sessions from SQLite DB to flat `raw/` as kind=session
- `lyra file` — Q&A filing: query wiki and persist answer to `wiki/qa/`
- `lyra lint` — structural health checks (orphans, broken supersessions, contradictions)
- `lyra install` — copy hook and skill into Claude Code user/project scope
- `lyra status` — report config, vault, and source health
- ObsidianTasksSource — read-only source over `Tasks/*.md`
- AGENTS.md schema template with entity types, relation taxonomy, ADR-8 supersession protocol
- SKILL.md with progressive discovery and install instructions
- `session-start.mjs` Claude Code hook for automatic brief injection

### Architecture

- ADR-1: No MCP server (CLI + hook + skill pattern)
- ADR-3: Single SKILL.md with progressive discovery
- ADR-5: Brief default-ON, ≤4KB, tiered items (top-3 full summaries, tail titles only)
- ADR-6: `raw/` is flat — all records at `raw/<ulid>-<slug>.md`; `kind:` discriminates
- ADR-7: 4-tier consolidation: working → episodic → semantic → procedural
- ADR-8: Explicit supersession primary (`supersedes`/`superseded_by`/`contradicts`)
