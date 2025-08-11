# backend/app.py

import logging
import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pymongo import MongoClient
from datetime import datetime
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from functools import wraps

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
app.logger.setLevel(logging.DEBUG)

ALLOWED_ORIGIN = os.getenv('ALLOWED_ORIGIN', '*')

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin']  = ALLOWED_ORIGIN
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response


# ── JWT Decorator ────────────────────────────────────────────────────────────

def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            app.logger.error("[jwt] Missing/invalid Authorization header")
            return jsonify({"error": "Missing/invalid token"}), 401

        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            app.logger.debug(f"[jwt] ✅ payload: {payload}")
        except ExpiredSignatureError as e:
            app.logger.error(f"[jwt] ❌ expired token: {e}")
            return jsonify({"error": "Invalid or expired token"}), 401
        except InvalidTokenError as e:
            app.logger.error(f"[jwt] ❌ invalid token: {e}")
            return jsonify({"error": "Invalid or expired token"}), 401

        # Attach user info to the request context
        request.user_id  = int(payload["sub"])
        request.username = payload.get("username")
        return fn(*args, **kwargs)
    return wrapper

# ── Error Handler ────────────────────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # catch any unhandled exception anywhere in the app
    app.logger.exception(f"[error] Unhandled error during {request.method} {request.path}")
    return jsonify({"error": "Internal server error"}), 500

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.route("/history", methods=["GET"])
@jwt_required
def history():
    uid = str(request.user_id)
    cursor = messages_collection.find({"user_id": uid}).sort("time", 1)

    history = []
    for doc in cursor:
        history.append({
            "sender": "user" if doc["role"] == "user" else "bot",
            "text":   doc["content"],
            "time":   doc["time"].isoformat()
        })

    app.logger.debug(f"[history] returning {len(history)} messages")
    return jsonify({"messages": history})


@app.route("/chat", methods=["POST"])
@jwt_required
def chat():
    user_id = request.user_id
    app.logger.info(f"[chat] user_id={user_id} called /chat")
    try:
        data = request.get_json(force=True)
        app.logger.debug(f"[chat] payload: {data}")
        history = data.get("history", [])

        # 1) Extract the latest user message
        last_user = next(
            (turn["content"] for turn in reversed(history) if turn["role"] == "user"),
            ""
        )
        app.logger.debug(f"[chat] last_user=\"{last_user}\"")

        # 2) Retrieve top-k doc snippets
        docs = retrieve_relevant(last_user, k=3)
        app.logger.debug(f"[chat] retrieved {len(docs)} docs")
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
        app.logger.info(f"[chat] sending request to Gemini model={MODEL_NAME}")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=parts,
            config=types.GenerateContentConfig(
                thinking_config=THINK_CFG,
                response_mime_type="text/plain"
            )
        )
        reply_text = response.text.strip()
        app.logger.debug(f"[chat] Gemini replied: \"{reply_text}\"")

        # 5) Persist both messages
        if last_user:
            now = datetime.utcnow()
            insert_docs = [
                {"user_id": str(user_id), "role": "user",      "content": last_user,   "time": now},
                {"user_id": str(user_id), "role": "assistant", "content": reply_text, "time": datetime.utcnow()}
            ]
            messages_collection.insert_many(insert_docs)
            app.logger.debug(f"[chat] persisted {len(insert_docs)} messages")

        return jsonify({"reply": reply_text})

    except Exception:
        app.logger.exception(f"[chat] Error handling /chat for user_id={user_id}")
        return jsonify({"error": "Failed to process chat"}), 500


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
