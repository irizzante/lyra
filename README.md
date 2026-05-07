# Lyra

Local-first, vendor-agnostic memory orchestrator for AI coding agents.

Lyra operates over one or more memory **sources** through a uniform plugin contract. The bundled `Karpathy Wiki V2` is the canonical default source: a markdown-first knowledge store you keep in an Obsidian vault and a git repo. External sources (agentmemory, mcp-memory-service, plain markdown trees, MCP memory servers) plug in as additional read-paths in later milestones. Sinks — the inverse contract that lets Lyra write back into external sources — are deferred.

Inspired by Andrej Karpathy's [LLM Wiki idea](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), Rohit Ghumare's [LLM Wiki v2](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) extension, and [agentmemory](https://github.com/rohitg00/agentmemory)'s runtime patterns.

> Status: pre-alpha. M1 scaffolding only. Specs live under `.walden/specs/opencode-karpathy-wiki/`.

## Quick start

```bash
uv sync
uv run lyra init ~/Obsidian/Lyra
uv run lyra status
```

`lyra init <vault>` creates the `<vault>/raw/` and `<vault>/wiki/` layout, writes `~/lyra/config.yaml`, and deploys an `AGENTS.md` template that tells your agent to call `lyra brief` on every session start.

## Architecture

Four-layer design (see `.walden/specs/opencode-karpathy-wiki/design.md`):

1. **Source plane** — uniform plugin contract over one or more memory sources.
2. **Canonical vault** — the bundled Karpathy Wiki V2 source; `raw/` and `wiki/` markdown.
3. **Promotion pipeline** — session capture (Claude Code SessionStart hook + OpenCode SQLite reader), raw → wiki compilation with confidence, supersession, and typed relations.
4. **Derived retrieval** — qmd (BM25/FTS5 + vector) + a SQLite graph projection of typed relations. Cross-source query fan-out with citations.

## Delivery roadmap

- **M1** — orchestrator spine + Karpathy Wiki V2 canonical source + agentic feedback loop (current).
- **M2** — pluggable external sources (read-only): agentmemory, mcp-memory-service.
- **M3** — entity extraction + multi-hop graph traversal + auto-supersession.
- **M4** — confidence decay, retention, scheduled lint.
- **M5** — sinks (write-back) + team promotion via git.

## License

Apache-2.0.
