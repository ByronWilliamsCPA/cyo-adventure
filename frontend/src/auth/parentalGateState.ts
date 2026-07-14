/**
 * Warm state for the adult step-up gate (ADR-014 Phase 5, AdultGate.tsx).
 *
 * A successful guardian re-auth (password re-entry, or the documented
 * OAuth-bypass) "warms" the gate for ADULT_GATE_TTL_MS so a grown-up is not
 * re-challenged on every navigation between adult console pages
 * (guardian<->guardian, guardian<->admin, admin<->guardian). The warm entry
 * lives in `sessionStorage`, not module memory: a same-tab full-page reload
 * (the switch-account OAuth round-trip is exactly this) must NOT re-cold the
 * gate for the same user, or the switch-account flow re-prompts every time
 * even though the underlying Supabase session never left. `sessionStorage`
 * still clears on tab close, which is the property that keeps "a kid opens a
 * fresh tab on this device" cold.
 *
 * #CRITICAL: security: the warm entry is keyed by the Supabase user id, so a
 * different guardian signing in on the same device within the TTL of the
 * previous guardian's unlock is NOT inherited as warm. This is the single
 * invariant that makes the switch-account flow safe: signing out (which
 * clears the entry, see clearAdultGate) then signing back in as someone else
 * always lands cold for that new identity.
 * #VERIFY: AdultGate.test.tsx "stays locked when the warm entry belongs to a
 * different user" and the switch-account regression test (same-user reload
 * stays warm, different-user reload is cold).
 *
 * parkAdultGate() is called on entering kid mode (DeviceAuthorizedRoute.tsx)
 * so returning up from a kid profile always re-demands the grown-up
 * password, regardless of how much of the TTL window was left. This module
 * has NO imports (in particular nothing from `supabaseClient` or any other
 * `@supabase/supabase-js`-reaching module): it is imported directly by the
 * kid chunk (DeviceAuthorizedRoute.tsx), which must never pull Supabase into
 * the kid bundle (see router.tsx's header comment).
 */

/** How long one successful re-auth (or OAuth-bypass) keeps the gate open. */
export const ADULT_GATE_TTL_MS = 5 * 60 * 1000

/** sessionStorage key for the single warm entry (one signed-in adult at a time). */
const STORAGE_KEY = 'cyo_adult_gate_warm'

interface WarmEntry {
  userId: string
  expiresAt: number
}

function isWarmEntry(value: unknown): value is WarmEntry {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.userId === 'string' && typeof candidate.expiresAt === 'number'
}

/**
 * Read the warm entry from sessionStorage, if present and well-formed.
 * #EDGE: browser-compat: sessionStorage can throw in private/locked-down
 * browsing modes, or hold a corrupt/foreign value under this key; either way
 * treat it as cold rather than propagating the error into the gate's render.
 */
function readWarm(): WarmEntry | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    return isWarmEntry(parsed) ? parsed : null
  } catch {
    return null
  }
}

/** Write (or clear, when `entry` is null) the warm entry. Best-effort. */
function writeWarm(entry: WarmEntry | null): void {
  try {
    if (entry === null) {
      sessionStorage.removeItem(STORAGE_KEY)
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entry))
    }
  } catch {
    // #EDGE: browser-compat: storage unavailable (private mode, quota full).
    // The gate simply falls back to always-cold for the rest of this tab,
    // which is the fail-closed direction.
  }
}

/** Record a successful guardian re-auth for `userId`, starting the TTL now. */
export function warmAdultGate(userId: string, now: number = Date.now()): void {
  writeWarm({ userId, expiresAt: now + ADULT_GATE_TTL_MS })
}

/**
 * Milliseconds of warmth remaining for `userId`; 0 when the gate is cold,
 * expired, parked, or warmed by a different user.
 */
export function adultGateRemainingMs(userId: string, now: number = Date.now()): number {
  const warm = readWarm()
  if (warm?.userId !== userId) return 0
  return Math.max(0, warm.expiresAt - now)
}

/** True when the gate is currently warm for exactly this user. */
export function isAdultGateWarm(userId: string, now: number = Date.now()): boolean {
  return adultGateRemainingMs(userId, now) > 0
}

/**
 * Drop any warm state so the next check is cold. Called when entering kid
 * mode (DeviceAuthorizedRoute.tsx): a device handed to a child must always
 * require the grown-up password again on the way back up, however much of
 * the TTL window was left.
 * #VERIFY: AdultGate.test.tsx "entering the kid surface parks the gate".
 */
export function parkAdultGate(): void {
  writeWarm(null)
}

/**
 * Drop any warm state on explicit sign-out (AuthContext.tsx), so warmth never
 * survives a sign-out into the next sign-in. Functionally identical to
 * parkAdultGate(); kept as a distinct export so call sites read as intent
 * ("this is a sign-out clearing itself", not "this is a kid-mode park").
 * #VERIFY: AuthContext.test.tsx "sign-out drops warm adult-gate state".
 */
export function clearAdultGate(): void {
  writeWarm(null)
}
