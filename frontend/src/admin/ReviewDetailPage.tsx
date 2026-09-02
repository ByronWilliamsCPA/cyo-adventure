import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'
import { isAxiosError } from 'axios'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { makeCoverApi } from '../guardian/coverApi'
import { makeRescreenApi, type BookVerdictView } from './rescreenApi'
import { FlagBadge } from '../guardian/FlagBadge'
import { verdictTone } from '../guardian/verdictTone'
import {
  affectedPassagesLabel,
  distinctFindingsLabel,
  surfaceCounts,
  surfacePopulation,
  tierBreakdownLabel,
} from '../guardian/findingCounts'
import { makePassageEditApi } from '../guardian/passageEditApi'
import { findingKey, readReviewedKeys, toggleReviewed } from './findingTriageStore'
import { Finding, passageDomId, Passage, RankedFinding } from '../guardian/ReviewPassage'
import {
  makeReviewApi,
  type FindingView,
  type GenerationMeasuresView,
  type ReviewSurface,
  type SendBackReasonCode,
  type Visibility,
} from '../guardian/reviewApi'
import { ageBandLabel } from '../guardian/storyRequestOptions'
import { StoryStructureSummary } from '../guardian/StoryStructureSummary'
import { usePassageEdit } from '../guardian/usePassageEdit'
import { buildReadThrough, pluralize } from './reviewDiff'
import {
  DEFAULT_SAMPLE_SIZE,
  SAMPLE_NOT_CALIBRATED,
  buildReviewSample,
  readSampleBandContext,
} from './reviewSample'
import { VersionDiffView } from './ReviewCompare'
import { useCoverGeneration } from './useCoverGeneration'
import { useVersionCompare } from './useVersionCompare'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; surface: ReviewSurface }

type ActionDialog = null | 'approve' | 'sendback' | 'archive' | 'rescreen'

/**
 * Send-back reason codes, in display order, paired with a short reviewer-
 * facing label. Mirrors SendBackReasonCodeLiteral in
 * src/cyo_adventure/publishing/reason_codes.py; the API is the source of
 * truth for the wire contract and the domain module owns the vocabulary, this is
 * just the console's presentation of the same closed vocabulary.
 */
const SEND_BACK_REASON_CODES: ReadonlyArray<{ value: SendBackReasonCode; label: string }> = [
  { value: 'safety_concern', label: 'Safety concern' },
  { value: 'reading_level', label: 'Reading level' },
  { value: 'coherence_error', label: 'Coherence error' },
  { value: 'continuity_error', label: 'Continuity error' },
  { value: 'weak_choices', label: 'Weak choices' },
  { value: 'repetitive', label: 'Repetitive' },
  { value: 'prose_quality', label: 'Prose quality' },
  { value: 'unsatisfying_ending', label: 'Unsatisfying ending' },
  { value: 'factual_error', label: 'Factual error' },
  { value: 'other', label: 'Other' },
]

/**
 * Single-story re-screen trigger state (register A4's UI-only gap: the
 * backend `POST /api/v1/admin/rescreen` was fully complete and tested with
 * zero admin callers). Deliberately separate from `submitting`/`actionError`
 * (the approve/send-back/archive trio): a re-screen is not a status
 * transition and, unlike those three, its result (the verdict) is worth
 * surfacing in place rather than navigating away.
 */
type RescreenState =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'success'; verdict: BookVerdictView | null }
  | { kind: 'error' }

/**
 * Flags-first review detail (C4a-4, wireframe 4.4). Flagged passages surface
 * first, then the full story read-through with flagged nodes highlighted. The
 * Approve / Send Back actions stay pinned at the bottom. Swipe-to-approve is
 * deliberately excluded (ADR-005: approval is safety-critical and must be a
 * deliberate, recorded human action).
 */
/**
 * Renders a rate as a whole percentage, or `null` when there is no rate.
 *
 * The null return is the point: an absent measurement must not render as
 * "0%", which an approver would read as a book that filled nothing.
 */
function asPercent(rate: number | null | undefined): string | null {
  return typeof rate === 'number' ? `${Math.round(rate * 100)}%` : null
}

/**
 * The measurements behind the routing decision, shown alongside the findings
 * they explain (R-2).
 *
 * Without this the approval screen showed findings but not the numbers the
 * automated gate judged them on, so a book that scraped past the fill floor
 * and one that cleared it comfortably looked identical.
 *
 * Deliberately absent: the deterministic validator's `safety_flagged`. Its
 * SAFE-14 producer is a Phase-2 stub that returns an empty finding list by
 * construction, so it is structurally always false and would read here as a
 * clean bill from a check that never ran. The safety roll-up comes from the
 * moderation gate, which does run.
 */
function GenerationMeasuresBlock({ measures }: { measures: GenerationMeasuresView }) {
  const rate = asPercent(measures.fill_rate)
  const floor = asPercent(measures.fill_rate_floor)
  const concerns = measures.safety_concerns ?? []
  return (
    <div className="review-group review-measures" id="generation-measures">
      <h2>What the automated gate measured</h2>
      <ul className="review-measures__list">
        <li className="review-measures__item">
          {rate === null ? (
            <span className="cyo-text-muted">Fill rate not recorded for this version.</span>
          ) : (
            <>
              <span className="review-measures__label">Fill rate</span>
              <span className="review-measures__value">{rate}</span>
              {floor === null ? null : (
                <span className="cyo-text-muted">of the commissioned words (floor {floor})</span>
              )}
            </>
          )}
          {/*
            Outside the rate branch on purpose: the downgrade flag is persisted
            independently of the rate, so a version whose rate is absent or
            malformed can still have been routed as below-floor. Nesting the
            badge inside the rate branch hid exactly that combination, which is
            the case an approver most needs to see.
          */}
          {measures.fill_rate_downgrade ? (
            <FlagBadge tone="flag" label="Below the fill floor" />
          ) : null}
        </li>
        {/*
            `RS-A3`: this read "The moderation gate raised no content
            concerns" while five findings rendered directly below it, because
            `measures.safety_concerns` is built ONLY from non-structural
            safety-category findings that carry a concern label
            (review_surface.py::_generation_measures). Empty here means no
            concern LABEL was recorded, which is not the same claim as no
            findings, so the copy now names the population it counted.
          */}
        <li className="review-measures__item">
          {concerns.length === 0 ? (
            <span className="cyo-text-muted">
              No safety concern labels were recorded for this version. Findings below still need a
              look; this line only reports labelled concerns.
            </span>
          ) : (
            <>
              <span className="review-measures__label">Concerns raised</span>
              {concerns.map((entry) => (
                <span key={entry.concern} className="review-measures__concern">
                  {entry.concern} ({entry.count})
                </span>
              ))}
            </>
          )}
        </li>
      </ul>
    </div>
  )
}

/**
 * Narrow an unknown thrown value to the `rule` a `BusinessLogicError`
 * carries (`core/exceptions.py::to_dict`'s `details.rule`), or `null` when
 * the response either has no body shaped that way or never arrived at all
 * (a transient failure, a 404, an offline client).
 *
 * `approve_requires_override_reason` is genuinely reachable here even
 * through a correct client: `needsOverride` is computed once from the
 * surface loaded at page-open, and never revalidated before submit, so a
 * concurrent re-screen or edit that raises a finding's severity between load
 * and submit reaches this exact rule on the backend's re-check.
 */
function businessRuleOf(err: unknown): string | null {
  if (!isAxiosError(err)) return null
  const data: unknown = err.response?.data
  if (typeof data !== 'object' || data === null) return null
  const details = (data as Record<string, unknown>).details
  if (typeof details !== 'object' || details === null) return null
  const rule = (details as Record<string, unknown>).rule
  return typeof rule === 'string' ? rule : null
}

/**
 * Thin wrapper whose only job is the `key`: React Router reuses the same
 * `ReviewDetailPageInner` instance across a `storybookId` param change (the
 * route registers no key of its own), which is exactly what the review
 * queue's auto-advance (UX-A1, `runAction` below) does after every decision.
 * Without this, every piece of this page's local state, most importantly the
 * approve dialog's open/closed flag and its override-reason textarea, rides
 * from the story just decided into the next, unrelated one instead of
 * starting fresh. Keying on `storybookId` forces a full unmount/remount on
 * every navigation to a different story, which is the React-idiomatic reset
 * here (an effect that calls several setState functions to mimic this was
 * rejected by this repo's `react-hooks/set-state-in-effect` lint rule, and
 * remounting also covers every other piece of local state this page owns or
 * will ever come to own, not just the five fields this bug happened to be
 * found through).
 * #CRITICAL: security: a justification an admin typed to approve over one
 * book's severe finding must never survive to gate, or worse silently
 * satisfy, an unrelated next book's approval
 * (publishing/service.py::approve, rule="approve_requires_override_reason").
 * #VERIFY: ReviewDetailPage.test.tsx "clears the approve dialog and its
 * override reason when the queue advances to a new story".
 */
export function ReviewDetailPage() {
  const { storybookId = '' } = useParams()
  return <ReviewDetailPageInner key={storybookId} />
}

const EMPTY_KEYS: Set<string> = new Set()

function ReviewDetailPageInner() {
  usePageTitle('Review')
  const { storybookId = '' } = useParams()
  const api = useApi()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const coverApi = useMemo(() => makeCoverApi(api), [api])
  const passageEditApi = useMemo(() => makePassageEditApi(api), [api])
  const rescreenApi = useMemo(() => makeRescreenApi(api), [api])
  const navigate = useNavigate()
  const location = useLocation()

  // The ordered review-queue ids the console handed off (UX-A1), so this page
  // can show "Reviewing N of M" and auto-advance to the next item after a
  // decision. Absent on a direct deep-link, which degrades to the old
  // back-to-queue behavior.
  const reviewQueue = useMemo<string[]>(() => {
    const raw = (location.state as { reviewQueue?: unknown } | null)?.reviewQueue
    return Array.isArray(raw) && raw.every((v): v is string => typeof v === 'string') ? raw : []
  }, [location.state])
  const queueIndex = reviewQueue.indexOf(storybookId)
  const nextInQueue = queueIndex >= 0 ? reviewQueue[queueIndex + 1] : undefined

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [dialog, setDialog] = useState<ActionDialog>(null)
  const [visibility, setVisibility] = useState<Visibility>('family')
  const [overrideReason, setOverrideReason] = useState('')
  const [reason, setReason] = useState('')
  const [reasonCode, setReasonCode] = useState<SendBackReasonCode>('other')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState(false)
  // Which backend rule (BusinessLogicError's details.rule) a failed approve
  // was rejected for, or null when the failure was not that shape (a
  // transient error, a 404, ...). Only the approve dialog renders a
  // rule-specific message from this; sendBack/archive keep their own generic
  // copy regardless of what this holds.
  // #VERIFY: ReviewDetailPage.test.tsx "surfaces a rule-specific message when
  // the backend rejects approval for needing an override reason".
  const [actionErrorRule, setActionErrorRule] = useState<string | null>(null)
  const [rescreenState, setRescreenState] = useState<RescreenState>({ kind: 'idle' })

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

  // RS-A5: per-finding "I have looked at this" markers, so a reviewer 60
  // findings deep can see where they are. Browser-local (localStorage),
  // scoped to this book and version, and deliberately never sent to the
  // server.
  //
  // #CRITICAL: security: triage state MUST NOT gate approval. It lives in a
  // store the reviewer's browser can clear at any moment, so treating it as
  // an approval precondition would let a cache eviction silently reset a
  // safety decision. Nothing below feeds `needsOverride`, the confirm
  // button's disabled state, or the approve request body.
  // #VERIFY: ReviewDetailPage.test.tsx "marking every finding reviewed
  // changes nothing about approval".
  //
  // Derived, not synced: `stored` re-reads whenever the book or version
  // changes, and `override` (this session's toggles) only wins while its own
  // scope still matches. An effect that pushed the stored value into state
  // would be the same logic with a stale window in it, and would make the
  // reset depend on a dependency array instead of on the scope comparison.
  // ReviewDetailPage's `key={storybookId}` remounts this component per book
  // as well, so the scope check is the second of two guards; it is kept
  // because that `key` exists for the approve dialog, not for triage.
  // #VERIFY: ReviewDetailPage.test.tsx "shows the next book unmarked when the
  // queue advances to it" fails when both guards are removed.
  const triageScope = `${storybookId}:${readyVersion ?? ''}`
  const storedReviewedKeys = useMemo(
    () => (readyVersion === null ? EMPTY_KEYS : readReviewedKeys(storybookId, readyVersion)),
    [storybookId, readyVersion]
  )
  const [reviewedOverride, setReviewedOverride] = useState<{
    scope: string
    keys: Set<string>
  } | null>(null)
  const reviewedKeys =
    reviewedOverride !== null && reviewedOverride.scope === triageScope
      ? reviewedOverride.keys
      : storedReviewedKeys
  const toggleFindingReviewed = useCallback(
    (key: string) => {
      if (readyVersion === null) return
      setReviewedOverride((current) => ({
        scope: triageScope,
        keys: toggleReviewed(
          storybookId,
          readyVersion,
          key,
          current !== null && current.scope === triageScope ? current.keys : storedReviewedKeys
        ),
      }))
    },
    [storybookId, readyVersion, triageScope, storedReviewedKeys]
  )
  const triageFor = useCallback(
    (finding: FindingView) => {
      const key = findingKey(finding)
      return { reviewed: reviewedKeys.has(key), onToggle: () => toggleFindingReviewed(key) }
    },
    [reviewedKeys, toggleFindingReviewed]
  )

  const {
    coverStatus,
    coverUrl,
    coverBusy,
    coverTimedOut,
    coverApproveError,
    generateCover,
    approveCover,
  } = useCoverGeneration({
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
    setActionErrorRule(null)
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
      setActionErrorRule(businessRuleOf(err))
    } finally {
      // #CRITICAL: security: this MUST run on the success path too, not only
      // the catch above. It previously did not, so after one successful
      // queue-advance action `submitting` stayed true for the rest of the
      // session and every later Confirm button (approve/send-back/archive)
      // was permanently disabled. That accidentally hid a related defect: a
      // stale override reason (see the storybookId-reset effect above) could
      // never actually be submitted while Confirm stayed disabled, so fixing
      // this is what makes that other fix observable and exercisable at all.
      // #VERIFY: ReviewDetailPage.test.tsx "re-enables the confirm button for
      // a second action after the first succeeds".
      setSubmitting(false)
    }
  }

  // Open/close reset the transient action state so a prior failure can never
  // bleed into the other dialog: without this, a failed Approve leaves
  // actionError set, and reopening (or switching to Send Back) would render a
  // stale error alert for an action the reviewer never attempted.
  function openDialog(kind: Exclude<ActionDialog, null>) {
    setActionError(false)
    setActionErrorRule(null)
    // Reset to the default visibility every time the approve dialog opens, so
    // a prior "catalog" choice on one story never silently carries over and
    // gets applied to the next approval.
    if (kind === 'approve') setVisibility('family')
    // Same reasoning as actionError above: a prior re-screen's result or
    // error must never bleed into the next time this dialog opens.
    if (kind === 'rescreen') setRescreenState({ kind: 'idle' })
    setDialog(kind)
  }

  function closeDialog() {
    setActionError(false)
    setActionErrorRule(null)
    setReason('')
    setReasonCode('other')
    setOverrideReason('')
    setRescreenState({ kind: 'idle' })
    setDialog(null)
  }

  // Re-screens ONLY this story (register A4's single-story trigger; a
  // full-catalog sweep is Phase 9 and explicitly out of scope). Deliberately
  // does not use `runAction`: a re-screen never changes the story's status,
  // so there is nothing to navigate away to, and the point is to surface the
  // verdict in place, not to advance a queue.
  //
  // #ASSUME: data integrity: the backend silently skips a scoped id that is
  // not currently published, so `results` can come back empty even on a 200.
  // The dialog treats a missing verdict as its own explicit state (see the
  // `results[0] ?? null` handling below) rather than crashing or claiming a
  // pass.
  // #VERIFY: ReviewDetailPage.test.tsx "re-screen" success/error/empty-results cases.
  async function runRescreen() {
    setRescreenState({ kind: 'submitting' })
    try {
      const summary = await rescreenApi.triggerForStorybook(storybookId)
      setRescreenState({ kind: 'success', verdict: summary.results[0] ?? null })
    } catch (err) {
      // Log the message, not the axios error object (its config carries the
      // caller's Authorization bearer token), mirroring every other catch on
      // this page.
      console.error('rescreen failed:', err instanceof Error ? err.message : err)
      setRescreenState({ kind: 'error' })
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
      <p role="alert" className="console__error cyo-text-error">
        {state.message}
      </p>
    )
  }

  const { surface } = state
  const readThrough = buildReadThrough(surface.blob)
  // `RS-A2`: prose lookup so a ranked finding can be the entry point to its
  // own affected passages. Built from the read-through rather than from
  // flagged_passages, because `RS-A1` deliberately keeps low advisories OUT
  // of flagged_passages; sourcing the prose there would leave exactly the
  // collapsed findings with no context, which is the opposite of "counted and
  // available for a reviewer to dig into".
  const proseByNodeId = new Map(
    [...readThrough.reachable, ...readThrough.unreachable].map((node) => [node.id, node.body])
  )
  const proseForNode = (nodeId: string): string | null => proseByNodeId.get(nodeId) ?? null
  const totalPassages = readThrough.reachable.length + readThrough.unreachable.length
  const coverage = `${pluralize(totalPassages, 'passage')}, ${readThrough.reachable.length} reachable from the start, ${pluralize(readThrough.endingCount, 'ending')}`
  // `RS-A3`: every count this page shows comes from here, so a reviewer can
  // never be handed two numbers for one book without being told which
  // population each one counted.
  const counts = surfaceCounts(surface)
  // The very population `counts.distinct` counted, for the story-overview
  // footer's tier split, so the badge and its breakdown cannot disagree: both
  // come from surfacePopulation, including its legacy-report fallback.
  const mergedFindings = surfacePopulation(surface)
  // `RS-A4`: every node any finding names, which is a wider set than
  // flaggedIds. flagged_passages is the fan-out, and `RS-A1` deliberately
  // keeps low advisories out of it, so a node named ONLY by a collapsed low
  // advisory is absent there. Sampling it as "the gate said nothing here"
  // would be false: the gate did say something, quietly.
  const findingNodeIds = new Set<string>(surface.flagged_passages.map((passage) => passage.node_id))
  for (const finding of mergedFindings) {
    if (finding.node_id !== null) findingNodeIds.add(finding.node_id)
    for (const nodeId of finding.node_ids ?? []) findingNodeIds.add(nodeId)
  }
  // `RS-A6`: every finding that names a node, keyed by node, so the edit
  // dialog can show a reviewer WHAT is wrong with the prose it is asking them
  // to rewrite. Both sources are unioned for the same reason findingNodeIds
  // unions them: a low advisory is kept out of the fan-out by design
  // (`RS-A1`), so a node named only by one is absent from flagged_passages,
  // and a dialog built on that source alone would show "nothing recorded" for
  // a passage the gate did comment on.
  const findingsByNodeId = new Map<string, FindingView[]>()
  const noteFinding = (nodeId: string, finding: FindingView) => {
    const existing = findingsByNodeId.get(nodeId)
    if (existing === undefined) {
      findingsByNodeId.set(nodeId, [finding])
      return
    }
    // The two sources overlap by construction (a fanned-out finding is in
    // both), so dedupe on the same identity the triage store keys on.
    const key = findingKey(finding)
    if (!existing.some((seen) => findingKey(seen) === key)) existing.push(finding)
  }
  for (const passage of surface.flagged_passages) {
    for (const finding of passage.findings) noteFinding(passage.node_id, finding)
  }
  for (const finding of mergedFindings) {
    const targets =
      finding.node_ids && finding.node_ids.length > 0
        ? finding.node_ids
        : finding.node_id !== null && finding.node_id !== undefined
          ? [finding.node_id]
          : []
    for (const nodeId of targets) noteFinding(nodeId, finding)
  }
  const sample = buildReviewSample(
    [...readThrough.reachable, ...readThrough.unreachable],
    findingNodeIds,
    DEFAULT_SAMPLE_SIZE
  )
  const bandContext = readSampleBandContext(surface.blob)
  const tierBreakdown = tierBreakdownLabel(counts)
  const passageScope = affectedPassagesLabel(counts)
  const flaggedIds = new Set(surface.flagged_passages.map((passage) => passage.node_id))
  const allFindings = [
    ...surface.flagged_passages.flatMap((passage) => passage.findings),
    ...surface.story_level_findings,
  ]
  // Mirrors the backend's severe_finding_counts exactly (moderation/report.py,
  // gated on by publishing/service.py::approve, rule="approve_requires_
  // override_reason"; api/approval.py::approve_storybook only forwards
  // override_reason to that call and holds none of the gating logic itself):
  // a block verdict at any severity, or a flag verdict at high severity,
  // requires the reviewer to record why they are approving over it.
  // Advisories, and flags below high severity, never require one.
  // #CRITICAL: security: this predicate must stay in lockstep with the
  // backend's; drifting it looser would let the confirm button enable without
  // the reason the backend actually demands (a 400 the reviewer cannot
  // recover from except by retyping), and drifting it stricter would block a
  // legitimate approval the backend would have allowed.
  // #VERIFY: ReviewDetailPage.test.tsx "requires an override reason before
  // approving over a block finding".
  const needsOverride = allFindings.some(
    (finding) =>
      finding.verdict === 'block' || (finding.verdict === 'flag' && finding.severity === 'high')
  )
  // Stage B3 additive fields (design doc 2.6): default to [] so an older
  // backend response or a pre-Stage-B stored report (which projects these as
  // empty, per test_build_review_surface_new_buckets_degrade_on_legacy_report)
  // renders none of the new sections rather than throwing on `undefined`.
  const rankedFindings = surface.ranked_findings ?? []
  const structuralFindings = surface.structural_findings ?? []
  const lowAdvisoryFindings = surface.low_advisory_findings ?? []
  const validatorFindings = surface.validator_findings ?? []
  // The findings that actually render a triage control. The fan-out fallback
  // population (surfacePopulation's legacy arm) renders through Passage/Finding
  // instead, so counting it here would give the progress line a denominator
  // the reviewer has no way to reach.
  const triageableFindings = [...rankedFindings, ...structuralFindings, ...lowAdvisoryFindings]
  const triagedCount = triageableFindings.filter((finding) =>
    reviewedKeys.has(findingKey(finding))
  ).length
  const title =
    typeof surface.blob.title === 'string' && surface.blob.title
      ? surface.blob.title
      : surface.storybook_id
  const reasonValid = reason.trim().length >= 1 && reason.trim().length <= 2000
  // `RS-A6`: the findings on the passage the edit dialog is open over. Empty
  // is a real case, not a bug: the `RS-A4` spot check offers an edit on a
  // passage nothing flagged.
  const editFindings = editNodeId === null ? [] : (findingsByNodeId.get(editNodeId) ?? [])

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
          {/*
            `RS-A3`: this used to render `surface.summary.count`, the count of
            finding rows PERSISTED on the version (moderation/report.py
            ::to_dict, `len(persisted)`). That is a third population, distinct
            from both what this page renders and what the queue row shows: it
            predates the admin noise floor, so a floor that filters rows leaves
            the header claiming findings the page never displays. Derive from
            the rendered surface instead, via the one module that defines these
            counts, and name each denominator: `The Teddy Bears' Picnic` used to
            report `2 advisories` on its queue row, `4 findings` here, and
            `5 flagged` in the overview footer, for one book.
          */}
          <span className="review-summary__count">{distinctFindingsLabel(counts)}</span>
          {tierBreakdown !== null ? (
            <span className="review-summary__scope cyo-text-muted">{tierBreakdown}</span>
          ) : null}
          {passageScope !== null ? (
            <span className="review-summary__scope cyo-text-muted">{passageScope}</span>
          ) : null}
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
              .filter((source): source is string => typeof source === 'string')
          )
        )
        return degradedSources.length > 0 ? (
          <p role="alert" className="review-detail__degraded">
            Automated screening was degraded for this version: {degradedSources.join(', ')} did not
            run. Review the prose extra carefully; the automated safety net was not fully applied.
          </p>
        ) : null
      })()}

      {/*
        A16 (capability-register.md), H2 human-approval half
        (security-hardening-plan-2026-07.md): a generated cover stops at
        cover_status "pending_review" and is withheld from CHILDREN until an
        admin approves it here. This admin surface is deliberately not
        withheld: api/covers.py::_cover_url presigns "pending_review" as well
        as "ready", because the reviewer has to see the image to judge it, and
        every endpoint reaching that helper is behind _require_admin. A
        pending_review cover with no URL yet (R2 unconfigured) renders the
        Approve action ALONE, with no image and no status line, rather than a
        broken <img>: the "Cover approved." line is the else arm of the
        pending_review branch and never renders while a cover is pending.

        Placed near the top of the page, below the moderation verdict strip and
        the degraded-screening alert, NOT at the foot of the page: a pending
        cover is an outstanding approval action, and below this point the page
        runs through every passage, finding list and the full story text, so a
        reviewer who does not scroll to the very bottom never learns the cover
        is waiting on them. It sits BELOW the classifier_degraded alert rather
        than above it because that alert says part of the automated safety net
        never ran, which outranks a cover decision; a reviewer must read it
        before anything else on the page. This is a second, separate approval
        from the story approve in the action bar (publishing the book does not
        approve its cover, and covers/service.py::approve_cover only checks
        cover_status, never the book's lifecycle status), so it must be
        discoverable on its own rather than inferred from the action bar.
        #VERIFY: ReviewDetailPage.test.tsx renders-pending-cover-with-approve,
        approves-a-pending-cover, surfaces-a-cover-approval-error,
        offers-the-approve-action-without-an-image, and
        renders-the-cover-approval-above-the-fold (which asserts this DOM
        order, including that the block follows the degraded-screening alert,
        so a refactor that pushes the block back down the page, or back above
        the safety alert, fails a test instead of shipping silently) tests.
      */}
      {coverStatus === 'pending_review' || coverStatus === 'ready' ? (
        <div className="review-cover-preview">
          <h2>Generated cover</h2>
          {coverUrl ? (
            <img
              src={coverUrl}
              alt={
                coverStatus === 'pending_review'
                  ? `Generated cover for ${title}, pending review`
                  : `Approved cover for ${title}`
              }
              className="review-cover-preview__image"
            />
          ) : null}
          {coverStatus === 'pending_review' ? (
            <div className="review-cover-preview__actions">
              <Button onClick={() => void approveCover()} disabled={coverBusy}>
                Approve cover
              </Button>
              {coverApproveError ? (
                <span className="review-cover-error" role="alert">
                  Could not approve the cover; try again.
                </span>
              ) : null}
            </div>
          ) : (
            <p className="review-cover-preview__status cyo-text-muted">Cover approved.</p>
          )}
        </div>
      ) : null}

      {surface.summary?.repaired ? (
        <p className="review-repaired-hint cyo-text-muted">
          This story was auto-repaired. Compare with the previous version to see what changed.
        </p>
      ) : null}

      {surface.generation_measures ? (
        <GenerationMeasuresBlock measures={surface.generation_measures} />
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
          {/*
            `RS-A3`: the distinct merged population, not `allFindings.length`.
            allFindings is the fan-out (flagged_passages x their findings, plus
            story-level), so this footer read `5 flagged` on a book whose
            header read `4 findings` and whose queue row read `2 advisories`.
            countBasis makes the denominator explicit in the badge rather than
            leaving the reader to guess which of the two numbers it is.
          */}
          <StoryStructureSummary
            blob={surface.blob}
            screened={surface.screened}
            flaggedCount={counts.distinct}
            findings={mergedFindings}
            countBasis="distinct"
          />
        </div>
      </details>

      {surface.report_unusable && (
        // Deliberately cause-neutral: moderation_report_unusable() (moderation/report.py)
        // already covers, and is expected to keep growing, multiple distinct causes (an
        // absent report, a malformed report or finding entry, a non-independent/mock
        // reviewer, artifact-only findings). Naming one cause here (the old copy claimed
        // "only pipeline fail-safe artifacts") misdiagnoses every other arm, so this tells
        // the reviewer what to do instead of guessing why.
        // #VERIFY: ReviewDetailPage.test.tsx "shows a cause-neutral unusable-report banner".
        <div role="alert" className="cyo-card review-unusable-banner">
          <strong>Moderation unavailable.</strong> This report cannot be relied on for a content
          judgment. Re-run moderation before reviewing (see the reviewer SOP); this version cannot
          be approved until a genuine report exists.
        </div>
      )}

      {/*
        Stage B3 (design doc 2.6): the merged findings ranked by
        (verdict, severity, affected-node-count, stable tiebreak), with
        structural findings split into their own block and low-ADVISORY
        findings collapsed behind a toggle. All four buckets default empty on
        an older backend response or a pre-Stage-B stored report, so this
        renders nothing extra in that case.
        The "Story-level notes" section (which rendered story_level_findings
        directly) was removed here as a pure duplicate: ranked_findings and
        structural_findings are built from the SAME FindingView objects that
        populate flagged_passages and story_level_findings, so every
        story-level finding already lands in one of the two sections here
        (structural if `structural` is true, otherwise ranked or
        low-advisory).

        `RS-A2`: this triage cluster now sits ABOVE "Flagged passages", which
        follows it. The overlap between the two is deliberate and is not the
        duplication described above: this list is triage-ordered for scanning
        verdict/severity across the whole story, while "Flagged passages"
        joins each finding to its node prose in read order. Ranking is what a
        reviewer needs first, so it goes first; the flat list is the
        second read, not the entry point.
      */}
      {/*
        `RS-A2`: rendered UNCONDITIONALLY, unlike the two blocks below it.
        Conditional rendering removed the most decision-useful section from
        the page exactly on the books a reviewer could clear fastest: on the
        four queued books whose findings are all low-severity advisories,
        ranked_findings is empty, so the section vanished and the reviewer was
        left with prose and no triage summary at all. An explicit "nothing
        ranked" statement is a finding about the book; an absent section is
        indistinguishable from a page that failed to load.
        #VERIFY: ReviewDetailPage.test.tsx "renders the ranked findings
        section above the flagged passages, even with nothing ranked".
      */}
      <div className="review-group" id="ranked-findings">
        <h2>Ranked findings</h2>
        {triageableFindings.length > 0 ? (
          <p className="review-triage__progress cyo-text-muted">
            {`${triagedCount} of ${pluralize(triageableFindings.length, 'finding')} marked reviewed in this browser.`}{' '}
            Triage is a bookmark for your own place in the list. It is stored only on this device
            and has no effect on approval.
          </p>
        ) : null}
        {rankedFindings.length > 0 ? (
          <ul className="review-findings review-findings--ranked">
            {rankedFindings.map((finding) => (
              <RankedFinding
                key={`${finding.concern ?? finding.category}-${finding.severity ?? ''}-${finding.verdict}-${finding.message}`}
                finding={finding}
                onJump={jumpToPassage}
                knownIds={readThrough.knownIds}
                proseFor={proseForNode}
                triage={triageFor(finding)}
              />
            ))}
          </ul>
        ) : (
          <p className="console__muted cyo-text-muted">
            No findings are ranked for triage on this version.
            {lowAdvisoryFindings.length > 0
              ? ` ${lowAdvisoryFindings.length} low-priority ${lowAdvisoryFindings.length === 1 ? 'advisory is' : 'advisories are'} collapsed below.`
              : ''}
          </p>
        )}
      </div>

      {structuralFindings.length > 0 ? (
        <div className="review-group" id="structural-findings">
          <h2>Structural findings</h2>
          <ul className="review-findings review-findings--ranked">
            {structuralFindings.map((finding) => (
              <RankedFinding
                key={`${finding.concern ?? finding.category}-${finding.severity ?? ''}-${finding.verdict}-${finding.message}`}
                finding={finding}
                onJump={jumpToPassage}
                knownIds={readThrough.knownIds}
                proseFor={proseForNode}
                triage={triageFor(finding)}
              />
            ))}
          </ul>
        </div>
      ) : null}

      {lowAdvisoryFindings.length > 0 ? (
        <details className="review-group" id="low-advisory-findings">
          <summary>Low-priority advisories ({lowAdvisoryFindings.length})</summary>
          <ul className="review-findings review-findings--ranked">
            {lowAdvisoryFindings.map((finding) => (
              <RankedFinding
                key={`${finding.concern ?? finding.category}-${finding.severity ?? ''}-${finding.verdict}-${finding.message}`}
                finding={finding}
                onJump={jumpToPassage}
                knownIds={readThrough.knownIds}
                proseFor={proseForNode}
                triage={triageFor(finding)}
              />
            ))}
          </ul>
        </details>
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

      {validatorFindings.length > 0 ? (
        <div className="review-group" id="validator-findings">
          <h2>Validator findings</h2>
          <p className="cyo-text-muted">
            Read-only projections from the deterministic validation gate (reading level and
            words-per-node); these never gate approval.
          </p>
          <ul className="review-findings">
            {validatorFindings.map((finding) => (
              <li
                key={`${finding.rule_id}-${finding.severity}-${finding.node_id ?? ''}-${finding.message}`}
                className="review-finding"
              >
                <span className="review-finding__category">{finding.rule_id}</span>
                <span
                  className={`review-finding__severity review-finding__severity--${finding.severity}`}
                >
                  {finding.severity}
                </span>
                <span className="review-finding__message">{finding.message}</span>
                {finding.node_id !== null && readThrough.knownIds.has(finding.node_id) ? (
                  <button
                    type="button"
                    className="review-jump"
                    onClick={() => jumpToPassage(finding.node_id as string)}
                  >
                    Show in story
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/*
        `RS-A4`: rendered only when the draw is genuinely a SAMPLE. A spot check
        exists because reading 250 screens is infeasible; on a book with 15 or
        fewer passages the full read-through below already is the sample, and
        repeating every passage twice on one page adds noise to the surface
        this whole plan exists to de-noise.
      */}
      {sample.nodes.length > 0 && sample.totalPassages > sample.nodes.length ? (
        <div className="review-group" id="review-sample">
          <h2>Spot check for missed content</h2>
          {/*
            `RS-A4`: the findings sections above serve the false-POSITIVE half
            of the reviewer's job. This serves the other half. Owner ruling
            2026-08-31: "I dont expect that a reviewer can read the entire
            book. They are trying to catch false positives and false
            negatives." The only affordance for the second half used to be the
            full read-through below, which is 250-plus screens on a large book.
          */}
          <p className="review-sample__caveat" role="note">
            {`${pluralize(sample.nodes.length, 'passage')} drawn across the story's ${pluralize(sample.totalPassages, 'passage')}, weighted toward passages the gate raised nothing about.`}{' '}
            {/*
              #CRITICAL: security: the caveat is not decoration. Ruling 2
              (2026-08-31) settled that the sample size ships labelled
              provisional until `RS-CAL3` measures a false-negative rate,
              because "15 of 550 passages checked" with no qualifier
              manufactures confidence in exactly the channel this section
              exists to make trustworthy. A reviewer must never read a clean
              sample as evidence the book is clean.
              #VERIFY: ReviewDetailPage.test.tsx "labels the spot check sample
              as uncalibrated, beside the count".
            */}
            <strong className="review-sample__uncalibrated">{SAMPLE_NOT_CALIBRATED}</strong>: a
            clean sample is not evidence the book is clean.
          </p>
          {bandContext.ageBand !== null || bandContext.readingLevel !== null ? (
            <p className="review-sample__band cyo-text-muted">
              Judge these passages against{' '}
              {bandContext.ageBand !== null ? ageBandLabel(bandContext.ageBand) : 'the target band'}
              {bandContext.readingLevel !== null
                ? `, reading level ${bandContext.readingLevel}`
                : ''}
              .
            </p>
          ) : null}
          <ol className="review-sample__list">
            {sample.nodes.map((node) => (
              <li key={node.id} className="review-sample__item">
                <div className="review-sample__head">
                  <span className="review-sample__node">{node.id}</span>
                  <span className="review-sample__position cyo-text-muted">
                    {`passage ${node.position} of ${sample.totalPassages}`}
                  </span>
                  {node.hasFinding ? <FlagBadge tone="flag" label="already flagged above" /> : null}
                  <button
                    type="button"
                    className="review-jump"
                    onClick={() => jumpToPassage(node.id)}
                  >
                    Show in story
                  </button>
                </div>
                <PassageText text={node.body} />
              </li>
            ))}
          </ol>
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
          disabled={surface.status !== 'in_review' || surface.report_unusable}
          aria-describedby={
            [
              surface.status !== 'in_review' ? 'review-actions-disabled-hint' : null,
              surface.report_unusable ? 'review-approve-unusable-hint' : null,
            ]
              .filter((id): id is string => id !== null)
              .join(' ') || undefined
          }
        >
          Approve
        </Button>
        {/*
          Archive is the inverse gate of Approve/Send Back: it un-publishes a
          published book, and the backend state machine permits archive only
          from "published" (any other status 409s). So on an in-review story
          this is disabled while the other two are live, and on a published
          story (reached via the admin library, P19) it is the sole live
          action.
        */}
        <Button
          variant="danger"
          onClick={() => openDialog('archive')}
          disabled={surface.status !== 'published'}
          aria-describedby={
            surface.status !== 'published' ? 'review-archive-disabled-hint' : undefined
          }
        >
          Archive
        </Button>
        {/*
          Re-screen (register A4) shares Archive's published-only gate: the
          backend sweep only ever acts on already-published storybooks
          (moderation/rescreen.py), silently skipping any other status.
        */}
        <Button
          variant="ghost"
          onClick={() => openDialog('rescreen')}
          disabled={surface.status !== 'published'}
          aria-describedby={
            surface.status !== 'published' ? 'review-rescreen-disabled-hint' : undefined
          }
        >
          Re-screen
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
      {surface.status !== 'published' ? (
        <p id="review-archive-disabled-hint" className="review-actionbar__hint cyo-text-muted">
          Only published stories can be archived.
        </p>
      ) : null}
      {surface.status !== 'published' ? (
        <p id="review-rescreen-disabled-hint" className="review-actionbar__hint cyo-text-muted">
          Only published stories can be re-screened.
        </p>
      ) : null}
      {/*
        #CRITICAL: security: an unusable report carries no genuine content
        judgment (fail-safe or mock-reviewer artifacts only), so there is
        nothing an override reason could justify approving over. The backend
        rejects approval unconditionally in this state
        (rule="approve_with_unusable_moderation", publishing/service.py); this
        disables Approve to match rather than letting the confirm dialog open
        with no override field and round-trip to a guaranteed 400.
        Deliberately does NOT name "Re-screen" as the remedy: that action
        (api/rescreen.py) only ever runs against already-published stories
        and, by design, never writes to moderation_report, so it would not
        fix this even where it is enabled. The actual re-run-moderation path
        for an in-review story is the admin-only remoderate endpoint
        (POST /api/v1/admin/remoderate/{storybook_id}/{version},
        api/remoderate.py), which has no UI on this page yet (flagged
        follow-up, not built here). Re-screen itself stays visible and
        untouched below; this hint is purely informational and does not
        reference it.
        #VERIFY: ReviewDetailPage.test.tsx "disables Approve and directs the
        reviewer to re-run moderation when the report is unusable" test.
      */}
      {surface.report_unusable ? (
        <p id="review-approve-unusable-hint" className="review-actionbar__hint cyo-text-muted">
          Approval is blocked until moderation is re-run for this story. Ask an operator to re-run
          moderation (admin remoderate).
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
                The `surface.report_unusable` clause is defense in depth: the
                Approve button that opens this dialog is already disabled in
                that state, so this branch should be unreachable in practice,
                but the backend rejects unconditionally
                (rule="approve_with_unusable_moderation") and this keeps the
                confirm button from ever being the one live control in that
                state.
              */}
              <Button
                disabled={
                  submitting ||
                  surface.report_unusable ||
                  (needsOverride && overrideReason.trim().length < 10)
                }
                // Mirrors the outer Approve button's pattern above: point at
                // the helper text explaining WHY this control is disabled,
                // rather than overwriting the button's own accessible name.
                // Only wired for the override-reason-length reason (the other
                // two disabling conditions, submitting and report_unusable,
                // have no dedicated helper text inside this dialog to point
                // at); needsOverride being true is exactly the condition
                // under which the referenced hint span below is rendered.
                // #VERIFY: ReviewDetailPage.test.tsx "describes why Confirm
                // approve is disabled for a too-short override reason".
                aria-describedby={
                  needsOverride && overrideReason.trim().length < 10
                    ? 'review-detail-override-hint'
                    : undefined
                }
                onClick={() =>
                  void runAction(() =>
                    reviewApi.approve(
                      storybookId,
                      visibility,
                      needsOverride ? overrideReason.trim() : undefined
                    )
                  )
                }
              >
                Confirm approve
              </Button>
            </>
          }
        >
          {actionError ? (
            <p role="alert" className="review-detail__action-error cyo-text-error">
              {actionErrorRule === 'approve_requires_override_reason'
                ? 'This story has a severe finding that still needs a written override reason. Add or revise the reason below and try again.'
                : actionErrorRule === 'approve_with_unusable_moderation'
                  ? 'Moderation for this story is unavailable, so it cannot be approved. Ask an operator to re-run moderation, then reload this page.'
                  : 'We could not approve this story. It may be unscreened or no longer in review.'}
            </p>
          ) : null}
          <p>Approving publishes this story to the assigned children.</p>
          {needsOverride ? (
            <label className="review-detail__override-reason">
              Override reason
              {/*
                No `aria-label` here: the wrapping <label> already associates
                this textarea with its "Override reason" text, and an
                aria-label would win over that association, so if the two
                text sources ever diverged a screen-reader user would hear a
                different name than a sighted user sees (WCAG 2.5.3 Label in
                Name). `required`/`minLength` are deliberately absent too:
                this control is not inside a <form> with a submit button, so
                native constraint validation never runs against them; the
                real gate is the Confirm button's manually computed
                `disabled` above.
              */}
              <textarea
                value={overrideReason}
                onChange={(event) => setOverrideReason(event.target.value)}
                maxLength={2000}
                rows={3}
              />
              <span id="review-detail-override-hint" className="cyo-text-muted">
                This story has a severe finding. Explain why it is appropriate to approve anyway;
                the reason is logged for audit, not stored on the story itself.
              </span>
            </label>
          ) : null}
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
                onClick={() =>
                  void runAction(() => reviewApi.sendBack(storybookId, reason.trim(), reasonCode))
                }
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
          <label className="review-detail__reason-code">
            Reason category (for calibration)
            <select
              value={reasonCode}
              onChange={(event) => setReasonCode(event.target.value as SendBackReasonCode)}
            >
              {SEND_BACK_REASON_CODES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
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

      {dialog === 'archive' ? (
        <Dialog
          title="Archive this story?"
          onClose={closeDialog}
          actions={
            <>
              <Button variant="ghost" onClick={closeDialog}>
                Cancel
              </Button>
              {/*
                #CRITICAL: security: confirming archive un-publishes this story
                and removes it from the library for every assigned child; a
                misclick must not silently pull a live book.
                #VERIFY: this confirm dialog gates the action and the backend
                state machine rejects archive from any status other than
                published (ReviewDetailPage.test.tsx archive success + gating).
              */}
              <Button
                variant="danger"
                disabled={submitting}
                onClick={() => void runAction(() => reviewApi.archive(storybookId))}
              >
                Confirm archive
              </Button>
            </>
          }
        >
          {actionError ? (
            <p role="alert" className="review-detail__action-error cyo-text-error">
              We could not archive this story. It may no longer be published.
            </p>
          ) : null}
          <p>
            Archiving removes this story from the library. Assigned children will no longer see it.
          </p>
        </Dialog>
      ) : null}

      {dialog === 'rescreen' ? (
        <Dialog
          title="Re-screen this story?"
          onClose={closeDialog}
          actions={
            rescreenState.kind === 'success' ? (
              <Button onClick={closeDialog}>Close</Button>
            ) : (
              <>
                <Button
                  variant="ghost"
                  onClick={closeDialog}
                  disabled={rescreenState.kind === 'submitting'}
                >
                  Cancel
                </Button>
                {/*
                  #CRITICAL: security: confirming re-screen re-runs the
                  safety/policy gate over already-published content; a
                  misclick must not silently skip this behind an unconfirmed
                  click. Unlike Approve/Send Back/Archive, this action never
                  changes the story's status (ADR-005: a flagged result is
                  never auto-archived), so the confirm gate protects against
                  redundant re-screens, not an unsafe state transition.
                  #VERIFY: ReviewDetailPage.test.tsx "re-screen" cases.
                */}
                <Button
                  disabled={rescreenState.kind === 'submitting'}
                  onClick={() => void runRescreen()}
                >
                  {rescreenState.kind === 'submitting' ? 'Re-screening…' : 'Confirm re-screen'}
                </Button>
              </>
            )
          }
        >
          {rescreenState.kind === 'idle' || rescreenState.kind === 'submitting' ? (
            <p>
              Re-screening re-runs the current safety policy and thresholds against this story. A
              flagged result is never auto-archived; you review the result and archive by hand if
              warranted.
            </p>
          ) : null}
          {rescreenState.kind === 'error' ? (
            <p role="alert" className="review-detail__action-error cyo-text-error">
              We could not re-screen this story. Please try again.
            </p>
          ) : null}
          {rescreenState.kind === 'success' ? (
            rescreenState.verdict ? (
              <div role="status" className="review-rescreen-result">
                <p>
                  Outcome: <strong>{rescreenState.verdict.outcome}</strong>
                </p>
                {rescreenState.verdict.reasons.length > 0 ? (
                  <ul>
                    {rescreenState.verdict.reasons.map((reason, index) => (
                      // Reasons are static per render; index key is stable here.
                      <li key={index}>{reason}</li>
                    ))}
                  </ul>
                ) : null}
                {rescreenState.verdict.error ? (
                  <p role="alert" className="cyo-text-error">
                    {rescreenState.verdict.error}
                  </p>
                ) : null}
              </div>
            ) : (
              // #ASSUME: data integrity: the backend silently skips an id that
              // is not currently published (see runRescreen's #ASSUME above);
              // this is the UI's explicit rendering of that empty-results case.
              <p role="status">
                This story was not included in the sweep. It may no longer be published.
              </p>
            )
          ) : null}
        </Dialog>
      ) : null}

      {editNodeId !== null ? (
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
              #VERIFY: ReviewDetailPage.test.tsx passage-edit success + 422 cases.
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
          {/*
            `RS-A6`: the reviewer is being asked to rewrite prose, so the
            dialog states what is wrong with it and what band the rewrite has
            to hold. Before this, the dialog was a bare textarea: a reviewer
            who reached it from the ranked list had to remember the finding,
            and one who reached it from the spot check had never seen one.
            #VERIFY: ReviewDetailPage.test.tsx "shows the findings that name
            the passage being edited" and "says so when no finding names the
            passage being edited".
          */}
          <div className="review-edit__context">
            <h3 className="review-edit__context-heading">What the gate said about this passage</h3>
            {editFindings.length > 0 ? (
              <ul className="review-findings review-edit__findings">
                {editFindings.map((finding) => (
                  <li key={findingKey(finding)} className="review-finding">
                    <FlagBadge tone={verdictTone(finding.verdict)} />
                    {finding.severity ? (
                      <span
                        className={`review-finding__severity review-finding__severity--${finding.severity}`}
                      >
                        {finding.severity}
                      </span>
                    ) : null}
                    <span className="review-finding__category">
                      {finding.concern ?? finding.category}
                    </span>
                    {typeof finding.score === 'number' ? (
                      <span className="review-finding__score">{finding.score.toFixed(2)}</span>
                    ) : null}
                    <span className="review-finding__message">{finding.message}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="cyo-text-muted">
                No finding names this passage. You are editing it on your own reading, not to clear
                a recorded concern.
              </p>
            )}
            {bandContext.ageBand !== null || bandContext.readingLevel !== null ? (
              <p className="review-edit__band cyo-text-muted">
                Write for{' '}
                {bandContext.ageBand !== null
                  ? ageBandLabel(bandContext.ageBand)
                  : 'the target band'}
                {bandContext.readingLevel !== null
                  ? `, reading level ${bandContext.readingLevel}`
                  : ''}
                . Saving re-runs the deterministic gate, which rejects an edit that leaves the
                band's reading-level or length envelope.
              </p>
            ) : null}
          </div>
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
