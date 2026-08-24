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
 * is kept distinct from the residual `transient` bucket (404, timeouts, and
 * anything else unclassified) because "something went wrong on our end" is a
 * different claim than "please try again" for a client-side failure.
 *
 * `validation` (422) is opt-in, not automatic: see classifyApiError's own
 * doc comment for why.
 */
export type ApiErrorKind =
  | 'unauthenticated'
  | 'forbidden'
  | 'offline'
  | 'rateLimited'
  | 'server'
  | 'transient'
  | 'validation'

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
  server: 'Something went wrong on our end. Please try again in a moment.',
  transient: 'Something went wrong. Please try again.',
  // Unreachable by construction, and present only because ApiErrorKind is
  // exhaustive over this Record. Reaching kind 'validation' at all requires
  // the caller to have supplied `overrides.validation` (that is the opt-in
  // signal), so the `?? DEFAULT_MESSAGES.validation` arm in classifyApiError
  // can never be taken: the override is always defined by then. Kept as
  // honest copy rather than a placeholder in case the opt-in gate is ever
  // keyed off something other than the override's presence.
  validation: 'That could not be saved. Please review your entry and try again.',
}

/**
 * Classify an unknown thrown value (typically an AxiosError) into one of the
 * actionable kinds above with a default human message.
 *
 * Pass `overrides` to supply page-specific copy for a kind while keeping the
 * classification shared; an omitted kind falls back to its default message.
 *
 * #ASSUME: data-integrity: 401, 403, 429, 5xx, and offline (no response,
 * including a timeout: axios surfaces ECONNABORTED with no `response`) are
 * always distinguished. Every other HTTP status that did get a response
 * (404, ...) still maps to `transient`, preserving prior behavior for those
 * cases.
 *
 * 422 is the one exception, and it is opt-in rather than automatic (UW-C351).
 * `classifyApiError` is shared by every console surface, and a 422 from this
 * app can be either a business-rule rejection (`core.exceptions.ValidationError`,
 * with a caller-facing `message` string in the body; e.g. the provider-allowlist
 * family-lane guard, commit d1fb0b7b) or FastAPI's own request-validation
 * failure (`{"detail": [{"type", "loc", "msg"}, ...]}`, app.py's
 * `_handle_request_validation_error`). Surfacing that raw detail is an
 * improvement for a page like ProviderAllowlistPage, where a 422 is a specific,
 * actionable business rule, but would be a regression for a page that has no
 * 422-shaped affordance and is only prepared for its own `transient` copy: an
 * unreviewed switch of every 422 to a different kind and message would be a
 * blast-radius change made in this one shared helper. Requesting the kind is
 * therefore keyed off the same mechanism a caller already uses to customize
 * `transient` copy: supplying a `validation` entry in `overrides`. That string
 * doubles as the fallback message when the 422 body can't be parsed into
 * something displayable (a missing body, or a `detail` that is neither a
 * string nor a list of `{msg}` objects, so nothing here would ever render a
 * stringified object like "[object Object]").
 *
 * #VERIFY: classifyApiError.test.ts covers 401 / 403 / 429 / 5xx / no-response
 * (offline) / timeout (offline) / other-status / non-axios / the override
 * precedence / the 422 opt-in gate (no `validation` override -> stays
 * `transient`) / the `message`-string body shape / the FastAPI list-`detail`
 * shape / the string-`detail` shape / the unparseable-body fallback.
 */
export function classifyApiError(
  error: unknown,
  overrides?: Partial<Record<ApiErrorKind, string>>
): ClassifiedApiError {
  const kind = classifyKind(error, overrides?.validation !== undefined)
  if (kind === 'validation') {
    const detail = parseValidationDetail(error)
    return { kind, message: detail ?? overrides?.validation ?? DEFAULT_MESSAGES.validation }
  }
  return { kind, message: overrides?.[kind] ?? DEFAULT_MESSAGES[kind] }
}

function classifyKind(error: unknown, detectValidation: boolean): ApiErrorKind {
  if (isAxiosError(error)) {
    const status = error.response?.status
    if (status === 401) return 'unauthenticated'
    if (status === 403) return 'forbidden'
    if (status === 429) return 'rateLimited'
    if (status !== undefined && status >= 500) return 'server'
    if (detectValidation && status === 422) return 'validation'
    // No response reached the client at all: network down, DNS failure,
    // connection refused, CORS failure, or a timeout. A response that arrived
    // with an unhandled status (404, an un-opted-in 422, ...) has `status`
    // set and falls through to `transient` below instead.
    if (status === undefined) return 'offline'
  }
  return 'transient'
}

/**
 * Extract a human-readable reason from a 422 response body, or undefined if
 * none is usable.
 *
 * Handles the two 422 body shapes this backend actually produces (see the
 * #ASSUME note on classifyApiError above): a business-rule rejection's
 * `{"message": "..."}`, checked first since it is what raised this feature
 * (UW-C351), and FastAPI's own `{"detail": ...}`, which is either a string or
 * a list of `{msg}` error objects. Anything else (a missing body, a `detail`
 * that is neither) returns undefined rather than risk rendering a stringified
 * object.
 */
function parseValidationDetail(error: unknown): string | undefined {
  if (!isAxiosError(error)) return undefined
  const data: unknown = error.response?.data
  if (data === null || typeof data !== 'object') return undefined
  const body = data as Record<string, unknown>

  if (typeof body.message === 'string' && body.message.trim().length > 0) {
    return body.message
  }

  const detail: unknown = body.detail
  if (typeof detail === 'string' && detail.trim().length > 0) {
    return detail
  }
  if (Array.isArray(detail)) {
    const messages = (detail as unknown[])
      .map((item) => {
        if (item !== null && typeof item === 'object' && 'msg' in item) {
          return typeof item.msg === 'string' ? item.msg : undefined
        }
        return undefined
      })
      .filter((msg): msg is string => msg !== undefined && msg.trim().length > 0)
    if (messages.length > 0) return messages.join('; ')
  }

  return undefined
}
