"""
run_executive_ai_discovery — batch ops for executive AI fluency / FOMO cohort (200).

Subcommands:
  status          — YAML + twins.db readiness
  plan            — research goals and openers per cell
  interview-cmd   — print interview_archetype CLI (mode executive-ai-fluency)
  write-dispatch  — emit .dispatch YAML (one slug per file recommended)
  count           — verify matrix size

Does not run FULL ingest on DO runner. See 47-EXEC-AI-FLUENCY-PSYCHOGRAPHY.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.twins import storage
from rag.twins.executive_ai_fluency_cohort import COHORT_MATRIX
from rag.twins.executive_ai_fluency_manifest import (
    DEFAULT_EXEC_OPENER,
    DEFAULT_EXEC_RESEARCH_GOAL,
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


def cmd_count() -> int:
    print(f"cohort cells: {len(COHORT_MATRIX)} (expected 200)")
    return 0 if len(COHORT_MATRIX) == 200 else 1


def cmd_status(*, db_path: Path | None, priority: str) -> int:
    from rag.twins.executive_ai_fluency_manifest import ExecutiveInterviewSpec

    if priority.upper() == "P0+8":
        from rag.twins.executive_ai_fluency_cohort import cells_for_priority as cells

        cohort = list(cells("P0")) + [x for x in cells("ALL") if x.priority == "P2" and x.slice_id == "sp-cap-listada"][:8]
        specs = [
            ExecutiveInterviewSpec(
                person_id=c.person_id,
                lote=c.lote,
                priority=c.priority,
                research_goal=c.research_goal,
                opener=c.opener,
                archetype_id=c.archetype_id,
                slice_id=c.slice_id,
            )
            for c in cohort
        ]
    else:
        specs = specs_for_priority(priority)
    print(f"{'person_id':<55} {'yaml':^5} {'twin':^5}")
    print("-" * 70)
    yaml_ok = twin_ok = 0
    for spec in specs:
        y = (PERSONS_DIR / f"{spec.person_id}.yaml").exists()
        twin = _twin_for_person(spec.person_id, db_path)
        if y:
            yaml_ok += 1
        if twin:
            twin_ok += 1
        print(
            f"{spec.person_id:<55} {'yes' if y else 'NO':^5} "
            f"{'yes' if twin else 'NO':^5}"
        )
    print(f"\n{yaml_ok}/{len(specs)} YAML, {twin_ok}/{len(specs)} twin rows")
    return 0


def cmd_plan(*, priority: str) -> int:
    for spec in specs_for_priority(priority):
        print(f"\n## {spec.priority} — {spec.person_id}")
        print(f"archetype: {spec.archetype_id} | slice: {spec.slice_id}")
        print(f"research_goal: {spec.research_goal}")
        print(f"opener: {spec.opener}")
    return 0


def cmd_interview_cmd(
    *,
    db_path: Path | None,
    priority: str,
    turns: int,
    mock: bool,
    guide: str | None = None,
) -> int:
    from rag.twins.executive_ai_fluency_manifest import ExecutiveInterviewSpec

    if priority.upper() == "P0+8":
        from rag.twins.executive_ai_fluency_cohort import cells_for_priority as cells

        cohort = list(cells("P0")) + [x for x in cells("ALL") if x.priority == "P2" and x.slice_id == "sp-cap-listada"][:8]
        spec_list = [
            ExecutiveInterviewSpec(
                person_id=c.person_id,
                lote=c.lote,
                priority=c.priority,
                research_goal=c.research_goal,
                opener=c.opener,
                archetype_id=c.archetype_id,
                slice_id=c.slice_id,
            )
            for c in cohort
        ]
    else:
        spec_list = specs_for_priority(priority)
    for spec in spec_list:
        twin = _twin_for_person(spec.person_id, db_path)
        slug = twin["id"] if twin else spec.person_id
        mock_flag = " --mock" if mock else ""
        guide_flag = f" --guide {guide}" if guide else ""
        goal = spec.research_goal
        opener = spec.opener
        if guide == "mom-test":
            from rag.twins.executive_ai_fluency_interview_guide import (
                MOM_TEST_DEFAULT_TURNS,
                MOM_TEST_OPENER,
                MOM_TEST_RESEARCH_GOAL,
            )

            goal = MOM_TEST_RESEARCH_GOAL
            opener = MOM_TEST_OPENER
            if turns == 8:
                turns = MOM_TEST_DEFAULT_TURNS
        print(
            f"python3 -m rag.twins.interview_archetype {slug!r} "
            f"--mode executive-ai-fluency --turns {turns}{mock_flag}{guide_flag} "
            f"--research-goal {goal!r} "
            f"--opener {opener!r}\n"
        )
    return 0


def _write_dispatch_yaml(
    path: Path,
    *,
    slugs: list[str],
    mode: str,
    confirm_full: bool,
    comment: str = "",
) -> None:
    lines: list[str] = []
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
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)


def _slugs_for_priority(priority: str) -> list[str]:
    pri = priority.upper()
    if pri == "P0+8":
        from rag.twins.executive_ai_fluency_cohort import cells_for_priority as cells

        return [c.person_id for c in list(cells("P0")) + [x for x in cells("ALL") if x.priority == "P2" and x.slice_id == "sp-cap-listada"][:8]]
    return [s.person_id for s in specs_for_priority(priority)]


def cmd_write_dispatch(
    *,
    priority: str,
    mode: str,
    confirm_full: bool,
    one_per_file: bool,
    out_name: str | None,
) -> int:
    slugs = _slugs_for_priority(priority)
    if one_per_file:
        for slug in slugs:
            name = f"exec-ai-{slug}.yml"
            _write_dispatch_yaml(
                DISPATCH_DIR / name,
                slugs=[slug],
                mode=mode,
                confirm_full=confirm_full,
                comment="Executive AI fluency — one slug per dispatch (90min timeout rule).",
            )
        return 0
    name = out_name or f"exec-ai-fluency-{priority.lower()}.yml"
    _write_dispatch_yaml(
        DISPATCH_DIR / name,
        slugs=slugs,
        mode=mode,
        confirm_full=confirm_full,
        comment=(
            "Executive AI fluency batch — prefer --one-per-file for DO runner. "
            f"Defaults: goal={DEFAULT_EXEC_RESEARCH_GOAL[:60]}…"
        ),
    )
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("count", help="Verify 200-cell matrix")

    s = sub.add_parser("status")
    s.add_argument("--priority", default="P0")

    s = sub.add_parser("plan")
    s.add_argument("--priority", default="P0")

    s = sub.add_parser("interview-cmd")
    s.add_argument("--priority", default="P0")
    s.add_argument("--turns", type=int, default=8)
    s.add_argument("--mock", action="store_true")
    s.add_argument(
        "--guide",
        default=None,
        choices=("mom-test",),
        help="Mom-Test Blocos 0–4 (~24 turns when --turns omitted at 8).",
    )

    s = sub.add_parser("write-dispatch")
    s.add_argument("--priority", default="P0")
    s.add_argument("--mode", default="full", choices=("dry-run", "full"))
    s.add_argument("--confirm-full", action="store_true")
    s.add_argument("--one-per-file", action="store_true", help="One YAML per slug (recommended)")
    s.add_argument("--out", default=None, dest="out_name")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.cmd == "count":
        return cmd_count()
    if args.cmd == "status":
        return cmd_status(db_path=args.db, priority=args.priority)
    if args.cmd == "plan":
        return cmd_plan(priority=args.priority)
    if args.cmd == "interview-cmd":
        return cmd_interview_cmd(
            db_path=args.db,
            priority=args.priority,
            turns=args.turns,
            mock=args.mock,
            guide=args.guide,
        )
    if args.cmd == "write-dispatch":
        return cmd_write_dispatch(
            priority=args.priority,
            mode=args.mode,
            confirm_full=args.confirm_full,
            one_per_file=args.one_per_file,
            out_name=args.out_name,
        )
    raise SystemExit(f"unknown command {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
