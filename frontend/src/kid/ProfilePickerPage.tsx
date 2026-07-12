import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { clearChildSession, setChildSession } from '../auth/childSession'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { makeChildSessionApi } from './childSessionApi'
import { Mascot } from './Mascot'

// `unauthenticated` is the stable, expected no-grown-up-signed-in gate, not a
// flaky fetch. `forbidden` is defensive: GET /v1/profiles does not authorize
// per role today (the backend never returns 403 on list), so that branch only
// fires if a future backend change adds one. `error` stays the transient-only
// label so its existing role="alert" and retry copy keep meaning "this should
// have worked, try again".
type PickerState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'forbidden' }
  | { status: 'error' }
  | { status: 'ready'; profiles: ProfileView[] }

/**
 * Kid-surface entry point (wireframe 4.1): a 2-column avatar grid; picking a
 * profile lands the child in their own library. The book-status pill
 * (wireframe 4.1) is deferred: a child principal cannot read sibling
 * profiles' libraries (authorize_profile), so the pill needs a bulk status
 * endpoint; tracked for C4a-6. The "Add Child" tile routes to the auth-gated
 * guardian surface, so kids cannot create profiles.
 */
export function ProfilePickerPage() {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const childSessionApi = useMemo(() => makeChildSessionApi(api), [api])
  const navigate = useNavigate()
  const [state, setState] = useState<PickerState>({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)
  // Guards against a rapid double-click firing two concurrent mints for the
  // same (or a different) profile. Every pick path ends in navigation, which
  // unmounts this page, so the flag is latched and never reset.
  const pickInFlightRef = useRef(false)

  // #ASSUME: external-resources: minting the child session (G1 / P6-04) can
  // fail (network blip, a guardian session that expired between page load
  // and this click). A mint failure must not trap the child on the picker:
  // useApi's request interceptor already falls back to the guardian token
  // (if any) on a kid-token route with no child session, identical to
  // pre-G1 behavior, so navigation proceeds either way. The mint call itself
  // runs while still on `/kids`, which useApi deliberately excludes from its
  // kid-token routes (see childSession.ts's isKidTokenRoute), so it carries
  // the guardian bearer as required by the backend's guardian-or-admin gate.
  // #VERIFY: ProfilePickerPage.test.tsx "mints and stores a child session
  // before navigating" and "still navigates when the mint call fails".
  const pickProfile = useCallback(
    async (profileId: string) => {
      if (pickInFlightRef.current) return
      pickInFlightRef.current = true
      // #CRITICAL: security: clear any prior child session BEFORE minting.
      // Otherwise a failed mint for THIS profile would leave a still-valid
      // session for a PREVIOUSLY picked profile in storage, and useApi's
      // interceptor would attach that stale token on /library/<thisProfile>,
      // producing a confusing cross-profile 403 gate instead of the clean
      // guardian-token fallback this handler's failure path relies on.
      // #VERIFY: ProfilePickerPage.test.tsx "clears a prior session before
      // minting so a failed mint does not carry the old token".
      clearChildSession()
      try {
        const session = await childSessionApi.mint(profileId)
        setChildSession({
          token: session.token,
          expiresAt: session.expires_at,
          profileId: session.profile_id,
        })
      } catch (err) {
        // Redacted shape only, never the raw axios error; see logApiError.
        logApiError('child session mint failed', err)
      }
      void navigate(`/library/${profileId}`)
    },
    [childSessionApi, navigate]
  )

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ status: 'loading' })
      try {
        const profiles = await profilesApi.list()
        if (!cancelled) setState({ status: 'ready', profiles })
      } catch (err) {
        // Redacted shape only, never the raw axios error (its `config` carries
        // the Authorization header); see logApiError.
        logApiError('profile list failed', err)
        if (!cancelled) {
          const { kind } = classifyApiError(err)
          if (kind === 'unauthenticated') setState({ status: 'unauthenticated' })
          else if (kind === 'forbidden') setState({ status: 'forbidden' })
          else setState({ status: 'error' })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, reloadKey])

  if (state.status === 'loading') {
    return (
      <div role="status" aria-live="polite" className="picker-loading">
        Loading profiles…
      </div>
    )
  }

  if (state.status === 'unauthenticated') {
    return (
      <div role="status" aria-live="polite">
        <EmptyState
          title="Ask a grown-up to help"
          description="A grown-up needs to sign in before you can pick who's reading."
          icon={<Mascot size={96} />}
          actions={
            <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
              I am a grown-up
            </Link>
          }
        />
      </div>
    )
  }

  if (state.status === 'forbidden') {
    return (
      <div role="status" aria-live="polite">
        <EmptyState
          title="We can't show this right now"
          description="Ask a grown-up to take a look."
          icon={<Mascot size={96} />}
          actions={
            <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
              I am a grown-up
            </Link>
          }
        />
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div role="alert">
        <EmptyState
          title="Oops, we hit a snag"
          description="We could not load your profiles right now."
          actions={
            <>
              <button
                type="button"
                className="picker-retry"
                onClick={() => setReloadKey((k) => k + 1)}
              >
                Try again
              </button>
              <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
                I am a grown-up
              </Link>
            </>
          }
        />
      </div>
    )
  }

  if (state.profiles.length === 0) {
    return (
      <EmptyState
        title="No profiles yet"
        description="Ask a grown-up to add you!"
        actions={
          <Link className="picker-tile__add-link" to="/guardian/profiles">
            I am a grown-up
          </Link>
        }
      />
    )
  }

  return (
    <section className="picker">
      <div className="picker__hello">
        <Mascot size={88} />
        <h1 className="picker__title">Who&apos;s reading?</h1>
      </div>
      <ul className="picker__grid">
        {state.profiles.map((profile) => (
          <li key={profile.id}>
            <Link
              className="picker-tile"
              to={`/library/${profile.id}`}
              // A profile pick must mint a child session BEFORE navigating
              // (see pickProfile above), so the default immediate Link
              // navigation is suppressed in favor of the async flow; `to`
              // is kept so the tile still renders a real, inspectable href.
              onClick={(e) => {
                // Preserve the browser's native open-in-new-tab/window
                // affordances: a modified or non-primary click must fall
                // through to the real href instead of being hijacked into the
                // async mint-then-navigate flow (which only drives the current
                // tab). Only a plain left click runs the mint.
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) {
                  return
                }
                e.preventDefault()
                void pickProfile(profile.id)
              }}
            >
              <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
              <span className="picker-tile__name">{profile.display_name}</span>
            </Link>
          </li>
        ))}
        <li>
          <Link className="picker-tile picker-tile--add" to="/guardian/profiles">
            <AvatarCircle avatar={null} name="+" />
            <span className="picker-tile__name">Add Child</span>
          </Link>
        </li>
      </ul>
    </section>
  )
}
