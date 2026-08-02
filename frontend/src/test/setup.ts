import '@testing-library/jest-dom'
import { beforeEach } from 'vitest'

import { clearInFlightProgress } from '../kid/progressApi'

// `GET /v1/me/progress` coalesces concurrent callers through a module-level
// map (see progressApi.ts). Cleared here rather than in each suite's own
// beforeEach so a new test file cannot forget: several suites mock a fetch
// that never settles, which never runs the entry's own cleanup and would
// otherwise hand a later case the earlier case's pending promise.
beforeEach(() => {
  clearInFlightProgress()
})

// Mock environment variables for tests
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:8000',
    VITE_SUPABASE_URL: 'https://test-project.supabase.co',
    VITE_SUPABASE_ANON_KEY: 'test-anon-key',
    PROD: false,
    DEV: true,
  },
})
