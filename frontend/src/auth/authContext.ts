import { createContext } from 'react'

import type { Principal } from './types'

export type AuthStatus = 'loading' | 'signed-out' | 'signed-in'

/**
 * A session was established with Supabase but the backend could not resolve it
 * to a Principal (GET /me failed, the JWT was rejected, the role was
 * unrecognized, or the Supabase subject has no backend User row). Distinct from
 * plain 'signed-out' (no session at all) so the login form can tell the user
 * "you're signed in, but we couldn't load your account" instead of stranding
 * them on an idle form. Null when there is no such error.
 */
export type AuthError = 'principal-unresolved'

export interface Credentials {
  email: string
  password: string
}

export interface AuthContextValue {
  status: AuthStatus
  principal: Principal | null
  authError: AuthError | null
  /**
   * True while this page load is the return leg of a password-recovery link
   * (Supabase fired PASSWORD_RECOVERY, the landing hash carried
   * type=recovery, or another guardian tab broadcast a recovery landing).
   * LoginPage renders the set-new-password form instead of redirecting while
   * this is set; it clears on a successful password update or on sign-out.
   */
  recovery: boolean
  /**
   * Set when this page load is the FAILED return leg of a recovery link (an
   * expired or already-used link). Distinct from `recovery`: no session was
   * established, so LoginPage should show its normal sign-in form with an
   * explanatory message rather than the set-new-password gate. Null when
   * this load is not a failed recovery return.
   */
  recoveryError: { code: string; description: string } | null
  signInWithOAuth: (provider: 'google' | 'apple') => Promise<void>
  signInWithPassword: (credentials: Credentials) => Promise<void>
  signOut: () => Promise<void>
  /**
   * Emails a password-reset link to `email`. Resolves whether or not the
   * address exists (Supabase does not reveal it), so callers must show a
   * neutral confirmation and never leak account existence.
   */
  requestPasswordReset: (email: string) => Promise<void>
  /**
   * Sets a new password on the current (recovery) session and, on success,
   * clears {@link recovery} so the app auto-continues to the console. Rethrows
   * Supabase's error so the form can surface a retryable failure.
   */
  updatePassword: (newPassword: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
