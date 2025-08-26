# backend/app.py

import logging
import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pymongo import MongoClient
from datetime import datetime, timezone
from flask import Flask, jsonify, request, g
from dotenv import load_dotenv
from functools import wraps

from chat_routes import chat_bp
from jwt_utils import verify_jwt, require_jwt
from retrieval import retrieve_relevant
from google import genai
from google.genai import types

# ── Environment & Clients ────────────────────────────────────────────────────

load_dotenv()

MONGO_URI            = os.getenv("MONGO_URI", "mongodb://mongo:27017")
mongo_client         = MongoClient(MONGO_URI)
db                   = mongo_client["chat_db"]
messages_collection  = db["messages"]

API_KEY    = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")

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

client = genai.Client()

# ── Flask App & Logging ───────────────────────────────────────────────────────

app = Flask(__name__, static_folder="../ui", static_url_path="")
# Register Chats API blueprint
app.register_blueprint(chat_bp, url_prefix="/api")
ALLOWED_ORIGIN = os.getenv('ALLOWED_ORIGIN', '*')

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin']  = ALLOWED_ORIGIN
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response


# ── JWT Decorator ────────────────────────────────────────────────────────────

def jwt_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # 1) Try Authorization: Bearer <token>
        auth = request.headers.get("Authorization", "")
        token = None
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()
        # 2) Fallback: Cookie named "jwt" (useful if upstream sets HttpOnly cookie)
        if not token:
            token = request.cookies.get("jwt")
        if not token:
            # If HTML is acceptable, return a simple page; otherwise JSON 401
            accept = request.headers.get("Accept", "")
            if "text/html" in accept and "application/json" not in accept:
                return (
                    "<!doctype html><title>401 Unauthorized</title>"
                    "<h1>401 – Not authorized</h1>"
                    "<p>This endpoint requires a valid JWT in the Authorization header.</p>",
                    401,
                    {"Content-Type": "text/html"},
                )
            return jsonify({"error": "Missing token"}), 401

        payload = verify_jwt(token)
        if not payload:
            accept = request.headers.get("Accept", "")
            if "text/html" in accept and "application/json" not in accept:
                return (
                    "<!doctype html><title>401 Unauthorized</title>"
                    "<h1>401 – Invalid or expired token</h1>",
                    401,
                    {"Content-Type": "text/html"},
                )
            return jsonify({"error": "Invalid or expired token"}), 401

        # Attach both a dict and convenience attributes for compatibility
        request.user = {"id": payload.get("sub"), "username": payload.get("username")}
        try:
            request.user_id = payload.get("sub")
            request.username = payload.get("username")
        except Exception:
            # In some Flask setups request is a LocalProxy; setting attributes is fine,
            # but if an environment disallows it we just rely on request.user
            pass

        return f(*args, **kwargs)
    return wrapper

# ── Error Handler ────────────────────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # catch any unhandled exception anywhere in the app
    return jsonify({"error": "Internal server error"}), 500

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.route("/history", methods=["GET",'OPTIONS'])
@jwt_required
def history():
    if request.method == 'OPTIONS':
        return ('', 204)
    uid = str(request.user_id)
    cursor = messages_collection.find({"user_id": uid}).sort("time", 1)

    history = []
    for doc in cursor:
        history.append({
            "sender": "user" if doc["role"] == "user" else "bot",
            "text":   doc["content"],
            "time":   doc["time"].isoformat()
        })
    return jsonify({"messages": history})


@app.route("/chat", methods=["POST",'OPTIONS'])
@jwt_required
def chat():
    if request.method == 'OPTIONS':
        return ('', 204)

    user_id = request.user_id
    try:
        data = request.get_json(force=True)
        history = data.get("history", [])

        # 1) Extract the latest user message
        last_user = next(
            (turn["content"] for turn in reversed(history) if turn["role"] == "user"),
            ""
        )

        # 2) Retrieve top-k doc snippets
        docs = retrieve_relevant(last_user, k=3)
        context = "\n\n".join(docs)

        # 3) Build the prompt parts
        parts = [
            types.Part.from_text(text=SYSTEM_INSTRUCTION),
            types.Part.from_text(text="----\nRelevant Documentation:\n" + context),
        ]
        for turn in history:
            prefix = "User:" if turn["role"] == "user" else "Assistant:"
            parts.append(types.Part.from_text(text=f"{prefix} {turn['content']}"))
        parts.append(types.Part.from_text(text="Assistant:"))

        # 4) Call Gemini
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=parts,
            config=types.GenerateContentConfig(
                thinking_config=THINK_CFG,
                response_mime_type="text/plain"
            )
        )
        reply_text = response.text.strip()

        # 5) Persist both messages
        if last_user:
            now = datetime.now(timezone.utc)
            insert_docs = [
                {"user_id": str(user_id), "role": "user",      "content": last_user,   "time": now},
                {"user_id": str(user_id), "role": "assistant", "content": reply_text, "time": datetime.now(timezone.utc)}
            ]
            messages_collection.insert_many(insert_docs)

        return jsonify({"reply": reply_text})

    except Exception:
        return jsonify({"error": "Failed to process chat"}), 500

@app.get("/api/me")
@require_jwt
def whoami():
    # Returns the authenticated user id and full JWT payload (helpful while testing)
    return jsonify({
        "user_id": g.user_id,
        "claims": getattr(g, "jwt_payload", {})
    }), 200

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
