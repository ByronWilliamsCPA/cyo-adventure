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

  it('still classifies a 422 as the residual transient bucket when the caller does not opt in', () => {
    // Pins the opt-in contract: classifyApiError is shared by every console
    // surface, so a 422 must keep its prior (transient) classification unless
    // the caller explicitly asks for `validation` via an override, exactly as
    // it would ask for custom `transient` copy.
    const result = classifyApiError({
      isAxiosError: true,
      response: { status: 422, data: { message: 'provider may not be enabled' } },
    })
    expect(result.kind).toBe('transient')
  })

  it('classifies a 422 as validation, surfacing the server message, when the caller opts in', () => {
    const result = classifyApiError(
      {
        isAxiosError: true,
        response: {
          status: 422,
          data: { message: "provider 'openrouter' may not be enabled on the allowlist" },
        },
      },
      { validation: 'fallback copy' }
    )
    expect(result.kind).toBe('validation')
    expect(result.message).toBe("provider 'openrouter' may not be enabled on the allowlist")
  })

  it('joins a FastAPI request-validation 422 list-shaped detail into one readable message', () => {
    const result = classifyApiError(
      {
        isAxiosError: true,
        response: {
          status: 422,
          data: {
            detail: [
              { type: 'missing', loc: ['body', 'model_id'], msg: 'Field required' },
              {
                type: 'string_type',
                loc: ['body', 'provider'],
                msg: 'Input should be a valid string',
              },
            ],
          },
        },
      },
      { validation: 'fallback copy' }
    )
    expect(result.kind).toBe('validation')
    expect(result.message).toBe('Field required; Input should be a valid string')
  })

  it('uses a string-shaped 422 detail directly', () => {
    const result = classifyApiError(
      {
        isAxiosError: true,
        response: { status: 422, data: { detail: 'not permitted' } },
      },
      { validation: 'fallback copy' }
    )
    expect(result.kind).toBe('validation')
    expect(result.message).toBe('not permitted')
  })

  it('falls back to the caller-supplied validation override when the 422 body has no usable text', () => {
    const result = classifyApiError(
      { isAxiosError: true, response: { status: 422, data: {} } },
      { validation: 'fallback copy' }
    )
    expect(result.kind).toBe('validation')
    expect(result.message).toBe('fallback copy')
  })

  it('falls back to the validation override, never "[object Object]", when detail is a non-string non-list shape', () => {
    const result = classifyApiError(
      {
        isAxiosError: true,
        response: { status: 422, data: { detail: { unexpected: 'shape' } } },
      },
      { validation: 'fallback copy' }
    )
    expect(result.kind).toBe('validation')
    expect(result.message).toBe('fallback copy')
    expect(result.message).not.toContain('[object Object]')
  })

  it('does not misclassify a no-response network failure as validation even with a validation override present', () => {
    const result = classifyApiError({ isAxiosError: true }, { validation: 'fallback copy' })
    expect(result.kind).toBe('offline')
  })
})
