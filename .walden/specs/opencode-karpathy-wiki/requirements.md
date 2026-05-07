---
status: in-review
approved_at: 
last_modified: 2026-05-06T16:30:00Z
---

# Requirements Document

## Introduction

`Lyra` is a local-first, vendor-agnostic memory orchestrator for AI coding work. It operates over one or more memory **sources** through a uniform plugin contract; the bundled `Karpathy Wiki V2` is the canonical default source and the only source required for V1. External sources (e.g. agentmemory, mcp-memory-service, plain markdown trees, MCP memory servers) plug in as additional read-paths in later milestones. **Sinks** — the inverse contract that would let Lyra write back into external sources — are out of scope for V1. V1 captures raw session and research artifacts under `raw/`, compiles curated knowledge under `wiki/` with typed relations and confidence/supersession metadata, and exposes a small public command surface that hides qmd, the graph projection, and other internal retrieval details. Inspired by Karpathy's LLM Wiki, Rohit's LLM Wiki v2, and agentmemory's runtime patterns, while keeping the canonical wiki source markdown-first.

<!-- assumed: Lyra is an orchestrator over plug-in memory sources; Karpathy Wiki V2 in the Obsidian vault is the canonical default source; sinks (write-back), additional sources, multi-hop graph traversal, lifecycle decay, entity extraction, and team-shared memory are deferred to later milestones -->

## Requirements

### R0 Memory Tiers (Karpathy Wiki V2 alignment)

**User Story:** As an AI agent user, I want a clear consolidation pipeline where raw observations are progressively compressed into more confident long-lived knowledge, so that the wiki reflects how things actually work over time, not just the latest captured noise.

#### Acceptance Criteria

1. `R0.AC1` The system SHALL implement four memory tiers — **working**, **episodic**, **semantic**, **procedural** — each more compressed, more confident, and longer-lived than the one below it (per LLM Wiki v2 "Consolidation tiers").
2. `R0.AC2` Working memory (recent observations, not yet processed) SHALL live in `raw/` as a **flat** directory; the only allowed sub-directory is `raw/assets/` for binary attachments referenced by markdown wrappers.
3. `R0.AC3` The kind of each raw record (research|clip|session) SHALL be discriminated by the `kind:` frontmatter field, not by directory path.
4. `R0.AC4` Episodic memory (session summaries compressed from raw observations) SHALL live in `wiki/sessions/`.
5. `R0.AC5` Semantic memory (cross-session facts) SHALL live in `wiki/{sources,concepts,connections,synthesis}/`, with progressive consolidation from single-source (`sources`) to convergent multi-source synthesis (`synthesis`).
6. `R0.AC6` Procedural memory (workflows and patterns extracted from repeated semantics) SHALL live in `wiki/procedures/`.
7. `R0.AC7` Filed-back Q&A pages (answers worth promoting from `lyra query` results) SHALL live in `wiki/qa/`.
8. `R0.AC8` Schema and operational meta-documents SHALL live in `wiki/meta/`; the canonical schema document SHALL be `wiki/AGENTS.md`.

### R1 Vault Layout And Ownership

**User Story:** As an AI agent user, I want the wiki stored in a dedicated Obsidian vault layout, so that raw inputs and compiled knowledge stay separated and inspectable.

#### Acceptance Criteria

1. `R1.AC1` The system SHALL organize knowledge inside a user-chosen Obsidian vault with separate `raw/` and `wiki/` roots.
2. `R1.AC2` WHEN the user initializes a wiki, the system SHALL create a flat `raw/` directory plus `raw/assets/` for binary wrappers (per `R0.AC2`).
3. `R1.AC3` WHEN the user initializes a wiki, the system SHALL create `wiki/{AGENTS.md,index.md,log.md,sessions,sources,concepts,connections,procedures,synthesis,qa,meta}`.
4. `R1.AC4` IF the target vault path is missing or not writable, THEN the system SHALL stop initialization with an actionable error.
5. `R1.AC5` The system SHALL treat files under `raw/` as immutable source inputs after ingest.
6. `R1.AC6` WHEN the target vault pre-exists with user-authored content, the system SHALL operate additively: it SHALL NOT overwrite or delete any file that Lyra did not itself create.
7. `R1.AC7` User-authored markdown pages without a Lyra `id` ULID frontmatter SHALL remain queryable through `lyra query` but SHALL be excluded from graph projection traversal.

### R2 Installer And Runtime Discovery

**User Story:** As an AI agent user, I want the runtime to discover the wiki through installed configuration, so that the vault can live outside the current repository.

#### Acceptance Criteria

1. `R2.AC1` WHEN the user runs the installer, the system SHALL capture the absolute vault path and wiki root used by the current installation.
2. `R2.AC2` WHEN the installer configures OpenCode, the system SHALL write runtime configuration that includes the absolute wiki path.
3. `R2.AC3` WHEN the installer configures OpenCode, the system SHALL write the public CLI entry points used by runtime actions.
4. `R2.AC4` IF the installer is re-run for an existing wiki, THEN the system SHALL refresh generated runtime configuration without overwriting user-authored wiki content.
5. `R2.AC5` WHEN runtime starts outside the vault directory, the system SHALL resolve the wiki through the installed absolute path instead of the current working directory.

### R2A Lyra Public Interface

**User Story:** As an AI agent user, I want Lyra to be the stable public interface over the wiki, so that the canonical vault and the internal retrieval engine can evolve without changing the agent contract.

#### Acceptance Criteria

1. `R2A.AC1` The system SHALL present `Lyra` as the public orchestration interface for reading and operating on the wiki.
2. `R2A.AC2` WHEN the runtime exposes commands to the agent, the system SHALL route them through a small Lyra command surface instead of exposing qmd internals directly.
3. `R2A.AC3` WHILE Lyra serves as the public interface, the system SHALL keep the Obsidian vault as the canonical knowledge store.

### R3 Raw Session Capture

**User Story:** As an AI agent user, I want session context captured before it disappears, so that the wiki can later compile accurate episodic memory.

#### Acceptance Criteria

1. `R3.AC1` WHEN a session ends, the system SHALL write a structured session artifact under flat `raw/` with `kind: session` frontmatter (per `R0.AC2`–`R0.AC3`).
2. `R3.AC2` WHEN a pre-compaction event fires, the system SHALL capture the active working context as a `kind: session` raw record before compaction continues.
3. `R3.AC3` IF a captured session payload exceeds the configured size limit, THEN the system SHALL summarize lower-priority sections before persisting the artifact.
4. `R3.AC4` WHILE session artifacts are being written, the system SHALL serialize concurrent writes that target the same record.

### R4 Session-Start Brief

**User Story:** As an AI agent, I want a compact startup brief, so that I can discover the wiki quickly without loading the entire corpus into context.

#### Acceptance Criteria

1. `R4.AC1` WHEN a session starts, the system SHALL inject a compact operational brief aligned with the token-minimizing SessionStart pattern used by agentmemory and LLM Wiki v2.
2. `R4.AC2` WHEN a session starts, the system SHALL advertise the public Lyra read interface instead of internal retrieval implementation details.
3. `R4.AC3` WHEN recent activity exists, the system SHALL include recent activity and open threads in the startup brief.
4. `R4.AC4` WHEN recent context is summarized for startup, the system SHALL prefer a small derived summary over the full wiki index.
5. `R4.AC5` WHILE Lyra retrieval is available, the system SHALL NOT inject the full compiled wiki corpus into session-start context.
6. `R4.AC6` Brief items SHALL be enumerated by identifier + summary (top-3 entries per section ≤ 400 chars, tail entries ≤ 120 chars), never by full body — agents resolve detail via `lyra query <id>` (brief is a map, not the territory).
7. `R4.AC7` SessionStart brief injection SHALL be ON by default to align with LLM Wiki v2 "load relevant context from the wiki based on recent activity"; opt-out via env `LYRA_INJECT_BRIEF=false` or installer flag `lyra install --hook --no-inject`.
8. `R4.AC8` The brief SHALL aggregate: active tasks (top 3 with last checkpoint summary + tail title-only), recent episodic sessions (top 3), top semantic pages (titles), recent compile log (last 5 entries), and Lyra usage hint — total ≤ 4 KB (NFR3).

### R5 Public CLI Contract

**User Story:** As an AI agent user, I want a stable public command surface, so that runtime adapters can rely on a small vendor-neutral contract.

#### Acceptance Criteria

1. `R5.AC1` The system SHALL expose a small public Lyra command surface for query, compile, lint, status, and recent-context workflows.
2. `R5.AC2` WHEN the Lyra query interface receives a question, the system SHALL answer from compiled wiki content with citations to supporting pages.
3. `R5.AC3` IF the derived retrieval index is missing or stale, THEN the Lyra query interface SHALL rebuild or refresh it before returning results.
4. `R5.AC4` WHILE public commands are running, the system SHALL keep qmd-specific configuration and retrieval commands behind the Lyra layer.

### R6 Compilation Pipeline

**User Story:** As an AI agent user, I want raw artifacts compiled into browsable wiki pages, so that knowledge compounds across sessions and sources.

#### Acceptance Criteria

1. `R6.AC1` WHEN `lyra compile` processes new raw artifacts, the system SHALL create or update compiled pages under `wiki/{sessions,sources,concepts,connections,procedures,synthesis,qa,meta}` dispatched by the raw record's `kind:` frontmatter (research|clip → `wiki/sources/`; session → `wiki/sessions/` for episodic compression).
2. `R6.AC2` WHEN a compiled page is updated, the system SHALL record links to the contributing raw artifacts or source pages.
3. `R6.AC3` WHEN compilation creates or updates related knowledge pages, the system SHALL preserve bidirectional Obsidian links between them.
4. `R6.AC4` IF new evidence conflicts with an existing compiled claim, THEN the system SHALL flag the conflict in the target wiki page (`contradicts:` frontmatter) or `wiki/log.md`.
5. `R6.AC5` WHEN compilation completes, the system SHALL regenerate `wiki/index.md`.
6. `R6.AC6` WHEN compilation completes, the system SHALL append a chronological entry to `wiki/log.md`.
7. `R6.AC7` Compilation SHALL touch only Lyra-owned paths: `wiki/sessions/`, `wiki/sources/`, `wiki/index.md`, `wiki/log.md`. User-authored content elsewhere in `wiki/` SHALL NOT be modified by compile.
8. `R6.AC8` Promotion of a `kind: session` raw into `wiki/sessions/` is a minimal V1 episodic compression (frontmatter + summary). Richer multi-session synthesis into `wiki/synthesis/` is M2+.

### R7 Raw Research And Clip Ingestion

**User Story:** As an AI agent user, I want non-session sources captured in the same pipeline, so that the wiki can combine research, clips, and session memory.

#### Acceptance Criteria

1. `R7.AC1` WHEN the user ingests a research note or clip, the system SHALL store the canonical raw record in flat `raw/` with `kind:` frontmatter set to `research` or `clip` (per `R0.AC2`–`R0.AC3`).
2. `R7.AC2` IF an ingest item includes binary media, THEN the system SHALL place the media under `raw/assets/` and link it from the canonical raw record.
3. `R7.AC3` WHEN a raw source is promoted into the wiki, the system SHALL create or update a corresponding page under `wiki/sources/` (research|clip) or `wiki/sessions/` (session).

### R8 OpenCode Hook Adapter

**User Story:** As an OpenCode user, I want a first-party hook adapter, so that vendor-specific events can drive the wiki without leaking into the knowledge schema.

#### Acceptance Criteria

1. `R8.AC1` The system SHALL provide an OpenCode hook adapter implemented in TypeScript or JavaScript.
2. `R8.AC2` WHEN the OpenCode adapter receives session-start, pre-compaction, or session-end events, the system SHALL map each event to the corresponding Lyra workflow.
3. `R8.AC3` WHILE the OpenCode adapter is translating vendor payloads, the system SHALL preserve a vendor-neutral `raw/` and `wiki/` schema.
4. `R8.AC4` IF an OpenCode hook payload is missing required fields, THEN the adapter SHALL emit a diagnosable error.

### R9 Wiki Health And Retrieval

**User Story:** As an AI agent user, I want local search and health checks over the compiled wiki, so that the wiki stays trustworthy and usable as it grows.

#### Acceptance Criteria

1. `R9.AC1` The system SHALL use qmd for BM25/FTS5 and vector retrieval over the compiled wiki, configured with the local embedding model and reranker selected for the installation.
2. `R9.AC2` WHEN `lyra lint` runs, the system SHALL report broken internal links, orphan pages, stale claims, broken supersession edges, dangling typed relations, and flagged conflicts.
3. `R9.AC3` WHEN `lyra lint` detects an orphan page, the system SHALL suggest at least one potential inbound link.
4. `R9.AC4` IF `lyra query` finds no relevant pages for a question, THEN the system SHALL report that the compiled wiki does not contain the requested answer.

### R10 Source Plugin Contract

**User Story:** As an AI agent user, I want Lyra to plug additional memory sources beyond the canonical Karpathy Wiki V2, so that knowledge stored in agentmemory, mcp-memory-service, or other adapters can be queried through the same Lyra interface.

#### Acceptance Criteria

1. `R10.AC1` The system SHALL define a uniform Source plugin contract exposing at least `query(q, k, filters)`, `list_recent(window)`, `health()`, and `capabilities()`.
2. `R10.AC2` WHEN a source returns a result, the system SHALL normalise it to `{id, source, title, snippet, score, citations, last_seen}`.
3. `R10.AC3` The system SHALL ship `Karpathy Wiki V2` as the built-in canonical source implementing the contract.
4. `R10.AC4` WHILE V1 is in scope, the system SHALL support read-only sources only.
5. `R10.AC5` WHILE V1 is in scope, the system SHALL NOT implement write-back sinks for any source.
6. `R10.AC6` IF a source declares itself unhealthy via `health()`, THEN Lyra SHALL exclude it from cross-source query fan-out and surface the failure in `lyra status`.

### R11 Hybrid Retrieval And Graph Projection

**User Story:** As an AI agent user, I want hybrid lexical, vector, and graph-based retrieval over the canonical wiki, so that queries surface relevant pages, supporting evidence, and related concepts.

#### Acceptance Criteria

1. `R11.AC1` The system SHALL build a BM25/FTS5 index, a vector index, and a SQLite-backed graph projection over the canonical wiki.
2. `R11.AC2` WHEN `lyra query` runs, the system SHALL combine BM25/FTS5, vector, and one-hop graph hits into a hybrid ranked result with citations.
3. `R11.AC3` The system SHALL build the graph projection from typed relations declared in page frontmatter (`relations:`) and from inline `supports::` / `contradicts::` / `uses::` / `supersedes::` annotations resolved at compile time.
4. `R11.AC4` The system SHALL store graph edges keyed by `target_id` ULID, not by filename, so that renames do not break the graph.
5. `R11.AC5` IF the index or graph projection is missing or stale, THEN Lyra SHALL rebuild it from the vault before serving results.
6. `R11.AC6` The system SHALL keep the index, vector store, and graph projection rebuildable from markdown-only canonical content.

### R12 Lyra Skill (single, progressive discovery)

**User Story:** As an AI agent user, I want a single Lyra skill installable into Claude Code and OpenCode, so that the agent can discover and call Lyra capabilities on demand without paying an always-on MCP context tax.

#### Acceptance Criteria

1. `R12.AC1` The system SHALL ship a single skill at `skills/lyra/SKILL.md` following the progressive-discovery pattern (concise frontmatter trigger description, body progressively teaches the full CLI surface when the skill is activated).
2. `R12.AC2` WHEN the agent matches the skill trigger (queries about wiki content, "what was I working on", ingest requests), the system SHALL load the SKILL.md body and expose `lyra query`, `lyra ingest`, `lyra brief`, `lyra status`, `lyra recent` invocations.
3. `R12.AC3` The skill SHALL be cross-agent: usable by Claude Code and OpenCode without modification; clients without skill support fall back to the CLI directly.
4. `R12.AC4` The skill SHALL NOT register MCP tools (per `NFR7`).

### R13 Obsidian Tasks Source

**User Story:** As an AI agent user, I want my Obsidian Tasks/ directory queryable through Lyra without duplicating obsidian-manager's writer role, so that operational state shows up in `lyra brief` and `lyra query` results.

#### Acceptance Criteria

1. `R13.AC1` The system SHALL ship `ObsidianTasksSource` as a second built-in Source plugin implementing the `R10` contract over `<vault>/Tasks/*.md`.
2. `R13.AC2` WHEN `lyra query` runs, the system SHALL fan out to both `KarpathyWikiSource` and `ObsidianTasksSource` and merge results with the source label preserved in the normalised hit.
3. `R13.AC3` WHEN `lyra brief` runs, the system SHALL surface up to 5 active tasks (filtered by `status: in_progress`) ordered by priority and latest-checkpoint timestamp.
4. `R13.AC4` `ObsidianTasksSource` SHALL be read-only; obsidian-manager MCP remains the canonical writer for task notes.

### R14 Schema Document (`wiki/AGENTS.md`)

**User Story:** As an AI agent user, I want a single canonical schema document that turns a generic LLM into a disciplined knowledge worker for my domain, so that ingestion and consolidation behave consistently and the schema co-evolves with the wiki (per LLM Wiki v2 "The schema is the real product").

#### Acceptance Criteria

1. `R14.AC1` `lyra init` SHALL deploy `wiki/AGENTS.md` only when absent, and SHALL NOT overwrite an existing file (`R1.AC6`).
2. `R14.AC2` The deployed `wiki/AGENTS.md` template SHALL encode: entity types, typed relationships, ingestion rules per `kind`, when-to-create-vs-update guidance, quality standards, contradiction-handling policy, consolidation schedule, and private/shared scoping conventions.
3. `R14.AC3` The schema document SHALL be co-evolvable: subsequent `lyra` operations SHALL read it (when present) but never silently rewrite it.
4. `R14.AC4` Q&A pages worth filing back into the wiki SHALL be appended (or referenced) under a `## Q&A` section convention defined by the schema.

### R15 Wiki Page Schema (frontmatter)

**User Story:** As an AI agent user, I want every compiled wiki page to carry a uniform structured frontmatter, so that retrieval, lint, supersession, and graph projection have stable fields to work with.

#### Acceptance Criteria

1. `R15.AC1` Every compiled wiki page SHALL declare frontmatter with at least: `id` (ULID), `title`, `type` (entity-type, e.g. source|concept|procedure|connection|qa|synthesis|session|meta), `sources`, `confidence`, `created`, `last_confirmed`, `supersedes`, `superseded_by`, `relations`.
2. `R15.AC2` Frontmatter SHALL additionally support optional `scope` (per `R16`), `quality` (auto|draft|reviewed|canonical), `contradicts` (list of page-ids), `last_consolidated` (date), and `aliases` (historical filenames).
3. `R15.AC3` The `tier` of a page (working|episodic|semantic|procedural) SHALL be derived from its directory path; an explicit `tier:` frontmatter field is NOT required.
4. `R15.AC4` Lyra `lint` SHALL flag pages missing required frontmatter fields and SHALL NOT auto-fix them (humans curate).

### R16 Scoping (private vs shared)

**User Story:** As an AI agent user, I want pages tagged as private or shared, so that team promotion via git stays explicit and personal observations don't leak into shared knowledge by default (per LLM Wiki v2 "Shared vs. private").

#### Acceptance Criteria

1. `R16.AC1` Pages SHALL carry an optional `scope:` frontmatter with values `private` (default), `shared`, `team`.
2. `R16.AC2` V1 SHALL treat all promoted pages as `scope: private` unless the user manually marks otherwise; V1 does NOT enforce scope on git operations.
3. `R16.AC3` M5 sinks SHALL respect `scope:` when promoting via shared git branches or mesh sync.

### R17 Q&A Filing Workflow

**User Story:** As an AI agent user, I want answers worth keeping to be filed back into the wiki, so that the next time the same question comes up the answer is canonical and cited (per LLM Wiki v2 "On query → check if the answer is worth filing back").

#### Acceptance Criteria

1. `R17.AC1` The system SHALL provide `lyra file --question "<q>" --answer "<a>" --sources <id1,id2>` to create a `wiki/qa/<ulid>-<slug>.md` page with `type: qa` frontmatter and provenance to source pages.
2. `R17.AC2` Q&A pages SHALL be queryable via the same hybrid retrieval path as semantic-tier pages.
3. `R17.AC3` `lyra query` SHALL NOT auto-file answers in V1; filing is explicitly user/agent triggered.
4. `R17.AC4` The default Q&A page body SHALL contain `# Question` and `# Answer` sections plus a `## Sources` list with wikilinks to the supporting pages.

## Non-Functional Requirements

- `NFR1` The system SHALL operate locally without requiring agentmemory, iii-engine, or a long-lived external memory service for V1.
- `NFR2` The system SHALL store canonical knowledge as plain markdown inside the Obsidian vault.
- `NFR3` The default session-start brief SHALL stay under 4 KB unless the user raises the limit.
- `NFR4` Core ingest, compile, query, and lint workflows SHALL run without proprietary LLM API keys.
- `NFR5` The public CLI SHALL run on Linux, macOS, and Windows via WSL.
- `NFR6` The public Lyra interface SHALL hide internal retrieval and indexing implementation details from the agent.
- `NFR7` Lyra V1 SHALL NOT expose an always-on MCP server; agent integration is delivered via the single `skills/lyra/` skill (R12) and the SessionStart hook to keep context-window overhead near zero (per ADR-1).

## Constraints And Dependencies

- `C1` The external Obsidian vault is the canonical storage location, even when the code repository lives elsewhere.
- `C2` qmd and the local Qwen3 embedding and reranker configuration are required dependencies for retrieval.
- `C3` Lyra remains the orchestrator/public interface; the Karpathy Wiki inside the vault remains the canonical store.
- `C4` V1 must not reimplement all of agentmemory; only the patterns required for a markdown-first orchestration model should be adopted.
- `C5` qmd is an internal implementation detail behind the public Lyra layer.
- `C6` Installer-generated runtime configuration may be rewritten, but user-authored wiki pages and raw artifacts must not be overwritten.

## Out Of Scope

- Sinks: write-back from Lyra into external sources (deferred to M5)
- Adapters for non-canonical sources beyond `KarpathyWikiSource` and `ObsidianTasksSource` in V1 (M2: agentmemory, mcp-memory-service, plain markdown trees)
- Multi-hop graph traversal beyond one hop (M3)
- Entity extraction (people, projects, libraries, concepts) at compile time (M3)
- Auto-supersession via contradiction detection at compile time (M3)
- Time-decay confidence and scheduled retention/consolidation jobs (M4) — V1 prefers explicit supersession over decay (per ADR-8)
- Procedural memory extraction (`wiki/procedures/` auto-population from repeated semantics) — M2+
- Task harvest pipeline (raw extraction of decisions from done Obsidian tasks → `raw/` → `wiki/sources/` via compile) — M2+
- Team-shared memory, mesh sync, and `scope: shared|team` enforcement (M5)
- Multi-agent coordination
- Always-on MCP server or any direct runtime dependency on agentmemory, iii-engine (per `NFR1`, `NFR7`)

## Delivery Model

<!-- assumed: plain GitHub repo plus installer; no persistent runtime skill -->

The system is distributed as a **plain GitHub repository** containing scripts, hook adapters, installer logic, and configuration. There is **no persistent runtime skill** and **no dependency on an always-on memory server** for V1.

Setup flow (single-shot, agent-driven):

1. The user tells the agent to clone the repository and run the installer for the chosen vault.
2. The installer records the absolute vault and wiki paths in the generated OpenCode runtime configuration.
3. The installer creates the `raw/` and `wiki/` layout in the target Obsidian vault and configures qmd behind the public script layer.
4. From that point on, OpenCode session hooks discover the wiki through the installed path and interact with it through the public CLI.

This keeps the runtime contract small and portable: a local vault, a public CLI, and an OpenCode adapter. Lyra-style multi-memory orchestration and agentmemory-style lifecycle features remain follow-on work rather than V1 dependencies.
