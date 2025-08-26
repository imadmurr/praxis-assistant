# backend/shell.py
"""
Quick smoke tests for Praxis Assistant backend.

What it does:
  1) Loads .env automatically (project root or current directory).
  2) Pings MongoDB and prints the active indexes.
  3) If JWT_SECRET_KEY is set, generates one or two dev tokens and decodes them.
  4) Tests:
     - /api/me (identity)
     - Legacy flow: /history and /chat
     - Chats API: /api/chats and /messages
     - Isolation: user A cannot read user B's chat

CLI examples:
  python backend/shell.py --show-env
  python backend/shell.py --gen-token --sub alice --minutes 120
  python backend/shell.py --decode --token <JWT>
  python backend/shell.py --test-me --token <JWT>
  python backend/shell.py --test-legacy --gen-token
  python backend/shell.py --test-chats --gen-token
  python backend/shell.py --test-iso --gen-token-pair --sub alice --sub2 bob

Env:
  .env (auto-loaded) OR exported variables:
    JWT_SECRET_KEY  HS256 secret
    MONGO_URL       Mongo connection (optional; defaults to localhost)

Deps:
  PyJWT, pymongo, Flask, python-dotenv
"""

from __future__ import annotations

import os
import argparse
from datetime import datetime, timedelta, timezone

# --- Load .env early ---
try:
    from dotenv import load_dotenv, find_dotenv
    env_path = find_dotenv()
    if env_path:
        load_dotenv(env_path, override=False)
    else:
        from pathlib import Path
        root_env = (Path(__file__).resolve().parents[1] / ".env")
        if root_env.exists():
            load_dotenv(str(root_env), override=False)
except Exception:
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
    # Flask app for test client
    from app import app as flask_app
except Exception:
    try:
        from app import app as flask_app  # type: ignore
    except Exception:
        flask_app = None

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

def test_legacy_flow(token: str) -> None:
    """
    Legacy endpoints that the current UI uses:
      - GET /history
      - POST /chat   { history: [{role, content}, ...] } -> { reply }
    These now operate on the unified Mongo schema via the user's default chat.
    """
    if flask_app is None:
        print("== Legacy flow test skipped (Flask app not importable) ==")
        return
    print("== Legacy flow (/history, /chat) ==")
    with flask_app.test_client() as client:
        # 1) Get history (should succeed; may be empty on first run)
        resp = client.get("/history", headers={"Authorization": f"Bearer {token}"})
        print("GET  /history ->", resp.status_code)
        print("json:", resp.get_json())

        # 2) Send one user message
        payload = {"history": [{"role": "user", "content": "Hello from legacy test"}]}
        resp = client.post("/chat",
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                           json=payload)
        print("POST /chat    ->", resp.status_code, resp.get_json())

        # 3) History again (should include user + bot)
        resp = client.get("/history", headers={"Authorization": f"Bearer {token}"})
        print("GET  /history ->", resp.status_code)
        res_json = resp.get_json()
        print("last 2 msgs:", (res_json or {}).get("messages", [])[-2:])
    print()

def test_chats_flow(token: str) -> None:
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
                           json={"content": "Hello from chats test"})
        print(f"POST /api/chats/{chat_id}/messages ->", resp.status_code, resp.get_json())

        # 4) Get messages
        resp = client.get(f"/api/chats/{chat_id}/messages?limit=50",
                          headers={"Authorization": f"Bearer {token}"})
        print(f"GET  /api/chats/{chat_id}/messages ->", resp.status_code, resp.get_json())
    print()

def test_isolation(token_a: str, token_b: str) -> None:
    """
    Creates a chat as user A, then tries to read it as user B -> expect 404.
    """
    if flask_app is None:
        print("== Isolation test skipped (Flask app not importable) ==")
        return
    print("== Isolation (user A vs user B) ==")
    with flask_app.test_client() as client:
        # Create chat as A
        resp = client.post("/api/chats",
                           headers={"Authorization": f"Bearer {token_a}",
                                    "Content-Type": "application/json"},
                           json={"title": "A's private chat"})
        print("A: POST /api/chats ->", resp.status_code, resp.get_json())
        if resp.status_code >= 300:
            return
        chat_id = resp.get_json().get("id")

        # Try to read A's chat messages as B
        resp = client.get(f"/api/chats/{chat_id}/messages",
                          headers={"Authorization": f"Bearer {token_b}"})
        print("B: GET  /api/chats/{chat_id}/messages ->", resp.status_code)
        if resp.status_code == 404:
            print("OK: user B cannot access user A's chat (404).")
        else:
            print("WARNING: expected 404, got", resp.status_code)
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
    p.add_argument("--test-legacy", action="store_true", help="Run legacy flow (/history, /chat)")
    p.add_argument("--test-chats", action="store_true", help="Run Chats API flow")

    # Isolation options
    p.add_argument("--test-iso", action="store_true", help="Run isolation test (user A vs user B)")
    p.add_argument("--gen-token-pair", action="store_true", help="Auto-generate two tokens for isolation test")
    p.add_argument("--sub2", type=str, default="smoke-user-2", help="sub claim for second token (isolation)")
    p.add_argument("--token2", type=str, help="Second JWT (if not generating)")

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()

    run_all = not any([
        args.show_env, args.ping_db, args.gen_token, args.decode,
        args.test_me, args.test_legacy, args.test_chats, args.test_iso
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
            print("== /api/me test skipped (no token).\n")

    if args.test_legacy or (run_all and token):
        if token:
            test_legacy_flow(token)
        else:
            print("== Legacy test skipped (no token).\n")

    if args.test_chats or (run_all and token):
        if token:
            test_chats_flow(token)
        else:
            print("== Chats test skipped (no token).\n")

    if args.test_iso:
        token_a = token
        if args.gen_token_pair:
            token_a = generate_dev_token(args.sub, args.minutes)
            token_b = generate_dev_token(args.sub2, args.minutes)
        else:
            token_b = args.token2
            if not (token_a and token_b):
                print("== Isolation test needs two tokens. Use --gen-token-pair OR provide --token and --token2. ==")
                return
        test_isolation(token_a, token_b)

if __name__ == "__main__":
    main()
