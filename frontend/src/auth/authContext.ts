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
  signInWithOAuth: (provider: 'google' | 'apple') => Promise<void>
  signInWithPassword: (credentials: Credentials) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
