## Quick Start (Dev)

### Prereqs
- Node 20+, Python 3.11+, MongoDB 7.x running on localhost:27017 (or update MONGO_URL)

### 1) Backend (port 5003)
export JWT_SECRET_KEY='devsecret'
export MONGO_URL='mongodb://localhost:27017/praxis_assistant'
python app.py  # or: gunicorn --bind 0.0.0.0:5003 app:app

### 2) Frontend (port 3000)
# vite.config.js proxies /api/history -> http://localhost:5003/history, /api/chat -> .../chat
npm install
npm run dev
# open http://localhost:3000

### 3) Test
- Paste a JWT (HS256; sub=user id) in the UI gate.
- You should see history load and be able to chat.

## Quick Start (Docker)

### Build & Run
docker compose build
docker compose up -d

### Open
http://localhost

### Override env (if needed)
- docker-compose.yml sets:
  - backend: JWT_SECRET_KEY, MONGO_URL=mongodb://mongo:27017/praxis_assistant
  - frontend: VITE_BACKEND_URL=/api baked into the build

## Endpoints (legacy UI flow)
- GET  /history       (Authorization: Bearer <jwt>)
- POST /chat          (Authorization: Bearer <jwt>; body { history: [{role, content}] })
- GET  /api/me        (Authorization: Bearer <jwt>)

## Smoke Tests
TOKEN="<dev_jwt>"
curl -i http://localhost/api/me -H "Authorization: Bearer $TOKEN"
curl -i http://localhost/api/history -H "Authorization: Bearer $TOKEN"
curl -i http://localhost/api/chat -H "Authorization: Bearer $TOKEN" \
-H "Content-Type: application/json" --data '{"history":[{"role":"user","content":"hello"}]}'
