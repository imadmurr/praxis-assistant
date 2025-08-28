# backend/chat_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request, abort, g
from bson import ObjectId

# Imports
try:
    from jwt_utils import require_jwt
    from db import chats, messages
    from ai_service import generate_reply
except Exception:
    from jwt_utils import require_jwt  # type: ignore
    from db import chats, messages     # type: ignore
    from ai_service import generate_reply  # type: ignore

chat_bp = Blueprint("chats", __name__)

# ---- helpers ----

def _oid(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except Exception:
        abort(404, description="Chat not found.")

def _now_utc_naive() -> datetime:
    return datetime.utcnow()

def _to_iso_z(dt: datetime) -> str:
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
    cid = _oid(chat_id)
    doc = chats.find_one({"_id": cid, "user_id": g.user_id, "archived": {"$ne": True}})
    if not doc:
        abort(404, description="Chat not found.")
    return doc

def _fetch_messages(user_id: str, chat_id: ObjectId, limit: int, before: Optional[datetime]) -> Tuple[List[Dict[str, Any]], bool]:
    q: Dict[str, Any] = {"user_id": user_id, "chat_id": chat_id}
    if before is not None:
        q["created_at"] = {"$lt": before}
    cur = messages.find(q).sort("created_at", -1).limit(limit + 1)
    docs = list(cur)
    has_more = len(docs) > limit
    docs = docs[:limit]
    docs.reverse()
    result: List[Dict[str, Any]] = []
    for m in docs:
        result.append({
            "id": str(m["_id"]),
            "role": m.get("role", "assistant"),
            "content": m.get("content", ""),
            "createdAt": _to_iso_z(m.get("created_at", _now_utc_naive())),
        })
    return result, has_more

# ---- routes ----

@chat_bp.get("/chats")
@require_jwt
def list_chats():
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

    # Generate reply via centralized service
    assistant_text = generate_reply(g.user_id, chat_doc["_id"], content, history_limit=20)

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
    chat_doc = _get_owned_chat_or_404(chat_id)
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"archived": True, "updated_at": _now_utc_naive()}})
    return jsonify({"ok": True}), 200