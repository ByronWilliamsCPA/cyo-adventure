import { useEffect, useMemo, useState } from 'react'

import { useApi } from '../hooks/useApi'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'

// KidShell and KidNav both call this hook and mount in the same commit on a
// library view, which used to fire two identical GET /v1/profiles requests
// per page. Concurrent lookups for the SAME profileId share one in-flight
// request instead (StrictMode's double-invoked effects collapse too).
//
// Keyed by profileId, cleared on settle: a profileId SWITCH mid-flight must
// keep issuing its own fresh fetch, because the switch is what refreshes the
// list a stale in-flight response would otherwise serve to the new id (see
// the effect's #ASSUME below). Only the true duplicate, two consumers of one
// route's profile, ever joins.
let inflightProfilesList: { forId: string; promise: Promise<ProfileView[]> } | null = null

function listProfilesShared(
  profilesApi: ReturnType<typeof makeProfilesApi>,
  forId: string
): Promise<ProfileView[]> {
  const current = inflightProfilesList
  if (current !== null && current.forId === forId) return current.promise
  const promise = profilesApi.list()
  inflightProfilesList = { forId, promise }
  // Clear the slot when this request settles (unless a newer one replaced
  // it). The chain is deliberately swallowed: callers hold the ORIGINAL
  // promise and handle its rejection themselves; this bookkeeping copy must
  // not surface as an unhandled rejection of its own.
  promise
    .finally(() => {
      if (inflightProfilesList?.promise === promise) inflightProfilesList = null
    })
    .catch(() => undefined)
  return promise
}

/** Test-only: drop a shared in-flight list so suites stay isolated. */
export function _resetKidProfileFetch(): void {
  inflightProfilesList = null
}

export interface KidProfileLookup {
  /** The profileId this lookup was resolved for. */
  forId: string
  /** `null` once the fetch has settled and found no matching profile (or failed). */
  profile: ProfileView | null
}

/**
 * Best-effort lookup of the profile behind a kid-surface profileId: name,
 * avatar, age band, and the guardian-set reduce-motion preference. Reuses the
 * same authenticated `/v1/profiles` list the picker uses, scoped server-side
 * to whatever session token the browser holds; a failure (offline, hiccup)
 * degrades to `profile: null` rather than throwing.
 *
 * Returns `null` (not a lookup with a null profile) while the fetch for the
 * CURRENT profileId is still in flight, or before one has been requested at
 * all (`profileId` undefined). Once settled, the result is keyed by the
 * profileId it was loaded for, so a profile switch or a stale in-flight
 * response for a since-abandoned id never flashes the wrong child's data.
 */
export function useKidProfile(profileId: string | undefined): KidProfileLookup | null {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [loaded, setLoaded] = useState<KidProfileLookup | null>(null)

  // #ASSUME: external-resources: the profile list can fail or resolve after
  // the child has already switched profiles.
  // #VERIFY: `cancelled` guards the setState, and the fetched result is keyed
  // by the profileId it was loaded for; a switch to a new profileId or a
  // failed re-fetch therefore shows the generic/neutral fallback, never the
  // previous child's identity or CSS tier.
  useEffect(() => {
    if (profileId === undefined) return undefined
    const forId = profileId
    let cancelled = false
    async function load() {
      try {
        const profiles = await listProfilesShared(profilesApi, forId)
        if (!cancelled) {
          setLoaded({ forId, profile: profiles.find((p) => p.id === forId) ?? null })
        }
      } catch (err) {
        console.error('kid profile lookup failed', err instanceof Error ? err.message : err)
        if (!cancelled) setLoaded({ forId, profile: null })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, profileId])

  return loaded?.forId === profileId ? loaded : null
}
