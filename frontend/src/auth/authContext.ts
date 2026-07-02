import { createContext } from 'react'

import type { Principal } from './types'

export type AuthStatus = 'loading' | 'signed-out' | 'signed-in'

export interface AuthContextValue {
  status: AuthStatus
  principal: Principal | null
  signInWithOAuth: (provider: 'google' | 'apple') => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
