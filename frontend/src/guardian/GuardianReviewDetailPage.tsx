import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { GUARDIAN_CONSOLE_PATH } from '../routes'
import { FlagBadge } from './FlagBadge'
import { makePassageEditApi } from './passageEditApi'
import type { GateFindingView } from './passageEditApi'
import { Finding, passageDomId, Passage } from './ReviewPassage'
import { makeReviewApi, type ReviewSurface } from './reviewApi'
import { buildReadThrough, pluralize } from './storyReadThrough'
import type { EditableChoice } from './storyReadThrough'
import { StoryStructureSummary } from './StoryStructureSummary'
import { usePassageEdit } from './usePassageEdit'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; surface: ReviewSurface }

/**
 * Guardian-facing review/edit page (register G6, the edit half): a family's
 * own guardian can read the full story a generation run produced and fix a
 * flagged passage's prose or choice labels while the story is still
 * `in_review` or `needs_revision`, without waiting on an admin reviewer for a
 * wording fix.
 *
 * Deliberately NOT a guardian-role-widened `admin/ReviewDetailPage`: this
 * page omits Approve / Send Back / Archive, cover generation, and
 * version-compare entirely. Those stay admin-only (ADR-005: publish is a
 * safety-critical, deliberately human-gated action, and whether a guardian
 * should ever get an equivalent reject/veto action for their own family's
 * story is an open product question this page does not answer or preempt).
 * The two pages share their read-through, passage, and passage-edit building
 * blocks (`storyReadThrough.ts`, `ReviewPassage.tsx`, `passageEditApi.ts`,
 * `usePassageEdit.ts`) so the edit UX and its validation-gate handling stay
 * identical for both audiences.
 *
 * Reachable only for the requesting family's own story: the backend's
 * `_load_review_target` (api/approval.py) authorizes a guardian for the GET
 * review surface only when the storybook's `family_id` matches the
 * guardian's own family, mirroring every other family-scoped guardian
 * endpoint (`authorize_family`). A cross-family id 403s, which this page
 * renders as the standard forbidden message via classifyApiError.
 */
export function GuardianReviewDetailPage() {
  const { storybookId = '' } = useParams()
  const api = useApi()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const passageEditApi = useMemo(() => makePassageEditApi(api), [api])

  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Briefly tint the passage a jump landed on, mirroring the admin page's
  // same affordance for the flagged-passages "Show in story" links.
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
        if (!cancelled && isMountedRef.current) setState({ kind: 'ready', surface })
      } catch (err) {
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error(
          'guardian review surface load failed:',
          err instanceof Error ? err.message : err
        )
        if (!cancelled && isMountedRef.current) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              forbidden: 'This story belongs to a different family.',
              transient: 'We could not load this story. Please reload.',
              server: 'We could not load this story. Please reload.',
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

  const readySurface = state.kind === 'ready' ? state.surface : null

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

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading story…
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <div>
        <p role="alert" className="console__error cyo-text-error">
          {state.message}
        </p>
        <Link to={`${GUARDIAN_CONSOLE_PATH}/intake`}>Back to My Requests</Link>
      </div>
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

  return (
    <section className="review-detail">
      <Link to={`${GUARDIAN_CONSOLE_PATH}/intake`} className="review-detail__back">
        Back to My Requests
      </Link>
      <h1>{title}</h1>

      {/*
        #ASSUME: UI state: a guardian can land here for any status their own
        family's story has passed through (in_review, needs_revision,
        published, archived); the edit affordance below is gated on
        editingDisabled the same way the admin actionbar gates Approve/Send
        Back, so this status line is informational, not a permission check.
        #VERIFY: GuardianReviewDetailPage.test.tsx status-line + editingDisabled tests.
      */}
      <p className="review-detail__status cyo-text-muted">
        {surface.status === 'in_review'
          ? 'Waiting for a reviewer. You can fix a passage below while you wait.'
          : surface.status === 'needs_revision'
            ? 'A reviewer sent this back for changes. Fix the passages below, then it will be re-reviewed.'
            : surface.status === 'published'
              ? 'This story is published and can no longer be edited here.'
              : 'This story can no longer be edited here.'}
      </p>

      {surface.summary ? (
        <div className="review-summary">
          <span className="review-summary__count">
            {pluralize(surface.summary.count, 'finding')}
          </span>
          {surface.summary.hard_block ? <FlagBadge tone="block" label="Hard block" /> : null}
          {surface.summary.soft_flag ? <FlagBadge tone="flag" label="Soft flags" /> : null}
          {surface.summary.repaired ? <FlagBadge tone="flag" label="Repaired" /> : null}
        </div>
      ) : null}

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

      {editNodeId !== null ? (
        <PassageEditDialog
          editNodeId={editNodeId}
          editBody={editBody}
          editChoices={editChoices}
          editSubmitting={editSubmitting}
          editError={editError}
          editGateFindings={editGateFindings}
          editBodyValid={editBodyValid}
          closeEditDialog={closeEditDialog}
          setEditBody={setEditBody}
          setEditChoiceLabel={setEditChoiceLabel}
          saveEdit={saveEdit}
        />
      ) : null}
    </section>
  )
}

// Split out only so the props list stays typed and readable; still owned and
// rendered exclusively by GuardianReviewDetailPage above, not reused
// elsewhere (admin/ReviewDetailPage.tsx inlines the identical dialog rather
// than sharing this, since its dialog is one of four in that file's own
// action-dialog union and factoring it out there would not simplify it).
interface PassageEditDialogProps {
  editNodeId: string
  editBody: string
  editChoices: EditableChoice[]
  editSubmitting: boolean
  editError: string | null
  editGateFindings: GateFindingView[] | null
  editBodyValid: boolean
  closeEditDialog: () => void
  setEditBody: (body: string) => void
  setEditChoiceLabel: (choiceId: string, label: string) => void
  saveEdit: () => Promise<void>
}

function PassageEditDialog({
  editNodeId,
  editBody,
  editChoices,
  editSubmitting,
  editError,
  editGateFindings,
  editBodyValid,
  closeEditDialog,
  setEditBody,
  setEditChoiceLabel,
  saveEdit,
}: PassageEditDialogProps) {
  return (
    <Dialog
      title={`Edit passage ${editNodeId}`}
      onClose={closeEditDialog}
      actions={
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
            #VERIFY: GuardianReviewDetailPage.test.tsx passage-edit success + 422 cases.
          */}
          <Button disabled={!editBodyValid || editSubmitting} onClick={() => void saveEdit()}>
            Save
          </Button>
        </>
      }
    >
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
  )
}
