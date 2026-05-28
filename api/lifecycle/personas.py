"""
Workforce OS — Persona Lifecycle
================================

CI/CD for the 150 canonical personas:

  eval     → run persona-eval edge function; records agent_eval_runs
  promote  → if last eval mean >= threshold, set personas.lifecycle_stage
             ('promoted') and stamp promoted_at; snapshot persona_md to
             persona_versions
  deprecate→ set deprecated_at + deprecated_reason; optionally supersede
             by another persona (supersedes_persona_id)
  version  → append-only snapshot of persona_md to persona_versions
             (so edits via the Febrain pipeline can be reverted/diffed)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from supabase import Client, create_client

from ..config import get_settings

log = logging.getLogger(__name__)

EVAL_FN = "persona-eval"
PROMOTE_THRESHOLD = 0.65


class PersonaLifecycle:
    """Lifecycle operations on personas."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        if not self._client:
            self._client = create_client(
                self.settings.supabase_url,
                self.settings.supabase_service_role_key,
            )
        return self._client

    def _edge_url(self) -> str:
        return f"{(self.settings.supabase_url or '').rstrip('/')}/functions/v1/{EVAL_FN}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
        }

    async def eval_persona(
        self,
        persona_slug: str,
        *,
        num_questions: Optional[int] = None,
        threshold: Optional[float] = None,
        create_baseline_if_missing: bool = True,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "persona_slug": persona_slug,
            "create_baseline_if_missing": create_baseline_if_missing,
        }
        if num_questions is not None:
            body["num_questions"] = num_questions
        if threshold is not None:
            body["threshold"] = threshold
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(self._edge_url(), headers=self._headers(), json=body)
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:500]}
                if isinstance(data, dict):
                    data["status_code"] = resp.status_code
                return data
        except Exception as e:
            log.warning(f"persona eval failed for {persona_slug}: {e}")
            return {"error": str(e)}

    async def get_persona(self, slug: str) -> Optional[Dict[str, Any]]:
        try:
            r = (
                self.client.table("personas")
                .select(
                    "id, slug, name, role, home_team, persona_md, status, "
                    "lifecycle_stage, promoted_at, deprecated_at, deprecated_reason, "
                    "supersedes_persona_id, baseline_eval_run_id, quality_score, "
                    "times_used, last_used_at"
                )
                .eq("slug", slug).single().execute()
            )
            return r.data or None
        except Exception as e:
            log.warning(f"get_persona failed for {slug}: {e}")
            return None

    async def last_eval_run(self, persona_slug: str) -> Optional[Dict[str, Any]]:
        """Most recent agent_eval_runs row for this persona's baseline eval."""
        try:
            # First find the baseline eval id
            p = await self.get_persona(persona_slug)
            if not p:
                return None
            eval_row = (
                self.client.table("agent_evals")
                .select("id")
                .eq("persona_id", p["id"])
                .eq("slug", f"eval-{persona_slug}-baseline")
                .maybeSingle()
                .execute()
            )
            if not eval_row.data:
                return None
            eval_id = eval_row.data["id"]
            run = (
                self.client.table("agent_eval_runs")
                .select("id, eval_id, output, passed, created_at")
                .eq("eval_id", eval_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            return run.data[0] if run.data else None
        except Exception as e:
            log.warning(f"last_eval_run failed for {persona_slug}: {e}")
            return None

    async def snapshot_version(self, persona_slug: str) -> Dict[str, Any]:
        """Append-only snapshot of current persona_md to persona_versions."""
        try:
            p = await self.get_persona(persona_slug)
            if not p:
                return {"snapshotted": False, "reason": "persona not found"}

            # Compute next version number
            last = (
                self.client.table("persona_versions")
                .select("version")
                .eq("persona_id", p["id"])
                .order("version", desc=True)
                .limit(1)
                .execute()
            )
            next_version = (last.data[0]["version"] + 1) if last.data else 1

            ins = (
                self.client.table("persona_versions")
                .insert({
                    "persona_id": p["id"],
                    "slug": p["slug"],
                    "version": next_version,
                    "persona_md": p["persona_md"] or "",
                })
                .select("id, version, created_at").single().execute()
            )
            return {"snapshotted": True, **(ins.data or {})}
        except Exception as e:
            log.warning(f"snapshot_version failed for {persona_slug}: {e}")
            return {"snapshotted": False, "error": str(e)}

    async def promote(
        self,
        persona_slug: str,
        *,
        threshold: float = PROMOTE_THRESHOLD,
        require_passed_run: bool = True,
    ) -> Dict[str, Any]:
        """Promote persona to lifecycle_stage='promoted' if last eval passed.

        Snapshots the current persona_md to persona_versions as a side-effect
        so the promotion is auditable.
        """
        p = await self.get_persona(persona_slug)
        if not p:
            return {"promoted": False, "reason": "persona not found"}

        run = await self.last_eval_run(persona_slug)
        if not run:
            return {"promoted": False, "reason": "no eval runs"}
        if require_passed_run and not run.get("passed"):
            return {
                "promoted": False,
                "reason": "last eval did not pass",
                "eval_run_id": run["id"],
                "scores": run.get("output"),
            }

        # Stricter threshold check on the mean (in case run.passed used a
        # lower threshold than the operator wants to promote at).
        output = run.get("output") or {}
        mean = output.get("mean")
        if mean is not None and mean < threshold:
            return {
                "promoted": False,
                "reason": f"mean {mean:.3f} below promote threshold {threshold}",
                "eval_run_id": run["id"],
            }

        # Snapshot then promote
        snap = await self.snapshot_version(persona_slug)
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            self.client.table("personas").update({
                "lifecycle_stage": "promoted",
                "promoted_at": now_iso,
                "baseline_eval_run_id": run["id"],
                "updated_at": now_iso,
            }).eq("id", p["id"]).execute()
        except Exception as e:
            return {"promoted": False, "error": str(e)}

        return {
            "promoted": True,
            "persona_slug": persona_slug,
            "lifecycle_stage": "promoted",
            "promoted_at": now_iso,
            "eval_run_id": run["id"],
            "mean": mean,
            "version_snapshot": snap.get("version"),
        }

    async def deprecate(
        self,
        persona_slug: str,
        *,
        reason: str,
        supersedes_persona_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = await self.get_persona(persona_slug)
        if not p:
            return {"deprecated": False, "reason": "persona not found"}

        supersedes_id: Optional[str] = None
        if supersedes_persona_slug:
            sup = await self.get_persona(supersedes_persona_slug)
            if sup:
                supersedes_id = sup["id"]

        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        updates: Dict[str, Any] = {
            "lifecycle_stage": "deprecated",
            "deprecated_at": now_iso,
            "deprecated_reason": reason[:1000],
            "updated_at": now_iso,
        }
        if supersedes_id:
            updates["supersedes_persona_id"] = supersedes_id

        try:
            self.client.table("personas").update(updates).eq("id", p["id"]).execute()
            return {
                "deprecated": True,
                "persona_slug": persona_slug,
                "deprecated_at": now_iso,
                "supersedes_persona_id": supersedes_id,
            }
        except Exception as e:
            return {"deprecated": False, "error": str(e)}
