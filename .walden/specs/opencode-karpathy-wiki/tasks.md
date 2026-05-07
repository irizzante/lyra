---
status: draft
approved_at:
last_modified: 2026-05-07T00:00:00Z
source_design_approved_at:
---

# Implementation Plan

V1 ships as the M1 fat vertical defined in design.md. Each top-level item below maps to one sub-deliverable of M1. Coverage references requirements from `requirements.md`.

**Status legend.** ✅ done in V1 code; 🔧 REFACTOR PENDING (functional but layout differs from current spec — see ADR-6 raw flat); ⏳ planned.

- [✅] 1. M1.1 — `lyra init` and runtime config
  - [✅] 1.1 Implement Python package skeleton with `src/lyra/` layout, `pyproject.toml` (uv), and the `lyra` CLI entry point
    - Requirements: `R2.AC1`, `R2.AC2`, `R2.AC3`, `NFR5`
    - Design: `Components And Interfaces > Lyra Public Interface`
    - Verification:
      - command: ["uv", "run", "lyra", "--help"]
  - [🔧] 1.2 Implement `lyra init <vault>` to bootstrap `~/lyra/config.yaml`, create the **flat** `<vault>/raw/` (per ADR-6) and `<vault>/wiki/{sessions,sources,concepts,connections,procedures,synthesis,qa,meta}` layout, and deploy `AGENTS.md` only when absent (`R14.AC1`, `R1.AC6`)
    - Requirements: `R0.AC2`, `R1.AC1`–`R1.AC7`, `R14.AC1`–`R14.AC4`, `R2.AC4`, `R2.AC5`
    - Design: `Memory Layers`, `Components > Canonical Vault`, `Components > Schema Document`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_init.py"]
    - Refactor pending: current `vault.py` creates only `wiki/sources/` plus old `raw/{research,clips,sessions,assets}` subfolders. Refactor to flat raw + tier subfolders.

- [🔧] 2. M1.2 — Raw research and clip ingest
  - [🔧] 2.1 Implement `lyra ingest <path|url>` writing canonical raw records into **flat** `raw/<ulid>-<slug>.md` with `kind: research|clip` frontmatter (per ADR-6), with binary assets routed to `raw/assets/`
    - Requirements: `R0.AC2`, `R0.AC3`, `R7.AC1`, `R7.AC2`
    - Design: `Memory Layers`, `Components > Canonical Vault`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_ingest.py"]
    - Refactor pending: current code writes into `raw/research/` or `raw/clips/`. Move to flat `raw/`, frontmatter discriminates kind.

- [🔧] 3. M1.3 — Session export adapters
  - [🔧] 3.1 Implement OpenCode session reader against `~/.local/share/opencode/opencode.db` (filesystem-based, post-hoc) emitting raw session artifacts into **flat** `raw/<ulid>-<slug>.md` with `kind: session` (per ADR-6)
    - Requirements: `R0.AC2`, `R0.AC3`, `R3.AC1`–`R3.AC4`, `R8.AC3`
    - Design: `Architecture > Promotion pipeline layer`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_opencode_session.py"]
    - Refactor pending: current code writes into `raw/sessions/`. Move to flat `raw/`.
  - [✅] 3.2 Implement Claude Code `SessionStart` hook (JS/TS) under `hooks/claude-code/` that prepends `lyra brief` output to the session by default (per ADR-5, `R4.AC7`)
    - Requirements: `R4.AC7`, `R8.AC1`, `R8.AC2`, `R8.AC4`
    - Design: `Components > Lyra Skill`, `Components > OpenCode Hook Adapter`
    - Verification:
      - command: ["node", "--check", "hooks/claude-code/session-start.mjs"]
  - [✅] 3.3 Pre-existing vault smoke test: initialise Lyra over a vault that already contains user-authored markdown + `Tasks/` notes; assert no overwrites and that user pages stay queryable (`R1.AC6`, `R1.AC7`)
    - Requirements: `R1.AC6`, `R1.AC7`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_pre_existing_vault.py"]

- [🔧] 4. M1.4 — Compile pipeline with frontmatter, supersession, kind-dispatch
  - [🔧] 4.1 Implement `lyra compile` to walk **flat** `raw/*.md`, dispatch by `kind:` frontmatter (`research|clip → wiki/sources/`, `session → wiki/sessions/` for minimal episodic compression), and write extended frontmatter (`id` ULID, `type`, `scope`, `quality`, `sources`, `confidence`, `created`, `last_confirmed`, `last_consolidated`, `supersedes`, `superseded_by`, `contradicts`, `relations`)
    - Requirements: `R6.AC1`–`R6.AC8`, `R7.AC3`, `R15.AC1`–`R15.AC4`
    - Design: `Cross-reference Model`, `Memory Layers`
    - Verification:
      - command: ["uv", "run", "pytest", "-q", "tests/test_compile.py"]
    - Refactor pending: current code walks `raw/research/` + `raw/clips/`. Move to flat raw walk + dispatch by kind. Add session-kind path to `wiki/sessions/`.
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
