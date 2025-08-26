# backend/chat_routes.py
"""
Chats API (WhatsApp-style) for Praxis Assistant.

Endpoints (all require JWT via @require_jwt):
  GET    /api/chats
  POST   /api/chats
  GET    /api/chats/<chat_id>/messages?limit=50&before=<ISO8601>
  POST   /api/chats/<chat_id>/messages
  DELETE /api/chats/<chat_id>   (soft-archive; optional)

Security:
- We never trust user_id from the client. It always comes from the verified JWT (g.user_id).
- Every DB query scopes by BOTH user_id and the chat_id.
- If a chat does not belong to the caller, we return 404 (do not leak existence).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request, abort, g
from bson import ObjectId

# Local imports (works when run from backend/)
try:
    from jwt_utils import require_jwt
    from db import chats, messages
except Exception:
    # Package-style fallback
    from backend.jwt_utils import require_jwt  # type: ignore
    from backend.db import chats, messages     # type: ignore

# RAG pieces (reuse your retrieval + Gemini client, mirroring app.py logic)
try:
    from retrieval import retrieve_relevant
except Exception:
    from backend.retrieval import retrieve_relevant  # type: ignore

from google import genai
from google.genai import types

chat_bp = Blueprint("chats", __name__)

# ---- Model / prompting config (copied from app.py to avoid circular imports) ----

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
_gen_client = genai.Client()


# -------------------- helpers --------------------

def _oid(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except Exception:
        abort(404, description="Chat not found.")


def _now_utc_naive() -> datetime:
    # Store naive UTC in Mongo for simplicity (consistent sort)
    return datetime.utcnow()


def _to_iso_z(dt: datetime) -> str:
    # Represent as RFC3339-ish "YYYY-mm-ddTHH:MM:SS.sssZ"
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="milliseconds") + "Z"


def _parse_before_param(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        abort(400, description="Invalid 'before' timestamp.")


def _require_nonempty_text(text: Optional[str], field_name: str = "content", max_len: int = 8000) -> str:
    if not isinstance(text, str):
        abort(400, description=f"Missing or invalid '{field_name}'.")
    clean = text.strip()
    if not clean:
        abort(422, description=f"'{field_name}' cannot be empty.")
    if len(clean) > max_len:
        abort(413, description=f"'{field_name}' exceeds {max_len} characters.")
    return clean


def _get_owned_chat_or_404(chat_id: str) -> Dict[str, Any]:
    """Ensure the chat exists AND belongs to g.user_id."""
    cid = _oid(chat_id)
    doc = chats.find_one({"_id": cid, "user_id": g.user_id, "archived": {"$ne": True}})
    if not doc:
        abort(404, description="Chat not found.")
    return doc


def _fetch_messages(user_id: str, chat_id: ObjectId, limit: int, before: Optional[datetime]) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Time-based pagination optimized for infinite scroll UP:
      - If 'before' is provided, fetch older messages (< before).
      - Otherwise, fetch latest 'limit' messages.
    Always sort DESC in DB, then reverse before returning so UI renders ASC.
    """
    q: Dict[str, Any] = {"user_id": user_id, "chat_id": chat_id}
    if before is not None:
        q["created_at"] = {"$lt": before}

    # Fetch one extra to see if more exist
    cur = messages.find(q).sort("created_at", -1).limit(limit + 1)
    docs = list(cur)
    has_more = len(docs) > limit
    docs = docs[:limit]
    docs.reverse()  # oldest -> newest for UI

    result: List[Dict[str, Any]] = []
    for m in docs:
        result.append({
            "id": str(m["_id"]),
            "role": m.get("role", "assistant"),
            "content": m.get("content", ""),
            "createdAt": _to_iso_z(m.get("created_at", _now_utc_naive())),
        })
    return result, has_more


# -------------------- RAG adapter (mirrors app.py generation) --------------------

def _generate_assistant_reply(latest_user_text: str, history: List[Dict[str, str]]) -> str:
    """
    Use your current stack: retrieve top-k docs, build parts, call Gemini, return text.
    """
    # Retrieve docs for context
    try:
        docs = retrieve_relevant(latest_user_text, k=3)
        context = "\n\n".join(docs)
    except Exception:
        context = ""

    parts: List[types.Part] = [
        types.Part.from_text(text=SYSTEM_INSTRUCTION),
        types.Part.from_text(text="----\nRelevant Documentation:\n" + context),
    ]
    # Rebuild the same "User:" / "Assistant:" pattern
    for turn in history:
        prefix = "User:" if turn.get("role") == "user" else "Assistant:"
        parts.append(types.Part.from_text(text=f"{prefix} {turn.get('content','')}"))
    parts.append(types.Part.from_text(text="Assistant:"))

    response = _gen_client.models.generate_content(
        model=MODEL_NAME,
        contents=parts,
        config=types.GenerateContentConfig(
            thinking_config=THINK_CFG,
            response_mime_type="text/plain",
        ),
    )
    return (response.text or "").strip()


# -------------------- routes --------------------

@chat_bp.get("/chats")
@require_jwt
def list_chats():
    """
    List the caller's chats, newest first.
    Response: [{ id, title, lastMessageAt }]
    """
    cur = chats.find(
        {"user_id": g.user_id, "archived": {"$ne": True}},
        projection={"title": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(200)

    items = []
    for c in cur:
        items.append({
            "id": str(c["_id"]),
            "title": c.get("title") or "New chat",
            "lastMessageAt": _to_iso_z(c.get("updated_at", _now_utc_naive())),
        })
    return jsonify(items), 200


@chat_bp.post("/chats")
@require_jwt
def create_chat():
    """
    Create a new chat for the caller.
    Body: { "title": "optional name" }
    Response: { "id": "<chat_id>" }
    """
    body = request.get_json(silent=True) or {}
    title = body.get("title")
    now = _now_utc_naive()
    doc = {
        "user_id": g.user_id,
        "title": title.strip() if isinstance(title, str) and title.strip() else None,
        "created_at": now,
        "updated_at": now,
        "archived": False,
    }
    res = chats.insert_one(doc)
    return jsonify({"id": str(res.inserted_id)}), 201


@chat_bp.get("/chats/<chat_id>/messages")
@require_jwt
def get_messages(chat_id: str):
    """
    Get messages for the caller's chat.
    Query:
      - limit (default 50, max 200)
      - before (ISO8601; fetch older messages strictly before this timestamp)
    Response:
      {
        "chatId": "<id>",
        "messages": [{ id, role, content, createdAt }],
        "hasMore": true|false
      }
    """
    chat_doc = _get_owned_chat_or_404(chat_id)

    try:
        limit = int(request.args.get("limit", "50"))
    except Exception:
        limit = 50
    limit = max(1, min(limit, 200))

    before = _parse_before_param(request.args.get("before"))
    msgs, has_more = _fetch_messages(g.user_id, chat_doc["_id"], limit, before)

    return jsonify({"chatId": str(chat_doc["_id"]), "messages": msgs, "hasMore": has_more}), 200


@chat_bp.post("/chats/<chat_id>/messages")
@require_jwt
def post_message(chat_id: str):
    """
    Append a user message, call AI, and persist the assistant reply.
    Body: { "content": "text" }
    Response:
      {
        "ok": true,
        "assistant": { "id": "...", "role": "assistant", "content": "...", "createdAt": "..." }
      }
    """
    chat_doc = _get_owned_chat_or_404(chat_id)
    body = request.get_json(silent=True) or {}
    content = _require_nonempty_text(body.get("content"), "content")

    now = _now_utc_naive()
    # Insert user message
    user_msg = {
        "user_id": g.user_id,
        "chat_id": chat_doc["_id"],
        "role": "user",
        "content": content,
        "created_at": now,
    }
    messages.insert_one(user_msg)
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"updated_at": now}})

    # Build a small history window for the generator
    hist_cur = messages.find(
        {"user_id": g.user_id, "chat_id": chat_doc["_id"]},
        projection={"role": 1, "content": 1, "created_at": 1},
    ).sort("created_at", -1).limit(20)
    hist_docs = list(hist_cur)
    hist_docs.reverse()
    history = [{"role": d.get("role","user"), "content": d.get("content","")} for d in hist_docs]

    # Generate reply (same stack as app.py)
    try:
        assistant_text = _generate_assistant_reply(content, history)
    except Exception:
        assistant_text = "I couldn't generate a response just now. Please try again."

    # Insert assistant message
    asst_doc = {
        "user_id": g.user_id,
        "chat_id": chat_doc["_id"],
        "role": "assistant",
        "content": assistant_text,
        "created_at": _now_utc_naive(),
    }
    ins = messages.insert_one(asst_doc)
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"updated_at": _now_utc_naive()}})

    assistant_out = {
        "id": str(ins.inserted_id),
        "role": "assistant",
        "content": assistant_text,
        "createdAt": _to_iso_z(asst_doc["created_at"]),
    }
    return jsonify({"ok": True, "assistant": assistant_out}), 200


@chat_bp.delete("/chats/<chat_id>")
@require_jwt
def archive_chat(chat_id: str):
    """
    Soft-archive a chat (do not delete messages).
    Response: { "ok": true }
    """
    chat_doc = _get_owned_chat_or_404(chat_id)
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"archived": True, "updated_at": _now_utc_naive()}})
    return jsonify({"ok": True}), 200
