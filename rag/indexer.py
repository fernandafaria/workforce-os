"""
RAG Indexer — Builds BM25 and semantic search indices from knowledge markdown files.

Scans all knowledge/ directories across teams and creates per-team indices.
Supports hybrid mode: BM25 (keyword) + semantic embeddings (when available).
"""

import hashlib
import json
import logging
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)

# Tag cache lives next to the code so reindexing from a different cwd still hits.
_TOPIC_CACHE_PATH = Path(__file__).with_name("topic_cache.json")


def chunk_markdown(text: str, min_words: int = 20, max_words: int = 250) -> list[str]:
    """
    Split markdown into semantic chunks by paragraph.
    Merges short paragraphs and splits overly long ones.
    """
    paragraphs = re.split(r"\n\n+", text)

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        word_count = len(para.split())

        if current_words + word_count > max_words and current:
            joined = "\n\n".join(current)
            if len(joined.split()) >= min_words:
                chunks.append(joined)
            current = [para]
            current_words = word_count
        else:
            current.append(para)
            current_words += word_count

    if current:
        joined = "\n\n".join(current)
        if len(joined.split()) >= min_words:
            chunks.append(joined)

    return chunks


def tokenize(text: str) -> list[str]:
    """Normalize and tokenize text for BM25."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]


def _chunk_fingerprint(chunk: str) -> str:
    """Stable short hash used as the tag-cache key."""
    return hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:16]


def _load_topic_cache() -> dict[str, list[str]]:
    """Read the on-disk tag cache; return an empty dict if it doesn't exist
    or is corrupted. The cache is advisory — callers always handle misses."""
    if not _TOPIC_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_TOPIC_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("topic_cache.json unreadable; starting with empty cache.")
        return {}


def _save_topic_cache(cache: dict[str, list[str]]) -> None:
    """Persist the tag cache. Non-fatal if it fails (e.g. read-only FS)."""
    try:
        _TOPIC_CACHE_PATH.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    except OSError as e:
        log.warning("Failed to persist topic_cache.json: %s", e)


def _tag_chunk_topics(
    chunk: str,
    taxonomy: dict[str, str],
    threshold: float = 0.35,
    max_tags: int = 3,
) -> list[str]:
    """Zero-shot tag a single chunk against `taxonomy`.

    Returns up to `max_tags` tag slugs scoring above `threshold`. Returns an
    empty list if the classifier is unavailable — callers treat missing tags
    as "no topic filter" rather than as a failure.
    """
    from rag.classifier import classify_query

    # classify_query already handles model loading, truncation, and unavailability.
    matches = classify_query(chunk, labels=taxonomy, top_k=max_tags, threshold=threshold)
    return [m["team"] for m in matches]  # `team` key holds the slug


def build_index(
    repo_root: str,
    use_embeddings: bool = True,
    contextualize: str = "template",
    chunk_strategy: str = "paragraph",
    tag_topics: bool = False,
) -> dict:
    """
    Build BM25 and optional semantic indices for all teams that have a knowledge/ directory.

    Args:
        repo_root:      Path to the repository root
        use_embeddings: Whether to also build semantic embeddings index
        contextualize:  Chunk contextualization mode — 'off', 'template', or 'llm'.
                        Default 'template' prepends a deterministic metadata
                        prefix (team, persona, source type) to each chunk. This
                        is Anthropic's "Contextual Retrieval" technique in its
                        cheapest form; switch to 'llm' to generate per-chunk
                        context sentences via Haiku (requires ANTHROPIC_API_KEY).
        chunk_strategy: 'paragraph' (default) uses chunk_markdown; 'semantic'
                        opts into Chonkie's embedding-boundary chunker via
                        rag.chunker.chunk, with graceful fallback if Chonkie
                        is not installed.
        tag_topics:     When True, each chunk is zero-shot tagged against its
                        team's vocabulary in rag.topic_taxonomy and the tags
                        are written to metadata['topics']. Tags are cached in
                        rag/topic_cache.json by chunk fingerprint, so reindexing
                        unchanged content is free after the first pass.

    Returns:
        {
            team_name: {
                'bm25': BM25Okapi,
                'chunks': [str, ...],
                'metadata': [{'team', 'persona', 'file', 'topics': [..]}, ...],
                'embeddings': np.ndarray | None,
            }
        }
    """
    from rag.contextualize import contextualize_chunks

    repo_path = Path(repo_root)
    index: dict = {}

    # Topic-tagging state (only touched when tag_topics=True).
    topic_cache = _load_topic_cache() if tag_topics else {}
    cache_dirty = False
    taxonomy_cache: dict[str, dict[str, str] | None] = {}

    # Try to import embeddings module once
    encode_fn = None
    if use_embeddings:
        try:
            from rag.embeddings import encode_texts, is_available

            if is_available():
                encode_fn = encode_texts
                log.info("Semantic embeddings enabled.")
            else:
                log.info("Semantic embeddings unavailable (sentence-transformers not installed).")
        except ImportError:
            log.info("Semantic embeddings unavailable (import failed).")

    for team_dir in sorted(repo_path.iterdir()):
        if not team_dir.is_dir() or team_dir.name.startswith("."):
            continue

        knowledge_dir = team_dir / "knowledge"
        if not knowledge_dir.exists():
            continue

        team_name = team_dir.name
        chunks: list[str] = []
        metadata: list[dict] = []

        for md_file in sorted(knowledge_dir.rglob("*.md")):
            rel = md_file.relative_to(knowledge_dir)
            parts = rel.parts
            persona = parts[0] if len(parts) > 1 else "general"

            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if chunk_strategy == "semantic":
                from rag.chunker import chunk as chunk_with_strategy

                raw_chunks = chunk_with_strategy(text, strategy="semantic")
            else:
                raw_chunks = chunk_markdown(text)
            if not raw_chunks:
                continue

            rel_to_repo = str(md_file.relative_to(repo_path))
            enriched_chunks = contextualize_chunks(
                raw_chunks,
                doc_text=text,
                team=team_name,
                persona=persona,
                source_file=rel_to_repo,
                mode=contextualize,
            )

            # Per-team taxonomy is looked up once and cached for the run.
            if tag_topics and team_name not in taxonomy_cache:
                from rag.topic_taxonomy import get_taxonomy

                taxonomy_cache[team_name] = get_taxonomy(team_name)

            team_taxonomy = taxonomy_cache.get(team_name) if tag_topics else None

            for chunk in enriched_chunks:
                chunk_topics: list[str] = []
                if tag_topics and team_taxonomy:
                    fp = _chunk_fingerprint(chunk)
                    cached = topic_cache.get(fp)
                    if cached is not None:
                        chunk_topics = cached
                    else:
                        chunk_topics = _tag_chunk_topics(chunk, team_taxonomy)
                        topic_cache[fp] = chunk_topics
                        cache_dirty = True

                chunks.append(chunk)
                metadata.append(
                    {
                        "team": team_name,
                        "persona": persona,
                        "file": rel_to_repo,
                        "topics": chunk_topics,
                    }
                )

        if not chunks:
            continue

        tokenized = [tokenize(c) for c in chunks]
        bm25 = BM25Okapi(tokenized)

        team_index: dict = {
            "bm25": bm25,
            "chunks": chunks,
            "metadata": metadata,
            "embeddings": None,
        }

        # Build semantic embeddings if available (using the single reference)
        if encode_fn is not None:
            try:
                embs = encode_fn(chunks)
                if embs is not None:
                    team_index["embeddings"] = embs
                    log.info("[%s] %d chunks indexed (BM25 + semantic)", team_name, len(chunks))
                else:
                    log.info("[%s] %d chunks indexed (BM25 only)", team_name, len(chunks))
            except Exception as e:
                log.info(
                    "[%s] %d chunks indexed (BM25 only, embedding failed: %s)",
                    team_name,
                    len(chunks),
                    e,
                )
        else:
            log.info("[%s] %d chunks indexed", team_name, len(chunks))

        index[team_name] = team_index

    if tag_topics and cache_dirty:
        _save_topic_cache(topic_cache)

    return index
