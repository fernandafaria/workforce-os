"""Structured twin extraction via Anthropic, DeepSeek, or OpenAI."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from rag.twins.api_keys import resolve_build_provider

log = logging.getLogger(__name__)

DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-pro"
OPENAI_DEFAULT_MODEL = "gpt-4o"
ANTHROPIC_DEFAULT_MODEL = "claude-opus-4-7"

# User-facing aliases → official API model ids
_MODEL_ALIASES = {
    "deepseekpro": DEEPSEEK_DEFAULT_MODEL,
    "deepseek-pro": DEEPSEEK_DEFAULT_MODEL,
    "deepseek_v4_pro": DEEPSEEK_DEFAULT_MODEL,
}


def resolve_build_model(provider: str, model: str | None) -> str:
    if model:
        return _MODEL_ALIASES.get(model.strip().lower(), model)
    if provider == "deepseek":
        return os.environ.get("TWINS_BUILD_MODEL_DEEPSEEK", DEEPSEEK_DEFAULT_MODEL).strip()
    if provider == "openai":
        return os.environ.get("TWINS_BUILD_MODEL_OPENAI", OPENAI_DEFAULT_MODEL).strip()
    return os.environ.get("TWINS_BUILD_MODEL_ANTHROPIC", ANTHROPIC_DEFAULT_MODEL).strip()


def extract_structured(
    corpus_text: str,
    *,
    tool_schema: dict[str, Any],
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    provider: str | None = None,
) -> dict[str, Any]:
    """Run tool-style structured extraction with the configured LLM provider."""
    chosen = provider or resolve_build_provider()
    resolved_model = resolve_build_model(chosen, model)
    log.info("llm_extract provider=%s model=%s", chosen, resolved_model)

    if chosen == "deepseek":
        return _extract_deepseek(
            corpus_text,
            tool_schema=tool_schema,
            system_prompt=system_prompt,
            user_message=user_message,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if chosen == "openai":
        return _extract_openai(
            corpus_text,
            tool_schema=tool_schema,
            system_prompt=system_prompt,
            user_message=user_message,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )
    return _extract_anthropic(
        corpus_text,
        tool_schema=tool_schema,
        system_prompt=system_prompt,
        user_message=user_message,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _openai_style_tool(tool_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool_schema["name"],
            "description": tool_schema.get("description", ""),
            "parameters": tool_schema["input_schema"],
        },
    }


def _parse_tool_arguments(resp: Any) -> dict[str, Any]:
    choice = resp.choices[0]
    tool_calls = getattr(choice.message, "tool_calls", None) or []
    if not tool_calls:
        raise RuntimeError("LLM response did not include tool_calls")
    raw = tool_calls[0].function.arguments
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def _extract_openai(
    corpus_text: str,
    *,
    tool_schema: dict[str, Any],
    system_prompt: str,
    user_message: str,
    model: str,
    temperature: float,
    max_tokens: int,
    base_url: str,
    api_key_env: str,
) -> dict[str, Any]:
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("openai SDK not installed") from e

    key = os.environ.get(api_key_env, "").strip()
    if not key:
        raise RuntimeError(f"{api_key_env} not set")

    client = OpenAI(api_key=key, base_url=base_url.rstrip("/"))
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message + "\n\n" + corpus_text},
        ],
        tools=[_openai_style_tool(tool_schema)],
        tool_choice={
            "type": "function",
            "function": {"name": tool_schema["name"]},
        },
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _parse_tool_arguments(resp)


def _extract_deepseek(
    corpus_text: str,
    *,
    tool_schema: dict[str, Any],
    system_prompt: str,
    user_message: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    key = (
        os.environ.get("DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("DEEPSEEK_PRO_API_KEY", "").strip()
    )
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set — add at cursor.com/agents → Secrets "
            "(model: deepseek-v4-pro)"
        )
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    # Non-thinking mode for deterministic JSON tool output (faster/cheaper).
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("openai SDK not installed") from e

    client = OpenAI(api_key=key, base_url=base_url.rstrip("/"))
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message + "\n\n" + corpus_text},
        ],
        tools=[_openai_style_tool(tool_schema)],
        tool_choice={
            "type": "function",
            "function": {"name": tool_schema["name"]},
        },
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return _parse_tool_arguments(resp)


def _extract_anthropic(
    corpus_text: str,
    *,
    tool_schema: dict[str, Any],
    system_prompt: str,
    user_message: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed") from e

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=key)
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "tools": [tool_schema],
        "tool_choice": {"type": "tool", "name": tool_schema["name"]},
        "messages": [
            {
                "role": "user",
                "content": user_message + "\n\n" + corpus_text,
            }
        ],
    }
    if not model.startswith("claude-opus-4") and not model.startswith("claude-sonnet-4-6"):
        kwargs["temperature"] = temperature
    resp = client.messages.create(**kwargs)

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    raise RuntimeError("Anthropic response did not include a tool_use block")
