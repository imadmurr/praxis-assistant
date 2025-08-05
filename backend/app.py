# backend/app.py
import logging
import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pymongo import MongoClient
from datetime import datetime
import random
from datetime import datetime

from flask import Flask, jsonify, request
from dotenv import load_dotenv
from google import genai
from google.genai import types
from functools import wraps
from retrieval import retrieve_relevant

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["chat_db"]
messages_collection = db["messages"]

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")
client = genai.Client(api_key=API_KEY)
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM")
SYSTEM_INSTRUCTION = """You are the Praxis ERP AI Assistant.
- Always answer clearly, concisely, and in complete sentences.
- Focus on guiding users through ERP features, generating or explaining reports, and suggesting next actions.
- If you don’t know an answer, admit it and offer to escalate to human support.
- When giving step-by-step instructions, number each step.
- Refer to ERP modules by their exact names.

If you cannot confidently answer, reply:
“I’m not certain about that. Would you like me to connect you with a support agent or documentation link?
"""

THINK_CFG  = types.ThinkingConfig(thinking_budget=-1)
MODEL_NAME = "gemini-2.5-flash"

app = Flask(__name__, static_folder="../ui", static_url_path="")

# Decorator for JWT-protected routes
def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing/invalid token"}), 401

        token = auth.split(" ", 1)[1]

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            app.logger.debug(f"✅ JWT payload: {payload}")
        except ExpiredSignatureError as e:
            app.logger.error(f"❌ JWT expired: {e}")
            return jsonify({"error": "Invalid or expired token"}), 401
        except InvalidTokenError as e:
            app.logger.error(f"❌ JWT invalid: {e}")
            return jsonify({"error": "Invalid or expired token"}), 401

        # all good—attach to request
        request.user_id  = int(payload["sub"])
        request.username = payload.get("username")
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.route("/history", methods=["GET"])
@jwt_required
def history():
    uid = request.user_id
    # Query both forms
    cursor = messages_collection.find({
        "$or": [
            {"user_id": uid},
            {"user_id": str(uid)}
        ]
    }).sort("time", 1)

    history = []
    for doc in cursor:
        history.append({
            "sender": "user" if doc["role"]=="user" else "bot",
            "text":   doc["content"],
            "time":   doc["time"].isoformat()
        })
    return jsonify({"messages": history})


@app.route('/chat', methods=['POST'])
@jwt_required
def chat():
    user_id = request.user_id
    data = request.get_json()
    history = data.get("history", [])

    # 1) Extract the latest user message
    last_user = next((turn["content"] for turn in reversed(history)
                      if turn["role"] == "user"), "")

    # 2) Retrieve top‐k doc snippets
    docs = retrieve_relevant(last_user, k=3)
    context = "\n\n".join(docs)

    # 3) Build the prompt parts: system + context + conversation
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
    # persist both messages
    if last_user:
        now = datetime.utcnow()
        messages_collection.insert_many([
            {"user_id": str(user_id), "role": "user", "content": last_user, "time": now},
            {"user_id": str(user_id), "role": "assistant", "content": reply_text, "time": datetime.utcnow()}
        ])
    return jsonify({"reply": reply_text})


if __name__ == "__main__":
    app.run(debug=True)
