import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

/**
 * Whether a URL fragment is the return leg of a Supabase password-recovery
 * link. The recovery link lands on the implicit-flow hash
 * `#access_token=...&type=recovery`; the sole discriminator from an ordinary
 * OAuth/bearer or signup return is `type=recovery`. Kept pure (takes the hash,
 * touches no globals) so the module-level detection below is trivially testable.
 */
export function hashIndicatesRecovery(hash: string): boolean {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  return params.get('type') === 'recovery'
}

/**
 * True when THIS page load is a password-recovery landing.
 *
 * #CRITICAL: security: read the hash and freeze the answer BEFORE createClient
 * runs. createClient defaults to detectSessionInUrl=true, and the constructor
 * starts a fire-and-forget initialize() that consumes the implicit-flow hash
 * and then strips it from the URL. The strip lands asynchronously, after an
 * auth-server round trip, so the fragment is still readable for a while after
 * construction returns; the point is that it does NOT survive, and any read
 * racing that strip would see an empty fragment, miss the recovery intent,
 * and silently send the guardian into the console instead of the
 * set-new-password form. Computing it here, above createClient, is what makes
 * the read unconditional rather than a race.
 * #VERIFY: supabaseClient.test.ts hashIndicatesRecovery cases; keep this
 * assignment strictly above the createClient call below.
 */
export const isPasswordRecovery = hashIndicatesRecovery(window.location.hash)

/**
 * Parses Supabase's recovery-link FAILURE redirect: an expired or already-used
 * link lands with `#error=access_denied&error_code=otp_expired&error_description=...`,
 * not `type=recovery`, so `hashIndicatesRecovery` above never sees it. Kept
 * pure and side-effect-free like `hashIndicatesRecovery`, for the same reason.
 */
export function hashIndicatesRecoveryError(
  hash: string
): { code: string; description: string } | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  const error = params.get('error')
  if (!error) return null
  return {
    code: params.get('error_code') ?? error,
    description: params.get('error_description') ?? 'The link is invalid or has expired.',
  }
}

/**
 * Set when THIS page load is the failed return leg of a recovery link.
 *
 * #CRITICAL: security: frozen BEFORE createClient for the same reason as
 * isPasswordRecovery above: detectSessionInUrl processes the hash and then
 * strips it asynchronously, so a later read can see nothing.
 * #VERIFY: supabaseClient.test.ts hashIndicatesRecoveryError cases.
 */
export const recoveryErrorFromUrl = hashIndicatesRecoveryError(window.location.hash)

/**
 * Same-origin channel a tab that lands on a recovery link broadcasts on, so a
 * guardian's OTHER already-open guardian-login tab also enters the
 * set-new-password gate.
 *
 * #CRITICAL: concurrency: Supabase's PASSWORD_RECOVERY auth event and the
 * recovery hash are both scoped to the tab that actually followed the
 * link; a second tab only learns about the new session via Supabase's
 * cross-tab session sync (no PASSWORD_RECOVERY event there), which would
 * otherwise flip it straight to signed-in on the guardian's OLD password,
 * skipping the required set-new-password step entirely.
 * #VERIFY: AuthContext.test.tsx "a second tab enters recovery when notified
 * over the recovery broadcast channel".
 */
export const RECOVERY_BROADCAST_CHANNEL_NAME = 'cyo-guardian-recovery'

if (isPasswordRecovery && typeof BroadcastChannel !== 'undefined') {
  new BroadcastChannel(RECOVERY_BROADCAST_CHANNEL_NAME).postMessage('recovery')
}

// #CRITICAL: external-resources: the guardian surface cannot function without a
// Supabase project. This module is imported only inside the guardian lazy chunk
// (auth/GuardianAuthLayout, wired lazily under /guardian in router.tsx), so a
// missing key fails the guardian route (caught by that subtree's errorElement),
// never the unauthenticated kid surface (/ and /read/*), which never imports it.
// #VERIFY: GuardianAuthLayout is lazy-loaded only under /guardian in router.tsx;
// createClient throws on a falsy url/key, so we surface an actionable message.
if (!supabaseUrl || !supabaseAnonKey) {
  const msg =
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY: the guardian sign-in ' +
    'surface cannot start. Set both from Supabase dashboard > Project Settings > API.'
  throw new Error(msg)
}

/**
 * The Supabase client for guardian sign-in (ADR-009). Never used on the kid
 * surface: a child never authenticates as a guardian, and this session is
 * guardian/admin-only per the auth seam in api/deps.py. The module is loaded
 * only inside the guardian lazy chunk so the kid bundle omits it entirely.
 */
export const supabase = createClient(supabaseUrl, supabaseAnonKey)

/**
 * User id of a sign-in that supabase-js reported before AuthProvider could
 * observe it, held until the first principal resolution consumes it. Null
 * once consumed, and null when no such sign-in happened on this page load.
 */
let pendingEarlySignInUserId: string | null = null

/**
 * Captures a 'SIGNED_IN' that lands before AuthProvider subscribes.
 *
 * #CRITICAL: security: AdultGate's warm entry may only be written when a
 * guardian has JUST proven credentials, which AuthContext detects via
 * supabase-js's 'SIGNED_IN' event. On an OAuth return leg, detectSessionInUrl
 * consumes the callback hash from inside createClient's initialize(), and the
 * resulting 'SIGNED_IN' is dispatched from a setTimeout(..., 0) macrotask
 * (GoTrueClient _initialize). Whether AuthProvider's own subscriber is
 * registered by then depends on how fast the guardian lazy chunk mounts
 * relative to the _getUser round trip that macrotask waits on, so the event
 * is observable on some loads and lost on others. When it is lost the gate
 * stays cold, the guardian is challenged the instant they arrive, and the
 * challenge's own "Continue with Google" button returns them in exactly the
 * same state: an endless bounce through Google with no way into the console.
 * Subscribing HERE removes the race rather than guessing at its outcome.
 * onAuthStateChange registers its callback into stateChangeEmitters
 * synchronously, and this runs at module evaluation, strictly before any
 * React mount, so this subscriber is always in place before that macrotask.
 * #CRITICAL: security: the recorded id comes from supabase-js, which emits
 * 'SIGNED_IN' from the URL path only AFTER _getUser validates the token
 * against the auth server. A fragment someone types or replays cannot reach
 * this callback, so the gate can no longer be warmed by an unvalidated URL.
 * The predicate this replaces read the hash directly and accepted any string
 * containing access_token, including the empty value that supabase-js itself
 * rejects.
 * #VERIFY: supabaseClient.test.ts "records a SIGNED_IN that lands before
 * AuthProvider subscribes" and "ignores a restored session and a silent
 * token refresh"; AuthContext.test.tsx "warms the adult gate on an OAuth
 * return leg whose SIGNED_IN arrived before mount".
 */
const earlySignIn = supabase.auth.onAuthStateChange((event, session) => {
  if (event !== 'SIGNED_IN' || session === null) return
  pendingEarlySignInUserId = session.user.id
  earlySignIn.data.subscription.unsubscribe()
})

/**
 * Reads and clears the early-sign-in capture. Single-use by construction: the
 * first caller receives the id and every later caller receives null.
 *
 * #CRITICAL: security: consuming is what bounds the warm to one resolution.
 * `syncPrincipal` runs again on every later principal re-resolution in the
 * same page load (recordConsent, startVerification, and the refreshStatus
 * behind each guardian interstitial's "check again" control), so a capture
 * left in place would re-warm the gate and slide its idle TTL forward for a
 * guardian who has walked away. Call this exactly once per resolution, on
 * every path, warming or not, so the fact cannot outlive its page load.
 * #VERIFY: AuthContext.test.tsx "does not re-warm on a later refreshStatus in
 * the same page load".
 */
export function consumeEarlySignInUserId(): string | null {
  const userId = pendingEarlySignInUserId
  pendingEarlySignInUserId = null
  return userId
}
