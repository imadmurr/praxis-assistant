import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Legacy endpoints now called through /api/... by the frontend
      '/api/history': {
        target: 'http://localhost:5003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // -> /history
      },
      '/api/chat': {
        target: 'http://localhost:5003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // -> /chat
      },

      // New endpoints live under /api on the backend already
      '/api/chats': {
        target: 'http://localhost:5003',
        changeOrigin: true,
      },
      '/api/me': {
        target: 'http://localhost:5003',
        changeOrigin: true,
      },
    },
  }
})
