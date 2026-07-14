/**
 * Client-side storage and route classification for the device grant
 * (ADR-014 Phase 3): a durable, revocable, family-scoped credential a
 * guardian mints once per shared device so a child can pick a profile and
 * read, online or offline, without a live guardian Supabase session.
 *
 * Deliberately mirrors childSession.ts's shape and Supabase-free contract:
 * this module is imported by the kid chunk (DeviceAuthorizedRoute, useApi's
 * interceptor), which must never pull in @supabase/supabase-js. See
 * childSession.ts's header comment for why a single JSON-blob key beats
 * parallel keys, and why expiry is checked client-side only as a pre-check
 * (the backend independently verifies `exp` and the grant's revocation
 * status on every online request; see `core/device_grant.py`).
 *
 * #CRITICAL: security: the device grant is a CONVENIENCE / routing artifact,
 * not the real authorization boundary. It authorizes nothing by itself; the
 * backend verifies the signature, expiry, and (online) revocation status of
 * the token on every request that carries it (`api/deps.py`'s device
 * principal branch). A forged or replayed local blob with no matching valid
 * token would still 401 server-side.
 * #VERIFY: the backend test suite covers signature/expiry/revocation
 * rejection independent of anything this module does.
 */

import { getDeviceGrantMirror, putDeviceGrantMirror, clearDeviceGrantMirror } from '../offline/db'
import { KID_PICKER_PATH } from '../routes'

const GRANT_KEY = 'device_grant'

export interface DeviceGrant {
  token: string
  /** ISO 8601 timestamp; the server's `expires_at` from `DeviceGrantView`. */
  expiresAt: string
  familyId: string
  id: string
}

function isDeviceGrant(value: unknown): value is DeviceGrant {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.token === 'string' &&
    typeof candidate.expiresAt === 'string' &&
    typeof candidate.familyId === 'string' &&
    typeof candidate.id === 'string'
  )
}

/**
 * Persist a freshly minted device grant (called from the guardian console's
 * authorizeDevice() after a successful `POST /v1/device-grants`, and by the
 * IndexedDB-mirror repair path below). Writes localStorage synchronously (the
 * primary store) and best-effort mirrors to IndexedDB asynchronously; a
 * mirror-write failure is swallowed exactly like childSession.ts's storage
 * failures; it only narrows offline resilience, it never blocks the caller.
 *
 * #VERIFY: deviceGrant.test.ts "storage failure on write is swallowed" and
 * "mirrors to IndexedDB".
 */
export function setDeviceGrant(grant: DeviceGrant): void {
  try {
    localStorage.setItem(GRANT_KEY, JSON.stringify(grant))
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing more to do here.
  }
  void putDeviceGrantMirror(grant).catch(() => {
    // #EDGE: browser-compat: IndexedDB unavailable or blocked; the
    // localStorage write above (if it succeeded) still authorizes this
    // device for the remainder of the session, just without the offline
    // resilience the mirror exists to provide.
  })
}

/** Clear a stored device grant: on 401 (expired/revoked), or explicit removal. */
export function clearDeviceGrant(): void {
  try {
    localStorage.removeItem(GRANT_KEY)
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing to clean up.
  }
  void clearDeviceGrantMirror().catch(() => {
    // #EDGE: browser-compat: IndexedDB unavailable or blocked; the mirror
    // may outlive the localStorage clear until it expires on its own TTL.
  })
}

/**
 * Read the stored device grant from localStorage, if a complete and
 * well-formed one is present. Does not check expiry or consult the
 * IndexedDB mirror; callers that need the durable, offline-resilient read
 * should use {@link hydrateDeviceGrant} instead.
 */
export function getDeviceGrant(): DeviceGrant | null {
  try {
    const raw = localStorage.getItem(GRANT_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    return isDeviceGrant(parsed) ? parsed : null
  } catch {
    // #EDGE: browser-compat: storage unavailable, or a corrupt/partial blob
    // that failed to parse; either way treat it as no grant.
    return null
  }
}

/**
 * #CRITICAL: timing dependencies: this is a CLIENT-SIDE pre-check only, same
 * caveat as childSession.ts's isExpired. The backend independently verifies
 * `exp` (and, online, revocation) on every request that carries the grant.
 * #VERIFY: deviceGrant.test.ts covers before/at/after the expiry boundary.
 */
export function isDeviceGrantExpired(expiresAt: string, now: Date = new Date()): boolean {
  const parsed = Date.parse(expiresAt)
  if (Number.isNaN(parsed)) return true
  return parsed <= now.getTime()
}

/**
 * Return the stored device grant only if present and not, per the client
 * clock, expired. An expired grant is cleared as a side effect so a stale
 * grant never lingers for a later synchronous read.
 */
export function getValidDeviceGrant(now: Date = new Date()): DeviceGrant | null {
  const grant = getDeviceGrant()
  if (!grant) return null
  if (isDeviceGrantExpired(grant.expiresAt, now)) {
    clearDeviceGrant()
    return null
  }
  return grant
}

/** Convenience boolean wrapper around {@link getValidDeviceGrant}. */
export function hasValidDeviceGrant(now: Date = new Date()): boolean {
  return getValidDeviceGrant(now) !== null
}

/**
 * Durable read: prefer the fast, synchronous localStorage grant; when
 * localStorage holds nothing valid (a fresh clear, private-mode eviction),
 * fall back to the IndexedDB mirror. A valid mirrored grant is written back
 * into localStorage (repairing it) before being returned, so the next
 * {@link hasValidDeviceGrant} synchronous check (the interceptor, a re-render)
 * sees it without touching IndexedDB again. An expired mirror entry is
 * dropped from both stores, same as the synchronous path.
 *
 * Intended for a ONE-TIME async check at the kid surface's gate
 * (DeviceAuthorizedRoute), not for the request interceptor (which must stay
 * synchronous; see useApi.ts).
 *
 * #VERIFY: deviceGrant.test.ts "falls back to the IndexedDB mirror when
 * localStorage is cleared" and "drops an expired mirror entry".
 */
export async function hydrateDeviceGrant(now: Date = new Date()): Promise<DeviceGrant | null> {
  const fast = getValidDeviceGrant(now)
  if (fast) return fast
  let mirrored: DeviceGrant | undefined
  try {
    mirrored = await getDeviceGrantMirror()
  } catch {
    // #EDGE: browser-compat: IndexedDB unavailable or blocked; treat as no
    // mirror, same as a missing entry.
    return null
  }
  if (!mirrored || isDeviceGrantExpired(mirrored.expiresAt, now)) {
    if (mirrored) {
      // Expired mirror entry: drop it so it is never offered again.
      void clearDeviceGrantMirror().catch(() => {
        // #EDGE: browser-compat: best-effort cleanup only.
      })
    }
    return null
  }
  setDeviceGrant(mirrored)
  return mirrored
}

/**
 * Kid-surface route whose requests should attach the device-grant bearer
 * (in preference to the guardian token) when a valid grant exists: only the
 * profile picker (`/kids`), which is the sole caller of `GET /v1/profiles`
 * and `POST /v1/child-sessions` on the kid side.
 *
 * #ASSUME: security: deliberately narrower than "the whole kid tree" (unlike
 * DeviceAuthorizedRoute, which gates `/kids`, `/library/*`, and `/read/*`).
 * The guardian console's OWN `GET /v1/profiles` call (ConsolePage's
 * onboarding child-count check) must keep using the guardian bearer even
 * though the backend would also accept a device grant for the same family;
 * gating on the exact picker path is the only signal the interceptor has for
 * which UI surface issued the call.
 * #VERIFY: useApi.test.ts "device-grant bearer selection" cases.
 */
export function isDeviceGrantAuthRoute(pathname: string): boolean {
  return pathname === KID_PICKER_PATH
}
