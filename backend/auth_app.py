# auth_app.py

"""
Auth application for generating JWTs.

This Flask app exposes only a single `/login` endpoint that accepts a
username in JSON and returns a signed JSON Web Token (JWT).  The
purpose of separating this login logic from the main chat backend is to
reflect a production architecture where authentication is handled by a
dedicated service or identity provider.
"""
import os
import random
from flask import Flask, request, jsonify
from pymongo import MongoClient

from jwt_utils import create_jwt

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo = MongoClient(MONGO_URI)["chat_db"]
users = mongo["users"]          # ↔ username ⇄ user_id map

auth_app = Flask(__name__)



@auth_app.route('/login', methods=['POST'])
def login():
    """
    Issue a JWT for a given username.

    The client should POST a JSON body with a `username` field.  A
    randomly generated 64‑bit integer will be used as the subject (`sub`)
    claim in the JWT.  The provided username is included in the
    `username` claim for convenience when displaying greetings in the
    frontend.  The token is valid for 60 minutes by default (as
    configured in ``create_jwt``).
    """
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    if not username:
        return jsonify({"error": "Missing username"}), 400

    doc = users.find_one({"username": username})
    if doc:
        user_id = doc["user_id"]  # reuse existing
    else:
        user_id = random.getrandbits(63)  # 64‑bit signed positive
        users.insert_one({"user_id": user_id, "username": username})

    token = create_jwt(user_id=user_id, username=username)
    return jsonify({"token": token})

if __name__ == '__main__':
    # Bind to port 5001 to avoid collision with the chat backend.
    auth_app.run(port=5001, debug=True)
