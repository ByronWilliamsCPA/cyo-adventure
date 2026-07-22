import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makePassageEditApi } from './passageEditApi'
import { makeCoverApi } from '../guardian/coverApi'
import { FlagBadge, verdictTone } from '../guardian/FlagBadge'
import {
  makeReviewApi,
  type FindingView,
  type ReviewSurface,
  type Visibility,
} from '../guardian/reviewApi'
import { StoryStructureSummary } from '../guardian/StoryStructureSummary'
import { buildReadThrough, pluralize, type StoryNodeView } from './reviewDiff'
import { VersionDiffView } from './ReviewCompare'
import { useCoverGeneration } from './useCoverGeneration'
import { useVersionCompare } from './useVersionCompare'
import { usePassageEdit } from './usePassageEdit'

/**
 * DOM id for a passage container. encodeURIComponent keeps the id free of
 * whitespace (node ids are arbitrary strings on this defensive surface) while
 * staying deterministic from both a blob node id and a finding's node_id.
 * Duplicate node ids share a DOM id; a jump lands on the first (reachable)
 * copy, and the duplicate still renders in the unreachable section.
 */
function passageDomId(nodeId: string): string {
  return `passage-${encodeURIComponent(nodeId)}`
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

interface PassageProps {
  node: StoryNodeView
  isStart: boolean
  flagged: boolean
  highlighted: boolean
  knownIds: Set<string>
  onJump: (nodeId: string) => void
  onEdit: (nodeId: string) => void
  editDisabled: boolean
}

/**
 * One passage of the read-through: structure badges (Start / Ending with
 * kind and valence), the prose, then the kid-facing choice labels with a jump
 * button per resolvable target. tabIndex={-1} lets a jump move real focus
 * here; badges carry text, never color alone.
 *
 * `onEdit` opens the G6 passage-edit dialog (prose only: body text and
 * choice labels); `editDisabled` mirrors the Approve/Send Back actionbar's
 * own status guard so an edit is never offered on a published/archived/draft
 * version the backend would reject anyway.
 */
function Passage({
  node,
  isStart,
  flagged,
  highlighted,
  knownIds,
  onJump,
  onEdit,
  editDisabled,
}: PassageProps) {
  const classes = ['review-node']
  if (flagged) classes.push('review-node--flagged')
  if (highlighted) classes.push('review-node--highlight')
  const endingDetail = node.ending
    ? [node.ending.kind, node.ending.valence]
        .filter((part): part is string => part !== null)
        .join(', ')
    : ''
  return (
    <div id={passageDomId(node.id)} tabIndex={-1} className={classes.join(' ')}>
      {isStart || node.isEnding ? (
        <p className="review-node__badges">
          {isStart ? (
            <span className="review-node__badge review-node__badge--start">Start</span>
          ) : null}
          {node.isEnding ? (
            <span className="review-node__badge review-node__badge--ending">
              {endingDetail ? `Ending: ${endingDetail}` : 'Ending'}
            </span>
          ) : null}
        </p>
      ) : null}
      <PassageText text={node.body} />
      <Button
        variant="ghost"
        size="sm"
        className="review-node__edit"
        onClick={() => onEdit(node.id)}
        disabled={editDisabled}
      >
        Edit passage
      </Button>
      {node.choices.length > 0 ? (
        <ul className="review-choices">
          {node.choices.map((choice, index) => (
            // Choices are static per render; index key is stable here.
            <li key={index} className="review-choice">
              <span className="review-choice__label">{choice.label || '(missing label)'}</span>
              {knownIds.has(choice.target) ? (
                <button type="button" className="review-jump" onClick={() => onJump(choice.target)}>
                  Go to {choice.target}
                </button>
              ) : (
                // A dead link would 404 the reviewer's attention; name the
                // defect instead so it can be sent back with a reason.
                <span className="review-choice__missing cyo-text-error">missing target</span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
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
  const passageEditApi = useMemo(() => makePassageEditApi(api), [api])
  const navigate = useNavigate()
  const location = useLocation()

  // The ordered review-queue ids the console handed off (UX-A1), so this page
  // can show "Reviewing N of M" and auto-advance to the next item after a
  // decision. Absent on a direct deep-link, which degrades to the old
  // back-to-queue behavior.
  const reviewQueue = useMemo<string[]>(() => {
    const raw = (location.state as { reviewQueue?: unknown } | null)?.reviewQueue
    return Array.isArray(raw) && raw.every((v): v is string => typeof v === 'string')
      ? raw
      : []
  }, [location.state])
  const queueIndex = reviewQueue.indexOf(storybookId)
  const nextInQueue = queueIndex >= 0 ? reviewQueue[queueIndex + 1] : undefined

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [dialog, setDialog] = useState<ActionDialog>(null)
  const [visibility, setVisibility] = useState<Visibility>('family')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState(false)

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

  // Briefly tint the passage a jump landed on so the reviewer's eye finds it
  // after the scroll; cleared by a timer (and on unmount), not by blur, so
  // keyboard users keep the highlight while reading.
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (highlightTimer.current !== null) clearTimeout(highlightTimer.current)
    },
    []
  )

  const jumpToPassage = useCallback((nodeId: string) => {
    const el = document.getElementById(passageDomId(nodeId))
    if (!el) return
    // Focus first (the container carries tabIndex={-1}): assistive tech
    // announces the passage and the next Tab starts from it; preventScroll
    // leaves the scrolling to scrollIntoView. Optional-call scrollIntoView:
    // it is absent under jsdom (test env) and always present in real browsers.
    el.focus({ preventScroll: true })
    el.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    setHighlightedId(nodeId)
    if (highlightTimer.current !== null) clearTimeout(highlightTimer.current)
    highlightTimer.current = setTimeout(() => setHighlightedId(null), 1800)
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
              server: 'We could not load this story for review. Please reload.',
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

  // #CRITICAL: data integrity/concurrency: `state` is the single source of
  // truth for the loaded review surface and stays owned here, not by any of
  // the three hooks below, so a cover-generation poll, a version-compare
  // fetch, and a passage-edit save can never each hold a stale copy that
  // drifts from what the page renders. Each hook receives only the derived
  // slice it needs (`readyVersion` / a nullable `surface`), and the edit hook
  // is handed `onSurfaceRefreshed`, which feeds a successful save's refreshed
  // surface back into this same `setState`.
  // #VERIFY: ReviewDetailPage.test.tsx's passage-edit "saves an edit and
  // refreshes the surface" test asserts the page re-renders the new prose
  // from this same state slot after a save.
  const readyVersion = state.kind === 'ready' ? state.surface.version : null
  const readySurface = state.kind === 'ready' ? state.surface : null

  const { coverStatus, coverBusy, coverTimedOut, generateCover } = useCoverGeneration({
    storybookId,
    readyVersion,
    coverApi,
    isMountedRef,
  })

  const { compareOpen, compareState, toggleCompare, diff } = useVersionCompare({
    storybookId,
    surface: readySurface,
    reviewApi,
    isMountedRef,
  })

  const {
    editNodeId,
    editBody,
    editChoices,
    editSubmitting,
    editError,
    editGateFindings,
    editBodyValid,
    editingDisabled,
    openEditDialog,
    closeEditDialog,
    setEditBody,
    setEditChoiceLabel,
    saveEdit,
  } = usePassageEdit({
    storybookId,
    surface: readySurface,
    passageEditApi,
    onSurfaceRefreshed: (refreshed) => setState({ kind: 'ready', surface: refreshed }),
  })

  async function runAction(action: () => Promise<unknown>) {
    setSubmitting(true)
    setActionError(false)
    try {
      await action()
      // UX-A1: after a decision, advance to the next item in the handed-off
      // queue instead of always bouncing back to the list; on the last item (or
      // a direct deep-link with no queue) return to the queue as before.
      if (nextInQueue !== undefined) {
        void navigate(`/admin/review/${nextInQueue}`, { state: { reviewQueue } })
      } else {
        void navigate('/admin')
      }
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
  const readThrough = buildReadThrough(surface.blob)
  const totalPassages = readThrough.reachable.length + readThrough.unreachable.length
  const coverage = `${pluralize(totalPassages, 'passage')}, ${readThrough.reachable.length} reachable from the start, ${pluralize(readThrough.endingCount, 'ending')}`
  const flaggedIds = new Set(surface.flagged_passages.map((passage) => passage.node_id))
  const allFindings = [
    ...surface.flagged_passages.flatMap((passage) => passage.findings),
    ...surface.story_level_findings,
  ]
  const title =
    typeof surface.blob.title === 'string' && surface.blob.title
      ? surface.blob.title
      : surface.storybook_id
  const reasonValid = reason.trim().length >= 1 && reason.trim().length <= 2000

  return (
    <section className="review-detail">
      {queueIndex >= 0 ? (
        <p className="review-detail__queue-position cyo-text-muted">
          Reviewing {queueIndex + 1} of {reviewQueue.length} in the queue
        </p>
      ) : null}
      <h1>{title}</h1>

      {!surface.screened ? (
        <p role="alert" className="review-detail__unscreened">
          This version was never screened by moderation. Approving it will be rejected until it has
          been screened.
        </p>
      ) : null}

      {surface.summary ? (
        // Moderation verdict strip the reviewer scans before any prose.
        // hard_block gets the danger tone; every badge carries text, never
        // color alone.
        <div className="review-summary">
          <span className="review-summary__count">
            {pluralize(surface.summary.count, 'finding')}
          </span>
          {surface.summary.hard_block ? <FlagBadge tone="block" label="Hard block" /> : null}
          {surface.summary.soft_flag ? <FlagBadge tone="flag" label="Soft flags" /> : null}
          {surface.summary.repaired ? <FlagBadge tone="flag" label="Repaired" /> : null}
          <FlagBadge
            tone={surface.summary.reviewer_independent ? 'clean' : 'advisory'}
            label={
              surface.summary.reviewer_independent
                ? 'Independent review'
                : 'Not independently reviewed'
            }
          />
        </div>
      ) : null}

      {(() => {
        // A classifier_degraded finding means an automated safety classifier was
        // down or unconfigured when this story was screened. Surface it as a
        // distinct alert so the reviewer does not read a thin report as "clean"
        // when part of the automated net never ran.
        const degradedSources = Array.from(
          new Set(
            surface.story_level_findings
              .filter((finding) => finding.category === 'classifier_degraded')
              .map((finding) => finding.source)
              .filter((source): source is string => typeof source === 'string'),
          ),
        )
        return degradedSources.length > 0 ? (
          <p role="alert" className="review-detail__degraded">
            Automated screening was degraded for this version:{' '}
            {degradedSources.join(', ')} did not run. Review the prose extra carefully; the
            automated safety net was not fully applied.
          </p>
        ) : null
      })()}

      {surface.summary?.repaired ? (
        <p className="review-repaired-hint cyo-text-muted">
          This story was auto-repaired. Compare with the previous version to see what changed.
        </p>
      ) : null}

      {surface.version > 1 ? (
        <div className="review-compare">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => toggleCompare()}
            aria-expanded={compareOpen}
          >
            {compareOpen ? 'Hide comparison' : `Compare with version ${surface.version - 1}`}
          </Button>
          {compareOpen ? (
            <div className="review-compare__panel">
              {compareState.kind === 'loading' ? (
                <p className="review-compare__status" role="status" aria-live="polite">
                  Loading version {surface.version - 1}…
                </p>
              ) : compareState.kind === 'unavailable' ? (
                <p className="review-compare__status cyo-text-muted">
                  Version {surface.version - 1} is no longer available.
                </p>
              ) : compareState.kind === 'error' ? (
                <p role="alert" className="review-compare__status cyo-text-error">
                  {compareState.message}
                </p>
              ) : compareState.kind === 'ready' && diff ? (
                <VersionDiffView diff={diff} />
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/*
        G5 skim aid: the structure/branch overview a reviewer scans before
        deciding whether to read every passage or jump straight to the
        flagged ones below. Open by default since this IS the skim entry
        point; <details> lets it collapse out of the way once read.
      */}
      <details className="review-overview" open>
        <summary>Story overview</summary>
        <div className="review-overview__body">
          <StoryStructureSummary
            blob={surface.blob}
            screened={surface.screened}
            flaggedCount={allFindings.length}
            findings={allFindings}
          />
        </div>
      </details>

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
              {readThrough.knownIds.has(passage.node_id) ? (
                <button
                  type="button"
                  className="review-jump review-card__jump"
                  onClick={() => jumpToPassage(passage.node_id)}
                >
                  Show in story
                </button>
              ) : (
                // A finding's node_id misses the read-through when the blob
                // node's id was malformed and got a synthetic one; the prose
                // above is still the full flagged content, so nothing hides.
                <span className="review-card__missing-node cyo-text-muted">
                  This passage id was not found in the story below.
                </span>
              )}
            </article>
          ))}
        </div>
      ) : surface.screened ? (
        <p className="console__muted cyo-text-muted">
          No flagged passages. This story screened clean.
        </p>
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
        <p className="review-coverage cyo-text-muted">{coverage}</p>
        {totalPassages === 0 ? (
          <p role="alert" className="cyo-text-error">
            No readable passages were found in this version. Do not approve it until the story
            content can be reviewed.
          </p>
        ) : null}
        {readThrough.reachable.map((node, index) => (
          // The traversal root is always reachable[0]; it gets the Start badge.
          <Passage
            key={node.blobIndex}
            node={node}
            isStart={index === 0}
            flagged={flaggedIds.has(node.id)}
            highlighted={highlightedId === node.id}
            knownIds={readThrough.knownIds}
            onJump={jumpToPassage}
            onEdit={openEditDialog}
            editDisabled={editingDisabled}
          />
        ))}
        {readThrough.unreachable.length > 0 ? (
          <section className="review-unreachable" aria-labelledby="review-unreachable-heading">
            <h3 id="review-unreachable-heading" className="review-unreachable__heading">
              Unreachable passages
            </h3>
            <p className="review-unreachable__note cyo-text-muted">
              No choice path from the start reaches these passages. They are listed here so every
              passage still gets reviewed.
            </p>
            {readThrough.unreachable.map((node) => (
              <Passage
                key={node.blobIndex}
                node={node}
                isStart={false}
                flagged={flaggedIds.has(node.id)}
                highlighted={highlightedId === node.id}
                knownIds={readThrough.knownIds}
                onJump={jumpToPassage}
                onEdit={openEditDialog}
                editDisabled={editingDisabled}
              />
            ))}
          </section>
        ) : null}
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
          {coverStatus === 'generating' && !coverTimedOut ? 'Generating cover…' : 'Generate cover'}
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

      {editNodeId !== null ? (
        <Dialog title={`Edit passage ${editNodeId}`} onClose={closeEditDialog} actions={
          <>
            <Button variant="ghost" onClick={closeEditDialog} disabled={editSubmitting}>
              Cancel
            </Button>
            {/*
              #CRITICAL: security: prose-only edit; the backend re-runs the
              deterministic gate and re-review before persisting, and rejects
              (422, unchanged blob) an edit that breaks a structural/length/
              reading-level rule. This dialog never lets structure (ids,
              targets, conditions, effects) be touched -- only body text and
              existing choice labels are editable fields here.
              #VERIFY: ReviewDetailPage.test.tsx passage-edit success + 422 cases.
            */}
            <Button
              disabled={!editBodyValid || editSubmitting}
              onClick={() => void saveEdit()}
            >
              Save
            </Button>
          </>
        }>
          {editError ? (
            <p role="alert" className="review-detail__action-error cyo-text-error">
              {editError}
            </p>
          ) : null}
          {editGateFindings && editGateFindings.length > 0 ? (
            <div role="alert" className="review-detail__gate-failure cyo-text-error">
              <p>This edit did not pass the validation gate:</p>
              <ul>
                {editGateFindings.map((finding, index) => (
                  // Findings are static per render; index key is stable here.
                  <li key={index}>
                    {finding.rule_id}: {finding.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <label className="review-detail__edit-body">
            Passage text
            <textarea
              value={editBody}
              onChange={(event) => setEditBody(event.target.value)}
              maxLength={20000}
              rows={6}
              required
            />
          </label>
          {editChoices.length > 0 ? (
            <fieldset className="review-detail__edit-choices">
              <legend>Choice labels</legend>
              {editChoices.map((choice) => (
                <label key={choice.id} className="review-detail__edit-choice">
                  {`Choice to ${choice.target || '(missing target)'}`}
                  <input
                    type="text"
                    value={choice.label}
                    maxLength={500}
                    onChange={(event) => setEditChoiceLabel(choice.id, event.target.value)}
                  />
                </label>
              ))}
            </fieldset>
          ) : null}
        </Dialog>
      ) : null}
    </section>
  )
}
