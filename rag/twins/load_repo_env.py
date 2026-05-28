"""Load repo-local env files before twins API calls.

Cloud Agents inject secrets at VM start; a stale or revoked ``ANTHROPIC_API_KEY``
there blocks Opus builds. ``.env.local`` (gitignored) overrides injected values
when present — same precedence as local Claude Code / ``SETUP_AUTH.md``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOADED = False


def load_repo_env(*, override: bool = True) -> bool:
    """Load ``.env.local`` then ``.env`` from repo root. Idempotent."""
    global _LOADED
    if _LOADED:
        return True

    try:
        from dotenv import load_dotenv
    except ImportError:
        log.debug("python-dotenv not installed — skipping .env.local")
        _LOADED = True
        return False

    loaded_any = False
    for name in (".env.local", ".env"):
        path = _REPO_ROOT / name
        if path.is_file():
            load_dotenv(path, override=override)
            log.info("loaded %s", path)
            loaded_any = True
    _LOADED = True
    return loaded_any
