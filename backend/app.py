# backend/app.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, request, jsonify, g

# ---- Local imports (run-from-backend friendly) ----
try:
    from jwt_utils import require_jwt
    from db import chats, messages
    from chat_routes import chat_bp
    import retrieval  # your RAG module
except Exception:
    # package-style fallback (if you run app as a package)
    from backend.jwt_utils import require_jwt  # type: ignore
    from backend.db import chats, messages     # type: ignore
    from backend.chat_routes import chat_bp    # type: ignore
    from backend import retrieval              # type: ignore

# ---- Google GenAI client ----
from google import genai
from google.genai import types

app = Flask(__name__)

# Register Chats API blueprint
app.register_blueprint(chat_bp, url_prefix="/api")

# ---------- Small helpers ----------

def _now_utc_naive() -> datetime:
    return datetime.utcnow()

def _to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    # Keep milliseconds for consistency with /api
    return dt.isoformat(timespec="milliseconds") + "Z"

def _require_nonempty_text(text: Optional[str], field_name: str = "content", max_len: int = 8000) -> str:
    if not isinstance(text, str):
        return ""
    clean = text.strip()
    if not clean or len(clean) > max_len:
        return ""
    return clean

def _get_or_create_default_chat(user_id: str) -> Dict[str, Any]:
    """
    Bridge for legacy /chat and /history: use one 'default' chat per user.
    Strategy:
      1) If a chat with is_default=True exists -> use it.
      2) Else reuse the most recently updated chat (if any) and mark it default.
      3) Else create a fresh default chat.
    """
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

# ---------- AI generation ----------

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

def _generate_assistant_reply(latest_user_text: str, history: List[Dict[str, str]]) -> str:
    # Use retrieval pipeline for context (reuse your retrieval module)
    try:
        docs = retrieval.retrieve_relevant(latest_user_text, k=3)
        context = "\n\n".join(docs)
    except Exception:
        context = ""

    parts: List[types.Part] = [
        types.Part.from_text(text=SYSTEM_INSTRUCTION),
        types.Part.from_text(text="----\nRelevant Documentation:\n" + context),
    ]
    # Rebuild "User:" / "Assistant:" turn-taking for the LLM
    for turn in history:
        prefix = "User:" if turn.get("role") == "user" else "Assistant:"
        parts.append(types.Part.from_text(text=f"{prefix} {turn.get('content','')}"))
    parts.append(types.Part.from_text(text="Assistant:"))

    try:
        response = _gen_client.models.generate_content(
            model=MODEL_NAME,
            contents=parts,
            config=types.GenerateContentConfig(
                thinking_config=THINK_CFG,
                response_mime_type="text/plain",
            ),
        )
        return (response.text or "").strip()
    except Exception:
        return "I couldn't generate a response just now. Please try again."

# ---------- Legacy-compatible endpoints (now unified on Mongo schema) ----------

@app.get("/history")
@require_jwt
def history():
    """
    Returns chat history in the shape ChatWidget.jsx expects:
      { "messages": [ { "sender": "user"|"bot", "text": str, "time": ISO } ] }
    Data is read from the unified Mongo `messages` collection,
    scoped to the user's default chat.
    """
    chat = _get_or_create_default_chat(g.user_id)
    # oldest -> newest
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
    """
    Accepts: { "history": [ { "role": "user"|"assistant", "content": str }, ... ] }
    Returns: { "reply": "<assistant text>" }
    Behavior:
      - Writes latest user message and assistant reply into unified Mongo schema
        under the user's default chat.
    """
    body = request.get_json(silent=True) or {}
    hist = body.get("history") or []

    # Determine the latest user message (ChatWidget sends it as the last element)
    latest_user_text = ""
    if isinstance(hist, list) and hist:
        last = hist[-1]
        if isinstance(last, dict) and last.get("role") == "user":
            latest_user_text = _require_nonempty_text(last.get("content") or "")
    if not latest_user_text:
        return jsonify({"error": "Missing latest user message."}), 400

    chat_doc = _get_or_create_default_chat(g.user_id)
    now = _now_utc_naive()

    # Persist user message
    user_msg = {
        "user_id": g.user_id,
        "chat_id": chat_doc["_id"],
        "role": "user",
        "content": latest_user_text,
        "created_at": now,
    }
    messages.insert_one(user_msg)
    chats.update_one({"_id": chat_doc["_id"]}, {"$set": {"updated_at": now}})

    # Build small history window for the model (20 recent turns)
    hist_cur = messages.find(
        {"user_id": g.user_id, "chat_id": chat_doc["_id"]},
        projection={"role": 1, "content": 1, "created_at": 1},
    ).sort("created_at", -1).limit(20)
    hist_docs = list(hist_cur)
    hist_docs.reverse()
    model_history = [{"role": d.get("role","user"), "content": d.get("content","")} for d in hist_docs]

    # Generate reply
    assistant_text = _generate_assistant_reply(latest_user_text, model_history)

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

    # Respond in legacy shape for ChatWidget.jsx
    return jsonify({"reply": assistant_text}), 200


# ---------- Utility endpoints ----------

@app.get("/api/me")
@require_jwt
def whoami():
    return jsonify({"user_id": g.user_id, "claims": getattr(g, "jwt_payload", {})}), 200

@app.get("/healthz")
def healthz():
    # You can enhance this to also ping Mongo if desired
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    # Default dev port; in prod you'll run via gunicorn/uwsgi
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
