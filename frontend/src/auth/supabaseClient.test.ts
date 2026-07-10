import { afterEach, describe, expect, it, vi } from 'vitest'

/**
 * Direct unit coverage for supabaseClient.ts itself: every other test in the
 * suite mocks this module (see AuthContext.test.tsx's `vi.mock('./supabaseClient')`
 * comment), so its own construction and env-guard logic are otherwise never
 * exercised.
 *
 * #ASSUME: data-integrity: src/test/setup.ts seeds VITE_SUPABASE_URL/
 * VITE_SUPABASE_ANON_KEY via a direct `Object.defineProperty(import.meta, 'env', ...)`
 * on its OWN module's import.meta, which does not propagate to other modules'
 * import.meta.env (each module gets its own env snapshot); only `vi.stubEnv`
 * (used by LoginPage.test.tsx elsewhere) reliably propagates across modules in
 * this Vite/Vitest setup. So every test below stubs both vars explicitly
 * rather than relying on the setup.ts defaults, then re-imports the module
 * fresh (vi.resetModules) so its module-level guard actually reruns.
 * #VERIFY: confirmed empirically: a fresh module's import.meta.env does not
 * contain the setup.ts-seeded VITE_SUPABASE_* keys without an explicit stub.
 */
describe('supabaseClient', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('constructs a Supabase client when both env vars are present', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test-project.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test-anon-key')
    vi.resetModules()
    const { supabase } = await import('./supabaseClient')
    expect(supabase.auth).toBeDefined()
    expect(typeof supabase.auth.signInWithOAuth).toBe('function')
    expect(typeof supabase.auth.signInWithPassword).toBe('function')
    expect(typeof supabase.auth.getSession).toBe('function')
  })

  it('throws an actionable error when VITE_SUPABASE_URL is missing', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test-anon-key')
    vi.resetModules()
    await expect(import('./supabaseClient')).rejects.toThrow(
      /Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY/
    )
  })

  it('throws an actionable error when VITE_SUPABASE_ANON_KEY is missing', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test-project.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')
    vi.resetModules()
    await expect(import('./supabaseClient')).rejects.toThrow(
      /Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY/
    )
  })
})
