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
      external: ['react', 'react-dom'],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
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
