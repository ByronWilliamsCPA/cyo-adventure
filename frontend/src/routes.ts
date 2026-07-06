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
