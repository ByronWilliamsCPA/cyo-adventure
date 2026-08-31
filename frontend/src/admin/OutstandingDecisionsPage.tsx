import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { FlagBadge } from '../guardian/FlagBadge'
import { ageBandLabel } from '../guardian/storyRequestOptions'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  makeOutstandingDecisionsApi,
  type OutstandingDecisionItem,
  type RecallReasonCode,
} from './outstandingDecisionsApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: OutstandingDecisionItem[] }

/**
 * Recall reason codes, in display order. Mirrors RecallReasonCodeLiteral in
 * src/cyo_adventure/publishing/reason_codes.py, the same way
 * ReviewDetailPage's SEND_BACK_REASON_CODES mirrors its send-back sibling: the
 * API owns the closed vocabulary, this is only the console's presentation of it.
 *
 * ``threshold_change`` leads because it is the reason this page exists: an owner
 * raises a threshold, books that were compliant yesterday now carry a block,
 * and each needs to go back through the human gate.
 */
const RECALL_REASON_CODES: ReadonlyArray<{ value: RecallReasonCode; label: string }> = [
  { value: 'threshold_change', label: 'Threshold change' },
  { value: 'safety_concern', label: 'Safety concern' },
  { value: 'content_correction', label: 'Content correction' },
  { value: 'curation', label: 'Curation' },
  { value: 'other', label: 'Other' },
]

/** A stable per-row key: a book can appear once per decision kind. */
function rowKey(item: OutstandingDecisionItem): string {
  return `${item.kind}:${item.storybook_id}:${item.version}`
}

/**
 * One-line summary of what is unresolved on this row.
 *
 * Written as a sentence rather than a count triple because the row's job is to
 * let an admin decide whether to open the book, and "1 block" plus the finding's
 * own message is what decides that. The advisory count is deliberately NOT part
 * of the headline (owner ruling 3: advisories are available to dig into, never a
 * gate), so it rides along in the metadata line instead.
 */
function decisionHeadline(item: OutstandingDecisionItem): string {
  if (item.kind === 'cover') {
    return item.cover?.child_facing
      ? 'Cover art is waiting for approval, and this book is on the shelf without it'
      : 'Cover art is waiting for approval'
  }
  const moderation = item.moderation
  if (!moderation) return 'A moderation decision is unresolved'
  if (moderation.report_unusable) {
    // Not "no findings": a report nothing could be drawn from is the case where
    // the book's safety is least established, and phrasing it as an absence is
    // exactly the misreading that let these books sit.
    return 'The moderation report could not be read, so this book has no usable verdict'
  }
  const parts: string[] = []
  if (moderation.block_findings > 0) {
    parts.push(`${moderation.block_findings} block${moderation.block_findings === 1 ? '' : 's'}`)
  }
  if (moderation.flag_findings > 0) {
    parts.push(`${moderation.flag_findings} flag${moderation.flag_findings === 1 ? '' : 's'}`)
  }
  return `${parts.join(' and ')} on a published book`
}

/** The severity pill tone for a row, matching the server's own ordering. */
function rowTone(item: OutstandingDecisionItem): 'block' | 'flag' | 'unscreened' | 'advisory' {
  if (item.kind === 'cover') return 'advisory'
  const moderation = item.moderation
  if (!moderation) return 'flag'
  if (moderation.block_findings > 0) return 'block'
  if (moderation.report_unusable) return 'unscreened'
  return 'flag'
}

/**
 * Admin-only list of decisions no other console surface shows (`RS-C2`,
 * `RS-C3`).
 *
 * The review queue lists ``in_review`` stories, which is correct for its own
 * job and is why two classes of decision had nowhere to appear: a moderation
 * verdict that became a block on an already-PUBLISHED book (what a threshold
 * change produces in bulk), and a cover parked at ``pending_review``. Under
 * ADR-005 the human approver is the final gate, so a decision with no surface
 * is not a missing convenience; it is a decision that never gets made.
 *
 * This page is also where `RS-C1`'s recall gets its control. Recall shipped as
 * an API with no button on purpose: a recall button with no way to find recall
 * candidates is inert, and the candidates are exactly these rows.
 */
export function OutstandingDecisionsPage() {
  usePageTitle('Outstanding Decisions')
  const api = useApi()
  const decisionsApi = useMemo(() => makeOutstandingDecisionsApi(api), [api])

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [recallTarget, setRecallTarget] = useState<OutstandingDecisionItem | null>(null)
  const [reasonCode, setReasonCode] = useState<RecallReasonCode>('threshold_change')
  const [submitting, setSubmitting] = useState(false)
  const [recallError, setRecallError] = useState(false)

  // Bumped after a successful recall to re-run the load effect. A counter
  // rather than calling a shared loader from the click handler: the loader has
  // to live inside the effect (react-hooks/set-state-in-effect rejects an
  // effect that calls a setState-ing callback), and one loader beats two copies
  // of the same error handling.
  const [reloadToken, setReloadToken] = useState(0)

  // #EDGE: timing dependencies: a load can settle after an unmount (route
  // change mid-flight) or after a recall bumped the token, so the flag drops a
  // stale response instead of overwriting a newer list with an older one.
  // #VERIFY: OutstandingDecisionsPage.test.tsx asserts the post-recall re-fetch
  // is what the list reflects ("sends the chosen reason code and re-fetches").
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const items = await decisionsApi.list()
        if (!cancelled) setState({ kind: 'ready', items })
      } catch (err) {
        // #CRITICAL: security: a failed load must never render as an empty
        // list. Under ADR-005 the human approver is the final gate, so "nothing
        // outstanding" is a safety claim about every published book; an outage
        // that produced it would be the same silent all-clear this surface
        // exists to end. classifyApiError also gives a 403 (admin capability
        // revoked mid-session) its own message rather than generic retry copy.
        // #VERIFY: OutstandingDecisionsPage.test.tsx, "shows an error instead of
        // an empty state when the load fails".
        console.error(
          'outstanding decisions load failed:',
          err instanceof Error ? err.message : err
        )
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load outstanding decisions. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [decisionsApi, reloadToken])

  async function confirmRecall(item: OutstandingDecisionItem) {
    setSubmitting(true)
    setRecallError(false)
    try {
      await decisionsApi.recall(item.storybook_id, reasonCode)
      setRecallTarget(null)
      // Re-fetch rather than patching the list in place. A recall changes which
      // rows exist AND what the survivors say (the moderation row goes away, and
      // the same book's cover row stops being child-facing), all of it decided
      // by server-side rules this page deliberately does not reimplement.
      setReloadToken((token) => token + 1)
    } catch (err) {
      console.error('recall failed:', err instanceof Error ? err.message : err)
      setRecallError(true)
    } finally {
      setSubmitting(false)
    }
  }

  if (state.kind === 'loading') {
    return <LoadingStatus />
  }
  if (state.kind === 'error') {
    return <ErrorBanner className="console__error">{state.message}</ErrorBanner>
  }

  const { items } = state

  return (
    <div>
      <h1>Outstanding decisions</h1>
      <p>
        Decisions on books the review queue does not list: a published book whose moderation verdict
        now carries a block or a flag, and cover art still waiting for approval. Worst first, oldest
        content first within each group.
      </p>
      {items.length === 0 ? (
        <p className="console__muted cyo-text-muted" data-testid="no-outstanding-decisions">
          Nothing outstanding. Every published book has a usable, clean verdict and no cover is
          waiting for approval.
        </p>
      ) : (
        <ul className="console-list">
          {items.map((item) => (
            <li key={rowKey(item)} className="console-row cyo-card" data-testid={rowKey(item)}>
              <div className="console-row__body">
                <p className="console-row__title">
                  <FlagBadge tone={rowTone(item)} /> {item.title}
                </p>
                <p>{decisionHeadline(item)}</p>
                <p className="console__muted cyo-text-muted">
                  {item.status} · v{item.version}
                  {item.age_band ? ` · ${ageBandLabel(item.age_band)}` : ''}
                  {item.moderation && item.moderation.advisory_findings > 0
                    ? ` · ${item.moderation.advisory_findings} advisory`
                    : ''}
                </p>
                {item.moderation?.top_finding ? (
                  <p className="console__muted cyo-text-muted">
                    {item.moderation.top_finding.category}: {item.moderation.top_finding.message}
                  </p>
                ) : null}
              </div>
              <div className="console-row__actions">
                {/*
                  Both kinds link to the same review page: it is where the
                  findings, the passages, and the cover approval all live, so
                  sending a cover row somewhere else would split one book's
                  review across two surfaces.
                */}
                <Link to={`/admin/review/${item.storybook_id}`}>Open review</Link>
                {/*
                  #ASSUME: security: `recallable` is the API's own answer,
                  derived from publishing/state_machine.py's transition table.
                  The client never re-derives it from `status`, which would
                  offer a button the API answers 409 to the moment that table
                  changes.
                  #VERIFY: OutstandingDecisionsPage.test.tsx, "offers recall
                  only on a recallable moderation row", plus
                  tests/unit/test_outstanding_decisions.py::
                  test_recallable_is_derived_from_the_transition_table.
                */}
                {item.kind === 'moderation' && item.recallable ? (
                  <Button
                    variant="danger"
                    onClick={() => {
                      setRecallError(false)
                      setReasonCode('threshold_change')
                      setRecallTarget(item)
                    }}
                  >
                    Recall to review
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {recallTarget ? (
        <Dialog
          title={`Recall "${recallTarget.title}"?`}
          onClose={() => setRecallTarget(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setRecallTarget(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={submitting}
                onClick={() => void confirmRecall(recallTarget)}
              >
                Confirm recall
              </Button>
            </>
          }
        >
          {recallError ? (
            <p role="alert" className="cyo-text-error">
              We could not recall this book. Please try again.
            </p>
          ) : null}
          <p>
            This takes the book off every child&apos;s shelf and puts it back in the review queue.
            Assignments and the published version are kept, so approving it again restores the shelf
            with nothing to reassign.
          </p>
          <p className="console__muted cyo-text-muted">
            {/*
              Stated because it is the one thing recall cannot do, and an
              operator reaching for it as an incident response would otherwise
              assume it can: offline eviction is reconcile-on-fetch
              (offline/revocation.ts), so a device already holding this book
              keeps it until its next successful library sync.
            */}
            A device that already downloaded this book keeps its copy until it next syncs its
            library.
          </p>
          <label className="review-detail__reason-code">
            Reason
            <select
              value={reasonCode}
              onChange={(event) => setReasonCode(event.target.value as RecallReasonCode)}
            >
              {RECALL_REASON_CODES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </Dialog>
      ) : null}
    </div>
  )
}
