# Wiki Runtime Instructions

This vault is the canonical knowledge store managed by [Lyra](https://github.com/irizzante/lyra).
Read this file before you do anything else in this session.

---

## On session start

As the **first action** of every session, run:

```bash
lyra brief --project <project-id>
```

This returns a token-budgeted preamble with recent activity, open threads, and the most relevant
pages for the current project. Read it before answering anything. Do not assume context from prior
sessions without this brief.

If a Claude Code `SessionStart` hook is installed, the brief is prepended automatically.

---

## Memory tiers and storage layout

| Tier | Path | Lifecycle |
|------|------|-----------|
| **Working** | `raw/<ulid>-<slug>.md` (flat) + `raw/assets/` (binaries only) | Append-only, immutable post-ingest |
| **Episodic** | `wiki/sessions/<ulid>-<slug>.md` | Promoted by `lyra compile` from `kind: session` raws |
| **Semantic** | `wiki/sources/`, `wiki/concepts/`, `wiki/connections/`, `wiki/synthesis/` | Promoted and refined by `lyra compile` + manual edits |
| **Procedural** | `wiki/procedures/` | Reserved for M2+ extraction |
| **Q&A** | `wiki/qa/` | Filed back via `lyra file` |
| **Meta** | `wiki/meta/`, `wiki/AGENTS.md` | Schema, lint reports |

**Rule:** `raw/` is flat. The only sub-directory is `raw/assets/` for binary files. `kind:` frontmatter
discriminates record type, not the file path.

---

## Entity types

Every wiki page has a `type:` frontmatter field drawn from this taxonomy:

| Type | Storage tier | When to use |
|------|--------------|-------------|
| `source` | `wiki/sources/` | A single external source promoted from raw (paper, doc, URL, clip) |
| `concept` | `wiki/concepts/` | A cross-source abstracted idea or definition |
| `connection` | `wiki/connections/` | A relationship or pattern linking two or more concepts |
| `synthesis` | `wiki/synthesis/` | Convergent insight from multiple sources; highest confidence |
| `session` | `wiki/sessions/` | Compressed session summary promoted from `kind: session` raw |
| `procedure` | `wiki/procedures/` | Extracted workflow or recipe (M2+) |
| `qa` | `wiki/qa/` | Filed answer from `lyra query` / `lyra file` |
| `meta` | `wiki/meta/` | Schema docs, lint reports, vault configuration notes |

---

## Frontmatter schema

### Raw records (`raw/*.md`)

```yaml
raw_id: <ULID>               # canonical identity
kind: research | clip | session
source: <local path or URL>
ingested_at: <ISO 8601>
content_type: <mime>
title: <derived or supplied>
asset: raw/assets/<name>     # only for binary wrappers
```

### Wiki pages (`wiki/**/*.md`)

```yaml
id: <ULID>                   # durable canonical identity; never changes
title: <human title>
type: source | concept | connection | synthesis | session | procedure | qa | meta
sources: [<raw_id>, ...]     # raw records that contributed to this page
confidence: 0.0–1.0          # see confidence scale below
created: <ISO 8601 date>
last_confirmed: <ISO 8601 date>
supersedes: [<ULID>, ...]    # pages this page explicitly replaces
superseded_by: <ULID> | null # set when this page is superseded
contradicts: [<ULID>, ...]   # pages with conflicting claims (do not resolve silently)
relations:                   # typed graph edges
  - type: <relation-type>
    target_id: <ULID>        # resolved at compile time
    confidence: 0.0–1.0      # optional per-edge confidence
```

---

### Entity pages (`wiki/entities/<entity_type>/<ulid>-<slug>.md`)

Entity pages represent first-class named things extracted from sources (M3, ADR-9).

```yaml
id: <ULID>                     # durable canonical identity
type: entity
entity_type: person | project | library | concept | file | decision
title: <canonical name>
aliases: [<alternative name>, ...]
attributes: {<key>: <value>}   # arbitrary entity-specific attributes
created: <ISO 8601 date>
last_confirmed: <ISO 8601 date>
mentioned_by: [<source-page-ULID>, ...]  # source pages that reference this entity
supersedes: []
superseded_by: null
relations: []
```

Entity pages are created and updated automatically by `lyra compile` via entity extraction.
Do not create or edit entity pages manually; they are regenerated from raw annotations.

---

## Raw promotion workflow (M3, ADR-9)

When `lyra brief` shows **N raw pages pending promotion**, use this workflow to promote them
with the full power of the agent's own LLM:

1. **Read** the raw page body.
2. **Extract entities** using the prompt template below.
3. **Apply** with `lyra compile --raw-id <id> --entities '<json>'`.

### Entity extraction prompt template

```
Extract entities from the following text.

Return ONLY a JSON list (no prose) where each item has:
  - "entity_type": one of concept, decision, file, library, person, project
  - "name": canonical name
  - "aliases": list of alternate names (may be empty)
  - "attributes": dict of extra attributes (may be empty)

Text:
<paste raw page body>
```

### Entity JSON schema example

```json
[
  {"entity_type": "library",  "name": "litellm",         "aliases": ["LiteLLM"],  "attributes": {}},
  {"entity_type": "person",   "name": "Andrej Karpathy", "aliases": ["Karpathy"], "attributes": {}},
  {"entity_type": "project",  "name": "nanoGPT",         "aliases": [],           "attributes": {}},
  {"entity_type": "concept",  "name": "BM25",            "aliases": [],           "attributes": {"tier": "semantic"}},
  {"entity_type": "file",     "name": "src/lyra/cli.py", "aliases": [],           "attributes": {}},
  {"entity_type": "decision", "name": "ADR-9",           "aliases": [],           "attributes": {}}
]
```

### Inline annotation syntax (for future raw pages)

Annotate entities inline in the raw body for heuristic extraction:

```
entity::<type> <name>
```

Examples:
```
entity::library litellm
entity::person Andrej Karpathy
entity::project nanoGPT
```

---

## Relation taxonomy

Use inline annotations in raw body or the `relations:` frontmatter list:

| Type | Meaning | Inline syntax |
|------|---------|---------------|
| `supports` | This page provides evidence for the target | `supports:: [[Target]]` |
| `contradicts` | This page conflicts with the target | `contradicts:: [[Target]]` |
| `uses` | This page applies or extends the target | `uses:: [[Target]]` |
| `supersedes` | This page replaces the target (target becomes stale) | `supersedes:: [[Target]]` |
| `depends_on` | This page requires the target to hold | `depends_on:: [[Target]]` |
| `caused` | This page describes a cause of the target event | `caused:: [[Target]]` |
| `fixed` | This page resolves an issue described by the target | `fixed:: [[Target]]` |

Inline annotations are parsed from the body at compile time and merged into `relations:`.
Use `[[Page Title]]` or a bare ULID as target.

---

## Confidence scale

| Value | Meaning |
|-------|---------|
| 0.9–1.0 | Verified, multi-source, no known contradictions |
| 0.7–0.89 | Single reliable source, no active contradictions |
| 0.5 | Default for freshly promoted sources (unreviewed) |
| 0.3–0.49 | Conflicting evidence present; treat as hypothesis |
| 0.0–0.29 | Speculative; requires confirmation before acting |

---

## Supersession and contradiction protocol (ADR-8)

**Explicit supersession is the primary staleness primitive.** Age alone does not make a page stale.

- When a new page replaces an old one: set `supersedes: [<old-id>]` on the new page and
  `superseded_by: <new-id>` on the old page.
- When two pages conflict without resolution: add `contradicts: [<other-id>]` on both.
  Do **not** silently delete or overwrite either page.
- `lyra lint` surfaces pages with unresolved `contradicts` edges as open issues.
- Decay-based retention is deferred to M4 and is opt-in only.

---

## Ingest rules

When to use each `kind`:

| Situation | Command |
|-----------|---------|
| External paper, doc, or reference URL | `lyra ingest <url> --as research` |
| Short clip, quote, or bookmark | `lyra ingest <url-or-path> --as clip` |
| Session artifact / conversation dump | `lyra ingest <path> --as session` |

**What belongs in the wiki:** facts, decisions, patterns, and references that inform future sessions.  
**What does not belong:** ephemeral state, one-off commands, transient debugging output.

---

## Q&A conventions

Filed answers live in `wiki/qa/` with `type: qa`.

```bash
lyra query "<question>"          # query + print answer
lyra file "<question>"           # query + file answer back to wiki/qa/
```

Filed Q&A pages carry a `sources:` list pointing to the wiki pages that supported the answer,
enabling graph traversal back to the original evidence.

---

## Authoring rules for agents

- **Do not write directly to `wiki/`.** The wiki is generated by `lyra compile` from `raw/`.
  Direct edits may be overwritten or flagged as drift by `lyra lint`.
- **Do not create `raw/` subdirectories.** Only `raw/assets/` is a valid subdir.
- **Do not assume the vault is in the current directory.** Lyra resolves it from `~/lyra/config.yaml`.
- **Do not paste long context dumps** when `lyra brief` provides a token-budgeted summary.
- **Do not invoke `qmd` or SQLite graph queries directly.** The CLI surface is the public contract.
- **Do not silently merge conflicting pages.** Use `contradicts:` and let `lyra lint` surface them.
