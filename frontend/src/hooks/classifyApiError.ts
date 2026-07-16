import { isAxiosError } from 'axios'

/**
 * The distinct failure conditions a guardian-facing fetch can hit. Before this
 * helper, every page collapsed all of them into one boolean and one "please try
 * again" string (naive-UX report 2026-07-05, finding F1), so a permanent 403
 * (wrong role) read identically to a flaky network blip. Separating them lets a
 * page choose copy, and imply a next action, that matches the actual cause.
 *
 * `offline` (no response reached the client at all) and `rateLimited` (429)
 * invite a different next action than a generic retry: an offline guardian
 * should not be told to "try again" as if the server is at fault, and a
 * rate-limited one should not be invited to retry immediately. `server` (5xx)
 * is kept distinct from the residual `transient` bucket (404, 422, timeouts,
 * and anything else unclassified) because "something went wrong on our end"
 * is a different claim than "please try again" for a client-side failure.
 */
export type ApiErrorKind =
  | 'unauthenticated'
  | 'forbidden'
  | 'offline'
  | 'rateLimited'
  | 'server'
  | 'transient'

export interface ClassifiedApiError {
  kind: ApiErrorKind
  message: string
}

const DEFAULT_MESSAGES: Record<ApiErrorKind, string> = {
  // 401 recovery on guardian surfaces is owned by the useApi response
  // interceptor (it clears the token and redirects to the login route), so this
  // string is only a fallback for the brief pre-navigation window; kid surfaces
  // (`/kids`, `/library/*`) deliberately supply their own ask-a-grown-up gate
  // (ProfilePickerPage's and LibraryPage's `unauthenticated`/`forbidden` states)
  // and do not route here.
  unauthenticated: 'Your session has ended. Please sign in again.',
  forbidden: 'You do not have permission to do that.',
  offline: "You're offline. Check your connection and try again.",
  rateLimited: "You're doing that a bit fast. Please wait a moment and try again.",
  server: "Something went wrong on our end. Please try again in a moment.",
  transient: 'Something went wrong. Please try again.',
}

/**
 * Classify an unknown thrown value (typically an AxiosError) into one of the
 * actionable kinds above with a default human message.
 *
 * Pass `overrides` to supply page-specific copy for a kind while keeping the
 * classification shared; an omitted kind falls back to its default message.
 *
 * #ASSUME: data-integrity: only 401, 403, offline (no response, including a
 * timeout: axios surfaces ECONNABORTED with no `response`), and 429/5xx are
 * distinguished. Every other HTTP status that did get a response (404, 422,
 * ...) still maps to `transient`, preserving prior behavior for those cases.
 * #VERIFY: classifyApiError.test.ts covers 401 / 403 / 429 / 5xx / no-response
 * (offline) / timeout (offline) / other-status / non-axios and the override
 * precedence.
 */
export function classifyApiError(
  error: unknown,
  overrides?: Partial<Record<ApiErrorKind, string>>,
): ClassifiedApiError {
  const kind = classifyKind(error)
  return { kind, message: overrides?.[kind] ?? DEFAULT_MESSAGES[kind] }
}

function classifyKind(error: unknown): ApiErrorKind {
  if (isAxiosError(error)) {
    const status = error.response?.status
    if (status === 401) return 'unauthenticated'
    if (status === 403) return 'forbidden'
    if (status === 429) return 'rateLimited'
    if (status !== undefined && status >= 500) return 'server'
    // No response reached the client at all: network down, DNS failure,
    // connection refused, CORS failure, or a timeout. A response that arrived
    // with an unhandled status (404, 422, ...) has `status` set and falls
    // through to `transient` below instead.
    if (status === undefined) return 'offline'
  }
  return 'transient'
}
