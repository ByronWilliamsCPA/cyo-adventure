import { isAxiosError } from 'axios'

/**
 * Log an API failure as a redacted, console-safe shape, never the raw thrown
 * value. A raw AxiosError carries `config.headers.Authorization` (the guardian
 * bearer token) and `response.data` (an arbitrary backend body); neither should
 * reach the browser console or any log-collection tooling. This helper is the
 * single redaction point for kid-surface fetch and rating failures, so the
 * invariant "no auth material in the console" lives in one place a test can pin.
 *
 * For an AxiosError it logs only `{ status, url }`: the HTTP status and the
 * request path, both non-sensitive and useful for diagnosing a failure. The
 * response body is deliberately omitted. For a plain Error it logs the message;
 * for any other thrown value it logs the value as-is (a non-axios throw carries
 * no auth material).
 *
 * #ASSUME: security: `err.config?.url` is a bare request path (e.g.
 * `/v1/library/{profileId}`) that carries no credential; only `.headers`
 * carries the Authorization token, and this helper never reads `.headers`.
 * #VERIFY: logApiError.test.ts asserts a bearer token placed on
 * `config.headers.Authorization` never appears in the logged output.
 */
export function logApiError(label: string, err: unknown): void {
  if (isAxiosError(err)) {
    console.error(label, { status: err.response?.status, url: err.config?.url })
    return
  }
  console.error(label, err instanceof Error ? err.message : err)
}
