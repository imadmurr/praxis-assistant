# backend/shell.py
"""
Quick smoke tests for Praxis Assistant backend.

What it does when you run `python backend/shell.py`:
  1) Loads .env automatically (project root or current directory).
  2) Pings MongoDB and prints the active indexes.
  3) If JWT_SECRET_KEY is set, generates a dev token for sub="smoke-user",
     prints it, and decodes it via backend.jwt_utils.decode_jwt.
  4) If your app exposes GET /api/me with @require_jwt, it will call it
     using Flask's test client and print the result.
  5) (Optional) Chats API end-to-end smoke test.

CLI examples:
  python backend/shell.py --show-env
  python backend/shell.py --ping-db
  python backend/shell.py --gen-token --sub alice --minutes 120
  python backend/shell.py --decode --token <JWT>
  python backend/shell.py --test-me --token <JWT>
  python backend/shell.py --test-chats --gen-token

Environment:
  .env file (auto-loaded) OR exported env vars.
  Needs: JWT_SECRET_KEY for HS256 JWTs, MONGO_URL for DB (if not default).

Dependencies:
  PyJWT, pymongo, Flask, python-dotenv
"""

from __future__ import annotations

import os
import argparse
from datetime import datetime, timedelta, timezone

# --- Load .env early (project root or current) ---
try:
    from dotenv import load_dotenv, find_dotenv
    # find_dotenv() searches upward from CWD for a .env; returns '' if not found.
    # We call twice: once standard, once with override_path if running from backend/
    env_path = find_dotenv()
    if env_path:
        load_dotenv(env_path, override=False)
    else:
        # fallback: try repo root assuming this file is backend/shell.py
        from pathlib import Path
        root_env = (Path(__file__).resolve().parents[1] / ".env")
        if root_env.exists():
            load_dotenv(str(root_env), override=False)
except Exception:
    # If python-dotenv isn't installed, we just proceed (user can export vars manually)
    pass

# ---- flexible imports so you can run from repo root or from /backend ----
try:
    from db import db, chats, messages, ping as mongo_ping
except Exception:
    from db import db, chats, messages, ping as mongo_ping  # type: ignore

try:
    from jwt_utils import decode_jwt
except Exception:
    from jwt_utils import decode_jwt  # type: ignore

try:
    # Try to import the Flask app for the /api/me and chats tests
    from app import app as flask_app
except Exception:
    try:
        from app import app as flask_app  # type: ignore
    except Exception:
        flask_app = None  # Not fatal; tests will be skipped if missing

try:
    import jwt  # PyJWT
except Exception as e:
    print("ERROR: PyJWT not installed. Add 'PyJWT>=2.8,<3' to requirements.txt.")
    raise


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")


# ---- Utilities ----

def show_env() -> None:
    print("== Env check ==")
    print("JWT_SECRET_KEY set:", bool(JWT_SECRET_KEY))
    print("MONGO_URL:", os.getenv("MONGO_URL", "(default)"))
    print()


def print_mongo_status() -> None:
    print("== Mongo status ==")
    print(f"db: {db.name} ping: {mongo_ping()}")
    print("chats idx:", [i for i in chats.list_indexes()])
    print("messages idx:", [i for i in messages.list_indexes()])
    print()


def generate_dev_token(sub: str, minutes: int = 60) -> str:
    """
    Create an HS256 JWT for quick local testing.
    - Uses JWT_SECRET_KEY from env (loaded from .env or exported).
    - Adds 'sub' and 'exp' claims.
    """
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Define it in your .env or export it, e.g.\n"
            "  export JWT_SECRET_KEY='devsecret'"
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
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


def test_chats_flow(token: str) -> None:
    """
    End-to-end smoke test for the Chats API using Flask's test client:
      - POST /api/chats
      - GET  /api/chats
      - POST /api/chats/:id/messages
      - GET  /api/chats/:id/messages
    """
    if flask_app is None:
        print("== Chats API test skipped (Flask app not importable) ==")
        return

    print("== Chats API (Flask test client) ==")
    with flask_app.test_client() as client:
        # 1) Create chat
        resp = client.post("/api/chats",
                           headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json"},
                           json={})
        print("POST /api/chats ->", resp.status_code, resp.get_json())
        if resp.status_code >= 300:
            return
        chat_id = resp.get_json().get("id")

        # 2) List chats
        resp = client.get("/api/chats", headers={"Authorization": f"Bearer {token}"})
        print("GET  /api/chats  ->", resp.status_code, resp.get_json())

        # 3) Send a message
        resp = client.post(f"/api/chats/{chat_id}/messages",
                           headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json"},
                           json={"content": "Hello from shell smoke test"})
        print(f"POST /api/chats/{chat_id}/messages ->", resp.status_code, resp.get_json())

        # 4) Get messages
        resp = client.get(f"/api/chats/{chat_id}/messages?limit=50",
                          headers={"Authorization": f"Bearer {token}"})
        print(f"GET  /api/chats/{chat_id}/messages ->", resp.status_code, resp.get_json())

    print()


# ---- CLI ----

def build_parser():
    p = argparse.ArgumentParser(description="Praxis Assistant backend smoke tests")
    p.add_argument("--show-env", action="store_true", help="Print whether critical env vars are loaded")
    p.add_argument("--ping-db", action="store_true", help="Ping Mongo and list indexes")
    p.add_argument("--gen-token", action="store_true", help="Generate a dev JWT")
    p.add_argument("--sub", type=str, default="smoke-user", help="sub claim for dev token")
    p.add_argument("--minutes", type=int, default=60, help="Token lifetime in minutes")
    p.add_argument("--decode", action="store_true", help="Decode a JWT using jwt_utils")
    p.add_argument("--token", type=str, help="JWT to decode or to use with tests")
    p.add_argument("--test-me", action="store_true", help="Call /api/me with a token")
    p.add_argument("--test-chats", action="store_true", help="Run Chats API end-to-end test")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Default behavior: run everything helpful if no flags are passed
    run_all = not any([
        args.show_env, args.ping_db, args.gen_token, args.decode,
        args.test_me, args.test_chats
    ])

    if args.show_env or run_all:
        show_env()

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

    token = args.token or generated
    if args.test_me or (run_all and token):
        if token:
            test_api_me(token)
        else:
            print("== /api/me test skipped (no token). Use --token or --gen-token. ==\n")
    if args.test_chats or (run_all and token):
        if token:
            test_chats_flow(token)
        else:
            print("== Chats API test skipped (no token). Use --token or --gen-token. ==\n")


if __name__ == "__main__":
    main()
