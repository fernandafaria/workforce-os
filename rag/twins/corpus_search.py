"""
corpus_search — retrieval tool the twin is allowed to call during chat.

Harrison's rule: every factual claim must come from corpus_search(query)
or the twin declines. Alternatives (free-form recall, world knowledge)
are what turn a twin into hallucinated fanfic — we don't want that.

Implementation:
  - if embeddings are available, cosine-rank persona's non-holdout chunks
    against the Voyage query embedding and return top-k.
  - otherwise fall back to keyword match — good enough for local tests
    and keeps the tool answering when embeddings aren't set up yet.

The function returns plain dicts (source_type, source_date, source_url,
quote) that chat_with_twin.py can inline into the tool_result content.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from rag.twins import storage

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-záéíóúâêôãõç0-9]+", re.IGNORECASE)


def search(
    person_id: str,
    query: str,
    *,
    k: int = 4,
    db_path: Path | None = None,
) -> list[dict]:
    """Return up to `k` chunks most relevant to `query`.

    Never returns holdout chunks — those are reserved for eval. Returns
    shortened text (≤ 600 chars) so the twin's tool-result stays within
    a reasonable context budget.
    """
    chunks = storage.list_chunks(person_id, include_holdout=False, db_path=db_path)
    if not chunks:
        return []

    query_emb = _try_embed(query)
    scored: list[tuple[float, dict]] = []

    if query_emb is not None:
        for c in chunks:
            emb = c.get("embedding")
            if not emb:
                continue
            score = _cosine(query_emb, emb)
            scored.append((score, c))

    if not scored:  # no embeddings available — fall back to keyword overlap
        q_terms = set(_tokenize(query))
        for c in chunks:
            terms = set(_tokenize(c["text"]))
            if not terms:
                continue
            overlap = len(q_terms & terms)
            if overlap:
                scored.append((overlap / max(1, len(q_terms)), c))

    scored.sort(key=lambda row: row[0], reverse=True)

    results: list[dict] = []
    for score, c in scored[:k]:
        results.append(
            {
                "score": round(float(score), 4),
                "source_type": c["source_type"],
                "source_date": c.get("source_date"),
                "source_url": c.get("source_url"),
                "quote": _truncate(c["text"], 600),
            }
        )
    return results


def _try_embed(query: str) -> list[float] | None:
    try:
        from rag.voyage_embeddings import generate_query_embedding, is_available
    except ImportError:
        return None
    if not is_available():
        return None
    return generate_query_embedding(query)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[: n - 1].rsplit(" ", 1)[0] + "…"
