# Contributing to Lyra

## Quick start

```bash
git clone https://github.com/irizzante/lyra-memory
cd lyra-memory
uv pip install -e ".[dev]"
pytest -q
```

## Development principles

- **No breaking changes to the vault layout** without an ADR. The `raw/` flat structure (ADR-6) and wiki tier paths (ADR-7) are stable contracts.
- **No LLM API keys required** for core features (NFR4). Query, index, brief, and lint all run fully local.
- **Idempotency matters.** `init`, `ingest`, `compile`, `session`, and `index` must all be safe to run multiple times.
- **Tests before merge.** Every new feature ships with pytest coverage. Mocked subprocess tests are preferred for qmd integration; use `unittest.mock.patch` rather than skipping.

## Project layout

```
src/lyra/
  cli.py              # public CLI entry point
  vault.py            # layout enforcement (ADR-6)
  ingest.py           # raw/ record creation
  compile_pipeline.py # raw → wiki promotion
  brief.py            # SessionStart preamble (ADR-5)
  lint.py             # structural health checks
  file_cmd.py         # Q&A filing
  install.py          # hook + skill installation
  session/
    opencode.py       # OpenCode DB → raw/ export
  sources/
    obsidian_tasks.py # Tasks/*.md read-only source
  index/
    qmd_index.py      # qmd BM25/vector wrapper
    graph_projection.py
  query.py            # hybrid retrieval
  markdown.py         # YAML-frontmatter I/O
  ids.py              # ULID helpers
  templates/          # bundled AGENTS.md, SKILL.md, session-start.mjs
```

## Running tests

```bash
pytest -q                    # all tests
pytest tests/test_ingest.py  # single file
```

## Submitting changes

1. Open an issue describing the change (bug or feature).
2. Fork, branch from `main`, implement with tests.
3. Run `pytest -q` and `ruff check src/ tests/` locally.
4. Open a PR — the CI workflow runs automatically.

## Reporting bugs

Use [GitHub Issues](https://github.com/irizzante/lyra-memory/issues). Include:
- Lyra version (`lyra --version`)
- OS and Python version
- Steps to reproduce
- Expected vs. actual behaviour
