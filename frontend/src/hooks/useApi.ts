import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios'
import { useMemo } from 'react'
import { clearChildSession, getChildSession, getValidChildSession, isKidTokenRoute } from '../auth/childSession'
import { GUARDIAN_LOGIN_PATH } from '../routes'

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
      (error: AxiosError) => {
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
