import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from 'axios'
import { useMemo } from 'react'
import {
  clearChildSession,
  getValidChildSession,
  isKidTokenRoute,
  routeProfileId,
} from '../auth/childSession'
import { clearDeviceGrant, getValidDeviceGrant, isDeviceGrantAuthRoute } from '../auth/deviceGrant'
import { TOKEN_STORAGE_KEY } from '../auth/tokenStorageKey'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { logApiError } from './logApiError'

// The two endpoints a device grant is allowed to authorize (ADR-014 Phase 3):
// listing a family's profiles and minting a child session. Every other route
// is refused server-side via an allowlist (api/deps.py); this client-side set
// only decides which OUTGOING requests PREFER the device-grant bearer, it is
// not itself a security boundary.
const DEVICE_GRANT_AUTH_URLS = new Set(['/v1/child-sessions', '/v1/profiles'])

// Configs whose request carried the child session token, tagged at request-ISSUE
// time so the response interceptor can classify a 401 by what the failing request
// actually sent, not by re-reading storage when the error is handled.
//
// #CRITICAL: security: this MUST be decided at issue time, not handling time. Two
// in-flight requests can share the same (now dead) child token; the first 401
// clears the session, so a handling-time re-read of storage would see no child
// session and misclassify the second 401 as a guardian-token failure, wrongly
// wiping the guardian's `auth_token` and signing them out cross-tab. A WeakSet
// keyed on the config object records the decision that was true when the request
// left, and lets configs be garbage-collected with their requests.
// #VERIFY: useApi.test.ts "does not sign the guardian out when a second request
// with the same dead child token 401s".
const childTokenRequests = new WeakSet<object>()

// Same issue-time tagging pattern as childTokenRequests, for requests that
// carried the device-grant bearer (ADR-014 Phase 3) instead of the guardian
// or child-session token. A device-grant 401 means the grant expired or was
// revoked; it is classified independently of the other two so clearing it
// never touches an unrelated guardian or child session.
// #VERIFY: useApi.test.ts "device-grant bearer selection" 401 cases.
const deviceGrantRequests = new WeakSet<object>()

/**
 * A request config that may carry the one-shot retry marker set by the
 * guardian 401 refresh-and-retry path (P6-06). The marker guarantees a
 * request is retried at most once: a 401 on the retry itself falls through
 * to the normal failure path instead of looping.
 */
interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  guardianRetryAttempted?: boolean
}

// #CRITICAL: external-resources: supabase.auth.refreshSession() has no
// client-side timeout. Because the in-flight promise below is module-scoped and
// shared, a single hung auth endpoint would stall EVERY guardian 401 handler
// awaiting it, indefinitely. This deadline bounds the wait: on timeout the
// refresh resolves to the failure path (null), identical to any other refresh
// failure, so the caller tears the session down instead of hanging.
// #VERIFY: useApi.test.ts "a hung refresh resolves to the failure path after the
// deadline" (fake timers).
const REFRESH_DEADLINE_MS = 10_000

// #CRITICAL: concurrency: this in-flight promise is module-scoped ON PURPOSE
// so it is shared by every axios instance useApi() creates. A page whose
// guardian token just expired typically fails several requests at once; all
// of those 401 handlers must await the SAME refreshSession() call (Supabase
// refresh tokens are rotated on use, so racing parallel refreshes can
// invalidate each other and sign the guardian out). The first 401 creates
// the promise, later concurrent 401s reuse it, and it self-clears once
// settled so a later, independent 401 can trigger a fresh refresh.
// #VERIFY: useApi.test.ts "concurrent guardian 401s share a single refresh".
let guardianRefreshInFlight: Promise<string | null> | null = null

// #EDGE: browser-compat: epoch (ms) until which refreshing is suppressed. When a
// refresh succeeds but its write-through to localStorage throws (private mode /
// quota), the fresh token cannot be persisted, so the NEXT request re-reads the
// stale token and 401s again. Without a brake every such 401 would fire another
// refreshSession(), and Supabase rotates the refresh token on each call: a storm
// of rotations. After a failed persist we open a short cooldown so at most one
// refresh runs per window; requests in the window fall through to teardown
// (login), the correct terminal state when the browser cannot hold a session.
// #VERIFY: useApi.test.ts "a persist failure opens a refresh cooldown".
let refreshCooldownUntil = 0

/**
 * Race a Supabase session refresh against {@link REFRESH_DEADLINE_MS}. Resolves
 * to the fresh access token, or null on any failure (no session, refresh token
 * expired/revoked, or the deadline elapsing first). Never rejects: a rejected
 * refreshSession() surfaces to the caller of {@link refreshGuardianToken}.
 */
async function refreshWithDeadline(
  refresh: () => Promise<{
    data: { session: { access_token: string } | null }
    error: unknown
  }>,
): Promise<string | null> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<'timeout'>((resolve) => {
    timer = setTimeout(() => resolve('timeout'), REFRESH_DEADLINE_MS)
  })
  try {
    const outcome = await Promise.race([refresh(), deadline])
    if (outcome === 'timeout') return null
    const token = outcome.data.session?.access_token ?? null
    if (outcome.error !== null || token === null) return null
    return token
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

/**
 * Refresh the guardian's Supabase session once, returning the new access
 * token, or null when the refresh fails for any reason (no session, refresh
 * token expired/revoked, Supabase unreachable, the deadline elapsing, a
 * persist-failure cooldown being in effect, or the Supabase client module
 * itself unavailable). Callers treat null as "fall through to the existing
 * 401 failure path".
 */
function refreshGuardianToken(): Promise<string | null> {
  if (Date.now() < refreshCooldownUntil) return Promise.resolve(null)
  guardianRefreshInFlight ??= (async (): Promise<string | null> => {
    try {
      // Dynamic import, not static: supabaseClient throws at import time
      // when VITE_SUPABASE_* is missing and is deliberately kept out of the
      // kid bundle (see its #CRITICAL header comment). useApi is shared by
      // the kid surface, so the module may only be pulled in at the moment
      // a guardian refresh is actually needed; on the guardian surface it
      // is already loaded and this resolves from the module cache. Callers
      // gate this on !isKidTokenRoute so the import never runs on the kid
      // surface (see the response interceptor).
      const { supabase } = await import('../auth/supabaseClient')
      const token = await refreshWithDeadline(() => supabase.auth.refreshSession())
      if (token === null) return null
      // #ASSUME: security: AuthContext's onAuthStateChange also writes this
      // key on the TOKEN_REFRESHED event this refresh emits, but that write
      // is async (it happens inside syncPrincipal, alongside a /me refetch)
      // and may land after the retry below needs the token. Writing the same
      // access token here first is an idempotent write-through, not a
      // conflicting double-write; whichever runs second stores an identical
      // value.
      // #VERIFY: useApi.test.ts "stores the refreshed token" retry cases.
      try {
        localStorage.setItem(TOKEN_STORAGE_KEY, token)
      } catch {
        // #EDGE: browser-compat: storage unavailable (private/locked-down mode
        // or quota). The retry still carries the fresh token explicitly (the
        // request interceptor honors a retry config's existing header, see its
        // guard), so THIS request recovers; but the token is not persisted, so
        // open a cooldown to stop the next 401 from starting a refresh storm.
        refreshCooldownUntil = Date.now() + REFRESH_DEADLINE_MS
        console.warn(
          'guardian token refresh could not be persisted (storage unavailable); ' +
            'suppressing further refreshes briefly',
        )
      }
      return token
    } catch (err) {
      // Expected auth failures (expired/revoked refresh token, no session) come
      // back as the `error` field handled inside refreshWithDeadline and return
      // null WITHOUT reaching here. Reaching this catch means an UNEXPECTED
      // throw: a broken dynamic import, a transport-layer throw, or an SDK bug.
      // Surface it (redacted; logApiError never logs token values) instead of
      // collapsing it into the same silent null as routine expiry, then still
      // fall through to the pre-existing 401 teardown, which is the correct
      // terminal state.
      // #VERIFY: logApiError.test.ts keeps the token-never-logged invariant green.
      logApiError('guardian token refresh failed unexpectedly', err)
      return null
    }
  })().finally(() => {
    guardianRefreshInFlight = null
  })
  return guardianRefreshInFlight
}

/**
 * Creates and returns a configured Axios instance for API calls.
 *
 * In development, requests are proxied through Vite to avoid CORS issues.
 * In production, requests go directly to the configured API URL.
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const api = useApi()
 *
 *   const fetchData = async () => {
 *     const response = await api.get('/users')
 *     return response.data
 *   }
 * }
 * ```
 */
export function useApi(config?: AxiosRequestConfig): AxiosInstance {
  const api = useMemo(() => {
    const instance = axios.create({
      // In development, Vite proxies /api to the backend
      // In production, use the full API URL
      baseURL: import.meta.env.PROD ? import.meta.env.VITE_API_URL || '/api' : '/api',
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
      ...config,
    })

    // Request interceptor for auth tokens, logging, etc.
    instance.interceptors.request.use(
      (config) => {
        // #CRITICAL: security: a retry re-dispatched by the guardian 401 handler
        // already carries a FRESH bearer set directly on this config. Do not
        // overwrite it from localStorage: if the refresh's write-through setItem
        // failed (private mode / quota), localStorage still holds the EXPIRED
        // token, and re-reading it here would re-send the stale bearer, silently
        // defeating the retry. The one-shot marker is only ever set on a config
        // the guardian 401 path already authenticated, so returning it verbatim
        // is safe.
        // #VERIFY: useApi.test.ts "retry carries the fresh token even when
        // setItem threw".
        if ((config as RetriableRequestConfig).guardianRetryAttempted === true) {
          return config
        }
        // #ASSUME: security: on a kid-token route (/library/*, /read/*; see
        // isKidTokenRoute's #ASSUME for why /kids itself is excluded), a
        // valid child session token WHOSE PROFILE MATCHES THE ROUTE takes
        // priority over the guardian bearer, and the guardian token is never
        // attached alongside it. Two edge cases both fall through to the
        // guardian-token branch below, identical to pre-G1 behavior: a
        // kid-token route reached with no child session (a fresh deep link, a
        // reload, or an expired token just cleared by getValidChildSession),
        // and a route whose :profileId differs from the stored session's
        // profile (a stale session for another child reached via a new deep
        // link). ProfilePickerPage re-mints a fresh child session on the next
        // profile pick regardless.
        // #VERIFY: useApi.test.ts "request interceptor child-token selection" cases.
        const pathname = window.location.pathname
        if (isKidTokenRoute(pathname)) {
          const childSession = getValidChildSession()
          if (childSession && routeProfileId(pathname) === childSession.profileId) {
            config.headers.Authorization = `Bearer ${childSession.token}`
            // Tag at issue time so a later 401 is classified by what THIS
            // request carried, never by re-reading storage (see childTokenRequests).
            childTokenRequests.add(config)
            return config
          }
          // #CRITICAL: security (SEC-F1/SEC-F2): a kid-token route
          // (/library/*, /read/*) must NEVER fall back to the guardian bearer.
          // A guardian signed in on a shared device would otherwise let a
          // sibling deep-link to another profile's library or reader and be
          // served the whole family scope, silently bypassing the profile PIN
          // and the child/guardian boundary. With no child session matching the
          // routed profile we attach NO credential: the request 401s and the
          // kid surface's own ask-a-grown-up gate (classifyApiError's
          // `unauthenticated` state) owns recovery, sending the child back to
          // the picker to (re-)mint a scoped session. The guardian token is
          // never a valid principal on these routes.
          // #VERIFY: useApi.test.ts "kid-token route never falls back to the
          // guardian bearer" cases.
          return config
        }
        // #ASSUME: security: on the profile picker (`/kids`), a valid device
        // grant authorizes exactly the two calls the picker needs (list
        // profiles, mint a child session) and is PREFERRED over the guardian
        // bearer so the kid flow keeps working after the guardian's Supabase
        // session has expired (ADR-014 Phase 3). A guardian testing the
        // picker inline with no device grant yet still falls through to the
        // guardian-token branch below, unchanged from pre-ADR-014 behavior.
        // #VERIFY: useApi.test.ts "device-grant bearer selection" cases.
        if (isDeviceGrantAuthRoute(pathname) && DEVICE_GRANT_AUTH_URLS.has(config.url ?? '')) {
          const deviceGrant = getValidDeviceGrant()
          if (deviceGrant) {
            config.headers.Authorization = `Bearer ${deviceGrant.token}`
            deviceGrantRequests.add(config)
            return config
          }
        }
        // Add auth token if available
        const token = localStorage.getItem(TOKEN_STORAGE_KEY)
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      // axios types this handler's `error` param as `any`; annotating it as
      // `AxiosError` (what axios actually rejects transport failures with)
      // keeps the rejection reason a real Error for prefer-promise-reject-errors
      // and makes the `.response` access below type-safe.
      (error: AxiosError) => Promise.reject(error)
    )

    // Response interceptor for error handling
    instance.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        // Handle common errors
        if (error.response?.status === 401) {
          // #CRITICAL: security: classify the 401 by what the FAILING request
          // carried, captured at issue time in childTokenRequests, not by
          // re-reading storage now (which races concurrent requests sharing a
          // dead child token) and not by the route it was issued from (a
          // kid-token route with no matching child session sends the guardian
          // token, see the request interceptor's fallback). Only the token
          // that actually failed gets cleared, so a live guardian session is
          // never torn down by a stale/expired child token, and vice versa.
          // #VERIFY: useApi.test.ts "response interceptor" child-vs-guardian
          // 401 clearing cases, incl. the concurrent-dead-child-token case.
          const usedDeviceGrant = error.config ? deviceGrantRequests.has(error.config) : false
          const usedChildToken = error.config ? childTokenRequests.has(error.config) : false
          const authHeader = error.config?.headers?.Authorization
          const carriedBearer = typeof authHeader === 'string' && authHeader.length > 0

          if (usedDeviceGrant) {
            // #ASSUME: security: the device grant expired or was revoked
            // (ADR-014 Phase 3). Clear it locally; this request's caller
            // (ProfilePickerPage) already has its own ask-a-grown-up gate
            // (classifyApiError's `unauthenticated` state) for a 401 with no
            // usable bearer, so no navigation happens here. A child on `/kids`
            // must never be bounced into the guardian login page: that would
            // read as "the app just signed me into a login screen" instead of
            // the kid-safe "ask a grown-up" copy, and a repeated 401 (e.g. two
            // in-flight requests sharing the same dead grant) must not loop.
            // #VERIFY: useApi.test.ts "clears the device grant and does not
            // navigate on a device-grant 401".
            clearDeviceGrant()
          } else if (usedChildToken) {
            // Kid paths (`/kids`, `/library/*`, `/read/*`) intentionally do
            // NOT navigate here; the profile-picker's and library page's own
            // ask-a-grown-up gate (classifyApiError's `unauthenticated`
            // state) owns kid-surface 401 recovery. Re-minting only happens
            // from a fresh pick on the picker (which needs a live guardian
            // session), never automatically from here.
            clearChildSession()
          } else if (carriedBearer) {
            // Guardian-token 401 (P6-06): before tearing the session down, try
            // ONE refresh-and-retry. The typical cause is an access token that
            // expired before supabase-js's background refresh caught it; a
            // refresh recovers that silently.
            //
            // #CRITICAL: security: this refresh+retry lives STRICTLY inside the
            // guardian branch. `usedChildToken` (the WeakSet issue-time tag) is
            // the sole discriminator: a child-token 401 took the
            // clearChildSession() branch above and can NEVER reach here, so a
            // kid-surface request can never be refreshed or retried under a
            // guardian bearer (which would escalate it to guardian privilege
            // and, via the localStorage write-through, persist that identity).
            // Child tokens are also non-refreshable by design (fixed TTL; expiry
            // means hand the device back to a grown-up).
            // #VERIFY: useApi.test.ts "two concurrent kid-route 401s sharing a
            // dead child token clear only the child session and never refresh".
            const failedConfig = error.config as RetriableRequestConfig | undefined
            // #CRITICAL: security: never run the refresh (or its dynamic import
            // of supabaseClient) from a kid-token route. supabaseClient is
            // documented "never used on the kid surface"; gating on
            // !isKidTokenRoute keeps it off /library/* and /read/* even when
            // such a route sent the guardian bearer as a fallback. Those 401s
            // fall straight to the teardown below (no redirect off a kid path).
            // #VERIFY: useApi.test.ts "does not refresh or import supabaseClient
            // on a kid-token route".
            const onKidRoute = isKidTokenRoute(window.location.pathname)
            if (
              failedConfig !== undefined &&
              !onKidRoute &&
              failedConfig.guardianRetryAttempted !== true
            ) {
              const freshToken = await refreshGuardianToken()
              if (freshToken !== null) {
                failedConfig.guardianRetryAttempted = true
                failedConfig.headers.Authorization = `Bearer ${freshToken}`
                // Re-dispatch through the instance so the request interceptor
                // runs again. The interceptor's retry guard returns the config
                // verbatim, preserving this fresh bearer even if the
                // write-through to localStorage failed.
                return instance.request(failedConfig)
              }
              // Refresh failed: fall through to the pre-existing teardown
              // below, exactly as if no retry machinery existed.
            }
            // #ASSUME: security: an expired/invalid guardian session token
            // means the guardian is no longer authenticated for guardian-only
            // routes. Kid paths intentionally do NOT navigate here either (same
            // ask-a-grown-up gate as above).
            // #VERIFY: only navigate off a guardian path, and never navigate
            // away from the login page itself (redirect-loop guard).
            localStorage.removeItem(TOKEN_STORAGE_KEY)
            const path = window.location.pathname
            if (path.startsWith('/guardian') && path !== GUARDIAN_LOGIN_PATH) {
              // Use replace(), not assign(): the expired guardian URL must not stay
              // in history, or Back would return to it, hit another 401, and bounce
              // to login again in a loop.
              window.location.replace(GUARDIAN_LOGIN_PATH)
            }
          }
          // A 401 on a request that carried NO Authorization header (an
          // unauthenticated public call, or a kid-token route with neither a
          // matching child session nor a guardian token) clears NEITHER token:
          // there is no evidence either stored session is the one that failed,
          // so tearing one down would be a guess that can sign a guardian out
          // for an unrelated anonymous 401.
        }
        return Promise.reject(error)
      }
    )

    return instance
  }, [config])

  return api
}
