/**
 * The origin/prefix selection useApi() gives its axios instance: in
 * development, Vite proxies `/api` to the backend; in production, the full
 * `VITE_API_URL` is used when set, else `/api`.
 *
 * Lives in its own dependency-free module ON PURPOSE, the same pattern
 * `auth/tokenStorageKey.ts` uses for the same reason: roughly thirty existing
 * test files (`grep -rl "vi.mock('../hooks/useApi'"`) mock `../hooks/useApi`
 * with a partial object that defines only `useApi`. A caller that cannot use
 * axios, like the notification SSE stream's fetch-based reader (native
 * EventSource cannot carry a bearer header; see notificationsStream.ts),
 * needs this same base-URL logic without pulling in useApi.ts itself, or
 * every one of those thirty mocks would need `apiBaseUrl` added to stay
 * accurate (and a test that forgot would silently render a component tree
 * that throws instead of failing to compile).
 */
export function apiBaseUrl(): string {
  return import.meta.env.PROD ? import.meta.env.VITE_API_URL || '/api' : '/api'
}
