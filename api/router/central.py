"""
Workforce OS — Central Router
Routes CEO questions to the best specialist agents.

Strategy: Hybrid
  1. pgvector semantic similarity (Voyage voyage-4, 1024d)
  2. Deterministic domain rules (DOMAIN_AGENT_MAP)
  3. Team diversity in top-k (avoid 3 agents from same home_team)

Routing is delegated to AgentCatalog.match() which calls the canonical
match_personas() RPC in Supabase. The router only handles selection
policy (top-k, diversity, explicit overrides).
"""

from typing import List, Optional
import logging

from ..agents.catalog import AgentCatalog, DOMAIN_AGENT_MAP
from ..config import get_settings

log = logging.getLogger(__name__)


class CentralRouter:
    """Routes natural language questions to specialist agents."""

    def __init__(self):
        self.catalog = AgentCatalog()
        self.settings = get_settings()
        self.max_agents = self.settings.max_agents_per_council
    
    async def route(
        self,
        question: str,
        explicit_agents: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[dict]:
        """
        Select best agents for a question.
        
        Args:
            question: CEO's question in natural language
            explicit_agents: User-specified agent slugs (skip routing)
            top_k: Max agents to return
        
        Returns:
            List of agent configs with scores
        """
        # If user explicitly chose agents, use those
        if explicit_agents:
            agents = []
            for slug in explicit_agents[:top_k]:
                prompt = await self.catalog.get_prompt(slug)
                agents.append({
                    "slug": slug,
                    "source": "explicit",
                    "score": 1.0,
                    "prompt": prompt,
                })
            return agents
        
        # Route via hybrid strategy
        matches = await self.catalog.match(question, top_k=top_k * 2)
        
        # Select top-k, ensuring diversity (at least 2 different teams if possible)
        selected = []
        seen_teams = set()
        
        for m in matches:
            if len(selected) >= top_k:
                break
            team = m.get("home_team", "")
            
            # Prioritize diverse teams for first 3 slots
            if len(selected) < 3 and team in seen_teams:
                # Still add if score is very high
                if m["score"] < 0.7:
                    continue
            
            prompt = await self.catalog.get_prompt(m["slug"])
            selected.append({
                "slug": m["slug"],
                "handle": m["handle"],
                "name": m["name"],
                "source": m["source"],
                "score": m["score"],
                "prompt": prompt,
            })
            seen_teams.add(team)
        
        log.info(f"Router: '{question[:60]}...' → {len(selected)} agents ({[a['slug'] for a in selected]})")
        return selected
    
    def get_domains(self) -> List[str]:
        """List all known domains for deterministic routing."""
        return sorted(DOMAIN_AGENT_MAP.keys())
    
    def get_domain_agents(self, domain: str) -> List[str]:
        """Get agent slugs for a domain."""
        return DOMAIN_AGENT_MAP.get(domain, [])
