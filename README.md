# Lyra

[![CI](https://github.com/irizzante/lyra/actions/workflows/ci.yml/badge.svg)](https://github.com/irizzante/lyra/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**Local-first, vendor-agnostic memory orchestrator for AI coding agents.**

Lyra turns your Obsidian vault into a queryable long-term memory for any AI coding
agent (Claude Code, OpenCode, Cursor, etc.). Sessions, research notes, decisions,
and contradictions are captured into flat markdown, compiled into a tiered wiki with
explicit supersession, and served back through hybrid search (BM25 + vector +
typed-relation graph) on the next session start.

Inspired by Andrej Karpathy's [LLM Wiki idea](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f),
Rohit Ghumare's [LLM Wiki v2](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2)
extension, and [agentmemory](https://github.com/rohitg00/agentmemory)'s runtime patterns.

> **Status: v0.1.0 (Beta).** Milestones M1 + M2 + M3 complete. 315 tests passing.
> Public API is stable but minor breaking changes may still occur before v1.0.
> See [CHANGELOG.md](CHANGELOG.md) and the ADRs in
> [`.walden/specs/opencode-karpathy-wiki/design.md`](.walden/specs/opencode-karpathy-wiki/design.md).

---

## Why Lyra

Coding agents are amnesic between sessions. Existing solutions either:

- **Push to a vendor cloud** (vendor lock-in, privacy concerns, opaque retrieval).
- **Bolt on an MCP server** (adds a process to manage, fragments knowledge across
  tools, hides the data in a SQLite blob).

Lyra takes the opposite stance:

- **Data is plain markdown** in your Obsidian vault + git repo. You can read it,
  edit it, diff it, branch it, share it.
- **No daemon, no server.** Just a CLI (`lyra`), a SessionStart hook, and a single
  installable skill. The agent's host LLM does the smart work; Lyra orchestrates.
- **Explicit supersession over silent decay** (ADR-8). Old decisions don't fade —
  they get explicit `superseded_by` pointers. Git is the audit trail.
- **Hybrid retrieval out of the box.** BM25/FTS5 + vector + typed-relation graph,
  fused with Reciprocal Rank Fusion (RRF, k=60). Multi-hop BFS traversal via SQLite
  recursive CTE.

---

## Installation

### Prerequisite — `qmd` CLI (hybrid search backend)

Lyra's hybrid index delegates BM25/FTS5 + vector search to
[**qmd**](https://github.com/tobi/qmd), a small Node-based CLI. Install it once
globally:

```bash
npm install -g @tobilu/qmd
qmd --version    # should print 2.1.0 or later
```

### From source (recommended for v0.1.0)

```bash
git clone https://github.com/irizzante/lyra.git
cd lyra
uv sync                       # creates .venv, installs runtime deps
uv pip install -e ".[dev]"    # add dev deps (pytest, ruff)
uv run lyra --version
```

### From PyPI (coming soon)

```bash
pip install lyra-memory
```

> Package name on PyPI is `lyra-memory`; the CLI command is `lyra`.

### Optional: entity extraction with LiteLLM

For batch entity extraction outside a session (cron, CI, manual recompile):

```bash
uv pip install -e ".[extraction]"
```

Lyra always prefers the **agent-host LLM** when running inside a session
(deterministic, no extra API key needed). LiteLLM is the standalone fallback
(ADR-9).

---

## Quick start

### 1. Initialize a vault

```bash
uv run lyra init ~/Obsidian/Lyra
```

This creates:

- `~/Obsidian/Lyra/raw/` — flat working memory (ADR-6).
- `~/Obsidian/Lyra/wiki/{sources,concepts,connections,synthesis,sessions,qa,procedures}/`
  — tiered semantic memory (ADR-7).
- `~/Obsidian/Lyra/wiki/AGENTS.md` — the schema contract agents read on startup.
- `~/lyra/config.yaml` — runtime config (vault path, sources, auto-supersession
  weights, query parameters).

### 2. Install the agent integration

```bash
uv run lyra install --hook --skill        # user scope (~/.claude/)
uv run lyra install --hook --skill --scope project   # project scope (./.claude/)
```

This copies:

- `~/.claude/hooks/lyra/session-start.mjs` — emits the `lyra brief` preamble on
  every new session (≤4 KB, default-ON, ADR-5).
- `~/.claude/hooks/lyra/session-end.mjs` — runs `lyra compile` at session end so
  the next session sees the latest raw → wiki promotion.
- `~/.claude/skills/lyra/SKILL.md` — the skill that teaches the agent how to use
  `lyra query`, `lyra file`, and the entity-extraction workflow.
- `~/.claude/settings.json` — patched (idempotently) to wire both hooks.

### 3. Use it

Inside any coding agent (Claude Code, OpenCode, etc.):

```bash
# Capture a research clip
uv run lyra ingest --kind research --title "RRF k=60 in agentmemory" \
  --source https://example.com/paper

# Promote raw → wiki (creates ULID, supersession, typed relations)
uv run lyra compile

# Query hybrid index with citations
uv run lyra query "what did we decide about supersession?"

# Q&A filing — answer + persist to wiki/qa/<ulid>-<slug>.md
uv run lyra file "How does auto-supersession score contradictions?"

# Health check
uv run lyra status
uv run lyra lint
```

---

## CLI reference

| Command | Purpose |
|---|---|
| `lyra init <vault>` | Bootstrap config + vault layout |
| `lyra status` | Vault + index + source health |
| `lyra ingest` | Capture raw research/clip into `raw/` |
| `lyra session` | Export OpenCode sessions from SQLite into `raw/` |
| `lyra compile` | Promote `raw/` → `wiki/sources/` (idempotent) |
| `lyra compile --raw-id <id> --entities '<json>'` | Imperative single-page mode (bypass LLM) |
| `lyra index` | Rebuild BM25 + vector + graph projection |
| `lyra query <q>` | Hybrid retrieval with citations |
| `lyra brief` | SessionStart preamble (≤4 KB) |
| `lyra file <q>` | Q&A filing workflow |
| `lyra lint` | Structural health checks with score breakdown for contradictions |
| `lyra source list/add/remove/refresh` | Manage external sources |
| `lyra install --hook --skill` | Deploy hooks + skill to Claude Code |

Run `lyra <command> --help` for full flags.

---

## Skill distribution (Claude Code)

Lyra ships its **agent skill** as a packaged template inside the Python wheel.
`lyra install` copies it into the Claude Code scope you choose:

```
~/.claude/                              (user scope, --scope user, default)
├── hooks/lyra/
│   ├── session-start.mjs              → emits `lyra brief` preamble
│   └── session-end.mjs                → runs `lyra compile`
├── skills/lyra/
│   └── SKILL.md                       → progressive-discovery skill
└── settings.json                       (patched to wire hooks)
```

The skill teaches the agent to:

1. Read the `lyra brief` preamble at session start (active tasks, recent sessions,
   top semantic pages, lyra usage hint, **raw-pending count**).
2. Call `lyra query <q>` before answering knowledge questions, and **cite results
   by ULID** in its response.
3. When the brief shows `📋 N raw pages pending promotion`, **extract entities**
   from each pending raw page using the documented prompt template, then call
   `lyra compile --raw-id <id> --entities '<json>'` to promote it deterministically.

The skill is **progressive-discovery** (ADR-3): a single `SKILL.md` file the agent
reads once, no MCP server to manage.

---

## OpenCode integration

OpenCode stores sessions in a local SQLite database. Lyra reads them post-hoc:

```bash
# Export every OpenCode session not yet captured in raw/
uv run lyra session

# Override DB path if needed
uv run lyra session --db ~/.local/share/opencode/opencode.db
```

Default DB path: `~/.local/share/opencode/opencode.db`.

Exported sessions land in `raw/<ulid>-<slug>.md` with `kind: session` and
`source: opencode` frontmatter. The next `lyra compile` promotes promotable ones
into `wiki/sessions/`.

> Live SessionStart/SessionEnd integration with OpenCode hooks is on the
> roadmap once OpenCode exposes a stable hook spec.

---

## Architecture

Four-layer design (full detail in
[`.walden/specs/opencode-karpathy-wiki/design.md`](.walden/specs/opencode-karpathy-wiki/design.md)):

1. **Source plane** — uniform plugin contract (`query`, `list_recent`, `health`,
   `capabilities`). Adapters for `karpathy_wiki` (default), `obsidian_tasks`,
   `plain_markdown`, `agentmemory`, `mcp_memory`.
2. **Canonical vault** — `raw/` (flat working memory) + `wiki/` (tiered semantic
   memory: sources → concepts → connections → synthesis; sessions; procedures; qa).
   Frontmatter-typed; ULIDs are durable identity, never filenames.
3. **Promotion pipeline** — session capture (Claude Code hooks + OpenCode SQLite
   reader) → `lyra compile` (extraction, frontmatter, supersession, typed
   relations, auto-supersession scoring).
4. **Derived retrieval** — qmd (BM25/FTS5 + vector) + a SQLite graph projection of
   typed relations. Cross-source fan-out, multi-hop BFS, RRF fusion.

### Architecture Decision Records (ADRs)

All in [`design.md`](.walden/specs/opencode-karpathy-wiki/design.md):

| ADR | Decision |
|---|---|
| ADR-1 | No MCP server — CLI + hook + skill pattern |
| ADR-3 | Single SKILL.md with progressive discovery |
| ADR-5 | Brief default-ON, ≤4 KB, tiered items |
| ADR-6 | `raw/` flat; `wiki/` organized by tier |
| ADR-7 | 4-tier consolidation (working → episodic → semantic → procedural) |
| ADR-8 | Explicit supersession primary; retention decay deferred |
| ADR-9 | Agent-host LLM for extraction; LiteLLM fallback |
| ADR-10 | BFS depth=2 default; RRF fusion (k=60) |
| ADR-11 | Auto-supersession via weighted score; threshold-gated |

---

## Delivery roadmap

| Milestone | Scope | Status |
|---|---|---|
| **M1** | Orchestrator spine + Karpathy Wiki V2 canonical source + agentic feedback loop | ✅ shipped in v0.1.0 |
| **M2** | Pluggable external sources (read-only): plain markdown, agentmemory, mcp-memory-service | ✅ shipped in v0.1.0 |
| **M3** | Entity extraction + multi-hop graph traversal + auto-supersession | ✅ shipped in v0.1.0 |
| **M4** | Confidence decay (opt-in), retention, scheduled lint, conflict resolution | planned |
| **M5** | Sinks (write-back) + team promotion via git branch + PR + optional mesh sync | planned |

---

## Project layout

```
src/lyra/
  cli.py              # public CLI entry point
  vault.py            # layout enforcement (ADR-6)
  ingest.py           # raw/ record creation
  compile_pipeline.py # raw → wiki promotion + auto-supersession (ADR-11)
  brief.py            # SessionStart preamble (ADR-5)
  lint.py             # structural health checks with score breakdown
  file_cmd.py         # Q&A filing
  install.py          # hook + skill installation
  query.py            # hybrid retrieval (BM25 + vector + multi-hop graph + RRF)
  relations.py        # typed relation parser
  session/
    opencode.py       # OpenCode DB → raw/ export
  sources/
    base.py           # Source protocol (ADR-3 source plane)
    obsidian_tasks.py
    plain_markdown.py
    agentmemory.py
    mcp_memory.py
  index/
    qmd_index.py      # qmd BM25/vector wrapper
    graph_projection.py  # SQLite typed-relation graph + BFS traversal
  markdown.py         # YAML-frontmatter I/O
  ids.py              # ULID helpers
  templates/          # bundled AGENTS.md, SKILL.md, session-start.mjs, session-end.mjs

tests/                # 315 tests
.walden/specs/        # design.md, requirements.md, tasks.md (planning artifacts)
.github/workflows/    # ci.yml (pytest matrix 3.11/3.12 + ruff lint)
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Quick version:

```bash
uv pip install -e ".[dev]"
uv run pytest        # 315 tests
uv run ruff check src/ tests/
```

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

Bug reports and feature requests:
[GitHub Issues](https://github.com/irizzante/lyra/issues).

---

## License

[Apache-2.0](LICENSE).
