"""
Workforce OS — Dynamic Agent Spawner (Python client)
Thin httpx wrapper that invokes the ``agent-spawn`` Supabase edge function
where the actual LLM + Voyage work happens. Lives next to the catalog so
the orchestrator can import either side independently.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

SPAWN_FN = "agent-spawn"


class AgentSpawner:
    """Invokes the agent-spawn edge function."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _url(self) -> str:
        return f"{(self.settings.supabase_url or '').rstrip('/')}/functions/v1/{SPAWN_FN}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
        }

    async def spawn(
        self,
        *,
        question: str,
        expertise_gap: str,
        context: Optional[str] = None,
        user_id: Optional[str] = None,
        parent_team_slug: Optional[str] = None,
        parent_persona_slugs: Optional[List[str]] = None,
        ttl_hours: Optional[int] = None,
        max_uses: Optional[int] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "question": question,
            "expertise_gap": expertise_gap,
        }
        if context is not None:
            body["context"] = context
        if user_id:
            body["user_id"] = user_id
        if parent_team_slug:
            body["parent_team_slug"] = parent_team_slug
        if parent_persona_slugs:
            body["parent_persona_slugs"] = parent_persona_slugs
        if ttl_hours is not None:
            body["ttl_hours"] = ttl_hours
        if max_uses is not None:
            body["max_uses"] = max_uses

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(self._url(), headers=self._headers(), json=body)
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:500]}
                if isinstance(data, dict):
                    data["status_code"] = resp.status_code
                return data
        except Exception as e:
            log.warning(f"Agent spawn failed: {e}")
            return {"error": str(e), "status_code": -1}
