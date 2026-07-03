import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { useApi } from '../hooks/useApi'
import { FlagBadge, verdictTone } from './FlagBadge'
import { makeReviewApi, type FindingView, type ReviewSurface } from './reviewApi'

interface StoryNode {
  id: string
  body: string
}

/** Read the story nodes from a loosely typed blob, skipping malformed entries. */
function readNodes(blob: Record<string, unknown>): StoryNode[] {
  const raw = blob.nodes
  if (!Array.isArray(raw)) return []
  const nodes: StoryNode[] = []
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const record = entry as Record<string, unknown>
    const id = typeof record.id === 'string' ? record.id : ''
    const body = typeof record.body === 'string' ? record.body : ''
    if (id) nodes.push({ id, body })
  }
  return nodes
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error' }
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
  const navigate = useNavigate()

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [dialog, setDialog] = useState<ActionDialog>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const surface = await reviewApi.surface(storybookId)
        if (!cancelled) setState({ kind: 'ready', surface })
      } catch (err) {
        console.error('review surface load failed', err)
        if (!cancelled) setState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [reviewApi, storybookId])

  async function runAction(action: () => Promise<unknown>) {
    setSubmitting(true)
    setActionError(false)
    try {
      await action()
      navigate('/guardian')
    } catch (err) {
      console.error('review action failed', err)
      setActionError(true)
      setSubmitting(false)
    }
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
      <p role="alert" className="console__error">
        We could not load this story for review. Please reload.
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
            <article key={passage.node_id} className="review-card">
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
        <p className="console__muted">No flagged passages. This story screened clean.</p>
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

      <div className="review-actionbar">
        <Button variant="danger" onClick={() => setDialog('sendback')}>
          Send Back
        </Button>
        <Button onClick={() => setDialog('approve')}>Approve</Button>
      </div>

      {dialog === 'approve' ? (
        <Dialog
          title="Approve this story?"
          onClose={() => setDialog(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setDialog(null)}>
                Cancel
              </Button>
              <Button
                disabled={submitting}
                onClick={() => void runAction(() => reviewApi.approve(storybookId))}
              >
                Confirm approve
              </Button>
            </>
          }
        >
          {actionError ? (
            <p role="alert" className="review-detail__action-error">
              We could not approve this story. It may be unscreened or no longer in review.
            </p>
          ) : null}
          <p>Approving publishes this story to the assigned children.</p>
        </Dialog>
      ) : null}

      {dialog === 'sendback' ? (
        <Dialog
          title="Send back for revision"
          onClose={() => setDialog(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setDialog(null)}>
                Cancel
              </Button>
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
            <p role="alert" className="review-detail__action-error">
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
