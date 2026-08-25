import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { CharacterCreator } from '../characters/CharacterCreator'
import { CharacterPicker } from '../characters/CharacterPicker'
import { LOOK_SWATCHES } from '../characters/characterApi'
import { useActiveCharacter } from '../characters/useActiveCharacter'
import { makeRemoveDownload } from '../api/readerApi'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { useKidOutletContext } from '../kid/kidOutletContext'
import { EMPTY_PROGRESS, makeProgressApi, type ProgressSummary } from '../kid/progressApi'
import { Mascot } from '../kid/Mascot'
import { getOrCreateDeviceId } from '../offline/deviceId'
import {
  consumeDownloadEviction,
  consumeDownloadRefusal,
  OFFLINE_BUDGET_FULL_MESSAGE,
  OFFLINE_EVICTION_MESSAGE,
} from '../offline/downloadBudget'
import { evictStaleOfflineBooks, reconcileOfflineCache } from '../offline/revocation'
import { GUARDIAN_LOGIN_PATH, KID_PICKER_PATH } from '../routes'
import { cacheLibraryList, getCachedLibraryList, getCachedStorybook } from '../offline/db'
import { BookCard } from './BookCard'
import { EndingsGallery } from './EndingsGallery'
import { makeLibraryApi, type LibraryItemView, type ReadingHistoryItem } from './libraryApi'
import { pickHero } from './pickHero'
import { makeRecommendationsApi, type RecommendationItem } from './recommendationsApi'
import { summarizeRecommendations } from './recommendationsUtils'
import { RequestStory, type ContinueAnchor } from './RequestStory'
import './library.css'

// `unauthenticated` and `forbidden` are stable, expected gates (no grown-up
// signed in / this profile isn't the signed-in child's), not a flaky fetch;
// `error` stays the transient-only label so its existing retry copy keeps
// meaning "this should have worked, try again".
//
// `history` (K6 endings tracker) starts empty and fills in behind the
// items, best-effort: it must never gate or delay the shelf itself. An empty
// array is indistinguishable from "still loading" or "fetch failed", which
// is intentional: BookCard already withholds the badge for a book with no
// matching row, so every one of those cases degrades identically (absence,
// not an error state).
//
// `recommendations` (K17, ADR-016 rings 1-2) follows the exact same
// best-effort shape: starts empty, fills in behind the items, and a fetch
// failure degrades to "no chips" rather than an error state, per ADR-016
// design point 3 (kid-safe, never an error surface for a decoration).
type LibraryState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'forbidden' }
  | { status: 'error' }
  | {
      status: 'ready'
      items: LibraryItemView[]
      history: ReadingHistoryItem[]
      recommendations: RecommendationItem[]
    }
  // Offline fallback (UX-K1): the network fetch failed but a cached shelf
  // exists. `downloaded` holds the ids of books whose blob is in the local
  // cache and can actually be opened offline.
  | { status: 'offline'; items: LibraryItemView[]; downloaded: Set<string> }

/** Which of these books have a downloaded blob available offline. */
async function downloadedIds(items: LibraryItemView[]): Promise<Set<string>> {
  const results = await Promise.all(
    items.map(async (item) => {
      try {
        return (await getCachedStorybook(item.id, item.version)) ? item.id : null
      } catch {
        return null
      }
    })
  )
  return new Set(results.filter((id): id is string => id !== null))
}

export interface LibraryPageProps {
  /**
   * Guardian preview-as-child mode (frontend/src/guardian/PreviewAsChildPage.tsx):
   * suppresses every mutation affordance (rating, "ask for the next book",
   * requesting a new story) and the book covers stop linking into the real
   * kid-token-gated Reader route, so a guardian previewing a child's shelf can
   * only look, never write data under that child's identity.
   */
  readOnly?: boolean
}

/**
 * Kid library home (wireframe 4.2): Continue Reading hero for the most
 * recently active book, then a More to Explore shelf grid for the rest.
 * The server already filters to published, approved, family-scoped books.
 */
export function LibraryPage({ readOnly = false }: LibraryPageProps = {}) {
  const { profileId } = useParams()
  const navigate = useNavigate()
  const api = useApi()
  const libraryApi = useMemo(() => makeLibraryApi(api), [api])
  const recommendationsApi = useMemo(() => makeRecommendationsApi(api), [api])
  const progressApi = useMemo(() => makeProgressApi(api, profileId), [api, profileId])
  // G15 storage/download view: reports a book's removal from this device's
  // offline cache to the guardian console. The only caller today is the
  // reconcileOfflineCache call in `load` below (the shared-content purge,
  // offline/revocation.ts's own `reportRemoval` option); best-effort and
  // fire-and-forget, mirroring ReaderRoute.tsx's `reportRemoval` for the
  // reader's own eviction path.
  const removeDownloadApi = useMemo(() => makeRemoveDownload(api), [api])
  const reportRemoval = useCallback(
    (storybookId: string) => {
      // #EDGE: external resources: guard a synchronous throw here, not just a
      // rejected promise, same reason as ReaderRoute.tsx's own reportRemoval:
      // reconcileOfflineCache calls this synchronously from inside its purge
      // loop, and the arguments are evaluated before .catch() is attached.
      // Defense in depth rather than the only guard: revocation.ts wraps this
      // callback too, so removing this try/catch does not by itself break the
      // shelf. It exists so this call site is safe on its own terms, the way
      // ReaderRoute's is, instead of depending on a caller's discipline.
      // #VERIFY: the load-bearing assertion is revocation.test.ts "a
      // synchronously-throwing reporter does not break the purge loop";
      // LibraryPage.test.tsx "finishes the shelf load when the device-id
      // lookup throws during a purge" covers the end-to-end containment.
      try {
        removeDownloadApi({
          deviceId: getOrCreateDeviceId(),
          storybookId,
        }).catch((err: unknown) => {
          // Redacted shape only, never the raw axios error; see logApiError.
          logApiError('device-download removal report failed', err)
        })
      } catch (err: unknown) {
        logApiError('device-download removal report could not be sent', err)
      }
    },
    [removeDownloadApi]
  )
  const [state, setState] = useState<LibraryState>({ status: 'loading' })
  // Task 8: which character (if any) is active for this profile, and the
  // toggle for the inline switcher below the heading. Fetched independently
  // of the shelf itself, the same best-effort-sibling shape as `progress`
  // above: this widget renders nothing unless the fetch resolves to
  // 'ready', so it can never gate or delay the shelf.
  //
  // KidShell already resolves this for the library route and hands it down
  // through the Outlet, so the routed kid library reuses that one lookup
  // instead of issuing a duplicate GET /v1/characters. The local hook below
  // stays for the mounts that have no KidShell above them (the guardian
  // preview-as-child route), and is passed `undefined` when the shell
  // supplied one, which makes it fetch nothing at all. Both branches must
  // be present unconditionally: a hook cannot be called conditionally.
  const kidOutlet = useKidOutletContext()
  const shellActiveCharacter = kidOutlet?.activeCharacter ?? null
  // `readOnly` (guardian preview-as-child, see LibraryPageProps) also
  // suppresses the fetch, not just the KidShell branch above: the whole
  // character section below is gated on `!readOnly && ...` and its result is
  // never rendered in preview mode, so issuing GET /v1/characters on every
  // PreviewAsChildPage mount was a live network call for a value that could
  // never be shown. `readOnly` is a prop, not state, so this cannot change
  // the number of hooks called across renders.
  const ownActiveCharacter = useActiveCharacter(
    shellActiveCharacter || readOnly ? undefined : profileId
  )
  const activeCharacter = shellActiveCharacter ?? ownActiveCharacter
  const [showCharacterPicker, setShowCharacterPicker] = useState(false)
  // Owner decision (gate-rework): a click on a gated card (needsCharacterFor
  // below) parks its read target here instead of navigating immediately, so
  // the creator can be shown in the card's place and the child still lands
  // in the read they chose once one exists. Replaces an earlier design where
  // KidShell gated the whole library route on "this profile has no
  // character yet", which hard-gated every kid with no skip affordance even
  // though zero catalog books could use one.
  const [pendingRead, setPendingRead] = useState<{
    to: string
    state?: { personalizationEligible: boolean }
  } | null>(null)
  const handleNeedsCharacter = useCallback(
    (to: string, state?: { personalizationEligible: boolean }) => setPendingRead({ to, state }),
    []
  )
  // W3.2: the Endings Gallery / "Every path walked!" data source, fetched
  // independently of the shelf (best-effort, like history/recommendations):
  // a failed or slow fetch degrades to no ribbon and no gallery button,
  // never an error state for the shelf itself.
  const [progress, setProgress] = useState<ProgressSummary>(EMPTY_PROGRESS)
  // #ASSUME: data integrity: EMPTY_PROGRESS is indistinguishable from a real
  // empty result, so the gallery needs to know WHY it has nothing. Without
  // this, a failed fetch opens the modal on the empty-state copy ("Keep
  // reading to start finding endings!"), and it does so in the one place the
  // contradiction is visible on screen: the gallery BUTTON is gated on
  // `endingsFor`, which reads reading HISTORY, a separate fetch. So a child
  // whose card badge reads "3 of 5" can tap through to a modal telling them
  // they have found none. `/v1/me/progress` is child-principal-only, so a
  // guardian previewing as their child hits this every time via a 403.
  // 'loading' shares the unavailable branch: the fetch starts on mount so a
  // tap almost always lands after it settles, but "we could not load this
  // yet" is the honest thing to say in the window where it has not.
  // #VERIFY: LibraryPage.test.tsx "does not report an empty ending collection
  // when the progress fetch failed".
  const [progressLoad, setProgressLoad] = useState<{
    profileId: string
    status: 'ready' | 'failed'
  } | null>(null)
  // Stored WITH the profile it belongs to and derived during render, rather
  // than reset to 'loading' inside the effect: that would be a synchronous
  // setState in an effect body (react-hooks/set-state-in-effect). The derived
  // form is also the more correct one, since it makes a settled result
  // implicitly stale the moment the profile changes instead of relying on a
  // reset to land first.
  const progressStatus: 'loading' | 'ready' | 'failed' =
    progressLoad !== null && progressLoad.profileId === profileId ? progressLoad.status : 'loading'
  useEffect(() => {
    if (!profileId) return undefined
    let cancelled = false
    progressApi
      .getProgress()
      .then((result) => {
        if (cancelled) return
        setProgress(result)
        setProgressLoad({ profileId, status: 'ready' })
      })
      .catch((err: unknown) => {
        logApiError('progress fetch failed', err)
        if (!cancelled) setProgressLoad({ profileId, status: 'failed' })
      })
    return () => {
      cancelled = true
    }
  }, [progressApi, profileId])
  // The Endings Gallery modal: at most one open at a time, keyed by the
  // storybook id it is showing. `null` means closed.
  const [galleryStorybookId, setGalleryStorybookId] = useState<string | null>(null)
  // W4.3: a story download refused during a PAST reader session (offline
  // storage budget, D20) surfaces here, once, the next time this profile's
  // shelf loads. LibraryPage is the reachable kid-facing surface for this:
  // ReaderPage.tsx (the only place a download is actually initiated) is out
  // of scope for this change, so it cannot show the refusal copy directly;
  // see offline/downloadBudget.ts for the full flow.
  const [budgetFull, setBudgetFull] = useState(false)
  // Same flow, opposite outcome: a book WAS saved, and an older one was
  // removed to make room. Reported separately because the refusal copy
  // ("bookshelf is full") would be actively wrong here.
  const [evicted, setEvicted] = useState(false)
  const [continueAnchor, setContinueAnchor] = useState<ContinueAnchor | null>(null)
  // Bumped by the shelf's "Ask for a new story" end-cap tile; RequestStory
  // opens on the bump and the effect below brings the form into view. A
  // counter (not a boolean) so every tap re-triggers, even with the form
  // already open.
  const [requestOpenSignal, setRequestOpenSignal] = useState(0)
  const requestStoryRef = useRef<HTMLDivElement>(null)

  const askForNextBook = useCallback(
    (item: LibraryItemView) => setContinueAnchor({ id: item.id, title: item.title }),
    []
  )
  const clearContinueAnchor = useCallback(() => setContinueAnchor(null), [])
  const askForNewStory = useCallback(() => setRequestOpenSignal((signal) => signal + 1), [])

  // Smooth only when nothing asks for reduced motion: the OS-level media
  // query OR the guardian-set profile flag (data-reduce-motion on the kid
  // shell, band-tokens.css), mirroring Reader.tsx's passage scroll.
  const scrollRequestIntoView = useCallback(() => {
    const reduceMotion =
      (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false) ||
      Boolean(requestStoryRef.current?.closest('[data-reduce-motion="true"]'))
    // Optional-call scrollIntoView: it is absent under jsdom (test env) and
    // guarding keeps the focus move working there without a test shim.
    requestStoryRef.current?.scrollIntoView?.({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    })
    requestStoryRef.current?.focus()
  }, [])

  // #ASSUME: UI state: tapping "Ask for the next book" opens the RequestStory
  // form at the top of the page with no visual cue near the tapped card;
  // without moving focus/scroll, a keyboard or low-vision user has no way to
  // notice the form appeared.
  // #VERIFY: whenever continueAnchor becomes non-null, the form container is
  // scrolled into view and receives focus.
  useEffect(() => {
    if (continueAnchor !== null) {
      scrollRequestIntoView()
    }
  }, [continueAnchor, scrollRequestIntoView])

  // The end-cap tile's twin of the anchor effect above: same wayfinding rule
  // (opening something far away must move the reader there), keyed on its
  // own signal so clearing an anchor never re-scrolls.
  useEffect(() => {
    if (requestOpenSignal > 0) {
      scrollRequestIntoView()
    }
  }, [requestOpenSignal, scrollRequestIntoView])

  // #ASSUME: timing dependencies: the "Try again" button calls `load()`
  // directly and discards its cleanup, so `cancelled` alone cannot stop a
  // stale setState if the component unmounts while that manual retry is
  // still in flight (the effect-driven call is still covered by `cancelled`
  // via its own cleanup).
  // #VERIFY: `isMountedRef` closes that gap; every setState below checks it
  // alongside `cancelled` before writing state.
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // #ASSUME: timing dependencies: the fetch below can outlive its effect
  // (profileId changes, or a manual retry re-fires while the prior request
  // is still in flight).
  // #VERIFY: `cancelled` guards every setState so a stale response never
  // clobbers a newer one; the setState calls live in a nested async
  // function, not the effect body itself, per the set-state-in-effect rule.
  const load = useCallback(() => {
    if (!profileId) return undefined
    const id = profileId
    let cancelled = false
    async function fetchItems() {
      setState({ status: 'loading' })
      try {
        const items = await libraryApi.list(id)
        // Cache the last-good shelf so an offline kid still has a bookshelf.
        void cacheLibraryList(id, items).catch(() => undefined)
        if (cancelled || !isMountedRef.current) return
        setState({ status: 'ready', items, history: [], recommendations: [] })
        // Offline-copy revocation (roadmap Phase 5, register G8/A5): this shelf
        // fetch just succeeded, so `items` is the authoritative set of books
        // this profile may read. Reconcile the device's offline cache against
        // it so an archived/pulled/unassigned book is removed from local
        // storage at this connection, not just hidden from the shelf. Fire-
        // and-forget and best-effort, like history/recommendations below: a
        // reconcile failure (blocked storage, private browsing) must not
        // block the shelf from rendering. Deliberately placed only in this
        // success branch, never in the catch below: see revocation.ts's
        // #CRITICAL note on never purging after a failed fetch.
        reconcileOfflineCache(
          id,
          items.map((item) => item.id),
          { reportRemoval }
        ).catch((err: unknown) => {
          logApiError('offline cache reconcile failed', err)
        })
        // Content-staleness eviction, a sibling of the reconcile above and
        // deliberately not folded into it: revocation asks "may any profile
        // on this device still read this book", staleness asks "is the blob
        // this device cached still the blob the server serves". A version is
        // supposed to be immutable, but a blob rewritten in place under an
        // unchanged version (scripts/retrofit_personalization.py did exactly
        // that to 15 published rows) is invisible to a cache keyed on
        // `id@version`. Same placement rule as the reconcile: ONLY in this
        // success branch, never in the catch below, because both purge local
        // state on the strength of this response being authoritative. Fire-
        // and-forget for the same reason too: it evicts only, and the
        // re-download is ReaderPage's existing cache-miss path.
        evictStaleOfflineBooks(items).catch((err: unknown) => {
          logApiError('offline stale-content eviction failed', err)
        })
        // K6 endings tracker: best-effort and deliberately NOT awaited above.
        // A failure (or a slow response) here must never delay or block the
        // shelf itself from rendering; the badges just stay absent until this
        // resolves, or forever on failure.
        libraryApi
          .history(id)
          .then((history) => {
            if (!cancelled && isMountedRef.current) {
              setState((prev) => (prev.status === 'ready' ? { ...prev, history } : prev))
            }
          })
          .catch((err: unknown) => {
            // Redacted shape only, never the raw axios error; see logApiError.
            logApiError('reading history fetch failed', err)
          })
        // K17 recommendations feed (ADR-016 rings 1-2): same best-effort
        // shape as history above, deliberately NOT awaited. A failure (or a
        // slow response, e.g. the sibling backend endpoint still landing)
        // must never delay or error the shelf; the chips just stay absent
        // until this resolves, or forever on failure.
        recommendationsApi
          .list(id)
          .then((recommendations) => {
            if (!cancelled && isMountedRef.current) {
              setState((prev) => (prev.status === 'ready' ? { ...prev, recommendations } : prev))
            }
          })
          .catch((err: unknown) => {
            // Redacted shape only, never the raw axios error; see logApiError.
            logApiError('recommendations fetch failed', err)
          })
      } catch (err) {
        // Redacted shape only, never the raw axios error (its `config` carries
        // the Authorization header); see logApiError.
        logApiError('library list failed', err)
        if (cancelled || !isMountedRef.current) return
        const { kind } = classifyApiError(err)
        if (kind === 'unauthenticated') {
          setState({ status: 'unauthenticated' })
          return
        }
        if (kind === 'forbidden') {
          setState({ status: 'forbidden' })
          return
        }
        // Transient/offline: fall back to the cached shelf if we have one, so
        // the child never hits a dead-end "Try again" that can't succeed
        // offline (UX-K1). Only truly cache-less failures reach the error state.
        const cached = await getCachedLibraryList(id).catch(() => undefined)
        if (cancelled || !isMountedRef.current) return
        if (cached && cached.length > 0) {
          const downloaded = await downloadedIds(cached)
          if (cancelled || !isMountedRef.current) return
          setState({ status: 'offline', items: cached, downloaded })
        } else {
          setState({ status: 'error' })
        }
      }
    }
    void fetchItems()
    return () => {
      cancelled = true
    }
  }, [libraryApi, recommendationsApi, profileId, reportRemoval])

  useEffect(load, [load])

  // W4.3: check once per mount, not per `load()` call, so a retry ("Try
  // again") does not re-show a banner already consumed this page view.
  // #ASSUME: timing dependencies: deferred through setTimeout(fn, 0) rather
  // than calling setBudgetFull directly in the effect body; a direct call
  // here would set state synchronously from inside the effect, which
  // `react-hooks/set-state-in-effect` flags as a cascading-render risk (the
  // established fix elsewhere in this codebase, e.g. guardian/BudgetBanner.tsx).
  useEffect(() => {
    const timer = setTimeout(() => {
      if (consumeDownloadRefusal()) {
        setBudgetFull(true)
      }
      if (consumeDownloadEviction()) {
        setEvicted(true)
      }
    }, 0)
    return () => clearTimeout(timer)
  }, [])

  // Offline-copy revocation (roadmap Phase 5, G8/A5): re-fetch on reconnect
  // too, not just on mount. A device can sit on this page through a
  // connectivity drop and recovery; the 'online' event re-runs `load()`,
  // whose success path above reconciles the offline cache, so a book pulled
  // while this device was offline is still caught at "next connection"
  // instead of only at the next full page load. Mirrors
  // useReplayOnReconnect's mount+online pattern (hooks/useReplayOnReconnect.ts).
  useEffect(() => {
    const onOnline = () => load()
    window.addEventListener('online', onOnline)
    return () => window.removeEventListener('online', onOnline)
  }, [load])

  const rate = useCallback(
    (storybookId: string, value: number) => {
      if (!profileId) return
      libraryApi
        .rate(profileId, storybookId, value)
        .then((view) =>
          setState((prev) =>
            prev.status === 'ready'
              ? {
                  ...prev,
                  items: prev.items.map((item) =>
                    item.id === view.storybook_id ? { ...item, rating: view.value } : item
                  ),
                }
              : prev
          )
        )
        .catch((err: unknown) => {
          // A 401 means the session is dead (the useApi interceptor already
          // cleared the token), so every rating and refetch from here on would
          // fail too; surface the ask-a-grown-up gate instead of a page that
          // silently stops responding.
          if (classifyApiError(err).kind === 'unauthenticated') {
            if (isMountedRef.current) setState({ status: 'unauthenticated' })
            return
          }
          // Otherwise keep the previous rating; a transient failure must not
          // break browsing. Redacted shape only, never the raw axios error
          // (its `config` carries the Authorization header); see logApiError.
          logApiError('rating save failed', err)
        })
    },
    [libraryApi, profileId]
  )

  if (!profileId) return null
  // Rendered ahead of every load-state branch below, and regardless of
  // `state.status`, so a background refetch flipping back to 'loading' (the
  // 'online' reconnect effect above, or a manual retry) can never yank the
  // creator out from under a child mid-form.
  // #ASSUME: timing dependencies: `activeCharacter.refresh()` and
  // `navigate()` both fire from `onCreated` without waiting on each other;
  // the read target was already fixed when the gate first triggered, so
  // refresh's result is not needed to decide where to go next.
  // #VERIFY: LibraryPage.test.tsx "LibraryPage character gate" suite, "lands
  // in the read the child originally chose after creating a character".
  if (pendingRead) {
    const target = pendingRead
    return (
      <CharacterCreator
        profileId={profileId}
        // This creator was reached optionally (a tap on a gated book), not
        // the mandatory empty-profile path CharacterPicker.tsx renders, so a
        // child who got here by accident (or changed their mind) has a way
        // back to the shelf instead of being stuck with only "make a
        // character" and the browser Back button (which would leave
        // /library/:profileId entirely, since pendingRead is local state,
        // not a route).
        onBack={() => setPendingRead(null)}
        onCreated={() => {
          activeCharacter.refresh()
          setPendingRead(null)
          void navigate(target.to, { state: target.state })
        }}
      />
    )
  }
  if (state.status === 'loading') {
    // Branded, kid-facing loading state (Pip + short reassurance), matching
    // the reader's "Opening your story…" pattern so every wait on the kid
    // surface looks like the same friendly app, not a bare system message.
    return (
      <div className="library__loading" role="status" aria-live="polite">
        <Mascot size={96} className="library__loading-mascot" />
        <p className="library__loading-text">Loading your books…</p>
      </div>
    )
  }
  if (state.status === 'unauthenticated') {
    return (
      <div className="library" role="status" aria-live="polite">
        <EmptyState
          title="Time to find your grown-up"
          description="Your grown-up needs to sign in again before your books can load."
          icon={<Mascot size={96} />}
          actions={
            <>
              <Link className="picker-tile__add-link" to={KID_PICKER_PATH}>
                Back to Who&apos;s reading?
              </Link>
              <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
                I am a grown-up
              </Link>
            </>
          }
        />
      </div>
    )
  }
  if (state.status === 'forbidden') {
    return (
      <div className="library" role="status" aria-live="polite">
        <EmptyState
          title="This bookshelf isn't yours"
          description="Let's go back and pick your own name."
          icon={<Mascot size={96} />}
          actions={
            <Link className="picker-tile__add-link" to={KID_PICKER_PATH}>
              Back to Who&apos;s reading?
            </Link>
          }
        />
      </div>
    )
  }
  if (state.status === 'error') {
    return (
      <div className="library">
        <EmptyState
          title="We lost the bookshelf"
          description="Something went wrong loading your books."
          icon={<Mascot size={96} />}
          actions={
            <>
              <Button variant="primary" size="lg" onClick={load}>
                Try again
              </Button>
              <Link className="picker-tile__add-link" to={KID_PICKER_PATH}>
                Back to Who&apos;s reading?
              </Link>
            </>
          }
        />
      </div>
    )
  }
  const { items } = state
  const offline = state.status === 'offline'
  // UX-K1 offline shelf: only an offline state carries a downloaded-blob set;
  // online, every assigned book is openable, so isDownloaded is always true.
  const offlineDownloaded = state.status === 'offline' ? state.downloaded : null
  const isDownloaded = (item: LibraryItemView): boolean =>
    offlineDownloaded === null || offlineDownloaded.has(item.id)
  // ADR-028 / gate-rework: the positive signal only. `accepts_character`
  // undefined or false, or an active-character status other than exactly
  // 'none' ('loading', 'error', 'unauthenticated', 'forbidden', 'ready'),
  // all skip the gate and go straight to the read. Failing open on every
  // unknown character status is deliberate: the backend already treats an
  // unseeded read as normal (`_bind_active_character` returns `(None,
  // None)`), so the worst case is a read without a character, never a child
  // locked out of a book they are allowed to read.
  // #ASSUME: data integrity: `item.accepts_character === true` is the only
  // positive signal; `undefined` reads as `false`, never as "needs one".
  // #VERIFY: LibraryPage.test.tsx "LibraryPage character gate" suite.
  const needsCharacterFor = (item: LibraryItemView): boolean =>
    item.accepts_character === true && activeCharacter.state.status === 'none'
  // K6/K17 decorations only exist on a live (ready) fetch; an offline shelf has
  // neither history nor recommendations, so both degrade to no badges.
  const history = state.status === 'ready' ? state.history : []
  const recommendations = state.status === 'ready' ? state.recommendations : []
  // K6 endings tracker: keyed by storybook id so BookCard can look up its own
  // row in O(1); a book with no row (history still loading, fetch failed, or
  // genuinely no completion yet) gets `undefined` and BookCard renders no badge.
  const historyByBook = new Map(history.map((row) => [row.storybook_id, row]))
  const endingsFor = (item: LibraryItemView): { found: number; total: number } | undefined => {
    const row = historyByBook.get(item.id)
    return row ? { found: row.endings_found, total: row.total_endings } : undefined
  }
  // K17 recommendations feed (ADR-016 rings 1-2): same lookup shape as
  // history above. Recommendations only ever decorate a book already on this
  // shelf (per design: no separate unassigned-books browse, that would
  // bypass the assignment gate), so any feed entry for a book absent from
  // `items` is simply never looked up and never rendered.
  const recommendationsByBook = summarizeRecommendations(recommendations)
  const recommendationFor = (item: LibraryItemView) => recommendationsByBook.get(item.id)
  // W3.2: keyed by storybook id, same shape as historyByBook above. A book
  // with no row (progress fetch still loading, failed, or genuinely no
  // completion yet) gets no ribbon. It does NOT get "no gallery button": the
  // button is gated on `endingsFor`, which comes from reading history, so it
  // can be present while this map is empty. That gap is what `progressStatus`
  // above exists to close.
  const progressByBook = new Map(progress.books.map((book) => [book.storybook_id, book]))
  const everyPathWalkedFor = (item: LibraryItemView): boolean =>
    progressByBook.get(item.id)?.every_path_walked ?? false
  const galleryBook = galleryStorybookId ? progressByBook.get(galleryStorybookId) : undefined
  const galleryItem = galleryStorybookId
    ? items.find((item) => item.id === galleryStorybookId)
    : undefined
  if (items.length === 0) {
    return (
      <div className="library">
        <EmptyState
          title="No books yet"
          description="Ask a grown-up to add one!"
          icon={<Mascot size={96} />}
        />
        {readOnly ? null : <RequestStory profileId={profileId} />}
      </div>
    )
  }
  const hero = pickHero(items)
  const shelf = items
    .filter((item) => item.id !== hero?.id)
    .sort((a, b) => a.title.localeCompare(b.title))
  // Requesting (a new story, or a series continuation) needs the network:
  // offline, the form and the "Ask for the next book" taps could only end in
  // a failure message, so neither affordance renders then. readOnly (guardian
  // preview) suppresses them for the write-isolation reasons documented on
  // LibraryPageProps.
  const canRequest = !readOnly && !offline
  return (
    <div className="library">
      <h1 className="library__heading">My Books</h1>
      {/* Suppressed under readOnly (guardian preview-as-child): a guardian
          previewing a child's shelf can look but never switch or create that
          child's character, mirroring RequestStory's own suppression above. */}
      {!readOnly && activeCharacter.state.status === 'ready' ? (
        <section className="library__character" aria-label="Your character">
          <p className="library__character-current">
            {/* Decorative: the visible "Playing as <name>" text already
                carries the accessible name, so the swatch is never
                announced twice by assistive tech. */}
            <span className="library__character-avatar" aria-hidden="true">
              {LOOK_SWATCHES[activeCharacter.state.character.look]}
            </span>
            Playing as <strong>{activeCharacter.state.character.name}</strong>
          </p>
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={showCharacterPicker}
            onClick={() => setShowCharacterPicker((open) => !open)}
          >
            {showCharacterPicker ? 'Hide characters' : 'Switch character'}
          </Button>
          {showCharacterPicker ? (
            <CharacterPicker
              profileId={profileId}
              onActiveCharacterChange={() => {
                activeCharacter.refresh()
                setShowCharacterPicker(false)
              }}
            />
          ) : null}
        </section>
      ) : null}
      {offline ? (
        <p className="library__offline-banner" role="status">
          No internet. These books are ready to read.
        </p>
      ) : null}
      {budgetFull ? (
        <p className="library__offline-banner" role="status">
          {OFFLINE_BUDGET_FULL_MESSAGE}
        </p>
      ) : null}
      {evicted ? (
        <p className="library__offline-banner" role="status">
          {OFFLINE_EVICTION_MESSAGE}
        </p>
      ) : null}
      {hero ? (
        <section aria-label="Continue Reading">
          {/* A visible name for the hero spot (the section aria-label alone
              gave sighted kids no cue why this book is big). A finished hero
              stays the most recent activity, so its invitation flips to a
              replay nudge instead of a nonsensical "keep reading". */}
          <h2 className="library__shelf-heading">
            {hero.progress?.completed ? 'Read it again?' : 'Keep reading'}
          </h2>
          <BookCard
            item={hero}
            profileId={profileId}
            hero
            onRate={rate}
            onContinue={canRequest ? askForNextBook : undefined}
            downloaded={isDownloaded(hero)}
            readOnly={readOnly}
            ratable={!offline}
            endings={endingsFor(hero)}
            recommendation={recommendationFor(hero)}
            everyPathWalked={everyPathWalkedFor(hero)}
            onOpenGallery={setGalleryStorybookId}
            needsCharacter={needsCharacterFor(hero)}
            onNeedsCharacter={handleNeedsCharacter}
          />
        </section>
      ) : null}
      {shelf.length > 0 ? (
        <section aria-label="More to Explore">
          {/* With a hero above, the grid really is "more"; on a fresh shelf
              (nothing started, no hero) it is the whole page, so the heading
              becomes the call to action instead. Visible text only: the
              region's accessible name stays "More to Explore" so assistive
              tech and the e2e suite keep one stable landmark name. */}
          <h2 className="library__shelf-heading">{hero ? 'More to Explore' : 'Pick a book!'}</h2>
          <ul className="library__shelf">
            {shelf.map((item) => (
              <li key={item.id}>
                <BookCard
                  item={item}
                  profileId={profileId}
                  onRate={rate}
                  onContinue={canRequest ? askForNextBook : undefined}
                  downloaded={isDownloaded(item)}
                  readOnly={readOnly}
                  ratable={!offline}
                  endings={endingsFor(item)}
                  recommendation={recommendationFor(item)}
                  everyPathWalked={everyPathWalkedFor(item)}
                  onOpenGallery={setGalleryStorybookId}
                  needsCharacter={needsCharacterFor(item)}
                  onNeedsCharacter={handleNeedsCharacter}
                />
              </li>
            ))}
            {/* End-cap "Ask for a new story" tile: the request box lives
                below the shelf and falls under the fold once a family has a
                few books, so the invitation also appears where a browsing
                child's eyes already are, as the shelf's last slot. Tapping
                it opens the form (openSignal) and scrolls there. Same gate
                as the form itself: never in guardian preview or offline. */}
            {canRequest ? (
              <li>
                <button
                  type="button"
                  className="book-card book-card--request"
                  onClick={askForNewStory}
                >
                  <span className="book-card__tile book-card__tile--request" aria-hidden="true">
                    ✨
                  </span>
                  <span className="book-card__request-label">Ask for a new story</span>
                </button>
              </li>
            ) : null}
          </ul>
        </section>
      ) : null}
      {/* Requesting a new story comes after the child's own books, not before
          them: the shelf is the point of the page, the request box is secondary.
          Omitted entirely in guardian preview mode (readOnly): a guardian
          previewing their child's shelf has their own request flow already
          (guardian console), and this form would otherwise submit a request
          under the previewed child's identity. Also omitted on the offline
          shelf (canRequest): sending an idea needs the network, and inviting
          one only to answer with "Something went wrong" is a dead end. */}
      {canRequest ? (
        <div ref={requestStoryRef} tabIndex={-1} className="library__request">
          <RequestStory
            profileId={profileId}
            anchor={continueAnchor}
            onClearAnchor={clearContinueAnchor}
            libraryIds={items.map((item) => item.id)}
            openSignal={requestOpenSignal}
          />
        </div>
      ) : null}
      {galleryStorybookId ? (
        <EndingsGallery
          open
          onClose={() => setGalleryStorybookId(null)}
          bookTitle={galleryItem?.title ?? ''}
          totalEndings={galleryBook?.total_endings ?? 0}
          foundEndings={galleryBook?.found_endings ?? []}
          unavailable={progressStatus !== 'ready'}
        />
      ) : null}
    </div>
  )
}
