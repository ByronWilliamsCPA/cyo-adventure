import * as Sentry from '@sentry/react'

// Breadcrumb data keys that could carry a request/response body; stripped
// defensively in scrubEvent below even though Sentry's own fetch/XHR
// breadcrumbs normally carry only body SIZES, never raw bodies.
const BODY_SHAPED_BREADCRUMB_KEYS = new Set([
  'body',
  'request_body',
  'response_body',
  'headers',
])

/**
 * Sentry error tracking for the browser app.
 *
 * A documented no-op unless `VITE_SENTRY_DSN` is set (see `.env.example`):
 * local dev and CI never set it, so `Sentry.init` is never called there, and
 * this function is safe to call unconditionally from `main.tsx` regardless
 * of environment.
 *
 * Session Replay and performance tracing (BrowserTracing) are deliberately
 * NOT enabled. This is a kids' reading app: Session Replay records DOM
 * mutations and interaction video of whoever is using the page, which is
 * exactly the kind of telemetry a children's-privacy-conscious app must not
 * collect, so it stays off unconditionally rather than gated behind a
 * sample rate. `@sentry/react`'s default integration set does not include
 * BrowserTracing or Replay unless explicitly added via `integrations:
 * [...]`; simply never adding them is what turns both off, and the
 * `tracesSampleRate`/`replays*SampleRate` values below are a second,
 * explicit belt-and-braces signal even though nothing would sample them.
 *
 * `beforeSend` (`scrubEvent`) strips anything that could still carry PII
 * past that default posture: request/response bodies and any user
 * identifier beyond a bare anonymous id.
 *
 * #CRITICAL: security: never send PII (child/guardian names, emails,
 * request or response bodies, precise identifiers) from this kids' app to a
 * third-party error tracker.
 * #VERIFY: observability.test.ts asserts scrubEvent strips email/username/
 * ip_address from `event.user` (keeping only `id`) and data/cookies/headers
 * from `event.request`, and that `initSentry()` never calls `Sentry.init`
 * without a configured DSN.
 */
export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) {
    return
  }

  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    // No BrowserTracing/Replay integrations are added; see the module
    // docstring above for why. These sample rates are 0 as a second,
    // explicit guard even though no integration exists to read them.
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    sendDefaultPii: false,
    beforeSend: scrubEvent,
  })
}

/**
 * Strip request/response bodies and any user identifier beyond a bare
 * anonymous id from an outgoing Sentry event, before it leaves the browser.
 *
 * Exported separately from `initSentry` so it can be unit tested directly
 * against representative event shapes, rather than only indirectly through
 * a mocked `Sentry.init` call.
 *
 * @param event - The event Sentry is about to send.
 * @returns The same event object, mutated in place and returned (matches
 *   `beforeSend`'s expected return shape).
 */
export function scrubEvent(event: Sentry.ErrorEvent): Sentry.ErrorEvent {
  if (event.request) {
    // Keep only the non-body fields useful for debugging (url, method,
    // query string); drop `data` (request body), `cookies`, and `headers`
    // (which can carry an Authorization bearer token or session cookie).
    const { url, method, query_string } = event.request
    event.request = { url, method, query_string }
  }

  if (event.user) {
    // `id` here is the app's own anonymous/local identifier, never a
    // guardian email or child name; everything else on `User` (email,
    // username, ip_address, geo, and any custom key) is dropped.
    const anonymousId = event.user.id
    event.user = anonymousId === undefined ? undefined : { id: anonymousId }
  }

  if (event.breadcrumbs) {
    event.breadcrumbs = event.breadcrumbs.map((crumb) => {
      if (!crumb.data) {
        return crumb
      }
      // Sentry's own fetch/XHR breadcrumbs normally carry only body SIZES,
      // not raw bodies, but this strips any body-shaped key defensively in
      // case a future integration or manual breadcrumb adds one.
      const data = crumb.data as Record<string, unknown>
      const safeData = Object.fromEntries(
        Object.entries(data).filter(
          ([key]) => !BODY_SHAPED_BREADCRUMB_KEYS.has(key)
        )
      )
      return { ...crumb, data: safeData }
    })
  }

  return event
}
