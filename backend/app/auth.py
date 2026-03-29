"""JWT authentication utilities and FastAPI dependency."""

from __future__ import annotations

import hashlib
import hmac as _hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

_ALGORITHM = "HS256"
_EXPIRE_HOURS = 24 * 7  # 7 days


def create_access_token(user_id: UUID, secret: str) -> str:
    """Return a signed JWT encoding the given user_id."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret: str) -> UUID:
    """Decode and validate a JWT; return the user_id or raise HTTP 401."""
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def make_csrf_token(session_id: str, user_id: str, secret: str) -> str:
    """Return an HMAC-SHA256 token bound to a specific session and user.

    Stateless — verifiable without DB storage. Uses the JWT secret so only
    the server can produce valid tokens. Inputs are expected to be UUIDs
    (which never contain ':'), keeping the ':' separator unambiguous.
    """
    msg = f"{session_id}:{user_id}".encode()
    return _hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    token: str | None = Query(default=None, include_in_schema=False),
    settings: Settings = Depends(get_settings),
) -> UUID:
    """FastAPI dependency: extract and verify the caller's JWT.

    Accepts the token from either:
    - ``Authorization: Bearer <token>`` header (API clients, JS fetch calls)
    - ``?token=<token>`` query parameter (browser review page initial load)
    """
    raw = (credentials.credentials if credentials else None) or token
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(raw, settings.jwt_secret_key.get_secret_value())
