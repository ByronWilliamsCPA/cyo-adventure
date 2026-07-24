import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { LibraryPage } from '../library/LibraryPage'
import { useApi } from '../hooks/useApi'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { GUARDIAN_CONSOLE_PATH } from '../routes'
import './guardian.css'

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; profile: ProfileView | null }

/**
 * Guardian preview-as-child (read-only): renders the real kid LibraryPage for
 * a chosen child profile, guardian-authed, with no device grant or child
 * session needed.
 *
 * Deliberately mounted at `/guardian/preview/:profileId`, NOT under
 * `/library/*`: those paths are kid-token-gated (`useApi.ts`'s
 * `isKidTokenRoute`), which refuses to attach the guardian's own bearer at
 * all. This path falls through to the ordinary guardian-bearer branch
 * instead, and the backend authorizes it because a guardian principal's
 * `profile_ids` already covers every active profile in their own family
 * (`api/deps.py::_resolve_profiles`) -- no backend change needed for read
 * access.
 *
 * Every mutation affordance (rating, "ask for the next book", requesting a
 * new story, and the cover's link into the real Reader route) is suppressed
 * via `LibraryPage`'s `readOnly` prop: this is a look, not a login as the
 * child.
 */
export function PreviewAsChildPage() {
  const { profileId } = useParams()
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  // #ASSUME: external-resources: the profile list can fail or be slow; the
  // preview still renders LibraryPage underneath (neutral band/motion) rather
  // than blocking on this best-effort lookup, which only supplies the
  // data-age-band/data-reduce-motion attributes and the banner's child name.
  useEffect(() => {
    if (profileId === undefined) return undefined
    let cancelled = false
    profilesApi
      .list()
      .then((profiles) => {
        if (!cancelled) {
          setState({ status: 'ready', profile: profiles.find((p) => p.id === profileId) ?? null })
        }
      })
      .catch((err: unknown) => {
        console.error('preview profile lookup failed', err instanceof Error ? err.message : err)
        if (!cancelled) setState({ status: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [profilesApi, profileId])

  if (profileId === undefined) return null

  const profile = state.status === 'ready' ? state.profile : null

  return (
    <div
      className="preview-as-child"
      data-age-band={profile?.age_band}
      data-reduce-motion={profile?.reduce_motion ? 'true' : undefined}
    >
      <div className="preview-as-child__banner" role="status">
        <span>
          {profile
            ? `Previewing as ${profile.display_name} (read-only)`
            : 'Previewing (read-only)'}
        </span>
        <Link className="preview-as-child__exit" to={`${GUARDIAN_CONSOLE_PATH}/profiles`}>
          Exit preview
        </Link>
      </div>
      <LibraryPage readOnly />
    </div>
  )
}
