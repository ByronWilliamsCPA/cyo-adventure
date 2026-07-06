import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'
import { useMemo } from 'react'
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
        // Add auth token if available
        const token = localStorage.getItem('auth_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // Response interceptor for error handling
    instance.interceptors.response.use(
      (response) => response,
      (error) => {
        // Handle common errors
        if (error.response?.status === 401) {
          // #ASSUME: security: an expired/invalid session token means the
          // guardian is no longer authenticated for guardian-only routes.
          // Kid paths (`/`, `/library/*`) intentionally do NOT navigate here;
          // the profile-picker's own error UI owns kid-surface 401 recovery.
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
        return Promise.reject(error)
      }
    )

    return instance
  }, [config])

  return api
}

/**
 * Standalone API client for use outside React components.
 * Prefer useApi() hook inside components for proper lifecycle management.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})
