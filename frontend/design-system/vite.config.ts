import { resolve } from 'node:path'
import react from '@vitejs/plugin-react-swc'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'CYO',
      formats: ['es', 'umd'],
      fileName: (format) => `cyo-design-system.${format === 'es' ? 'js' : 'umd.cjs'}`,
      cssFileName: 'cyo-design-system',
    },
    rollupOptions: {
      // #CRITICAL: external resource: react/jsx-runtime must stay external.
      // Vite 8 (rolldown) inlines it otherwise, and its CJS interop leaves a
      // runtime require("react") that throws in browsers consuming the ESM
      // dist without a bundler (the design-sync converter is one).
      // #VERIFY: after a build, `grep -c 'react-stack-top-frame' dist/cyo-design-system.js` must be 0.
      external: ['react', 'react-dom', 'react/jsx-runtime'],
      output: {
        // #EDGE: external resource: these globals only matter to a bare
        // <script> consumer of the UMD build, which nothing in this repo is.
        // 'ReactJSXRuntime' is a placeholder name no real React build
        // exposes; require()-based consumers resolve through package.json's
        // CJS branch and never read it.
        // #VERIFY: if the UMD artifact ever gains a bare-script consumer,
        // that consumer must define window.ReactJSXRuntime itself.
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
          'react/jsx-runtime': 'ReactJSXRuntime',
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: [resolve(__dirname, 'src/test/setup.ts')],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      // Scope coverage to library source (see the frontend config note): an
      // include keeps node_modules, dist, and .design-sync out of the lcov so
      // Codecov does not reject the report over unmappable paths.
      include: ['src/**'],
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'src/test/',
        'src/index.ts',
        'src/components/**/index.ts',
        '**/*.d.ts',
        '**/*.config.*',
        '**/*.{test,spec}.{ts,tsx}',
      ],
    },
  },
})
