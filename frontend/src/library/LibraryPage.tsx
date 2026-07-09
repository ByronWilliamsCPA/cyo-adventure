import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { BookCard } from './BookCard'
import { makeLibraryApi, type LibraryItemView } from './libraryApi'
import { pickHero } from './pickHero'
import { RequestStory, type ContinueAnchor } from './RequestStory'
import './library.css'

type LibraryState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; items: LibraryItemView[] }

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

  const continueThisStory = useCallback(
    (item: LibraryItemView) => setContinueAnchor({ id: item.id, title: item.title }),
    []
  )
  const clearContinueAnchor = useCallback(() => setContinueAnchor(null), [])

  // #ASSUME: UI state: tapping "Continue this story" opens the RequestStory
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
        if (!cancelled && isMountedRef.current) setState({ status: 'ready', items })
      } catch {
        if (!cancelled && isMountedRef.current) setState({ status: 'error' })
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
        .catch(() => {
          /* keep the previous rating; transient failure must not break browsing */
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
  if (state.status === 'error') {
    return (
      <div className="library">
        <EmptyState
          title="We lost the bookshelf"
          description="Something went wrong loading your books."
          actions={
            <Button variant="primary" size="lg" onClick={load}>
              Try again
            </Button>
          }
        />
      </div>
    )
  }
  const { items } = state
  if (items.length === 0) {
    return (
      <div className="library">
        <EmptyState title="No books yet" description="Ask a grown-up to add one!" />
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
      <div ref={requestStoryRef} tabIndex={-1}>
        <RequestStory
          profileId={profileId}
          anchor={continueAnchor}
          onClearAnchor={clearContinueAnchor}
        />
      </div>
      {hero ? (
        <section aria-label="Continue Reading">
          <BookCard
            item={hero}
            profileId={profileId}
            hero
            onRate={rate}
            onContinue={continueThisStory}
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
                  onContinue={continueThisStory}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
