import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from '../guardian/LoginPage'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { AuthProvider } from './AuthContext'
import { getChildSession, setChildSession } from './childSession'
import { adultGateRemainingMs, clearAdultGate, warmAdultGate } from './parentalGateState'
import { useAuth } from './useAuth'

const mockGet = vi.fn()
const mockPost = vi.fn()
// A stable object, not a fresh literal per call: useApi() is memoized in
// production (useMemo(..., [config])), and AuthContext's effect depends on
// [api]. A fresh object per render here would re-fire the effect on every
// state update, re-running getSession()/onAuthStateChange spuriously.
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

/**
 * The onboarding response every test gets by default (an already-approved,
 * already-consented guardian), so syncPrincipal's onboarding check always
 * falls through to /v1/me exactly as it did before onboarding existed in
 * this flow. Tests that specifically exercise the awaiting-approval or
 * needs-consent branches override mockPost's resolved value themselves.
 */
const RESOLVED_ONBOARDING_RESPONSE = {
  data: {
    family_id: 'fam-1',
    user_id: 'user-1',
    role: 'guardian',
    created: false,
    status: 'active',
    consent_recorded: true,
    // Present and false, not omitted: the real response always carries both,
    // and the ADR-018 D1 branch reads them. Leaving them off would make every
    // test below pass through that branch on `undefined` being falsy, which
    // is the same outcome for the wrong reason.
    verification_required: false,
    verification_status: 'none',
  },
}

const mockGetSession = vi.fn()
const mockOnAuthStateChange = vi.fn()
const mockSignInWithOAuth = vi.fn()
const mockSignInWithPassword = vi.fn()
const mockSignOut = vi.fn()
const mockResetPasswordForEmail = vi.fn()
const mockUpdateUser = vi.fn()
// Drives the recovery seed (AuthProvider's useState(isPasswordRecovery)).
// A `mock`-prefixed let so vitest allows referencing it inside the hoisted
// factory; a getter re-reads it at each mount so tests can flip it before
// render to simulate a password-recovery landing.
let mockIsPasswordRecovery = false
// Drives the OAuth-return arm of the adult-gate warm (AuthContext's
// isFreshOAuthLanding). Frozen from the callback hash at module load in the
// real module, so it gets the same `mock`-prefixed let + getter treatment as
// mockIsPasswordRecovery above.
let mockIsOAuthReturn = false
// Drives AuthProvider's recoveryError (frozen from recoveryErrorFromUrl at
// module load, same seeding pattern as mockIsPasswordRecovery above).
let mockRecoveryErrorFromUrl: { code: string; description: string } | null = null
const mockRecoveryBroadcastChannelName = 'test-cyo-guardian-recovery'
// Each mock method's return type is annotated `unknown`, not inferred, so the
// untyped vi.fn() mocks don't leak a bare `any` past this seam: the real
// AuthContext.tsx compiles against supabaseClient.ts's actual Supabase types
// regardless of this test-only substitution.
vi.mock('./supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]): unknown => mockGetSession(...args),
      onAuthStateChange: (...args: unknown[]): unknown => mockOnAuthStateChange(...args),
      signInWithOAuth: (...args: unknown[]): unknown => mockSignInWithOAuth(...args),
      signInWithPassword: (...args: unknown[]): unknown => mockSignInWithPassword(...args),
      signOut: (...args: unknown[]): unknown => mockSignOut(...args),
      resetPasswordForEmail: (...args: unknown[]): unknown => mockResetPasswordForEmail(...args),
      updateUser: (...args: unknown[]): unknown => mockUpdateUser(...args),
    },
  },
  get isPasswordRecovery(): boolean {
    return mockIsPasswordRecovery
  },
  get isOAuthReturn(): boolean {
    return mockIsOAuthReturn
  },
  get recoveryErrorFromUrl(): { code: string; description: string } | null {
    return mockRecoveryErrorFromUrl
  },
  // A getter, not a plain property: the hoisted factory runs before this
  // file's own top-level `const` initializers, so eagerly referencing
  // mockRecoveryBroadcastChannelName here would throw a TDZ error.
  get RECOVERY_BROADCAST_CHANNEL_NAME(): string {
    return mockRecoveryBroadcastChannelName
  },
}))

// Mocked so the sign-out purge tests can assert both offline stores were
// cleared without depending on a real IndexedDB implementation in jsdom
// (purgeAuthenticatedDataAtRest's real dynamic import silently no-ops here
// otherwise, since jsdom has no IndexedDB).
const mockClearReadingStates = vi.fn()
const mockClearPersonalizationValues = vi.fn()
vi.mock('../offline/db', () => ({
  clearReadingStates: (...args: unknown[]): unknown => mockClearReadingStates(...args),
  clearPersonalizationValues: (...args: unknown[]): unknown =>
    mockClearPersonalizationValues(...args),
}))

function Probe() {
  const { status, principal, authError, verificationStatus, recovery, recoveryError } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{principal?.role ?? 'none'}</span>
      <span data-testid="isAdmin">{principal ? String(principal.isAdmin) : 'none'}</span>
      <span data-testid="authError">{authError ?? 'none'}</span>
      <span data-testid="verificationStatus">{verificationStatus ?? 'null'}</span>
      <span data-testid="recovery">{String(recovery)}</span>
      <span data-testid="recoveryError">{recoveryError?.code ?? 'none'}</span>
    </div>
  )
}

/**
 * Probe plus the verification start affordance, so the ADR-018 D1 start leg
 * can be driven without pulling in GuardianVerificationPage. Records the
 * rejected status code rather than a boolean: the two refusals this endpoint
 * makes by design (409, 429) are distinguishable only by code, and a test
 * that asserted merely "it threw" would pass against an implementation that
 * mapped both to the wrong one.
 */
function VerificationProbe() {
  const { verificationStatus, startVerification } = useAuth()
  const [startError, setStartError] = useState('none')
  return (
    <div>
      <span data-testid="verificationStatus">{verificationStatus ?? 'null'}</span>
      <span data-testid="startError">{startError}</span>
      <button
        type="button"
        onClick={() => {
          void startVerification('US').catch((err: unknown) => {
            const status = (err as { response?: { status?: number } }).response?.status
            setStartError(String(status ?? 'unknown'))
          })
        }}
      >
        start
      </button>
    </div>
  )
}

/**
 * Probe plus the retry affordance the backend-unreachable interstitial uses
 * (#452), so the recovery path can be driven from a test without pulling in
 * the page component.
 */
function RefreshProbe() {
  const { status, refreshStatus } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <button type="button" onClick={() => void refreshStatus()}>
        refresh
      </button>
    </div>
  )
}

/** Exercises the recovery actions and surfaces the rejections they rethrow. */
function RecoveryProbe() {
  const { recovery, requestPasswordReset, updatePassword } = useAuth()
  const [caught, setCaught] = useState('none')
  return (
    <div>
      <span data-testid="recovery">{String(recovery)}</span>
      <span data-testid="caught">{caught}</span>
      <button
        type="button"
        onClick={() =>
          void requestPasswordReset('reset@example.com').catch((e: Error) => setCaught(e.message))
        }
      >
        request reset
      </button>
      <button
        type="button"
        onClick={() =>
          void updatePassword('new-password-123').catch((e: Error) => setCaught(e.message))
        }
      >
        update password
      </button>
    </div>
  )
}

function ActionsProbe() {
  const { signInWithOAuth, signInWithPassword, signOut } = useAuth()
  return (
    <div>
      <button type="button" onClick={() => void signInWithOAuth('google')}>
        sign in
      </button>
      <button
        type="button"
        onClick={() => void signInWithPassword({ email: 'a@b.com', password: 'pw' })}
      >
        sign in password
      </button>
      <button type="button" onClick={() => void signOut()}>
        sign out
      </button>
    </div>
  )
}

/** Exercises recordConsent and surfaces any rejection it rethrows. */
function ConsentProbe() {
  const { status, recordConsent } = useAuth()
  const [caught, setCaught] = useState('none')
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="caught">{caught}</span>
      <button
        type="button"
        onClick={() =>
          void recordConsent('Jane A. Guardian', 'US').catch((e: Error) => setCaught(e.message))
        }
      >
        agree
      </button>
    </div>
  )
}

/** Mirrors how real call sites consume the rejections these actions now throw. */
function CatchingActionsProbe() {
  const { signInWithOAuth, signInWithPassword, signOut } = useAuth()
  const [caught, setCaught] = useState('none')
  return (
    <div>
      <span data-testid="caught">{caught}</span>
      <button
        type="button"
        onClick={() => void signInWithOAuth('google').catch((e: Error) => setCaught(e.message))}
      >
        sign in
      </button>
      <button
        type="button"
        onClick={() =>
          void signInWithPassword({ email: 'a@b.com', password: 'pw' }).catch((e: Error) =>
            setCaught(e.message)
          )
        }
      >
        sign in password
      </button>
      <button
        type="button"
        onClick={() => void signOut().catch((e: Error) => setCaught(e.message))}
      >
        sign out
      </button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  clearAdultGate()
  mockGet.mockReset()
  mockPost.mockReset().mockResolvedValue(RESOLVED_ONBOARDING_RESPONSE)
  mockGetSession.mockReset()
  mockOnAuthStateChange
    .mockReset()
    .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  mockSignInWithOAuth.mockReset()
  mockSignInWithPassword.mockReset()
  mockSignOut.mockReset()
  mockResetPasswordForEmail.mockReset()
  mockUpdateUser.mockReset()
  mockClearReadingStates.mockReset()
  mockClearPersonalizationValues.mockReset()
  mockIsPasswordRecovery = false
  mockIsOAuthReturn = false
  mockRecoveryErrorFromUrl = null
})

describe('AuthProvider', () => {
  it('resolves to signed-out with no session, without calling /me', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(mockGet).not.toHaveBeenCalled()
    expect(screen.getByTestId('authError')).toHaveTextContent('none')
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('clears an active child session (G1 / P6-04) when there is no guardian session at all', async () => {
    // Covers the "no guardian ever signed in on this device load" path, not
    // just an explicit sign-out click: safeRemoveToken() runs here too.
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(getChildSession()).toBeNull()
  })

  it('resolves the principal via /me when a session exists', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(screen.getByTestId('role')).toHaveTextContent('guardian')
    // is_admin is absent from this legacy-shaped response: the capability
    // must fail closed to false, never default open.
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('false')
    expect(screen.getByTestId('authError')).toHaveTextContent('none')
    expect(mockGet).toHaveBeenCalledWith('/v1/me')
    expect(localStorage.getItem('auth_token')).toBe('tok-1')
  })

  it('short-circuits to awaiting-approval without ever calling /me', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: true,
        status: 'awaiting_approval',
        consent_recorded: false,
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('awaiting-approval'))
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('short-circuits to needs-consent without ever calling /me', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: false,
        status: 'active',
        consent_recorded: false,
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('needs-consent'))
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('routes an unverified guardian to needs-verification ahead of awaiting-approval', async () => {
    // The ordering assertion, not just the status one. This response is
    // BOTH unverified and unapproved, which is the ordinary state of a
    // brand-new self-signup on a gated tier, so a reader of the status alone
    // cannot tell which branch produced it. Verification must win: an
    // unverified guardian parked on the awaiting-approval dead end has no
    // route forward, because no admin is going to approve an account nobody
    // asked them to look at.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: true,
        status: 'awaiting_approval',
        consent_recorded: false,
        verification_required: true,
        verification_status: 'none',
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('needs-verification')
    )
    expect(screen.getByTestId('verificationStatus')).toHaveTextContent('none')
    // require_principal refuses this user outright, so calling /me would 401.
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('keeps an unverified guardian in needs-verification once an email is in flight', async () => {
    // 'pending' is still not verified, so the status must not advance; what
    // changes is only which face the page shows. Pinned separately because
    // the two are one AuthStatus and a naive implementation that treated any
    // attempt as progress would let an unverified adult through.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: false,
        status: 'awaiting_approval',
        consent_recorded: false,
        verification_required: true,
        verification_status: 'pending',
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('needs-verification')
    )
    expect(screen.getByTestId('verificationStatus')).toHaveTextContent('pending')
  })

  it('leaves a guardian alone while the tier does not require verification', async () => {
    // The flag-off tier reports verification_status 'none' for EVERY caller,
    // which is byte-identical to what a gated-but-unstarted guardian reports.
    // Keying the branch on the status alone would therefore park every
    // guardian on every ungated deployment in front of a verification screen
    // they can never complete. This is the test that fails if the
    // verification_required conjunct is dropped.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: false,
        status: 'active',
        consent_recorded: true,
        verification_required: false,
        verification_status: 'none',
      },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        is_admin: false,
        family_id: 'fam-1',
        profile_ids: [],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
  })

  it('startVerification sends the country and re-resolves into the waiting state', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    const unstarted = {
      family_id: 'fam-1',
      user_id: 'user-1',
      role: 'guardian',
      created: false,
      status: 'awaiting_approval',
      consent_recorded: false,
      verification_required: true,
      verification_status: 'none',
    }
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/consent/kws/start') {
        return Promise.resolve({ data: { attempt_id: 'att-1', status: 'sent' } })
      }
      // The onboarding read reflects the row the start call just created, so
      // it answers 'pending' from the second call onward.
      const started = mockPost.mock.calls.some(([called]) => called === '/v1/consent/kws/start')
      return Promise.resolve({
        data: { ...unstarted, verification_status: started ? 'pending' : 'none' },
      })
    })
    render(
      <AuthProvider>
        <VerificationProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('verificationStatus')).toHaveTextContent('none'))

    fireEvent.click(screen.getByText('start'))

    await waitFor(() =>
      expect(screen.getByTestId('verificationStatus')).toHaveTextContent('pending')
    )
    // The country reaches the wire, and nothing else does: no email field is
    // sent, because the recipient is fixed server-side.
    expect(mockPost).toHaveBeenCalledWith('/v1/consent/kws/start', { location: 'US' })
  })

  it('startVerification rethrows a refusal and leaves the state unstarted', async () => {
    // 409 and 429 are the endpoint's designed refusals. Swallowing either
    // would advance the page to "check your email" for a mail that was never
    // sent, so the rejection has to reach the caller.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/consent/kws/start') {
        return Promise.reject(
          Object.assign(new Error('rate limited'), { response: { status: 429 } })
        )
      }
      return Promise.resolve({
        data: {
          family_id: 'fam-1',
          user_id: 'user-1',
          role: 'guardian',
          created: false,
          status: 'awaiting_approval',
          consent_recorded: false,
          verification_required: true,
          verification_status: 'none',
        },
      })
    })
    render(
      <AuthProvider>
        <VerificationProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('verificationStatus')).toHaveTextContent('none'))

    fireEvent.click(screen.getByText('start'))

    await waitFor(() => expect(screen.getByTestId('startError')).toHaveTextContent('429'))
    expect(screen.getByTestId('verificationStatus')).toHaveTextContent('none')
  })

  it('does not gate a non-guardian role on approval or consent', async () => {
    // An admin-only account never carries awaiting_approval (only the
    // self-signup guardian track sets it) and has no VPC consent concept;
    // onboarding.role !== 'guardian' must skip both short-circuits.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'admin',
        created: false,
        status: 'active',
        consent_recorded: false,
      },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'admin', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(mockGet).toHaveBeenCalledWith('/v1/me')
  })

  it('recordConsent posts the signature then resolves the principal via /me', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: false,
        status: 'active',
        consent_recorded: false,
      },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <ConsentProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('needs-consent'))

    // The next onboarding call (from recordConsent's own retry, and from
    // syncPrincipal's re-run after it) reports consent now recorded.
    mockPost.mockResolvedValue({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: false,
        status: 'active',
        consent_recorded: true,
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'agree' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(mockPost).toHaveBeenCalledWith('/v1/onboarding', {
      consent: {
        accepted: true,
        policy_version: expect.any(String) as string,
        signer_name: 'Jane A. Guardian',
        residence_country: 'US',
        adulthood_attested: true,
      },
    })
    expect(screen.getByTestId('caught')).toHaveTextContent('none')
  })

  it('recordConsent rethrows on failure and leaves status at needs-consent', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockPost.mockResolvedValueOnce({
      data: {
        family_id: 'fam-1',
        user_id: 'user-1',
        role: 'guardian',
        created: false,
        status: 'active',
        consent_recorded: false,
      },
    })
    render(
      <AuthProvider>
        <ConsentProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('needs-consent'))

    mockPost.mockRejectedValueOnce(new Error('422 from backend'))
    fireEvent.click(screen.getByRole('button', { name: 'agree' }))

    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('422 from backend'))
    expect(screen.getByTestId('status')).toHaveTextContent('needs-consent')
  })

  it('carries the is_admin capability onto the principal for a dual-role adult', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        is_admin: true,
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(screen.getByTestId('role')).toHaveTextContent('guardian')
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('true')
  })

  it('fails closed on a malformed truthy is_admin value', async () => {
    // The strict `=== true` guard must reject any non-boolean truthy value
    // (e.g. a stray "true" string or a 1/0 flag from a misbehaving backend),
    // never coerce it to the capability. Fail closed, not open.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        is_admin: 'true',
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(screen.getByTestId('role')).toHaveTextContent('guardian')
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('false')
  })

  it('fails closed and sets authError when /me rejects a session', async () => {
    // A session that establishes but cannot resolve a Principal must fail closed
    // AND record authError, so LoginPage can tell the user their account could
    // not be loaded instead of stranding them on an idle form.
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockRejectedValue(new Error('401 from backend'))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(screen.getByTestId('authError')).toHaveTextContent('principal-unresolved')
    expect(localStorage.getItem('auth_token')).toBeNull()
    // A guardian session that never resolves to a principal also ends
    // whatever child session shared this device's storage (G1 / P6-04).
    expect(getChildSession()).toBeNull()
  })

  // #452 classification. The security-critical half of this fix is not the
  // interstitial, it is that ONLY an unambiguous "our backend never answered"
  // signal keeps a session alive. Everything else must land on the unchanged
  // fail-closed path asserted by the test above.
  describe('principal-resolution error classification', () => {
    function arrangeSession() {
      mockGetSession.mockResolvedValue({
        data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
      })
    }

    // Faithful to the 2026-07-23 outage: axios leaves `response` undefined
    // when the request never completed. Shape matches the repo's existing
    // axios-error mocks (see reviewApi.test.ts).
    it('keeps the session on a network error and routes to backend-unreachable', async () => {
      arrangeSession()
      mockPost.mockRejectedValue({ isAxiosError: true, code: 'ERR_NETWORK' })
      render(
        <AuthProvider>
          <Probe />
        </AuthProvider>
      )
      await waitFor(() =>
        expect(screen.getByTestId('status')).toHaveTextContent('backend-unreachable')
      )
      // The token surviving is what lets a retry reach signed-in without a
      // re-login; losing it here would recreate the loop.
      expect(localStorage.getItem('auth_token')).toBe('tok-1')
      // Not an authError: LoginPage's inline banner is for the terminal case.
      expect(screen.getByTestId('authError')).toHaveTextContent('none')
      expect(screen.getByTestId('role')).toHaveTextContent('none')
    })

    it.each([500, 502, 503, 504])(
      'treats a %i from our own API as transient',
      async (status: number) => {
        arrangeSession()
        mockGet.mockRejectedValue({ isAxiosError: true, response: { status } })
        render(
          <AuthProvider>
            <Probe />
          </AuthProvider>
        )
        await waitFor(() =>
          expect(screen.getByTestId('status')).toHaveTextContent('backend-unreachable')
        )
        expect(localStorage.getItem('auth_token')).toBe('tok-1')
      }
    )

    // #CRITICAL security: a 401/403 is the backend REJECTING this JWT. If
    // that were ever classified transient we would park a dead session behind
    // a retry button and imply the guardian is still signed in.
    it.each([400, 401, 403, 404, 422])(
      'fails closed on a %i, discarding the session',
      async (status: number) => {
        arrangeSession()
        mockGet.mockRejectedValue({ isAxiosError: true, response: { status } })
        render(
          <AuthProvider>
            <Probe />
          </AuthProvider>
        )
        await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
        expect(screen.getByTestId('authError')).toHaveTextContent('principal-unresolved')
        expect(localStorage.getItem('auth_token')).toBeNull()
      }
    )

    // The fail-closed default. An error we cannot classify says nothing about
    // the session, so it must not be assumed recoverable.
    it('fails closed on an unclassifiable non-axios error', async () => {
      arrangeSession()
      mockGet.mockRejectedValue(new TypeError('undefined is not a function'))
      render(
        <AuthProvider>
          <Probe />
        </AuthProvider>
      )
      await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
      expect(localStorage.getItem('auth_token')).toBeNull()
    })

    // The recovery this whole change exists to enable.
    it('refreshStatus reaches signed-in once the backend recovers, with no re-login', async () => {
      arrangeSession()
      mockPost.mockRejectedValue({ isAxiosError: true, code: 'ERR_NETWORK' })
      render(
        <AuthProvider>
          <RefreshProbe />
        </AuthProvider>
      )
      await waitFor(() =>
        expect(screen.getByTestId('status')).toHaveTextContent('backend-unreachable')
      )

      // The host comes back: onboarding and /me answer normally again.
      mockPost.mockResolvedValue(RESOLVED_ONBOARDING_RESPONSE)
      mockGet.mockResolvedValue({
        data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
      })
      fireEvent.click(screen.getByRole('button', { name: 'refresh' }))

      await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
      expect(mockSignOut).not.toHaveBeenCalled()
    })
  })

  it('re-syncs from an onAuthStateChange event (e.g. sign-out elsewhere)', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))

    act(() => {
      changeHandler?.('SIGNED_OUT', null)
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('sign-out clears an active child session (G1 / P6-04) alongside the guardian token', async () => {
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(getChildSession()).not.toBeNull()

    act(() => {
      changeHandler?.('SIGNED_OUT', null)
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(getChildSession()).toBeNull()
  })

  it('fails closed to signed-out when /me returns an unrecognized role', async () => {
    // The role drives ProtectedRoute's allow/deny. A value outside the closed
    // Role set must be rejected (fail closed), not cast into a Principal.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'superuser', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('keeps the latest /me result when responses arrive out of order', async () => {
    // seq 1 (from getSession) resolves AFTER seq 2 (from an auth-change event).
    // The monotonic guard must discard seq 1's stale result so seq 2 survives.
    let resolveFirst: ((value: unknown) => void) | undefined
    const firstResponse = new Promise((resolve) => {
      resolveFirst = resolve
    })
    mockGet.mockReturnValueOnce(firstResponse).mockResolvedValueOnce({
      data: { subject: 'sub-new', role: 'admin', family_id: 'fam', profile_ids: [] },
    })
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    // Let the getSession-driven sync (seq 1) start and park on firstResponse.
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))

    // Fire the newer sync (seq 2); its /me resolves immediately.
    act(() => {
      changeHandler?.('TOKEN_REFRESHED', { access_token: 'tok-2', user: { id: 'u1' } })
    })
    await waitFor(() => expect(screen.getByTestId('role')).toHaveTextContent('admin'))

    // Now let seq 1's late response land: it must be ignored, not overwrite seq 2.
    await act(async () => {
      resolveFirst?.({
        data: { subject: 'sub-old', role: 'guardian', family_id: 'fam', profile_ids: [] },
      })
      await firstResponse
    })
    expect(screen.getByTestId('role')).toHaveTextContent('admin')
    expect(screen.getByTestId('status')).toHaveTextContent('signed-in')
  })

  it('delegates signInWithOAuth to supabase', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithOAuth.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in'))
    await waitFor(() =>
      expect(mockSignInWithOAuth).toHaveBeenCalledWith({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}${GUARDIAN_LOGIN_PATH}` },
      })
    )
  })

  it('delegates signInWithPassword to supabase', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithPassword.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in password'))
    await waitFor(() =>
      expect(mockSignInWithPassword).toHaveBeenCalledWith({ email: 'a@b.com', password: 'pw' })
    )
  })

  it('rejects signInWithPassword when supabase reports an error', async () => {
    // Bad credentials resolve with { error } rather than throwing; the context
    // must rethrow so LoginPage can show a failure message instead of no-op'ing.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithPassword.mockResolvedValue({ data: {}, error: new Error('invalid login') })
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in password'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('invalid login'))
  })

  it('clears a stale authError when a new password sign-in starts', async () => {
    // Regression: a session that could not resolve a Principal leaves authError
    // set. A retry must clear it up front, or LoginPage's
    // `busy = submitting && !authError` goes false on the new attempt's first
    // render, re-enabling the button and keeping the old alert visible.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockRejectedValue(new Error('401 from backend'))
    mockSignInWithPassword.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <Probe />
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() =>
      expect(screen.getByTestId('authError')).toHaveTextContent('principal-unresolved')
    )
    fireEvent.click(screen.getByText('sign in password'))
    await waitFor(() => expect(screen.getByTestId('authError')).toHaveTextContent('none'))
  })

  it('delegates signOut to supabase', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
  })

  it("signs out only this device, never the account's other sessions", async () => {
    // #CRITICAL: security: supabase-js defaults signOut to scope 'global',
    // revoking every refresh token the account holds. Every caller here is
    // device-local by intent, and two of them (LoginPage's authorize-device,
    // ConsolePage's handoff) run on a KID's device: under the default, handing
    // the iPad to a child also signed the parent out on their own phone and
    // laptop. Assert the argument, not just the call, because the defect is
    // invisible in a mock that only records that signOut happened.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(mockSignOut).toHaveBeenCalledWith({ scope: 'local' }))
  })

  it('sign-out purges the authenticated runtime caches (SEC-F5)', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    const deleted: string[] = []
    const originalCaches = (globalThis as { caches?: unknown }).caches
    Object.defineProperty(globalThis, 'caches', {
      configurable: true,
      value: {
        delete: (name: string): Promise<boolean> => {
          deleted.push(name)
          return Promise.resolve(true)
        },
      },
    })
    try {
      render(
        <AuthProvider>
          <ActionsProbe />
        </AuthProvider>
      )
      await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
      fireEvent.click(screen.getByText('sign out'))
      await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
      await waitFor(() => expect(deleted).toContain('api-cache'))
      expect(deleted).toContain('storybook-blobs')
    } finally {
      Object.defineProperty(globalThis, 'caches', {
        configurable: true,
        value: originalCaches,
      })
    }
  })

  it('sign-out purges cached personalization values (ADR-023 P6)', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
    await waitFor(() => expect(mockClearReadingStates).toHaveBeenCalled())
    expect(mockClearPersonalizationValues).toHaveBeenCalled()
  })

  it('still purges personalization values when the reading-state purge fails, and warns', async () => {
    // The two sign-out purges are independent (different IndexedDB stores), so
    // a transient failure clearing reading states must neither skip the
    // personalization purge (the child's name at rest is the higher-stakes
    // data) nor pass silently: the rejected settlement is surfaced via
    // console.warn.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    mockClearReadingStates.mockRejectedValueOnce(new Error('transient IDB failure'))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    try {
      render(
        <AuthProvider>
          <ActionsProbe />
        </AuthProvider>
      )
      await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
      fireEvent.click(screen.getByText('sign out'))
      await waitFor(() => expect(mockClearPersonalizationValues).toHaveBeenCalled())
      await waitFor(() =>
        expect(warnSpy).toHaveBeenCalledWith(
          expect.stringContaining('reading states'),
          expect.any(Error)
        )
      )
    } finally {
      warnSpy.mockRestore()
    }
  })

  it('sign-out drops warm adult-gate state', async () => {
    // ADR-014 Phase 5: an explicit sign-out hands the device over, so a warm
    // adult gate must not survive it and greet the next sign-in already
    // unlocked.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    warmAdultGate('u1')
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)

    fireEvent.click(screen.getByText('sign out'))

    await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('clears the local credential and adult gate even when the network revoke fails', async () => {
    // #CRITICAL: security (C1): on a shared kid device the guardian bearer must
    // not survive a sign-out just because the network revoke failed. Supabase's
    // GoTrueClient._signOut removes the local session only AFTER a successful or
    // 4xx revoke, so a transport failure/5xx would otherwise strand auth_token
    // in localStorage for the useApi fallthrough to attach on a kid route.
    // AuthContext therefore clears the token (and the now-meaningless warm adult
    // gate) up front, before the revoke and independently of its outcome; the
    // revoke error still propagates to the caller.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: new Error('revoke failed') })
    warmAdultGate('u1')
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    // A bearer still in storage at sign-out time (set after mount settles so
    // the initial signed-out resolution does not clear it first).
    localStorage.setItem('auth_token', 'guardian-bearer')

    fireEvent.click(screen.getByText('sign out'))

    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('revoke failed'))
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('warms the adult gate on a genuine SIGNED_IN event', async () => {
    // ADR-014 Phase 5: the guardian just proved full credentials (password
    // submit or an OAuth redirect return), so entering the console
    // immediately after must NOT show the step-up.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(adultGateRemainingMs('u1')).toBe(0)

    act(() => {
      changeHandler?.('SIGNED_IN', { access_token: 'tok-1', user: { id: 'u1' } })
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)
  })

  it('does NOT warm the adult gate on a restored session or a silent token refresh', async () => {
    // #CRITICAL: security: only an explicit SIGNED_IN event may warm the
    // gate. Warming on the initial getSession()-driven restore (no event) or
    // on a periodic TOKEN_REFRESHED would let a merely-persisted or
    // auto-refreshing session look identical to a guardian who just typed a
    // password, defeating the step-up.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    // The session was restored via getSession(), not an explicit sign-in.
    expect(adultGateRemainingMs('u1')).toBe(0)

    act(() => {
      changeHandler?.('TOKEN_REFRESHED', { access_token: 'tok-2', user: { id: 'u1' } })
    })
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('warms the adult gate on an OAuth return leg', async () => {
    // The Google sign-in loop: supabase-js consumes the callback hash inside
    // createClient's initialize(), emitting 'SIGNED_IN' before AuthProvider
    // subscribes, so this provider is replayed 'INITIAL_SESSION' and the
    // SIGNED_IN-only warm above never fired. The guardian landed on a COLD
    // gate whose own "Continue with Google" button sent them back through
    // Google into the identical state, forever. isOAuthReturn carries the
    // fact that vanished event was needed for.
    mockIsOAuthReturn = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockOnAuthStateChange.mockImplementation(() => ({
      data: { subscription: { unsubscribe: vi.fn() } },
    }))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)
  })

  it('does NOT re-warm on a token refresh during an OAuth-return page load', async () => {
    // #CRITICAL: security: isOAuthReturn stays true for the WHOLE page load,
    // so the URL-derived arm has to be narrowed to the first resolution. Were
    // it keyed on the flag alone, every silent TOKEN_REFRESHED in this tab
    // would slide the idle TTL forward and a walked-away console would never
    // re-challenge.
    mockIsOAuthReturn = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    // Drop the landing's warm entry, so the only thing that could re-warm the
    // gate below is the refresh event itself.
    clearAdultGate()
    act(() => {
      changeHandler?.('TOKEN_REFRESHED', { access_token: 'tok-2', user: { id: 'u1' } })
    })
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('rejects signInWithOAuth when supabase reports an error', async () => {
    // supabase-js resolves with { error } instead of throwing; the context
    // must rethrow so a failed OAuth redirect is not silently swallowed.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithOAuth.mockResolvedValue({ data: {}, error: new Error('oauth unavailable') })
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('oauth unavailable'))
  })

  it('rejects signOut when supabase reports an error', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: new Error('revoke failed') })
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('revoke failed'))
  })

  it('useAuth throws when used outside an AuthProvider', () => {
    function Bare() {
      useAuth()
      return null
    }
    expect(() => render(<Bare />)).toThrow('useAuth must be used within an AuthProvider')
  })
})

describe('AuthProvider password recovery', () => {
  it('seeds recovery=false on an ordinary load', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(screen.getByTestId('recovery')).toHaveTextContent('false')
  })

  it('seeds recovery=true when the page load is a recovery-link landing', async () => {
    // supabaseClient froze isPasswordRecovery=true from the #type=recovery hash
    // before createClient stripped it; the provider must start in recovery mode
    // so LoginPage shows the set-new-password form instead of redirecting.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
  })

  it('enters recovery on a PASSWORD_RECOVERY auth event', async () => {
    // supabase-js fires PASSWORD_RECOVERY when it processes the recovery hash
    // after mount (the event can arrive slightly after the initial seed race),
    // so the provider must also flip into recovery on the event itself.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))

    act(() => {
      changeHandler?.('PASSWORD_RECOVERY', { access_token: 'tok-r', user: { id: 'u1' } })
    })

    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
  })

  it('requestPasswordReset delegates to supabase with a login-page redirect', async () => {
    // The reset email links back to the guardian login page, the only surface
    // that loads supabase-js and can process the recovery hash (same constraint
    // as the OAuth redirectTo).
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockResetPasswordForEmail.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('request reset'))
    await waitFor(() =>
      expect(mockResetPasswordForEmail).toHaveBeenCalledWith('reset@example.com', {
        redirectTo: `${window.location.origin}${GUARDIAN_LOGIN_PATH}`,
      })
    )
  })

  it('rejects requestPasswordReset when supabase reports an error', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockResetPasswordForEmail.mockResolvedValue({ data: {}, error: new Error('rate limited') })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('request reset'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('rate limited'))
  })

  it('updatePassword delegates to supabase.auth.updateUser', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockUpdateUser.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() =>
      expect(mockUpdateUser).toHaveBeenCalledWith({ password: 'new-password-123' })
    )
  })

  it('rejects updatePassword when supabase reports an error', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockUpdateUser.mockResolvedValue({ data: {}, error: new Error('weak password') })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('weak password'))
  })

  it('clears recovery after a successful password update (auto-continue)', async () => {
    // Once the new password is saved, the recovery session is a normal signed-in
    // session; clearing recovery lets LoginPage fall through to its role-based
    // redirect (the approved "auto-continue to console" behavior).
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockUpdateUser.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))
  })

  it('leaves recovery set when the password update fails', async () => {
    // A failed update must keep the user on the set-new-password form to retry,
    // not drop them into the console with the old password still active.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockUpdateUser.mockResolvedValue({ data: {}, error: new Error('weak password') })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('weak password'))
    expect(screen.getByTestId('recovery')).toHaveTextContent('true')
  })

  it('clears recovery on sign-out', async () => {
    // Abandoning recovery (signing out from the set-new-password form) must not
    // leave the provider stuck in recovery for the next session on this device.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <Probe />
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))
  })

  it('drops the rendered set-new-password form on sign-out, not just the internal recovery flag', async () => {
    // Same scenario as the test above, but asserted at the UI level LoginPage
    // actually renders, not just AuthContext's internal recovery flag.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/guardian/login']}>
          <Routes>
            <Route path="/guardian/login" element={<LoginPage />} />
            <Route path="/guardian" element={<div>console landing</div>} />
          </Routes>
        </MemoryRouter>
        <ActionsProbe />
      </AuthProvider>
    )
    expect(await screen.findByLabelText('New password')).toBeInTheDocument()
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(screen.queryByLabelText('New password')).not.toBeInTheDocument())
  })

  it('seeds recoveryError from a failed recovery-link landing', async () => {
    // Supabase's expired/already-used redirect carries #error=... with no
    // type=recovery, so isPasswordRecovery never fires; LoginPage instead
    // needs recoveryError to show an actionable message.
    mockRecoveryErrorFromUrl = {
      code: 'otp_expired',
      description: 'Email link is invalid or has expired',
    }
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() =>
      expect(screen.getByTestId('recoveryError')).toHaveTextContent('otp_expired')
    )
    expect(screen.getByTestId('recovery')).toHaveTextContent('false')
  })

  it('a second tab enters recovery when notified over the recovery broadcast channel', async () => {
    // A stale second guardian tab never sees the recovery hash or the
    // PASSWORD_RECOVERY event (both scoped to the tab that followed the
    // link); it must instead learn about the recovery landing from the
    // cross-tab broadcast supabaseClient.ts sends.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))

    const sender = new BroadcastChannel(mockRecoveryBroadcastChannelName)
    act(() => {
      sender.postMessage('recovery')
    })
    sender.close()

    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
  })
})
