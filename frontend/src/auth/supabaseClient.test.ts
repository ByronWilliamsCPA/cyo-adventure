import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * #CRITICAL: timing dependencies: supabaseClient.ts throws at module-eval time
 * when VITE_SUPABASE_* env vars are absent (see the guard clause below). A
 * static top-level `import { hashIndicatesRecovery } from './supabaseClient'`
 * is hoisted and evaluated before any vi.stubEnv() call in this file runs,
 * crashing test collection in CI where those vars are unset. Stub the env in
 * beforeEach and load the module dynamically, matching the pattern the
 * `describe('supabaseClient', ...)` block below already uses.
 * #VERIFY: CI failure at src/auth/supabaseClient.test.ts:3 (fixed by this
 * change) and CodeRabbit's independent flag on the same line.
 */
describe('hashIndicatesRecovery', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test-project.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test-anon-key')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('is true for a Supabase recovery-link hash', async () => {
    // Supabase's /verify?type=recovery redirect lands with an implicit-flow
    // hash carrying type=recovery alongside the access token.
    const { hashIndicatesRecovery } = await import('./supabaseClient')
    expect(
      hashIndicatesRecovery('#access_token=abc.def.ghi&expires_in=3600&type=recovery')
    ).toBe(true)
  })

  it('is false for an ordinary OAuth / bearer return hash', async () => {
    // A normal sign-in return must NOT be treated as a recovery, or every
    // login would show the set-new-password form.
    const { hashIndicatesRecovery } = await import('./supabaseClient')
    expect(
      hashIndicatesRecovery('#access_token=abc.def.ghi&expires_in=3600&type=bearer')
    ).toBe(false)
  })

  it('is false for a signup-confirmation hash', async () => {
    const { hashIndicatesRecovery } = await import('./supabaseClient')
    expect(hashIndicatesRecovery('#access_token=abc&type=signup')).toBe(false)
  })

  it('is false for an empty or bare-hash location', async () => {
    const { hashIndicatesRecovery } = await import('./supabaseClient')
    expect(hashIndicatesRecovery('')).toBe(false)
    expect(hashIndicatesRecovery('#')).toBe(false)
  })

  it('tolerates a hash with no leading # (defensive)', async () => {
    const { hashIndicatesRecovery } = await import('./supabaseClient')
    expect(hashIndicatesRecovery('type=recovery&access_token=abc')).toBe(true)
  })
})

describe('hashIndicatesRecoveryError', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test-project.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test-anon-key')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('extracts the code and description from an expired/used recovery-link hash', async () => {
    // Supabase's own shape for a rejected recovery redirect: no `type` param,
    // just error/error_code/error_description.
    const { hashIndicatesRecoveryError } = await import('./supabaseClient')
    expect(
      hashIndicatesRecoveryError(
        '#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired'
      )
    ).toEqual({ code: 'otp_expired', description: 'Email link is invalid or has expired' })
  })

  it('falls back to the bare error code and a generic description when error_code/error_description are absent', async () => {
    const { hashIndicatesRecoveryError } = await import('./supabaseClient')
    expect(hashIndicatesRecoveryError('#error=access_denied')).toEqual({
      code: 'access_denied',
      description: 'The link is invalid or has expired.',
    })
  })

  it('is null for a successful recovery hash', async () => {
    const { hashIndicatesRecoveryError } = await import('./supabaseClient')
    expect(
      hashIndicatesRecoveryError('#access_token=abc.def.ghi&expires_in=3600&type=recovery')
    ).toBeNull()
  })

  it('is null for an empty or bare-hash location', async () => {
    const { hashIndicatesRecoveryError } = await import('./supabaseClient')
    expect(hashIndicatesRecoveryError('')).toBeNull()
    expect(hashIndicatesRecoveryError('#')).toBeNull()
  })
})

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
