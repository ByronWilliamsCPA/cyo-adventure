import { renderHook } from '@testing-library/react'
import { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { useApi } from './useApi'

/**
 * Pulls the response interceptor's rejection handler out of an axios
 * instance so tests can exercise it directly without a real network call.
 */
function getResponseRejectedHandler(api: AxiosInstance) {
  const handlers = api.interceptors.response as unknown as {
    handlers: Array<{ rejected: (error: AxiosError) => Promise<never> } | null>
  }
  const handler = handlers.handlers[0]
  if (!handler) {
    throw new Error('Expected a registered response interceptor')
  }
  return handler.rejected
}

function makeUnauthorizedError(): AxiosError {
  return new AxiosError(
    'Unauthorized',
    'ERR_BAD_REQUEST',
    {} as InternalAxiosRequestConfig,
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

function setPathname(pathname: string) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, pathname, assign: vi.fn() },
  })
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
    setPathname('/guardian/console')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(window.location.assign).toHaveBeenCalledWith(GUARDIAN_LOGIN_PATH)
  })

  it('clears the token but does not navigate on a kid-path 401', async () => {
    setPathname('/library/some-story')
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(window.location.assign).not.toHaveBeenCalled()
  })

  it('does not redirect loop when already on the guardian login page', async () => {
    setPathname(GUARDIAN_LOGIN_PATH)
    const { result } = renderHook(() => useApi())
    const rejected = getResponseRejectedHandler(result.current)

    await expect(rejected(makeUnauthorizedError())).rejects.toBeInstanceOf(AxiosError)

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(window.location.assign).not.toHaveBeenCalled()
  })
})
