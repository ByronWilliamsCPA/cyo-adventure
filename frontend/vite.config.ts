import path from 'node:path'
import react from '@vitejs/plugin-react-swc'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'CYO Adventure',
        short_name: 'Adventure',
        description: 'Choose-your-own-adventure reader for the family library.',
        theme_color: '#1d3557',
        background_color: '#f1faee',
        display: 'standalone',
        start_url: '/',
      },
      workbox: {
        // Story version blobs are immutable: cache-first, long-lived.
        // Reading state and other API calls: network-first with a cache fallback
        // so a downloaded story still plays offline.
        runtimeCaching: [
          {
            urlPattern: /\/api\/v1\/storybooks\/.*\/versions\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'storybook-blobs',
              expiration: { maxEntries: 50 },
            },
          },
          {
            urlPattern: /\/api\/v1\/.*/,
            handler: 'NetworkFirst',
            options: { cacheName: 'api-cache' },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      // Proxy API requests to backend during development
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    // Unit/component tests live under src; e2e/ is Playwright's.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: ['node_modules/', 'src/test/', 'src/client/', '**/*.d.ts', '**/*.config.*'],
    },
  },
})
