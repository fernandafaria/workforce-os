"""
joint_discovery_worker — drain Supabase queue on the twins runner.

Pairs with migrations 107 + 108 and .github/workflows/joint-discovery-cron.yml.

Usage:
    python -m rag.twins.joint_discovery_worker enqueue-daily
    python -m rag.twins.joint_discovery_worker drain-queue --phase aspasia --max-runs 1
    python -m rag.twins.joint_discovery_worker drain-queue --phase iza --max-runs 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from rag.twins.joint_discovery import (
    AspasiaPhaseResult,
    JointDiscoveryResult,
    _format_transcript,
    render_markdown,
    run_interview_and_aspasia,
    run_iza_pass_from_row,
)

log = logging.getLogger("joint_discovery_worker")

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = (
    REPO_ROOT
    / "company"
    / "SyntheticPerson"
    / "syntheticperson-ai"
    / "memory"
    / "synthetic-interviews"
)
JOINT_DISCOVERY_ASPASIA_TRIGGER_ID = "00000000-0000-4000-a000-000000005002"
JOINT_DISCOVERY_IZA_TRIGGER_ID = "00000000-0000-4000-a000-000000005003"
DEFAULT_TURNS = 8
Phase = Literal["aspasia", "iza"]


@dataclass
class Supa:
    url: str
    key: str

    @classmethod
    def from_env(cls) -> Supa:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        return cls(url=url, key=key)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        r = httpx.post(
            f"{self.url}/rest/v1/rpc/{name}",
            headers=self._headers,
            json=payload,
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def patch(self, table: str, row_id: str, fields: dict[str, Any]) -> None:
        r = httpx.patch(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers,
            params={"id": f"eq.{row_id}"},
            json=fields,
            timeout=30.0,
        )
        r.raise_for_status()

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers,
            json=row,
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data

    def get_default_company(self) -> tuple[str, str]:
        r = httpx.get(
            f"{self.url}/rest/v1/companies",
            headers=self._headers,
            params={
                "select": "id,user_id",
                "is_default": "eq.true",
                "deleted_at": "is.null",
                "order": "created_at.asc",
                "limit": "1",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise SystemExit("No default company in Supabase")
        return rows[0]["id"], rows[0]["user_id"]


def _write_output_file(slug: str, markdown: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d")
    path = OUTPUT_DIR / f"{slug}-{ts}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def enqueue_daily(*, trigger_id: str | None = None) -> dict[str, Any] | None:
    supa = Supa.from_env()
    company_id, user_id = supa.get_default_company()
    tid = trigger_id or JOINT_DISCOVERY_ASPASIA_TRIGGER_ID
    row = supa.rpc(
        "enqueue_next_joint_discovery_run",
        {
            "p_company_id": company_id,
            "p_user_id": user_id,
            "p_trigger_id": tid,
        },
    )
    if not row:
        log.info(
            "enqueue_daily: nothing to enqueue "
            "(in-flight today or empty catalog)"
        )
        return None
    log.info("enqueued joint_discovery run id=%s slug=%s", row.get("id"), row.get("slug"))
    return row


def _create_agent_run(
    supa: Supa,
    *,
    company_id: str,
    user_id: str,
    trigger_id: str,
    slug: str,
    persona_slug: str,
    phase: Phase,
    output_md: str,
) -> str:
    row = supa.insert(
        "agent_runs",
        {
            "company_id": company_id,
            "user_id": user_id,
            "trigger_id": trigger_id,
            "status": "completed",
            "input": {
                "pipeline": "joint_discovery",
                "phase": phase,
                "slug": slug,
                "persona_slug": persona_slug,
            },
            "output_md": output_md[:500_000],
            "ended_at": datetime.now(UTC).isoformat(),
        },
    )
    return row["id"]


def _claim_rpc(phase: Phase) -> str:
    return "claim_joint_discovery_run" if phase == "aspasia" else "claim_joint_discovery_run_iza"


def _process_aspasia(
    supa: Supa,
    claimed: dict[str, Any],
    *,
    company_id: str,
    user_id: str,
    turns: int,
    mock: bool,
) -> dict[str, Any]:
    run_id = claimed["id"]
    slug = claimed["slug"]
    goal = claimed["research_goal"]
    opener = claimed.get("opener")

    aspasia = run_interview_and_aspasia(
        slug,
        research_goal=goal,
        opener=opener,
        turns=turns,
        mock=mock,
    )
    brief_md = (
        f"# Joint discovery — `{slug}` (phase 1 Aspasia)\n\n"
        f"**Session:** `{aspasia.session_id}`  \n"
        f"**Evidence tier:** {aspasia.evidence_tier}\n\n"
        f"{aspasia.aspasia_brief_md}"
    )
    agent_run_id = _create_agent_run(
        supa,
        company_id=company_id,
        user_id=user_id,
        trigger_id=JOINT_DISCOVERY_ASPASIA_TRIGGER_ID,
        slug=slug,
        persona_slug="aspasia-pm",
        phase="aspasia",
        output_md=brief_md,
    )
    now = datetime.now(UTC).isoformat()
    supa.patch(
        "joint_discovery_runs",
        run_id,
        {
            "status": "aspasia_done",
            "aspasia_completed_at": now,
            "session_id": aspasia.session_id,
            "twin_id": aspasia.twin_id,
            "interview_profile": aspasia.interview_profile,
            "evidence_tier": aspasia.evidence_tier,
            "aspasia_brief_md": aspasia.aspasia_brief_md[:500_000],
            "aspasia_agent_run_id": agent_run_id,
            "agent_run_id": agent_run_id,
        },
    )
    return {
        "run_id": run_id,
        "slug": slug,
        "phase": "aspasia",
        "session_id": aspasia.session_id,
        "aspasia_agent_run_id": agent_run_id,
    }


def _process_iza(
    supa: Supa,
    claimed: dict[str, Any],
    *,
    company_id: str,
    user_id: str,
    mock: bool,
) -> dict[str, Any]:
    run_id = claimed["id"]
    slug = claimed["slug"]
    goal = claimed["research_goal"]
    session_id = claimed.get("session_id")
    aspasia_brief = claimed.get("aspasia_brief_md")
    if not session_id or not aspasia_brief:
        raise RuntimeError(
            f"run {run_id} missing session_id or aspasia_brief_md for Iza phase"
        )

    iza = run_iza_pass_from_row(
        session_id=session_id,
        slug=slug,
        research_goal=goal,
        aspasia_brief_md=aspasia_brief,
        interview_profile=claimed.get("interview_profile") or "buyer_professional",
        evidence_tier=claimed.get("evidence_tier") or "exploratory",
        twin_id=claimed.get("twin_id") or "",
        mock=mock,
    )

    aspasia = AspasiaPhaseResult(
        session_id=session_id,
        twin_id=claimed.get("twin_id") or "",
        person_id=slug,
        interview_profile=claimed.get("interview_profile") or "buyer_professional",
        research_goal=goal,
        transcript_md=_format_transcript(session_id),
        aspasia_brief_md=aspasia_brief,
        evidence_tier=claimed.get("evidence_tier") or "exploratory",
    )

    full = JointDiscoveryResult.merge(aspasia, iza)
    md = render_markdown(full)
    out_path = _write_output_file(slug, md)

    surface_md = (
        f"# Joint discovery — `{slug}` (phase 2 Iza)\n\n"
        f"**Session:** `{session_id}`\n\n"
        f"{iza.iza_surface_md}"
    )
    iza_agent_run_id = _create_agent_run(
        supa,
        company_id=company_id,
        user_id=user_id,
        trigger_id=JOINT_DISCOVERY_IZA_TRIGGER_ID,
        slug=slug,
        persona_slug="iza-designer",
        phase="iza",
        output_md=surface_md,
    )
    now = datetime.now(UTC).isoformat()
    supa.patch(
        "joint_discovery_runs",
        run_id,
        {
            "status": "completed",
            "completed_at": now,
            "iza_completed_at": now,
            "iza_surface_md": iza.iza_surface_md[:500_000],
            "iza_agent_run_id": iza_agent_run_id,
            "agent_run_id": iza_agent_run_id,
            "output_md": md[:500_000],
            "output_path": str(out_path.relative_to(REPO_ROOT)),
        },
    )
    return {
        "run_id": run_id,
        "slug": slug,
        "phase": "iza",
        "path": str(out_path),
        "iza_agent_run_id": iza_agent_run_id,
    }


def drain_queue(
    *,
    phase: Phase = "aspasia",
    max_runs: int = 1,
    gh_run_id: int | None = None,
    turns: int = DEFAULT_TURNS,
    mock: bool = False,
) -> list[dict[str, Any]]:
    supa = Supa.from_env()
    company_id, user_id = supa.get_default_company()
    completed: list[dict[str, Any]] = []
    claim_fn = _claim_rpc(phase)

    for _ in range(max_runs):
        claimed = supa.rpc(claim_fn, {"p_gh_run_id": gh_run_id})
        if not claimed:
            log.info("drain_queue phase=%s: queue empty", phase)
            break

        run_id = claimed["id"]
        slug = claimed["slug"]
        log.info("processing phase=%s run_id=%s slug=%s", phase, run_id, slug)

        try:
            if phase == "aspasia":
                row = _process_aspasia(
                    supa,
                    claimed,
                    company_id=company_id,
                    user_id=user_id,
                    turns=turns,
                    mock=mock,
                )
            else:
                row = _process_iza(
                    supa,
                    claimed,
                    company_id=company_id,
                    user_id=user_id,
                    mock=mock,
                )
            completed.append(row)
            log.info("completed phase=%s slug=%s", phase, slug)
        except Exception as e:
            log.exception("joint_discovery failed phase=%s slug=%s", phase, slug)
            supa.patch(
                "joint_discovery_runs",
                run_id,
                {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_message": f"[{phase}] {e}"[:4000],
                },
            )

    return completed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    p_enq = sub.add_parser("enqueue-daily", help="Enqueue next arch-mkt slug for today")
    p_enq.add_argument("--trigger-id", default=JOINT_DISCOVERY_ASPASIA_TRIGGER_ID)

    p_drain = sub.add_parser("drain-queue", help="Process queued joint_discovery runs")
    p_drain.add_argument(
        "--phase",
        choices=("aspasia", "iza"),
        default="aspasia",
        help="aspasia: interview+brief; iza: surface on aspasia_done rows",
    )
    p_drain.add_argument("--max-runs", type=int, default=1)
    p_drain.add_argument("--gh-run-id", type=int, default=None)
    p_drain.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    p_drain.add_argument("--mock", action="store_true")
    p_drain.add_argument("--verbose", action="store_true")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO)

    if args.command == "enqueue-daily":
        row = enqueue_daily(trigger_id=args.trigger_id)
        print(json.dumps(row or {"enqueued": False}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "drain-queue":
        rows = drain_queue(
            phase=args.phase,
            max_runs=args.max_runs,
            gh_run_id=args.gh_run_id,
            turns=args.turns,
            mock=args.mock,
        )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
