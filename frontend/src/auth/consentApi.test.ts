import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeConsentApi } from './consentApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeConsentApi', () => {
  it('posts the location and returns the attempt view', async () => {
    const post = vi.fn().mockResolvedValue({
      data: { status: 'sent', requested_at: '2026-08-10T12:00:00Z' },
    })
    const api = makeConsentApi(fakeAxios({ post }))

    const result = await api.startKwsVerification('US')

    expect(post).toHaveBeenCalledWith('/v1/consent/kws/start', { location: 'US' })
    expect(result).toEqual({ status: 'sent', requested_at: '2026-08-10T12:00:00Z' })
  })

  it('sends no recipient of any kind', async () => {
    // #CRITICAL: security: the recipient is fixed server-side from the
    // caller's verified token, and the request body has no field for it. This
    // asserts the exact body rather than a subset, so adding an email (or any
    // other caller-chosen address field) to the payload fails here rather
    // than quietly reaching an endpoint that sits outside the approval gate.
    const post = vi.fn().mockResolvedValue({ data: {} })
    const api = makeConsentApi(fakeAxios({ post }))

    await api.startKwsVerification('GB')

    const body = post.mock.calls[0]?.[1] as Record<string, unknown>
    expect(Object.keys(body)).toEqual(['location'])
  })

  it('propagates a refusal rather than resolving', async () => {
    // The page distinguishes 409 from 429 from a real fault by status code,
    // so this adapter must not flatten a rejection into a resolved value.
    const post = vi
      .fn()
      .mockRejectedValue(Object.assign(new Error('conflict'), { response: { status: 409 } }))
    const api = makeConsentApi(fakeAxios({ post }))

    await expect(api.startKwsVerification('US')).rejects.toMatchObject({
      response: { status: 409 },
    })
  })
})
