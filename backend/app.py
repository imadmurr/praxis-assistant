# backend/app.py

import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types

from jwt_utils import create_jwt, verify_jwt
from retrieval import retrieve_relevant

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")
client = genai.Client(api_key=API_KEY)

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

@app.route("/")
def home():
    return app.send_static_file("index.html")

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    # For demo: accept any username, no password check!
    if not username:
        return jsonify({"error": "Missing username"}), 400
    # Example: user_id is the username for now
    token = create_jwt(user_id=username)
    return jsonify({"token": token})

# Decorator for JWT-protected routes
from functools import wraps
def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing/invalid token"}), 401
        token = auth.split(" ", 1)[1]
        user_id = verify_jwt(token)
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401
        request.user_id = user_id  # attach user_id to request
        return fn(*args, **kwargs)
    return wrapper

@app.route("/chat", methods=["POST"])
@jwt_required
def chat():
    user_id = getattr(request, "user_id", None)
    data    = request.get_json()
    history = data.get("history", [])

    # Optionally: print/log the user ID for auditing
    print("Chat request from user:", user_id)

    # 1) Grab the last user message for retrieval:
    last_user = next(
      (turn["content"] for turn in reversed(history) if turn["role"]=="user"),
      ""
    )

    # 2) Retrieve top‐k doc snippets
    docs = retrieve_relevant(last_user, k=3)
    context = "\n\n".join(docs)

    # 3) Build the prompt parts: system + context + conversation
    parts = [
      types.Part.from_text(text=SYSTEM_INSTRUCTION),
      types.Part.from_text(text="----\nRelevant Documentation:\n" + context),
    ]
    for turn in history:
      prefix = "User:" if turn["role"]=="user" else "Assistant:"
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

    return jsonify({"reply": response.text.strip()})

if __name__ == "__main__":
    app.run(debug=True)
