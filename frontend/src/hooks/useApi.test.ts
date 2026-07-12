import { renderHook } from '@testing-library/react'
import { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getChildSession, setChildSession } from '../auth/childSession'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { useApi } from './useApi'

// useApi's guardian 401 handler dynamically imports the Supabase client to
// call refreshSession() (P6-06). Mock the whole module: the real one throws
// at import time when VITE_SUPABASE_* is unset, and no test here should ever
// hit the network. vi.hoisted lets the hoisted factory close over the mock.
const { refreshSessionMock } = vi.hoisted(() => ({
  refreshSessionMock: vi.fn(),
}))

vi.mock('../auth/supabaseClient', () => ({
  supabase: { auth: { refreshSession: refreshSessionMock } },
}))

/** Config shape carrying the one-shot retry marker set by the P6-06 path. */
type RetriableRequestConfig = InternalAxiosRequestConfig & {
  guardianRetryAttempted?: boolean
}

// Default every test to a FAILING refresh so the pre-P6-06 guardian 401
// behavior (clear token, redirect off guardian paths) stays the observable
// outcome unless a test explicitly opts into a successful refresh.
beforeEach(() => {
  refreshSessionMock.mockReset()
  refreshSessionMock.mockResolvedValue({
    data: { user: null, session: null },
    error: { name: 'AuthApiError', message: 'refresh failed' },
  })
})

function mockRefreshSuccess(token = 'refreshed-token') {
  refreshSessionMock.mockResolvedValue({
    data: { user: null, session: { access_token: token } },
    error: null,
  })
}

/**
 * Pulls the response interceptor's rejection handler out of an axios
 * instance so tests can exercise it directly without a real network call.
 * The handler usually re-rejects, but the guardian refresh-and-retry path
 * can also RESOLVE with the retried request's response, hence
 * Promise<unknown> rather than Promise<never>.
 */
function getResponseRejectedHandler(api: AxiosInstance) {
  const handlers = api.interceptors.response as unknown as {
    handlers: Array<{ rejected: (error: AxiosError) => Promise<unknown> } | null>
  }
  const handler = handlers.handlers[0]
  if (!handler) {
    throw new Error('Expected a registered response interceptor')
  }
  return handler.rejected
}

/** Same extraction for the response interceptor's fulfilled (pass-through) handler. */
function getResponseFulfilledHandler(api: AxiosInstance) {
  const handlers = api.interceptors.response as unknown as {
    handlers: Array<{ fulfilled: (response: unknown) => unknown } | null>
  }
  const handler = handlers.handlers[0]
  if (!handler) {
    throw new Error('Expected a registered response interceptor')
  }
  return handler.fulfilled
}

/** And for the request interceptor's fulfilled/rejected pair. */
function getRequestHandlers(api: AxiosInstance) {
  const handlers = api.interceptors.request as unknown as {
    handlers: Array<{
      fulfilled: (config: InternalAxiosRequestConfig) => InternalAxiosRequestConfig
      rejected: (error: AxiosError) => Promise<never>
    } | null>
  }
  const handler = handlers.handlers[0]
  if (!handler) {
    throw new Error('Expected a registered request interceptor')
  }
  return handler
}

function makeRequestConfig(): InternalAxiosRequestConfig {
  // A minimal config with a real headers bag, which is all the interceptor touches.
  return { headers: {} } as unknown as InternalAxiosRequestConfig
}

/**
 * @param authorization The Authorization header the FAILING request actually
 * carried (used by the response interceptor to decide which token to clear).
 * Omitted to match a request that carried no bearer at all.
 */
function makeUnauthorizedError(authorization?: string): AxiosError {
  return new AxiosError(
    'Unauthorized',
    'ERR_BAD_REQUEST',
    {
      headers: authorization ? { Authorization: authorization } : {},
    } as InternalAxiosRequestConfig,
    undefined,
    {
      status: 401,
      statusText: 'Unauthorized',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
      data: undefined,
    }
  )
}

/**
 * Run a fresh request config through the request interceptor so it picks up
 * whatever bearer the interceptor would attach AND, for a child-token request,
 * the module-scoped tag the response interceptor classifies on. The response
 * interceptor must see the SAME config object the request went out with, which
 * is exactly what axios threads onto `error.config`; a hand-built error config
 * would never carry that tag and would misrepresent the real flow.
 */
function issueThroughInterceptor(api: AxiosInstance): InternalAxiosRequestConfig {
  const { fulfilled } = getRequestHandlers(api)
  return fulfilled(makeRequestConfig())
}

/** A 401 AxiosError whose `.config` is the exact object the request carried. */
function unauthorizedForConfig(config: InternalAxiosRequestConfig): AxiosError {
  return new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
    status: 401,
    statusText: 'Unauthorized',
    headers: {},
    config,
    data: undefined,
  })
}

// #ASSUME: external resources: jsdom does not implement real navigation, so
// window.location is replaced with a stub object per test rather than
// spied on directly (its `assign` is non-configurable in jsdom).
// #VERIFY: each test reads window.location.assign as a vi.fn() mock after
// calling setPathname, and afterEach restores the real location.
const originalLocation = window.location

// Returning the mocks directly (rather than reading them back off
// `window.location`) sidesteps @typescript-eslint/unbound-method: the DOM
// lib types `Location.replace`/`.assign` as methods that could lose `this`
// if referenced unbound, which doesn't apply to these plain vi.fn() stubs
// but the type checker cannot see that once they are read from a
// Location-typed object.
function setPathname(pathname: string) {
  const assign = vi.fn()
  const replace = vi.fn()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, pathname, assign, replace },
  })
  return { assign, replace }
}

describe('useApi 401 interceptor', () => {
  beforeEach(() => {
    localStorage.setItem('auth_token', 'test-token')
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
    localStorage.clear()
  })

  it('clears the token and redirects to the guardian login on a guardian-path 401', async () => {
    const location = setPathname('/guardian/console')
    const { result } = renderHook(() => useApi())
    // Issue through the interceptor so the request carries the guardian bearer,
    // exactly as a real guardian request does; the 401 handler clears the token
    // that actually failed rather than guessing from the route.
    const config = issueThroughInterceptor(result.current)
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    // replace(), not assign(): the expired URL must not linger in history.
    expect(location.replace).toHaveBeenCalledWith(GUARDIAN_LOGIN_PATH)
    expect(location.assign).not.toHaveBeenCalled()
  })

  it('clears the token but does not navigate on a kid-path 401', async () => {
    // No child session here, so a kid-route request falls back to the guardian
    // bearer; a 401 then means the guardian token is dead. It is cleared, but
    // there is no navigation off a kid path.
    const location = setPathname('/library/some-story')
    const { result } = renderHook(() => useApi())
    const config = issueThroughInterceptor(result.current)
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('does not redirect loop when already on the guardian login page', async () => {
    const location = setPathname(GUARDIAN_LOGIN_PATH)
    const { result } = renderHook(() => useApi())
    const config = issueThroughInterceptor(result.current)
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(location.replace).not.toHaveBeenCalled()
  })
})

describe('useApi 401 interceptor child session clearing (G1 / P6-04)', () => {
  beforeEach(() => {
    localStorage.setItem('auth_token', 'test-token')
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
    localStorage.clear()
  })

  it('clears only the child session when the failing request carried the child bearer', async () => {
    setPathname('/library/p1')
    const { result } = renderHook(() => useApi())
    // Issue the request through the interceptor so its config is tagged as a
    // child-token request; that tag is what the 401 handler classifies on.
    const config = issueThroughInterceptor(result.current)
    expect(config.headers.Authorization).toBe('Bearer child-token')
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    expect(getChildSession()).toBeNull()
    // The guardian's own, unrelated session must survive: only the token
    // that actually failed gets cleared.
    expect(localStorage.getItem('auth_token')).toBe('test-token')
  })

  it('does not navigate off a kid-token route when clearing the child session', async () => {
    const location = setPathname('/read/p1/story-1/2')
    const { result } = renderHook(() => useApi())
    const config = issueThroughInterceptor(result.current)
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    expect(getChildSession()).toBeNull()
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('clears the guardian token (not the child session) when the failing request carried the guardian bearer', async () => {
    // A guardian route never attaches the child token, so the request goes out
    // with the guardian bearer and is not tagged as a child request.
    setPathname('/guardian/console')
    const { result } = renderHook(() => useApi())
    const config = issueThroughInterceptor(result.current)
    expect(config.headers.Authorization).toBe('Bearer test-token')
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    // An unrelated, still-valid child session must survive a guardian 401.
    expect(getChildSession()).not.toBeNull()
  })

  it('clears NEITHER token when the failing request carried no Authorization header', async () => {
    // Behavior change (was: wiped the guardian token). A 401 on a request that
    // carried no bearer at all is not evidence that either stored session is
    // the one that failed (e.g. an anonymous public call), so tearing one down
    // would be a guess that could sign a guardian out for an unrelated 401.
    setPathname('/library/p1')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBe('test-token')
    expect(getChildSession()).not.toBeNull()
  })

  it('does not sign the guardian out when a second request with the same dead child token 401s', async () => {
    // Critical 1 (privilege-boundary TOCTOU) regression guard: two in-flight
    // requests share the (now dead) child token. The first 401 clears the child
    // session; the second must still be classified as a child-token failure from
    // its issue-time WeakSet tag, NOT re-derived from now-empty storage (which
    // would misread it as a guardian failure). A misclassified second 401 would
    // refreshSession() and overwrite the child bearer with a fresh GUARDIAN
    // bearer, then retry the kid-surface request under guardian identity. So the
    // second 401 must: clear only the child session, never touch auth_token,
    // never refresh, and never retry.
    const location = setPathname('/library/p1')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const first = issueThroughInterceptor(result.current)
    const second = issueThroughInterceptor(result.current)
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(unauthorizedForConfig(first))).rejects.toBeInstanceOf(AxiosError)
    expect(getChildSession()).toBeNull()

    await expect(rejected(unauthorizedForConfig(second))).rejects.toBeInstanceOf(AxiosError)
    // The guardian's own session must survive the second, now-orphaned 401.
    expect(localStorage.getItem('auth_token')).toBe('test-token')
    // No privilege escalation: neither 401 may refresh or retry under guardian.
    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(location.replace).not.toHaveBeenCalled()
  })
})

describe('useApi guardian 401 refresh-and-retry (P6-06)', () => {
  beforeEach(() => {
    localStorage.setItem('auth_token', 'test-token')
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
    localStorage.clear()
  })

  it('refreshes the session once and retries the request with the new token', async () => {
    const location = setPathname('/guardian/console')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi
      .spyOn(result.current, 'request')
      .mockResolvedValue({ status: 200, data: { ok: true } })
    const rejected = getResponseRejectedHandler(result.current)

    const response = await rejected(makeUnauthorizedError('Bearer test-token'))

    expect(refreshSessionMock).toHaveBeenCalledTimes(1)
    expect(requestSpy).toHaveBeenCalledTimes(1)
    const retriedConfig = requestSpy.mock.calls[0][0] as RetriableRequestConfig
    expect(retriedConfig.headers.Authorization).toBe('Bearer refreshed-token')
    expect(retriedConfig.guardianRetryAttempted).toBe(true)
    expect(response).toEqual({ status: 200, data: { ok: true } })
    // The interceptor stores the refreshed token so the request interceptor
    // (and AuthContext, until its own TOKEN_REFRESHED write lands) sees it.
    expect(localStorage.getItem('auth_token')).toBe('refreshed-token')
    // A recovered 401 must not tear the session down or bounce to login.
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('falls through to the existing failure path when the refresh fails', async () => {
    const location = setPathname('/guardian/console')
    // Default mock: refresh fails.
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError('Bearer test-token'))).rejects.toBeInstanceOf(
      AxiosError
    )

    expect(refreshSessionMock).toHaveBeenCalledTimes(1)
    expect(requestSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(location.replace).toHaveBeenCalledWith(GUARDIAN_LOGIN_PATH)
  })

  it('does not refresh or retry again when the retried request itself 401s', async () => {
    const location = setPathname('/guardian/console')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const rejected = getResponseRejectedHandler(result.current)

    // Simulate the 401 coming back on a request the interceptor already
    // retried once: its config carries the one-shot marker.
    const secondFailure = makeUnauthorizedError('Bearer refreshed-token')
    ;(secondFailure.config as RetriableRequestConfig).guardianRetryAttempted = true

    await expect(rejected(secondFailure)).rejects.toBeInstanceOf(AxiosError)

    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(location.replace).toHaveBeenCalledWith(GUARDIAN_LOGIN_PATH)
  })

  it('shares a single refresh across concurrent guardian 401s', async () => {
    setPathname('/guardian/console')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi
      .spyOn(result.current, 'request')
      .mockResolvedValue({ status: 200, data: { ok: true } })
    const rejected = getResponseRejectedHandler(result.current)

    // Two requests fail with 401 in the same tick, before either handler's
    // refresh resolves: both must await the SAME in-flight refresh.
    const first = rejected(makeUnauthorizedError('Bearer test-token'))
    const second = rejected(makeUnauthorizedError('Bearer test-token'))
    await Promise.all([first, second])

    expect(refreshSessionMock).toHaveBeenCalledTimes(1)
    expect(requestSpy).toHaveBeenCalledTimes(2)
    for (const call of requestSpy.mock.calls) {
      const config = call[0] as RetriableRequestConfig
      expect(config.headers.Authorization).toBe('Bearer refreshed-token')
    }
  })

  it('never attempts a refresh for a child-token 401', async () => {
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    const location = setPathname('/library/p1')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const rejected = getResponseRejectedHandler(result.current)
    // Issue through the interceptor so the config is tagged as a child-token
    // request at issue time (the WeakSet tag the 401 handler classifies on).
    // The tag, not a re-read of storage, is the sole child-vs-guardian
    // discriminator, so a child 401 can never reach the guardian refresh path.
    const config = issueThroughInterceptor(result.current)
    expect(config.headers.Authorization).toBe('Bearer child-token')

    await expect(rejected(unauthorizedForConfig(config))).rejects.toBeInstanceOf(AxiosError)

    // Child tokens are not refreshable by design (fixed TTL); the existing
    // clear-and-gate behavior must be byte-for-byte what it was pre-P6-06.
    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(getChildSession()).toBeNull()
    expect(localStorage.getItem('auth_token')).toBe('test-token')
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('never refreshes AND clears no token when the failing request carried no bearer', async () => {
    // Invariant (base redesign): a 401 on a request that carried NO Authorization
    // header is not evidence that either stored session is the one that failed
    // (e.g. an anonymous public call). So it must neither refresh (nothing to
    // refresh) nor tear down auth_token; clearing it would be a guess that could
    // sign a guardian out for an unrelated anonymous 401. An earlier revision of
    // this PR wrongly asserted the token was cleared here; that regressed the
    // base's deliberate clear-neither behavior.
    setPathname('/guardian/console')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem('auth_token')).toBe('test-token')
  })

  it('does not refresh or import the Supabase client from a kid-token route', async () => {
    // Important 6: even when a kid-token route (/library/*, /read/*) sent the
    // guardian bearer as a fallback (no child session), a 401 there must NOT
    // trigger the guardian refresh, whose dynamic import would pull the Supabase
    // client onto the kid surface (documented "never used on the kid surface").
    // The 401 falls straight to teardown, with no redirect off the kid path.
    const location = setPathname('/library/p1')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError('Bearer test-token'))).rejects.toBeInstanceOf(
      AxiosError
    )

    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('a hung refresh resolves to the failure path after the deadline', async () => {
    // Critical 4: refreshSession() has no client-side timeout and its in-flight
    // promise is module-scoped, so a hung auth endpoint would otherwise stall
    // every guardian 401 handler forever. The bounded deadline must resolve the
    // shared refresh to the failure path (null) so teardown proceeds.
    vi.useFakeTimers()
    vi.setSystemTime(0)
    try {
      const location = setPathname('/guardian/console')
      // A refresh that never settles on its own.
      refreshSessionMock.mockReturnValue(new Promise(() => {}))
      const { result } = renderHook(() => useApi())
      const requestSpy = vi.spyOn(result.current, 'request')
      const rejected = getResponseRejectedHandler(result.current)

      // Attach the rejection expectation BEFORE advancing timers so the reject
      // is handled the moment the deadline fires (no unhandled-rejection noise).
      const settled = expect(
        rejected(makeUnauthorizedError('Bearer test-token'))
      ).rejects.toBeInstanceOf(AxiosError)
      // Drive past the client-side deadline (REFRESH_DEADLINE_MS = 10s).
      await vi.advanceTimersByTimeAsync(10_000)
      await settled

      expect(requestSpy).not.toHaveBeenCalled()
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(location.replace).toHaveBeenCalledWith(GUARDIAN_LOGIN_PATH)
    } finally {
      vi.useRealTimers()
    }
  })

  it('retries with the fresh token even when the write-through to localStorage fails', async () => {
    // Critical 2: the retry re-dispatches through instance.request, which re-runs
    // the request interceptor. If the refresh's setItem write-through threw
    // (private mode / quota), localStorage still holds the EXPIRED token; the
    // retry must nonetheless carry the FRESH bearer, never the stale stored one.
    // Important 7: a persist failure also emits a console.warn breadcrumb.
    vi.useFakeTimers()
    vi.setSystemTime(0)
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    try {
      setPathname('/guardian/console')
      mockRefreshSuccess('refreshed-token')
      const { result } = renderHook(() => useApi())
      const requestSpy = vi
        .spyOn(result.current, 'request')
        .mockResolvedValue({ status: 200, data: { ok: true } })
      const rejected = getResponseRejectedHandler(result.current)
      // Storage rejects the write-through (simulate private mode / quota). Set
      // this only now so the beforeEach seed of auth_token already succeeded.
      setItemSpy.mockImplementation(() => {
        throw new Error('QuotaExceededError')
      })

      await rejected(makeUnauthorizedError('Bearer test-token'))

      expect(requestSpy).toHaveBeenCalledTimes(1)
      const retried = requestSpy.mock.calls[0][0] as RetriableRequestConfig
      expect(retried.headers.Authorization).toBe('Bearer refreshed-token')
      expect(retried.guardianRetryAttempted).toBe(true)
      // The persist failure must be surfaced as a breadcrumb, not swallowed.
      expect(warnSpy).toHaveBeenCalled()

      // Important 7: the failed persist opens a cooldown, so a second guardian
      // 401 in the window does NOT fire another (refresh-token-rotating) refresh.
      const second = rejected(makeUnauthorizedError('Bearer test-token'))
      await expect(second).rejects.toBeInstanceOf(AxiosError)
      expect(refreshSessionMock).toHaveBeenCalledTimes(1)

      // Once the cooldown elapses, refreshing resumes (this refresh succeeds and
      // its retry resolves via the request spy, so the call itself resolves).
      vi.advanceTimersByTime(11_000)
      await rejected(makeUnauthorizedError('Bearer test-token'))
      expect(refreshSessionMock).toHaveBeenCalledTimes(2)
    } finally {
      setItemSpy.mockRestore()
      warnSpy.mockRestore()
      vi.useRealTimers()
    }
  })
})

describe('useApi request interceptor child-token selection (G1 / P6-04)', () => {
  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
    localStorage.clear()
  })

  it('attaches the child session token on a library route when a valid session exists', () => {
    setPathname('/library/p1')
    setChildSession({ token: 'child-token', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p1' })
    localStorage.setItem('auth_token', 'guardian-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer child-token')
  })

  it('attaches the child session token on a reader route when a valid session exists', () => {
    setPathname('/read/p1/story-1/2')
    setChildSession({ token: 'child-token', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p1' })
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer child-token')
  })

  it('falls back to the guardian token on a kid-token route when no child session exists', () => {
    setPathname('/library/p1')
    localStorage.setItem('auth_token', 'guardian-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer guardian-token')
  })

  it('falls back to the guardian token, and clears storage, when the child session is expired', () => {
    setPathname('/library/p1')
    setChildSession({ token: 'child-token', expiresAt: '2000-01-01T00:00:00Z', profileId: 'p1' })
    localStorage.setItem('auth_token', 'guardian-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer guardian-token')
    expect(getChildSession()).toBeNull()
  })

  it('does not attach a child token whose profile does not match the routed profile', () => {
    // A still-valid session for p1 must NOT authorize a request for p2's
    // library reached via a fresh deep link; that would 403 as p1 on p2's
    // resources (a confusing wrong-gate). The interceptor falls back to the
    // guardian token on the mismatch instead.
    setPathname('/library/p2')
    setChildSession({ token: 'child-token', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p1' })
    localStorage.setItem('auth_token', 'guardian-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer guardian-token')
    // The mismatched session is left in place (not cleared): a later request
    // for p1's own library will still use it.
    expect(getChildSession()).not.toBeNull()
  })

  it('always uses the guardian token on the profile picker path, even with a valid child session', () => {
    setPathname('/kids')
    setChildSession({ token: 'child-token', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p1' })
    localStorage.setItem('auth_token', 'guardian-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer guardian-token')
  })

  it('always uses the guardian token on a guardian route, even with a valid child session', () => {
    setPathname('/guardian/console')
    setChildSession({ token: 'child-token', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p1' })
    localStorage.setItem('auth_token', 'guardian-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer guardian-token')
  })
})

describe('useApi 401 interceptor non-401 pass-through', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('re-rejects a non-401 error without touching the token or navigating', async () => {
    localStorage.setItem('auth_token', 'test-token')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    const serverError = new AxiosError(
      'Server Error',
      'ERR_BAD_RESPONSE',
      {} as InternalAxiosRequestConfig,
      undefined,
      {
        status: 500,
        statusText: 'Internal Server Error',
        headers: {},
        config: {} as InternalAxiosRequestConfig,
        data: undefined,
      }
    )
    await expect(rejected(serverError)).rejects.toBe(serverError)

    // A 500 is not a session problem: the token survives for the retry.
    expect(localStorage.getItem('auth_token')).toBe('test-token')
  })
})

describe('useApi baseURL selection', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('uses the dev proxy path when not in production', () => {
    // Vitest runs with PROD=false, matching dev: requests go through /api.
    const { result } = renderHook(() => useApi())
    expect(result.current.defaults.baseURL).toBe('/api')
  })

  it('uses VITE_API_URL directly in production builds', () => {
    vi.stubEnv('PROD', true)
    vi.stubEnv('VITE_API_URL', 'https://api.example.test')
    const { result } = renderHook(() => useApi())
    expect(result.current.defaults.baseURL).toBe('https://api.example.test')
  })

  it('falls back to /api in production when VITE_API_URL is unset', () => {
    vi.stubEnv('PROD', true)
    vi.stubEnv('VITE_API_URL', '')
    const { result } = renderHook(() => useApi())
    expect(result.current.defaults.baseURL).toBe('/api')
  })
})

describe('useApi request interceptor', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('attaches the stored auth token as a Bearer Authorization header', () => {
    localStorage.setItem('auth_token', 'stored-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBe('Bearer stored-token')
  })

  it('leaves Authorization unset when no token is stored', () => {
    localStorage.removeItem('auth_token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const config = fulfilled(makeRequestConfig())

    expect(config.headers.Authorization).toBeUndefined()
  })

  it('re-rejects a request setup error unchanged', async () => {
    const { result } = renderHook(() => useApi())
    const { rejected } = getRequestHandlers(result.current)

    const error = new AxiosError('setup failed', 'ERR_NETWORK')
    await expect(rejected(error)).rejects.toBe(error)
  })

  it('preserves a retry config fresh bearer instead of overwriting from localStorage', () => {
    // Critical 2: a retry re-dispatched by the guardian 401 path carries a FRESH
    // bearer set directly on its config and the one-shot marker. If the refresh's
    // write-through setItem failed, localStorage still holds the EXPIRED token;
    // the interceptor must return the retry config verbatim rather than re-read
    // the stale stored token, or the retry would re-send the expired bearer.
    localStorage.setItem('auth_token', 'stale-expired-token')
    const { result } = renderHook(() => useApi())
    const { fulfilled } = getRequestHandlers(result.current)

    const retryConfig = makeRequestConfig() as RetriableRequestConfig
    retryConfig.guardianRetryAttempted = true
    retryConfig.headers.Authorization = 'Bearer fresh-token'

    const config = fulfilled(retryConfig)

    expect(config.headers.Authorization).toBe('Bearer fresh-token')
  })
})

describe('useApi response interceptor pass-through', () => {
  it('returns a successful response unchanged', () => {
    const { result } = renderHook(() => useApi())
    const fulfilled = getResponseFulfilledHandler(result.current)

    const response = { status: 200, data: { ok: true } }
    expect(fulfilled(response)).toBe(response)
  })
})
