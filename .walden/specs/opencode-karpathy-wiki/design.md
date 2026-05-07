---
status: draft
approved_at:
last_modified: 2026-05-06T16:30:00Z
source_requirements_approved_at:
---

# Feature Design

## Overview

The preferred design keeps the Karpathy Wiki in a user-chosen Obsidian vault as the canonical store and puts `Lyra` in front of it as the public orchestration interface. Hooks and ingest workflows write only raw artifacts into `vault/raw/`; compilation promotes selected knowledge into `vault/wiki/`; retrieval operates through derived indexes built from the vault but hidden behind Lyra. This preserves a markdown-first model while reusing the strongest ideas from agentmemory: hook-driven capture, compact SessionStart context, promotion from raw work into reusable knowledge, and efficient retrieval that avoids replaying the same tool work.

## Memory Layers (Karpathy Wiki V2 alignment)

Lyra implements the four-tier consolidation pipeline described in LLM Wiki v2 "The missing layer: memory lifecycle". Each tier is more compressed, more confident, and longer-lived than the one below it. Information is **promoted upward** as evidence accumulates.

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Lyra Memory Tiers                              │
├──────────────────────────────────────────────────────────────────────┤
│ Working   →  raw/<ulid>-<slug>.md  (flat directory)                  │
│              kind: research|clip|session   — append-only, no synth   │
│              binary attachments under raw/assets/ only               │
│                                                                      │
│ Episodic  →  wiki/sessions/<ulid>-<slug>.md                          │
│              compressed session summaries from raw kind=session      │
│                                                                      │
│ Semantic  →  wiki/sources/      single-source promotions             │
│              wiki/concepts/     consolidated cross-source facts      │
│              wiki/connections/  relationship pages (graph nodes)     │
│              wiki/synthesis/    convergent multi-source synthesis    │
│              ULID + confidence + supersedes + typed relations        │
│                                                                      │
│ Procedural → wiki/procedures/   workflows + patterns (M2+ extract)   │
│                                                                      │
│ Q&A       →  wiki/qa/           filed-back answers from lyra query   │
│ Meta      →  wiki/meta/         schema docs, lint reports            │
│ Schema    →  wiki/AGENTS.md     the schema document — co-evolves     │
│                                                                      │
│ Index     →  ~/lyra/index/<source>/ qmd BM25/FTS5 + vector + graph   │
│              derived, rebuildable from markdown only                 │
└──────────────────────────────────────────────────────────────────────┘
```

The path is the tier — a page's directory tells you which consolidation level it's at. The frontmatter `type:` field is the **entity type** within that tier (open taxonomy defined per-domain in `wiki/AGENTS.md`).

## Architecture

Lyra is a memory orchestrator. It operates over one or more memory **sources** through a uniform plugin contract; Karpathy Wiki V2 is the canonical default source. V1 ships with two built-in sources: `KarpathyWikiSource` (canonical wiki) and `ObsidianTasksSource` (read-only over `<vault>/Tasks/*.md`). External sources (agentmemory, mcp-memory-service, plain markdown trees, MCP memory servers) plug in as additional read-paths in M2+. **Sinks** — the inverse contract that would let Lyra write back into external sources — are out of scope for V1 and revisited later.

The design has four layers.

1. Source plane
- Each source implements a small contract: `query`, `list_recent`, `health`, `capabilities`.
- Karpathy Wiki V2 is the bundled canonical source. Other sources are optional adapters.
- Sinks (write-back) are deferred.

2. Canonical vault layer (Karpathy Wiki V2 source)
- `vault/raw/` stores immutable raw inputs in a **flat** directory; `kind:` frontmatter discriminates research|clip|session. Binary attachments live under `vault/raw/assets/`.
- `vault/wiki/` stores compiled team-readable knowledge organized by memory tier: `sessions` (episodic), `sources/concepts/connections/synthesis` (semantic), `procedures` (procedural), `qa` (filed-back answers), `meta` (schema/lint).
- The vault is the source of truth for this source. If indexes or caches are lost, they are rebuilt from the vault.

3. Promotion pipeline layer (Karpathy Wiki V2 source)
- Claude Code `SessionStart` hook captures session lifecycle live and prepends `lyra brief` output by default (opt-out via `LYRA_INJECT_BRIEF=false`).
- OpenCode sessions are read post-hoc from the local SQLite store at `~/.local/share/opencode/opencode.db` because OpenCode does not expose a stable SessionStart-equivalent for prompt injection in V1.
- Raw artifacts are written to flat `vault/raw/` with `kind:` frontmatter.
- Compilation reads raw artifacts and dispatches by `kind:`: `research|clip → wiki/sources/`, `session → wiki/sessions/` (episodic compression). Promoted pages carry provenance, confidence, supersession edges, and typed relations.

4. Derived retrieval layer
- Per-source: BM25/FTS5 + vector via qmd, plus a SQLite graph projection built from typed relations parsed out of markdown frontmatter and inline annotations.
- Cross-source: Lyra fans out queries across enabled sources, merges results with a hybrid ranker, and emits citations scoped to the originating source.
- The `lyra brief` workflow aggregates recent activity from all enabled sources into a compact SessionStart-style preamble.

## Options Considered

### Option A

- Summary: Markdown-first Lyra orchestrator over a canonical Obsidian Karpathy Wiki.
- Why chosen: This preserves the team-readable, git-friendly source of truth you want while still allowing efficient query and hook-driven promotion. It adopts agentmemory's strongest runtime patterns without making iii/state storage the canonical model.

### Option B

- Summary: Agentmemory-style runtime as the canonical memory with Obsidian export as a mirror.
- Why rejected: This is operationally attractive because many capabilities already exist, but it makes the wiki a derived artifact instead of the canonical knowledge store. That weakens the markdown-first, repo-first team knowledge model and makes Lyra less distinct.

### Option C

- Summary: Pure Karpathy Wiki tooling without Lyra as a named orchestrator.
- Why rejected: This keeps the system small, but it loses the clearer product boundary you already decided on: Lyra as the stable public interface over a canonical wiki and derived retrieval internals.

## Simplicity And Elegance Review

- Simplest viable shape: Keep only two physical data areas, `raw/` and `wiki/`, and avoid intermediate canonical stores. Promotion is a logical workflow, not a third primary store.
- Coupling check: Hooks know events, Lyra knows orchestration, qmd knows retrieval, and the vault holds knowledge. No internal component other than the vault is canonical.
- Future-proofing: Confidence scoring, richer typed graph traversal, team-shared promotion policies, and non-OpenCode adapters are deferred but compatible with the model.

## Components And Interfaces

### Source Plugin Contract

- Purpose: Allow Lyra to plug in additional memory sources beyond the canonical Karpathy Wiki V2.
- Inputs/Outputs: Each source exposes `query(q, k, filters)`, `list_recent(window)`, `health()`, `capabilities()`. Returns are normalised to `{id, source, title, snippet, score, citations, last_seen}`.
- Dependencies: Lyra core plus per-source adapter (filesystem, MCP client, HTTP client, etc.).
- V1 sources: Karpathy Wiki V2 (built-in). Adapters for agentmemory and mcp-memory-service are post-V1.
- Sinks (write-back contract) are deferred; not part of V1.
- Requirements: `R2A` (covers public interface); a dedicated requirement for the source plugin contract is pending in `requirements.md`.

### Lyra Public Interface

- Purpose: Stable public interface used by agents and runtime adapters.
- Inputs/Outputs: Accepts query/status/recent-context/compile/lint/source style commands and returns concise operational results with citations or diagnostics. Cross-source orchestration is part of this surface, not the per-source adapters.
- Dependencies: Source Plugin Contract, canonical vault, query layer, compile/lint/status scripts.
- Requirements: `R2A`, `R4`, `R5`, `NFR6`

### OpenCode Hook Adapter

- Purpose: Translate OpenCode lifecycle events into Lyra workflows.
- Inputs/Outputs: Hook payload in, Lyra workflow invocation and best-effort startup/context output out.
- Dependencies: OpenCode hook contract, Lyra public interface.
- Requirements: `R3`, `R4`, `R8`

### Canonical Vault

- Purpose: Store raw and compiled knowledge in markdown form.
- Inputs/Outputs: Raw artifacts and compiled pages.
- Dependencies: Obsidian-compatible filesystem layout.
- Requirements: `R1`, `R6`, `R7`, `NFR2`

### Derived Retrieval Layer

- Purpose: Provide efficient BM25/vector/graph-assisted retrieval without becoming the source of truth.
- Inputs/Outputs: Reads vault markdown and emits search indexes, graph projections, and startup summaries.
- Dependencies: qmd, local embedding/reranker configuration, markdown relation parser.
- Requirements: `R4`, `R5`, `R9`, `C2`, `C5`

### Lyra Skill (single, progressive discovery)

- Purpose: Cross-agent (Claude Code + OpenCode) entry point that exposes Lyra capabilities on demand without paying an always-on MCP context tax.
- Form: One file at `skills/lyra/SKILL.md` with concise frontmatter trigger description and a body that progressively teaches the full CLI surface (query, ingest, brief, status, recent, file).
- Distribution: `lyra install --skill` copies into `~/.claude/skills/lyra/` (or `--scope=project` for `.claude/skills/lyra/`).
- Requirements: `R12`, `NFR7`

### Obsidian Tasks Source

- Purpose: Surface operational state from the user's `<vault>/Tasks/*.md` (managed by `obsidian-manager` MCP) without duplicating the writer role.
- Inputs/Outputs: Implements the Source contract (`query`, `list_recent`, `health`, `capabilities`) over a separate qmd collection (`lyra-tasks`); read-only.
- Dependencies: `<vault>/Tasks/*.md` filesystem; `obsidian-manager` MCP remains canonical writer.
- Requirements: `R10`, `R13`

### Schema Document (`wiki/AGENTS.md`)

- Purpose: The single canonical schema that turns a generic LLM into a disciplined knowledge worker for the user's domain (per LLM Wiki v2: "the schema is the real product").
- Encodes: entity types, typed relationships, ingestion rules per `kind`, when-to-create-vs-update, quality standards, contradiction-handling policy, consolidation schedule, scope conventions, Q&A filing conventions.
- Lifecycle: deployed by `lyra init` only when absent; co-evolves via human + agent edits; `lint` reads it but never silently rewrites it.
- Requirements: `R14`, `R15`, `R16`, `R17`, `R2A`

## Data Models

Primary data models:

- Raw session artifact
  - Stored under `vault/raw/sessions/`
  - Contains captured session narrative, tool-derived outcomes, provenance, and compacted context snapshots.

- Raw research/clip artifact
  - Stored under `vault/raw/research/` or `vault/raw/clips/`
  - Represents uncompiled source material.

- Wiki page
  - Stored under `vault/wiki/...`
  - Canonical markdown page with frontmatter or inline metadata for provenance, confidence/frequency where available, and typed relations where modeled.

- Derived query/index data
  - Not canonical.
  - Includes qmd indexes, graph adjacency projections, and SessionStart summaries.

Logical states of knowledge:
- raw
- promotable
- canonical

Only `raw` and `canonical` require primary storage in the vault. `promotable` is a pipeline state, not a required top-level directory.

## Cross-reference Model

Two reference layers coexist in the canonical vault. They serve different purposes and resolve through different mechanisms.

1. Obsidian wikilinks — `[[Page Name]]` in page bodies. Used for human navigation in Obsidian and resolve by **filename**. Obsidian's "automatically update internal links on rename" handles slug changes inside the editor. Use these for prose links inside compiled wiki pages.

2. Lyra typed relations — declared in frontmatter `relations:` and inline `supports::` / `contradicts::` / `uses::` / `supersedes::` annotations. Targets resolve by **ULID** in the canonical graph projection. Stable across renames, rewrites, and external edits.

Authoring flow:
- Humans write the human-friendly form: `supports:: [[Page Name]]`.
- `lyra compile` resolves `[[Page Name]]` to the target's ULID `id` at promotion time and stores the canonical edge in the graph projection as `{type: supports, target_id: <ULID>, confidence: <float>}`.
- The body of the page may keep the wikilink for Obsidian readability; the graph layer relies only on the resolved ULID edge.

Page frontmatter therefore carries:

```yaml
id: 01HXYZ...           # ULID, durable, never reused
aliases: [old-slug]     # historical filenames for Obsidian alias resolution
type: concept | procedure | connection | qa | synthesis | source | session | meta
scope: private          # private (default) | shared | team — enforced from M5 sinks onward
quality: auto           # auto | draft | reviewed | canonical
sources: [<raw-id>, ...]
confidence: 0.85
created: 2026-05-06
last_confirmed: 2026-05-06
last_consolidated: 2026-05-06
supersedes: [<page-id-ulid>]
superseded_by: <page-id-ulid>
contradicts: [<page-id-ulid>, ...]
relations:
  - {type: supports, target_id: 01HABC..., confidence: 0.9}
  - {type: contradicts, target_id: 01HDEF...}
```

The `tier` (working|episodic|semantic|procedural) is derived from the page's directory path — no explicit `tier:` field. The `type:` taxonomy is open and defined per-domain in `wiki/AGENTS.md`; the values above are the default seed taxonomy.

Filenames remain slug-derived for human readability and clean git diffs; the durable identity is the ULID. When a page is renamed, the old filename is appended to `aliases:` so existing Obsidian links keep resolving while the graph layer stays anchored on the unchanged ULID.

## Architecture Decisions

These ADRs are intentionally inline in the design document (not separate `.walden/adr/` files) so future readers reach them in the same place they reach the architecture they explain.

### ADR-1 No always-on MCP server in V1

**Context.** MCP tool definitions live in the agent's context window for the entire session, even when unused. Each tool description costs ~50–200 tokens. agentmemory ships ~50 tools = ~5–10 KB sustained overhead per session.

**Decision.** Lyra V1 ships **no always-on MCP server**. Agent integration is delivered via (a) a single skill loaded on-demand (`R12`) and (b) a SessionStart hook that injects a one-shot brief (`R4`).

**Consequences.** Lower context-window overhead (Lyra's design priority is "least invasive"). Agents that don't speak skill protocols (Cursor/Continue) integrate via plain CLI. MCP-only hosts revisited in M2+ if demand emerges; not a V1 dependency.

### ADR-2 No iii-engine dependency in V1

**Context.** agentmemory layers conversation memory on top of `iii-engine`, a long-lived memory service. iii is a different concern (per-session conversational state) from Lyra (canonical markdown knowledge with ULID + relations).

**Decision.** Lyra V1 has **no iii-engine dependency**. `NFR1` codifies this. Storage is filesystem (vault) + qmd index + SQLite graph projection.

**Consequences.** No service to run, no per-session daemon. Lifecycle features that depend on long-lived state (live conversation summarization, multi-machine session memory) revisited in M2+ if mesh-sync requires.

### ADR-3 Single skill with progressive discovery

**Context.** Multiple skills (`lyra-query`, `lyra-ingest`, `lyra-recent`) fragment metadata, increase trigger noise, and complicate maintenance. The `skill-creator` pattern recommends one skill that progressively teaches its capabilities when activated.

**Decision.** Lyra ships a **single skill** at `skills/lyra/SKILL.md`. Frontmatter trigger is concise; body progressively documents `lyra query/ingest/brief/status/recent/file`.

**Consequences.** One file to maintain. Cross-capability awareness when activated. Lower trigger noise.

### ADR-4 Tasks as L2 Source plugin in V1; harvest pipeline M2+

**Context.** Obsidian tasks are operational state (Layer 2 / external) managed by `obsidian-manager` MCP. They are distinct from sessions (raw conversational trace) and from canonical wiki knowledge.

**Decision.** V1 exposes Tasks as a read-only Source plugin (`R13`). Harvest pipeline that distills decisions from done tasks into `raw/` → `wiki/sources/` is **deferred to M2+**.

**Consequences.** `lyra brief` shows active tasks immediately. obsidian-manager remains canonical writer. Promotion of operational decisions into canonical knowledge stays explicit (manual `lyra ingest <task_path>` for now), avoiding wiki pollution from operational chatter.

### ADR-5 Brief is a map (IDs + summaries), default-ON

**Context.** Two competing pressures: agentmemory disabled session-start injection by default at 0.8.10 to protect the context window; LLM Wiki v2 explicitly recommends "On session start: load relevant context from the wiki based on recent activity".

**Decision.** Lyra V1 brief injection is **ON by default** (gist alignment). Items in the brief are **identifier + ≤400 char summary** (top-3 per section) or **identifier + ≤120 char title** (tail), never full bodies. Total ≤ 4 KB per `NFR3`. Opt-out via `LYRA_INJECT_BRIEF=false` or `lyra install --hook --no-inject`.

**Consequences.** Agents start each session with operational context. The brief is a map; agents resolve detail via `lyra query <id>`. The user can disable injection with one env var if they ever feel the cost outweighs the benefit.

### ADR-6 `raw/` flat; `wiki/` organized by tier

**Context.** Raw observations are unprocessed working memory — organizing them by kind (`raw/research/`, `raw/clips/`, `raw/sessions/`) duplicates the `kind:` frontmatter and pretends `raw/` has structure it doesn't have.

**Decision.** `raw/` is **flat**: every record at `raw/<ulid>-<slug>.md` with `kind:` frontmatter discriminating. The only allowed sub-directory is `raw/assets/` for binary attachments (technical separation, not organizational). `wiki/` is **organized by memory tier** (sessions, sources, concepts, etc.).

**Consequences.** Single-pass walk over `raw/*.md` for compile, dispatching by `kind:`. Refactor pending on M1.2/M1.3/M1.4 code that currently writes into `raw/research/` etc.

### ADR-7 Four-tier consolidation model (working/episodic/semantic/procedural)

**Context.** The original Karpathy LLM Wiki has flat raw + wiki. LLM Wiki v2 introduces consolidation tiers: working → episodic → semantic → procedural, each more compressed and confident than the previous.

**Decision.** Lyra adopts the four-tier model. Path tells tier. Promotion is one-directional, evidence-driven. V1 implements working (raw flat) + episodic (wiki/sessions, minimal compression) + semantic (wiki/sources/concepts/connections/synthesis). Procedural (wiki/procedures/) is reserved for M2+ extraction.

**Consequences.** A page's storage location is informative (no need for explicit `tier:` field). Agents can reason about confidence by tier. Future M4 retention can apply different decay curves per tier.

### ADR-8 Explicit supersession primary; retention decay secondary

**Context.** From the gist comment thread (Mattia83it):
> Forgetting curves applied to errors and superseded decisions are how you repeat the same mistake. Old doesn't mean stale. A bug logged six months ago is often more valuable than one from last week, because it's the one you're about to forget. The right primitive is **explicit supersession**, not decay. Nothing disappears; future readers know in three seconds what is live and what is history. Git becomes the natural audit trail.

**Decision.** V1 implements **explicit supersession only** (`supersedes`, `superseded_by`, `contradicts` frontmatter). Retention decay is **deferred to M4** and SHALL be opt-in when introduced. Old pages are kept with explicit pointers to their replacements.

**Consequences.** No silent fading of knowledge. Git history is the audit trail. Errors and bug fixes from months ago remain visible and retrievable — they are the ones the user is about to forget.

### ADR-9 Entity extraction strategy: agent-host LLM (preferred) + LiteLLM fallback; mode implicit from CLI flags

**Context.** Karpathy Wiki V2 and `agentmemory` both perform LLM-driven entity extraction at compile/ingest time. `agentmemory` runs an always-on REST server (port 3111) that owns the LLM, called from session lifecycle hooks. Lyra cannot follow that pattern verbatim because **NFR7** forbids an always-on memory server in V1 and **NFR1** forbids requiring proprietary API keys for core functionality. We also want **full provider compatibility, including GitHub Copilot**, for the standalone path.

**Decision.** Two complementary extraction paths, switched **implicitly by the form of the `lyra compile` invocation** — no env var, no global mode flag.

1. **Agent-host path (preferred when running inside an agent session).** The Lyra skill (`skills/lyra/SKILL.md`, installed by `lyra install`) instructs the agent: when raw pages are pending (surfaced in the brief, after `lyra ingest`, or on user request), read each raw page, extract entities with the agent's own LLM using the documented prompt template, and apply via `lyra compile --raw-id <id> --entities '<json>'`. The CLI sub-form `--entities '<json>'` **bypasses any LLM call** — it applies the supplied entities deterministically (kind dispatch, frontmatter, graph edges, supersession). This is the signal "skip LLM, entities pre-extracted."
2. **LiteLLM path (standalone fallback for cron, CI, and outside-session manual use).** `lyra compile` (no `--entities`) uses LiteLLM under the hood with the provider configured in `~/lyra/config.yaml: extraction.llm = {provider, model, ...}`. LiteLLM unifies OpenAI, Anthropic, Ollama, **GitHub Copilot**, Azure OpenAI, Bedrock, Vertex AI, Groq, Mistral, Cohere, etc. — single dependency, ~100 providers, idiomatic Python.
3. **Heuristic baseline (always on).** Inline `entity::<type> <name>` annotations, `[[wikilinks]]` resolution to entity pages, frontmatter `entities: [...]`, regex patterns for file paths and Python/JS imports run regardless of provider. Guarantees minimum entity coverage even with no LLM available.

The CLI is auto-explanatory: `lyra compile` (batch) uses LiteLLM-or-heuristic; `lyra compile --raw-id <id> --entities '<json>'` is a deterministic single-page primitive used by the agent. **Mode resolution is a property of the command, not a runtime flag.**

**Consequences.** Inside an agent session the user never sets up API keys, never configures a provider; the host LLM (Claude / Copilot / Cursor / etc.) does the work via skill orchestration. Outside the session, LiteLLM provides full provider compatibility through a single dependency. NFR1 and NFR7 are honoured. Tests can exercise the deterministic path (`--entities`) without any LLM mocking. The skill becomes the single source of truth for the in-session prompt template.

### ADR-10 Multi-hop graph traversal: BFS depth=2 default, RRF fusion (k=60) of BM25 + vector + graph

**Context.** M1 hybrid retrieval combines BM25 + vector + **one-hop** graph extension. Karpathy Wiki V2 explicitly recommends multi-hop traversal: _"Start at the Redis node, walk outward through 'depends on' and 'uses' edges, find everything downstream"_. `agentmemory` ships **BFS traversal** triggered when entities are detected in the query, with **Reciprocal Rank Fusion (RRF, k=60)** combining the three retrieval streams. `agentmemory` reports 95.2% on LongMemEval-S using this fusion pattern.

**Decision.** V1 (post-M3) replaces the one-hop graph extension with a configurable **BFS traversal via SQLite recursive CTE**:

- `traverse(start_ids, max_hops, edge_types)` in `graph_projection.py`.
- Default `max_hops = 2`, configurable via `~/lyra/config.yaml: query.max_hops`, capped at `4`.
- Edge-type filter excludes `contradicts` and `superseded_by` from BFS expansion (those describe history, not navigation).
- Per-query result-size cap to prevent expansion explosion on dense graphs.
- `lyra query` exposes `--max-hops N` for ad-hoc tuning.

Final ranking uses **Reciprocal Rank Fusion with `k=60`**, combining the BM25, vector, and graph-traversal streams. RRF is parameter-light, robust to different score scales, and matches the agentmemory result-quality benchmark.

**Consequences.** Two-hop traversal captures the dominant association pattern in personal knowledge graphs ("page → entity → other-page-mentioning-same-entity") without the noise of three-plus hops on small graphs. Recursive CTE keeps the projection in SQLite (no new dependency). RRF fusion replaces ad-hoc score addition and is documented as the merge primitive for any future stream addition.

### ADR-11 Auto-supersession via weighted score on contradiction; threshold-gated; both pages preserved

**Context.** ADR-8 establishes explicit supersession as the primary lifecycle primitive (no decay). Karpathy Wiki V2 takes this further: _"The LLM should propose which claim is more likely correct based on **source recency, source authority, and the number of supporting observations**. The human can override, but the default behavior should usually be right."_ Without an automatic resolution rule, contradictions linger in lint reports and the wiki accumulates unresolved tension.

**Decision.** At compile time, when `A contradicts:: B` (or vice versa) and neither side has an existing `supersedes` / `superseded_by` link to the other, score both pages:

```
score(p) = w_r · recency(p) + w_a · authority(p) + w_s · support(p)

defaults:  w_r = 0.5    w_a = 0.3    w_s = 0.2
           threshold τ = 0.2
```

- `recency(p)`: normalised `last_confirmed` timestamp (more recent = higher).
- `authority(p)`: function of cited `sources:` count + `quality: high|medium|low` weight.
- `support(p)`: count of inbound `supports::` edges in the graph projection.

Decision rule:

- If `|score(A) − score(B)| ≥ τ`: auto-set `winner.supersedes = [loser.id]` and `loser.superseded_by = winner.id`. Emit a decision-log entry containing the score breakdown.
- If `|score(A) − score(B)| < τ`: leave the contradiction unresolved; `lyra lint` surfaces it as **needs human resolution** with the score breakdown attached.

**Both pages are always preserved**, consistent with ADR-8. Auto-supersession edits frontmatter, never deletes content. Weights and threshold are configurable via `~/lyra/config.yaml: auto_supersession = {enabled, weights, threshold}`. Default is `enabled: true` because the design.md goal explicitly mandates "auto-supersession via contradiction detection at compile time" (M3 vertical).

**Consequences.** Most contradictions resolve without human intervention; only genuinely ambiguous ones (close score) reach lint. The score breakdown makes every auto-decision auditable. Conservative threshold (`0.2`) prefers human review over silent overwrite when signals disagree. Numeric weights are tunable but exposed only via config — they are not "false-precision confidence floats on individual claims" (the gist's critique), they are a **resolution heuristic**, applied once per contradiction and logged.

## Error Handling

- Missing or unwritable vault path: fail fast during install and runtime discovery.
- Hook payload gaps: emit diagnosable errors without corrupting vault state.
- Stale or missing query indexes: rebuild before serving results.
- Compilation conflict: preserve canonical page, append conflict/log note, and surface diagnostic output.
- SessionStart summary over budget: degrade gracefully by truncating lower-priority sections.

## Security Considerations

- Raw capture should avoid storing secrets unnecessarily and should preserve user control over what is promoted.
- The canonical vault may be shared through git, so promotion policy must remain conservative.
- Internal runtime details should not be exposed in the public Lyra brief unless needed for diagnostics.

## Failure Modes And Tradeoffs

- Failure mode: Derived indexes become stale.
- Mitigation: Rebuild on demand and treat indexes as disposable.
- Tradeoff: Slight query latency on rebuild is accepted to preserve a markdown-first canonical model.

- Failure mode: The public interface drifts and starts exposing internals.
- Mitigation: Keep Lyra commands minimal and route internal retrieval details behind them.
- Tradeoff: Some debugging becomes indirect, but agent-facing simplicity improves.

- Failure mode: The design duplicates too much of agentmemory.
- Mitigation: Reuse only the patterns that support a markdown-first source of truth and avoid rebuilding a general-purpose memory runtime prematurely.
- Tradeoff: V1 may have fewer runtime features than agentmemory, but the product boundary stays coherent.

## Testing Strategy

- Unit tests for hook payload normalization, vault path resolution, and relation parsing.
- Integration tests for compile/query/lint/status flows over a sample vault.
- End-to-end checks for OpenCode hook to Lyra workflow to vault update.
- Retrieval checks proving that derived indexes rebuild correctly from markdown-only source data.

## Delivery Verticals

V1 ships as a single fat vertical (M1) that proves the orchestrator end-to-end on the canonical Karpathy Wiki V2 source. M2-M5 layer additional capabilities. Source pluggability is a stated architectural goal from M1; it is exercised by the canonical source so M2 can add more without rework.

### M1 — Lyra spine + Karpathy Wiki V2 canonical source + agentic feedback loop

Goal: from a fresh repo, the user runs `lyra init`, ingests material, captures a session, and the next agent boot reads a brief that includes recent activity and relevant pages from the wiki. End-to-end loop closed on one source.

Sub-deliverables:

- `M1.1` — `lyra init <vault>` bootstraps `~/lyra/config.yaml` and the `vault/raw/` + `vault/wiki/{sessions,sources,concepts,connections,procedures,synthesis,qa,meta}` layout, additive over pre-existing vaults.
- `M1.2` — `lyra ingest <path|url>` writes raw research/clips into **flat** `vault/raw/` with `kind:` frontmatter (per ADR-6).
- `M1.3` — Session export: OpenCode adapter reads sessions from `~/.local/share/opencode/opencode.db` (filesystem-based, post-hoc); Claude Code adapter consumes the `SessionStart` hook for live capture. Both write into flat `vault/raw/` with `kind: session` (per ADR-6).
- `M1.4` — `lyra compile` reads flat `raw/*.md`, dispatches by `kind:` (research|clip → `wiki/sources/`, session → `wiki/sessions/` for episodic compression), and writes frontmatter: `id` (ULID), `type`, `scope`, `quality`, `sources`, `confidence`, `created`, `last_confirmed`, `last_consolidated`, `supersedes`, `superseded_by`, `contradicts`, `relations` (typed).
- `M1.5` — Typed relation parser: extracts `relations:` frontmatter and inline `supports::` / `contradicts::` / `uses::` / `supersedes::` annotations.
- `M1.6` — Index: qmd builds BM25/FTS5 + vector indexes over wiki content; SQLite graph projection materialises `(src, type, dst, confidence)` edges from typed relations. All rebuildable from vault.
- `M1.7` — `lyra query <q>` runs hybrid retrieval (BM25 + vector + one-hop graph) over both built-in sources (wiki + tasks) with citations and per-claim confidence.
- `M1.8` — `lyra brief` emits a token-budgeted SessionStart preamble (default-ON, ≤4 KB, items as IDs + ≤400ch top-3 / ≤120ch tail per ADR-5): active tasks (from `ObsidianTasksSource`), recent episodic sessions, top semantic pages, recent compile log, Lyra usage hint.
- `M1.9` — Feedback loop delivery: the canonical `vault/wiki/AGENTS.md` schema document is deployed when absent (per `R14`); single Lyra skill `skills/lyra/SKILL.md` plus `lyra install --hook --skill --scope=user|project` distribute hook + skill; Claude Code `SessionStart` hook prepends the brief automatically (default-ON).
- `M1.10` — `lyra status` (vault and index health) and `lyra lint` (orphans, broken supersessions, dangling relations, missing required frontmatter, contradictions without explicit supersession).
- `M1.11` — `ObsidianTasksSource` plugin (per `R13`): second built-in source over `<vault>/Tasks/*.md`, separate qmd collection `lyra-tasks`, fan-out integrated into `lyra query` and `lyra brief`. Validates the Source contract on a real second source.
- `M1.12` — `lyra file` Q&A filing workflow (per `R17`): create `wiki/qa/<ulid>-<slug>.md` from a question + answer + source page IDs.

Source plane scope in M1: two built-in sources — `KarpathyWikiSource` (canonical) and `ObsidianTasksSource` (operational state, read-only). The plugin contract is defined and exercised by both.

### M2 — Pluggable external sources (read-only)

Goal: plug `agentmemory` and/or `mcp-memory-service` as additional read-only sources. `lyra source add/list/remove/refresh`. Cross-source query fan-out with merged citations and per-source health surfaced by `lyra status`.

### M3 — Entity extraction + richer graph traversal

Goal: extract entities (people, projects, libraries, concepts, files, decisions) at compile time; multi-hop graph queries; auto-supersession via contradiction detection at compile time.

### M4 — Lifecycle: confidence decay, retention, scheduled lint

Goal: time-decay confidence, periodic retention pass, scheduled lint and consolidation jobs, basic conflict resolution.

### M5 — Sinks (write-back) and team promotion via git

Goal: implement the inverse plugin contract so Lyra can write into selected external sources; team promotion via vault git branch + PR + optional mesh sync.

## Verification Plan

- Requirement proof: Demonstrate raw capture into `raw/`, compilation into `wiki/`, and Lyra-mediated query/startup workflows over the same vault.
- Test evidence: Targeted tests for hook capture, compilation promotion, query citations, and startup brief generation.
- Operational evidence: Script outputs from `compile`, `lint`, `status`, and query rebuild behavior showing that derived indexes can be recreated from the vault.

## Requirement Coverage

| Requirement | Covered By |
| --- | --- |
| `R1` | `Canonical Vault` layout and install flow |
| `R2` | `Installer And Runtime Discovery` in `Lyra Public Interface` + install flow |
| `R2A` | `Lyra Public Interface` |
| `R3` | `OpenCode Hook Adapter` + raw session artifacts |
| `R4` | `Lyra Public Interface` + `Derived Retrieval Layer` startup brief |
| `R5` | `Lyra Public Interface` over `Derived Retrieval Layer` |
| `R6` | `Canonical Vault` + compilation pipeline |
| `R7` | Raw research/clip ingestion into the canonical vault |
| `R8` | `OpenCode Hook Adapter` |
| `R9` | `Derived Retrieval Layer` + lint/query flows |
| `R10` | `Source Plugin Contract` + `Lyra Public Interface` cross-source orchestration |
| `R11` | `Derived Retrieval Layer` (BM25/FTS5 + vector via qmd, SQLite graph projection) + cross-reference model |
| `R0` | `Memory Layers` section + ADR-6, ADR-7 |
| `R12` | `Lyra Skill (single, progressive discovery)` component |
| `R13` | `Obsidian Tasks Source` component |
| `R14` | `Schema Document` component |
| `R15` | `Cross-reference Model` page frontmatter spec |
| `R16` | `Cross-reference Model` `scope:` field + ADR-4 |
| `R17` | `Schema Document` Q&A conventions + `M1.12` |
| `NFR1` | No dependency on agentmemory/iii as canonical runtime + ADR-2 |
| `NFR2` | Markdown canonical store in vault |
| `NFR3` | Compact SessionStart brief design + ADR-5 |
| `NFR4` | Local-first compile/query/lint flow |
| `NFR5` | Scripted command surface on supported platforms |
| `NFR6` | Lyra hides internal retrieval details |
| `NFR7` | ADR-1 (no always-on MCP V1) + `Lyra Skill` component |
