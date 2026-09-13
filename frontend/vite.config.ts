import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The SPA is served by Flask under /app (see serve_spa in app.py), so assets must
// resolve against /app/ rather than the site root.
const BASE = '/app/'

// Flask dev server. In dev we proxy instead of enabling CORS, so the browser sees a
// single origin and the existing session cookie keeps working untouched.
const FLASK = 'http://127.0.0.1:5000'

export default defineConfig({
  base: BASE,
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: FLASK, changeOrigin: false },
      // Achievement/attribute artwork still lives on the Flask side.
      '/static': { target: FLASK, changeOrigin: false },
      '/login': { target: FLASK, changeOrigin: false },
      '/logout': { target: FLASK, changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
