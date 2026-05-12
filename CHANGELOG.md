# Changelog

All notable changes to Lyra are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-12

Initial release. Closes milestones **M1**, **M2**, **M3**. 315 tests passing.

### Added — M1 (orchestrator spine + Karpathy Wiki V2 source)

- `lyra init <vault>` — bootstrap runtime config at `~/lyra/config.yaml` and vault
  layout (`raw/`, `wiki/` with sources/concepts/connections/synthesis/sessions/qa).
- `lyra ingest` — capture raw research and clip records into `raw/<ulid>-<slug>.md`
  with `kind:` frontmatter.
- `lyra session` — export OpenCode SQLite sessions into `raw/` (filesystem-based,
  post-hoc reader).
- `lyra compile` — promote `raw/` → `wiki/sources/` with ULID, supersession,
  typed relations, idempotent rebuild.
- Typed relation parser — `supports::`, `contradicts::`, `uses::`, `supersedes::`,
  `depends_on::`, `caused::`, `fixed::` (inline + frontmatter).
- Hybrid index — BM25/FTS5 (via qmd) + vector + SQLite graph projection of
  typed relations, all rebuildable from the vault.
- `lyra query <q>` — hybrid retrieval with citations and per-claim confidence.
- `lyra brief` — token-budgeted SessionStart preamble (default-ON, ≤4 KB).
- `lyra status` — vault and index health snapshot.
- `lyra lint` — structural checks (orphans, broken supersessions, dangling
  relations, missing frontmatter, contradictions).
- `lyra file <q>` — Q&A filing workflow creating `wiki/qa/<ulid>-<slug>.md`.
- `lyra install --hook --skill` — copies SessionStart/SessionEnd hooks and the
  Lyra skill into `~/.claude/` (user scope) or `./.claude/` (project scope) and
  wires `settings.json`.
- `ObsidianTasksSource` plugin — second built-in source over `<vault>/Tasks/*.md`.

### Added — M2 (pluggable external sources, read-only)

- Source registry with dynamic adapter loading via dotted class path.
- `lyra source list/add/remove/refresh` CLI subcommands.
- Cross-source query fan-out integrated into `lyra query` and `lyra brief`.
- Per-source health surfaced in `lyra status`.
- Adapters: `PlainMarkdownSource`, `AgentmemorySource`, `McpMemorySource`.

### Added — M3 (entity extraction + multi-hop graph + auto-supersession)

- Entity model — people, projects, libraries, concepts, files, decisions as
  first-class wiki pages.
- Heuristic entity extractor (deterministic baseline, no LLM required).
- Compile pipeline integration with an extraction provider abstraction;
  agent-host LLM (Mode A) preferred, LiteLLM standalone (Mode B) as fallback
  for cron/CI/manual use (ADR-9).
- `lyra compile --raw-id <id> --entities '<json>'` — imperative single-page
  mode bypassing any LLM call.
- LiteLLM provider for batch compile.
- Multi-hop graph traversal — BFS via SQLite recursive CTE, default
  `max_hops=2`, excludes `contradicts` and `superseded_by` edges from
  expansion (ADR-10).
- `lyra query` multi-hop integration with Reciprocal Rank Fusion (RRF, k=60)
  combining BM25 + vector + graph streams.
- Auto-supersession via weighted score on contradiction
  (`score = w_r·recency + w_a·authority + w_s·support`, defaults 0.5/0.3/0.2,
  threshold τ=0.2; ADR-11). Configurable in `~/lyra/config.yaml`.
- `lyra lint` CONTRADICTION issues now carry score breakdown per page so the
  operator can see why compile left a contradiction unresolved.
- SessionEnd hook — runs `lyra compile` at session end; brief shows
  `📋 N raw pages pending promotion` when relevant.
- Skill update — in-session entity extraction workflow with prompt template
  and entity JSON schema documented in `SKILL.md`.

### Architecture Decision Records

ADR-1..11 published under `.walden/specs/opencode-karpathy-wiki/design.md`:

- ADR-1: No MCP server (CLI + hook + skill pattern)
- ADR-3: Single SKILL.md with progressive discovery
- ADR-5: Brief default-ON, ≤4 KB, tiered items
- ADR-6: `raw/` flat; `wiki/` organized by tier
- ADR-7: 4-tier consolidation (working → episodic → semantic → procedural)
- ADR-8: Explicit supersession primary; retention decay deferred to M4
- ADR-9: Agent-host LLM preferred for entity extraction; LiteLLM fallback
- ADR-10: BFS depth=2 default, RRF fusion (k=60) of BM25 + vector + graph
- ADR-11: Auto-supersession via weighted score; threshold-gated; both pages preserved

[Unreleased]: https://github.com/irizzante/lyra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/irizzante/lyra/releases/tag/v0.1.0
