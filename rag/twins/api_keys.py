"""Validate API keys used by the twins pipeline (no secret values logged)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from rag.twins.load_repo_env import load_repo_env

log = logging.getLogger(__name__)


@dataclass
class KeyStatus:
    name: str
    configured: bool
    ok: bool
    detail: str


def _probe_anthropic(key: str) -> tuple[bool, str]:
    try:
        import httpx
    except ImportError:
        return False, "httpx not installed"
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-3-5-haiku-latest",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "ping"}],
            },
            timeout=30.0,
        )
    except Exception as e:
        return False, str(e)[:120]
    if resp.status_code == 200:
        return True, "ok"
    try:
        err = resp.json().get("error", {})
        msg = err.get("message", resp.text[:120])
    except Exception:
        msg = resp.text[:120]
    return False, f"HTTP {resp.status_code}: {msg}"


def _probe_openai(key: str) -> tuple[bool, str]:
    try:
        import httpx
    except ImportError:
        return False, "httpx not installed"
    try:
        resp = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30.0,
        )
    except Exception as e:
        return False, str(e)[:120]
    if resp.status_code == 200:
        return True, "ok"
    return False, f"HTTP {resp.status_code}: {resp.text[:120]}"


def anthropic_key() -> str:
    load_repo_env()
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def openai_key() -> str:
    load_repo_env()
    return os.environ.get("OPENAI_API_KEY", "").strip()


def deepseek_key() -> str:
    load_repo_env()
    return (
        os.environ.get("DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("DEEPSEEK_PRO_API_KEY", "").strip()
    )


def _probe_deepseek(key: str) -> tuple[bool, str]:
    try:
        import httpx
    except ImportError:
        return False, "httpx not installed"
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.environ.get("TWINS_BUILD_MODEL_DEEPSEEK", "deepseek-v4-pro"),
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
                "thinking": {"type": "disabled"},
            },
            timeout=45.0,
        )
    except Exception as e:
        return False, str(e)[:120]
    if resp.status_code == 200:
        return True, "ok"
    try:
        err = resp.json().get("error", {})
        msg = err.get("message", resp.text[:120])
    except Exception:
        msg = resp.text[:120]
    return False, f"HTTP {resp.status_code}: {msg}"


def check_anthropic(*, probe: bool = True) -> KeyStatus:
    key = anthropic_key()
    if not key:
        return KeyStatus("ANTHROPIC_API_KEY", False, False, "not set")
    if not probe or os.environ.get("TWINS_SKIP_KEY_PROBE", "").lower() in ("1", "true", "yes"):
        return KeyStatus("ANTHROPIC_API_KEY", True, True, "configured (probe skipped)")
    ok, detail = _probe_anthropic(key)
    return KeyStatus("ANTHROPIC_API_KEY", True, ok, detail)


def check_openai(*, probe: bool = True) -> KeyStatus:
    key = openai_key()
    if not key:
        return KeyStatus("OPENAI_API_KEY", False, False, "not set")
    if not probe or os.environ.get("TWINS_SKIP_KEY_PROBE", "").lower() in ("1", "true", "yes"):
        return KeyStatus("OPENAI_API_KEY", True, True, "configured (probe skipped)")
    ok, detail = _probe_openai(key)
    return KeyStatus("OPENAI_API_KEY", True, ok, detail)


def check_deepseek(*, probe: bool = True) -> KeyStatus:
    key = deepseek_key()
    if not key:
        return KeyStatus("DEEPSEEK_API_KEY", False, False, "not set")
    if not probe or os.environ.get("TWINS_SKIP_KEY_PROBE", "").lower() in ("1", "true", "yes"):
        return KeyStatus("DEEPSEEK_API_KEY", True, True, "configured (probe skipped)")
    ok, detail = _probe_deepseek(key)
    return KeyStatus("DEEPSEEK_API_KEY", True, ok, detail)


def resolve_build_provider() -> str:
    """Return ``deepseek``, ``anthropic``, or ``openai`` for twin extraction."""
    forced = os.environ.get("TWINS_BUILD_LLM_PROVIDER", "auto").strip().lower()
    if forced in ("deepseek", "deepseekpro", "anthropic", "openai"):
        if forced == "deepseekpro":
            return "deepseek"
        return forced
    if forced not in ("", "auto"):
        log.warning("unknown TWINS_BUILD_LLM_PROVIDER=%s — using auto", forced)

    deepseek_st = check_deepseek()
    if deepseek_st.ok:
        return "deepseek"
    anth = check_anthropic()
    if anth.ok:
        if deepseek_st.configured and not deepseek_st.ok:
            log.warning("DEEPSEEK_API_KEY invalid (%s) — using Anthropic", deepseek_st.detail)
        return "anthropic"
    openai_st = check_openai()
    if openai_st.ok:
        log.warning(
            "Using OpenAI for build (deepseek=%s; anthropic=%s)",
            deepseek_st.detail,
            anth.detail,
        )
        return "openai"
    raise RuntimeError(
        "No working LLM for twin build. Set DEEPSEEK_API_KEY (deepseek-v4-pro) in "
        "cursor.com/agents → Secrets, or fix ANTHROPIC_API_KEY / OPENAI_API_KEY. "
        f"deepseek={deepseek_st.detail}; anthropic={anth.detail}; openai={openai_st.detail}"
    )
