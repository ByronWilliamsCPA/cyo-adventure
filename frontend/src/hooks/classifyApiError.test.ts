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

  it('classifies a 5xx as transient', () => {
    expect(classifyApiError(axiosErrorWithStatus(503)).kind).toBe('transient')
  })

  it('classifies a network failure (no response) as transient', () => {
    expect(classifyApiError({ isAxiosError: true }).kind).toBe('transient')
  })

  it('classifies a timeout (ECONNABORTED, no response) as transient', () => {
    const timeout = new AxiosError('timeout of 10000ms exceeded', AxiosError.ECONNABORTED)
    expect(classifyApiError(timeout).kind).toBe('transient')
  })

  it('classifies a non-axios error as transient', () => {
    expect(classifyApiError(new Error('boom')).kind).toBe('transient')
  })

  it('gives the three kinds textually distinct default messages', () => {
    const messages = [401, 403, 500].map(
      (status) => classifyApiError(axiosErrorWithStatus(status)).message
    )
    expect(new Set(messages).size).toBe(3)
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
    expect(result.kind).toBe('transient')
    expect(result.message).toMatch(/try again/i)
  })
})
