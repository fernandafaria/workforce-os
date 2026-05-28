"""
Workforce OS — Agent Catalog
Supabase queries for persona discovery, loading, and matching.
"""

from functools import lru_cache
from typing import Optional, List, Dict, Any
import logging

from supabase import create_client, Client

from ..config import get_settings
from ..knowledge.embeddings import embed_query

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Domain → Agent Mapping (deterministic rules)
# ═══════════════════════════════════════════════════════════════════════════

DOMAIN_AGENT_MAP: Dict[str, List[str]] = {
    "pricing": ["patrick-campbell", "bobby-pinero"],
    "monetization": ["patrick-campbell", "bill-gurley"],
    "positioning": ["april-dunford"],
    "gtm": ["april-dunford", "rand-fishkin"],
    "strategy": ["roger-martin", "rumelt"],
    "finance": ["bobby-pinero", "ruth-porat", "bill-gurley"],
    "growth": ["elena-verna", "hiten-shah"],
    "marketing": ["amanda-natividad", "seth-godin"],
    "sales": ["chris-voss", "frank", "sam-blond"],
    "product": ["marty-cagan", "lenny"],
    "tech": ["simon-willison", "tim-cook", "harrison-chase"],
    "ai": ["simon-willison", "andrej-karpathy", "harrison-chase"],
    "operations": ["matt"],
    "people": ["claire-hughes-johnson", "molly"],
    "org": ["claire-hughes-johnson", "molly"],
    "fundraising": ["paul-graham", "naval-ravikant", "bill-gurley"],
    "compliance": ["claudinei-vieira"],
    "lgpd": ["claudinei-vieira"],
    "industry": ["carlos-eduardo-boechat"],
    "brazil": ["joca-torres", "claudinei-vieira"],
    "risk": ["ruth-porat", "rumelt"],
    "negotiation": ["chris-voss", "bill-gurley"],
}


class AgentCatalog:
    """Catalog of 150+ Febrain personas via Supabase."""
    
    def __init__(self):
        self._client: Optional[Client] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
    
    @property
    def client(self) -> Client:
        if not self._client:
            settings = get_settings()
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
        return self._client
    
    async def count(self) -> int:
        """Total canonical personas available."""
        try:
            result = self.client.table("personas").select(
                "slug", count="exact"
            ).eq("status", "canonical").execute()
            return result.count or 0
        except Exception as e:
            log.warning(f"Persona count failed: {e}")
            return 0
    
    async def list_all(self, team: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """List all personas (status='canonical'), optionally filtered by team."""
        try:
            query = self.client.table("personas").select(
                "slug, handle, name, home_team, domains, persona_md, role"
            ).eq("status", "canonical")

            if team:
                query = query.eq("home_team", team)

            result = query.limit(limit).execute()

            return [
                {
                    "slug": r["slug"],
                    "handle": r["handle"],
                    "name": r["name"],
                    "home_team": r["home_team"],
                    "role": r.get("role"),
                    "domains": r.get("domains") or [],
                    "prompt_length": len(r.get("persona_md") or ""),
                }
                for r in (result.data or [])
            ]
        except Exception as e:
            log.warning(f"Supabase personas query failed: {e}")
            return []
    
    async def get_prompt(self, slug: str) -> Optional[str]:
        """Load full SOUL/prompt for a persona."""
        try:
            result = self.client.table("personas").select("persona_md").eq("slug", slug).single().execute()
            return result.data.get("persona_md") if result.data else None
        except Exception as e:
            log.warning(f"Failed to load persona {slug}: {e}")
            return None
    
    async def match(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Hybrid match: pgvector semantic similarity (Voyage) + domain rules.

        Calls the canonical `match_personas(query_embedding, match_threshold,
        match_count, p_team_slug, p_user_id)` RPC in Supabase, which requires
        a real Voyage embedding of the query and filters status='canonical'.
        """
        matches: List[Dict[str, Any]] = []

        # 1. Deterministic domain rules — boost the agents we know belong here
        query_lower = query.lower()
        matched_slugs: set = set()
        for domain, slugs in DOMAIN_AGENT_MAP.items():
            if domain in query_lower:
                for s in slugs:
                    matched_slugs.add(s)

        # 2. Embed query (Voyage) and call semantic RPC
        try:
            query_embedding = await embed_query(query)
            if query_embedding:
                result = self.client.rpc(
                    "match_personas",
                    {
                        "query_embedding": query_embedding,
                        "match_threshold": 0.50,
                        "match_count": top_k * 2,
                    },
                ).execute()

                for r in (result.data or []):
                    matches.append({
                        "slug": r["slug"],
                        "handle": r.get("handle") or f"@{r['slug']}",
                        "name": r.get("name") or r["slug"],
                        "home_team": r.get("home_team") or "",
                        "role": r.get("role"),
                        "score": float(r.get("similarity") or 0.0),
                        "source": "semantic",
                    })
        except Exception as e:
            log.warning(f"Semantic search via match_personas failed: {e}")

        # 3. Boost domain-matched agents already present
        for m in matches:
            if m["slug"] in matched_slugs:
                m["score"] = min(1.0, m["score"] + 0.20)
                m["source"] = "semantic+domain"

        # 4. Inject domain-matched agents missing from semantic results
        for slug in matched_slugs:
            if any(m["slug"] == slug for m in matches):
                continue
            try:
                r = self.client.table("personas").select(
                    "slug, handle, name, home_team, role"
                ).eq("slug", slug).eq("status", "canonical").single().execute()
                if r.data:
                    matches.append({
                        "slug": r.data["slug"],
                        "handle": r.data.get("handle") or f"@{slug}",
                        "name": r.data.get("name") or slug,
                        "home_team": r.data.get("home_team") or "",
                        "role": r.data.get("role"),
                        "score": 0.65,
                        "source": "domain_rule",
                    })
            except Exception:
                continue

        matches.sort(key=lambda m: m["score"], reverse=True)
        return matches[:top_k]
    
    async def search(self, query: str, team: Optional[str] = None) -> List[Dict[str, Any]]:
        """Text search across persona names, handles, and domains."""
        try:
            query_term = f"%{query}%"
            q = self.client.table("personas").select(
                "slug, handle, name, home_team, domains"
            ).or_(f"name.ilike.{query_term},handle.ilike.{query_term}")
            
            if team:
                q = q.eq("home_team", team)
            
            result = q.limit(20).execute()
            return result.data or []
        except Exception as e:
            log.warning(f"Search failed: {e}")
            return []
