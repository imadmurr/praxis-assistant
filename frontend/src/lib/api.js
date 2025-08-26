// src/lib/api.js
// Centralized API client for Praxis Assistant (Vite + fetch).
// - Attaches Authorization: Bearer <jwt> to every request.
// - On 401, clears token and routes user to login/paste-JWT.
// - Exposes helpers for legacy (/history, /chat) and new (/api/chats/*) endpoints.

// Base URLs
const RAW = (import.meta.env.VITE_BACKEND_URL ?? "/api").toString();
export const BACKEND_URL = RAW.replace(/\/+$/, "");   // e.g., "/api"
export const AUTH_URL = (import.meta.env.VITE_AUTH_URL ?? "/auth").toString().replace(/\/+$/, "");

// Token storage (matches App.jsx)
const TOKEN_KEY = "jwt_token"; // <- App.jsx uses this key

export function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}
export function setToken(token) {
    try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch {}
}
export function clearToken() { setToken(""); }

// Core request
export async function request(path, { method = "GET", headers = {}, body, raw = false } = {}) {
    const url = path.startsWith("http") ? path : `${path.startsWith("/auth") ? AUTH_URL : BACKEND_URL}/${path.replace(/^\/+/, "")}`;
    const token = getToken();

    const baseHeaders = {
        ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
    };

    const res = await fetch(url, {
        method,
        headers: baseHeaders,
        body: body && !(body instanceof FormData) ? JSON.stringify(body) : body,
        credentials: "include",
    });

    if (res.status === 401) {
        clearToken();
        if (typeof window !== "undefined") window.location.href = "/"; // App.jsx shows the paste-JWT gate
        throw new Error("Unauthorized");
    }

    if (raw) return res;

    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
        const json = await res.json();
        if (!res.ok) throw new Error((json && (json.error || json.message)) || `HTTP ${res.status}`);
        return json;
    } else {
        const text = await res.text();
        if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
        return text;
    }
}

// Convenience helpers
export function get(path, opts)  { return request(path, { ...opts, method: "GET"  }); }
export function post(path, body, opts) { return request(path, { ...opts, method: "POST", body }); }
export function del(path, opts)  { return request(path, { ...opts, method: "DELETE" }); }

// Legacy endpoints (current UI)
export function getHistory()         { return get("/history"); }
export function sendChat(history)    { return post("/chat", { history }); }

// New WhatsApp-style endpoints (ready when you switch UI)
export function listChats()                          { return get("/api/chats"); }
export function createChat(title)                    { return post("/api/chats", title ? { title } : {}); }
export function getMessages(chatId, { limit = 50, before } = {}) {
    const q = new URLSearchParams();
    if (limit) q.set("limit", String(limit));
    if (before) q.set("before", before);
    return get(`/api/chats/${chatId}/messages?${q.toString()}`);
}
export function sendMessage(chatId, content)         { return post(`/api/chats/${chatId}/messages`, { content }); }
export function archiveChat(chatId)                  { return del(`/api/chats/${chatId}`); }

const api = {
    BACKEND_URL,
    AUTH_URL,
    getToken, setToken, clearToken,
    request, get, post, del,
    getHistory, sendChat,
    listChats, createChat, getMessages, sendMessage, archiveChat,
};
export default api;
