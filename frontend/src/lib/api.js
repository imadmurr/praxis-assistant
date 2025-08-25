// Single source of truth for the API base
// Prefer same-origin '/api' so Nginx can proxy to the backend container.
const raw = (import.meta.env.VITE_BACKEND_URL ?? '/api').toString();
export const BACKEND_URL = raw.replace(/\/+$/, '');

if (typeof window !== 'undefined') {
    console.log('[config] BACKEND_URL =', BACKEND_URL);
}
