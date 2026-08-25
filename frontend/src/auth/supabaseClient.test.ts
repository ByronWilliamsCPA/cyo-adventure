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
    expect(hashIndicatesRecovery('#access_token=abc.def.ghi&expires_in=3600&type=recovery')).toBe(
      true
    )
  })

  it('is false for an ordinary OAuth / bearer return hash', async () => {
    // A normal sign-in return must NOT be treated as a recovery, or every
    // login would show the set-new-password form.
    const { hashIndicatesRecovery } = await import('./supabaseClient')
    expect(hashIndicatesRecovery('#access_token=abc.def.ghi&expires_in=3600&type=bearer')).toBe(
      false
    )
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

/**
 * The early-sign-in capture is what warms the adult gate on an OAuth return
 * leg. These tests pin the two properties that make it safe to warm from:
 * it records ONLY a supabase-js 'SIGNED_IN', and it is single-use.
 *
 * #CRITICAL: security: the predicate this replaced read window.location.hash
 * directly and returned true for any fragment carrying an `access_token` key,
 * including `#access_token=` with an empty value, which supabase-js itself
 * declines to treat as a callback. That let a typed, bookmarked, or replayed
 * URL warm the gate for an already-persisted session, bypassing the ADR-014
 * step-up entirely. "ignores a URL fragment that no supabase-js event backs"
 * below is the regression test for exactly that bypass.
 * #VERIFY: this block, plus AuthContext.test.tsx's OAuth-return warm tests.
 */
describe('early sign-in capture', () => {
  type AuthHandler = (event: string, session: { user: { id: string } } | null) => void

  const originalHash = window.location.hash

  beforeEach(() => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test-project.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test-anon-key')
  })

  afterEach(() => {
    window.location.hash = originalHash
    vi.doUnmock('@supabase/supabase-js')
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  /**
   * Loads supabaseClient.ts against a stubbed createClient so the module's
   * own onAuthStateChange subscriber is observable, and hands back a way to
   * drive it. Stubbing at the supabase-js boundary (rather than mocking
   * supabaseClient itself) is what keeps the subscriber under test.
   */
  async function loadWithStubbedAuth(): Promise<{
    consumeEarlySignInUserId: () => string | null
    emit: AuthHandler
    unsubscribe: ReturnType<typeof vi.fn>
  }> {
    const unsubscribe = vi.fn()
    const holder: { handler: AuthHandler | null } = { handler: null }
    vi.resetModules()
    vi.doMock('@supabase/supabase-js', () => ({
      createClient: () => ({
        auth: {
          onAuthStateChange: (handler: AuthHandler) => {
            holder.handler = handler
            return { data: { subscription: { unsubscribe } } }
          },
        },
      }),
    }))
    const mod = await import('./supabaseClient')
    return {
      consumeEarlySignInUserId: mod.consumeEarlySignInUserId,
      emit: (event, session) => {
        const handler = holder.handler
        if (handler === null) throw new Error('supabaseClient never subscribed')
        handler(event, session)
      },
      unsubscribe,
    }
  }

  it('records a SIGNED_IN that lands before AuthProvider subscribes', async () => {
    // This is the OAuth return leg: detectSessionInUrl signs the guardian in
    // from inside createClient's initialize(), so the event can fire before
    // any React subscriber exists. The module-scope subscriber catches it.
    const { consumeEarlySignInUserId, emit } = await loadWithStubbedAuth()
    emit('SIGNED_IN', { user: { id: 'guardian-1' } })
    expect(consumeEarlySignInUserId()).toBe('guardian-1')
  })

  it('is single-use, so a later resolution in the same page load cannot re-warm', async () => {
    // #CRITICAL: security: syncPrincipal runs again for recordConsent,
    // startVerification, and every guardian interstitial's "check again"
    // refreshStatus. If the capture survived consumption, each of those would
    // slide the gate's idle TTL forward for a guardian who has walked away.
    const { consumeEarlySignInUserId, emit } = await loadWithStubbedAuth()
    emit('SIGNED_IN', { user: { id: 'guardian-1' } })
    expect(consumeEarlySignInUserId()).toBe('guardian-1')
    expect(consumeEarlySignInUserId()).toBeNull()
    expect(consumeEarlySignInUserId()).toBeNull()
  })

  it('unsubscribes once it has captured a sign-in', async () => {
    const { emit, unsubscribe } = await loadWithStubbedAuth()
    expect(unsubscribe).not.toHaveBeenCalled()
    emit('SIGNED_IN', { user: { id: 'guardian-1' } })
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('ignores a restored session and a silent token refresh', async () => {
    // These are the events the adult gate must stay cold for: a persisted
    // session replayed on load, and a walked-away tab refreshing itself.
    const { consumeEarlySignInUserId, emit } = await loadWithStubbedAuth()
    emit('INITIAL_SESSION', { user: { id: 'guardian-1' } })
    emit('TOKEN_REFRESHED', { user: { id: 'guardian-1' } })
    emit('USER_UPDATED', { user: { id: 'guardian-1' } })
    emit('PASSWORD_RECOVERY', { user: { id: 'guardian-1' } })
    expect(consumeEarlySignInUserId()).toBeNull()
  })

  it('ignores a SIGNED_IN carrying no session', async () => {
    const { consumeEarlySignInUserId, emit } = await loadWithStubbedAuth()
    emit('SIGNED_IN', null)
    expect(consumeEarlySignInUserId()).toBeNull()
  })

  it('is null on an ordinary page load where no event fires', async () => {
    const { consumeEarlySignInUserId } = await loadWithStubbedAuth()
    expect(consumeEarlySignInUserId()).toBeNull()
  })

  it('ignores a URL fragment that no supabase-js event backs', async () => {
    // #CRITICAL: security: the regression test for the bypass this design
    // replaced. Every one of these fragments made the old hash predicate
    // return true; `#access_token=` did so without supabase-js even treating
    // the load as a callback, leaving the fragment in the address bar so the
    // URL stayed shareable and worked on every visit. With the capture, a
    // fragment on its own proves nothing, because only a server-validated
    // sign-in reaches the subscriber.
    for (const hash of [
      '#access_token=',
      '#access_token',
      '#access_token=forged',
      '#access_token=forged&expires_in=3600&refresh_token=r1&token_type=bearer',
      '#access_token=forged&type=signup',
      '#access_token=forged&type=magiclink',
    ]) {
      window.location.hash = hash
      const { consumeEarlySignInUserId } = await loadWithStubbedAuth()
      expect(consumeEarlySignInUserId()).toBeNull()
      vi.doUnmock('@supabase/supabase-js')
    }
  })
})
