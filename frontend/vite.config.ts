import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Flask serves the SPA at the site root (see index() in app.py).
const BASE = '/'

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
      '/register': { target: FLASK, changeOrigin: false },
      '/classic': { target: FLASK, changeOrigin: false },
      '/admin': { target: FLASK, changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
