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
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    // replace(), not assign(): the expired URL must not linger in history.
    expect(location.replace).toHaveBeenCalledWith(GUARDIAN_LOGIN_PATH)
    expect(location.assign).not.toHaveBeenCalled()
  })

  it('clears the token but does not navigate on a kid-path 401', async () => {
    const location = setPathname('/library/some-story')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('does not redirect loop when already on the guardian login page', async () => {
    const location = setPathname(GUARDIAN_LOGIN_PATH)
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

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
    const rejected = getResponseRejectedHandler(result.current)

    await expect(
      rejected(makeUnauthorizedError('Bearer child-token'))
    ).rejects.toBeInstanceOf(AxiosError)

    expect(getChildSession()).toBeNull()
    // The guardian's own, unrelated session must survive: only the token
    // that actually failed gets cleared.
    expect(localStorage.getItem('auth_token')).toBe('test-token')
  })

  it('does not navigate off a kid-token route when clearing the child session', async () => {
    const location = setPathname('/read/p1/story-1/2')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(
      rejected(makeUnauthorizedError('Bearer child-token'))
    ).rejects.toBeInstanceOf(AxiosError)

    expect(getChildSession()).toBeNull()
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('clears the guardian token (not the child session) when the failing request carried the guardian bearer', async () => {
    setPathname('/guardian/console')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(
      rejected(makeUnauthorizedError('Bearer test-token'))
    ).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    // An unrelated, still-valid child session must survive a guardian 401.
    expect(getChildSession()).not.toBeNull()
  })

  it('clears the guardian token when a kid-token-route request carried no bearer at all', async () => {
    setPathname('/library/p1')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    // Not a child-bearer 401 (no Authorization matched the stored child
    // token), so the child session itself is left untouched here.
    expect(getChildSession()).not.toBeNull()
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

    await expect(rejected(makeUnauthorizedError('Bearer child-token'))).rejects.toBeInstanceOf(
      AxiosError
    )

    // Child tokens are not refreshable by design (fixed TTL); the existing
    // clear-and-gate behavior must be byte-for-byte what it was pre-P6-06.
    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(getChildSession()).toBeNull()
    expect(localStorage.getItem('auth_token')).toBe('test-token')
    expect(location.replace).not.toHaveBeenCalled()
  })

  it('never attempts a refresh when the failing request carried no bearer', async () => {
    setPathname('/guardian/console')
    mockRefreshSuccess('refreshed-token')
    const { result } = renderHook(() => useApi())
    const requestSpy = vi.spyOn(result.current, 'request')
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(refreshSessionMock).not.toHaveBeenCalled()
    expect(requestSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem('auth_token')).toBeNull()
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
})

describe('useApi response interceptor pass-through', () => {
  it('returns a successful response unchanged', () => {
    const { result } = renderHook(() => useApi())
    const fulfilled = getResponseFulfilledHandler(result.current)

    const response = { status: 200, data: { ok: true } }
    expect(fulfilled(response)).toBe(response)
  })
})
