"""
Workforce OS — Telegram Channel Webhook
Receives Telegram messages and routes to Council/Group/Ping.

Integrates with Febrain's existing Telegram infrastructure
(company_channels table) rather than building from scratch.
"""

from fastapi import APIRouter, Request, HTTPException
from typing import Optional
import logging
import json

from ..config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/channels/telegram", tags=["channels"])

# Telegram bot token — from env or shared Febrain config
TELEGRAM_BOT_TOKEN = None  # Lazily loaded from settings


def _get_token() -> str:
    global TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        import os
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    return TELEGRAM_BOT_TOKEN


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram message via webhook.

    Expected payload: Telegram Update object.
    Routes to Council endpoint for question processing.

    Febrain integration: uses existing company_channels table
    for channel configuration (not reimplementing).
    """
    body = await request.json()
    log.info(f"Telegram webhook received: {json.dumps(body, indent=2)[:500]}")

    # Extract message
    message = body.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not text or not chat_id:
        return {"status": "ignored", "reason": "no text or chat_id"}

    # Route to Council as default mode
    # In production: parse commands (/council, /group, /ping)
    try:
        from ..orchestrator import CouncilOrchestrator
        from ..formatter.hierarchical import HierarchicalFormatter

        orch = CouncilOrchestrator()
        result = await orch.execute(text, context=None, agent_slugs=None)

        formatter = HierarchicalFormatter()
        formatted = await formatter.format_council(
            text,
            result["responses"],
            result.get("synthesis", ""),
        )

        # Send reply via Telegram API
        reply_text = formatted.get("markdown", json.dumps(formatted))[:4000]
        await _send_telegram_message(chat_id, reply_text)

        return {"status": "processed", "chat_id": chat_id, "reply_length": len(reply_text)}

    except Exception as e:
        log.error(f"Telegram webhook processing failed: {e}")
        await _send_telegram_message(chat_id, "❌ Erro ao processar sua pergunta. Tente novamente.")
        return {"status": "error", "error": str(e)}


@router.get("/setup")
async def telegram_setup_info():
    """Return Telegram bot setup instructions."""
    token = _get_token()
    return {
        "status": "configured" if token else "missing_token",
        "webhook_url": f"{get_settings().supabase_url}/channels/telegram/webhook",
        "setup_steps": [
            "1. Set TELEGRAM_BOT_TOKEN in environment",
            "2. Set webhook: curl https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WEBHOOK_URL>",
            "3. Test: send /start to your bot",
        ],
    }


@router.get("/health")
async def telegram_health():
    """Health check for Telegram channel."""
    token = _get_token()
    if not token:
        return {"status": "unconfigured", "error": "TELEGRAM_BOT_TOKEN not set"}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "ok",
                    "bot": data.get("result", {}).get("username", "unknown"),
                }
            return {"status": "error", "telegram_error": resp.text}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _send_telegram_message(chat_id: int, text: str) -> None:
    """Send message via Telegram Bot API."""
    token = _get_token()
    if not token:
        log.warning("Cannot send Telegram message: no token configured")
        return

    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
    except Exception as e:
        log.error(f"Failed to send Telegram message: {e}")
