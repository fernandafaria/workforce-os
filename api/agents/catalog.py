"""
Workforce OS — Agent Catalog
Supabase queries for persona discovery, loading, and matching.
"""

from functools import lru_cache
from typing import Optional, List, Dict, Any
import logging

from supabase import create_client, Client

from ..config import get_settings

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
        """Total personas available."""
        try:
            result = self.client.table("personas").select("slug", count="exact").execute()
            return result.count or 150
        except Exception:
            return 150
    
    async def list_all(self, team: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """List all personas, optionally filtered by team."""
        try:
            query = self.client.table("personas").select(
                "slug, handle, name, home_team, domains, persona_md"
            ).not_("persona_md", "is", "null")
            
            if team:
                query = query.eq("home_team", team)
            
            result = query.limit(limit).execute()
            
            return [
                {
                    "slug": r["slug"],
                    "handle": r["handle"],
                    "name": r["name"],
                    "home_team": r["home_team"],
                    "domains": r.get("domains", []),
                    "prompt_length": len(r.get("persona_md", "")),
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
        """Semantic match: pgvector similarity search + domain rules + LLM refine."""
        matches = []
        
        # 1. Domain rule matching
        query_lower = query.lower()
        matched_slugs = set()
        for domain, slugs in DOMAIN_AGENT_MAP.items():
            if domain in query_lower:
                for s in slugs:
                    matched_slugs.add(s)
        
        # 2. pgvector semantic search
        try:
            result = self.client.rpc(
                "match_personas",
                {"query_text": query, "match_limit": top_k},
            ).execute()
            
            if result.data:
                for r in result.data:
                    matches.append({
                        "slug": r["slug"],
                        "handle": r.get("handle", f"@{r['slug']}"),
                        "name": r.get("name", r["slug"]),
                        "home_team": r.get("home_team", ""),
                        "score": r.get("similarity", 0.5),
                        "source": "semantic",
                    })
        except Exception as e:
            log.warning(f"Semantic search failed: {e}")
        
        # 3. Boost domain-matched agents
        for m in matches:
            if m["slug"] in matched_slugs:
                m["score"] = min(1.0, m["score"] + 0.2)
                m["source"] = "semantic+domain"
        
        # 4. Add domain-matched agents not in semantic results
        for slug in matched_slugs:
            if not any(m["slug"] == slug for m in matches):
                try:
                    result = self.client.table("personas").select("slug, handle, name, home_team").eq("slug", slug).single().execute()
                    if result.data:
                        matches.append({
                            "slug": result.data["slug"],
                            "handle": result.data.get("handle", f"@{slug}"),
                            "name": result.data.get("name", slug),
                            "home_team": result.data.get("home_team", ""),
                            "score": 0.6,
                            "source": "domain_rule",
                        })
                except Exception:
                    pass
        
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
