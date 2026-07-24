import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { Mascot } from '../kid/Mascot'
import { reconcileOfflineCache } from '../offline/revocation'
import { GUARDIAN_LOGIN_PATH, KID_PICKER_PATH } from '../routes'
import {
  cacheLibraryList,
  getCachedLibraryList,
  getCachedStorybook,
} from '../offline/db'
import { BookCard } from './BookCard'
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
  const api = useApi()
  const libraryApi = useMemo(() => makeLibraryApi(api), [api])
  const recommendationsApi = useMemo(() => makeRecommendationsApi(api), [api])
  const [state, setState] = useState<LibraryState>({ status: 'loading' })
  const [continueAnchor, setContinueAnchor] = useState<ContinueAnchor | null>(null)
  const requestStoryRef = useRef<HTMLDivElement>(null)

  const askForNextBook = useCallback(
    (item: LibraryItemView) => setContinueAnchor({ id: item.id, title: item.title }),
    []
  )
  const clearContinueAnchor = useCallback(() => setContinueAnchor(null), [])

  // #ASSUME: UI state: tapping "Ask for the next book" opens the RequestStory
  // form at the top of the page with no visual cue near the tapped card;
  // without moving focus/scroll, a keyboard or low-vision user has no way to
  // notice the form appeared.
  // #VERIFY: whenever continueAnchor becomes non-null, the form container is
  // scrolled into view and receives focus.
  useEffect(() => {
    if (continueAnchor !== null) {
      // Optional-call scrollIntoView: it is absent under jsdom (test env) and
      // guarding keeps the focus move working there without a test shim.
      requestStoryRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      requestStoryRef.current?.focus()
    }
  }, [continueAnchor])

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
          items.map((item) => item.id)
        ).catch((err: unknown) => {
          logApiError('offline cache reconcile failed', err)
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
  }, [libraryApi, recommendationsApi, profileId])

  useEffect(load, [load])

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
  if (state.status === 'loading') {
    return (
      <p className="library__status" role="status" aria-live="polite">
        Loading your books…
      </p>
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
  return (
    <div className="library">
      <h1 className="library__heading">My Books</h1>
      {offline ? (
        <p className="library__offline-banner" role="status">
          No internet. These books are ready to read.
        </p>
      ) : null}
      {hero ? (
        <section aria-label="Continue Reading">
          <BookCard
            item={hero}
            profileId={profileId}
            hero
            onRate={rate}
            onContinue={readOnly ? undefined : askForNextBook}
            downloaded={isDownloaded(hero)}
            readOnly={readOnly}
            endings={endingsFor(hero)}
            recommendation={recommendationFor(hero)}
          />
        </section>
      ) : null}
      {shelf.length > 0 ? (
        <section aria-label="More to Explore">
          <h2 className="library__shelf-heading">More to Explore</h2>
          <ul className="library__shelf">
            {shelf.map((item) => (
              <li key={item.id}>
                <BookCard
                  item={item}
                  profileId={profileId}
                  onRate={rate}
                  onContinue={readOnly ? undefined : askForNextBook}
                  downloaded={isDownloaded(item)}
                  readOnly={readOnly}
                  endings={endingsFor(item)}
                  recommendation={recommendationFor(item)}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {/* Requesting a new story comes after the child's own books, not before
          them: the shelf is the point of the page, the request box is secondary.
          Omitted entirely in guardian preview mode (readOnly): a guardian
          previewing their child's shelf has their own request flow already
          (guardian console), and this form would otherwise submit a request
          under the previewed child's identity. */}
      {readOnly ? null : (
        <div ref={requestStoryRef} tabIndex={-1} className="library__request">
          <RequestStory
            profileId={profileId}
            anchor={continueAnchor}
            onClearAnchor={clearContinueAnchor}
            libraryTitles={items.map((item) => item.title)}
          />
        </div>
      )}
    </div>
  )
}
