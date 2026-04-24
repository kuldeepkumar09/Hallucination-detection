import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/verify': { target: 'http://localhost:80', changeOrigin: true },
      '/health': { target: 'http://localhost:80', changeOrigin: true },
      '/audit':  { target: 'http://localhost:80', changeOrigin: true },
      '/kb':     { target: 'http://localhost:80', changeOrigin: true },
      '/cache':  { target: 'http://localhost:80', changeOrigin: true },
      '/v1':     { target: 'http://localhost:80', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
})
