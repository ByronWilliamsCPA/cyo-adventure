import { afterEach, describe, expect, it, vi } from 'vitest'

import { logApiError } from './logApiError'

// A realistically-shaped AxiosError. axios's isAxiosError type guard only
// checks the isAxiosError flag, but a real one carries the Authorization
// bearer token on config.headers and an arbitrary backend body on
// response.data. Both must stay out of the console; this fixture makes a leak
// detectable by giving each a unique, greppable sentinel.
function axiosErrorWithSecrets() {
  return {
    isAxiosError: true,
    message: 'Request failed with status code 401',
    config: {
      url: '/v1/library/kid-profile-id',
      headers: { Authorization: 'Bearer super-secret-token' },
    },
    response: {
      status: 401,
      data: { detail: 'body-should-never-be-logged', email: 'kid@example.com' },
    },
  }
}

describe('logApiError', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('logs only the redacted { status, url } shape for an AxiosError', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    logApiError('library list failed', axiosErrorWithSecrets())
    expect(spy).toHaveBeenCalledWith('library list failed', {
      status: 401,
      url: '/v1/library/kid-profile-id',
    })
  })

  // The point of the helper: the raw AxiosError (Authorization header + response
  // body) must never reach the console. This is the regression guard the page
  // tests lacked, so a future refactor that logs `err` directly fails here.
  it('never lets the Authorization token or the response body reach the console', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    logApiError('library list failed', axiosErrorWithSecrets())
    const logged = JSON.stringify(spy.mock.calls)
    expect(logged).not.toContain('super-secret-token')
    expect(logged).not.toContain('Authorization')
    expect(logged).not.toContain('body-should-never-be-logged')
    expect(logged).not.toContain('kid@example.com')
  })

  it('logs the message for a plain Error, not the Error object', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    logApiError('rating save failed', new Error('socket hangup'))
    expect(spy).toHaveBeenCalledWith('rating save failed', 'socket hangup')
  })

  it('logs a non-Error, non-axios rejection value as-is', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    logApiError('rating save failed', 'plain string reason')
    expect(spy).toHaveBeenCalledWith('rating save failed', 'plain string reason')
  })
})
