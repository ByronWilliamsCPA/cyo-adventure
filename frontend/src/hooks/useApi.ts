import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios'
import { useMemo } from 'react'
import {
  clearChildSession,
  getValidChildSession,
  isKidTokenRoute,
  routeProfileId,
} from '../auth/childSession'
import { GUARDIAN_LOGIN_PATH } from '../routes'

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
      (error: AxiosError) => {
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
          const usedChildToken = error.config ? childTokenRequests.has(error.config) : false
          const authHeader = error.config?.headers?.Authorization
          const carriedBearer = typeof authHeader === 'string' && authHeader.length > 0

          if (usedChildToken) {
            // Kid paths (`/kids`, `/library/*`, `/read/*`) intentionally do
            // NOT navigate here; the profile-picker's and library page's own
            // ask-a-grown-up gate (classifyApiError's `unauthenticated`
            // state) owns kid-surface 401 recovery. Re-minting only happens
            // from a fresh pick on the picker (which needs a live guardian
            // session), never automatically from here.
            clearChildSession()
          } else if (carriedBearer) {
            // #ASSUME: security: the failing request carried the guardian
            // bearer, so an expired/invalid guardian session token means the
            // guardian is no longer authenticated for guardian-only routes.
            // Kid paths intentionally do NOT navigate here either (same
            // ask-a-grown-up gate as above).
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
