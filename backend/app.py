# backend/app.py (only the parts that change are shown here; paste full file if you prefer)
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, request, jsonify, g

try:
    from jwt_utils import require_jwt
    from db import chats, messages
    from chat_routes import chat_bp
    from ai_service import generate_reply
except Exception:
    from jwt_utils import require_jwt  # type: ignore
    from db import chats, messages     # type: ignore
    from chat_routes import chat_bp    # type: ignore
    from ai_service import generate_reply  # type: ignore

app = Flask(__name__)
app.register_blueprint(chat_bp, url_prefix="/api")

def _now_utc_naive():
    return datetime.utcnow()

def _to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="milliseconds") + "Z"

def _get_or_create_default_chat(user_id: str) -> Dict[str, Any]:
    doc = chats.find_one({"user_id": user_id, "archived": {"$ne": True}, "is_default": True})
    if doc:
        return doc
    existing = chats.find({"user_id": user_id, "archived": {"$ne": True}}).sort("updated_at", -1).limit(1)
    if existing:
        doc = list(existing)
        if doc:
            chat = doc[0]
            chats.update_one({"_id": chat["_id"]}, {"$set": {"is_default": True}})
            chat["is_default"] = True
            return chat
    now = _now_utc_naive()
    new_doc = {
        "user_id": user_id,
        "title": "Default",
        "created_at": now,
        "updated_at": now,
        "archived": False,
        "is_default": True,
    }
    ins = chats.insert_one(new_doc)
    new_doc["_id"] = ins.inserted_id
    return new_doc

@app.get("/history")
@require_jwt
def history():
    chat = _get_or_create_default_chat(g.user_id)
    cur = messages.find(
        {"user_id": g.user_id, "chat_id": chat["_id"]},
        projection={"role": 1, "content": 1, "created_at": 1},
    ).sort("created_at", 1).limit(1000)

    out = []
    for m in cur:
        sender = "user" if m.get("role") == "user" else "bot"
        out.append({
            "sender": sender,
            "text":   m.get("content", ""),
            "time":   _to_iso_z(m.get("created_at", _now_utc_naive())),
        })
    return jsonify({"messages": out}), 200

@app.post("/chat")
@require_jwt
def chat():
    body = request.get_json(silent=True) or {}
    hist = body.get("history") or []
    latest_user_text = ""
    if isinstance(hist, list) and hist:
        last = hist[-1]
        if isinstance(last, dict) and last.get("role") == "user":
            latest_user_text = (last.get("content") or "").strip()
    if not latest_user_text:
        return jsonify({"error": "Missing latest user message."}), 400

    chat_doc = _get_or_create_default_chat(g.user_id)
    now = _now_utc_naive()

    # Persist user message
    messages.insert_one({
        "user_id": g.user_id,
        "chat_id": chat_doc["_id"],
        "role": "user",
        "content": latest_user_text,
        "created_at": now,
    })
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"updated_at": now}})

    # Centralized AI call
    assistant_text = generate_reply(g.user_id, chat_doc["_id"], latest_user_text, history_limit=20)

    # Persist assistant message
    asst_doc = {
        "user_id": g.user_id,
        "chat_id": chat_doc["_id"],
        "role": "assistant",
        "content": assistant_text,
        "created_at": _now_utc_naive(),
    }
    messages.insert_one(asst_doc)
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"updated_at": _now_utc_naive()}})

    return jsonify({"reply": assistant_text}), 200

@app.get("/api/me")
@require_jwt
def whoami():
    return jsonify({"user_id": g.user_id, "claims": getattr(g, "jwt_payload", {})}), 200

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
