/**
 * Client-side storage and route classification for guardian-minted child
 * session tokens (G1 / P6-04).
 *
 * A guardian (or admin) mints a short-lived, backend-signed bearer for one
 * child profile via `POST /v1/child-sessions` (see
 * `src/cyo_adventure/core/child_session.py` for the server-side trust model:
 * HS256, a distinct issuer/audience from the guardian's Supabase JWT, a
 * default 12h TTL, and no refresh). `ProfilePickerPage` mints and stores one
 * of these after a profile is picked; `useApi`'s request/response
 * interceptors are the single place that reads this module to decide which
 * bearer (child vs. guardian) a given request should carry.
 */

// A single JSON-blob key, not three parallel keys. Writing three keys
// non-atomically meant a mid-sequence throw (quota, a locked-down browser
// evicting between calls) could leave a mixed triple: token present, profileId
// stale from a previous session, which getChildSession would accept as a valid
// session for the WRONG profile. One setItem/removeItem makes a stored session
// all-or-nothing.
// deepcode ignore HardcodedNonCryptoSecret: this is a localStorage key name,
// not a credential; see the design comment above for the atomic JSON-blob
// rationale.
const SESSION_KEY = 'child_session'

// The pre-blob triple keys. No longer read (a stale triple from before this
// change is treated as "no session"), but still removed on clear so an old
// triple can never linger alongside the new blob.
const LEGACY_KEYS = [
  'child_session_token',
  'child_session_expires_at',
  'child_session_profile_id',
] as const

export interface ChildSession {
  token: string
  /** ISO 8601 timestamp; the server's `expires_at` from `ChildSessionView`. */
  expiresAt: string
  profileId: string
}

function isChildSession(value: unknown): value is ChildSession {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.token === 'string' &&
    typeof candidate.expiresAt === 'string' &&
    typeof candidate.profileId === 'string'
  )
}

/**
 * Persist a freshly minted child session (called from ProfilePickerPage
 * after a successful `POST /v1/child-sessions`).
 *
 * #EDGE: browser-compat: localStorage.setItem throws in private/locked-down
 * browser modes. The mint already succeeded server-side regardless, so a
 * storage failure here just means the next kid-token-route request finds no
 * child session and falls back to the guardian token (if any), same as a
 * fresh deep link; it must not throw out of the picker's click handler. The
 * single-key write also means a throw leaves NO partial session behind.
 * #VERIFY: childSession.test.ts "storage failure on write is swallowed".
 */
export function setChildSession(session: ChildSession): void {
  try {
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        token: session.token,
        expiresAt: session.expiresAt,
        profileId: session.profileId,
      })
    )
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing more to do here.
  }
}

/** Clear a stored child session: on 401, on client-detected expiry, or on guardian sign-out. */
export function clearChildSession(): void {
  try {
    localStorage.removeItem(SESSION_KEY)
    // Also drop any pre-blob triple so a legacy write can never be revived.
    for (const key of LEGACY_KEYS) {
      localStorage.removeItem(key)
    }
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing to clean up.
  }
}

/**
 * Read the stored child session, if a complete and well-formed one is present.
 * Does not check expiry; request-time callers should use `getValidChildSession`
 * instead so an expired token is never attached to a request.
 */
export function getChildSession(): ChildSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    return isChildSession(parsed) ? parsed : null
  } catch {
    // #EDGE: browser-compat: storage unavailable, or a corrupt/partial blob
    // that failed to parse; either way treat it as no session.
    return null
  }
}

/**
 * #CRITICAL: timing dependencies: this is a CLIENT-SIDE pre-check only. The
 * backend independently verifies the token's `exp` claim on every request
 * (`core/child_session.py::verify_child_session_token`); a clock-skewed
 * client could still attach a token the server considers expired (handled by
 * useApi's 401 branch clearing the session) or briefly withhold one it
 * considers still valid (handled by the kid-token-route fallback to the
 * guardian token, if any). This check exists only so an OBVIOUSLY expired
 * token is never attached in the first place.
 * #VERIFY: childSession.test.ts covers before/at/after the expiry boundary.
 */
export function isExpired(expiresAt: string, now: Date = new Date()): boolean {
  const parsed = Date.parse(expiresAt)
  if (Number.isNaN(parsed)) return true
  return parsed <= now.getTime()
}

/**
 * Return the stored child session only if present and not, per the client
 * clock, expired. An expired session is cleared as a side effect so a stale
 * token never lingers for a later read that does not itself check expiry
 * (e.g. KidNav's profile lookup).
 */
export function getValidChildSession(now: Date = new Date()): ChildSession | null {
  const session = getChildSession()
  if (!session) return null
  if (isExpired(session.expiresAt, now)) {
    clearChildSession()
    return null
  }
  return session
}

/**
 * Kid-surface routes whose requests should prefer the child session token
 * over the guardian bearer, when a valid one exists.
 *
 * #ASSUME: security: `KID_PICKER_PATH` (`/kids`) is deliberately EXCLUDED
 * even though it is a kid-facing route. The picker's own `GET /v1/profiles`
 * (list every family profile) and its `POST /v1/child-sessions` mint call
 * (mint a session for whichever profile is picked next) both need the
 * GUARDIAN's scope; a child token only ever authorizes its own single
 * profile (`api/profiles.py::list_profiles` scopes to
 * `principal.profile_ids`, which for a child principal is just that one
 * profile). If `/kids` preferred a lingering child token from a previous
 * pick, `KidNav`'s "Switch reader" link (which returns to `/kids` without
 * clearing anything) would silently narrow the picker to one profile instead
 * of showing every child in the family.
 * #VERIFY: childSession.test.ts "isKidTokenRoute excludes the picker path";
 * useApi.test.ts "request interceptor child-token selection" drives the real
 * interceptor that calls this (picker/guardian routes fall through to the
 * guardian token; library/read routes attach the child token). The
 * ProfilePickerPage tests mock useApi wholesale, so they never run the
 * interceptor and cannot exercise this predicate.
 */
export function isKidTokenRoute(pathname: string): boolean {
  return pathname.startsWith('/library/') || pathname.startsWith('/read/')
}

/**
 * Extract the profile id a kid-token route is scoped to, or null when the path
 * is not a kid-token route. Both surfaces put the profile id in the same
 * position: `/library/:profileId` and `/read/:profileId/:storybookId/:version`.
 *
 * #ASSUME: security: used by useApi's request interceptor to attach the child
 * token ONLY when the routed profile matches the session's profile. A session
 * for profile A must never authorize a request for profile B's library (a
 * lingering A-session reached via a B deep link would otherwise 403 as A on
 * B's resources, a confusing wrong-gate); the interceptor falls back to the
 * guardian token in that mismatch instead.
 * #VERIFY: useApi.test.ts "does not attach a child token whose profile does
 * not match the routed profile".
 */
export function routeProfileId(pathname: string): string | null {
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length >= 2 && (segments[0] === 'library' || segments[0] === 'read')) {
    return segments[1]
  }
  return null
}
