import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { isAxiosError } from 'axios'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { PassageText } from '@ds/components/PassageText'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import {
  asGateFailure,
  makePassageEditApi,
  type GateFindingView,
} from './passageEditApi'
import { makeCoverApi, type CoverStatusView } from '../guardian/coverApi'
import { FlagBadge, verdictTone } from '../guardian/FlagBadge'
import {
  makeReviewApi,
  type FindingView,
  type ReviewSurface,
  type Visibility,
} from '../guardian/reviewApi'
import { StoryStructureSummary } from '../guardian/StoryStructureSummary'

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

interface EditableChoice {
  id: string
  label: string
  target: string
}

interface EditableNode {
  body: string
  choices: EditableChoice[]
}

/**
 * Read one node's editable fields (body plus each choice's id/label/target)
 * straight from the raw blob, bypassing `readNodes`/`ChoiceView` (which never
 * carry a choice's `id` -- the read-through and diff views key choices by
 * `target` instead, deliberately, see `diffChoices`). The G6 edit dialog
 * needs the real choice id to build a `choice_labels: {choice_id: label}`
 * PATCH body, so this reads it directly rather than widening the
 * read-through's own types for a value only the edit dialog uses.
 *
 * Returns `null` when the node id is not found or the node has no usable
 * prose id -- the Edit button that opens this dialog only ever passes an id
 * already rendered from `readNodes`, so this is a defensive fallback, not an
 * expected path.
 */
function findEditableNode(blob: Record<string, unknown>, nodeId: string): EditableNode | null {
  const raw = blob.nodes
  if (!Array.isArray(raw)) return null
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const record = entry as Record<string, unknown>
    if (record.id !== nodeId) continue
    const body = typeof record.body === 'string' ? record.body : ''
    const choices: EditableChoice[] = []
    if (Array.isArray(record.choices)) {
      for (const choiceEntry of record.choices) {
        if (typeof choiceEntry !== 'object' || choiceEntry === null) continue
        const choiceRecord = choiceEntry as Record<string, unknown>
        const id = typeof choiceRecord.id === 'string' ? choiceRecord.id : ''
        if (!id) continue
        choices.push({
          id,
          label: typeof choiceRecord.label === 'string' ? choiceRecord.label : '',
          target: typeof choiceRecord.target === 'string' ? choiceRecord.target : '',
        })
      }
    }
    return { body, choices }
  }
  return null
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

interface ChangedNodeDiff {
  id: string
  previous: StoryNodeView
  current: StoryNodeView
  bodyChanged: boolean
  choicesChanged: boolean
}

interface VersionDiff {
  added: StoryNodeView[]
  removed: StoryNodeView[]
  changed: ChangedNodeDiff[]
}

/**
 * Passage-level diff between two review surfaces' blobs, reusing readNodes so
 * a malformed node is handled identically to the main read-through (a
 * synthetic id rather than a silent drop). Nodes are keyed by id, first
 * occurrence wins (matching buildReadThrough's duplicate-id rule): a node id
 * only on one side is added/removed, and a node id on both sides is
 * `changed` when its body text differs OR its choices array differs (by
 * JSON.stringify; ChoiceView's shape is stable, so this also catches a
 * reworded label, an added/removed choice, or a retargeted/reordered one).
 *
 * #ASSUME: data integrity: this is a reviewer-facing summary, not the
 * safety-critical read-through above; it does not attempt to distinguish a
 * reordered node list from an untouched one, and a duplicate id still
 * collapses to its first occurrence on each side.
 * #VERIFY: ReviewDetailPage.test.tsx compare-diff tests assert added/removed/
 * changed counts and that an untouched node produces no changed entry.
 */
function diffNodes(previousBlob: Record<string, unknown>, currentBlob: Record<string, unknown>): VersionDiff {
  const byId = (blob: Record<string, unknown>): Map<string, StoryNodeView> => {
    const map = new Map<string, StoryNodeView>()
    for (const node of readNodes(blob)) {
      if (!map.has(node.id)) map.set(node.id, node)
    }
    return map
  }
  const previousById = byId(previousBlob)
  const currentById = byId(currentBlob)
  const added: StoryNodeView[] = []
  const changed: ChangedNodeDiff[] = []
  for (const [id, node] of currentById) {
    const prior = previousById.get(id)
    if (!prior) {
      added.push(node)
      continue
    }
    const bodyChanged = prior.body !== node.body
    // Order-insensitive, matching diffChoices below (which the detail panel
    // renders from): choices are matched by target, not position, so a
    // reorder with no other change must not flag this passage as changed,
    // and any real add/remove/reword must always be counted as one.
    const choiceDiff = diffChoices(prior.choices, node.choices)
    const choicesChanged =
      choiceDiff.added.length > 0 || choiceDiff.removed.length > 0 || choiceDiff.reworded.length > 0
    if (bodyChanged || choicesChanged) {
      changed.push({ id, previous: prior, current: node, bodyChanged, choicesChanged })
    }
  }
  const removed: StoryNodeView[] = []
  for (const [id, node] of previousById) {
    if (!currentById.has(id)) removed.push(node)
  }
  return { added, removed, changed }
}

interface ChoiceDiff {
  added: ChoiceView[]
  removed: ChoiceView[]
  reworded: { target: string; from: string; to: string }[]
}

/**
 * Choice-level detail for one changed passage. Choices carry no id, so a
 * choice is matched across versions by its target node id, not position.
 *
 * #EDGE: data integrity: two choices sharing the same target (a duplicate
 * link) collapse to one entry here. This is display-only detail under an
 * already-changed passage, not the safety-critical read-through, so the
 * simplification is acceptable; a full positional diff would be scope creep
 * for a "what changed" hint.
 */
function diffChoices(previous: ChoiceView[], current: ChoiceView[]): ChoiceDiff {
  const previousByTarget = new Map(previous.map((choice) => [choice.target, choice]))
  const currentByTarget = new Map(current.map((choice) => [choice.target, choice]))
  const added: ChoiceView[] = []
  const reworded: { target: string; from: string; to: string }[] = []
  for (const [target, choice] of currentByTarget) {
    const prior = previousByTarget.get(target)
    if (!prior) {
      added.push(choice)
    } else if (prior.label !== choice.label) {
      reworded.push({ target, from: prior.label, to: choice.label })
    }
  }
  const removed: ChoiceView[] = []
  for (const [target, choice] of previousByTarget) {
    if (!currentByTarget.has(target)) removed.push(choice)
  }
  return { added, removed, reworded }
}

/** One changed passage: old vs new body (when the body itself changed), plus
 * a choices note. Collapsed behind <details> since a version can change many
 * passages and the reviewer scans the summary line first. */
function ChangedNodeDetail({ entry }: { entry: ChangedNodeDiff }) {
  const choiceDiff = diffChoices(entry.previous.choices, entry.current.choices)
  const hasChoiceDetail =
    choiceDiff.added.length > 0 || choiceDiff.removed.length > 0 || choiceDiff.reworded.length > 0
  return (
    <details className="review-compare__node">
      <summary>Passage {entry.id} changed</summary>
      {entry.bodyChanged ? (
        <div className="review-compare__body">
          <div className="review-compare__before">
            <h4>Previous</h4>
            <PassageText text={entry.previous.body} />
          </div>
          <div className="review-compare__after">
            <h4>Current</h4>
            <PassageText text={entry.current.body} />
          </div>
        </div>
      ) : null}
      {entry.choicesChanged ? (
        <div className="review-compare__choices">
          <p>Choices changed{hasChoiceDetail ? ':' : '.'}</p>
          {hasChoiceDetail ? (
            <ul>
              {choiceDiff.reworded.map((change) => (
                <li key={`reworded-${change.target}`}>
                  &quot;{change.from}&quot; reworded to &quot;{change.to}&quot;
                </li>
              ))}
              {choiceDiff.added.map((choice) => (
                <li key={`added-${choice.target}`}>
                  Added choice &quot;{choice.label || '(missing label)'}&quot;
                </li>
              ))}
              {choiceDiff.removed.map((choice) => (
                <li key={`removed-${choice.target}`}>
                  Removed choice &quot;{choice.label || '(missing label)'}&quot;
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </details>
  )
}

/** Compact diff summary line first, then expandable per-node detail for
 * changed passages; added/removed passages get a one-line list entry since
 * there is no "old" or "new" body to show for either. */
function VersionDiffView({ diff }: { diff: VersionDiff }) {
  return (
    <div className="review-compare__diff">
      <p className="review-compare__summary">
        {pluralize(diff.added.length, 'passage')} added, {diff.changed.length} changed,{' '}
        {diff.removed.length} removed
      </p>
      {diff.added.length > 0 ? (
        <ul className="review-compare__list">
          {diff.added.map((node) => (
            <li key={node.id}>Added: passage {node.id}</li>
          ))}
        </ul>
      ) : null}
      {diff.removed.length > 0 ? (
        <ul className="review-compare__list">
          {diff.removed.map((node) => (
            <li key={node.id}>Removed: passage {node.id}</li>
          ))}
        </ul>
      ) : null}
      {diff.changed.map((entry) => (
        <ChangedNodeDetail key={entry.id} entry={entry} />
      ))}
    </div>
  )
}

type CompareState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'unavailable' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; previous: ReviewSurface }

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
  const [editNodeId, setEditNodeId] = useState<string | null>(null)
  const [editBody, setEditBody] = useState('')
  const [editChoices, setEditChoices] = useState<EditableChoice[]>([])
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editGateFindings, setEditGateFindings] = useState<GateFindingView[] | null>(null)
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

  const [compareOpen, setCompareOpen] = useState(false)
  const [compareState, setCompareState] = useState<CompareState>({ kind: 'idle' })

  // #ASSUME: external resources: the previous version may no longer exist
  // (pruned, or the current version is 1 with no version 0 at all); the
  // backend 404s the surface fetch in that case, which axios surfaces as a
  // normal error response, not a thrown/rejected navigation.
  // #ASSUME: timing dependencies: the reviewer can navigate away mid-fetch;
  // isMountedRef (already used by generateCover above) guards every setState
  // after the await so a late response never writes into an unmounted page.
  // #VERIFY: ReviewDetailPage.test.tsx compare tests cover the loading state,
  // the ready diff, and the 404-to-"no longer available" branch.
  const loadCompare = useCallback(
    async (previousVersion: number) => {
      setCompareState({ kind: 'loading' })
      try {
        const previous = await reviewApi.surface(storybookId, previousVersion)
        if (isMountedRef.current) setCompareState({ kind: 'ready', previous })
      } catch (err) {
        console.error('compare version load failed:', err instanceof Error ? err.message : err)
        if (!isMountedRef.current) return
        if (isAxiosError(err) && err.response?.status === 404) {
          setCompareState({ kind: 'unavailable' })
        } else {
          setCompareState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load the previous version for comparison.',
              server: 'We could not load the previous version for comparison.',
            }).message,
          })
        }
      }
    },
    [reviewApi, storybookId]
  )

  // Toggling closed just hides the panel. A successful ('ready') or
  // permanent (404 'unavailable') outcome stays cached so reopening does not
  // refetch; a transient 'error' is retried on reopen instead, so a network
  // blip does not permanently block comparison for the rest of the page's
  // lifetime the way caching it forever would.
  function toggleCompare(previousVersion: number) {
    if (compareOpen) {
      setCompareOpen(false)
      return
    }
    setCompareOpen(true)
    if (compareState.kind === 'idle' || compareState.kind === 'error') {
      void loadCompare(previousVersion)
    }
  }

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

  // G6: an edit is offered only while the backend would accept one
  // (in_review or needs_revision); mirrors the Approve/Send Back guard above.
  const editingDisabled = surface.status !== 'in_review' && surface.status !== 'needs_revision'
  const editBodyValid = editBody.trim().length >= 1

  function openEditDialog(nodeId: string) {
    const found = findEditableNode(surface.blob, nodeId)
    if (!found) return
    setEditNodeId(nodeId)
    setEditBody(found.body)
    setEditChoices(found.choices)
    setEditError(null)
    setEditGateFindings(null)
  }

  function closeEditDialog() {
    setEditNodeId(null)
    setEditError(null)
    setEditGateFindings(null)
    setEditSubmitting(false)
  }

  function setEditChoiceLabel(choiceId: string, label: string) {
    setEditChoices((current) => current.map((c) => (c.id === choiceId ? { ...c, label } : c)))
  }

  async function saveEdit() {
    if (editNodeId === null) return
    setEditSubmitting(true)
    setEditError(null)
    setEditGateFindings(null)
    try {
      const refreshed = await passageEditApi.editNode(storybookId, surface.version, editNodeId, {
        body: editBody,
        ...(editChoices.length > 0
          ? { choice_labels: Object.fromEntries(editChoices.map((c) => [c.id, c.label])) }
          : {}),
      })
      setState({ kind: 'ready', surface: refreshed })
      closeEditDialog()
    } catch (err) {
      // Log the message, not the axios error object (its config.headers
      // carries the caller's Authorization bearer token).
      console.error('passage edit failed:', err instanceof Error ? err.message : err)
      const gateFailure = asGateFailure(err)
      if (gateFailure) {
        setEditGateFindings(gateFailure.findings)
      } else {
        setEditError(
          classifyApiError(err, {
            transient: 'We could not save this edit. Please try again.',
            server: 'We could not save this edit. Please try again.',
          }).message
        )
      }
      setEditSubmitting(false)
    }
  }

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
            onClick={() => toggleCompare(surface.version - 1)}
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
              ) : compareState.kind === 'ready' ? (
                <VersionDiffView diff={diffNodes(compareState.previous.blob, surface.blob)} />
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
