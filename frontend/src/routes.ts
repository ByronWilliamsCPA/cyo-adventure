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
 * KWS parent-verification interstitial (AuthStatus 'needs-verification',
 * ADR-018 D1): where an adult starts, and then waits out, Epic's Kids Web
 * Services parent verification.
 *
 * This one comes FIRST of the three, before awaiting-approval and before
 * consent, which is the ratified order and not the obvious one. Verifying
 * that an adult is an adult is cheap, entirely self-service, and says nothing
 * about whether we want this account; admin approval is a human judgement
 * that should not be spent on an account that may never prove adulthood. The
 * practical consequence runs through the whole feature: this guardian's
 * ``User.status`` is still 'awaiting_approval', so
 * ``api/deps.py::require_principal`` refuses them, so neither this page nor
 * the endpoint behind it may depend on GET /v1/me.
 */
export const GUARDIAN_VERIFICATION_PATH = '/guardian/verify'

/**
 * VPC consent-capture interstitial (AuthStatus 'needs-consent', Phase 2 /
 * ADR-018 D1): ProtectedRoute sends an approved-but-unconsented guardian
 * here before they can reach any other guardian page.
 */
export const GUARDIAN_CONSENT_PATH = '/guardian/consent'

/**
 * Backend-unreachable interstitial (AuthStatus 'backend-unreachable', #452):
 * the third member of the pattern above. A guardian whose Supabase session is
 * fine but whose principal could not be resolved because our own API is down
 * lands here to retry, rather than being bounced to login, where the same
 * session would be re-established and fail the same way.
 */
export const GUARDIAN_UNAVAILABLE_PATH = '/guardian/unavailable'

/** Kid profile picker, relocated from `/` when the landing page took the root. */
export const KID_PICKER_PATH = '/kids'

/**
 * Public privacy policy and support pages.
 *
 * #CRITICAL: security: these two MUST stay outside every auth gate. Both are
 * registered with Epic's Kids Web Services (ADR-018 D1) as our Privacy Policy
 * and Support URLs, and a parent follows them mid-verification with no account
 * and no session. Nesting either under ProtectedRoute would send that parent to
 * a login page from a third-party consent flow, which reads as a phishing
 * redirect and is the failure this constant's placement exists to prevent.
 * Note the distinction from `/guardian/privacy`, which is a different page: the
 * signed-in G11 trust surface, which stays gated on purpose.
 * #VERIFY: router.test.tsx walks the exported route config and asserts the
 * chain of components between the tree root and each of these two paths
 * contains no gate, with a positive control so the assertion cannot pass by
 * failing to see gates at all. The paired page tests are the weaker companion
 * claim: they render each page with no auth provider mounted, which proves the
 * component needs no session but says nothing about where the route sits.
 */
export const PRIVACY_PATH = '/privacy'
export const SUPPORT_PATH = '/support'

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

/**
 * Guardian preview-as-child (read-only): mounted under the guardian console,
 * deliberately NOT under `/library/*`/`/read/*` (those paths are
 * kid-token-gated in `useApi.ts`'s `isKidTokenRoute` and would refuse the
 * guardian's own bearer).
 */
export function previewAsChildPath(profileId: string): string {
  return `${GUARDIAN_CONSOLE_PATH}/preview/${profileId}`
}

/**
 * Guardian review/edit page (register G6, the edit half): a family's own
 * guardian reaches their own story request here to view the full read-through
 * and fix a flagged passage's prose or choice labels, mirroring the admin
 * review route's `/admin/review/:storybookId` shape one level down.
 */
export function guardianReviewPath(storybookId: string): string {
  return `${GUARDIAN_CONSOLE_PATH}/review/${storybookId}`
}
