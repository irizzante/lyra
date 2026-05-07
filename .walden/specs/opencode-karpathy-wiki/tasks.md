---
status: draft
approved_at:
last_modified: 2026-05-07T00:00:00Z
source_design_approved_at:
---

# Implementation Plan

V1 ships M1 (canonical Karpathy Wiki source) plus M2 (pluggable external sources), per `design.md > Delivery Verticals`. M3 (entity extraction + multi-hop graph traversal + auto-supersession) is the next planned milestone. Each top-level item below maps to one sub-deliverable. Coverage references requirements from `requirements.md`.

**Status legend.** ✅ done in V1 code; 🔧 REFACTOR PENDING (functional but layout differs from current spec — see ADR-6 raw flat); ⏳ planned.

- [✅] 1. M1.1 — `lyra init` and runtime config
  - [✅] 1.1 Implement Python package skeleton with `src/lyra/` layout, `pyproject.toml` (uv), and the `lyra` CLI entry point
    - Requirements: `R2.AC1`, `R2.AC2`, `R2.AC3`, `NFR5`
    - Design: `Components And Interfaces > Lyra Public Interface`
    - Verification:
      - command: ["uv", "run", "lyra", "--help"]
  - [✅] 1.2 Implement `lyra init <vault>` to bootstrap `~/lyra/config.yaml`, create the **flat** `<vault>/raw/` (per ADR-6) and `<vault>/wiki/{sessions,sources,concepts,connections,procedures,synthesis,qa,meta}` layout, and deploy `AGENTS.md` only when absent (`R14.AC1`, `R1.AC6`)
    - Requirements: `R0.AC2`, `R1.AC1`–`R1.AC7`, `R14.AC1`–`R14.AC4`, `R2.AC4`, `R2.AC5`
    - Design: `Memory Layers`, `Components > Canonical Vault`, `Components > Schema Document`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_init.py"]

- [✅] 2. M1.2 — Raw research and clip ingest
  - [✅] 2.1 Implement `lyra ingest <path|url>` writing canonical raw records into **flat** `raw/<ulid>-<slug>.md` with `kind: research|clip` frontmatter (per ADR-6), with binary assets routed to `raw/assets/`
    - Requirements: `R0.AC2`, `R0.AC3`, `R7.AC1`, `R7.AC2`
    - Design: `Memory Layers`, `Components > Canonical Vault`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_ingest.py"]

- [✅] 3. M1.3 — Session export adapters
  - [✅] 3.1 Implement OpenCode session reader against `~/.local/share/opencode/opencode.db` (filesystem-based, post-hoc) emitting raw session artifacts into **flat** `raw/<ulid>-<slug>.md` with `kind: session` (per ADR-6)
    - Requirements: `R0.AC2`, `R0.AC3`, `R3.AC1`–`R3.AC4`, `R8.AC3`
    - Design: `Architecture > Promotion pipeline layer`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_opencode_session.py"]
  - [✅] 3.2 Implement Claude Code `SessionStart` hook (JS/TS) under `hooks/claude-code/` that prepends `lyra brief` output to the session by default (per ADR-5, `R4.AC7`)
    - Requirements: `R4.AC7`, `R8.AC1`, `R8.AC2`, `R8.AC4`
    - Design: `Components > Lyra Skill`, `Components > OpenCode Hook Adapter`
    - Verification:
      - command: ["node", "--check", "hooks/claude-code/session-start.mjs"]
  - [✅] 3.3 Pre-existing vault smoke test: initialise Lyra over a vault that already contains user-authored markdown + `Tasks/` notes; assert no overwrites and that user pages stay queryable (`R1.AC6`, `R1.AC7`)
    - Requirements: `R1.AC6`, `R1.AC7`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_pre_existing_vault.py"]

- [✅] 4. M1.4 — Compile pipeline with frontmatter, supersession, kind-dispatch
  - [✅] 4.1 Implement `lyra compile` to walk **flat** `raw/*.md`, dispatch by `kind:` frontmatter (`research|clip → wiki/sources/`, `session → wiki/sessions/` for minimal episodic compression), and write extended frontmatter (`id` ULID, `type`, `scope`, `quality`, `sources`, `confidence`, `created`, `last_confirmed`, `last_consolidated`, `supersedes`, `superseded_by`, `contradicts`, `relations`)
    - Requirements: `R6.AC1`–`R6.AC8`, `R7.AC3`, `R15.AC1`–`R15.AC4`
    - Design: `Cross-reference Model`, `Memory Layers`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_compile.py"]
  - [✅] 4.2 Author the canonical `wiki/AGENTS.md` schema template (per `R14.AC2`): entity types, typed relationships, ingestion rules per kind, when-to-create-vs-update, quality standards, contradiction-handling, consolidation schedule, scope conventions, Q&A filing conventions
    - Requirements: `R14.AC2`, `R14.AC3`
    - Design: `Components > Schema Document`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_agents_template.py"]

- [✅] 5. M1.5 — Typed relation parser
  - [✅] 5.1 Parse `relations:` frontmatter and inline `supports::` / `contradicts::` / `uses::` / `supersedes::` annotations and resolve `[[Page Name]]` to ULID `target_id` at compile time
    - Requirements: `R11.AC3`, `R11.AC4`
    - Design: `Cross-reference Model`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_relations.py"]

- [✅] 6. M1.6 — Hybrid index (BM25 + vector + graph)
  - [✅] 6.1 Wire qmd to build BM25/FTS5 + vector indexes over `wiki/` content
    - Requirements: `R9.AC1`, `R11.AC1`, `R11.AC5`, `R11.AC6`
    - Design: `Components And Interfaces > Derived Retrieval Layer`
    - Verification:
      - command: ["uv", "run", "lyra", "index", "--rebuild"]
  - [✅] 6.2 Build a SQLite graph projection materialising `(src, type, dst, confidence)` edges keyed by ULID; auto-populate from `compile_pipeline._upsert_graph`
    - Requirements: `R11.AC1`, `R11.AC4`
    - Design: `Cross-reference Model`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_graph_projection.py"]

- [✅] 7. M1.7 — `lyra query` with citations and confidence
  - [✅] 7.1 Implement hybrid retrieval combining BM25/FTS5, vector, and one-hop graph hops; return citations and per-claim confidence
    - Requirements: `R5.AC1`, `R5.AC2`, `R5.AC3`, `R5.AC4`, `R11.AC2`, `R11.AC5`
    - Design: `Components And Interfaces > Derived Retrieval Layer`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_query.py"]

- [✅] 8. M1.8 — `lyra brief` SessionStart preamble
  - [✅] 8.1 Generate a token-budgeted SessionStart preamble (default-ON, ≤4 KB, items as IDs + ≤400ch top-3 / ≤120ch tail per ADR-5): active tasks (from `ObsidianTasksSource`, M1.11), recent episodic sessions, top semantic pages, recent compile log, Lyra usage hint
    - Requirements: `R4.AC1`–`R4.AC8`, `NFR3`
    - Design: `Architecture > Derived retrieval layer`, ADR-5
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_brief.py"]

- [✅] 9. M1.9 — Feedback loop delivery
  - [✅] 9.1 Author the canonical `wiki/AGENTS.md` schema document template per `R14`: entity types, typed relationships, ingestion rules per `kind`, when-to-create-vs-update, quality standards, contradiction-handling policy, consolidation schedule, scope conventions, Q&A filing conventions; deploy on `lyra init` only when absent
    - Requirements: `R2A.AC1`–`R2A.AC3`, `R4.AC1`, `R4.AC2`, `R14.AC1`–`R14.AC4`, `NFR6`
    - Design: `Components > Schema Document`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_agents_template.py"]
  - [✅] 9.2 Wire the Claude Code `SessionStart` hook to call `lyra brief` and prepend its output to the session by default (`R4.AC7`); already implemented in `hooks/claude-code/session-start.mjs` (M1.3.2)
    - Requirements: `R4.AC1`, `R4.AC7`, `R8.AC1`, `R8.AC2`
    - Design: `Components > Lyra Skill`, ADR-5
    - Verification:
      - command: ["node", "--check", "hooks/claude-code/session-start.mjs"]
  - [✅] 9.3 Implement unified `lyra install [--hook] [--skill] [--scope=user|project] [--no-inject]` that copies `hooks/claude-code/session-start.mjs` and `skills/lyra/SKILL.md` into the chosen target (Claude Code: `~/.claude/` or `.claude/`; OpenCode: equivalent)
    - Requirements: `R4.AC7`, `R8.AC1`, `R12.AC1`–`R12.AC4`, `NFR5`, `NFR7`
    - Design: `Components > Lyra Skill`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_install.py"]
  - [✅] 9.4 Author the single Lyra skill at `skills/lyra/SKILL.md` (progressive discovery): concise frontmatter trigger + body that progressively documents `lyra query/ingest/brief/status/recent/file`
    - Requirements: `R12.AC1`–`R12.AC4`
    - Design: `Components > Lyra Skill`, ADR-3
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_skill_template.py"]

- [✅] 10. M1.10 — `lyra status` and `lyra lint`
  - [✅] 10.1 Implement `lyra status` reporting vault layout, index health, graph health, per-source health (both `KarpathyWikiSource` and `ObsidianTasksSource`)
    - Requirements: `R5.AC1`, `R10.AC6`, `R13.AC1`–`R13.AC4`
    - Design: `Components And Interfaces > Lyra Public Interface`
    - Verification:
      - command: ["uv", "run", "lyra", "status"]
  - [✅] 10.2 Implement `lyra lint` reporting orphans, broken supersessions, dangling typed relations, contradictions without explicit supersession (per ADR-8), pages missing required frontmatter (`R15.AC4`)
    - Requirements: `R9.AC2`, `R9.AC3`, `R9.AC4`, `R15.AC4`
    - Design: `Components And Interfaces > Derived Retrieval Layer`, ADR-8
    - Verification:
      - command: ["uv", "run", "lyra", "lint", "--structural-only"]

- [✅] 11. M1.11 — Obsidian Tasks Source plugin
  - [✅] 11.1 Define the `Source` protocol with `query`, `list_recent`, `health`, `capabilities` and ship `KarpathyWikiSource` as the built-in canonical source implementing it
    - Requirements: `R10.AC1`–`R10.AC6`
    - Design: `Components And Interfaces > Source Plugin Contract`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_source_contract.py"]
  - [✅] 11.2 Implement `ObsidianTasksSource` over `<vault>/Tasks/*.md` (read-only): separate qmd collection `lyra-tasks`, normalised hits with `source: "obsidian-tasks"`, integration into `lyra query` fan-out and `lyra brief` active-tasks section
    - Requirements: `R10.AC1`–`R10.AC6`, `R13.AC1`–`R13.AC4`
    - Design: `Components > Obsidian Tasks Source`, ADR-4
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_obsidian_tasks_source.py"]

- [✅] 12. M1.12 — `lyra file` Q&A filing workflow
  - [✅] 12.1 Implement `lyra file --question "<q>" --answer "<a>" --sources <id1,id2>` to create a `wiki/qa/<ulid>-<slug>.md` page with `type: qa`, `# Question` / `# Answer` / `## Sources` body sections, and `relations: [{type: answers, target_id: <source>}]`
    - Requirements: `R17.AC1`–`R17.AC4`
    - Design: `Components > Schema Document`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_qa_filing.py"]

## M2 — Pluggable external sources (read-only)

Goal: extend the source plugin contract so external read-only memories (plain markdown trees, agentmemory, mcp-memory-service) can be registered alongside the canonical Karpathy Wiki V2 source. Cross-source query fan-out with merged citations and per-source health surfaced by `lyra status`.

- [✅] 13. M2.1 — Source registry and dynamic adapter loading
  - [✅] 13.1 Add `adapter` field to `SourceConfig` (dotted class path) and implement `load_source` / `load_all_sources` in `lyra.sources` with a `_BUILTIN_ADAPTERS` lookup for `karpathy_wiki`, `obsidian_tasks`, `plain_markdown`, `agentmemory`, `mcp_memory`; graceful warning (no crash) when an adapter fails to instantiate
    - Requirements: `R10.AC1`–`R10.AC6`
    - Design: `Components And Interfaces > Source Plugin Contract`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_source_registry.py"]

- [✅] 14. M2.2 — `lyra source` CLI subcommands
  - [✅] 14.1 Implement `lyra source list|add|remove|refresh` over `~/lyra/config.yaml` with health probing on add/refresh and clear error messages for unknown adapters
    - Requirements: `R10.AC1`–`R10.AC6`, `NFR5`, `NFR6`
    - Design: `Components And Interfaces > Lyra Public Interface`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_source_cli.py"]

- [✅] 15. M2.3 — Cross-source query fan-out
  - [✅] 15.1 Implement `fanout_query` in `query.py`: for each enabled source call `Source.query`, merge `QueryHit` results with per-source attribution, expose via `lyra query` and `lyra brief`
    - Requirements: `R5.AC1`–`R5.AC4`, `R10.AC1`–`R10.AC6`
    - Design: `Components And Interfaces > Derived Retrieval Layer`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_source_registry.py"]

- [✅] 16. M2.4 — Per-source health in `lyra status`
  - [✅] 16.1 Surface per-source `health()` results (status, last error, document counts where applicable) in `lyra status` output for every enabled source
    - Requirements: `R5.AC1`, `R10.AC6`
    - Design: `Components And Interfaces > Lyra Public Interface`
    - Verification:
      - command: ["uv", "run", "lyra", "status"]

- [✅] 17. M2.5 — `PlainMarkdownSource` adapter
  - [✅] 17.1 Implement `PlainMarkdownSource` over an arbitrary directory of `*.md` files: walk read-only, extract frontmatter + body, return `QueryHit` results with `source: "plain-markdown"`; no qmd dependency, simple substring/BM25 matching against an in-memory index built per-call
    - Requirements: `R10.AC1`–`R10.AC6`
    - Design: `Components > Source Plugin Contract`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_plain_markdown_source.py"]

- [✅] 18. M2.6 — `AgentmemorySource` adapter
  - [✅] 18.1 Implement `AgentmemorySource` over an `agentmemory`-compatible HTTP endpoint with graceful degradation when the runtime is unavailable; normalised hits with `source: "agentmemory"`; explicit error surfaced via `health()` instead of raising
    - Requirements: `R10.AC1`–`R10.AC6`, `NFR1`
    - Design: `Components > Source Plugin Contract`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_network_sources.py"]

- [✅] 19. M2.7 — `McpMemorySource` adapter
  - [✅] 19.1 Implement `McpMemorySource` over an `mcp-memory-service` endpoint with graceful degradation when unreachable; normalised hits with `source: "mcp-memory"`; explicit error surfaced via `health()` instead of raising (preserves NFR7: no always-on MCP requirement in V1)
    - Requirements: `R10.AC1`–`R10.AC6`, `NFR1`, `NFR7`
    - Design: `Components > Source Plugin Contract`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_network_sources.py"]

## M3 — Entity extraction + multi-hop graph traversal + auto-supersession

Goal: extract entities (people, projects, libraries, concepts, files, decisions) at compile time as first-class wiki pages under `wiki/entities/<entity_type>/`; multi-hop graph queries with RRF fusion; auto-supersession via weighted score on contradiction detection at compile time.

**Mode split (no env var, implicit from CLI flags):**
- `lyra compile` — batch over pending raw. Uses LiteLLM if `extraction.llm.provider` configured, else heuristic baseline. Used by SessionEnd hook, cron, and outside-session manual invocation.
- `lyra compile --raw-id <id> --entities '<json>'` — imperative single-page. Skips LLM call (entities pre-extracted); applies them deterministically. Used by skill inside session host.
- `lyra compile --raw-id <id>` (no entities) — single-page, same provider logic as batch.

**Hook strategy** (aligned with agentmemory + Karpathy Wiki V2 gist patterns):
- SessionStart (existing M1.3.2): only `lyra brief` (load context). Fast, no compile.
- SessionEnd (NEW M3): runs `lyra compile`. Catches pending raw at session boundary.
- Brief extended to surface raw-pending count (cheap, stateless count).
- Inside session: skill orchestrates per-page compile via the agent's LLM (no env var, no IPC — skill instructions teach the pattern).
- Cleanup of `raw/` is M4 scope (retention/decay).

**ADRs to author in this milestone**: ADR-9 (entity extraction strategy: agent-host LLM via skill + LiteLLM fallback, no always-on server); ADR-10 (multi-hop default `max_hops=2` + RRF fusion `k=60`); ADR-11 (auto-supersession via weighted score `0.5·recency + 0.3·authority + 0.2·support`, threshold-gated, both pages preserved).

- [✅] 20. M3.0 — Author ADR-9, ADR-10, ADR-11 in `design.md`
  - [✅] 20.1 Add ADR-9 (entity extraction strategy), ADR-10 (multi-hop traversal + RRF fusion), ADR-11 (auto-supersession scoring) sections to `design.md > Architecture Decisions`; cross-reference from M3 sub-items below
    - Requirements: documentation pre-req for `R6`, `R11`, `R9`
    - Design: `Architecture Decisions`
    - Verification:
      - command: ["grep", "-q", "ADR-9", ".walden/specs/opencode-karpathy-wiki/design.md"]
      - command: ["grep", "-q", "ADR-10", ".walden/specs/opencode-karpathy-wiki/design.md"]
      - command: ["grep", "-q", "ADR-11", ".walden/specs/opencode-karpathy-wiki/design.md"]

- [⏳] 21. M3.1 — Entity model and first-class wiki pages
  - [⏳] 21.1 Define entity page schema: frontmatter `type: entity`, `entity_type: person|project|library|concept|file|decision`, `aliases: [...]`, `attributes: {...}`, ULID `id:`; ensure-layout for `wiki/entities/<entity_type>/` directories in `vault.py`; document conventions in canonical `wiki/AGENTS.md` template (`R14.AC2`)
    - Requirements: `R6.AC1`–`R6.AC8`, `R14.AC2`–`R14.AC4`, `R15.AC1`–`R15.AC4`
    - Design: `Components > Schema Document`, `Cross-reference Model`, ADR-9
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_entity_model.py"]

- [⏳] 22. M3.2 — Heuristic entity extractor (deterministic baseline)
  - [⏳] 22.1 Implement `src/lyra/extract/heuristic.py`: parse inline `entity::<type> <name>` annotations; resolve `[[wikilinks]]` whose target page has `type: entity`; read declarative frontmatter `entities: [...]` field; regex patterns for file paths (e.g. `src/foo.py`) and Python/JS imports; return `list[ExtractedEntity]` with type, name, aliases, mention positions
    - Requirements: `R6.AC1`–`R6.AC8`, `R11.AC3`, `R11.AC4`
    - Design: `Cross-reference Model`, ADR-9
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_heuristic_extractor.py"]

- [⏳] 23. M3.3 — Compile pipeline integration with extraction provider abstraction
  - [⏳] 23.1 Wire heuristic + provider abstraction in `compile_pipeline`: heuristic always runs; if `extraction.llm.provider` configured AND no `--entities` flag passed, call provider; merge heuristic + LLM results (dedup on `entity_type+name`); upsert entity pages under `wiki/entities/<entity_type>/<ulid>-<slug>.md`; add `mentions(src_id, entity_id, confidence)` graph edges to projection
    - Requirements: `R6.AC1`–`R6.AC8`, `R11.AC1`, `R11.AC4`
    - Design: `Components > Promotion Pipeline Layer`, ADR-9
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_compile_extraction.py"]

- [⏳] 24. M3.4 — `lyra compile` imperative single-page mode (`--raw-id` + `--entities`)
  - [⏳] 24.1 Add `--raw-id <id>` and `--entities '<json>'` flags to `lyra compile`; when `--entities` present → skip provider call, validate JSON schema, apply entities deterministically; idempotent across re-runs; clear error on malformed JSON or unknown entity type
    - Requirements: `R5.AC1`, `R6.AC1`–`R6.AC8`, `R10.AC1`
    - Design: `Components > Lyra Public Interface`, ADR-9
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_compile_imperative.py"]

- [⏳] 25. M3.5 — LiteLLM provider for batch compile (Mode B)
  - [⏳] 25.1 Add `litellm` as optional extras dep (`extraction`); extend `config.py` with `extraction.llm = {provider, model, endpoint?, ...}`; implement thin wrapper `src/lyra/extract/llm.py` calling `litellm.completion` with structured JSON schema prompt; supports `openai`, `anthropic`, `ollama`, `github_copilot`, `azure`, `bedrock`, etc.; graceful fallback to heuristic with warning when provider unreachable (preserves NFR1: no API key required for core)
    - Requirements: `R6.AC1`–`R6.AC8`, `R10.AC6`, `NFR1`
    - Design: `Components > Promotion Pipeline Layer`, ADR-9
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_litellm_provider.py"]

- [⏳] 26. M3.6 — Multi-hop graph traversal (BFS via SQLite recursive CTE)
  - [⏳] 26.1 Implement `traverse(start_ids, max_hops, edge_types)` in `graph_projection.py` using SQLite recursive CTE; default `max_hops=2` (configurable via `query.max_hops`, capped at 4); edge-type filter excludes `contradicts` and `superseded_by` from BFS expansion; result-size cap to prevent explosion on dense graphs
    - Requirements: `R11.AC1`–`R11.AC6`
    - Design: ADR-10
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_multi_hop_traversal.py"]

- [⏳] 27. M3.7 — `lyra query` multi-hop integration with RRF fusion
  - [⏳] 27.1 Add `--max-hops N` flag to `lyra query`; replace existing `_extend_with_graph` (one-hop) with `_traverse_graph(start_ids, max_hops, edge_types)`; implement RRF fusion (`k=60`) combining BM25 + vector + graph streams in `query.py`; surface multi-hop paths in citations (e.g. `Page A → mentions → Entity X → uses → Page B`)
    - Requirements: `R5.AC1`–`R5.AC4`, `R11.AC1`–`R11.AC6`
    - Design: `Components > Derived Retrieval Layer`, ADR-10
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_query_multi_hop.py"]

- [⏳] 28. M3.8 — Auto-supersession via weighted score on contradiction
  - [⏳] 28.1 Implement `src/lyra/supersession.py`: compute weighted score `0.5·recency + 0.3·authority + 0.2·support` per page (weights configurable via `auto_supersession.weights`); when `A contradicts:: B` and `|score(A) − score(B)| ≥ threshold` (default `0.2`), set `winner.supersedes=[loser.id]` + `loser.superseded_by=winner.id`; preserve both pages; emit decision log with breakdown; opt-out via `auto_supersession.enabled: false`
    - Requirements: `R6.AC1`–`R6.AC8`, `R9.AC2`, `R11.AC4`
    - Design: ADR-8 (existing) + ADR-11 (new)
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_supersession.py"]

- [⏳] 29. M3.9 — `lyra lint` updates for unresolved contradictions
  - [⏳] 29.1 Update lint to surface contradictions where score gap was below threshold (`needs human resolution`); show score breakdown (recency / authority / support) per ambiguous case; existing `CONTRADICTION` lint kind extended with `score_gap`, `winner_score`, `loser_score` fields
    - Requirements: `R9.AC2`, `R9.AC3`, `R9.AC4`, `R15.AC4`
    - Design: `Components > Derived Retrieval Layer`, ADR-11
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_lint_contradictions.py"]

- [⏳] 30. M3.10 — SessionEnd hook + brief extension for raw-pending visibility
  - [⏳] 30.1 Implement `hooks/claude-code/session-end.mjs` running `lyra compile` (LiteLLM if configured, else heuristic); extend `lyra brief` to include `📋 N raw pages pending promotion` line when `count(raw/*.md not yet promoted) > 0` (cheap directory scan, no hash); update `lyra install --hook` to install both SessionStart and SessionEnd
    - Requirements: `R3.AC1`–`R3.AC4`, `R4.AC1`–`R4.AC8`, `R8.AC1`–`R8.AC4`
    - Design: `Components > OpenCode Hook Adapter`, ADR-5
    - Verification:
      - command: ["node", "--check", "hooks/claude-code/session-end.mjs"]
      - command: ["uv", "run", "pytest", "-q", "tests/test_brief_pending_count.py"]

- [⏳] 31. M3.11 — Skill update: in-session entity extraction workflow
  - [⏳] 31.1 Add "Raw promotion workflow" section to `skills/lyra/SKILL.md`: when brief shows raw pending OR after `lyra ingest` succeeds OR on user request, agent reads each raw page, extracts entities (people/projects/libraries/concepts/files/decisions) using the documented prompt template, calls `lyra compile --raw-id <id> --entities '<json>'` per page; document entity JSON schema in skill body
    - Requirements: `R12.AC1`–`R12.AC4`, `R14.AC2`
    - Design: `Components > Lyra Skill`, ADR-3, ADR-9
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_skill_template.py"]
