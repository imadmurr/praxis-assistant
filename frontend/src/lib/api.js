// Use Vite env vars injected at build time
export const AUTH_URL    = import.meta.env.VITE_AUTH_URL ?? '';
export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? '';

// Helpful warning in case something is missing at runtime
if (!AUTH_URL || !BACKEND_URL) {
    // This shows in the browser console during testing
    console.warn('[config] Missing VITE_AUTH_URL or VITE_BACKEND_URL. ' +
        'Are your env vars set at build time?');
}
