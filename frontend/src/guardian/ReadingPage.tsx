import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { formatRelativeTime } from './intakeApi'
import {
  makeReadingApi,
  type ChildEngagementItem,
  type ReadingHistoryItem,
} from './readingApi'
import './guardian.css'

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; children: ChildEngagementItem[]; syncedAt: number }

type HistoryEntry =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; books: ReadingHistoryItem[] }

const LOAD_ERROR = "We could not load your family's reading activity. Please reload."
const HISTORY_ERROR = "We could not load this child's book detail. Please try again."

/**
 * Renders "no reading yet" for a child with zero books started, and the
 * signals-only stat row otherwise. Deliberately never mentions story titles,
 * choices, or node content (G9's privacy model: signals, not surveillance).
 */
function ChildStats({ child }: { child: ChildEngagementItem }) {
  if (child.books_started === 0) {
    return (
      <p className="reading-card__nudge cyo-text-muted">
        No reading yet.{' '}
        <Link className="reading-card__nudge-link" to="/guardian/books">
          Assign a book to get started
        </Link>
        .
      </p>
    )
  }
  return (
    <dl className="reading-card__stats">
      <div className="reading-card__stat">
        <dt>Books started</dt>
        <dd>{child.books_started}</dd>
      </div>
      <div className="reading-card__stat">
        <dt>Books finished</dt>
        <dd>{child.books_finished}</dd>
      </div>
      <div className="reading-card__stat">
        <dt>Endings found</dt>
        <dd>{child.total_endings_found}</dd>
      </div>
    </dl>
  )
}

function BookRow({ book, syncedAt }: { book: ReadingHistoryItem; syncedAt: number }) {
  const ago = formatRelativeTime(book.last_activity_at, syncedAt)
  return (
    <li className="reading-book cyo-card">
      <div className="reading-book__main">
        <span className="reading-book__title">{book.title}</span>
        <span className="reading-book__endings cyo-text-muted">
          {book.endings_found} of {book.total_endings} endings found
        </span>
      </div>
      {book.in_progress ? <span className="reading-book__progress">Still reading</span> : null}
      {ago !== null ? (
        <span
          className="reading-book__age cyo-text-muted"
          title={new Date(book.last_activity_at).toLocaleString()}
        >
          Last read {ago}
        </span>
      ) : null}
    </li>
  )
}

/**
 * Guardian engagement-visibility page (register G9, wireframe "Reading").
 * Per-child cards from GET /v1/families/me/reading-summary (books started,
 * finished, endings found, last activity); expanding a card lazy-fetches
 * that profile's per-book detail from GET /v1/reading-history/{profile_id}.
 *
 * Signals-only framing throughout, by design (never a surveillance log): no
 * choice, node, or story-content detail is fetched or rendered here, only
 * counts, titles, and timestamps the guardian can already see elsewhere
 * (the library listing, the Books page).
 */
export function ReadingPage() {
  const api = useApi()
  const readingApi = useMemo(() => makeReadingApi(api), [api])
  const [state, setState] = useState<PageState>({ kind: 'loading' })
  const [openId, setOpenId] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<string, HistoryEntry>>({})

  const load = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      const children = await readingApi.familySummary()
      setState({ kind: 'ready', children, syncedAt: Date.now() })
    } catch (err) {
      console.error('reading summary load failed:', err instanceof Error ? err.message : err)
      setState({
        kind: 'error',
        message: classifyApiError(err, { transient: LOAD_ERROR, server: LOAD_ERROR }).message,
      })
    }
  }, [readingApi])

  useEffect(() => {
    void load()
  }, [load])

  const loadHistory = useCallback(
    async (profileId: string) => {
      setHistory((prev) => ({ ...prev, [profileId]: { kind: 'loading' } }))
      try {
        const books = await readingApi.history(profileId)
        setHistory((prev) => ({ ...prev, [profileId]: { kind: 'ready', books } }))
      } catch (err) {
        console.error(
          'reading history load failed:',
          err instanceof Error ? err.message : err
        )
        setHistory((prev) => ({
          ...prev,
          [profileId]: {
            kind: 'error',
            message: classifyApiError(err, {
              transient: HISTORY_ERROR,
              server: HISTORY_ERROR,
            }).message,
          },
        }))
      }
    },
    [readingApi]
  )

  function toggle(profileId: string) {
    if (openId === profileId) {
      setOpenId(null)
      return
    }
    setOpenId(profileId)
    // Cache-on-open: a profile whose history already loaded (or is loading)
    // is not re-fetched just because the card was closed and reopened.
    const cached = history[profileId]
    if (cached === undefined || cached.kind === 'error') {
      void loadHistory(profileId)
    }
  }

  if (state.kind === 'loading') {
    return (
      <LoadingStatus>Loading reading activity…</LoadingStatus>
    )
  }

  if (state.kind === 'error') {
    return (
      <ErrorBanner className="reading__error">{state.message}</ErrorBanner>
    )
  }

  const { children, syncedAt } = state

  return (
    <section className="reading">
      <h1>Reading</h1>
      <p className="reading__intro cyo-text-muted">
        How the reading is going: what each child has picked up, finished,
        and when they last opened a book. This is not a log of what was
        read, only how things are going.
      </p>
      {children.length === 0 ? (
        <EmptyState
          title="No reading yet"
          description="Assign a book to a child to see how their reading is going."
          actions={
            <Link className="reading__cta" to="/guardian/books">
              Go to Books
            </Link>
          }
        />
      ) : (
        <ul className="reading__list">
          {children.map((child) => {
            const isOpen = openId === child.profile_id
            const entry = history[child.profile_id]
            const lastActivityAgo =
              child.last_activity_at !== null
                ? formatRelativeTime(child.last_activity_at, syncedAt)
                : null
            return (
              <li key={child.profile_id} className="reading-card cyo-card">
                <button
                  type="button"
                  className="reading-card__toggle"
                  aria-expanded={isOpen}
                  aria-controls={`reading-detail-${child.profile_id}`}
                  onClick={() => toggle(child.profile_id)}
                >
                  <span className="reading-card__name">{child.display_name}</span>
                  <span className="reading-card__activity cyo-text-muted">
                    {lastActivityAgo !== null ? `Active ${lastActivityAgo}` : 'No activity yet'}
                  </span>
                </button>
                <ChildStats child={child} />
                {isOpen ? (
                  <div id={`reading-detail-${child.profile_id}`} className="reading-card__detail">
                    {entry === undefined || entry.kind === 'loading' ? (
                      <p role="status" aria-live="polite">
                        Loading books…
                      </p>
                    ) : entry.kind === 'error' ? (
                      <ErrorBanner
                        className="reading-card__error"
                        onRetry={() => void loadHistory(child.profile_id)}
                      >
                        {entry.message}
                      </ErrorBanner>
                    ) : entry.books.length === 0 ? (
                      <p className="reading-card__nudge cyo-text-muted">
                        No books started yet.{' '}
                        <Link className="reading-card__nudge-link" to="/guardian/books">
                          Assign a book to get reading started
                        </Link>
                        .
                      </p>
                    ) : (
                      <ul className="reading-book-list">
                        {entry.books.map((book) => (
                          <BookRow key={book.storybook_id} book={book} syncedAt={syncedAt} />
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
