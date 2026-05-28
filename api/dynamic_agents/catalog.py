"""
Workforce OS — Dynamic Agents Catalog
Read + lifecycle operations on the `dynamic_agents` table.

Lifecycle:
  active  → (spawn-agent edge function, this PR)
  active  → dissolved  (TTL hit, max_uses exceeded, or manual)
  active  → promoted   (manual: a good dynamic agent becomes a persona)

Twin status check: ('active', 'dissolved', 'promoted')
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from ..config import get_settings

log = logging.getLogger(__name__)

ACTIVE = "active"
DISSOLVED = "dissolved"
PROMOTED = "promoted"


class DynamicAgentsCatalog:
    """Read + lifecycle for spawned dynamic agents."""

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

    async def list_active(
        self,
        *,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Active dynamic agents that haven't expired yet.

        If user_id is given, scopes to that user's agents only. Otherwise
        returns all active rows (admin view).
        """
        try:
            q = (
                self.client.table("dynamic_agents")
                .select(
                    "id, user_id, name, description, icon, parent_agent_id, "
                    "parent_persona_id, spawn_reason, model, status, "
                    "times_used, max_uses, expires_at, created_at"
                )
                .eq("status", ACTIVE)
                .order("created_at", desc=True)
                .limit(limit)
            )
            if user_id:
                q = q.eq("user_id", user_id)
            result = q.execute()
            now_iso = _now_iso()
            return [
                r for r in (result.data or [])
                if not r.get("expires_at") or r["expires_at"] > now_iso
            ]
        except Exception as e:
            log.warning(f"Dynamic agents list failed: {e}")
            return []

    async def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        try:
            r = (
                self.client.table("dynamic_agents")
                .select("*")
                .eq("id", agent_id)
                .single()
                .execute()
            )
            return r.data or None
        except Exception as e:
            log.warning(f"Dynamic agent get failed for {agent_id}: {e}")
            return None

    async def dissolve(self, agent_id: str, reason: str = "manual") -> Dict[str, Any]:
        """Set a single agent to status='dissolved'."""
        try:
            upd = (
                self.client.table("dynamic_agents")
                .update({"status": DISSOLVED, "dissolved_at": _now_iso()})
                .eq("id", agent_id)
                .select("id, status, dissolved_at")
                .execute()
            )
            if not upd.data:
                return {"dissolved": False, "reason": "agent not found"}
            return {"dissolved": True, "agent_id": agent_id, "trigger": reason}
        except Exception as e:
            log.warning(f"Dissolve failed for {agent_id}: {e}")
            return {"dissolved": False, "error": str(e)}

    async def dissolve_expired(self) -> Dict[str, Any]:
        """Bulk-dissolve agents past their TTL or over max_uses.

        Suitable as a cron target (pg_cron) or as a manual endpoint while
        we don't have one running.
        """
        try:
            now_iso = _now_iso()
            # Expired by time
            by_ttl = (
                self.client.table("dynamic_agents")
                .update({"status": DISSOLVED, "dissolved_at": now_iso})
                .eq("status", ACTIVE)
                .lt("expires_at", now_iso)
                .select("id")
                .execute()
            )
            # Note: max_uses gate is enforced at consume time; we don't bulk
            # dissolve by times_used here because supabase-py can't express
            # "where times_used >= max_uses" without an RPC.
            return {
                "dissolved_by_ttl": len(by_ttl.data or []),
                "ran_at": now_iso,
            }
        except Exception as e:
            log.warning(f"Bulk dissolve failed: {e}")
            return {"error": str(e)}

    async def record_use(self, agent_id: str) -> Dict[str, Any]:
        """Increment ``times_used``. If we hit max_uses, dissolve.

        Called by Council orchestrator when a dynamic agent participates
        in a session (next PR).
        """
        try:
            cur = await self.get(agent_id)
            if not cur:
                return {"recorded": False, "reason": "not found"}
            times_used = (cur.get("times_used") or 0) + 1
            max_uses = cur.get("max_uses") or 0
            updates: Dict[str, Any] = {"times_used": times_used}
            if max_uses and times_used >= max_uses:
                updates["status"] = DISSOLVED
                updates["dissolved_at"] = _now_iso()
            self.client.table("dynamic_agents").update(updates).eq("id", agent_id).execute()
            return {
                "recorded": True,
                "agent_id": agent_id,
                "times_used": times_used,
                "dissolved": updates.get("status") == DISSOLVED,
            }
        except Exception as e:
            log.warning(f"record_use failed for {agent_id}: {e}")
            return {"recorded": False, "error": str(e)}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
