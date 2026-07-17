/**
 * K15 flag button: a small "Tell a grown-up" affordance in the reader chrome
 * (available for the whole session, not only the ending screen, since the
 * content that scared a child can happen mid-story). Opens a kid-simple
 * choice of exactly three structured reasons; POSTs to /v1/flags with no
 * free text (the wire body forbids it, see KidFlagCreateBody's backend
 * docstring). Confirmation and the cap-reached message use the shared toast
 * (success/info tones only, matching the app's existing "no error red for a
 * background confirmation" convention).
 */

import { useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'

import type { KidFlagCreatedView } from '../client/types.gen'
import { FlagCapReachedError, type FlagReason, type SubmitFlagParams } from '../api/readerApi'
import { getValidChildSession } from '../auth/childSession'
import { useToast } from '../notifications/useToast'
import './reader.css'

export interface FlagButtonProps {
  profileId: string
  storybookId: string
  version: number
  /** The node the child was reading when they open the dialog; re-read at
   * submit time via `getNodeId` (not a snapshot prop) so a slow tap-through
   * dialog still reports the passage the child was actually on when they
   * picked a reason, not whichever passage was current when the button first
   * rendered. */
  getNodeId: () => string | undefined
  submitFlag: (params: SubmitFlagParams) => Promise<KidFlagCreatedView>
}

const REASONS: Array<{ value: FlagReason; label: string }> = [
  { value: 'did_not_like', label: "I didn't like it" },
  { value: 'scared_me', label: 'It scared me' },
  { value: 'confusing', label: 'It was confusing' },
]

/**
 * Hidden entirely (not disabled) when there is no valid child session for
 * this profile: filing a flag requires the child bearer the POST would carry,
 * and a guardian browsing the reader on the child's behalf (no child session
 * minted) has no use for a "tell a grown-up" affordance aimed at themselves.
 *
 * #ASSUME: security: session validity is read once per profileId change, not
 * re-checked continuously; a session that expires while the dialog is open
 * surfaces as a generic submit failure (the POST 401s), not a mid-interaction
 * disappearance of the button.
 * #VERIFY: FlagButton.test.tsx "hidden when no valid child session exists"
 * and "hidden when the stored session is for a different profile".
 */
export function FlagButton({
  profileId,
  storybookId,
  version,
  getNodeId,
  submitFlag,
}: FlagButtonProps) {
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(false)
  const { showToast } = useToast()

  const session = getValidChildSession()
  if (!session || session.profileId !== profileId) return null

  function closeDialog() {
    if (submitting) return
    setOpen(false)
    setError(false)
  }

  async function pick(reason: FlagReason) {
    if (submitting) return
    setSubmitting(true)
    setError(false)
    try {
      await submitFlag({
        profileId,
        storybookId,
        version,
        reason,
        nodeId: getNodeId() ?? null,
      })
      setOpen(false)
      showToast('Thanks for telling us. A grown-up will take a look.', { tone: 'success' })
    } catch (err) {
      if (err instanceof FlagCapReachedError) {
        setOpen(false)
        showToast("You've told us a lot already.", { tone: 'info' })
      } else {
        // Redacted shape only, never the raw axios error (its `config`
        // carries the Authorization header); mirrors logApiError's intent.
        console.error('[reader] flag submit failed', {
          profileId,
          storybookId,
          reason,
          error: err,
        })
        setError(true)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className="reader-flag-toggle"
        aria-label="Tell a grown-up"
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true">🚩</span>
        Tell a grown-up
      </button>
      <Dialog
        title="Tell a grown-up"
        open={open}
        onClose={closeDialog}
        actions={
          <Button variant="ghost" disabled={submitting} onClick={closeDialog}>
            Cancel
          </Button>
        }
      >
        <p className="reader-flag-prompt">What happened?</p>
        {error ? (
          <p role="alert" className="reader-flag-error">
            Something went wrong. Try again.
          </p>
        ) : null}
        <div className="reader-flag-reasons">
          {REASONS.map((reason) => (
            <Button
              key={reason.value}
              variant="ghost"
              disabled={submitting}
              onClick={() => void pick(reason.value)}
            >
              {reason.label}
            </Button>
          ))}
        </div>
      </Dialog>
    </>
  )
}
