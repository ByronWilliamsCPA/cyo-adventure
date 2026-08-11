import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeConsentApi } from './consentApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeConsentApi', () => {
  it('posts the location and returns the attempt view', async () => {
    // The fixture is the WHOLE wire shape, all three required fields of
    // KwsVerificationStartView, not the two this app happens to read today.
    // A fixture that omits `attempt_id` asserts a response the server cannot
    // send, so it would pass just as happily against an adapter that dropped
    // the field. Nothing type-checks this mock into agreement with the
    // generated type: `vi.fn()` returns `any`, so the fidelity has to be
    // maintained here deliberately.
    const view = {
      attempt_id: '6f1d2c7e-0b6a-4a1e-9f3c-2f7f1a8d9e40',
      status: 'sent',
      requested_at: '2026-08-10T12:00:00Z',
    }
    const post = vi.fn().mockResolvedValue({ data: view })
    const api = makeConsentApi(fakeAxios({ post }))

    const result = await api.startKwsVerification('US')

    expect(post).toHaveBeenCalledWith('/v1/consent/kws/start', { location: 'US' })
    expect(result).toEqual(view)
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
