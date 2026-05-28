"""
Workforce OS — Knowledge Retriever
RAG: pgvector + Voyage embeddings search across verticals, agents, and BR context.
"""

from typing import List, Dict, Any, Optional
import logging

from ..config import get_settings

log = logging.getLogger(__name__)


class KnowledgeRetriever:
    """Semantic search across knowledge bases."""
    
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
    
    async def search(
        self,
        query: str,
        persona_slug: Optional[str] = None,
        vertical: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across knowledge bases.
        
        Args:
            query: Search query
            persona_slug: Filter to specific agent's KB
            vertical: Filter to vertical (industria, varejo, saude...)
            top_k: Max results
        """
        results = []
        
        try:
            # Try semantic_search_knowledge RPC
            params = {"query_text": query, "match_limit": top_k}
            if persona_slug:
                params["persona_slug"] = persona_slug
            if vertical:
                params["vertical"] = vertical
            
            result = self.client.rpc("semantic_search_knowledge", params).execute()
            if result.data:
                results = result.data
        except Exception as e:
            log.warning(f"Semantic knowledge search failed: {e}")
        
        # If no semantic results, try direct KB loading
        if not results and vertical:
            results = await self._load_vertical_fallback(query, vertical, top_k)
        
        return results[:top_k]
    
    async def _load_vertical_fallback(
        self,
        query: str,
        vertical: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Fallback: load vertical KB file and do text search."""
        import os
        
        base = os.path.expanduser("~/code/Febrain/_shared/knowledge/verticais")
        path = os.path.join(base, f"{vertical}.md")
        
        try:
            with open(path) as f:
                content = f.read()
            
            # Simple relevance: split by headings, find matching sections
            sections = content.split("\n## ")
            query_lower = query.lower()
            matches = []
            
            for section in sections:
                if query_lower in section.lower():
                    matches.append({
                        "content": section[:500],
                        "source": f"vertical:{vertical}",
                        "score": 0.5,
                    })
            
            return matches[:top_k]
        except FileNotFoundError:
            log.warning(f"Vertical KB not found: {vertical}")
            return []
