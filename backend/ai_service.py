# backend/ai_service.py
"""
Single source of truth for generating assistant replies.

Usage:
    from backend.ai_service import generate_reply
    text = generate_reply(user_id=g.user_id, chat_id=chat_doc["_id"], latest_user_text="Hi")

This module:
- Fetches recent history from Mongo (messages collection).
- Uses retrieval.retrieve_relevant to get context.
- Calls Gemini to produce a reply.
- Returns the reply text (string). If anything fails, returns a safe fallback.
"""

from __future__ import annotations

import os
from datetime import timezone, datetime
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

# Flexible imports – works when run from repo root or as a package
try:
    from db import messages
    import retrieval
except Exception:
    from backend.db import messages  # type: ignore
    from backend import retrieval    # type: ignore

from bson import ObjectId
from google import genai
from google.genai import types

load_dotenv()

# ---- Model / prompting config (same everywhere) ----
SYSTEM_INSTRUCTION = """You are the Praxis ERP AI Assistant.
- Always answer clearly, concisely, and in complete sentences.
- Focus on guiding users through ERP features, generating or explaining reports, and suggesting next actions.
- If you don’t know an answer, admit it and offer to escalate to human support.
- When giving step-by-step instructions, number each step.
- Refer to ERP modules by their exact names.

If you cannot confidently answer, reply:
“I’m not certain about that. Would you like me to connect you with a support agent or documentation link?”
"""

THINK_CFG  = types.ThinkingConfig(thinking_budget=-1)
MODEL_NAME = "gemini-2.5-flash"
API_KEY    = os.getenv("GEMINI_API_KEY")
_client    = genai.Client()


def _now_utc_naive() -> datetime:
    return datetime.utcnow()


def _to_oid(cid: Any) -> ObjectId:
    return cid if isinstance(cid, ObjectId) else ObjectId(str(cid))


def _load_history(user_id: str, chat_id: Any, limit: int = 20) -> List[Dict[str, str]]:
    """
    Get the last `limit` turns for the given chat, oldest->newest, as [{role, content}, ...].
    """
    cur = messages.find(
        {"user_id": user_id, "chat_id": _to_oid(chat_id)},
        projection={"role": 1, "content": 1, "created_at": 1},
    ).sort("created_at", -1).limit(limit)
    docs = list(cur)
    docs.reverse()
    return [{"role": d.get("role", "user"), "content": d.get("content", "")} for d in docs]


def generate_reply(user_id: str, chat_id: Any, latest_user_text: str, history_limit: int = 20) -> str:
    """
    Generate a reply string using:
      - recent chat history (from Mongo),
      - retrieval context (your RAG),
      - Gemini.
    Returns a plain string. Never raises; falls back to a safe message on error.
    """
    try:
        history = _load_history(user_id, chat_id, history_limit)
    except Exception:
        history = []

    # Retrieval context (best-effort)
    try:
        docs = retrieval.retrieve_relevant(latest_user_text, k=3)
        context = "\n\n".join(docs)
    except Exception:
        context = ""

    # Build contents
    parts: List[types.Part] = [
        types.Part.from_text(text=SYSTEM_INSTRUCTION),
        types.Part.from_text(text="----\nRelevant Documentation:\n" + context),
    ]
    for turn in history:
        prefix = "User:" if turn.get("role") == "user" else "Assistant:"
        parts.append(types.Part.from_text(text=f"{prefix} {turn.get('content','')}"))
    # The new user message
    parts.append(types.Part.from_text(text=f"User: {latest_user_text}"))
    parts.append(types.Part.from_text(text="Assistant:"))

    # Call Gemini
    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=parts,
            config=types.GenerateContentConfig(
                thinking_config=THINK_CFG,
                response_mime_type="text/plain",
            ),
        )
        return (response.text or "").strip() or "I couldn't generate a response just now. Please try again."
    except Exception:
        return "I couldn't generate a response just now. Please try again."
