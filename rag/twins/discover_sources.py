"""
discover_sources — OSINT-driven source discovery for twin specs.

Problem this solves: today, populating `sources:` in a new
`rag/twins/persons/<slug>.yaml` is fully manual. The operator has to remember
every place a person publishes (Substack, Medium, LinkedIn, podcasts, personal
blog, X/Twitter) and paste each URL by hand. For founders/creators with heavy
digital footprint that's 30-60min of search per twin, and easy to miss the
long tail of guest podcast appearances, archived/deleted blog posts, or
mirrored republications.

Backends (all optional, graceful-degradation):

  1. **Maigret** (primary sweep): scans 2500+ sites for claimed profiles by
     username. Catches LinkedIn, Substack, Medium, X, GitHub, etc.
     https://github.com/soxoj/maigret

  2. **Wayback Machine CDX** (longitudinal): given a personal domain, lists
     historical snapshots so we recover blog posts that are no longer live.
     Public API, no auth. https://archive.org/wayback/cdx-server-api

  3. **iTunes Search API** (long-tail guest spots, no auth): public Apple
     endpoint that searches podcast episodes by term. Captures podcast
     appearances Maigret misses — Maigret matches by username on profile
     pages, not by name in episode metadata. Apple-indexed only (most
     mainstream BR/EN podcasts are; super-niche ones may not be).
     https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/

  4. **Firecrawl /search** (redundancy for podcasts): web search scoped to
     podcast hosts (open.spotify.com, podcasts.apple.com, youtube.com)
     with the person's name as query. Recall higher than iTunes (any
     podcast with a public page is reachable), noise also higher (catches
     mentions, not just guest spots). Reuses existing FIRECRAWL_API_KEY.

Each backend returns `DiscoveredSource` objects which are merged + deduped
globally. The output is **never** appended to the spec automatically —
operator pastes manually after reviewing each URL. This is intentional
(LGPD audit trail + false-positive filter): same username on different
sites ≠ same human, and Maigret/CDX/PI are matchers, not authorities.

Network: matches the established DO runner pattern. Maigret uses aiohttp,
which respects `HTTPS_PROXY` / `HTTP_PROXY` env vars; on the self-hosted
runner those point at the Webshare residential pool. We also forward
`--proxy` explicitly when set, to avoid relying on env-var precedence.
The Wayback CDX + PodcastIndex backends use httpx, which honors the same
env vars natively.

Usage
-----
    # discover by 1 username (typical case for creators)
    python -m rag.twins.discover_sources \
        --slug claire-vo \
        --name "Claire Vo" \
        --username clairevo

    # multiple usernames (people with handle drift across platforms)
    python -m rag.twins.discover_sources \
        --slug fernanda-faria \
        --name "Fernanda Faria" \
        --username fernandafaria --username fefaria

    # add Wayback Machine sweep for a known personal domain
    python -m rag.twins.discover_sources \
        --slug claire-vo --name "Claire Vo" --username clairevo \
        --wayback-domain claire.com --wayback-domain blog.claire.com

    # add iTunes sweep for guest podcast appearances (no auth)
    python -m rag.twins.discover_sources \
        --slug claire-vo --name "Claire Vo" --username clairevo \
        --enable-itunes

    # add Firecrawl podcast search as redundancy (requires FIRECRAWL_API_KEY)
    python -m rag.twins.discover_sources \
        --slug claire-vo --name "Claire Vo" --username clairevo \
        --enable-itunes --enable-firecrawl-podcasts

    # write fragment to file instead of stdout
    python -m rag.twins.discover_sources --slug ... --out /tmp/sources.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Mapping of site name (lowercased substring match) → SourceSpec.type.
# Order matters: first match wins. Keep specific patterns above generic ones.
# Types must be in VALID_SOURCE_TYPES from ingest_person.py:
#   {"interview", "podcast", "linkedin", "talk", "release", "book", "article", "crawl"}
_SITE_TYPE_MAP: list[tuple[str, str]] = [
    ("linkedin", "linkedin"),
    ("substack", "article"),
    ("medium", "article"),
    ("ghost", "article"),
    ("hashnode", "article"),
    ("dev.to", "article"),
    ("wordpress", "article"),
    ("blogger", "article"),
    ("tumblr", "article"),
    ("notion", "article"),
    ("spotify", "podcast"),
    ("anchor", "podcast"),
    ("apple podcasts", "podcast"),
    ("podcasts.apple", "podcast"),  # iTunes Search returns podcasts.apple.com URLs
    ("podchaser", "podcast"),
    ("goodreads", "book"),
    ("youtube", "article"),  # video metadata only; transcripts go via twins-run
    ("twitter", "article"),
    ("mastodon", "article"),
    ("threads", "article"),
    ("bluesky", "article"),
    ("github", "crawl"),
    ("gitlab", "crawl"),
]

# Tags Maigret attaches to sites we want to drop unconditionally.
_DROP_TAGS = {"porn", "adult", "nsfw", "dating", "gaming"}

# Sites we always drop regardless of tags (forums where username collisions
# are nearly guaranteed at the population level).
_DROP_SITES = {
    "4chan",
    "8kun",
    "reddit",
}


@dataclass
class DiscoveredSource:
    site_name: str
    url: str
    type: str
    tags: list[str] = field(default_factory=list)
    backend: str = "maigret"  # maigret | wayback | podcastindex
    notes: str | None = None


# ---------------------------------------------------------------------------
# Backend 1: Maigret
# ---------------------------------------------------------------------------


def run_maigret(
    username: str,
    *,
    top_sites: int = 500,
    timeout_per_site: int = 10,
    proxy: str | None = None,
) -> dict:
    """Invoke Maigret CLI, return parsed JSON report.

    Raises FileNotFoundError if maigret binary is absent (expected on the
    Claude Code sandbox; install lives on the DO runner).
    """
    if shutil.which("maigret") is None:
        raise FileNotFoundError(
            "maigret binary not found. Install with `pip install maigret` "
            "on the runner (DO droplet has it; sandbox does not)."
        )

    with tempfile.TemporaryDirectory(prefix="maigret-") as tmp:
        out_dir = Path(tmp)
        cmd = [
            "maigret",
            username,
            "--json",
            "simple",
            "--folderoutput",
            str(out_dir),
            "--no-progressbar",
            "--no-color",
            "--top-sites",
            str(top_sites),
            "--timeout",
            str(timeout_per_site),
        ]
        if proxy:
            cmd += ["--proxy", proxy]

        log.info("running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=top_sites * timeout_per_site + 60,
        )
        if result.returncode != 0:
            log.warning(
                "maigret exited %d (stderr: %s)",
                result.returncode,
                result.stderr.strip()[:300],
            )

        report_path = out_dir / f"report_{username}_simple.json"
        if not report_path.exists():
            candidates = list(out_dir.glob("*_simple.json"))
            if not candidates:
                raise RuntimeError(
                    f"maigret produced no JSON report for {username!r}; "
                    f"stderr: {result.stderr.strip()[:300]}"
                )
            report_path = candidates[0]

        return json.loads(report_path.read_text(encoding="utf-8"))


def filter_maigret(report: dict) -> list[DiscoveredSource]:
    """Filter Maigret raw report → high-signal DiscoveredSource list.

    Rules:
      - Only sites with status='Claimed' (positive match).
      - Drop adult/dating/gaming tags.
      - Drop hardcoded high-collision sites.
      - Dedupe by URL (Maigret occasionally double-reports mirrors).
    """
    # maigret <0.5 wrapped the per-site dict under "sites"; 0.6+ writes the
    # site map at the top level. Accept both — fall back to the report itself
    # when "sites" is absent and the top-level keys look like site payloads
    # (have "status" sub-dicts).
    sites = report.get("sites")
    if not sites and isinstance(report, dict):
        if any(isinstance(v, dict) and "status" in v for v in report.values()):
            sites = report
        else:
            sites = {}
    seen_urls: set[str] = set()
    out: list[DiscoveredSource] = []

    for site_name, payload in sites.items():
        status = payload.get("status", {})
        if status.get("status") != "Claimed":
            continue

        url = payload.get("url_user") or status.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        tags = [t.lower() for t in status.get("tags", [])]
        if any(t in _DROP_TAGS for t in tags):
            continue
        if site_name.lower() in _DROP_SITES:
            continue

        out.append(
            DiscoveredSource(
                site_name=site_name,
                url=url,
                type=classify(site_name),
                tags=tags,
                backend="maigret",
            )
        )

    return out


# ---------------------------------------------------------------------------
# Backend 2: Wayback Machine CDX API
# ---------------------------------------------------------------------------


def run_wayback(domain: str, *, limit: int = 200) -> list[DiscoveredSource]:
    """Query Wayback Machine CDX API for archived URLs under <domain>.

    Returns up to `limit` unique original URLs that were ever snapshotted.
    Useful for discovering blog posts that are no longer live (redesigns,
    moved domains, deleted content).

    Public API, no auth. Honors HTTPS_PROXY env var via httpx.
    """
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx required for Wayback backend") from e

    domain = domain.strip().rstrip("/")
    # CDX wildcard pattern: every URL under domain (any path).
    cdx_url = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "original,timestamp,statuscode",
        "collapse": "urlkey",
        "limit": str(limit),
        "filter": "statuscode:200",
    }
    log.info("wayback CDX: querying %s/* (limit=%d)", domain, limit)

    try:
        resp = httpx.get(cdx_url, params=params, timeout=30.0)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        log.error("wayback CDX failed for %s: %s", domain, e)
        return []

    # Format: first row is header [["original","timestamp","statuscode"], ...]
    if not rows or len(rows) < 2:
        return []
    data_rows = rows[1:]

    out: list[DiscoveredSource] = []
    for row in data_rows:
        original = row[0] if row else None
        if not original:
            continue
        # Skip the bare domain root (low-signal); keep deeper paths.
        if (
            original.rstrip("/") == f"https://{domain}"
            or original.rstrip("/") == f"http://{domain}"
        ):
            continue
        out.append(
            DiscoveredSource(
                site_name=f"Wayback ({domain})",
                url=original,
                type=classify(original),
                tags=["wayback", "historical"],
                backend="wayback",
                notes=f"snapshotted by archive.org (ts={row[1] if len(row) > 1 else '?'})",
            )
        )

    return out


# ---------------------------------------------------------------------------
# Backend 3: iTunes Search API (podcasts by term, no auth)
# ---------------------------------------------------------------------------


def run_itunes_podcasts(
    name: str, *, country: str = "BR", limit: int = 200
) -> list[DiscoveredSource]:
    """Query iTunes Search API for podcast episodes matching <name>.

    Public Apple endpoint, no auth. Returns Apple Podcasts URLs for episodes
    where the term appears in the metadata — captures both:
      - podcasts hosted by the person (caught also by Maigret)
      - guest spots in podcasts hosted by others (Maigret misses these)

    `country` defaults to BR (project context); pass `US` for broader EN
    coverage. Apple indexes globally but country tunes ranking + which
    storefront-specific entries surface first.
    """
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx required for iTunes backend") from e

    endpoint = "https://itunes.apple.com/search"
    params = {
        "term": name,
        "entity": "podcastEpisode",
        "country": country,
        "limit": str(limit),
    }
    log.info("itunes: querying podcastEpisode term=%r country=%s", name, country)

    try:
        resp = httpx.get(endpoint, params=params, timeout=30.0)
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        log.error("itunes failed for %s: %s", name, e)
        return []

    out: list[DiscoveredSource] = []
    for item in body.get("results") or []:
        url = item.get("trackViewUrl")
        if not url:
            continue
        feed = item.get("collectionName") or "Apple Podcasts"
        ep_title = item.get("trackName") or "(untitled episode)"
        release = item.get("releaseDate") or ""
        release_short = release[:10] if release else "?"
        notes = f"episode: {ep_title} (released {release_short})"
        out.append(
            DiscoveredSource(
                site_name=f"iTunes: {feed}",
                url=url,
                type="podcast",
                tags=["podcast", "itunes-indexed"],
                backend="itunes",
                notes=notes,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Backend 4: Firecrawl /search (podcast redundancy via web search)
# ---------------------------------------------------------------------------


def run_firecrawl_podcasts(name: str, *, limit: int = 30) -> list[DiscoveredSource]:
    """Search the web via Firecrawl for podcast pages mentioning <name>.

    Redundancy for the iTunes backend: catches podcasts that Apple does not
    index (independent feeds, niche shows, region-specific platforms).
    Query is scoped to known podcast hosts so we don't drown in mentions.

    Requires FIRECRAWL_API_KEY (already used elsewhere in this repo).
    Honors HTTPS_PROXY via httpx.
    """
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx required for Firecrawl backend") from e

    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        log.warning("Firecrawl podcasts disabled: FIRECRAWL_API_KEY not set")
        return []

    # Scope to podcast hosts so the query is podcast-shaped, not "any mention".
    query = (
        f'"{name}" (podcast OR interview OR episode) '
        f"(site:open.spotify.com OR site:podcasts.apple.com "
        f"OR site:youtube.com OR site:anchor.fm OR site:castbox.fm)"
    )
    log.info("firecrawl podcasts: query=%r limit=%d", query, limit)

    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v1/search",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": limit},
            timeout=45.0,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        log.error("firecrawl podcasts failed: %s", e)
        return []

    hits = body.get("data") or body.get("results") or []
    out: list[DiscoveredSource] = []
    for hit in hits:
        url = hit.get("url")
        if not url:
            continue
        title = (hit.get("title") or "").strip()
        host = urlparse(url).netloc or "Firecrawl"
        out.append(
            DiscoveredSource(
                site_name=f"Firecrawl/{host}",
                url=url,
                type="podcast",
                tags=["podcast", "firecrawl-search"],
                backend="firecrawl-podcasts",
                notes=f"matched title: {title[:120]}" if title else None,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def classify(site_name_or_url: str) -> str:
    """Map a site name or URL → SourceSpec.type. Default: 'crawl'."""
    needle = site_name_or_url.lower()
    for pattern, source_type in _SITE_TYPE_MAP:
        if pattern in needle:
            return source_type
    return "crawl"


def to_yaml_fragment(
    sources: list[DiscoveredSource],
    *,
    name: str,
    usernames: list[str],
    wayback_domains: list[str] | None = None,
    itunes_used: bool = False,
    firecrawl_used: bool = False,
) -> str:
    """Render discovered sources as a YAML fragment for spec paste-in.

    Output is intentionally pretty-printed + commented. Each entry has
    `# REVIEW` so the operator must consciously remove it before merging
    into the spec — that's the LGPD checkpoint.
    """
    backends_used = []
    if any(s.backend == "maigret" for s in sources):
        backends_used.append(f"maigret(usernames={usernames})")
    if wayback_domains:
        backends_used.append(f"wayback(domains={wayback_domains})")
    if itunes_used:
        backends_used.append(f"itunes(name={name!r})")
    if firecrawl_used:
        backends_used.append(f"firecrawl-podcasts(name={name!r})")

    if not sources:
        return (
            f"# discover_sources: 0 high-signal results for {name!r}\n"
            f"# backends tried: {backends_used}\n"
            f"# Either the person has minimal digital footprint, the\n"
            f"# usernames are off, or no backend was enabled. Try variants\n"
            f"# (full name, middle name, alternate handle, alt country).\n"
        )

    by_backend: dict[str, int] = {}
    for s in sources:
        by_backend[s.backend] = by_backend.get(s.backend, 0) + 1

    lines = [
        f"# discover_sources output for {name}",
        f"# backends: {backends_used}",
        f"# total candidates: {len(sources)}  (by backend: {by_backend})",
        "#",
        "# Pipeline rule: every URL below MUST be opened and verified to",
        "# belong to the right person. Each backend matches by a different",
        "# heuristic (username / domain / name-in-metadata) and any of them",
        "# can produce false positives. Same handle ≠ same human.",
        "",
        "sources:",
    ]
    for s in sources:
        review_meta = f"backend={s.backend}, site={s.site_name}, tags={s.tags or []}"
        if s.notes:
            review_meta += f", notes={s.notes!r}"
        lines.append(f"  # REVIEW — {review_meta}")
        lines.append(f"  - url: {s.url}")
        lines.append(f'    title: "{s.site_name}"')
        lines.append(f"    type: {s.type}")
        lines.append("    first_person: true")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Discover candidate sources for a twin spec via Maigret + "
            "Wayback Machine + iTunes Search + Firecrawl."
        )
    )
    parser.add_argument("--slug", required=True, help="twin slug (for output naming)")
    parser.add_argument("--name", required=True, help="person's public name")
    parser.add_argument(
        "--username",
        action="append",
        required=True,
        help="known username (can be passed multiple times)",
    )
    parser.add_argument(
        "--top-sites",
        type=int,
        default=500,
        help="Maigret top-sites limit (default: 500). Use 100 for smoke tests.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="per-site timeout in seconds for Maigret (default: 10)",
    )
    parser.add_argument(
        "--wayback-domain",
        action="append",
        default=[],
        help=(
            "personal domain to query Wayback Machine for archived URLs "
            "(can be passed multiple times). Skips the Wayback backend if absent."
        ),
    )
    parser.add_argument(
        "--wayback-limit",
        type=int,
        default=200,
        help="max archived URLs per domain (default: 200)",
    )
    parser.add_argument(
        "--enable-itunes",
        action="store_true",
        help=(
            "enable iTunes Search API podcast lookup (no auth). Catches "
            "Apple-indexed podcasts where the person appears (host or guest)."
        ),
    )
    parser.add_argument(
        "--itunes-country",
        default="BR",
        help="iTunes storefront country (default: BR). Use US for broader EN coverage.",
    )
    parser.add_argument(
        "--enable-firecrawl-podcasts",
        action="store_true",
        help=(
            "enable Firecrawl /search redundancy for podcasts (web search "
            "scoped to podcast hosts). Requires FIRECRAWL_API_KEY env var."
        ),
    )
    parser.add_argument(
        "--firecrawl-limit",
        type=int,
        default=30,
        help="Firecrawl podcast search result limit (default: 30)",
    )
    parser.add_argument(
        "--skip-maigret",
        action="store_true",
        help="skip Maigret sweep (use only Wayback / iTunes / Firecrawl)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write YAML fragment here instead of stdout",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable INFO logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Normalize HTTPS_PROXY / YTDLP_PROXY if they arrived in Webshare-list
    # format (host:port:user:pass). Idempotent — well-formed URLs pass
    # through unchanged. See rag/twins/proxy_utils.py.
    from rag.twins.proxy_utils import normalize_proxy_env

    normalize_proxy_env()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("YTDLP_PROXY")

    all_sources: list[DiscoveredSource] = []
    seen_urls: set[str] = set()

    def _merge(items: list[DiscoveredSource]) -> None:
        for s in items:
            if s.url in seen_urls:
                continue
            seen_urls.add(s.url)
            all_sources.append(s)

    # Backend 1: Maigret
    if not args.skip_maigret:
        for username in args.username:
            log.info("maigret: scanning username=%s", username)
            try:
                report = run_maigret(
                    username,
                    top_sites=args.top_sites,
                    timeout_per_site=args.timeout,
                    proxy=proxy,
                )
            except FileNotFoundError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            except Exception as e:
                log.error("maigret failed for %s: %s", username, e)
                continue
            _merge(filter_maigret(report))

    # Backend 2: Wayback Machine
    for domain in args.wayback_domain:
        try:
            _merge(run_wayback(domain, limit=args.wayback_limit))
        except Exception as e:
            log.error("wayback failed for %s: %s", domain, e)

    # Backend 3: iTunes Search API
    if args.enable_itunes:
        try:
            _merge(run_itunes_podcasts(args.name, country=args.itunes_country))
        except Exception as e:
            log.error("itunes failed: %s", e)

    # Backend 4: Firecrawl podcast redundancy
    if args.enable_firecrawl_podcasts:
        try:
            _merge(run_firecrawl_podcasts(args.name, limit=args.firecrawl_limit))
        except Exception as e:
            log.error("firecrawl-podcasts failed: %s", e)

    # Final sort: backend → type → site_name (stable, easy to scan).
    all_sources.sort(key=lambda s: (s.backend, s.type, s.site_name.lower()))

    fragment = to_yaml_fragment(
        all_sources,
        name=args.name,
        usernames=args.username,
        wayback_domains=args.wayback_domain or None,
        itunes_used=args.enable_itunes,
        firecrawl_used=args.enable_firecrawl_podcasts,
    )

    if args.out:
        args.out.write_text(fragment, encoding="utf-8")
        print(f"wrote {len(all_sources)} candidate(s) → {args.out}")
    else:
        print(fragment)

    return 0


if __name__ == "__main__":
    sys.exit(main())
