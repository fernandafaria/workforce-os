"""
Workforce OS — Twin Creation Pipeline (Stages 2-3)

Stage 2 — Corpus ingestion: fetch URL sources of a twin, chunk, embed,
          store in twin_corpus_chunk.
Stage 3 — Schema synthesis: read corpus, call Claude Opus to produce a
          rich cognitive schema, merge into twin.schema_json.

Each stage is implemented as a Supabase Edge Function (see
``supabase/functions/twin-corpus-ingest/`` and ``twin-synthesize/``) so
the work runs close to the data and the LLM/embedding secrets stay in
Supabase. This module is a thin Python wrapper that invokes those
functions over HTTP and returns the parsed result.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

INGEST_FN = "twin-corpus-ingest"
SYNTHESIZE_FN = "twin-synthesize"


class TwinPipeline:
    """Invoke twin pipeline stages running as Supabase edge functions."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _edge_url(self, fn_slug: str) -> str:
        base = (self.settings.supabase_url or "").rstrip("/")
        return f"{base}/functions/v1/{fn_slug}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
        }

    async def ingest(
        self,
        twin_id: str,
        *,
        max_sources: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Stage 2 — Ingest corpus from twin's source URLs.

        Idempotent: skips URLs already present in twin_corpus_chunk unless
        ``force=True``.
        """
        body: Dict[str, Any] = {"twin_id": twin_id, "force": force}
        if max_sources is not None:
            body["max_sources"] = max_sources

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    self._edge_url(INGEST_FN),
                    headers=self._headers(),
                    json=body,
                )
                return _safe_json(resp)
        except Exception as e:
            log.warning(f"Twin ingest failed for {twin_id}: {e}")
            return {"error": str(e)}

    async def synthesize(self, twin_id: str) -> Dict[str, Any]:
        """Stage 3 — Synthesize cognitive schema_json via Claude Opus.

        Requires at least one embedded corpus chunk (call ingest first).
        """
        body = {"twin_id": twin_id}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    self._edge_url(SYNTHESIZE_FN),
                    headers=self._headers(),
                    json=body,
                )
                return _safe_json(resp)
        except Exception as e:
            log.warning(f"Twin synthesize failed for {twin_id}: {e}")
            return {"error": str(e)}


def _safe_json(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
        if not isinstance(data, dict):
            return {"status_code": resp.status_code, "raw": data}
        data["status_code"] = resp.status_code
        return data
    except Exception:
        return {"status_code": resp.status_code, "raw": resp.text[:500]}
