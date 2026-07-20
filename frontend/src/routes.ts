/**
 * Shared route path constants.
 *
 * GUARDIAN_LOGIN_PATH is referenced by the router (the route definition and the
 * ProtectedRoute redirect) and by AuthContext's OAuth `redirectTo`, so the
 * redirect, the route, and the guard stay aligned if the path ever moves.
 */
export const GUARDIAN_LOGIN_PATH = '/guardian/login'

/**
 * Self-signup approval interstitial (AuthStatus 'awaiting-approval'):
 * ProtectedRoute sends a guardian here instead of looping them through
 * login, since they DO have a valid Supabase session, it just is not yet
 * approved (api/onboarding.py's self-signup track).
 */
export const GUARDIAN_AWAITING_APPROVAL_PATH = '/guardian/awaiting-approval'

/**
 * VPC consent-capture interstitial (AuthStatus 'needs-consent', Phase 2 /
 * ADR-018 D1): ProtectedRoute sends an approved-but-unconsented guardian
 * here before they can reach any other guardian page.
 */
export const GUARDIAN_CONSENT_PATH = '/guardian/consent'

/** Kid profile picker, relocated from `/` when the landing page took the root. */
export const KID_PICKER_PATH = '/kids'

/**
 * Guardian console root. The landing page links here (not to the login page)
 * so ProtectedRoute decides: signed-out visitors bounce to login, a
 * signed-in guardian lands straight on the console.
 */
export const GUARDIAN_CONSOLE_PATH = '/guardian'

/**
 * Admin console root: the parallel adult surface for admin-capability
 * functions (review queue, global story-request queue, moderation admin).
 * Shares the login page and AuthProvider with the guardian tree; an adult
 * holding both capabilities switches between /guardian and /admin via the
 * shell nav.
 */
export const ADMIN_CONSOLE_PATH = '/admin'

/**
 * Query parameter DeviceAuthorizedRoute appends to the guardian-login
 * redirect when the kid surface has no valid device grant (ADR-014 Phase 4).
 * Carried so a future login flow (Phase 5/6) can recognize "this sign-in is
 * to authorize a device, then return to the kid surface" and drive the
 * authorize-then-return flow automatically, rather than landing the guardian
 * on the console with no indication why they were sent to log in.
 */
export const AUTHORIZE_DEVICE_INTENT_PARAM = 'intent'
export const AUTHORIZE_DEVICE_INTENT_VALUE = 'authorize-device'
