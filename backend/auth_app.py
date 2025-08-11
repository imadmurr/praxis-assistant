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
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from pymongo import MongoClient

from jwt_utils import create_jwt

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
mongo = MongoClient(MONGO_URI)["chat_db"]
users = mongo["users"]          # ↔ username ⇄ user_id map
users.create_index("username", unique=True)

auth_app = Flask(__name__)

ALLOWED_ORIGIN = os.getenv('ALLOWED_ORIGIN', '*')

@auth_app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin']  = ALLOWED_ORIGIN
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

@auth_app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    if not username:
        return jsonify({"error": "Missing username"}), 400

    doc = users.find_one({"username": username})
    if doc:
        user_id = int(doc["user_id"])  # ensure int in case it’s stored as str
    else:
        user_id = random.getrandbits(63)  # new 63-bit positive int
        users.insert_one({
            "username": username,
            "user_id":  user_id,
            "created_at": datetime.now(timezone.utc)
        })

    token = create_jwt(user_id=user_id, username=username)  # create_jwt should set sub=str(user_id)
    return jsonify({"token": token})

if __name__ == '__main__':
    # Bind to port 5001 to avoid collision with the chat backend.
    auth_app.run(port=5001, debug=True)
