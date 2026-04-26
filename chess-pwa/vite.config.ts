import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        // Allow caching the large WASM + NNUE files
        maximumFileSizeToCacheInBytes: 600_000_000,
        globPatterns: ['**/*.{js,css,html,wasm,bin,nnue}'],
        // Don't precache the LLM model — WebLLM caches it in IndexedDB
        globIgnores: ['**/model/**'],
        runtimeCaching: [
          {
            urlPattern: /\/engine\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'engine-cache',
              expiration: { maxEntries: 10 },
            },
          },
        ],
      },
      manifest: {
        name: 'Chess Analyzer',
        short_name: 'ChessAI',
        description: 'ShashChess analysis with on-device AI commentary',
        display: 'standalone',
        background_color: '#1a1a1a',
        theme_color: '#769656',
        icons: [
          { src: '/icons/192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  optimizeDeps: {
    exclude: ['@mlc-ai/web-llm'],
  },
  build: {
    target: 'esnext',
  },
  server: {
    allowedHosts: true,
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
})
