"""
Voyage AI Embeddings — generates query embeddings via the Voyage API.

Used by structured RAG to produce query vectors compatible with the
Voyage-4 embeddings stored in Supabase (personas, skills, memories).

The local model (intfloat/e5-large) lives in a different embedding space,
so Supabase vector search requires Voyage-generated queries.

Requires: VOYAGE_API_KEY environment variable
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "").strip()
_VOYAGE_MODEL = "voyage-4"
_OUTPUT_DIMENSION = 1024


def is_available() -> bool:
    """Check if Voyage API is configured."""
    return bool(_VOYAGE_API_KEY)


def generate_query_embedding(text: str) -> list[float] | None:
    """Generate a query embedding via Voyage AI.

    Returns a 1024-dim float list, or None on failure.
    """
    if not _VOYAGE_API_KEY:
        log.warning("VOYAGE_API_KEY not set — structured RAG unavailable")
        return None

    try:
        import httpx
    except ImportError:
        log.warning("httpx not installed — Voyage embeddings unavailable")
        return None

    try:
        resp = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_VOYAGE_API_KEY}",
            },
            json={
                "model": _VOYAGE_MODEL,
                "input": text,
                "input_type": "query",
                "output_dimension": _OUTPUT_DIMENSION,
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            log.warning("Voyage API error: %d %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        embedding = data.get("data", [{}])[0].get("embedding")
        if not embedding:
            log.warning("Voyage API returned no embedding")
            return None

        return embedding
    except Exception as e:
        log.warning("Voyage embedding failed: %s", e)
        return None
