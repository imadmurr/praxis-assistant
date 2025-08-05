import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // forward any request from /chat → http://localhost:5000/chat
      '/chat': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/history': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    }
  }
})
