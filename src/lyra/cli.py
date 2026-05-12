"""Lyra public CLI — ``lyra <subcommand>``.

The CLI is the public interface. Direct qmd invocation, graph SQL queries, and
source-specific APIs are internal and may change without notice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lyra import __version__
from lyra import config as cfg_mod
from lyra.compile_pipeline import compile_page, compile_vault
from lyra.ingest import ingest as do_ingest
from lyra.vault import ensure_layout

NOT_IMPLEMENTED_EXIT = 64


def _cmd_init(args: argparse.Namespace) -> int:
    vault_path = Path(args.vault).expanduser().resolve()
    layout = ensure_layout(vault_path)

    config = cfg_mod.Config.default(vault_path)
    cfg_mod.save(config, cfg_mod.CONFIG_PATH)

    print(f"vault: {vault_path}")
    print(f"config: {cfg_mod.CONFIG_PATH}")
    print(f"created: {len(layout['created'])} paths")
    print(f"skipped (already present): {len(layout['skipped'])} paths")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    from lyra.sources import load_all_sources

    print(f"lyra: {__version__}")
    print(f"config: {cfg_mod.CONFIG_PATH}")
    print(f"vault: {config.vault_path}")
    print("sources:")

    sources = load_all_sources(config)
    all_ok = True
    for name, src in sources:
        h = src.health()
        marker = "ok" if h.ok else "error"
        detail = ""
        if h.ok and h.detail:
            kv = next(iter(h.detail.items()), None)
            if kv:
                detail = f"  {kv[0]}={kv[1]}"
        print(f"  {name:<20} health={marker}{detail}")
        if not h.ok:
            print(f"    ! {h.message}", file=sys.stderr)
            all_ok = False

    raw_count = len(list((config.vault_path / "raw").glob("*.md"))) if (config.vault_path / "raw").exists() else 0
    wiki_count = sum(1 for _ in (config.vault_path / "wiki").rglob("*.md")) if (config.vault_path / "wiki").exists() else 0
    print(f"raw records: {raw_count}  wiki pages: {wiki_count}")

    return 0 if all_ok else 1


def _cmd_source_list(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    from lyra.sources import load_source

    if not config.sources:
        print("no sources configured")
        return 0

    for src_cfg in config.sources:
        enabled = "enabled" if src_cfg.enabled else "disabled"
        adapter = src_cfg.adapter or src_cfg.type
        try:
            src = load_source(src_cfg, vault_path=config.vault_path)
            h = src.health()
            health_str = "ok" if h.ok else f"error: {h.message}"
        except Exception as exc:
            health_str = f"load-error: {exc}"
        print(f"  {src_cfg.name:<20} [{enabled}]  adapter={adapter}  health={health_str}")
    return 0


def _cmd_source_add(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if any(s.name == args.name for s in config.sources):
        print(f"source {args.name!r} already exists. Remove it first.", file=sys.stderr)
        return 1

    options: dict = {}
    for kv in (args.config or []):
        if "=" not in kv:
            print(f"invalid --config entry {kv!r}: expected key=value", file=sys.stderr)
            return 1
        k, _, v = kv.partition("=")
        options[k.strip()] = v.strip()

    src_cfg = cfg_mod.SourceConfig(
        name=args.name,
        type=args.name,
        adapter=args.adapter,
        options=options,
        enabled=True,
    )
    config.sources.append(src_cfg)
    cfg_mod.save(config, cfg_mod.CONFIG_PATH)
    print(f"added source {args.name!r}  adapter={args.adapter}")
    return 0


def _cmd_source_remove(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    before = len(config.sources)
    config.sources = [s for s in config.sources if s.name != args.name]
    if len(config.sources) == before:
        print(f"source {args.name!r} not found", file=sys.stderr)
        return 1
    cfg_mod.save(config, cfg_mod.CONFIG_PATH)
    print(f"removed source {args.name!r}")
    return 0


def _cmd_source_refresh(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    from lyra.sources import load_source

    targets = [s for s in config.sources if not args.name or s.name == args.name]
    if not targets:
        print(f"source {args.name!r} not found", file=sys.stderr)
        return 1

    for src_cfg in targets:
        try:
            src = load_source(src_cfg, vault_path=config.vault_path)
            h = src.health()
            print(f"  {src_cfg.name}: health={'ok' if h.ok else 'error'}")
        except Exception as exc:
            print(f"  {src_cfg.name}: error — {exc}", file=sys.stderr)
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = do_ingest(
        args.target,
        vault_path=config.vault_path,
        kind=args.kind,
        title=args.title,
    )
    print(f"raw_id: {result.raw_id}")
    print(f"kind: {result.kind}")
    print(f"record: {result.record_path}")
    if result.asset_path:
        print(f"asset: {result.asset_path}")
    return 0


def _cmd_compile(args: argparse.Namespace) -> int:
    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    ext = config.extraction
    raw_id: str | None = getattr(args, "raw_id", None)
    entities_json: str | None = getattr(args, "entities", None)

    if raw_id:
        # M3.4 — imperative single-page mode
        try:
            report = compile_page(
                raw_id,
                config.vault_path,
                entities_json=entities_json,
                extraction_provider=ext.provider,
                extraction_model=ext.model,
                extraction_endpoint=ext.endpoint,
                extraction_extra=ext.extra or None,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        # Batch mode
        report = compile_vault(
            config.vault_path,
            extraction_provider=ext.provider,
            extraction_model=ext.model,
            extraction_endpoint=ext.endpoint,
            extraction_extra=ext.extra or None,
        )

    print(f"promoted: {len(report.promoted)}")
    print(f"updated:  {len(report.updated)}")
    print(f"skipped:  {len(report.skipped)}")
    print(f"entities: {report.entities_upserted}")
    print(f"errors:   {len(report.errors)}")
    for path, message in report.errors:
        print(f"  ! {path}: {message}", file=sys.stderr)
    return 0 if not report.errors else 1


def _cmd_index(args: argparse.Namespace) -> int:
    from lyra.index.qmd_index import QmdIndexConfig, build, health

    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    qmd_cfg = QmdIndexConfig(vault_path=config.vault_path)

    if args.health_only:
        h = health(qmd_cfg)
        for k, v in h.items():
            print(f"{k}: {v}")
        return 0 if h.get("index_exists") else 1

    try:
        build(qmd_cfg, embed=not args.no_embed)
        h = health(qmd_cfg)
        print(f"index: ok  collection={h['collection_name']}  files={h.get('file_count', '?')}")
        return 0
    except Exception as exc:
        print(f"index build failed: {exc}", file=sys.stderr)
        return 1


def _cmd_brief(args: argparse.Namespace) -> int:
    from lyra.brief import generate_brief

    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    brief = generate_brief(config.vault_path, char_budget=args.budget)
    print(brief)
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    from lyra.query import hybrid_query, format_results
    from lyra.index.qmd_index import QmdIndexConfig, build, health as qmd_health

    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    qmd_cfg = QmdIndexConfig(vault_path=config.vault_path)

    # Auto-rebuild if index absent or empty (R5.AC3)
    h = qmd_health(qmd_cfg)
    if not h.get("index_exists") or h.get("file_count", 0) == 0:
        print("index not found — rebuilding (pass --no-rebuild to skip)...", file=sys.stderr)
        try:
            build(qmd_cfg, embed=False)
        except Exception as exc:
            print(f"index build failed: {exc}", file=sys.stderr)
            return 1

    max_hops = args.max_hops if args.max_hops is not None else config.query.max_hops
    hits = hybrid_query(
        args.question,
        config.vault_path,
        k=args.top_k,
        use_vector=not args.bm25_only,
        max_hops=max_hops,
    )
    print(format_results(hits, show_snippet=args.snippets))
    return 0 if hits else 1


def _cmd_session(args: argparse.Namespace) -> int:
    from lyra.session.opencode import export_sessions, DEFAULT_OPENCODE_DB

    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    db_path = Path(args.db) if args.db else DEFAULT_OPENCODE_DB
    try:
        results = export_sessions(config.vault_path, db_path=db_path, limit=args.limit)
        print(f"exported: {len(results)}")
        for r in results:
            print(f"  {r.raw_id}  {r.record_path.name}")
        return 0
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _stub(name: str, milestone: str):
    def _run(args: argparse.Namespace) -> int:
        print(
            f"`lyra {name}` is not yet implemented (planned for {milestone}).",
            file=sys.stderr,
        )
        return NOT_IMPLEMENTED_EXIT

    return _run


def _cmd_file(args: argparse.Namespace) -> int:
    from lyra.file_cmd import file_answer

    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = file_answer(
        args.question,
        config.vault_path,
        k=args.top_k,
        use_vector=not args.bm25_only,
    )
    print(result.answer)
    print(f"\nfiled: {result.qa_path}  (id={result.qa_id})")
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    from lyra.lint import lint_vault

    try:
        config = cfg_mod.load(cfg_mod.CONFIG_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    report = lint_vault(config.vault_path, structural_only=args.structural_only)

    if report.ok:
        print("lint: ok — no issues found")
        return 0

    for issue in report.issues:
        print(f"[{issue.kind}] {issue.path.name}: {issue.message}")
        if issue.kind == "CONTRADICTION" and issue.detail.get("scores"):
            for pid, sc in issue.detail["scores"].items():
                print(
                    f"  {pid}: recency={sc['recency']:.3f}"
                    f" authority={sc['authority']:.3f}"
                    f" support={sc['support']:.3f}"
                    f" → total={sc['total']:.3f}"
                )
    print(f"\n{len(report.issues)} issue(s) found")
    return 1


def _cmd_install(args: argparse.Namespace) -> int:
    from lyra.install import install

    if not args.hook and not args.skill:
        print("specify at least one of --hook or --skill", file=sys.stderr)
        return 1

    report = install(
        hook=args.hook,
        skill=args.skill,
        scope=args.scope,
        no_inject=args.no_inject,
    )
    for p in report.copied:
        print(f"copied:  {p}")
    for p in report.patched:
        print(f"patched: {p}")
    for p in report.skipped:
        print(f"skipped: {p}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lyra",
        description="Local-first memory orchestrator for AI coding agents.",
    )
    parser.add_argument(
        "--version", action="version", version=f"lyra {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="bootstrap config and vault layout")
    p_init.add_argument("vault", help="absolute or relative path to the Obsidian vault")
    p_init.set_defaults(func=_cmd_init)

    p_status = sub.add_parser("status", help="report config, vault, and source health")
    p_status.set_defaults(func=_cmd_status)

    p_ingest = sub.add_parser("ingest", help="ingest a local file or URL into raw/")
    p_ingest.add_argument("target", help="local path or http(s) URL")
    p_ingest.add_argument(
        "--as",
        dest="kind",
        choices=["research", "clip"],
        default="research",
        help="raw record kind (default: research)",
    )
    p_ingest.add_argument("--title", default=None, help="override the derived title")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_compile = sub.add_parser(
        "compile", help="promote raw research/clips into wiki/sources/"
    )
    p_compile.add_argument(
        "--raw-id",
        dest="raw_id",
        default=None,
        metavar="ID",
        help="compile a single raw page by its raw_id (imperative mode, M3.4)",
    )
    p_compile.add_argument(
        "--entities",
        default=None,
        metavar="JSON",
        help="pre-extracted entities as JSON list; requires --raw-id; skips LLM call",
    )
    p_compile.set_defaults(func=_cmd_compile)

    p_index = sub.add_parser("index", help="build or refresh BM25/vector/graph indexes")
    p_index.add_argument("--rebuild", action="store_true", default=True, help="rebuild (default)")
    p_index.add_argument("--no-embed", action="store_true", help="skip vector embedding step")
    p_index.add_argument("--health", dest="health_only", action="store_true", help="report health only")
    p_index.set_defaults(func=_cmd_index)

    p_brief = sub.add_parser("brief", help="emit a token-budgeted SessionStart preamble")
    p_brief.add_argument(
        "--budget",
        type=int,
        default=4096,
        metavar="CHARS",
        help="character budget for the preamble (default: 4096)",
    )
    p_brief.set_defaults(func=_cmd_brief)

    p_file = sub.add_parser("file", help="query + file answer to wiki/qa/")
    p_file.add_argument("question", help="natural language question")
    p_file.add_argument("--top-k", type=int, default=5, metavar="K", help="top results (default: 5)")
    p_file.add_argument("--bm25-only", action="store_true", help="skip vector retrieval")
    p_file.set_defaults(func=_cmd_file)

    p_query = sub.add_parser("query", help="hybrid BM25/vector/graph search with citations")
    p_query.add_argument("question", help="natural language query")
    p_query.add_argument("--top-k", type=int, default=10, metavar="K", help="top results (default: 10)")
    p_query.add_argument("--bm25-only", action="store_true", help="skip vector retrieval")
    p_query.add_argument("--snippets", action="store_true", default=True, help="show text snippets")
    p_query.add_argument("--no-snippets", dest="snippets", action="store_false")
    p_query.add_argument(
        "--max-hops",
        type=int,
        default=None,
        metavar="N",
        help="graph BFS depth 1-4 (default: from config.yaml query.max_hops, 2)",
    )
    p_query.set_defaults(func=_cmd_query)

    p_session = sub.add_parser("session", help="export OpenCode sessions into raw/sessions/")
    p_session.add_argument("--db", default=None, metavar="PATH", help="override OpenCode DB path")
    p_session.add_argument("--limit", type=int, default=50, help="max sessions to export (default: 50)")
    p_session.set_defaults(func=_cmd_session)

    p_install = sub.add_parser("install", help="install hook and/or skill into Claude Code")
    p_install.add_argument("--hook", action="store_true", default=False, help="install SessionStart hook")
    p_install.add_argument("--skill", action="store_true", default=False, help="install SKILL.md")
    p_install.add_argument(
        "--scope",
        choices=["user", "project"],
        default="user",
        help="user (~/.claude/) or project (.claude/) scope (default: user)",
    )
    p_install.add_argument(
        "--no-inject",
        action="store_true",
        default=False,
        help="copy files without patching settings.json",
    )
    p_install.set_defaults(func=_cmd_install)

    p_lint = sub.add_parser("lint", help="structural health checks (orphans, supersessions, contradictions)")
    p_lint.add_argument(
        "--structural-only",
        action="store_true",
        default=False,
        help="skip dangling-relation checks (faster on large vaults)",
    )
    p_lint.set_defaults(func=_cmd_lint)

    p_source = sub.add_parser("source", help="manage pluggable read-only sources (M2)")
    source_sub = p_source.add_subparsers(dest="source_action", required=True)

    source_sub.add_parser("list", help="list configured sources with health").set_defaults(func=_cmd_source_list)

    p_add = source_sub.add_parser("add", help="register a new source")
    p_add.add_argument("name", help="unique source name")
    p_add.add_argument("--adapter", required=True, metavar="DOTTED.CLASS", help="dotted class path for the adapter")
    p_add.add_argument("--config", action="append", metavar="KEY=VAL", help="adapter config (repeatable)")
    p_add.set_defaults(func=_cmd_source_add)

    p_rm = source_sub.add_parser("remove", help="unregister a source")
    p_rm.add_argument("name", help="source name to remove")
    p_rm.set_defaults(func=_cmd_source_remove)

    p_refresh = source_sub.add_parser("refresh", help="check/refresh a source's health")
    p_refresh.add_argument("name", nargs="?", default=None, help="source name (default: all)")
    p_refresh.set_defaults(func=_cmd_source_refresh)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
