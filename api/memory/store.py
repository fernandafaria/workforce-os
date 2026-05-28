"""
Workforce OS — Memory Store
Longitudinal memory for decisions, observations, and patterns.
Uses Supabase (observational_memory table).
"""

from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from ..config import get_settings

log = logging.getLogger(__name__)


class MemoryStore:
    """Persistent memory for user decisions and observations."""
    
    def __init__(self):
        self._client = None
    
    @property
    def client(self):
        if not self._client:
            from supabase import create_client
            settings = get_settings()
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
        return self._client
    
    async def add(
        self,
        user_id: str,
        observation: str,
        category: str = "decision",
    ) -> Dict[str, Any]:
        """Store a new memory."""
        try:
            result = self.client.table("observational_memory").insert({
                "user_id": user_id,
                "observation": observation,
                "confidence": 0.7,
                "source_conversation_ids": [],
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
            
            return {"status": "stored", "id": result.data[0]["id"] if result.data else None}
        except Exception as e:
            log.error(f"Memory store failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_user_memories(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieve user's memories, newest first."""
        try:
            result = self.client.table("observational_memory") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            return result.data or []
        except Exception as e:
            log.error(f"Memory retrieval failed: {e}")
            return []
    
    async def search_similar(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search in user memories."""
        try:
            result = self.client.rpc(
                "semantic_search_memories",
                {"query_text": query, "user_id": user_id, "match_limit": limit},
            ).execute()
            
            return result.data or []
        except Exception as e:
            log.warning(f"Semantic memory search not available: {e}")
            # Fallback: text search
            all_memories = await self.get_user_memories(user_id, 50)
            query_lower = query.lower()
            return [
                m for m in all_memories
                if query_lower in m.get("observation", "").lower()
            ][:limit]
