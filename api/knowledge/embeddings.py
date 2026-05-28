"""
Workforce OS — Voyage AI embedding helper.

Single source of truth for query embeddings used by:
  - Router (match_personas)
  - Memory pipeline (memory search + storage)
  - Knowledge retriever (vertical RAG)

Production uses voyage-4 with 1024 dimensions to match the
`personas.embedding` column and the existing generate-embedding
edge function in Supabase.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
DEFAULT_MODEL = "voyage-4"
DEFAULT_DIMENSIONS = 1024
MAX_INPUT_CHARS = 16000


async def embed_query(text: str, *, dimensions: int = DEFAULT_DIMENSIONS) -> Optional[List[float]]:
    """Embed a search query. Returns None on failure (caller falls back to rules)."""
    return await _embed(text, input_type="query", dimensions=dimensions)


async def embed_document(text: str, *, dimensions: int = DEFAULT_DIMENSIONS) -> Optional[List[float]]:
    """Embed a document for storage."""
    return await _embed(text, input_type="document", dimensions=dimensions)


async def _embed(text: str, *, input_type: str, dimensions: int) -> Optional[List[float]]:
    settings = get_settings()
    if not settings.voyage_api_key:
        log.warning("VOYAGE_API_KEY not configured; embedding skipped")
        return None
    if not text or not text.strip():
        return None

    payload = {
        "model": DEFAULT_MODEL,
        "input": text[:MAX_INPUT_CHARS],
        "input_type": input_type,
        "output_dimension": dimensions,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                VOYAGE_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.voyage_api_key}",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            vec = data.get("data", [{}])[0].get("embedding")
            if not vec or len(vec) != dimensions:
                log.warning("Voyage returned unexpected embedding shape")
                return None
            return vec
    except Exception as e:
        log.warning(f"Voyage embedding failed: {e}")
        return None
