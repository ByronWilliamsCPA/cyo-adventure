import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from 'axios'
import { useMemo } from 'react'
import { clearChildSession, getChildSession, getValidChildSession, isKidTokenRoute } from '../auth/childSession'
import { GUARDIAN_LOGIN_PATH } from '../routes'

/**
 * A request config that may carry the one-shot retry marker set by the
 * guardian 401 refresh-and-retry path (P6-06). The marker guarantees a
 * request is retried at most once: a 401 on the retry itself falls through
 * to the normal failure path instead of looping.
 */
interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  guardianRetryAttempted?: boolean
}

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

/**
 * Refresh the guardian's Supabase session once, returning the new access
 * token, or null when the refresh fails for any reason (no session, refresh
 * token expired/revoked, Supabase unreachable, or the Supabase client module
 * itself unavailable). Callers treat null as "fall through to the existing
 * 401 failure path".
 */
function refreshGuardianToken(): Promise<string | null> {
  guardianRefreshInFlight ??= (async (): Promise<string | null> => {
    try {
      // Dynamic import, not static: supabaseClient throws at import time
      // when VITE_SUPABASE_* is missing and is deliberately kept out of the
      // kid bundle (see its #CRITICAL header comment). useApi is shared by
      // the kid surface, so the module may only be pulled in at the moment
      // a guardian refresh is actually needed; on the guardian surface it
      // is already loaded and this resolves from the module cache.
      const { supabase } = await import('../auth/supabaseClient')
      const { data, error } = await supabase.auth.refreshSession()
      const token = data.session?.access_token ?? null
      if (error !== null || token === null) return null
      // #ASSUME: security: AuthContext's onAuthStateChange also writes this
      // key on the TOKEN_REFRESHED event this refresh emits, but that write
      // is async (it happens inside syncPrincipal, alongside a /me refetch)
      // and may land after the retry below needs the token. Writing the same
      // access token here first is an idempotent write-through, not a
      // conflicting double-write; whichever runs second stores an identical
      // value.
      // #VERIFY: useApi.test.ts "stores the refreshed token" retry cases.
      try {
        localStorage.setItem('auth_token', token)
      } catch {
        // #EDGE: browser-compat: storage unavailable (private/locked-down
        // mode); the retry still carries the fresh token explicitly, and
        // AuthContext's own setItem attempt owns any user-facing fallout.
      }
      return token
    } catch {
      // A failed refresh is not an error to surface from here: the caller
      // falls through to the pre-existing 401 handling (clear + redirect on
      // guardian paths), which is the correct terminal state.
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
        // #ASSUME: security: on a kid-token route (/library/*, /read/*; see
        // isKidTokenRoute's #ASSUME for why /kids itself is excluded), a
        // valid child session token takes priority over the guardian bearer
        // and the guardian token is never attached alongside it. The edge
        // case -- a kid-token route reached with no child session (a fresh
        // deep link, a reload, or an expired token just cleared by
        // getValidChildSession) -- falls through to the guardian-token
        // branch below, identical to pre-G1 behavior; ProfilePickerPage
        // re-mints a fresh child session on the next profile pick regardless.
        // #VERIFY: useApi.test.ts "request interceptor" child-token-selection cases.
        if (isKidTokenRoute(window.location.pathname)) {
          const childSession = getValidChildSession()
          if (childSession) {
            config.headers.Authorization = `Bearer ${childSession.token}`
            return config
          }
        }
        // Add auth token if available
        const token = localStorage.getItem('auth_token')
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
          // #CRITICAL: security: determine which bearer the FAILING request
          // actually carried (by comparing the request's Authorization header
          // to the stored child token), not which route it was issued from:
          // a kid-token route with no child session still sends the guardian
          // token (see the request interceptor's fallback), and that 401
          // means the guardian's own session is dead, not the child's. Only
          // the token that actually failed gets cleared, so a live guardian
          // session is never torn down by a stale/expired child token, and
          // vice versa.
          // #VERIFY: useApi.test.ts "response interceptor" child-vs-guardian
          // 401 clearing cases.
          const childSession = getChildSession()
          const authHeader = error.config?.headers?.Authorization
          const usedChildToken =
            childSession !== null && authHeader === `Bearer ${childSession.token}`

          if (usedChildToken) {
            // Kid paths (`/kids`, `/library/*`, `/read/*`) intentionally do
            // NOT navigate here; the profile-picker's and library page's own
            // ask-a-grown-up gate (classifyApiError's `unauthenticated`
            // state) owns kid-surface 401 recovery. Re-minting only happens
            // from a fresh pick on the picker (which needs a live guardian
            // session), never automatically from here.
            clearChildSession()
          } else {
            // Guardian-token 401 (P6-06): before tearing the session down,
            // try ONE refresh-and-retry. The typical cause is an access
            // token that expired before supabase-js's background refresh
            // caught it; a refresh recovers that silently. Only requests
            // that actually carried a bearer qualify (a 401 on an
            // unauthenticated request has nothing to refresh), and only if
            // this request has not already been retried (loop guard). Child
            // tokens are handled above and are never refreshed: they are
            // not refreshable by design (fixed TTL; expiry means hand the
            // device back to a grown-up).
            const failedConfig = error.config as RetriableRequestConfig | undefined
            const authHeaderValue = typeof authHeader === 'string' ? authHeader : null
            const carriedBearer =
              authHeaderValue !== null && authHeaderValue.startsWith('Bearer ')
            if (
              failedConfig !== undefined &&
              carriedBearer &&
              failedConfig.guardianRetryAttempted !== true
            ) {
              const freshToken = await refreshGuardianToken()
              if (freshToken !== null) {
                failedConfig.guardianRetryAttempted = true
                failedConfig.headers.Authorization = `Bearer ${freshToken}`
                // Re-dispatch through the instance so the request
                // interceptor runs again; it re-reads localStorage (already
                // holding the fresh token) and preserves the child-vs-
                // guardian selection rules for the route.
                return instance.request(failedConfig)
              }
              // Refresh failed: fall through to the pre-existing teardown
              // below, exactly as if no retry machinery existed.
            }
            // #ASSUME: security: an expired/invalid guardian session token
            // means the guardian is no longer authenticated for
            // guardian-only routes. Kid paths intentionally do NOT navigate
            // here either (same ask-a-grown-up gate as above).
            // #VERIFY: only navigate off a guardian path, and never navigate
            // away from the login page itself (redirect-loop guard).
            localStorage.removeItem('auth_token')
            const path = window.location.pathname
            if (path.startsWith('/guardian') && path !== GUARDIAN_LOGIN_PATH) {
              // Use replace(), not assign(): the expired guardian URL must not stay
              // in history, or Back would return to it, hit another 401, and bounce
              // to login again in a loop.
              window.location.replace(GUARDIAN_LOGIN_PATH)
            }
          }
        }
        return Promise.reject(error)
      }
    )

    return instance
  }, [config])

  return api
}
