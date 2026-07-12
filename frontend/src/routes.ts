/**
 * Shared route path constants.
 *
 * GUARDIAN_LOGIN_PATH is referenced by the router (the route definition and the
 * ProtectedRoute redirect) and by AuthContext's OAuth `redirectTo`, so the
 * redirect, the route, and the guard stay aligned if the path ever moves.
 */
export const GUARDIAN_LOGIN_PATH = '/guardian/login'

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
