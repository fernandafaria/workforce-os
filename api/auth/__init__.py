"""
Workforce OS — Auth: JWT validation for Supabase tokens.
Validates Supabase-issued JWTs against the project's JWT secret.
"""

import os
from typing import Optional
from fastapi import HTTPException, Request
from supabase import create_client

from ..config import get_settings


async def get_user_id(request: Request) -> str:
    """Extract and validate user_id from Supabase JWT.

    Returns:
        user_id (UUID string) if valid
    Raises:
        HTTPException(401) if no token or invalid
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    token = auth_header[7:]
    settings = get_settings()

    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        user = client.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(401, "Invalid or expired token")


def validate_jwt(token: str) -> Optional[str]:
    """Validate a Supabase JWT and return user_id.

    Returns None if invalid (non-raising version for internal use).
    """
    try:
        settings = get_settings()
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        user = client.auth.get_user(token)
        return user.user.id
    except Exception:
        return None
