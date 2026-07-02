import type { Session } from '@supabase/supabase-js'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { useApi } from '../hooks/useApi'
import { AuthContext, type AuthContextValue, type AuthStatus } from './authContext'
import { supabase } from './supabaseClient'
import { isRole, type Principal } from './types'

const TOKEN_STORAGE_KEY = 'auth_token'

/**
 * Clears the stored bearer token, swallowing the DOMException that some
 * browsers throw from localStorage in private/locked-down modes. Clearing is a
 * best-effort cleanup on the fail-closed path, so a throw here must not mask
 * the sign-out it accompanies.
 */
function safeRemoveToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing to clean up.
  }
}

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

  // #CRITICAL: concurrency: onAuthStateChange can fire several events in quick
  // succession (INITIAL_SESSION, then a near-immediate TOKEN_REFRESHED), each
  // starting an async /me fetch. Without an ordering guard a slow earlier
  // response can land after a newer one and overwrite it, leaving the UI on a
  // stale principal (or a stale signed-out). A monotonic sequence token makes
  // every handler ignore any result that is not the latest it launched.
  // #VERIFY: test_auth_context.test_out_of_order_me_responses_keep_latest.
  const requestSeq = useRef(0)

  useEffect(() => {
    let cancelled = false

    // #ASSUME: timing-dependencies: this re-fetches /me on every
    // onAuthStateChange event, including a periodic TOKEN_REFRESHED with an
    // unchanged role/family. That's wasted work, not a correctness bug, and
    // guardian sessions are low-frequency; revisit only if /me load becomes
    // measurable.
    // #VERIFY: test_auth_context.test_refetches_principal_on_token_refresh.
    async function syncPrincipal(session: Session | null) {
      const seq = ++requestSeq.current
      // A later handler already superseded this one, or the provider unmounted.
      const isStale = () => cancelled || seq !== requestSeq.current

      if (session === null) {
        safeRemoveToken()
        if (!isStale()) {
          setPrincipal(null)
          setStatus('signed-out')
        }
        return
      }
      try {
        // #EDGE: browser-compat: setItem throws in private-mode / quota-full
        // browsers. Keep it inside the try so a storage failure routes to the
        // fail-closed signed-out path below instead of stranding status on
        // 'loading' (it used to sit outside the try, where a throw was fatal).
        localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token)
        const res = await api.get<MeResponseBody>('/v1/me')
        if (isStale()) return
        // #CRITICAL: security: the role drives ProtectedRoute's allow/deny, so
        // an unexpected value must fail closed rather than being cast blindly.
        // #VERIFY: test_auth_context.test_invalid_role_signs_out.
        if (!isRole(res.data.role)) {
          throw new Error(`Unexpected role from /me: ${String(res.data.role)}`)
        }
        setPrincipal({
          subject: res.data.subject,
          role: res.data.role,
          familyId: res.data.family_id,
          profileIds: res.data.profile_ids,
        })
        setStatus('signed-in')
      } catch {
        // #CRITICAL: security: a session whose /me call fails (expired,
        // rejected by the backend's real JWT verification) or returns an
        // unrecognized role must never be treated as authenticated. Fail
        // closed to signed-out.
        // #VERIFY: test_auth_context.test_me_failure_signs_out.
        safeRemoveToken()
        if (!isStale()) {
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
