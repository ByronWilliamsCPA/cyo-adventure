import { isAxiosError } from 'axios'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { clearChildSession, setChildSession } from '../auth/childSession'
import { hasGuardianSession } from '../auth/guardianToken'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { makeChildSessionApi } from './childSessionApi'
import { Mascot } from './Mascot'
import { setReadAloudPreference } from './readAloudPreference'

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

// P6-07: the PIN prompt shown after picking a PIN-protected profile. `wrong`
// is deliberately gentle-retry-only copy (the child just mistyped, a grown-up
// already signed in); `trouble` is the kid-safe transient copy for a network
// blip or server error, so a correct-PIN child is never told their PIN was
// wrong when the request itself failed. An expired guardian session (401)
// leaves the prompt entirely for the ask-a-grown-up gate.
type PinPrompt = {
  profile: ProfileView
  status: 'idle' | 'checking' | 'wrong' | 'trouble'
  /** Consecutive wrong-PIN attempts, for the "ask a grown-up" escape (UX-K6). */
  attempts?: number
}

// After this many wrong tries, offer an "ask a grown-up" way out so a child who
// forgot their PIN is not stuck retrying forever.
const PIN_ATTEMPTS_BEFORE_HELP = 3

// The backend's mint endpoint signals a failed PIN check with a 403 whose
// body carries the distinct PIN_MISMATCH code (api/child_sessions.py); any
// other failure shape must NOT be presented as "wrong PIN".
function isPinMismatch(error: unknown): boolean {
  if (!isAxiosError(error) || error.response?.status !== 403) return false
  const data: unknown = error.response.data
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as { code?: unknown }).code === 'PIN_MISMATCH'
  )
}

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
  // The typed PIN lives ONLY in this transient state: cleared after every
  // attempt and never written to localStorage, sessionStorage, or anywhere
  // else (setChildSession stores the minted token, not the PIN).
  const [pinPrompt, setPinPrompt] = useState<PinPrompt | null>(null)
  const [pin, setPin] = useState('')
  // Guards against a rapid double-click firing two concurrent mints for the
  // same (or a different) profile. Every pick path ends in navigation, which
  // unmounts this page, so the flag is latched and never reset.
  const pickInFlightRef = useRef(false)
  // Whether to surface the guardian-only "Add Child" tile. `/kids` is reached
  // two ways: by a signed-in guardian (before they hand off the device) and,
  // under ADR-014 device grants, by a kid on a device that holds only a device
  // grant and no guardian session. Adding a child is a guardian action gated by
  // ProtectedRoute, so on a kid-only device the tile would bounce a child to
  // the guardian password screen (a dead end). Show it only when a grown-up is
  // actually signed in.
  // #ASSUME: concurrency: the value is seeded once at mount, but a guardian
  // sign-in or sign-out can also happen in ANOTHER tab on the same device while
  // this picker stays open (a grown-up signs out elsewhere, then hands the
  // tablet over). The `storage` event fires in every OTHER tab when
  // localStorage changes, so re-reading on it keeps the tile in sync without a
  // remount. A same-tab change cannot strand this snapshot: the kid surface is
  // mounted outside AuthProvider and never mutates the guardian token itself.
  // #VERIFY: ProfilePickerPage.test.tsx "reveals/hides the Add Child tile when
  // a guardian session appears/disappears in another tab".
  const [guardianSignedIn, setGuardianSignedIn] = useState(hasGuardianSession)
  useEffect(() => {
    const sync = () => setGuardianSignedIn(hasGuardianSession())
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

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
  //
  // Takes the full ProfileView (not just its id): this is the one place the
  // kid surface holds the profile's `tts_enabled` flag (K7 / Phase 4b
  // read-aloud), so it caches it here for ReaderRoute to read back later
  // (readAloudPreference.ts) rather than adding a second /v1/profiles fetch
  // on every reader page load.
  const pickProfile = useCallback(
    async (profile: ProfileView) => {
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
      // Cached regardless of whether the mint below succeeds: it only gates
      // a UI control (never an authorization decision), and the reader still
      // renders on a mint failure via the guardian-token fallback described
      // above, so the read-aloud toggle should still be able to appear then.
      setReadAloudPreference(profile.id, profile.tts_enabled)
      try {
        const session = await childSessionApi.mint(profile.id)
        setChildSession({
          token: session.token,
          expiresAt: session.expires_at,
          profileId: session.profile_id,
        })
      } catch (err) {
        // Redacted shape only, never the raw axios error; see logApiError.
        logApiError('child session mint failed', err)
      }
      void navigate(`/library/${profile.id}`)
    },
    [childSessionApi, navigate]
  )

  // #ASSUME: security: unlike the pin-less path above, a PIN-gated mint must
  // NOT navigate on failure: useApi's interceptor would fall back to the
  // guardian token on the library route, silently bypassing the lock. So this
  // flow stays on the prompt and classifies the failure: only the backend's
  // explicit 403 PIN_MISMATCH shows the wrong-PIN retry copy; an expired
  // guardian session (401) routes to the ask-a-grown-up gate exactly like a
  // failed profile load; anything else (network blip, 5xx) gets its own
  // kid-safe try-again-later copy, so a child typing the CORRECT PIN during
  // an outage is never told the PIN was wrong.
  // #VERIFY: ProfilePickerPage.test.tsx PIN-gate suite covers the wrong-PIN,
  // expired-guardian (401), and network/5xx branches separately.
  const submitPin = useCallback(async () => {
    // The minimum PIN length is 4 (schemas.PinCode); a shorter submit (e.g.
    // Enter with 1-3 digits typed) would be a guaranteed 403 shown as
    // "wrong PIN", so it is refused here to match the button's disabled gate.
    if (!pinPrompt || pin.length < 4 || pinPrompt.status === 'checking') return
    const target = pinPrompt.profile
    const attempt = pin
    // Carry the running attempt count through the 'checking' transition so the
    // wrong-PIN branch below increments it instead of resetting to 1 (UX-K6).
    setPinPrompt((prev) => ({ profile: target, status: 'checking', attempts: prev?.attempts }))
    setPin('')
    try {
      const session = await childSessionApi.mint(target.id, attempt)
      setChildSession({
        token: session.token,
        expiresAt: session.expires_at,
        profileId: session.profile_id,
      })
      // Unlike the pin-less path, this only runs on a confirmed-correct PIN:
      // a wrong-PIN attempt must not seed the toggle for a profile the child
      // has not actually proven they may read as.
      setReadAloudPreference(target.id, target.tts_enabled)
      setPinPrompt(null)
      void navigate(`/library/${target.id}`)
    } catch (err) {
      // Redacted shape only, never the raw axios error; see logApiError.
      logApiError('child session mint failed', err)
      if (isPinMismatch(err)) {
        setPinPrompt((prev) => ({
          profile: target,
          status: 'wrong',
          attempts: (prev?.attempts ?? 0) + 1,
        }))
        return
      }
      const { kind } = classifyApiError(err)
      if (kind === 'unauthenticated') {
        // The guardian session expired between page load and this submit; no
        // amount of correct-PIN retrying can succeed until a grown-up signs
        // back in, so leave the prompt for the same gate a failed load shows.
        setPinPrompt(null)
        setState({ status: 'unauthenticated' })
      } else if (kind === 'forbidden') {
        // A non-PIN 403 (role/family rejection) is permanent for this
        // session; retrying the PIN can never fix it.
        setPinPrompt(null)
        setState({ status: 'forbidden' })
      } else {
        setPinPrompt({ profile: target, status: 'trouble' })
      }
    }
  }, [childSessionApi, navigate, pin, pinPrompt])

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

  if (pinPrompt) {
    const busy = pinPrompt.status === 'checking'
    return (
      <section className="picker">
        <div className="picker__hello">
          <Mascot size={88} />
          <h1 className="picker__title">Hi {pinPrompt.profile.display_name}!</h1>
        </div>
        <form
          className="picker-pin"
          onSubmit={(e) => {
            e.preventDefault()
            void submitPin()
          }}
        >
          <label className="picker-pin__label" htmlFor="picker-pin-input">
            Type your secret PIN
          </label>
          {/* type=password keeps siblings from shoulder-reading; numeric
              inputMode brings up the digit pad; autoComplete=off so no
              browser or password manager ever offers to store the PIN. */}
          <input
            id="picker-pin-input"
            className="picker-pin__input"
            type="password"
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete="off"
            maxLength={8}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/[^0-9]/g, ''))}
            disabled={busy}
          />
          {pinPrompt.status === 'wrong' ? (
            <p role="alert" className="picker-pin__retry">
              Hmm, that PIN didn&apos;t work. Give it another try!
            </p>
          ) : null}
          {(pinPrompt.attempts ?? 0) >= PIN_ATTEMPTS_BEFORE_HELP ? (
            // UX-K6: after a few wrong tries, a child who forgot their PIN needs
            // a way out instead of retrying forever.
            <p className="picker-pin__help">
              Forgot your PIN?{' '}
              <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
                Ask a grown-up
              </Link>
            </p>
          ) : null}
          {pinPrompt.status === 'trouble' ? (
            <p role="alert" className="picker-pin__retry">
              We couldn&apos;t check your PIN right now. Try again in a moment!
            </p>
          ) : null}
          <div className="picker-pin__actions">
            <button
              type="button"
              className="picker-retry picker-pin__back"
              disabled={busy}
              onClick={() => {
                setPin('')
                setPinPrompt(null)
              }}
            >
              Go back
            </button>
            <button type="submit" className="picker-retry" disabled={busy || pin.length < 4}>
              Let&apos;s read!
            </button>
          </div>
        </form>
      </section>
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
              // P6-07: a PIN-locked tile announces the gate up front. The
              // label starts with the visible name so voice-control users
              // can still say the name they see; PIN-less tiles keep their
              // contents-derived name (AvatarCircle is aria-hidden, so that
              // is just the display name).
              aria-label={profile.has_pin ? `${profile.display_name} needs a PIN` : undefined}
              // A profile pick must mint a child session BEFORE navigating
              // (see pickProfile above), so the default immediate Link
              // navigation is suppressed in favor of the async flow; `to`
              // is kept so the tile still renders a real, inspectable href.
              // A PIN-protected profile (P6-07) detours through the PIN
              // prompt instead of minting straight away.
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
                if (profile.has_pin) {
                  setPin('')
                  setPinPrompt({ profile, status: 'idle' })
                } else {
                  void pickProfile(profile)
                }
              }}
            >
              <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
              <span className="picker-tile__name">{profile.display_name}</span>
              {/* P6-07: a PIN-locked profile shows a corner padlock so the
                  PIN prompt is anticipated, not a surprise. The glyph is
                  decorative (aria-hidden); the aria-label above carries the
                  "needs a PIN" hint for assistive tech. */}
              {profile.has_pin ? (
                <span className="picker-tile__pin" aria-hidden="true">
                  🔒
                </span>
              ) : null}
            </Link>
          </li>
        ))}
        {guardianSignedIn ? (
          <li>
            <Link className="picker-tile picker-tile--add" to="/guardian/profiles">
              <AvatarCircle avatar={null} name="+" />
              <span className="picker-tile__name">Add Child</span>
            </Link>
          </li>
        ) : null}
      </ul>
    </section>
  )
}
