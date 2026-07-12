import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeCoverApi, type CoverStatusView } from './coverApi'
import { FlagBadge, verdictTone } from './FlagBadge'
import { makeReviewApi, type FindingView, type ReviewSurface, type Visibility } from './reviewApi'

interface StoryNode {
  id: string
  body: string
}

/**
 * Read the story nodes from a loosely typed blob.
 *
 * Keeps any entry that has a real id OR real prose, and synthesizes a stable id
 * for a blank-id-but-has-prose node. This is deliberate for a safety surface: a
 * passage with malformed id must not silently drop out of the reviewer's
 * read-through, since the reviewer must see all prose before approving. A
 * synthetic id simply won't match flagged-node highlighting; flagged content
 * still appears in the server-driven flagged-passages section regardless. Only
 * entries that are not objects, or have neither an id nor prose, are skipped.
 */
function readNodes(blob: Record<string, unknown>): StoryNode[] {
  const raw = blob.nodes
  if (!Array.isArray(raw)) return []
  const nodes: StoryNode[] = []
  raw.forEach((entry, index) => {
    if (typeof entry !== 'object' || entry === null) return
    const record = entry as Record<string, unknown>
    const id = typeof record.id === 'string' ? record.id : ''
    const body = typeof record.body === 'string' ? record.body : ''
    if (!id && !body) return
    nodes.push({ id: id || `node-${index}`, body })
  })
  return nodes
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; surface: ReviewSurface }

type ActionDialog = null | 'approve' | 'sendback'

function Finding({ finding }: { finding: FindingView }) {
  return (
    <li className="review-finding">
      <FlagBadge tone={verdictTone(finding.verdict)} />
      <span className="review-finding__category">{finding.category}</span>
      <span className="review-finding__message">{finding.message}</span>
    </li>
  )
}

/**
 * Flags-first review detail (C4a-4, wireframe 4.4). Flagged passages surface
 * first, then the full story read-through with flagged nodes highlighted. The
 * Approve / Send Back actions stay pinned at the bottom. Swipe-to-approve is
 * deliberately excluded (ADR-005: approval is safety-critical and must be a
 * deliberate, recorded human action).
 */
export function ReviewDetailPage() {
  const { storybookId = '' } = useParams()
  const api = useApi()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const coverApi = useMemo(() => makeCoverApi(api), [api])
  const navigate = useNavigate()

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [dialog, setDialog] = useState<ActionDialog>(null)
  const [visibility, setVisibility] = useState<Visibility>('family')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState(false)
  const [coverStatus, setCoverStatus] = useState<CoverStatusView['cover_status']>('none')
  const [coverBusy, setCoverBusy] = useState(false)
  // Set when the poll loop hits its cap while the job is still 'generating', so
  // the reviewer gets a retry affordance instead of a permanently disabled
  // button with no feedback.
  const [coverTimedOut, setCoverTimedOut] = useState(false)

  // #ASSUME: timing dependencies: the cover-generation poll loop sleeps 2s up
  // to 30 times (~60s); a reviewer can navigate away mid-poll.
  // #VERIFY: generateCover checks isMountedRef after every await before
  // calling setState, so a late poll response never writes into an unmounted
  // component.
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const surface = await reviewApi.surface(storybookId)
        if (!cancelled) setState({ kind: 'ready', surface })
      } catch (err) {
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('review surface load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load this story for review. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [reviewApi, storybookId])

  // Seed the current server-side cover status once the surface is ready, so an
  // in-flight job (e.g. one started in another tab) is reflected and the
  // Generate button is not wrongly enabled. Best-effort: a failure keeps 'none'.
  const readyVersion = state.kind === 'ready' ? state.surface.version : null
  useEffect(() => {
    if (readyVersion === null) return
    let cancelled = false
    void (async () => {
      try {
        const current = await coverApi.status(storybookId, readyVersion)
        if (!cancelled && isMountedRef.current) setCoverStatus(current.cover_status)
      } catch (err) {
        // Best-effort seed; keep the default status on failure.
        void err
      }
    })()
    return () => {
      cancelled = true
    }
  }, [coverApi, storybookId, readyVersion])

  // #ASSUME: external resources: cover generation runs async on an RQ worker;
  // the 10s axios timeout in useApi rules out waiting on the POST itself, so
  // this fires the POST then polls the GET status endpoint until it leaves
  // 'generating' (or the poll cap is hit).
  // #VERIFY: coverApi.test.ts covers the request shapes; the isMountedRef
  // guard above stops the loop from writing state after unmount.
  const generateCover = useCallback(async () => {
    const surface = state.kind === 'ready' ? state.surface : null
    if (!surface) return
    const version = surface.version
    setCoverBusy(true)
    setCoverTimedOut(false)
    try {
      const started = await coverApi.generate(storybookId, version)
      if (!isMountedRef.current) return
      setCoverStatus(started.cover_status)
      let latest = started.cover_status
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (!isMountedRef.current) return
        const polled = await coverApi.status(storybookId, version)
        if (!isMountedRef.current) return
        latest = polled.cover_status
        setCoverStatus(latest)
        if (latest !== 'generating') break
      }
      // Poll cap reached with the job still generating: surface a retry
      // affordance rather than a stuck spinner. The backend short-circuits a
      // re-request while still 'generating', so retry cannot duplicate the job.
      if (isMountedRef.current && latest === 'generating') setCoverTimedOut(true)
    } catch (err) {
      // Log the message, not the axios error object (its config.headers
      // carries the caller's Authorization bearer token).
      console.error('cover generation failed:', err instanceof Error ? err.message : err)
      if (isMountedRef.current) setCoverStatus('failed')
    } finally {
      if (isMountedRef.current) setCoverBusy(false)
    }
  }, [coverApi, state, storybookId])

  async function runAction(action: () => Promise<unknown>) {
    setSubmitting(true)
    setActionError(false)
    try {
      await action()
      void navigate('/guardian')
    } catch (err) {
      console.error('review action failed:', err instanceof Error ? err.message : err)
      setActionError(true)
      setSubmitting(false)
    }
  }

  // Open/close reset the transient action state so a prior failure can never
  // bleed into the other dialog: without this, a failed Approve leaves
  // actionError set, and reopening (or switching to Send Back) would render a
  // stale error alert for an action the reviewer never attempted.
  function openDialog(kind: Exclude<ActionDialog, null>) {
    setActionError(false)
    // Reset to the default visibility every time the approve dialog opens, so
    // a prior "catalog" choice on one story never silently carries over and
    // gets applied to the next approval.
    if (kind === 'approve') setVisibility('family')
    setDialog(kind)
  }

  function closeDialog() {
    setActionError(false)
    setReason('')
    setDialog(null)
  }

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading story…
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <p role="alert" className="console__error cyo-text-error">
        {state.message}
      </p>
    )
  }

  const { surface } = state
  const nodes = readNodes(surface.blob)
  const flaggedIds = new Set(surface.flagged_passages.map((passage) => passage.node_id))
  const title =
    typeof surface.blob.title === 'string' && surface.blob.title
      ? surface.blob.title
      : surface.storybook_id
  const reasonValid = reason.trim().length >= 1 && reason.trim().length <= 2000

  return (
    <section className="review-detail">
      <h1>{title}</h1>

      {!surface.screened ? (
        <p role="alert" className="review-detail__unscreened">
          This version was never screened by moderation. Approving it will be rejected
          until it has been screened.
        </p>
      ) : null}

      {surface.flagged_passages.length > 0 ? (
        <div className="review-group">
          <h2>Flagged passages</h2>
          {surface.flagged_passages.map((passage) => (
            <article key={passage.node_id} className="review-card cyo-card">
              <PassageText text={passage.prose} />
              <ul className="review-findings">
                {passage.findings.map((finding, index) => (
                  // Findings are static per render; index key is stable here.
                  <Finding key={index} finding={finding} />
                ))}
              </ul>
            </article>
          ))}
        </div>
      ) : surface.screened ? (
        <p className="console__muted cyo-text-muted">No flagged passages. This story screened clean.</p>
      ) : null}

      {surface.story_level_findings.length > 0 ? (
        <div className="review-group">
          <h2>Story-level notes</h2>
          <ul className="review-findings">
            {surface.story_level_findings.map((finding, index) => (
              // Findings are static per render; index key is stable here.
              <Finding key={index} finding={finding} />
            ))}
          </ul>
        </div>
      ) : null}

      <div className="review-group" id="full-story">
        <h2>Full story</h2>
        {nodes.map((node) => (
          <div
            key={node.id}
            className={
              flaggedIds.has(node.id) ? 'review-node review-node--flagged' : 'review-node'
            }
          >
            <PassageText text={node.body} />
          </div>
        ))}
      </div>

      {/*
        #ASSUME: UI state: the backend already re-checks status on approve/send-back
        and rejects a story that is not in_review; this guard is UX only, so a
        guardian never clicks into a confusing rejection for a story someone else
        already approved or sent back in another tab.
        #VERIFY: ReviewDetailPage.test.tsx disabled-for-published/draft +
        enabled-for-in-review tests.
      */}
      <div className="review-actionbar">
        <Button
          variant="ghost"
          onClick={() => void generateCover()}
          disabled={coverBusy || (coverStatus === 'generating' && !coverTimedOut)}
        >
          {coverStatus === 'generating' && !coverTimedOut
            ? 'Generating cover…'
            : 'Generate cover'}
        </Button>
        {coverStatus === 'failed' ? (
          <span className="review-cover-error" role="alert">
            Cover failed; try again.
          </span>
        ) : coverTimedOut ? (
          <span className="review-cover-error" role="status">
            Still generating; keep waiting or retry.
          </span>
        ) : null}
        <Button
          variant="danger"
          onClick={() => openDialog('sendback')}
          disabled={surface.status !== 'in_review'}
          aria-describedby={
            surface.status !== 'in_review' ? 'review-actions-disabled-hint' : undefined
          }
        >
          Send Back
        </Button>
        <Button
          onClick={() => openDialog('approve')}
          disabled={surface.status !== 'in_review'}
          aria-describedby={
            surface.status !== 'in_review' ? 'review-actions-disabled-hint' : undefined
          }
        >
          Approve
        </Button>
      </div>
      {/*
        Keep each button's accessible name its visible label ("Approve" / "Send
        Back") and carry the disabled reason in a separate described-by hint, so a
        screen-reader user still hears the primary action name and sighted users see
        why the controls are greyed. Overwriting aria-label with the reason (the
        earlier approach) hid the action name from assistive tech.
      */}
      {surface.status !== 'in_review' ? (
        <p id="review-actions-disabled-hint" className="review-actionbar__hint cyo-text-muted">
          Only stories in review can be approved or sent back.
        </p>
      ) : null}

      {dialog === 'approve' ? (
        <Dialog
          title="Approve this story?"
          onClose={closeDialog}
          actions={
            <>
              <Button variant="ghost" onClick={closeDialog}>
                Cancel
              </Button>
              {/*
                #CRITICAL: security: confirming approve publishes this version to
                the assigned children; a misclick must not ship unreviewed content.
                #VERIFY: this confirm dialog gates the action and the backend
                re-checks the story is screened and still in review, rejecting
                anything unscreened (ReviewDetailPage.test.tsx approve + rejection).
              */}
              <Button
                disabled={submitting}
                onClick={() => void runAction(() => reviewApi.approve(storybookId, visibility))}
              >
                Confirm approve
              </Button>
            </>
          }
        >
          {actionError ? (
            <p role="alert" className="review-detail__action-error cyo-text-error">
              We could not approve this story. It may be unscreened or no longer in review.
            </p>
          ) : null}
          <p>Approving publishes this story to the assigned children.</p>
          <fieldset className="review-detail__visibility">
            <legend>Who can see this book?</legend>
            <label>
              <input
                type="radio"
                name="visibility"
                checked={visibility === 'family'}
                onChange={() => setVisibility('family')}
              />
              This family only
            </label>
            <label>
              <input
                type="radio"
                name="visibility"
                checked={visibility === 'catalog'}
                onChange={() => setVisibility('catalog')}
              />
              Catalog (every family)
            </label>
            {visibility === 'catalog' ? (
              <p className="review-detail__visibility-warning cyo-text-error">
                Catalog books are visible to every family. Confirm the story contains no names,
                photos, or personal details before sharing.
              </p>
            ) : null}
          </fieldset>
        </Dialog>
      ) : null}

      {dialog === 'sendback' ? (
        <Dialog
          title="Send back for revision"
          onClose={closeDialog}
          actions={
            <>
              <Button variant="ghost" onClick={closeDialog}>
                Cancel
              </Button>
              {/*
                #CRITICAL: security: confirming send back changes review state and
                returns the story to its author with a reason.
                #VERIFY: reasonValid plus this confirm dialog gate the action; the
                backend re-checks the story is still in review
                (ReviewDetailPage.test.tsx reason-required + whitespace-only tests).
              */}
              <Button
                variant="danger"
                disabled={!reasonValid || submitting}
                onClick={() => void runAction(() => reviewApi.sendBack(storybookId, reason.trim()))}
              >
                Confirm send back
              </Button>
            </>
          }
        >
          {actionError ? (
            <p role="alert" className="review-detail__action-error cyo-text-error">
              We could not send this story back. Please try again.
            </p>
          ) : null}
          <label className="review-detail__reason">
            Reason for sending back
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={2000}
              rows={3}
              required
            />
          </label>
        </Dialog>
      ) : null}
    </section>
  )
}
