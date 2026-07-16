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
        // Chrome suppresses the install prompt without a 192px and a 512px
        // icon plus a maskable variant, so this array is what makes the PWA
        // actually installable. PNGs live in public/ (generated from the Pip
        // mascot art in src/kid/Mascot.tsx on the design-system parchment).
        icons: [
          { src: '/pwa-icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/pwa-icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // #ASSUME: external-resources: Workbox's default globPatterns
        // precache only js/css/html, but the illustrated avatar set (issue
        // #65 phase 1) ships as WebP imports bundled into the app; without
        // webp (plus the usual raster/vector formats) here, profile pickers
        // show broken avatar images offline.
        // #VERIFY: when adding a new bundled asset format, extend this
        // pattern and confirm the asset renders with the network disabled.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webp}'],
        // Story version blobs are immutable: cache-first, long-lived.
        // Other API GETs: network-first with a cache fallback, so reads the
        // client has fetched before survive a flaky network. This is a
        // best-effort assist only; Workbox runtime caching handles GETs, and
        // durable offline reading lives in the IndexedDB store (src/offline/).
        //
        // Patterns are start-anchored against the full request URL: Workbox
        // applies a RegExp route to a cross-origin request only when the match
        // starts at the beginning of the URL, so a path-only pattern such as
        // the former /\/api\/v1\/.*/ silently never matched (no SW caching at
        // all) once VITE_API_URL pointed the client at another origin. The
        // optional 'api/' segment accepts both the same-origin proxy shape
        // ('/api/v1/...') and a cross-origin backend serving '/v1/...'.
        // #ASSUME: external-resources: the API is mounted at '/api/v1'
        // (same-origin proxy) or '/v1' (cross-origin host); any other prefix
        // silently disables SW caching for the API again.
        // #VERIFY: after changing VITE_API_URL or the backend route prefix,
        // load a story and confirm 'storybook-blobs' and 'api-cache' populate
        // under DevTools > Application > Cache Storage.
        runtimeCaching: [
          {
            urlPattern: /^https?:\/\/[^/]+\/(?:api\/)?v1\/storybooks\/.*\/versions\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'storybook-blobs',
              // Immutable blobs: keep a bounded set for a month.
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: /^https?:\/\/[^/]+\/(?:api\/)?v1\/.*/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              // Fall back to cache quickly on a flaky network, and bound the cache
              // so it cannot grow without limit.
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 7 },
              // #CRITICAL: security: these are authenticated GETs (/v1/me,
              // /v1/profiles, /v1/story_requests, /v1/families). Workbox keys
              // its cache by request URL alone, so on a shared or hand-me-down
              // family device the NetworkFirst fallback (offline, or past the
              // 5s timeout) could otherwise serve one child's or family's
              // cached response to whoever asks for the same URL next, even
              // after a sign-out or profile switch on the same device.
              // #VERIFY: cacheKeyWillBeUsed folds a hash of the request's
              // Authorization bearer token into the cache key, so distinct
              // sessions on the same device never share a cache entry for the
              // same URL. Hashed, not stored raw, so the token itself is not
              // duplicated into an inspectable Cache Storage key.
              plugins: [
                {
                  cacheKeyWillBeUsed: async ({ request }) => {
                    const auth = request.headers.get('Authorization') ?? ''
                    const digest = await crypto.subtle.digest(
                      'SHA-256',
                      new TextEncoder().encode(auth)
                    )
                    const authHash = Array.from(new Uint8Array(digest))
                      .map((byte) => byte.toString(16).padStart(2, '0'))
                      .join('')
                    const url = new URL(request.url)
                    url.searchParams.set('_auth', authHash)
                    return url.toString()
                  },
                },
              ],
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
