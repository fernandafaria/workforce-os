"""
Entrepreneur Digital Twins — MVP (Phase 1).

Synthetic twins of real non-digital entrepreneurs for use in product discovery.
Architected in war-room on 2026-04-21 (Claire + Hamel + Harrison + Jason +
Shreya + Simon). See rag/twins/README.md for the full plan.

Package layout:
    schema.py             — Pydantic models (EntrepreneurTwin, sub-profiles).
    storage.py            — SQLite-backed store for corpus, twins, runs, evals.
    ingest_person.py      — Pipeline: sources → chunks → embeddings → DB.
    build_twin.py         — Extracts EntrepreneurTwin from corpus via Anthropic.
    corpus_search.py      — Retrieval tool exposed to the twin during chat.
    chat_with_twin.py     — Turn-based CLI interview (interviewer ↔ twin).
    eval_twin.py          — Holdout-cosine eval harness (Hamel gate, layer 1).

MVP target (Phase 1, 2 weeks): 1 convincing twin, end-to-end, with logs.
"""

from __future__ import annotations

__all__ = [
    "schema",
    "storage",
]
