import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { Mascot } from '../kid/Mascot'
import { GUARDIAN_LOGIN_PATH, KID_PICKER_PATH } from '../routes'
import {
  cacheLibraryList,
  getCachedLibraryList,
  getCachedStorybook,
} from '../offline/db'
import { BookCard } from './BookCard'
import { makeLibraryApi, type LibraryItemView } from './libraryApi'
import { pickHero } from './pickHero'
import { RequestStory, type ContinueAnchor } from './RequestStory'
import './library.css'

// `unauthenticated` and `forbidden` are stable, expected gates (no grown-up
// signed in / this profile isn't the signed-in child's), not a flaky fetch;
// `error` stays the transient-only label so its existing retry copy keeps
// meaning "this should have worked, try again".
type LibraryState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'forbidden' }
  | { status: 'error' }
  | { status: 'ready'; items: LibraryItemView[] }
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

/**
 * Kid library home (wireframe 4.2): Continue Reading hero for the most
 * recently active book, then a More to Explore shelf grid for the rest.
 * The server already filters to published, approved, family-scoped books.
 */
export function LibraryPage() {
  const { profileId } = useParams()
  const api = useApi()
  const libraryApi = useMemo(() => makeLibraryApi(api), [api])
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
        if (!cancelled && isMountedRef.current) setState({ status: 'ready', items })
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
  }, [libraryApi, profileId])

  useEffect(load, [load])

  const rate = useCallback(
    (storybookId: string, value: number) => {
      if (!profileId) return
      libraryApi
        .rate(profileId, storybookId, value)
        .then((view) =>
          setState((prev) =>
            prev.status === 'ready'
              ? {
                  status: 'ready',
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
  const isDownloaded = (item: LibraryItemView): boolean =>
    !offline || state.downloaded.has(item.id)
  if (items.length === 0) {
    return (
      <div className="library">
        <EmptyState
          title="No books yet"
          description="Ask a grown-up to add one!"
          icon={<Mascot size={96} />}
        />
        <RequestStory profileId={profileId} />
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
            onContinue={askForNextBook}
            downloaded={isDownloaded(hero)}
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
                  onContinue={askForNextBook}
                  downloaded={isDownloaded(item)}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {/* Requesting a new story comes after the child's own books, not before
          them: the shelf is the point of the page, the request box is secondary. */}
      <div ref={requestStoryRef} tabIndex={-1} className="library__request">
        <RequestStory
          profileId={profileId}
          anchor={continueAnchor}
          onClearAnchor={clearContinueAnchor}
        />
      </div>
    </div>
  )
}
