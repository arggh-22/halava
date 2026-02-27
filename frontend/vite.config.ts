import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // Listen on all interfaces (IPv4 and IPv6)
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    // Allow tunnel URL
    allowedHosts: [

      '.trycloudflare.com',
      'population-filed-committees-jack.trycloudflare.com'
    ]
  },
})
