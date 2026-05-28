"""Proxy URL normalization helpers.

Defensive layer against a recurring misconfiguration: residential-proxy
providers (Webshare etc.) export their pools as "Proxy List Download"
text in `host:port:user:pass` format. Operators paste that string into
`YTDLP_PROXY` / `HTTPS_PROXY` secrets verbatim, and consumers explode:

- yt-dlp: `ERROR: nonnumeric port: '<password>'` (parses first `:` as
  host:port, then chokes on the rest)
- httpx: silently drops the malformed proxy and tries direct connection,
  which then bot-detects on YouTube/LinkedIn

The fix is one regex away. Doing it once at process startup means every
consumer (yt-dlp subprocess, httpx-via-Firecrawl, aiohttp-via-Maigret)
gets the corrected URL without each having to learn the failure mode.

Idempotent: well-formed `http://user:pass@host:port/` passes through
unchanged. Empty/None returns None.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# All env vars Python and subprocesses (yt-dlp) check for proxy config.
# Includes both upper- and lower-case variants because httpx + curl-style
# tools differ on which they read.
PROXY_ENV_VARS = (
    "YTDLP_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "https_proxy",
    "http_proxy",
)


def normalize_proxy_url(raw: str | None) -> str | None:
    """Convert common proxy-string formats to the URL form clients expect.

    Recognized inputs:
      - None / "" → None
      - "http://..." / "https://..." / "socks5://..." → passthrough
      - "host:port:user:pass" (Webshare list format, 3 colons, no @) →
        "http://user:pass@host:port/"
      - "host:port" (no auth) → "http://host:port/"

    Unknown formats pass through unchanged so downstream raises clearly
    instead of us silently mangling something we didn't anticipate.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    # Already a URL — passthrough. Catches http://, https://, socks5://, etc.
    if "://" in s:
        return s
    parts = s.split(":")
    # Webshare list format: host:port:user:pass with no `@` (auth not yet
    # URL-encoded). Requires numeric port to avoid false positives like
    # IPv6 fragments.
    if len(parts) == 4 and "@" not in s:
        host, port, user, pwd = parts
        if port.isdigit() and host and user and pwd:
            return f"http://{user}:{pwd}@{host}:{port}/"
    # Bare host:port without auth — prepend scheme.
    if len(parts) == 2 and parts[1].isdigit() and parts[0]:
        return f"http://{s}/"
    # Unknown — let downstream surface the real error.
    return s


def normalize_proxy_env() -> dict[str, str]:
    """Normalize all proxy env vars in `os.environ` in-place.

    Call once at the top of an entry-point script (CLI main, worker
    init). Returns a dict of vars that were rewritten, empty if nothing
    changed. Idempotent — safe to call multiple times.
    """
    changed: dict[str, str] = {}
    for var in PROXY_ENV_VARS:
        if var not in os.environ:
            continue
        raw = os.environ[var]
        normalized = normalize_proxy_url(raw)
        if normalized is None:
            continue
        if normalized != raw:
            os.environ[var] = normalized
            changed[var] = normalized
            log.info(
                "normalized proxy env var %s (Webshare-list → URL format)", var
            )
    return changed
