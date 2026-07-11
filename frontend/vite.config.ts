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
        // Default globPatterns only precache js/css/html; the illustrated
        // avatar set (issue #65 phase 1) ships as WebP imports bundled into
        // the app, so extend the pattern to include images (webp plus the
        // usual raster/vector formats) so profile pickers render avatars
        // offline instead of showing broken images.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webp}'],
        // Story version blobs are immutable: cache-first, long-lived.
        // Reading state and other API calls: network-first with a cache fallback
        // so a downloaded story still plays offline.
        runtimeCaching: [
          {
            urlPattern: /\/api\/v1\/storybooks\/.*\/versions\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'storybook-blobs',
              // Immutable blobs: keep a bounded set for a month.
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: /\/api\/v1\/.*/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              // Fall back to cache quickly on a flaky network, and bound the cache
              // so it cannot grow without limit.
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 7 },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@ds': path.resolve(__dirname, './design-system/src'),
    },
    // The @ds alias pulls design-system component source into this app, and
    // those components import React. Vite 8 no longer dedupes these by
    // default, so tests would load a second React copy (from the
    // design-system workspace) and fail with "Invalid hook call". Force a
    // single React instance across the app and the aliased design-system src.
    dedupe: ['react', 'react-dom'],
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
  preview: {
    port: 4173,
    // The real-backend e2e tier serves the built app via `vite preview` and
    // relies on this proxy to reach uvicorn; `server.proxy` alone is not
    // guaranteed to apply to the preview server, so the `/api` route is
    // re-declared here. Only `/api` is mirrored: the e2e-real tier never hits
    // `/openapi.json` (that route exists in `server.proxy` for dev-time client
    // generation, not for the built app).
    proxy: {
      '/api': {
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
    // In CI, also emit JUnit XML so the run can be uploaded to Codecov Test
    // Analytics (the "Tests" tab). GitHub Actions sets CI=true; locally we keep
    // just the default reporter so no stray junit.xml is written on every run.
    reporters: process.env.CI ? ['default', 'junit'] : ['default'],
    outputFile: { junit: './junit.xml' },
    coverage: {
      provider: 'v8',
      // Scope coverage to app source. Without an explicit include, the v8
      // provider reports every file the run touches (node_modules, dist, e2e
      // specs, design-system, even paths above frontend/), and those unmappable
      // paths made Codecov reject the whole lcov as an "unusable report".
      // Code files only: a bare 'src/**' also feeds non-code files (e.g.
      // src/assets/.gitkeep) into the uncovered-files pass, where the parser
      // fails on them with a noisy (though harmless) PARSE_ERROR.
      include: ['src/**/*.{ts,tsx}'],
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'src/test/',
        'src/client/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/*.{test,spec}.{ts,tsx}',
        // Bootstrap entry: only exercised by e2e (Playwright), never imported
        // by a unit/component test.
        'src/main.tsx',
        // Type-only module: no runtime statements to cover.
        'src/player/types.ts',
        // #ASSUME: data-integrity: the `include: ['src/**/*.{ts,tsx}']` glob
        // above is not anchored to the frontend root, so it also matches
        // `design-system/src/**` (reached via the `@ds` alias) even though
        // design-system is a separate npm workspace with its own vitest
        // config, its own coverage run, and its own Codecov `design-system`
        // flag (see .github/workflows/ci.yml `design-system` job). Without
        // this exclude, adding perFile thresholds here would also gate files
        // that are already covered and thresholded by that separate job.
        // #VERIFY: `npm run test:coverage` reports only `src/**` files below.
        '**/design-system/**',
      ],
      thresholds: {
        lines: 70,
        branches: 70,
        functions: 70,
        statements: 70,
        perFile: true,
      },
    },
  },
})
