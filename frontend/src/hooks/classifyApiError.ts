import { isAxiosError } from 'axios'

/**
 * The distinct failure conditions a guardian-facing fetch can hit. Before this
 * helper, every page collapsed all of them into one boolean and one "please try
 * again" string (naive-UX report 2026-07-05, finding F1), so a permanent 403
 * (wrong role) read identically to a flaky network blip. Separating them lets a
 * page choose copy, and imply a next action, that matches the actual cause.
 */
export type ApiErrorKind = 'unauthenticated' | 'forbidden' | 'transient'

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
  transient: 'Something went wrong. Please try again.',
}

/**
 * Classify an unknown thrown value (typically an AxiosError) into one of three
 * actionable kinds with a default human message.
 *
 * Pass `overrides` to supply page-specific copy for a kind while keeping the
 * classification shared; an omitted kind falls back to its default message.
 *
 * #ASSUME: data-integrity: only 401 and 403 are distinguished. Every other HTTP
 * status, a missing response (network failure), and a timeout all map to
 * `transient`, which preserves each caller's existing "please try again"
 * behavior so no page regresses when it adopts the classifier.
 * #VERIFY: classifyApiError.test.ts covers 401 / 403 / 5xx / no-response /
 * timeout / non-axios and the override precedence.
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
  }
  return 'transient'
}
