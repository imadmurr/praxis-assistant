# backend/db.py
"""
MongoDB helper for Praxis Assistant.
- Creates a single global MongoClient (thread-safe).
- Picks a database name from the URL or MONGO_DB.
- Exposes `db`, `chats`, and `messages` handles.
- Ensures the indexes we need for fast, user-scoped queries.

Env vars it understands:
  MONGO_URL   -> e.g. mongodb://localhost:27017/praxis_assistant
  (optional) MONGODB_URI (alias)
  (optional) MONGO_DB    -> overrides the DB name if URL has no path

You can import this anywhere:
    from backend.db import db, chats, messages
"""

from __future__ import annotations

import os
from urllib.parse import urlparse
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database

# ---- Configuration ----

_DEFAULT_URL = "mongodb://localhost:27017/praxis_assistant"

MONGO_URL: str = (
    os.getenv("MONGO_URL")
    or os.getenv("MONGODB_URI")
    or _DEFAULT_URL
).strip()

# Optional explicit DB name
MONGO_DB_ENV: Optional[str] = (os.getenv("MONGO_DB") or "").strip() or None


# ---- Client / DB selection ----

def _db_name_from_url(url: str) -> str:
    """
    If the URL has a path (/mydb), use that. Otherwise fall back to MONGO_DB
    or the default 'praxis_assistant'.
    """
    parsed = urlparse(url)
    path = (parsed.path or "").lstrip("/")
    if path:
        return path
    if MONGO_DB_ENV:
        return MONGO_DB_ENV
    return "praxis_assistant"


def _make_client() -> MongoClient:
    """
    Create a single, process-wide MongoClient.
    MongoClient is thread-safe and designed to be reused.
    """
    return MongoClient(
        MONGO_URL,
        tz_aware=True,
        uuidRepresentation="standard",
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
    )


_client: MongoClient = _make_client()
_DB_NAME: str = _db_name_from_url(MONGO_URL)
db: Database = _client[_DB_NAME]

# Collections we use
chats: Collection = db["chats"]
messages: Collection = db["messages"]


# ---- Indexes ----

def ensure_indexes() -> None:
    """
    Create the indexes we rely on. Safe to call multiple times.
    """
    # For listing chats quickly per user, newest first
    chats.create_index(
        [("user_id", ASCENDING), ("updated_at", DESCENDING)],
        name="chats_user_updated_idx",
        background=True,
    )

    # For fetching messages by user + chat, in chronological order
    messages.create_index(
        [("user_id", ASCENDING), ("chat_id", ASCENDING), ("created_at", ASCENDING)],
        name="msgs_user_chat_created_idx",
        background=True,
    )

    # Optional: helpful for quick per-chat scrolls (kept secondary)
    messages.create_index(
        [("chat_id", ASCENDING), ("created_at", ASCENDING)],
        name="msgs_chat_created_idx",
        background=True,
    )


# Run at import so first request has indexes
try:
    # Light connectivity check; won't crash app if Mongo isn't up yet
    _client.admin.command("ping")
except Exception:
    # In dev, Mongo might start after the app; indexes will still be created
    # on first real use.
    pass
finally:
    try:
        ensure_indexes()
    except Exception:
        # Avoid crashing on index creation race conditions across workers.
        # (Mongo will finalize in the background.)
        pass


# ---- Utilities (optional) ----

def ping() -> bool:
    """Simple health check you can reuse in /healthz."""
    try:
        _client.admin.command("ping")
        return True
    except Exception:
        return False
