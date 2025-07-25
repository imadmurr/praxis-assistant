# backend/retrieval.py

import os
import pickle
from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss

# ── Config ─────────────────────────────────────────────────────────────────
DOCS_DIR    = os.getenv("DOCS_DIR", "../docs")       # drop your .md/.txt here
INDEX_FILE  = os.getenv("RAG_INDEX_FILE", "rag_index.pkl")
EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")  # small, fast embedder

# ── Build or load the FAISS index + raw texts ──────────────────────────────
def load_or_build_index():
    if Path(INDEX_FILE).exists():
        with open(INDEX_FILE, "rb") as f:
            index, docs = pickle.load(f)
        print(f"[retrieval] Loaded existing index from {INDEX_FILE} ({len(docs)} docs)")
    else:
        print(f"[retrieval] No index file found; building new one from {DOCS_DIR}…")
        docs = []

        # scan both .md and .txt
        for ext in ("*.md", "*.txt"):
            for p in Path(DOCS_DIR).rglob(ext):
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    docs.append(text)

        if not docs:
            raise RuntimeError(f"No documents found in {DOCS_DIR} (searched .md and .txt)")

        # embed
        embeddings = EMBED_MODEL.encode(docs, convert_to_numpy=True)
        if embeddings.ndim != 2:
            raise RuntimeError(f"Embeddings have wrong shape: {embeddings.shape}")

        # create FAISS index
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)

        # persist
        with open(INDEX_FILE, "wb") as f:
            pickle.dump((index, docs), f)
        print(f"[retrieval] Built & saved index ({len(docs)} docs) → {INDEX_FILE}")

    return index, docs

# load on import
INDEX, DOC_TEXTS = load_or_build_index()

# ── Retrieval function ─────────────────────────────────────────────────────
def retrieve_relevant(query: str, k: int = 3) -> list[str]:
    q_emb = EMBED_MODEL.encode([query], convert_to_numpy=True)
    D, I = INDEX.search(q_emb, k)
    return [DOC_TEXTS[i] for i in I[0]]

# ── CLI entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_or_build_index()
