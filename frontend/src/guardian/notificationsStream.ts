/**
 * Real-time push transport for the guardian notification bell (register
 * G10/S9): an authenticated SSE connection to GET /v1/notifications/stream
 * (api/notifications.py::stream_notifications). Layered ADDITIVELY on top
 * of NotificationBell.tsx's existing 30s poll; never replaces it. A guardian
 * whose stream never connects (an unreachable backend, a proxy that blocks
 * SSE, an expired token) still gets every notification, just on the poll's
 * cadence instead of near-real-time.
 *
 * Reuses createSseClient (src/client/core/serverSentEvents.gen.ts), the
 * generic fetch-based SSE reader @hey-api/openapi-ts generates into every
 * project's committed client (it does not depend on any one route's
 * generated types; see client.gen.ts's `sse` methods). It already owns
 * frame parsing, malformed-frame tolerance, and exponential-backoff
 * reconnect with a retry cap, so this module owns only what generated code
 * cannot: attaching the guardian bearer token (native EventSource cannot
 * set a custom Authorization header, which is why this endpoint is SSE
 * consumed via fetch rather than EventSource in the first place; see
 * api/notifications.py's module docstring for why it is SSE and not
 * WebSocket at all) and building the same /api-prefixed URL useApi.ts's
 * axios instance uses.
 */

import { TOKEN_STORAGE_KEY } from '../auth/tokenStorageKey'
import type { NotificationView } from '../client'
import { createSseClient } from '../client/core/serverSentEvents.gen'
import { apiBaseUrl } from '../hooks/apiBaseUrl'

const STREAM_PATH = '/v1/notifications/stream'

// #ASSUME: external-resources: a stream this browser/network cannot use at
// all (a proxy that blocks SSE, an unreachable backend, a token the server
// keeps rejecting) must not retry forever. createSseClient's own
// exponential backoff (default 3s, doubling, capped at 30s) already spaces
// attempts out; this caps the COUNT on top of that, after which
// createSseClient's generator simply ends and this module stops delivering
// callbacks for the rest of that connection's lifetime -- the caller's 30s
// poll (never removed, see NotificationBell.tsx) is unaffected either way.
// #VERIFY: notificationsStream.test.ts "gives up after the retry budget is
// exhausted".
const SSE_MAX_RETRY_ATTEMPTS = 5

export interface NotificationStreamHandlers {
  /** Fired once per pushed `event: notification` frame, parsed and ready to use. */
  onNotification(item: NotificationView): void
  /**
   * Fired on every failed or dropped connection attempt (network error, a
   * non-2xx response, or a mid-stream read failure). createSseClient itself
   * decides whether to retry; this is advisory only (log it, mark the
   * transport degraded), never a signal to reconnect manually -- doing so
   * would race createSseClient's own retry loop.
   */
  onError(error: unknown): void
}

export interface NotificationStreamHandle {
  /** Aborts the underlying connection and any pending scheduled retry. */
  close(): void
}

/**
 * Open the guardian's SSE notification stream. Returns a handle whose
 * close() must be called on unmount; a missing bearer token opens no
 * network connection at all and reports it through `onError` the same way
 * a rejected connection would, so callers have one failure path to handle.
 */
export function openNotificationStream(
  since: string | undefined,
  handlers: NotificationStreamHandlers
): NotificationStreamHandle {
  const controller = new AbortController()

  // #CRITICAL: security: no stored guardian bearer means there is nothing
  // to authenticate the stream with. This must never fall back to an
  // unauthenticated request: the endpoint pushes safety-sensitive,
  // child-naming text (see api/notifications.py's guardian-only docstring),
  // so "no token" is treated as a connection failure, not "connect anyway".
  // #VERIFY: notificationsStream.test.ts "reports an error and opens no
  // connection when no guardian token is stored".
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token === null) {
    handlers.onError(new Error('no guardian token available'))
    return { close: () => controller.abort() }
  }

  const url = new URL(`${apiBaseUrl()}${STREAM_PATH}`, window.location.origin)
  if (since !== undefined) url.searchParams.set('since', since)

  const { stream } = createSseClient({
    url: url.toString(),
    signal: controller.signal,
    headers: { Authorization: `Bearer ${token}` },
    sseMaxRetryAttempts: SSE_MAX_RETRY_ATTEMPTS,
    onSseError: (error) => handlers.onError(error),
    onSseEvent: (event) => {
      // The server's keep-alive frame (": keep-alive\n\n") is a bare SSE
      // comment with no `event:`/`data:` field; createSseClient still
      // invokes onSseEvent for it (with event.event and event.data both
      // undefined), so this checks the event name explicitly rather than
      // treating every callback as a real notification.
      // #ASSUME: data-integrity: createSseClient's generic default types
      // `event.data` as an untyped JSON.parse result, not NotificationView
      // (the generated core module has no route-specific knowledge); a
      // trusted cast to the backend's own committed contract type is the
      // same trust level notificationsApi.ts already applies to the poll
      // response body, gated on the frame actually being a `notification`
      // event with a non-null parsed payload.
      // #VERIFY: notificationsStream.test.ts "ignores keep-alive frames";
      // "delivers a parsed notification on a real event".
      if (event.event === 'notification' && event.data !== undefined && event.data !== null) {
        handlers.onNotification(event.data as NotificationView)
      }
    },
  })

  // createSseClient's `stream` is an async generator; onSseEvent above is
  // where this module actually consumes each frame, but per normal
  // generator semantics nothing in its body runs until it is iterated.
  // Drain it in the background purely to pump that side effect -- callers
  // interact with this module only through `handlers` and the returned
  // handle, never through the generator's own yielded values (whose
  // element type is awkward for a flat object payload like
  // NotificationView; see serverSentEvents.gen.ts's ServerSentEventsResult).
  void (async () => {
    try {
      for await (const _item of stream) {
        // Consumption only; onSseEvent already delivered the item above.
        void _item
      }
    } catch {
      // #EDGE: external-resources: createSseClient's generator does not
      // currently throw past its own internal try/catch (every failure path
      // reports through onSseError and either retries or returns), so this
      // is defensive against a future change to that generated file, not a
      // path exercised today.
    }
  })()

  return {
    close(): void {
      controller.abort()
    },
  }
}
