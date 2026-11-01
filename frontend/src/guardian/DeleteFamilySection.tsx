import { useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { useAuth } from '../auth/useAuth'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { makeFamilyDeletionApi } from './familyDeletionApi'

/** The word a guardian must type to unlock the irreversible delete. */
export const DELETE_CONFIRMATION_WORD = 'DELETE'

/**
 * Whole-family account deletion (GDPR Article 17 / COPPA 312.10).
 *
 * This is the guardian-facing entry point for `DELETE /v1/me/family`, which
 * existed and was tested but had no UI, so a parent could not delete their
 * account through the product. The action is irreversible and takes every
 * adult in the family with it, so it is gated three ways: a danger button that
 * only opens a dialog, a dialog that states exactly what is lost, and a typed
 * confirmation that must match before the delete button enables.
 *
 * On success the session is signed out. The server has just deleted the user
 * row this session resolves to, so any further request would fail anyway.
 *
 * #CRITICAL: security: the delete is only ever issued from the dialog's own
 * button, never from the section's open button.
 * #VERIFY: DeleteFamilySection.test.tsx asserts no request fires on open, on
 * cancel, or while the typed confirmation does not match.
 */
export function DeleteFamilySection() {
  const api = useApi()
  const { signOut } = useAuth()
  const deletionApi = useMemo(() => makeFamilyDeletionApi(api), [api])
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const confirmed = typed.trim() === DELETE_CONFIRMATION_WORD

  function close() {
    if (deleting) return
    setOpen(false)
    setTyped('')
    setErrorMessage(null)
  }

  // #EDGE: external-resources: the delete can succeed while the sign-out
  // cannot reach Supabase. The account is already gone either way, so a failed
  // sign-out is swallowed here: the next request 401s and the auth layer sends
  // the guardian to login, which is the correct end state.
  async function deleteFamily() {
    setDeleting(true)
    setErrorMessage(null)
    try {
      await deletionApi.deleteMyFamily()
    } catch (err) {
      // Redacted, never the raw AxiosError: its `config.headers.Authorization`
      // carries the guardian bearer token (see logApiError).
      logApiError('family deletion failed', err)
      setErrorMessage(classifyApiError(err).message)
      setDeleting(false)
      return
    }
    try {
      await signOut()
    } catch {
      // See the #EDGE note above.
    }
  }

  return (
    <section
      id="delete-family"
      aria-label="Delete your family account"
      className="console-delete-family"
    >
      <h2>Delete your family account</h2>
      <p className="console__notice cyo-text-muted">
        This permanently erases your family account and everything in it. It cannot be undone.
      </p>
      <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
        Delete family account
      </Button>
      {open ? (
        <Dialog
          title="Delete your family account?"
          onClose={close}
          actions={
            <>
              <Button variant="ghost" onClick={close} disabled={deleting}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={!confirmed || deleting}
                onClick={() => void deleteFamily()}
              >
                {deleting ? 'Deleting…' : 'Delete everything'}
              </Button>
            </>
          }
        >
          <p>This permanently deletes:</p>
          <ul>
            <li>every child profile, with reading history, ratings, and saved places</li>
            <li>every story, request, and assignment your family owns, including cover art</li>
            <li>the sign-in for every adult in this family, including any co-parent</li>
          </ul>
          <p>
            Anyone you have connected with loses the connection.{' '}
            <strong>This cannot be undone.</strong>
          </p>
          <label className="console-delete-family__field cyo-field">
            <span>
              Type <strong>{DELETE_CONFIRMATION_WORD}</strong> to confirm
            </span>
            <input
              type="text"
              name="delete-confirmation"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              className="cyo-field__control"
              value={typed}
              disabled={deleting}
              onChange={(event) => setTyped(event.target.value)}
            />
          </label>
          {errorMessage !== null ? (
            <ErrorBanner className="console-delete-family__error">{errorMessage}</ErrorBanner>
          ) : null}
        </Dialog>
      ) : null}
    </section>
  )
}
