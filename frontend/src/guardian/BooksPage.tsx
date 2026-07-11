import { isAxiosError } from 'axios'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { AssignChildrenDialog } from './AssignChildrenDialog'
import { makeAssignApi, type GuardianBookItem } from './assignApi'
import { FlagBadge } from './FlagBadge'
import './guardian.css'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | { kind: 'ready'; books: GuardianBookItem[]; profiles: ProfileView[] }

/** Stable empty reference so the id->name memo does not churn before load. */
const EMPTY_PROFILES: ProfileView[] = []

/** The redacted content badge for one book, mirroring the console/dialog. */
function ContentBadge({ book }: { book: GuardianBookItem }) {
  if (!book.screened) return <FlagBadge tone="unscreened" />
  if (book.flagged_count > 0) {
    return <FlagBadge tone="flag" label={`${book.flagged_count} flagged`} />
  }
  return <FlagBadge tone="clean" />
}

/**
 * Render the display names a book is currently assigned to. An id with no
 * matching profile (e.g. a since-deleted child) is surfaced as an explicit
 * "N unknown profile(s)" placeholder rather than silently dropped, so a book
 * that IS assigned never renders the misleading "No one yet". Only a genuinely
 * empty assignment set renders "No one yet".
 */
function assignedNames(
  book: GuardianBookItem,
  nameById: Map<string, string>
): string {
  if (book.assigned_profile_ids.length === 0) return 'No one yet'
  const names: string[] = []
  let unknown = 0
  for (const id of book.assigned_profile_ids) {
    const name = nameById.get(id)
    if (name !== undefined) names.push(name)
    else unknown += 1
  }
  if (unknown > 0) {
    names.push(unknown === 1 ? '1 unknown profile' : `${unknown} unknown profiles`)
  }
  return names.join(', ')
}

/**
 * Guardian browse-and-assign page (Task 2.2): every published, approved book in
 * the guardian's family, each with a redacted content badge, its current
 * assignment status, and an Assign action that opens AssignChildrenDialog
 * (which lazy-fetches the full content tags from the Task 2.1 endpoint). The
 * endpoint is guardian-only; a deep-linking admin gets a 403 and a clear notice
 * rather than a broken page, mirroring ConsolePage's forbidden branch.
 */
export function BooksPage() {
  const api = useApi()
  const assignApi = useMemo(() => makeAssignApi(api), [api])
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [assigning, setAssigning] = useState<string | null>(null)

  // Build the id->name lookup once per profiles change (not once per book row).
  // onAssigned preserves the profiles reference, so this survives an assign.
  const profiles = state.kind === 'ready' ? state.profiles : EMPTY_PROFILES
  const nameById = useMemo(
    () => new Map(profiles.map((profile) => [profile.id, profile.display_name])),
    [profiles]
  )

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [books, profiles] = await Promise.all([
          assignApi.listBooks(),
          profilesApi.list(),
        ])
        if (!cancelled) setState({ kind: 'ready', books, profiles })
      } catch (err) {
        // #CRITICAL: security: this browse-to-assign page is guardian-only; an
        // admin (allowed into the /guardian tree but with no assign authority)
        // gets a 403 from the endpoint and must see a clear notice, not a broken
        // page. Mirrors ConsolePage's forbidden branch for the inverse role.
        // #VERIFY: BooksPage.test.tsx asserts the notice on 403 and the generic
        // error on 500.
        if (isAxiosError(err) && err.response?.status === 403) {
          if (!cancelled) setState({ kind: 'forbidden' })
          return
        }
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error(
          'guardian books load failed:',
          err instanceof Error ? err.message : err
        )
        if (!cancelled) setState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [assignApi, profilesApi])

  function onAssigned(storybookId: string, profileIds: string[]) {
    setState((prev) => {
      if (prev.kind !== 'ready') return prev
      return {
        ...prev,
        books: prev.books.map((book) =>
          book.storybook_id === storybookId
            ? { ...book, assigned_profile_ids: profileIds }
            : book
        ),
      }
    })
  }

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading books…
      </div>
    )
  }

  if (state.kind === 'forbidden') {
    return (
      <section className="books">
        <h1>Books</h1>
        <p className="console__notice cyo-text-muted">
          Assigning books is handled by a guardian. You do not manage
          assignments here.
        </p>
      </section>
    )
  }

  if (state.kind === 'error') {
    return (
      <p role="alert" className="console__error cyo-text-error">
        We could not load your family&apos;s books. Please reload.
      </p>
    )
  }

  const { books } = state

  return (
    <section className="books">
      <h1>Books</h1>
      {books.length === 0 ? (
        <EmptyState
          title="No published books yet"
          description="Books appear here once a story you request is approved."
        />
      ) : (
        <ul className="books__list">
          {books.map((book) => (
            <li key={book.storybook_id} className="books__row cyo-card">
              <div className="books__main">
                <span className="books__title">{book.title}</span>
                {book.visibility === 'catalog' && (
                  <span className="intake-pill">Catalog</span>
                )}
                <ContentBadge book={book} />
              </div>
              <p className="books__assigned">
                Assigned to: {assignedNames(book, nameById)}
              </p>
              <Button
                onClick={() => setAssigning(book.storybook_id)}
                aria-label={`Assign ${book.title}`}
              >
                Assign
              </Button>
            </li>
          ))}
        </ul>
      )}
      {assigning !== null ? (
        <AssignChildrenDialog
          storybookId={assigning}
          onClose={() => setAssigning(null)}
          onAssigned={(profileIds) => onAssigned(assigning, profileIds)}
        />
      ) : null}
    </section>
  )
}
