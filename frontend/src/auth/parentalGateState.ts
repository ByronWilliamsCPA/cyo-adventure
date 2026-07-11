/**
 * In-memory warm state for the parental gate (P6-08).
 *
 * A successful guardian re-auth "warms" the gate for a short TTL so the
 * guardian is not re-challenged on every navigation between sensitive console
 * pages. The state is deliberately module-level memory, never localStorage or
 * sessionStorage: a page reload (or a kid opening a new tab) must always start
 * cold and re-challenge, which is exactly the Kids Category gate behavior
 * Apple expects. Losing the warm state too often is a nuisance; persisting it
 * would defeat the gate.
 *
 * #CRITICAL: security: the warm entry is keyed by the Supabase user id, so a
 * different guardian signing in on the same device within the TTL of the
 * previous guardian's unlock is NOT inherited as warm.
 * #VERIFY: ParentalGate.test.tsx "stays locked when the warm entry belongs to
 * a different user".
 */

/** How long one successful re-auth keeps the gate open. */
export const PARENTAL_GATE_TTL_MS = 5 * 60 * 1000

let warmed: { userId: string; expiresAt: number } | null = null

/** Record a successful guardian re-auth for `userId`, starting the TTL now. */
export function warmParentalGate(userId: string, now: number = Date.now()): void {
  warmed = { userId, expiresAt: now + PARENTAL_GATE_TTL_MS }
}

/**
 * Milliseconds of warmth remaining for `userId`; 0 when the gate is cold,
 * expired, or warmed by a different user.
 */
export function parentalGateRemainingMs(userId: string, now: number = Date.now()): number {
  if (warmed === null || warmed.userId !== userId) return 0
  return Math.max(0, warmed.expiresAt - now)
}

/** Drop any warm state so the next mount re-challenges (tests, sign-out). */
export function coolParentalGate(): void {
  warmed = null
}
