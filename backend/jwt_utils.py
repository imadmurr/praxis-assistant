# backend/jwt_utils.py

import os
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from typing import Optional, Dict

load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_insecure_key")
ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")

def create_jwt(user_id, username, exp_minutes=1320):
    """
    Create a JSON Web Token for the given user.

    Parameters
    ----------
    user_id : str | int
        Unique user identifier. Will be stored under the `sub` claim.
    username : str
        Human-friendly username.
    exp_minutes : int
        Expiration in minutes (default ~22h).

    Returns
    -------
    str
        Signed JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    # PyJWT>=2 returns str for non-rsa; keep it as-is
    return token

def verify_jwt(token: str) -> Optional[Dict]:
    """
    Verify a JWT and return its payload if valid, otherwise None.

    Parameters
    ----------
    token : str
        The JWT as a compact JWS string.

    Returns
    -------
    dict | None
        The decoded payload if the token is valid, otherwise `None`.
        The payload will include at least the `sub` claim and may
        include additional fields such as `username`.
    """
    try:
        # Important: `algorithms` expects a list
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def extract_bearer(auth_header: str) -> Optional[str]:
    """
    Given an Authorization header value, return the JWT if present.
    """
    if not auth_header or not isinstance(auth_header, str):
        return None
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip() or None
