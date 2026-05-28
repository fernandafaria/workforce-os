"""
ingest_person — Phase 1 ingestion pipeline (Shreya's v1).

    sources.yaml  →  fetch (Firecrawl/file)  →  classify  →  chunk
                 →  quality score  →  embed (Voyage)  →  SQLite

Input:  a person sources file (YAML or JSON) like rag/twins/persons/<slug>.yaml:

    id: joao-distribuidor
    name_public: "João Silva"   # or null for fully anonymized
    archetype_label: "Distribuidor SP 50M sucessão-em-curso"
    authorization: public_figure  # pending|granted|public_figure|denied
    sources:
      - url: https://blog.example.com/entrevista-joao
        type: interview
        date: 2024-06-02
      - path: local/transcript-podcast-x.md
        type: podcast
        date: 2024-03-15
      - url: https://linkedin.com/in/joao/...
        type: linkedin
        date: 2025-02-01

Usage:
    python -m rag.twins.ingest_person rag/twins/persons/joao-distribuidor.yaml
    python -m rag.twins.ingest_person <file> --holdout-ratio 0.2 --dry-run

The CLI is intentionally small. Every heavy lib (Firecrawl, Voyage, yaml)
is imported lazily so `--dry-run` works with zero credentials — we want
contributors to be able to validate a sources file before asking for keys.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag.twins import storage
from rag.twins.proxy_utils import normalize_proxy_env

# Normalize proxy env vars at import time so Firecrawl SDK (which uses
# httpx via HTTPS_PROXY) gets a parseable URL even if the operator set
# the secret in Webshare-list format (host:port:user:pass). Idempotent
# — safe to call from multiple entry points. See proxy_utils.py for the
# failure mode this prevents (PR #676 diagnostic).
normalize_proxy_env()

log = logging.getLogger(__name__)

VALID_SOURCE_TYPES = {
    "interview",
    "podcast",
    "linkedin",
    "talk",
    "release",
    "book",
    "article",
    "crawl",
    "video",
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


@dataclass
class SourceSpec:
    url: str | None
    path: str | None
    type: str
    date: str | None
    first_person: bool = True
    title: str | None = None  # human-readable descriptor, e.g. "Os Sócios #142"


@dataclass
class PersonSpec:
    id: str
    archetype_label: str
    authorization: str
    name_public: str | None
    sources: list[SourceSpec]
    notes: str | None = None


def load_person_spec(config_path: Path) -> PersonSpec:
    raw = _read_structured(config_path)
    sources = [
        SourceSpec(
            url=s.get("url"),
            path=s.get("path"),
            type=s["type"],
            date=s.get("date"),
            first_person=s.get("first_person", True),
            title=s.get("title"),
        )
        for s in raw.get("sources", [])
    ]
    _validate(raw, sources, config_path)
    return PersonSpec(
        id=raw["id"],
        archetype_label=raw["archetype_label"],
        authorization=raw.get("authorization", "pending"),
        name_public=raw.get("name_public"),
        sources=sources,
        notes=raw.get("notes"),
    )


def _read_structured(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as e:
            raise SystemExit(f"PyYAML required to read {path}; pip install pyyaml") from e
        return yaml.safe_load(text) or {}
    if path.suffix.lower() == ".json":
        return json.loads(text)
    raise SystemExit(f"Unsupported config format: {path.suffix}")


def _validate(raw: dict, sources: list[SourceSpec], path: Path) -> None:
    required = {"id", "archetype_label"}
    missing = required - raw.keys()
    if missing:
        raise SystemExit(f"{path}: missing required field(s): {sorted(missing)}")
    if not sources:
        raise SystemExit(f"{path}: no sources declared")
    for i, s in enumerate(sources):
        if s.type not in VALID_SOURCE_TYPES:
            raise SystemExit(
                f"{path}: source[{i}] type={s.type!r} not in {sorted(VALID_SOURCE_TYPES)}"
            )
        if not (s.url or s.path):
            raise SystemExit(f"{path}: source[{i}] has neither url nor path")

    auth = raw.get("authorization", "pending")
    # `archetype_synthetic` supports population archetypes (not real
    # individuals) — corpus comes from IBGE stats + aggregated academic
    # ethnography + journalism longform + public forum threads; no
    # individual consent needed because the twin represents a segment
    # composite, not a named person.
    if auth not in {"pending", "granted", "public_figure", "denied", "archetype_synthetic"}:
        raise SystemExit(f"{path}: authorization={auth!r} invalid")
    if auth == "denied":
        raise SystemExit(
            f"{path}: authorization=denied — ingestion refused "
            "(LGPD — delete corpus on request, see README §Ethics)"
        )


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def fetch_source(
    spec: SourceSpec,
    *,
    person_id: str | None = None,
    corpus_base: Path | None = None,
) -> str:
    """Return raw text for a source.

    Resolution order:
      1. If `spec.path` is set, read that local file.
      2. For URL sources, if a transcript file already exists under
         `corpus_base/<person_id>/` (written by `transcribe.py`),
         read that. This is the critical integration so that the URLs
         added to backlog specs (like YouTube episodes) actually surface
         their Whisper transcript in ingestion — otherwise Firecrawl
         would fetch the YouTube HTML, which has no real content.
      3. Otherwise, fall back to Firecrawl on the URL.

    Graceful: if Firecrawl isn't available, raises a clear error rather
    than silently degrading — corpus ingestion without source text is a
    silent-failure mode that produces bad twins (Shreya's top risk).
    """
    if spec.path:
        p = Path(spec.path)
        if not p.exists():
            raise FileNotFoundError(f"Source path not found: {p}")
        return p.read_text(encoding="utf-8")

    if not spec.url:
        raise ValueError("SourceSpec has neither path nor url")

    if person_id:
        tx_path = _resolve_transcript_path(person_id, spec, corpus_base)
        if tx_path is not None and tx_path.exists() and tx_path.stat().st_size > 0:
            log.info("using local transcript for url=%s path=%s", spec.url, tx_path)
            return tx_path.read_text(encoding="utf-8")

    # firecrawl-py 4.x renamed the class to `Firecrawl` and the method to
    # `scrape(url, formats=[...])`. v3.x used `FirecrawlApp.scrape_url(...)`
    # — support both so the twin pipeline works across SDK versions.
    try:
        try:
            from firecrawl import Firecrawl  # v4.x

            _FC_API = "v4"
        except ImportError:
            from firecrawl import FirecrawlApp as Firecrawl  # v3.x shim

            _FC_API = "v3"
    except ImportError as e:
        raise RuntimeError(
            "firecrawl-py not installed — add local `path:` sources or install firecrawl-py"
        ) from e

    import os

    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY not set; cannot scrape URL sources")

    app = Firecrawl(api_key=key)
    if _FC_API == "v4" or hasattr(app, "scrape"):
        result = app.scrape(spec.url, formats=["markdown"])
    else:
        result = app.scrape_url(spec.url, params={"formats": ["markdown"]})

    # v4 returns a Document pydantic object with .markdown, .metadata.
    # v3 returned dict {"markdown": ...} or {"data": {"markdown": ...}}.
    if hasattr(result, "markdown"):
        return result.markdown or ""
    if isinstance(result, dict):
        return result.get("markdown") or result.get("data", {}).get("markdown", "")
    return str(result)


def _resolve_transcript_path(
    person_id: str,
    spec: SourceSpec,
    corpus_base: Path | None,
) -> Path | None:
    """Where transcribe.py would have written the transcript for this source.

    Must stay in sync with transcribe._slugify_descriptor + the output-path
    logic in transcribe_spec. We try the title-based slug first, then the
    type+hash fallback slug, mirroring transcribe's own fallback chain.
    """
    try:
        from rag.twins.transcribe import _slugify_descriptor, _url_hash
    except ImportError:
        return None

    root = (corpus_base or Path("rag/twins/persons/_corpus")) / person_id

    title_slug = _slugify_descriptor(
        spec.title, fallback=f"{spec.type}-{_url_hash(spec.url or '')}"
    )
    return root / f"{title_slug}.md"


# ---------------------------------------------------------------------------
# Chunking + quality scoring
# ---------------------------------------------------------------------------


def chunk_source(text: str) -> list[str]:
    """Chunk markdown text into retrieval-sized paragraphs.

    Tries to reuse rag.indexer.chunk_markdown for parity with the rest of
    Febrain's RAG stack; falls back to an inline paragraph splitter when
    rag.indexer's own deps (rank_bm25) aren't installed in the environment.
    """
    try:
        from rag.indexer import chunk_markdown as _chunk
    except ImportError:
        return _fallback_chunk(text)
    return _chunk(text)


def _fallback_chunk(text: str, min_words: int = 20, max_words: int = 250) -> list[str]:
    import re

    paragraphs = re.split(r"\n\n+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        wc = len(para.split())
        if current_words + wc > max_words and current:
            joined = "\n\n".join(current)
            if len(joined.split()) >= min_words:
                chunks.append(joined)
            current = [para]
            current_words = wc
        else:
            current.append(para)
            current_words += wc
    if current:
        joined = "\n\n".join(current)
        if len(joined.split()) >= min_words:
            chunks.append(joined)
    return chunks


def score_quality(chunk: str, source_type: str, first_person: bool) -> float:
    """Rough 0-1 quality score per Shreya's rubric.

    Signals we can compute without extra models:
      - penalize chunks dominated by boilerplate (very short, all caps,
        URLs-heavy)
      - bonus for first_person=True — the twin should sound like the
        person, not like a journalist writing about them
      - type-based baseline: interviews/talks > linkedin > release
    """
    base = {
        "interview": 0.9,
        "talk": 0.85,
        "podcast": 0.85,
        "book": 0.8,
        "article": 0.6,
        "linkedin": 0.55,
        "crawl": 0.45,
        "release": 0.3,
    }.get(source_type, 0.5)

    words = chunk.split()
    if len(words) < 30:
        base -= 0.2

    # URL-heavy or hashtag-heavy is a red flag for corporate LinkedIn
    link_density = sum(1 for w in words if w.startswith(("http", "#", "@"))) / max(1, len(words))
    if link_density > 0.05:
        base -= 0.2

    if not first_person:
        base -= 0.25

    return max(0.0, min(1.0, base))


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def embed_chunks(chunks: list[str]) -> list[list[float] | None]:
    """Voyage embeddings for retrieval parity with the rest of rag/.

    Returns list aligned with input — None per chunk when embedding fails
    (we still store the text; embedding can be backfilled later).
    """
    try:
        from rag.voyage_embeddings import generate_query_embedding, is_available
    except ImportError:
        log.warning("voyage_embeddings not importable — skipping embeddings")
        return [None] * len(chunks)

    if not is_available():
        log.warning("VOYAGE_API_KEY not set — storing chunks without embeddings")
        return [None] * len(chunks)

    embeddings: list[list[float] | None] = []
    for text in chunks:
        embeddings.append(generate_query_embedding(text))
    return embeddings


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    person_id: str
    sources_fetched: int
    sources_failed: int
    chunks_inserted: int
    holdout_marked: int
    total_tokens: int
    source_types: dict[str, int]


def run(
    config_path: Path,
    *,
    holdout_ratio: float = 0.2,
    dry_run: bool = False,
    db_path: Path | None = None,
) -> IngestReport:
    spec = load_person_spec(config_path)
    log.info(
        "ingest person=%s sources=%d authorization=%s",
        spec.id,
        len(spec.sources),
        spec.authorization,
    )

    if not dry_run:
        storage.upsert_person(
            spec.id,
            name_public=spec.name_public,
            archetype_label=spec.archetype_label,
            authorization=spec.authorization,
            notes=spec.notes,
            db_path=db_path,
        )

    fetched = 0
    failed = 0
    all_chunks: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}

    for src in spec.sources:
        try:
            text = fetch_source(src, person_id=spec.id)
        except Exception as e:
            log.warning("fetch failed source=%s err=%s", src.url or src.path, e)
            failed += 1
            continue
        fetched += 1

        pieces = chunk_source(text)
        for piece in pieces:
            all_chunks.append(
                {
                    "id": str(uuid.uuid4()),
                    "text": piece,
                    "source_url": src.url or src.path,
                    "source_type": src.type,
                    "source_date": src.date,
                    "first_person": src.first_person,
                    "quality_score": score_quality(piece, src.type, src.first_person),
                }
            )
        type_counts[src.type] = type_counts.get(src.type, 0) + len(pieces)

    log.info("chunked total=%d types=%s", len(all_chunks), type_counts)

    if dry_run:
        print(
            json.dumps(
                {
                    "person_id": spec.id,
                    "sources_fetched": fetched,
                    "sources_failed": failed,
                    "chunks_total": len(all_chunks),
                    "source_types": type_counts,
                    "sample": all_chunks[0]["text"][:240] if all_chunks else "",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return IngestReport(
            person_id=spec.id,
            sources_fetched=fetched,
            sources_failed=failed,
            chunks_inserted=0,
            holdout_marked=0,
            total_tokens=sum(len(c["text"]) // 4 for c in all_chunks),
            source_types=type_counts,
        )

    # Embed in one batch to keep API calls predictable
    texts = [c["text"] for c in all_chunks]
    embeddings = embed_chunks(texts)
    for c, emb in zip(all_chunks, embeddings, strict=True):
        c["embedding"] = emb

    inserted = storage.insert_chunks(spec.id, all_chunks, db_path=db_path)
    holdout = storage.mark_holdout(spec.id, ratio=holdout_ratio, db_path=db_path)

    stats = storage.corpus_stats(spec.id, db_path=db_path)
    report = IngestReport(
        person_id=spec.id,
        sources_fetched=fetched,
        sources_failed=failed,
        chunks_inserted=inserted,
        holdout_marked=holdout,
        total_tokens=stats["total_tokens"],
        source_types=stats["source_types"],
    )
    log.info("ingest done: %s", report)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("config", type=Path, help="Path to person YAML/JSON spec")
    p.add_argument("--holdout-ratio", type=float, default=0.2)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--db", type=Path, default=None, help="Override TWINS_DB_PATH")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    report = run(
        args.config,
        holdout_ratio=args.holdout_ratio,
        dry_run=args.dry_run,
        db_path=args.db,
    )
    if report.sources_failed and not args.dry_run:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
