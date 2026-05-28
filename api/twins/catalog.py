"""
Workforce OS — Twin Catalog
Read access to the `twin` + `twin_person` tables (cognitive twins of real
executives and operators). Twin creation is in ``api/twins/pipeline.py``.

Twin lifecycle: draft → corpus_ingested → synthesized → evaluated → published
Only `published` twins are exposed by default to end-user Council flows;
drafts are visible to admins for QA.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from ..config import get_settings

log = logging.getLogger(__name__)

# What we consider a "real, consultable twin" — both gates must be satisfied.
PUBLISHED_STATUS = "published"
PUBLIC_AUTHORIZATIONS = ("public_figure",)


class TwinCatalog:
    """Catalog of cognitive twins of real people."""

    def __init__(self) -> None:
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        if not self._client:
            settings = get_settings()
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
        return self._client

    async def list_twins(
        self,
        *,
        twin_kind: Optional[str] = None,
        status: Optional[str] = None,
        include_drafts: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List twins joined with their person record.

        By default returns only published twins. Set include_drafts=True
        for admin/QA views that need to see manifests in progress.
        """
        try:
            q = self.client.table("twin").select(
                "id, person_id, archetype_label, is_composite, status, "
                "eval_scores, reliability_json, schema_json, updated_at"
            ).limit(limit)

            if status:
                q = q.eq("status", status)
            elif not include_drafts:
                q = q.eq("status", PUBLISHED_STATUS)

            result = q.execute()
            twin_rows = result.data or []

            if not twin_rows:
                return []

            # Pull persons in one round-trip
            person_ids = list({t["person_id"] for t in twin_rows if t.get("person_id")})
            persons: Dict[str, Dict[str, Any]] = {}
            if person_ids:
                pr = (
                    self.client.table("twin_person")
                    .select("id, name_public, archetype_label, authorization, notes")
                    .in_("id", person_ids)
                    .execute()
                )
                persons = {p["id"]: p for p in (pr.data or [])}

            out: List[Dict[str, Any]] = []
            for t in twin_rows:
                person = persons.get(t.get("person_id"), {}) or {}
                kind = (t.get("schema_json") or {}).get("twin_kind")
                if twin_kind and kind != twin_kind:
                    continue
                out.append(
                    {
                        "id": t["id"],
                        "person_id": t["person_id"],
                        "name_public": person.get("name_public"),
                        "authorization": person.get("authorization"),
                        "archetype_label": t.get("archetype_label")
                        or person.get("archetype_label"),
                        "twin_kind": kind,
                        "status": t.get("status"),
                        "num_sources": len((t.get("schema_json") or {}).get("sources") or []),
                        "has_synthesis": bool(
                            (t.get("schema_json") or {}).get("synthesized")
                        ),
                        "eval_passed": _last_eval_passed(t.get("eval_scores")),
                    }
                )
            return out
        except Exception as e:
            log.warning(f"Twin list failed: {e}")
            return []

    async def get_twin(self, twin_id: str) -> Optional[Dict[str, Any]]:
        """Full twin record + person + ingestion status."""
        try:
            tr = (
                self.client.table("twin")
                .select("*")
                .eq("id", twin_id)
                .single()
                .execute()
            )
            if not tr.data:
                return None
            twin = tr.data

            person: Dict[str, Any] = {}
            if twin.get("person_id"):
                pr = (
                    self.client.table("twin_person")
                    .select("*")
                    .eq("id", twin["person_id"])
                    .single()
                    .execute()
                )
                person = pr.data or {}

            status = await self.get_status(twin_id)

            return {
                "twin": twin,
                "person": person,
                "pipeline_status": status,
            }
        except Exception as e:
            log.warning(f"Twin get failed for {twin_id}: {e}")
            return None

    async def get_status(self, twin_id: str) -> Dict[str, Any]:
        """Pipeline status: how many chunks, how many holdouts, synth state, eval state."""
        try:
            tr = (
                self.client.table("twin")
                .select("person_id, schema_json, status, eval_scores")
                .eq("id", twin_id)
                .single()
                .execute()
            )
            if not tr.data:
                return {"error": "twin not found"}

            person_id = tr.data.get("person_id")
            schema_json = tr.data.get("schema_json") or {}

            chunks_total = 0
            chunks_holdout = 0
            chunks_embedded = 0
            if person_id:
                cr = (
                    self.client.table("twin_corpus_chunk")
                    .select("id, holdout, embedding", count="exact")
                    .eq("person_id", person_id)
                    .execute()
                )
                rows = cr.data or []
                chunks_total = cr.count or len(rows)
                chunks_holdout = sum(1 for r in rows if r.get("holdout"))
                chunks_embedded = sum(1 for r in rows if r.get("embedding") is not None)

            eval_runs = 0
            last_passed = None
            try:
                er = (
                    self.client.table("twin_eval_run")
                    .select("passed, created_at", count="exact")
                    .eq("twin_id", twin_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                eval_runs = er.count or 0
                last_passed = (er.data[0]["passed"] if er.data else None)
            except Exception:
                pass

            num_sources = len(schema_json.get("sources") or [])
            synthesized = bool(schema_json.get("synthesized"))

            return {
                "twin_id": twin_id,
                "status": tr.data.get("status"),
                "num_sources": num_sources,
                "chunks_total": chunks_total,
                "chunks_embedded": chunks_embedded,
                "chunks_holdout": chunks_holdout,
                "synthesized": synthesized,
                "synthesized_model": schema_json.get("synthesized_model"),
                "synthesized_at": schema_json.get("synthesized_at"),
                "eval_runs": eval_runs,
                "last_eval_passed": last_passed,
                "ready_to_publish": (
                    synthesized and last_passed is True and chunks_embedded > 0
                ),
            }
        except Exception as e:
            log.warning(f"Twin status failed for {twin_id}: {e}")
            return {"error": str(e)}


def _last_eval_passed(eval_scores: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not eval_scores or not isinstance(eval_scores, dict):
        return None
    return eval_scores.get("passed") if "passed" in eval_scores else None
