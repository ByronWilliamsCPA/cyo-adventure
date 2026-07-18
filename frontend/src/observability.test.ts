import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock @sentry/react before importing observability.ts, since observability.ts
// imports it at module top-level; vi.mock is hoisted above imports by vitest
// so this ordering is safe.
vi.mock('@sentry/react', () => ({
  init: vi.fn(),
}))

import * as Sentry from '@sentry/react'

import { initSentry, scrubEvent } from './observability'

describe('initSentry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('does not call Sentry.init when VITE_SENTRY_DSN is unset', () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')

    initSentry()

    expect(Sentry.init).not.toHaveBeenCalled()
  })

  it('calls Sentry.init with the configured DSN when VITE_SENTRY_DSN is set', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')

    initSentry()

    expect(Sentry.init).toHaveBeenCalledTimes(1)
    const options = vi.mocked(Sentry.init).mock.calls[0][0]
    expect(options.dsn).toBe('https://examplePublicKey@o0.ingest.sentry.io/0')
  })

  it('sets sendDefaultPii to false', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')

    initSentry()

    const options = vi.mocked(Sentry.init).mock.calls[0][0]
    expect(options.sendDefaultPii).toBe(false)
  })

  it('disables session replay sampling', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')

    initSentry()

    const options = vi.mocked(Sentry.init).mock.calls[0][0]
    expect(options.replaysSessionSampleRate).toBe(0)
    expect(options.replaysOnErrorSampleRate).toBe(0)
  })

  it('disables performance trace sampling', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')

    initSentry()

    const options = vi.mocked(Sentry.init).mock.calls[0][0]
    expect(options.tracesSampleRate).toBe(0)
  })

  it('wires scrubEvent as beforeSend', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')

    initSentry()

    const options = vi.mocked(Sentry.init).mock.calls[0][0]
    expect(options.beforeSend).toBe(scrubEvent)
  })

  it('passes environment from import.meta.env.MODE', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')

    initSentry()

    const options = vi.mocked(Sentry.init).mock.calls[0][0]
    expect(options.environment).toBe(import.meta.env.MODE)
  })
})

describe('scrubEvent', () => {
  it('strips request body, cookies, and headers, keeping url/method/query_string', () => {
    const event = {
      request: {
        url: '/v1/library/kid-profile-id',
        method: 'GET',
        query_string: 'foo=bar',
        data: { pin: '1234' },
        cookies: { session: 'super-secret-session' },
        headers: { Authorization: 'Bearer super-secret-token' },
      },
    } as unknown as Sentry.ErrorEvent

    const scrubbed = scrubEvent(event)

    expect(scrubbed.request).toEqual({
      url: '/v1/library/kid-profile-id',
      method: 'GET',
      query_string: 'foo=bar',
    })
    const serialized = JSON.stringify(scrubbed)
    expect(serialized).not.toContain('super-secret-token')
    expect(serialized).not.toContain('super-secret-session')
    expect(serialized).not.toContain('1234')
  })

  it('reduces a user object to a bare anonymous id', () => {
    const event = {
      user: {
        id: 'anon-device-abc123',
        email: 'guardian@example.com',
        username: 'guardian_jane',
        ip_address: '203.0.113.5',
      },
    } as unknown as Sentry.ErrorEvent

    const scrubbed = scrubEvent(event)

    expect(scrubbed.user).toEqual({ id: 'anon-device-abc123' })
    const serialized = JSON.stringify(scrubbed)
    expect(serialized).not.toContain('guardian@example.com')
    expect(serialized).not.toContain('guardian_jane')
    expect(serialized).not.toContain('203.0.113.5')
  })

  it('drops the user entirely when it has no id', () => {
    const event = {
      user: { email: 'guardian@example.com' },
    } as unknown as Sentry.ErrorEvent

    const scrubbed = scrubEvent(event)

    expect(scrubbed.user).toBeUndefined()
  })

  it('strips body-shaped keys from breadcrumb data while keeping the rest', () => {
    const event = {
      breadcrumbs: [
        {
          category: 'fetch',
          data: {
            method: 'POST',
            url: '/v1/story_requests',
            status_code: 200,
            body: { text: 'a private story request' },
            request_body: { text: 'a private story request' },
            response_body: { id: '123' },
            headers: { Authorization: 'Bearer super-secret-token' },
          },
        },
      ],
    } as unknown as Sentry.ErrorEvent

    const scrubbed = scrubEvent(event)

    expect(scrubbed.breadcrumbs?.[0].data).toEqual({
      method: 'POST',
      url: '/v1/story_requests',
      status_code: 200,
    })
    const serialized = JSON.stringify(scrubbed)
    expect(serialized).not.toContain('a private story request')
    expect(serialized).not.toContain('super-secret-token')
  })

  it('passes through breadcrumbs with no data untouched', () => {
    const event = {
      breadcrumbs: [{ category: 'ui.click', message: 'clicked start' }],
    } as unknown as Sentry.ErrorEvent

    const scrubbed = scrubEvent(event)

    expect(scrubbed.breadcrumbs).toEqual([
      { category: 'ui.click', message: 'clicked start' },
    ])
  })

  it('is a no-op on an event with no request, user, or breadcrumbs', () => {
    const event = { message: 'plain error', level: 'error' } as unknown as Sentry.ErrorEvent

    const scrubbed = scrubEvent(event)

    expect(scrubbed).toEqual(event)
  })
})
