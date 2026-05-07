"""M1.10 — lyra lint: structural health checks for the wiki vault (ADR-8).

Checks:
  - ORPHAN_RAW    : raw records with no corresponding wiki page
  - ORPHAN_WIKI   : wiki pages whose sources raw_ids are all absent from raw/
  - DANGLING_REL  : relations whose target_id does not resolve to any wiki page
  - BROKEN_SUPER  : supersedes/superseded_by edges pointing to absent pages
  - CONTRADICTION : contradicts edges with no accompanying supersession
  - MISSING_FM    : wiki pages missing required frontmatter fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lyra import markdown as md
from lyra.ids import is_ulid

REQUIRED_FRONTMATTER = frozenset(
    {"id", "type", "sources", "confidence", "created", "last_confirmed"}
)

IssueKind = Literal[
    "ORPHAN_RAW",
    "ORPHAN_WIKI",
    "DANGLING_REL",
    "BROKEN_SUPER",
    "CONTRADICTION",
    "MISSING_FM",
]


@dataclass
class LintIssue:
    kind: IssueKind
    path: Path
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class LintReport:
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0

    def by_kind(self, kind: IssueKind) -> list[LintIssue]:
        return [i for i in self.issues if i.kind == kind]


def lint_vault(vault_path: Path, *, structural_only: bool = False) -> LintReport:
    """Run all lint checks and return a consolidated LintReport.

    Args:
        structural_only: when True, skip checks that require reading relation
                         targets (DANGLING_REL), which can be slow on large vaults.
    """
    report = LintReport()

    raw_index = _build_raw_index(vault_path)
    wiki_index = _build_wiki_index(vault_path)

    _check_orphan_raws(vault_path, raw_index, wiki_index, report)
    _check_orphan_wiki(vault_path, wiki_index, raw_index, report)
    _check_missing_frontmatter(vault_path, wiki_index, report)
    _check_broken_supersession(vault_path, wiki_index, report)
    _check_contradictions(vault_path, wiki_index, report)

    if not structural_only:
        _check_dangling_relations(vault_path, wiki_index, report)

    return report


# ------------------------------------------------------------------
# Index builders
# ------------------------------------------------------------------

def _build_raw_index(vault_path: Path) -> dict[str, Path]:
    """raw_id → path for all flat raw/ records."""
    out: dict[str, Path] = {}
    raw_dir = vault_path / "raw"
    if not raw_dir.exists():
        return out
    for path in raw_dir.glob("*.md"):
        try:
            doc = md.read(path)
            raw_id = doc.frontmatter.get("raw_id")
            if raw_id:
                out[str(raw_id)] = path
        except Exception:  # noqa: BLE001
            pass
    return out


def _build_wiki_index(vault_path: Path) -> dict[str, dict]:
    """page_ulid → frontmatter for all wiki pages."""
    out: dict[str, dict] = {}
    wiki_root = vault_path / "wiki"
    if not wiki_root.exists():
        return out
    for path in wiki_root.rglob("*.md"):
        if path.name in {"index.md", "log.md", "AGENTS.md"}:
            continue
        try:
            doc = md.read(path)
            page_id = doc.frontmatter.get("id")
            if page_id:
                fm = dict(doc.frontmatter)
                fm["_path"] = path
                out[str(page_id)] = fm
        except Exception:  # noqa: BLE001
            pass
    return out


# ------------------------------------------------------------------
# Individual checks
# ------------------------------------------------------------------

def _check_orphan_raws(
    vault_path: Path,
    raw_index: dict[str, Path],
    wiki_index: dict[str, dict],
    report: LintReport,
) -> None:
    """Raw records (kind=research|clip) with no corresponding wiki source."""
    all_wiki_sources: set[str] = set()
    for fm in wiki_index.values():
        for s in fm.get("sources") or []:
            all_wiki_sources.add(str(s))

    for raw_id, path in raw_index.items():
        try:
            doc = md.read(path)
            kind = doc.frontmatter.get("kind")
            if kind not in {"research", "clip"}:
                continue
            if raw_id not in all_wiki_sources:
                report.issues.append(
                    LintIssue(
                        kind="ORPHAN_RAW",
                        path=path,
                        message=f"raw record {raw_id!r} has not been promoted to wiki/sources/",
                        detail={"raw_id": raw_id, "kind": kind},
                    )
                )
        except Exception:  # noqa: BLE001
            pass


def _check_orphan_wiki(
    vault_path: Path,
    wiki_index: dict[str, dict],
    raw_index: dict[str, Path],
    report: LintReport,
) -> None:
    """Wiki pages whose every listed source raw_id is absent from raw/."""
    for page_id, fm in wiki_index.items():
        sources = [str(s) for s in (fm.get("sources") or [])]
        if not sources:
            continue
        missing = [s for s in sources if s not in raw_index]
        if len(missing) == len(sources):
            path = fm["_path"]
            report.issues.append(
                LintIssue(
                    kind="ORPHAN_WIKI",
                    path=path,
                    message=f"wiki page {page_id!r} references only absent raw sources",
                    detail={"missing_sources": missing},
                )
            )


def _check_missing_frontmatter(
    vault_path: Path,
    wiki_index: dict[str, dict],
    report: LintReport,
) -> None:
    for page_id, fm in wiki_index.items():
        missing = [f for f in REQUIRED_FRONTMATTER if f not in fm]
        if missing:
            path = fm["_path"]
            report.issues.append(
                LintIssue(
                    kind="MISSING_FM",
                    path=path,
                    message=f"page {page_id!r} missing required frontmatter: {missing}",
                    detail={"missing_fields": missing},
                )
            )


def _check_broken_supersession(
    vault_path: Path,
    wiki_index: dict[str, dict],
    report: LintReport,
) -> None:
    for page_id, fm in wiki_index.items():
        path = fm["_path"]

        for target_id in fm.get("supersedes") or []:
            if str(target_id) and str(target_id) not in wiki_index:
                report.issues.append(
                    LintIssue(
                        kind="BROKEN_SUPER",
                        path=path,
                        message=(
                            f"page {page_id!r} supersedes {target_id!r} "
                            "but target does not exist"
                        ),
                        detail={"target_id": str(target_id)},
                    )
                )

        superseded_by = fm.get("superseded_by")
        if superseded_by and str(superseded_by) not in wiki_index:
            report.issues.append(
                LintIssue(
                    kind="BROKEN_SUPER",
                    path=path,
                    message=(
                        f"page {page_id!r} has superseded_by={superseded_by!r} "
                        "but target does not exist"
                    ),
                    detail={"target_id": str(superseded_by)},
                )
            )


def _check_contradictions(
    vault_path: Path,
    wiki_index: dict[str, dict],
    report: LintReport,
) -> None:
    """Contradictions with no supersession on either side (ADR-8 / M3.9).

    Attaches auto-supersession score breakdown to each unresolved contradiction
    so the operator can see why compile did not auto-resolve it (score diff < τ).
    """
    from lyra.compile_pipeline import score_page
    from lyra import config as cfg_mod

    try:
        cfg = cfg_mod.load(cfg_mod.CONFIG_PATH)
        weights = cfg.auto_supersession.weights
        threshold = cfg.auto_supersession.threshold
    except Exception:  # noqa: BLE001
        weights = cfg_mod.AutoSupersessionWeights()
        threshold = 0.2

    all_dates = [str(fm.get("last_confirmed") or "") for fm in wiki_index.values()]

    seen: set[frozenset] = set()
    for page_id, fm in wiki_index.items():
        path = fm["_path"]
        contradicts = [str(t) for t in (fm.get("contradicts") or [])]
        if not contradicts:
            continue

        supersedes = {str(t) for t in (fm.get("supersedes") or [])}
        superseded_by = str(fm.get("superseded_by") or "")

        for target_id in contradicts:
            pair: frozenset = frozenset({page_id, target_id})
            if pair in seen:
                continue
            seen.add(pair)

            if target_id in supersedes or superseded_by == target_id:
                continue
            target_fm = wiki_index.get(target_id, {})
            target_supersedes = {str(t) for t in (target_fm.get("supersedes") or [])}
            target_superseded_by = str(target_fm.get("superseded_by") or "")
            if page_id in target_supersedes or target_superseded_by == page_id:
                continue

            score_a = score_page(page_id, fm, wiki_index, all_dates, weights)
            score_b = score_page(target_id, target_fm, wiki_index, all_dates, weights)
            diff = round(abs(score_a["total"] - score_b["total"]), 3)

            report.issues.append(
                LintIssue(
                    kind="CONTRADICTION",
                    path=path,
                    message=(
                        f"page {page_id!r} contradicts {target_id!r} — "
                        f"needs human resolution (score diff {diff:.3f} < τ={threshold:.2f})"
                    ),
                    detail={
                        "contradicts": target_id,
                        "scores": {page_id: score_a, target_id: score_b},
                        "diff": diff,
                        "threshold": threshold,
                    },
                )
            )


def _check_dangling_relations(
    vault_path: Path,
    wiki_index: dict[str, dict],
    report: LintReport,
) -> None:
    for page_id, fm in wiki_index.items():
        path = fm["_path"]
        for rel in fm.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            target_id = rel.get("target_id")
            if not target_id:
                continue
            if is_ulid(str(target_id)) and str(target_id) not in wiki_index:
                report.issues.append(
                    LintIssue(
                        kind="DANGLING_REL",
                        path=path,
                        message=(
                            f"page {page_id!r} has relation {rel.get('type')!r} "
                            f"→ {target_id!r} but target does not exist"
                        ),
                        detail={"relation": rel},
                    )
                )
