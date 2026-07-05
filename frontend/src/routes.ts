/**
 * Shared route path constants.
 *
 * GUARDIAN_LOGIN_PATH is referenced by the router (the route definition and the
 * ProtectedRoute redirect) and by AuthContext's OAuth `redirectTo`, so the
 * redirect, the route, and the guard stay aligned if the path ever moves.
 */
export const GUARDIAN_LOGIN_PATH = '/guardian/login'
