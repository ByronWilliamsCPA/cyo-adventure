import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeCoverApi, type CoverStatusView } from '../guardian/coverApi'
import { FlagBadge, verdictTone } from '../guardian/FlagBadge'
import {
  makeReviewApi,
  type FindingView,
  type ReviewSurface,
  type Visibility,
} from '../guardian/reviewApi'

interface ChoiceView {
  label: string
  target: string
}

interface EndingView {
  kind: string | null
  valence: string | null
}

interface StoryNodeView {
  /** Position in the blob's nodes array: a unique React key even when ids collide. */
  blobIndex: number
  id: string
  body: string
  choices: ChoiceView[]
  isEnding: boolean
  ending: EndingView | null
}

/**
 * Read a node's choices from the loosely typed blob. Non-object entries are
 * skipped; a kept entry keeps whatever label/target strings it has (either may
 * be '', rendered as "(missing label)" / a "missing target" note).
 */
function readChoices(raw: unknown): ChoiceView[] {
  if (!Array.isArray(raw)) return []
  const choices: ChoiceView[] = []
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const record = entry as Record<string, unknown>
    const label = typeof record.label === 'string' ? record.label : ''
    const target = typeof record.target === 'string' ? record.target : ''
    if (!label && !target) continue
    choices.push({ label, target })
  }
  return choices
}

/** Read the ending descriptor; kind/valence survive only when they are strings. */
function readEnding(raw: unknown): EndingView | null {
  if (typeof raw !== 'object' || raw === null) return null
  const record = raw as Record<string, unknown>
  return {
    kind: typeof record.kind === 'string' ? record.kind : null,
    valence: typeof record.valence === 'string' ? record.valence : null,
  }
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
 * Choices and ending metadata are read defensively too: a node missing or
 * mangling those fields still renders with whatever it has.
 */
function readNodes(blob: Record<string, unknown>): StoryNodeView[] {
  const raw = blob.nodes
  if (!Array.isArray(raw)) return []
  const nodes: StoryNodeView[] = []
  raw.forEach((entry, index) => {
    if (typeof entry !== 'object' || entry === null) return
    const record = entry as Record<string, unknown>
    const id = typeof record.id === 'string' ? record.id : ''
    const body = typeof record.body === 'string' ? record.body : ''
    if (!id && !body) return
    const ending = readEnding(record.ending)
    nodes.push({
      blobIndex: index,
      id: id || `node-${index}`,
      body,
      choices: readChoices(record.choices),
      isEnding: record.is_ending === true || ending !== null,
      ending,
    })
  })
  return nodes
}

interface ReadThrough {
  /** Passages in read order: depth-first from the start node, choice order first. */
  reachable: StoryNodeView[]
  /** Kept passages no choice path from the start reaches (rendered last, labeled). */
  unreachable: StoryNodeView[]
  /** Node ids present in the read-through, for jump-target existence checks. */
  knownIds: Set<string>
  endingCount: number
}

/**
 * Order the read-through by playing the story: depth-first from the blob's
 * start_node, following each node's choices in order and skipping nodes
 * already visited.
 *
 * #CRITICAL: data integrity: every kept node must appear exactly once in
 * reachable + unreachable; a passage dropped from the read-through could let
 * unreviewed prose reach a child.
 * #VERIFY: ReviewDetailPage.test.tsx traversal, unreachable-section, and
 * malformed-node tests assert the two lists cover all kept nodes.
 */
function buildReadThrough(blob: Record<string, unknown>): ReadThrough {
  const nodes = readNodes(blob)
  // First node with each id wins the traversal slot; a duplicate-id node can
  // never be visited, so it lands in the unreachable section instead of
  // silently vanishing.
  const byId = new Map<string, StoryNodeView>()
  for (const node of nodes) {
    if (!byId.has(node.id)) byId.set(node.id, node)
  }
  const declaredStart = typeof blob.start_node === 'string' ? blob.start_node : ''
  // #EDGE: data integrity: a missing or dangling start_node (a blob the
  // validator would reject) still needs an ordered read-through, so fall back
  // to the first kept node; everything then renders reachable-or-unreachable.
  // #VERIFY: malformed-node test renders a start_node-less blob end to end.
  const start = byId.get(declaredStart) ?? nodes[0] ?? null
  const visited = new Set<StoryNodeView>()
  const reachable: StoryNodeView[] = []
  if (start) {
    const stack: StoryNodeView[] = [start]
    while (stack.length > 0) {
      const node = stack.pop()
      if (!node || visited.has(node)) continue
      visited.add(node)
      reachable.push(node)
      // Push in reverse so the pop order follows the node's choice order.
      for (const choice of [...node.choices].reverse()) {
        const target = byId.get(choice.target)
        if (target && !visited.has(target)) stack.push(target)
      }
    }
  }
  return {
    reachable,
    unreachable: nodes.filter((node) => !visited.has(node)),
    knownIds: new Set(byId.keys()),
    endingCount: nodes.filter((node) => node.isEnding).length,
  }
}

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

function pluralize(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
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
}

/**
 * One passage of the read-through: structure badges (Start / Ending with
 * kind and valence), the prose, then the kid-facing choice labels with a jump
 * button per resolvable target. tabIndex={-1} lets a jump move real focus
 * here; badges carry text, never color alone.
 */
function Passage({ node, isStart, flagged, highlighted, knownIds, onJump }: PassageProps) {
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
      void navigate('/admin')
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
    </section>
  )
}
