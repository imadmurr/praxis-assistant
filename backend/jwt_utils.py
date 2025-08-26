# backend/jwt_utils.py
"""
JWT utilities for Praxis Assistant (HS256).
- Verifies Authorization: Bearer <token> on protected routes.
- Extracts user_id from the 'sub' claim and stores it in flask.g.user_id.
- Postpones issuer/audience checks until Praxis shares final values.

Environment:
  JWT_SECRET_KEY  -> HS256 shared secret used to verify the token signature.
"""

from __future__ import annotations

import os
import functools
from typing import Optional, Dict, Any

import jwt
from flask import request, g, abort


def _require_secret() -> str:
    """
    Read the HS256 secret at call-time (not import-time) to avoid
    'secret not set' issues when env gets loaded after imports.
    """
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. "
            "Set it in your environment/config before handling JWTs."
        )
    return secret


def get_bearer_token() -> Optional[str]:
    """Read the Bearer token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.startswith("Bearer "):
        return None
    return auth.split(" ", 1)[1].strip()


def decode_jwt(token: str) -> Dict[str, Any]:
    """
    Decode and verify an HS256 JWT.
    - Requires 'exp' by default.
    - Does NOT enforce 'iss' or 'aud' yet (postponed by request).
    """
    secret = _require_secret()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        abort(401, description="Token expired.")
    except jwt.InvalidTokenError:
        abort(401, description="Invalid token.")


# Back-compat helper: some existing code imports verify_jwt()
def verify_jwt(token: str) -> Dict[str, Any]:
    """
    Backward-compatible wrapper used by existing app.py.
    Returns the decoded payload (raises/aborts on failure).
    """
    return decode_jwt(token)


def require_jwt(fn):
    """
    Decorator that:
    - Extracts and verifies the Bearer token.
    - Puts user id from 'sub' into g.user_id.
    - Also exposes the full payload on g.jwt_payload (optional use).
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = get_bearer_token()
        if not token:
            abort(401, description="Missing Authorization: Bearer token.")
        payload = decode_jwt(token)

        user_id = payload.get("sub")
        if not user_id:
            abort(401, description="Token is missing 'sub' (user id).")

        g.user_id = str(user_id)
        g.jwt_payload = payload
        return fn(*args, **kwargs)
    return wrapper


def current_user_id() -> Optional[str]:
    """Convenience accessor for the user id stored by @require_jwt."""
    return getattr(g, "user_id", None)
