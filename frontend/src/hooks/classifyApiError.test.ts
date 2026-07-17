import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'

import { classifyApiError } from './classifyApiError'

// Mirrors how the guardian component tests fake an AxiosError: a plain object
// with isAxiosError:true satisfies axios's own isAxiosError type guard.
function axiosErrorWithStatus(status: number) {
  return { isAxiosError: true, response: { status } }
}

describe('classifyApiError', () => {
  it('classifies a 401 as unauthenticated with a sign-in message', () => {
    const result = classifyApiError(axiosErrorWithStatus(401))
    expect(result.kind).toBe('unauthenticated')
    expect(result.message).toMatch(/sign in/i)
  })

  it('classifies a 403 as forbidden with a permission message', () => {
    const result = classifyApiError(axiosErrorWithStatus(403))
    expect(result.kind).toBe('forbidden')
    expect(result.message).toMatch(/permission/i)
  })

  it('classifies a 429 as rateLimited with a slow-down message', () => {
    const result = classifyApiError(axiosErrorWithStatus(429))
    expect(result.kind).toBe('rateLimited')
    expect(result.message).toMatch(/wait a moment/i)
  })

  it('classifies a 5xx as server, not the generic transient bucket', () => {
    const result = classifyApiError(axiosErrorWithStatus(503))
    expect(result.kind).toBe('server')
    expect(result.message).toMatch(/our end/i)
  })

  it('classifies an unhandled status (404) as the residual transient bucket', () => {
    expect(classifyApiError(axiosErrorWithStatus(404)).kind).toBe('transient')
  })

  it('classifies a network failure (no response at all) as offline', () => {
    const result = classifyApiError({ isAxiosError: true })
    expect(result.kind).toBe('offline')
    expect(result.message).toMatch(/offline/i)
  })

  it('classifies a timeout (ECONNABORTED, no response) as offline', () => {
    const timeout = new AxiosError('timeout of 10000ms exceeded', AxiosError.ECONNABORTED)
    expect(classifyApiError(timeout).kind).toBe('offline')
  })

  it('classifies a non-axios error as transient', () => {
    expect(classifyApiError(new Error('boom')).kind).toBe('transient')
  })

  it('gives every kind a textually distinct default message', () => {
    const messages = [
      classifyApiError(axiosErrorWithStatus(401)).message,
      classifyApiError(axiosErrorWithStatus(403)).message,
      classifyApiError(axiosErrorWithStatus(429)).message,
      classifyApiError(axiosErrorWithStatus(500)).message,
      classifyApiError({ isAxiosError: true }).message,
      classifyApiError(new Error('boom')).message,
    ]
    expect(new Set(messages).size).toBe(messages.length)
  })

  it('applies a per-kind message override', () => {
    const result = classifyApiError(axiosErrorWithStatus(403), {
      forbidden: 'Only a guardian can add child profiles.',
    })
    expect(result.kind).toBe('forbidden')
    expect(result.message).toBe('Only a guardian can add child profiles.')
  })

  it('falls back to the default message for a kind with no override', () => {
    const result = classifyApiError(axiosErrorWithStatus(500), {
      forbidden: 'custom forbidden copy',
    })
    expect(result.kind).toBe('server')
    expect(result.message).toMatch(/try again/i)
  })
})
