from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from tts_shared.config import get_settings


settings = get_settings()


def is_authenticated(request: Request) -> bool:
    if request.session.get("authenticated") is True:
        return True

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return secrets.compare_digest(token, settings.app_access_token)


def require_auth(request: Request) -> None:
    if is_authenticated(request):
        return
    raise HTTPException(
        status_code=401,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
