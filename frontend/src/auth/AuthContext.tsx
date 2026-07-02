import type { Session } from '@supabase/supabase-js'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { useApi } from '../hooks/useApi'
import { AuthContext, type AuthContextValue, type AuthStatus } from './authContext'
import { supabase } from './supabaseClient'
import type { Principal, Role } from './types'

const TOKEN_STORAGE_KEY = 'auth_token'

interface MeResponseBody {
  subject: string
  role: string
  family_id: string
  profile_ids: string[]
}

/**
 * Wraps the Supabase guardian session and resolves it to a backend
 * {@link Principal} via GET /v1/me. The frontend never inspects the bearer
 * token itself (opaque locally, a signed JWT elsewhere); /me is the sole
 * source of truth for role/family, matching api/deps.py's Principal.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const api = useApi()
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  useEffect(() => {
    let cancelled = false

    // #ASSUME: timing-dependencies: this re-fetches /me on every
    // onAuthStateChange event, including a periodic TOKEN_REFRESHED with an
    // unchanged role/family. That's wasted work, not a correctness bug, and
    // guardian sessions are low-frequency; revisit only if /me load becomes
    // measurable.
    // #VERIFY: test_auth_context.test_refetches_principal_on_token_refresh.
    async function syncPrincipal(session: Session | null) {
      if (session === null) {
        localStorage.removeItem(TOKEN_STORAGE_KEY)
        if (!cancelled) {
          setPrincipal(null)
          setStatus('signed-out')
        }
        return
      }
      localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token)
      try {
        const res = await api.get<MeResponseBody>('/v1/me')
        if (cancelled) return
        setPrincipal({
          subject: res.data.subject,
          role: res.data.role as Role,
          familyId: res.data.family_id,
          profileIds: res.data.profile_ids,
        })
        setStatus('signed-in')
      } catch {
        // #CRITICAL: security: a session whose /me call fails (expired,
        // rejected by the backend's real JWT verification) must never be
        // treated as authenticated. Fail closed to signed-out.
        // #VERIFY: test_auth_context.test_me_failure_signs_out.
        if (!cancelled) {
          localStorage.removeItem(TOKEN_STORAGE_KEY)
          setPrincipal(null)
          setStatus('signed-out')
        }
      }
    }

    supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) void syncPrincipal(data.session)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      void syncPrincipal(session)
    })

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [api])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      principal,
      signInWithOAuth: async (provider) => {
        await supabase.auth.signInWithOAuth({ provider })
      },
      signOut: async () => {
        await supabase.auth.signOut()
      },
    }),
    [status, principal]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
