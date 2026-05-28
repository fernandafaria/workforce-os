"""
dev_seed — bootstrap twins.db outside the DO runner.

When `rag/twins/twins.db` is empty (sandbox, cloud agent, local dev), interviews
degenerate into plausible theater. This module seeds a **minimal** twin from the
checked-in YAML spec: person row, corpus chunks from `notes`, and a draft twin
so `interview_archetype` and `joint_discovery` can run with real corpus_search
hits — not a substitute for FULL ingest+build on DO, but unblocks CI and MCP.

Usage:
    python -m rag.twins.dev_seed arch-mkt-orquestrador-insights
    python -m rag.twins.dev_seed --all-arch-mkt
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import uuid
from pathlib import Path

from rag.twins import storage
from rag.twins.interview_profile import load_person_spec

log = logging.getLogger(__name__)

PERSONS_DIR = Path("rag/twins/persons")
_CHUNK_MIN_LEN = 80


def _paragraph_chunks(notes: str, *, source_type: str = "article") -> list[dict]:
    """Split YAML notes into corpus chunks for keyword search."""
    chunks: list[dict] = []
    for para in re.split(r"\n\s*\n", notes.strip()):
        text = " ".join(para.split())
        if len(text) < _CHUNK_MIN_LEN:
            continue
        chunks.append(
            {
                "text": text,
                "source_type": source_type,
                "first_person": False,
                "quality_score": 0.6,
            }
        )
    if not chunks and notes.strip():
        chunks.append(
            {
                "text": notes.strip()[:4000],
                "source_type": source_type,
                "first_person": False,
                "quality_score": 0.5,
            }
        )
    return chunks


def _minimal_twin_dict(person_id: str, spec: dict) -> dict:
    """Draft twin payload compatible with interview_archetype.build_archetype_system_prompt."""
    twin_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dev-seed:{person_id}"))
    label = spec.get("archetype_label") or spec.get("name_public") or person_id
    return {
        "id": twin_id,
        "person_id": person_id,
        "is_composite": True,
        "archetype_label": label,
        "name_public": spec.get("name_public"),
        "status": "draft",
        "linguistic": {
            "formality": (
                "formal"
                if person_id.startswith(("arch-mkt-", "arch-exec-ai-"))
                else "informal"
            ),
            "signature_phrases": [],
        },
        "decision": {
            "risk_appetite": "moderate",
            "decision_speed": "measured",
            "primary_drivers": [],
            "deal_breakers": [],
            "trust_sources": [],
        },
        "corpus": {
            "source_count": 0,
            "total_tokens": 0,
            "source_types": {},
        },
        "eval_scores": {},
        "extensions": {"dev_seed": True},
    }


def ensure_twin_ready(
    person_id: str,
    *,
    db_path: Path | None = None,
    force: bool = False,
) -> str:
    """Ensure person + corpus + twin exist; return twin_id (UUID)."""
    existing = storage.get_twin_by_slug(person_id, db_path=db_path)
    if existing and not force:
        return existing["id"]

    spec = load_person_spec(person_id)
    if not spec:
        raise SystemExit(f"No YAML spec at {PERSONS_DIR / (person_id + '.yaml')}")

    notes = str(spec.get("notes") or "").strip()
    if not notes:
        raise SystemExit(f"Spec {person_id} has no `notes:` — cannot dev-seed corpus")

    storage.upsert_person(
        person_id,
        name_public=spec.get("name_public"),
        archetype_label=spec.get("archetype_label", person_id),
        authorization=str(spec.get("authorization", "archetype_synthetic")),
        notes=notes,
        db_path=db_path,
    )

    if force:
        # Re-seed corpus only when forcing (avoid duplicate chunks on repeat calls).
        with storage.connect(db_path) as conn:
            conn.execute("DELETE FROM corpus_chunk WHERE person_id = ?", (person_id,))

    existing_chunks = storage.list_chunks(person_id, db_path=db_path)
    if not existing_chunks or force:
        inserted = storage.insert_chunks(
            person_id,
            _paragraph_chunks(notes),
            db_path=db_path,
        )
        log.info("dev_seed: inserted %s chunks for %s", inserted, person_id)

    twin_dict = _minimal_twin_dict(person_id, spec)
    storage.upsert_twin(twin_dict, db_path=db_path)
    return twin_dict["id"]


def list_arch_mkt_slugs() -> list[str]:
    return sorted(p.stem for p in PERSONS_DIR.glob("arch-mkt-*.yaml"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("slug", nargs="?", help="person_id / YAML slug")
    p.add_argument("--all-arch-mkt", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    slugs: list[str]
    if args.all_arch_mkt:
        slugs = list_arch_mkt_slugs()
    elif args.slug:
        slugs = [args.slug]
    else:
        p.error("Provide slug or --all-arch-mkt")

    for slug in slugs:
        tid = ensure_twin_ready(slug, db_path=args.db, force=args.force)
        print(f"{slug}\t{tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
