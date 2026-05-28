"""
url_finder — autonomous search for specific YouTube episode URLs.

Problem this solves: the person backlog specs under rag/twins/persons/*.yaml
were bootstrapped with channel-level YouTube URLs (e.g. `youtube.com/@g4educacao`)
as placeholders. The transcribe + run_all pipeline refuses channel URLs (strict
URL check) to avoid accidental full-channel downloads. We need to replace each
placeholder with a specific episode URL where the persona actually appears.

Approach: for every source in a spec that lists a channel-level URL + a
descriptive `title:`, compose a search query and pull the top YouTube
watch?v= match from Firecrawl's /search endpoint. If a plausible match is
found, emit a proposed YAML patch; `--apply` writes the patch in place.

This is Firecrawl-powered (FIRECRAWL_API_KEY in secrets) so the same worker
runs identically in GitHub Actions. When the key is missing we fall back to
DuckDuckGo's public HTML result page via httpx, sufficient for validation
but rate-limited — not recommended for batch runs.

Usage
-----
    # dry-run for 1 spec (prints proposed replacements, no writes)
    python -m rag.twins.url_finder rag/twins/persons/predilecta-vinicius-rosa.yaml

    # apply (rewrites the YAML in place)
    python -m rag.twins.url_finder <spec> --apply

    # batch across the backlog
    python -m rag.twins.url_finder rag/twins/persons/*.yaml --apply

    # limit searches per spec so cost is predictable
    python -m rag.twins.url_finder <spec> --max-per-spec 3

Design rules
------------
  * **Conservative matching.** Only replace when the top result URL matches
    the episode regex. If nothing matches, leave the placeholder untouched
    and emit a warning. Half-right URL is worse than no URL.
  * **Idempotent.** Re-running picks up where it stopped. Already-tight URLs
    are skipped.
  * **No blind trust of titles.** The script returns the found URL + its
    original title; operator reviews before merging the patch.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_EPISODE_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+",
    re.IGNORECASE,
)

_CHANNEL_HINT_RE = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str


@dataclass
class ProposedPatch:
    source_index: int
    old_url: str
    new_url: str
    new_title: str
    rationale: str


# ---------------------------------------------------------------------------
# Search backends
# ---------------------------------------------------------------------------


def search_firecrawl(query: str, *, limit: int = 5) -> list[SearchHit]:
    """Use Firecrawl's /search endpoint. Requires FIRECRAWL_API_KEY."""
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx not installed") from e

    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY not set")

    resp = httpx.post(
        "https://api.firecrawl.dev/v1/search",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query, "limit": limit},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return [
        SearchHit(
            url=item.get("url", ""),
            title=item.get("title", ""),
            snippet=item.get("description", "") or item.get("snippet", ""),
        )
        for item in data
        if item.get("url")
    ]


def search_fallback(query: str, *, limit: int = 5) -> list[SearchHit]:
    """DuckDuckGo HTML endpoint — no API key required, rate-limited. Used only
    when FIRECRAWL_API_KEY is unavailable; results are coarser but enough
    to validate the pipeline."""
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx not installed") from e

    resp = httpx.get(
        "https://duckduckgo.com/html/",
        params={"q": query + " site:youtube.com"},
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    hits: list[SearchHit] = []
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', resp.text
    ):
        raw_url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        # DDG wraps targets in its own redirect — extract the raw URL
        m2 = re.search(r"uddg=([^&]+)", raw_url)
        if m2:
            from urllib.parse import unquote

            raw_url = unquote(m2.group(1))
        hits.append(SearchHit(url=raw_url, title=title, snippet=""))
        if len(hits) >= limit:
            break
    return hits


def search(query: str, *, limit: int = 5) -> list[SearchHit]:
    """Pick the best available backend."""
    if os.environ.get("FIRECRAWL_API_KEY"):
        return search_firecrawl(query, limit=limit)
    log.warning("FIRECRAWL_API_KEY not set — falling back to DuckDuckGo (rate-limited)")
    return search_fallback(query, limit=limit)


# ---------------------------------------------------------------------------
# Match a hit against the spec
# ---------------------------------------------------------------------------


def _first_episode_url(hits: list[SearchHit]) -> SearchHit | None:
    for h in hits:
        if _EPISODE_RE.search(h.url):
            # normalize: drop anything after &pp= or similar tracking garbage
            h.url = _normalize_yt_url(h.url)
            return h
    return None


def _normalize_yt_url(url: str) -> str:
    m = re.search(r"youtube\.com/watch\?v=([\w\-]+)", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    m = re.search(r"youtu\.be/([\w\-]+)", url)
    if m:
        return f"https://youtu.be/{m.group(1)}"
    m = re.search(r"youtube\.com/shorts/([\w\-]+)", url)
    if m:
        return f"https://www.youtube.com/shorts/{m.group(1)}"
    return url


def _build_query(name_public: str, title: str | None, archetype: str) -> str:
    bits: list[str] = []
    if name_public:
        bits.append(f'"{name_public}"')
    elif archetype:
        bits.append(archetype)
    if title:
        # Strip the generic "Show Name — " prefix to avoid over-constraining
        clean_title = re.sub(r"^[^—]+ — ", "", title)
        clean_title = re.sub(r"[\"']", "", clean_title)[:80]
        bits.append(clean_title)
    bits.append("entrevista")
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Per-spec planner
# ---------------------------------------------------------------------------


def plan_patches(
    spec_path: Path,
    *,
    max_per_spec: int = 10,
) -> list[ProposedPatch]:
    from rag.twins.ingest_person import load_person_spec

    spec = load_person_spec(spec_path)
    patches: list[ProposedPatch] = []
    searches_done = 0

    for i, src in enumerate(spec.sources):
        if searches_done >= max_per_spec:
            break
        if not src.url:
            continue
        # Already a specific episode? skip
        if _EPISODE_RE.search(src.url):
            continue
        # Only YouTube channel-level URLs are in scope; other placeholder URLs
        # (LinkedIn, ri.company.com, etc) are intentional, not broken.
        if not _CHANNEL_HINT_RE.search(src.url):
            continue

        query = _build_query(spec.name_public or "", src.title, spec.archetype_label)
        log.info("[%s] searching: %s", spec.id, query)
        try:
            hits = search(query, limit=5)
        except Exception as e:
            log.warning("[%s] search failed: %s", spec.id, e)
            continue
        searches_done += 1

        chosen = _first_episode_url(hits)
        if not chosen:
            log.warning("[%s] no episode-URL match for %r", spec.id, src.title)
            continue

        patches.append(
            ProposedPatch(
                source_index=i,
                old_url=src.url,
                new_url=chosen.url,
                new_title=f"{src.title} — matched: {chosen.title[:80]}"
                if src.title
                else chosen.title,
                rationale=f"found via search: {chosen.title[:100]}",
            )
        )
    return patches


# ---------------------------------------------------------------------------
# Apply patches in place
# ---------------------------------------------------------------------------


def apply_patches(spec_path: Path, patches: list[ProposedPatch]) -> int:
    """Rewrite the YAML preserving formatting as best we can.

    We do minimal string replacement rather than a full YAML round-trip,
    since the file carries human-authored comments and formatting we want
    to keep.
    """
    text = spec_path.read_text(encoding="utf-8")
    applied = 0
    for p in patches:
        if p.old_url not in text:
            log.warning("could not locate old URL in file: %s", p.old_url)
            continue
        text = text.replace(p.old_url, p.new_url, 1)
        applied += 1
    spec_path.write_text(text, encoding="utf-8")
    return applied


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("specs", type=Path, nargs="+", help="rag/twins/persons/*.yaml")
    p.add_argument("--apply", action="store_true", help="write patches in place")
    p.add_argument(
        "--max-per-spec",
        type=int,
        default=10,
        help="cap number of search calls per spec (cost control)",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    all_results: dict[str, list[dict]] = {}
    for spec_path in args.specs:
        patches = plan_patches(spec_path, max_per_spec=args.max_per_spec)
        all_results[spec_path.stem] = [
            {
                "source_index": p.source_index,
                "old_url": p.old_url,
                "new_url": p.new_url,
                "rationale": p.rationale,
            }
            for p in patches
        ]
        if args.apply and patches:
            n = apply_patches(spec_path, patches)
            log.info("[%s] applied %d/%d patches", spec_path.stem, n, len(patches))

    print(json.dumps(all_results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
