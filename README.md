# Praxis Assistant Monorepo

This repository contains both the **frontend** (React + Vite + TailwindCSS) and **backend** (Flask + Google Gemini + JWT + FAISS RAG) services for the Praxis AI Assistant.

## 📁 Repository Structure

```
/ (root)
├─ frontend/                   # React chat widget & login UI
│  ├─ .gitignore               # Node & build ignores
│  ├─ package.json             # Frontend dependencies & scripts
│  ├─ postcss.config.js        # PostCSS & Tailwind setup
│  ├─ tailwind.config.js       # Tailwind configuration
│  ├─ vite.config.js           # Dev server and proxy settings
│  └─ src/
│     ├─ assets/               # Static images, icons, etc.
│     ├─ components/
│     │  ├─ ChatWidget.jsx     # Main chat interface
│     │  └─ LoginForm.jsx      # JWT-based login form
│     ├─ App.jsx               # Root component (theme toggle & auth)
│     ├─ index.css             # Tailwind directives & global overrides
│     └─ main.jsx              # App entry point
│
├─ backend/                    # Flask + Gemini + FAISS + JWT microservice
│  ├─ .gitignore               # Python & env ignores
│  ├─ requirements.txt         # Python dependencies
│  ├─ app.py                   # Flask application (login & chat endpoints)
│  ├─ jwt_utils.py             # JWT creation & verification
│  └─ retrieval.py             # FAISS index loader & RAG retriever
│
└─ README.md                   # Project overview and setup instructions
```

## 📋 Prerequisites

* **Node.js** (v16+) and **npm** for frontend
* **Python** (3.9+) and **pip** for backend

## 🔧 Environment Variables

Copy `/backend/.env.example` to `/backend/.env` and set:

```
GEMINI_API_KEY=YOUR_GOOGLE_GEMINI_API_KEY
JWT_SECRET_KEY=YOUR_RANDOM_SECRET_KEY
JWT_ALGORITHM=HS256
```

> **Testing:** Use the provided sample secret key for jwt: `f9b6SK88Ka0YqKEz0iSGe2Y3Kqzv0QwVcfdufru2r2o=`

## 🏃‍♀️ Running Locally

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

* Runs at [http://localhost:5000](http://localhost:5000)
* Endpoints:

  * `POST /login` → returns `{ token }`
  * `POST /chat` (requires `Authorization: Bearer <token>`) → returns `{ reply }`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

* Runs at [http://localhost:3000](http://localhost:3000)
* Proxies `/login` and `/chat` to the Flask backend

## 📑 Usage

1. Start backend and frontend.
2. In the browser, login with any username.
3. Chat with the assistant; JWT is sent in each request header.
4. Chat history persists per user in `sessionStorage`.
