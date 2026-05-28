"""
run_marketing_discovery — batch ops for Lote A/B marketing buyer discovery.

Subcommands:
  status          — twins.db readiness per slug
  plan            — print cohort table with goals/openers
  write-dispatch  — emit .dispatch YAML for DO daemon / GH workflow
  interview-cmd   — print interview_marketing_buyer CLI per slug
  export          — export transcripts → memory/synthetic-interviews/

Does not run FULL pipeline (needs DO runner). See aspasia/skills/run-marketing-discovery.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.twins import storage
from rag.twins.marketing_discovery_manifest import (
    MarketingInterviewSpec,
    cmo_slugs,
    specs_for_priority,
)

DISPATCH_DIR = Path("rag/twins/.dispatch")
PERSONS_DIR = Path("rag/twins/persons")


def _twin_for_person(person_id: str, db_path: Path | None) -> dict | None:
    with storage.connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM twin WHERE person_id = ? ORDER BY updated_at DESC LIMIT 1",
            (person_id,),
        ).fetchone()
    return dict(row) if row else None


def _cmo_specs(tier: str) -> list[MarketingInterviewSpec]:
    from rag.twins.marketing_discovery_manifest import (
        DEFAULT_CMO_OPENER,
        DEFAULT_CMO_RESEARCH_GOAL,
        cmo_slugs,
    )

    return [
        MarketingInterviewSpec(
            person_id=slug,
            lote="B",
            priority="T1" if tier.upper() in ("T1", "T1,T2", "ALL") else "T2",
            research_goal=DEFAULT_CMO_RESEARCH_GOAL,
            opener=DEFAULT_CMO_OPENER,
        )
        for slug in cmo_slugs(tier)
    ]


def _resolve_specs(*, priority: str | None, cmo: str | None) -> list[MarketingInterviewSpec]:
    specs: list[MarketingInterviewSpec] = []
    if priority:
        specs.extend(specs_for_priority(priority))
    if cmo:
        specs.extend(_cmo_specs(cmo))
    if not specs:
        raise ValueError("Provide --priority and/or --cmo (e.g. --cmo T1)")
    return specs


def cmd_status(*, db_path: Path | None, priority: str | None, cmo: str | None) -> int:
    specs = _resolve_specs(priority=priority, cmo=cmo)
    print(f"{'person_id':<40} {'spec':^5} {'twin':^5} {'twin_id':<38}")
    print("-" * 95)
    for spec in specs:
        spec_ok = (PERSONS_DIR / f"{spec.person_id}.yaml").exists()
        twin = _twin_for_person(spec.person_id, db_path)
        tid = (twin or {}).get("id", "")[:36]
        print(
            f"{spec.person_id:<40} {'yes' if spec_ok else 'NO':^5} "
            f"{'yes' if twin else 'NO':^5} {tid}"
        )
    with storage.connect(db_path) as conn:
        n_sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM interview_turn WHERE session_id LIKE 'mkt-interview%'"
        ).fetchone()[0]
    print(f"\nmarketing interview sessions in DB: {n_sessions}")
    return 0


def cmd_plan(*, priority: str, include_cmo: str | None) -> int:
    for spec in specs_for_priority(priority):
        print(f"\n## {spec.priority} — {spec.person_id}")
        print(f"research_goal: {spec.research_goal}")
        print(f"opener: {spec.opener}")
    if include_cmo:
        print("\n## Lote B CMO slugs")
        for slug in cmo_slugs(include_cmo):
            print(f"- {slug} (goal/opener: defaults — tailor per YAML notes)")
    return 0


def cmd_interview_cmd(
    *,
    db_path: Path | None,
    priority: str,
    turns: int,
    mock: bool,
) -> int:
    for spec in specs_for_priority(priority):
        twin = _twin_for_person(spec.person_id, db_path)
        if not twin:
            print(f"# SKIP {spec.person_id} — no twin in DB (ingest+build on DO runner)\n")
            continue
        mock_flag = " --mock" if mock else ""
        print(
            f"python3 -m rag.twins.interview_marketing_buyer {twin['id']} "
            f"--turns {turns}{mock_flag} "
            f"--research-goal {spec.research_goal!r} "
            f"--opener {spec.opener!r}\n"
        )
    return 0


def _write_dispatch_yaml(
    path: Path,
    *,
    slugs: list[str],
    mode: str,
    confirm_full: bool,
    skip_transcribe: bool = False,
    skip_build_eval: bool = False,
    comment: str = "",
) -> None:
    lines = []
    if comment:
        lines.extend([f"# {line}" for line in comment.strip().splitlines()])
        lines.append("")
    if len(slugs) == 1:
        lines.append(f"slug: {slugs[0]}")
    else:
        lines.append("slugs:")
        for s in slugs:
            lines.append(f"  - {s}")
    lines.extend(
        [
            "",
            f"mode: {mode}",
            f"confirm_full_mode: {'true' if confirm_full else 'false'}",
            f"skip_transcribe: {'true' if skip_transcribe else 'false'}",
            f"skip_build_eval: {'true' if skip_build_eval else 'false'}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)


def cmd_write_dispatch(
    *,
    priority: str | None,
    mode: str,
    confirm_full: bool,
    cmo_tier: str | None,
    cmo_only: bool,
    out_name: str | None,
) -> int:
    slugs: list[str] = []
    if cmo_only:
        if not cmo_tier:
            raise ValueError("--cmo-only requires --cmo (e.g. --cmo T1)")
        slugs = cmo_slugs(cmo_tier)
    else:
        if not priority:
            raise ValueError("Provide --priority (P0/P1) or --cmo-only with --cmo")
        slugs = [s.person_id for s in specs_for_priority(priority)]
        if cmo_tier:
            slugs.extend(cmo_slugs(cmo_tier))
    if cmo_only:
        name = out_name or f"2026-05-17-cmo-{cmo_tier.lower()}-{mode}.yml"
    else:
        name = out_name or f"2026-05-17-lote-a-{priority.lower()}-{mode}.yml"
    path = DISPATCH_DIR / name
    _write_dispatch_yaml(
        path,
        slugs=slugs,
        mode=mode,
        confirm_full=confirm_full,
        comment=(
            "Marketing discovery batch — generated by run_marketing_discovery.py. "
            "Process on DO twins runner (daemon or gh workflow twins-run)."
        ),
    )
    return 0


def cmd_export(*, db_path: Path | None) -> int:
    from rag.twins.export_interview_transcript import export_all, list_sessions

    sessions = list_sessions(db_path=db_path)
    if not sessions:
        print("No mkt-interview sessions in twins.db", file=sys.stderr)
        return 1
    for md, js in export_all(db_path=db_path):
        print(md)
    return 0


def cmd_joint_discovery_batch(
    *,
    db_path: Path | None,
    cmo: str,
    turns: int,
    mock: bool,
    skip_existing: bool,
    force: bool,
) -> int:
    """Aspasia + Iza joint discovery for each CMO slug (dev_seed if YAML has notes)."""
    from datetime import UTC, datetime

    from rag.twins.joint_discovery import (
        JointDiscoveryResult,
        render_markdown,
        run_joint_discovery,
    )

    out_dir = (
        Path("company/SyntheticPerson/syntheticperson-ai/memory/synthetic-interviews")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d")
    specs = _cmo_specs(cmo)
    ok, fail = 0, 0

    for spec in specs:
        slug = spec.person_id
        out_path = out_dir / f"{slug}-{ts}.md"
        if skip_existing and not force and out_path.exists():
            print(f"SKIP {slug} — {out_path} exists")
            ok += 1
            continue
        twin = _twin_for_person(slug, db_path)
        if not twin and not (PERSONS_DIR / f"{slug}.yaml").exists():
            print(f"FAIL {slug} — no YAML spec", file=sys.stderr)
            fail += 1
            continue
        try:
            result: JointDiscoveryResult = run_joint_discovery(
                slug,
                research_goal=spec.research_goal,
                opener=spec.opener,
                turns=turns,
                mock=mock,
                db_path=db_path,
            )
            out_path.write_text(render_markdown(result), encoding="utf-8")
            print(f"OK {slug} → {out_path} session={result.session_id}")
            ok += 1
        except Exception as exc:
            print(f"FAIL {slug} — {exc}", file=sys.stderr)
            fail += 1

    print(f"\njoint-discovery batch: {ok} ok, {fail} failed (tier {cmo})")
    return 0 if fail == 0 else 1


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Check spec + twin rows")
    s.add_argument("--priority", default=None, help="P0, P1, or P0,P1 (arch-mkt)")
    s.add_argument("--cmo", default=None, help="T1, T2, or T1,T2 for CMO BR slugs")

    s = sub.add_parser("plan", help="Print research goals and openers")
    s.add_argument("--priority", default="P0,P1")
    s.add_argument("--cmo", default=None, help="T1, T2, or T1,T2 to list CMO slugs")

    s = sub.add_parser("interview-cmd", help="Print interview CLI lines")
    s.add_argument("--priority", default="P0")
    s.add_argument("--turns", type=int, default=8)
    s.add_argument("--mock", action="store_true")

    s = sub.add_parser("write-dispatch", help="Write rag/twins/.dispatch/*.yml")
    s.add_argument("--priority", default=None, help="P0, P1, or P0,P1 (arch-mkt)")
    s.add_argument("--mode", default="full", choices=("dry-run", "full"))
    s.add_argument("--confirm-full", action="store_true")
    s.add_argument("--cmo", default=None, help="Append or sole cohort (--cmo-only)")
    s.add_argument(
        "--cmo-only",
        action="store_true",
        help="Dispatch only CMO tier slugs (no Lote A arch-mkt)",
    )
    s.add_argument("--out", default=None, dest="out_name")

    sub.add_parser("export", help="Export sessions to memory/synthetic-interviews")

    s = sub.add_parser(
        "joint-discovery",
        help="Run Aspasia+Iza joint_discovery per CMO slug; write memory/synthetic-interviews/",
    )
    s.add_argument("--cmo", default="T1", help="T1, T2, or T1,T2")
    s.add_argument("--turns", type=int, default=8)
    s.add_argument("--mock", action="store_true")
    s.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip if today's output file already exists",
    )
    s.add_argument(
        "--force",
        action="store_true",
        help="Overwrite today's output (replaces prior --mock runs)",
    )

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.cmd == "status":
        priority = getattr(args, "priority", None) or "P0"
        if getattr(args, "cmo", None) and not getattr(args, "priority", None):
            priority = None
        return cmd_status(
            db_path=args.db,
            priority=priority,
            cmo=getattr(args, "cmo", None),
        )
    if args.cmd == "plan":
        return cmd_plan(priority=args.priority, include_cmo=getattr(args, "cmo", None))
    if args.cmd == "interview-cmd":
        return cmd_interview_cmd(
            db_path=args.db,
            priority=args.priority,
            turns=args.turns,
            mock=args.mock,
        )
    if args.cmd == "write-dispatch":
        return cmd_write_dispatch(
            priority=getattr(args, "priority", None),
            mode=args.mode,
            confirm_full=args.confirm_full,
            cmo_tier=getattr(args, "cmo", None),
            cmo_only=getattr(args, "cmo_only", False),
            out_name=getattr(args, "out_name", None),
        )
    if args.cmd == "export":
        return cmd_export(db_path=args.db)
    if args.cmd == "joint-discovery":
        return cmd_joint_discovery_batch(
            db_path=args.db,
            cmo=args.cmo,
            turns=args.turns,
            mock=args.mock,
            skip_existing=args.skip_existing,
            force=getattr(args, "force", False),
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
