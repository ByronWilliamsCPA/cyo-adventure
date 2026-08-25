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
 * runs. createClient defaults to detectSessionInUrl=true, which consumes the
 * implicit-flow hash and strips it from the URL during construction; a later
 * read of window.location.hash would then see an empty fragment and miss the
 * recovery intent, silently sending the guardian into the console instead of
 * the set-new-password form. Computing it here, above createClient, captures
 * the fragment while it is still present.
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
 * isPasswordRecovery above: detectSessionInUrl processes and strips the hash
 * during construction, so a later read would see nothing.
 * #VERIFY: supabaseClient.test.ts hashIndicatesRecoveryError cases.
 */
export const recoveryErrorFromUrl = hashIndicatesRecoveryError(window.location.hash)

/**
 * Whether a URL fragment is the return leg of a COMPLETED OAuth sign-in: the
 * implicit-flow hash Supabase's `/auth/v1/callback` redirects to, carrying a
 * freshly minted `access_token`. A recovery landing (`type=recovery`) and a
 * cancelled or failed return (`error=...`) are both excluded, because neither
 * is a completed sign-in. Kept pure, like the two predicates above, so the
 * module-level detection below is trivially testable.
 */
export function hashIndicatesOAuthReturn(hash: string): boolean {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  if (params.get('type') === 'recovery') return false
  if (params.get('error') !== null) return false
  return params.get('access_token') !== null
}

/**
 * True when THIS page load is the return leg of an OAuth sign-in.
 *
 * #CRITICAL: security: AdultGate's warm entry may only be written when a
 * guardian has JUST proven credentials, which AuthContext detects via
 * supabase-js's 'SIGNED_IN' event. On an OAuth return that event is emitted
 * from INSIDE createClient's initialize() (detectSessionInUrl consumes the
 * hash there), which resolves before AuthProvider subscribes; a subscriber
 * registering afterwards is replayed 'INITIAL_SESSION', never 'SIGNED_IN'
 * (GoTrueClient.onAuthStateChange awaits initializePromise, then calls
 * _emitInitialSession). The event therefore reaches ZERO subscribers, the
 * gate stays cold, and the guardian is challenged the instant they arrive.
 * The challenge's own "Continue with Google" button returns them here in
 * exactly the same state, so the guardian bounces through Google forever and
 * never reaches the console. This flag carries, out of band, the one fact
 * that vanished event was needed for.
 * #CRITICAL: security: frozen BEFORE createClient for the same reason as
 * isPasswordRecovery above: detectSessionInUrl processes and strips the hash
 * during construction, so a later read would see nothing.
 * #ASSUME: security: this widens gate-warming from "supabase-js told us" to
 * "an access_token was in the URL on this page load". That is not a new trust
 * grant: anyone able to put a valid access_token in the address bar already
 * holds the session it names, so warming the gate concedes nothing they do
 * not already have. A restored or silently refreshed session still arrives
 * with no hash and stays cold, which is the property the gate depends on.
 * #VERIFY: supabaseClient.test.ts hashIndicatesOAuthReturn cases; keep this
 * assignment strictly above the createClient call below.
 */
export const isOAuthReturn = hashIndicatesOAuthReturn(window.location.hash)

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
