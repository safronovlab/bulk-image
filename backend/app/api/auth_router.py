"""
HTTP-обработка авторизации — login, logout.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.models import LoginRequest, TokenResponse
from app.dependencies import get_auth_provider, get_raw_token, rate_limit_login

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    _rate: None = Depends(rate_limit_login),
):
    auth_provider = get_auth_provider()
    ip = request.client.host if request.client else "unknown"

    result = auth_provider.authenticate(body.username, body.password)

    if result is None:
        logger.warning(
            f"Failed login attempt: ip={ip} username={body.username}"
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token, session_id, expires_at = result
    logger.info(f"Successful login: ip={ip} username={body.username}")

    return TokenResponse(token=token, expires_at=expires_at.isoformat())


@router.post("/logout")
def logout(
    request: Request,
    token: str = Depends(get_raw_token),
):
    auth_provider = get_auth_provider()

    # Validate token first
    session_id = auth_provider.validate_token(token)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    auth_provider.invalidate_token(token)
    return {"detail": "Logged out successfully"}
