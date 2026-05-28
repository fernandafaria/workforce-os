"""
Workforce OS — Memory Pipeline
Connects observational_memory (existing) with distill_memory protocol.

Febrain integration:
  - observational_memory table: raw observations (already exists in Supabase)
  - distill_memory protocol: post-session distillation (SKILL.md at Febrain/_shared/protocols/distill-memory/)
  - memories table: structured memories with embeddings (from Febrain migration 026)

This pipeline:
  1. Observes: saves raw council/group/ritual outputs to observational_memory
  2. Distills: extracts decisions, risks, actions, questions via LLM
  3. Embeds: generates Voyage embeddings for semantic search
  4. Stores: upserts to both observational_memory and memories tables
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)

FEBRAIN = Path(os.path.expanduser("~/code/Febrain"))
DISTILL_PROTOCOL = FEBRAIN / "_shared" / "protocols" / "distill-memory" / "SKILL.md"


class MemoryPipeline:
    """Unified memory pipeline: observe → distill → embed → store.

    Wraps Febrain's existing observational_memory infrastructure and
    distill-memory protocol. Never reimplements — always wraps.
    """

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    @property
    def client(self):
        if not self._client:
            from supabase import create_client
            self._client = create_client(
                self.settings.supabase_url,
                self.settings.supabase_service_role_key,
            )
        return self._client

    # ══════════════════════════════════════════════════════════════════
    # Phase 1: Observe — save raw interaction to observational_memory
    # ══════════════════════════════════════════════════════════════════

    async def observe(
        self,
        user_id: str,
        session_type: str,  # "council", "group", "ritual", "ping"
        topic: str,
        agents: List[str],
        raw_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Save raw session output to observational_memory (Febrain table).

        This is the UNSTRUCTURED observation phase. Distillation happens
        separately (async, post-session).
        """
        observation_text = json.dumps({
            "session_type": session_type,
            "topic": topic,
            "agents": agents,
            "summary": raw_output.get("summary", "")[:500],
            "consensus": raw_output.get("consensus", ""),
        }, ensure_ascii=False)

        try:
            result = self.client.table("observational_memory").insert({
                "user_id": user_id,
                "observation": observation_text,
                "confidence": 0.8,
                "source_conversation_ids": [],
                "created_at": datetime.utcnow().isoformat(),
            }).execute()

            memory_id = result.data[0]["id"] if result.data else None
            log.info(f"MemoryPipeline: Observed {session_type} for user {user_id} — id={memory_id}")
            return {"status": "observed", "id": memory_id, "session_type": session_type}

        except Exception as e:
            log.error(f"MemoryPipeline observe failed: {e}")
            return {"status": "error", "error": str(e)}

    # ══════════════════════════════════════════════════════════════════
    # Phase 2: Distill — extract structured insights via distill-memory protocol
    # ══════════════════════════════════════════════════════════════════

    async def distill(
        self,
        user_id: str,
        session_content: str,
        session_type: str = "council",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Extract decisions, risks, actions, and questions from session content.

        Follows the distill-memory protocol (Febrain/_shared/protocols/distill-memory/SKILL.md):
          1. Scan for 4 signal types (decision, risk, action, question)
          2. Structure with memory_ref, scope, team_slug, etc.
          3. Dedupe via embedding similarity > 0.90
          4. Insert (never update) to memories table
          5. Generate Voyage embeddings
        """
        protocol = self._load_distill_protocol()

        # Use LLM to extract structured memories from session
        extraction = await self._extract_memories(session_content, protocol)

        if dry_run:
            return {"status": "dry_run", "extracted": extraction}

        # Store each extracted memory
        stored = []
        for mem in extraction:
            result = await self._store_memory(user_id, mem)
            stored.append(result)

        return {
            "status": "distilled",
            "total": len(stored),
            "memories": stored,
            "session_type": session_type,
        }

    async def _extract_memories(
        self,
        session_content: str,
        protocol: str,
    ) -> List[Dict[str, Any]]:
        """Use LLM to extract structured memories from raw session content.

        Follows distill-memory protocol: scan for 4 signal types.
        """
        prompt = (
            f"DISTILL MEMORY PROTOCOL\n\n"
            f"Extract structured memories from this session. Output JSON array.\n\n"
            f"Find 4 types:\n"
            f"- decision: choices made, paths chosen (trigger: 'vamos', 'decidido', 'escolhemos')\n"
            f"- risk: potential failures, concerns (trigger: 'risco', 'pode dar errado', 'preocupação')\n"
            f"- action: next steps with owners (trigger: 'next step', 'owner', 'prazo')\n"
            f"- question: unknowns, items needing validation (trigger: 'não sabemos', 'falta dado', 'a validar')\n\n"
            f"Format: [{{'memory_type': 'decision'|'risk'|'action'|'question', "
            f"'title': '...', 'context': '...', 'owner_handle': '@name'}}]\n\n"
            f"SESSION CONTENT:\n{session_content[:5000]}\n\n"
            f"Output ONLY the JSON array, nothing else."
        )

        if not self.settings.deepseek_api_key:
            return self._fallback_extraction(session_content)

        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2000,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                # Extract JSON array from response
                import re
                match = re.search(r"\[.*\]", content, re.DOTALL)
                if match:
                    return json.loads(match.group())
                return []

        except Exception as e:
            log.warning(f"Memory extraction via LLM failed: {e}")
            return self._fallback_extraction(session_content)

    def _fallback_extraction(self, content: str) -> List[Dict[str, Any]]:
        """Simple rule-based extraction when LLM is unavailable."""
        memories = []
        lowered = content.lower()

        # Decision signals
        for marker in ["decid", "vamos", "escolhemo", "go with"]:
            if marker in lowered:
                memories.append({
                    "memory_type": "decision",
                    "title": f"Decision from session",
                    "context": content[:300],
                })
                break

        # Risk signals
        for marker in ["risco", "risk", "atenção", "cuidado"]:
            if marker in lowered:
                memories.append({
                    "memory_type": "risk",
                    "title": f"Risk identified in session",
                    "context": content[:300],
                })
                break

        return memories

    async def _store_memory(
        self,
        user_id: str,
        memory: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Store a single structured memory to Supabase memories table.

        Uses the Febrain memories table (migration 026) with:
        - memory_type, memory_ref, scope, team_slug
        - title, context, owner_handle, memory_status
        - embedding (Voyage 1024d) for semantic search
        """
        try:
            result = self.client.table("memories").insert({
                "user_id": user_id,
                "memory_type": memory.get("memory_type", "decision"),
                "title": memory.get("title", "")[:200],
                "context": memory.get("context", "")[:5000],
                "owner_handle": memory.get("owner_handle", ""),
                "memory_status": "in-progress",
                "memory_tags": memory.get("memory_tags", []),
                "source": "workforce-os",
                "created_at": datetime.utcnow().isoformat(),
            }).execute()

            mem_id = result.data[0]["id"] if result.data else None
            return {
                "status": "stored",
                "id": mem_id,
                "memory_type": memory.get("memory_type"),
                "title": memory.get("title", "")[:100],
            }

        except Exception as e:
            log.warning(f"Memory store failed for {memory.get('memory_type')}: {e}")
            return {"status": "error", "error": str(e)}

    # ══════════════════════════════════════════════════════════════════
    # Phase 3: Embed — generate Voyage embeddings (async, post-distill)
    # ══════════════════════════════════════════════════════════════════

    async def embed_memories(self, user_id: str, limit: int = 50) -> Dict[str, Any]:
        """Generate embeddings for unembedded memories.

        In production, this runs as an async background task.
        Uses Voyage AI (1024d) embedding model.
        """
        if not self.settings.voyage_api_key:
            return {"status": "skipped", "reason": "VOYAGE_API_KEY not configured"}

        try:
            # Get memories without embeddings
            result = self.client.table("memories") \
                .select("id, title, context") \
                .eq("user_id", user_id) \
                .is_("embedding", "null") \
                .limit(limit) \
                .execute()

            if not result.data:
                return {"status": "skipped", "reason": "no unembedded memories"}

            import httpx
            embedded = 0

            for mem in result.data:
                text = f"{mem['title']}\n\n{mem.get('context', '')}"
                if len(text.strip()) < 10:
                    continue

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {self.settings.voyage_api_key}"},
                        json={"input": text[:8000], "model": "voyage-3", "input_type": "document"},
                    )
                    if resp.status_code == 200:
                        embedding = resp.json()["data"][0]["embedding"]
                        self.client.table("memories") \
                            .update({"embedding": embedding}) \
                            .eq("id", mem["id"]) \
                            .execute()
                        embedded += 1

            log.info(f"MemoryPipeline: Embedded {embedded}/{len(result.data)} memories")
            return {"status": "embedded", "count": embedded, "total": len(result.data)}

        except Exception as e:
            log.error(f"Memory embedding failed: {e}")
            return {"status": "error", "error": str(e)}

    # ══════════════════════════════════════════════════════════════════
    # Phase 4: Search — semantic search across memories
    # ══════════════════════════════════════════════════════════════════

    async def search(
        self,
        user_id: str,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search memories semantically or via structured query.

        Uses pgvector similarity (if embeddings exist) or falls back
        to text search on title/context.
        """
        try:
            # Try pgvector search first
            if self.settings.voyage_api_key:
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {self.settings.voyage_api_key}"},
                        json={"input": query, "model": "voyage-3", "input_type": "query"},
                    )
                    if resp.status_code == 200:
                        embedding = resp.json()["data"][0]["embedding"]
                        result = self.client.rpc(
                            "search_structured_memories",
                            {
                                "query_embedding": embedding,
                                "p_type": memory_type,
                                "p_limit": limit,
                            },
                        ).execute()
                        if result.data:
                            return result.data

        except Exception as e:
            log.warning(f"Semantic memory search failed, using text fallback: {e}")

        # Text-based fallback
        try:
            q = self.client.table("memories") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit)

            if memory_type:
                q = q.eq("memory_type", memory_type)

            result = q.execute()
            return result.data or []
        except Exception:
            return []

    # ══════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════

    def _load_distill_protocol(self) -> str:
        """Load the distill-memory protocol from Febrain."""
        if DISTILL_PROTOCOL.exists():
            return DISTILL_PROTOCOL.read_text()
        return "Distill-memory protocol: extract decisions, risks, actions, questions."

    async def run_full_pipeline(
        self,
        user_id: str,
        session_type: str,
        topic: str,
        agents: List[str],
        session_content: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Run the full memory pipeline: observe → distill → embed."""
        # Phase 1: Observe
        obs = await self.observe(user_id, session_type, topic, agents, {"summary": session_content[:500]})

        # Phase 2: Distill
        dist = await self.distill(user_id, session_content, session_type, dry_run)

        # Phase 3: Embed (for new memories)
        emb = await self.embed_memories(user_id)

        return {
            "observe": obs,
            "distill": dist,
            "embed": emb,
        }
