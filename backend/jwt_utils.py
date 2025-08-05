# backend/jwt_utils.py

import os
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_insecure_key")
ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")

def create_jwt(user_id, username, exp_minutes=60):
    """
    Create a JSON Web Token for the given user.

    Parameters
    ----------
    user_id : int or str
        A unique identifier for the user. This will be stored in the
        `sub` (subject) claim of the JWT. Using an integer ID makes
        it harder to guess a user's identity and decouples the token
        payload from the user's login name.
    username : str, optional
        The human-readable login name or email address associated with
        the user. If provided, it will be stored in the `username`
        claim of the token. This allows backends or UIs to display
        friendly names without embedding them in the subject claim.
    exp_minutes : int, optional
        How many minutes from now the token should remain valid.

    Returns
    -------
    str
        The encoded JWT as a compact URL-safe string.
    """
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=exp_minutes)
    }
    return jwt.encode(payload=payload, key=SECRET_KEY, algorithm=ALGORITHM)

def verify_jwt(token):
    """
    Decode and validate a JWT.

    Parameters
    ----------
    token : str
        The encoded JWT provided by the client.

    Returns
    -------
    dict | None
        The decoded payload if the token is valid, otherwise `None`.
        The payload will include at least the `sub` claim and may
        include additional fields such as `username`.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithm=ALGORITHM)
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
