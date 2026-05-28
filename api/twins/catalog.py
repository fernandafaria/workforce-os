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

# Twins that have passed eval can be invited into a Council session.
# `production` would require an explicit human promotion beyond eval_passed.
CONSULTABLE_STATUSES = ("eval_passed", "production")

# Model used to interview/eval/answer-as twins. Twins were synthesized by
# Opus and reproduce voice best when answered by the same family.
TWIN_MODEL_REF = "claude-opus-4-7"


def build_twin_system_prompt(
    synth: Dict[str, Any], name_public: str
) -> str:
    """Construct a system prompt that makes an LLM answer *as* this twin.

    Used both by Council (when a twin participates) and by the eval/interview
    edge functions. Single source of truth for what 'speaking as' a twin
    means in this codebase.
    """
    voice = synth.get("voice", {}) or {}
    return (
        f"Você responde *como* {name_public}. Voz, padrões de decisão e "
        f"vieses devem refletir essa pessoa específica, não uma média. "
        f"Não invente fatos sobre quem você não é.\n\n"
        f"IDENTITY:\n{synth.get('identity', '')}\n\n"
        f"VOICE:\n- tone: {voice.get('tone', '')}\n"
        f"- register: {voice.get('register', '')}\n"
        f"- language: {voice.get('language', '')}\n"
        f"- quirks: {voice.get('language_quirks', [])}\n\n"
        f"DECISION PATTERNS:\n{synth.get('decision_patterns', [])}\n\n"
        f"BIASES:\n{synth.get('biases', [])}\n\n"
        f"SIGNATURE PHRASES (use naturalmente, sem forçar):\n"
        f"{synth.get('signature_phrases', [])}\n\n"
        f"DO:\n{synth.get('do', [])}\n\n"
        f"DONT:\n{synth.get('dont', [])}\n\n"
        f"Responda em 2-4 parágrafos. Sem lista numerada burocrática."
    )


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


    async def load_for_council(
        self, twin_ids: List[str], *, allow_drafts: bool = False
    ) -> List[Dict[str, Any]]:
        """Load twins ready to participate in a Council session.

        By default only returns twins in ``eval_passed`` or ``production``
        status whose ``schema_json.synthesized`` block exists. Each entry
        is shaped like an agent participant so the orchestrator can mix
        them with persona agents in a single Send[]-style fan-out.

        Returns rows with: ``twin_id, slug, name, system_prompt, model_ref,
        kind='twin'``. Missing/unfit twin_ids are silently dropped — the
        caller (Council) decides whether to surface that to the user.
        """
        if not twin_ids:
            return []
        try:
            q = (
                self.client.table("twin")
                .select("id, person_id, status, schema_json, archetype_label")
                .in_("id", twin_ids)
            )
            if not allow_drafts:
                q = q.in_("status", list(CONSULTABLE_STATUSES))
            twin_rows = (q.execute().data) or []
            if not twin_rows:
                return []

            person_ids = list({t["person_id"] for t in twin_rows if t.get("person_id")})
            persons: Dict[str, Dict[str, Any]] = {}
            if person_ids:
                pr = (
                    self.client.table("twin_person")
                    .select("id, name_public, authorization")
                    .in_("id", person_ids)
                    .execute()
                )
                persons = {p["id"]: p for p in (pr.data or [])}

            out: List[Dict[str, Any]] = []
            for t in twin_rows:
                schema = t.get("schema_json") or {}
                synth = schema.get("synthesized") or {}
                if not synth:
                    log.info(f"twin {t['id']} skipped: not synthesized")
                    continue
                person = persons.get(t.get("person_id"), {}) or {}
                name_public = person.get("name_public") or t.get("archetype_label") or "Unknown"

                out.append(
                    {
                        "twin_id": t["id"],
                        "slug": t["id"],  # used as primary key in framed_prompts/responses
                        "name": name_public,
                        "system_prompt": build_twin_system_prompt(synth, name_public),
                        "model_ref": TWIN_MODEL_REF,
                        "kind": "twin",
                        "source": f"Cognitive twin: {name_public}",
                        "status": t.get("status"),
                    }
                )
            return out
        except Exception as e:
            log.warning(f"Twin load_for_council failed: {e}")
            return []


def _last_eval_passed(eval_scores: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not eval_scores or not isinstance(eval_scores, dict):
        return None
    return eval_scores.get("passed") if "passed" in eval_scores else None
