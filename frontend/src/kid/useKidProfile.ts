import { useEffect, useMemo, useState } from 'react'

import { useApi } from '../hooks/useApi'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'

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
        const profiles = await profilesApi.list()
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
