# backend/shell.py
"""
Quick smoke tests for Praxis Assistant backend.

What it does when you run `python backend/shell.py`:
  1) Pings MongoDB and prints the active indexes.
  2) If JWT_SECRET_KEY is set, generates a dev token for sub="smoke-user",
     prints it, and decodes it via backend.jwt_utils.decode_jwt.
  3) If your app exposes GET /api/me with @require_jwt, it will call it
     using Flask's test client and print the result.

You can also run specific actions:
  python backend/shell.py --ping-db
  python backend/shell.py --gen-token --sub alice --minutes 120
  python backend/shell.py --decode --token <JWT>
  python backend/shell.py --test-me --token <JWT>

Environment:
  MONGO_URL        (or MONGODB_URI)  -> Mongo connection
  JWT_SECRET_KEY                      -> HS256 secret for JWTs

Dependencies:
  PyJWT, pymongo, Flask (already used by your app)
"""

from __future__ import annotations

import os
import sys
import argparse
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# ---- flexible imports so you can run from repo root or from /backend ----
try:
    from db import db, chats, messages, ping as mongo_ping
except Exception:
    # If package-style import fails, try local (when running from /backend)
    from db import db, chats, messages, ping as mongo_ping  # type: ignore

try:
    from jwt_utils import decode_jwt
except Exception:
    from jwt_utils import decode_jwt  # type: ignore

try:
    # Try to import the Flask app for the /api/me test
    from app import app as flask_app
except Exception:
    try:
        from app import app as flask_app  # type: ignore
    except Exception:
        flask_app = None  # Not fatal; /api/me test will be skipped

try:
    import jwt  # PyJWT
except Exception as e:
    print("ERROR: PyJWT not installed. Add 'PyJWT>=2.8,<3' to requirements.txt.")
    raise

load_dotenv()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")


# ---- Utilities ----

def print_mongo_status() -> None:
    print("== Mongo status ==")
    print(f"db: {db.name} ping: {mongo_ping()}")
    print("chats idx:", [i for i in chats.list_indexes()])
    print("messages idx:", [i for i in messages.list_indexes()])
    print()


def generate_dev_token(sub: str, minutes: int = 60) -> str:
    """
    Create an HS256 JWT for quick local testing.
    - Uses JWT_SECRET_KEY from env.
    - Adds 'sub' and 'exp' claims.
    """
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Export it to generate a token, e.g.\n"
            "  export JWT_SECRET_KEY='devsecret'"
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        # You can add dev-only claims here if needed
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    # PyJWT may return str or bytes depending on version; ensure str
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_and_print(token: str) -> None:
    print("== Decoding token via jwt_utils.decode_jwt ==")
    payload = decode_jwt(token)
    print("payload:", payload)
    print()


def test_api_me(token: str) -> None:
    """
    Calls GET /api/me with the provided token using Flask's test client.
    Skips if the app or route is unavailable.
    """
    if flask_app is None:
        print("== /api/me test skipped (Flask app not importable) ==")
        return
    print("== /api/me (Flask test client) ==")
    with flask_app.test_client() as client:
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        print("status:", resp.status_code)
        try:
            print("json:", resp.get_json())
        except Exception:
            print("body:", resp.data.decode("utf-8", errors="ignore"))
    print()


# ---- CLI ----

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Praxis Assistant backend smoke tests")
    p.add_argument("--ping-db", action="store_true", help="Ping Mongo and list indexes")

    p.add_argument("--gen-token", action="store_true", help="Generate a dev JWT")
    p.add_argument("--sub", type=str, default="smoke-user", help="sub claim for dev token")
    p.add_argument("--minutes", type=int, default=60, help="Token lifetime in minutes")

    p.add_argument("--decode", action="store_true", help="Decode a JWT using jwt_utils")
    p.add_argument("--token", type=str, help="JWT to decode or to use with --test-me")

    p.add_argument("--test-me", action="store_true", help="Call /api/me with a token")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Default behavior: run everything helpful if no flags are passed
    run_all = not any([args.ping_db, args.gen_token, args.decode, args.test_me])

    if args.ping_db or run_all:
        print_mongo_status()

    generated = None
    if args.gen_token or run_all:
        try:
            generated = generate_dev_token(args.sub, args.minutes)
            print("== Generated dev token ==")
            print(generated)
            print()
        except Exception as e:
            print(f"Could not generate token: {e}\n")

    if args.decode or (run_all and (generated or args.token)):
        token = args.token or generated
        if token:
            try:
                decode_and_print(token)
            except Exception as e:
                print(f"Decode failed: {e}\n")
        else:
            print("No token to decode. Use --token or --gen-token.\n")

    if args.test_me or run_all:
        token = args.token or generated
        if token:
            test_api_me(token)
        else:
            print("== /api/me test skipped (no token). Use --token or --gen-token. ==\n")


if __name__ == "__main__":
    main()
