import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TOKEN_STORAGE_KEY } from '../auth/tokenStorageKey'
import type { NotificationView } from '../client'
import type { ServerSentEventsOptions } from '../client/core/serverSentEvents.gen'
import { openNotificationStream } from './notificationsStream'

// createSseClient itself (frame parsing, exponential-backoff reconnect) is
// generated code with no route-specific knowledge; it is not re-tested here.
// This suite tests only what notificationsStream.ts owns on top of it: token
// gating, URL/header construction, and the notification/keep-alive event
// filter. See NotificationBell.test.tsx's "SSE push transport" describe
// block for the consumer-facing behavior (badge refresh, poll fallback).
// vi.mock calls are hoisted above imports by Vitest's transform, so
// notificationsStream's own `import { createSseClient } from
// '../client/core/serverSentEvents.gen'` resolves to this mock regardless of
// the import order written here.
const mockCreateSseClient =
  vi.fn<(options: ServerSentEventsOptions) => { stream: AsyncGenerator<unknown> }>()
vi.mock('../client/core/serverSentEvents.gen', () => ({
  createSseClient: (options: ServerSentEventsOptions) => mockCreateSseClient(options),
}))

async function drain(stream: AsyncGenerator<unknown>): Promise<void> {
  // notificationsStream.ts's own background drain loop is fire-and-forget
  // (`void (async () => { ... })()`); awaiting the same generator here from
  // the test just lets any pending microtasks flush before assertions run.
  for await (const _item of stream) void _item
}

function emptyStream(): AsyncGenerator<unknown> {
  return (async function* () {})()
}

const NOTIFICATION_ITEM: NotificationView = {
  id: 'evt-1',
  occurred_at: '2026-07-28T12:00:00Z',
  kind: 'story_ready',
  severity: 'info',
  title: 'A story is ready',
  body: 'It has been published to your family library.',
  storybook_id: 's1',
  request_id: null,
  profile_id: null,
}

describe('openNotificationStream', () => {
  beforeEach(() => {
    localStorage.clear()
    mockCreateSseClient.mockReset()
    mockCreateSseClient.mockReturnValue({ stream: emptyStream() })
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('reports an error and opens no connection when no guardian token is stored', () => {
    const onError = vi.fn()
    const handle = openNotificationStream(undefined, { onNotification: vi.fn(), onError })

    expect(onError).toHaveBeenCalledTimes(1)
    expect(mockCreateSseClient).not.toHaveBeenCalled()

    // The returned handle must still be safely closeable even though no
    // connection was ever opened.
    expect(() => handle.close()).not.toThrow()
  })

  it('attaches the bearer token and the since filter when a token is stored', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    openNotificationStream('2026-07-28T00:00:00Z', { onNotification: vi.fn(), onError: vi.fn() })

    expect(mockCreateSseClient).toHaveBeenCalledTimes(1)
    const options = mockCreateSseClient.mock.calls[0][0]
    expect(options.headers).toEqual({ Authorization: 'Bearer guardian-jwt' })
    expect(String(options.url)).toContain('/notifications/stream')
    expect(String(options.url)).toContain('since=2026-07-28T00%3A00%3A00Z')
  })

  it('omits the since param when no prior lastSeenAt is known', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    openNotificationStream(undefined, { onNotification: vi.fn(), onError: vi.fn() })

    const options = mockCreateSseClient.mock.calls[0][0]
    expect(String(options.url)).not.toContain('since=')
  })

  it('caps retry attempts so a permanently-broken stream does not retry forever', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    openNotificationStream(undefined, { onNotification: vi.fn(), onError: vi.fn() })

    const options = mockCreateSseClient.mock.calls[0][0]
    expect(options.sseMaxRetryAttempts).toBe(5)
  })

  it('delivers a parsed notification on a real "notification" event', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    const onNotification = vi.fn()
    openNotificationStream(undefined, { onNotification, onError: vi.fn() })

    const options = mockCreateSseClient.mock.calls[0][0]
    options.onSseEvent?.({ event: 'notification', data: NOTIFICATION_ITEM })

    expect(onNotification).toHaveBeenCalledWith(NOTIFICATION_ITEM)
  })

  it('ignores keep-alive frames (no event name, no data)', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    const onNotification = vi.fn()
    openNotificationStream(undefined, { onNotification, onError: vi.fn() })

    const options = mockCreateSseClient.mock.calls[0][0]
    options.onSseEvent?.({ event: undefined, data: undefined })

    expect(onNotification).not.toHaveBeenCalled()
  })

  it('forwards createSseClient connection errors to onError', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    const onError = vi.fn()
    openNotificationStream(undefined, { onNotification: vi.fn(), onError })

    const options = mockCreateSseClient.mock.calls[0][0]
    const failure = new Error('network error')
    options.onSseError?.(failure)

    expect(onError).toHaveBeenCalledWith(failure)
  })

  it('close() aborts the underlying connection', async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
    const stream = emptyStream()
    mockCreateSseClient.mockReturnValueOnce({ stream })
    const handle = openNotificationStream(undefined, { onNotification: vi.fn(), onError: vi.fn() })

    const options = mockCreateSseClient.mock.calls[0][0]
    const signal = options.signal as AbortSignal
    expect(signal.aborted).toBe(false)
    handle.close()
    expect(signal.aborted).toBe(true)

    await drain(stream)
  })
})
