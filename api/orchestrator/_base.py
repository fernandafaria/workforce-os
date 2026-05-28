"""
Workforce OS — Base orchestrator utilities.
Shared LLM call logic for all orchestrators.
"""

from ..config import get_settings


async def llm_call(system_prompt: str, user_message: str) -> str:
    """Call DeepSeek V4 Pro for agent response."""
    settings = get_settings()
    if not settings.deepseek_api_key:
        return "[LLM não configurado — resposta stub]"

    import httpx
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": (system_prompt or "")[:3000]},
                        {"role": "user", "content": user_message[:6000]},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erro LLM: {e}]"
