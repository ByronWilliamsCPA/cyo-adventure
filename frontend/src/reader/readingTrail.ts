/**
 * Reading-trail recorder (privacy-model.md "Reading trail").
 *
 * Turns the reader machine's transitions (player/transitions.ts) into the
 * closed step vocabulary the server stores (src/cyo_adventure/reading_trail/
 * steps.py) and hands batches to a send function that is fire-and-forget.
 * One instance records one reader mount; each read inside it (the opening
 * read, then one per Start over) gets its own client-minted read id, and
 * every step its own increasing `seq`, which is what makes a replay of any
 * batch a no-op server-side.
 *
 * What is recorded, and why:
 * - `start` / `resume` open a read. A read opened from saved progress is a
 *   `resume` (a new session of an existing read), not a new read.
 * - `choice` is a real decision: the node declares two or more choices. The
 *   choice id comes from the machine's own CHOOSE event, so two choices that
 *   lead to the same node are told apart (a ReadingState path cannot).
 * - `auto` is a move through a node that declares exactly one choice. Under
 *   ADR-026 flowed rendering (bands 8-11 and up) the reader walks these nodes
 *   itself via the same CHOOSE event; at page bands the child taps the only
 *   option. Neither is a decision, so they are MARKED rather than dropped:
 *   dropping them would break path reconstruction and fold the time spent
 *   reading a flowed passage into the next real choice, while marking keeps
 *   both intact and lets pick-rate reporting ignore them.
 * - `back` is one Go back transition. A "Try a different choice" rewind that
 *   sends several BACKs in a row records several `back` steps; the report
 *   counts the run once, at the node it lands on.
 * - `end` follows the step that reached an ending node.
 * - `restart` closes the current read where the child was; the new read
 *   opens with `start`.
 * - `jump` is any other position change (a bookmark load, or adopting
 *   another device's newer position after a sync conflict).
 * - `leave` is the abandon marker: the child left the book.
 *
 * Timing is `elapsed_s`, whole seconds since the read opened on this device's
 * clock. There is no wall-clock time anywhere in a step: the server stamps
 * only the calendar date a read first arrives.
 */

import type { ReadingTrailBatchBody, ReadingTrailStepBody, StepKind } from '../client/types.gen'
import type { TrailSendOutcome } from '../offline/readingTrailSync'
import type { ReaderTransition } from '../player/transitions'
import type { ReadingState, StoryNode, Storybook } from '../player/types'

/** Mirrors the server's MAX_ELAPSED_SECONDS (one week). */
export const MAX_ELAPSED_SECONDS = 7 * 24 * 60 * 60
/** Mirrors READING_TRAIL_MAX_STEPS; a read stops recording at this many steps. */
export const MAX_STEPS_PER_READ = 2000
/** Flush once this many steps are buffered (well under the server's 200). */
export const FLUSH_AT_STEPS = 20

export type SendTrail = (
  body: ReadingTrailBatchBody,
  options: { keepalive: boolean }
) => Promise<TrailSendOutcome>

export interface ReadingTrailRecorderOptions {
  story: Storybook
  /** The state the reader opened with: undefined for a fresh read. */
  baseline: ReadingState | undefined
  version: number
  send: SendTrail
  /** Milliseconds clock; defaults to Date.now. Only differences are used. */
  now?: () => number
  newId?: () => string
}

export class ReadingTrailRecorder {
  private readonly story: Storybook
  private readonly version: number
  private readonly send: SendTrail
  private readonly now: () => number
  private readonly newId: () => string
  private readonly nodes: Map<string, StoryNode>
  private readId = ''
  private seq = 0
  private openedAt = 0
  private position: string | null = null
  private buffer: ReadingTrailStepBody[] = []
  private disabled = false
  private closed = false

  constructor(options: ReadingTrailRecorderOptions) {
    this.story = options.story
    this.version = options.version
    this.send = options.send
    this.now = options.now ?? Date.now
    this.newId = options.newId ?? (() => crypto.randomUUID())
    this.nodes = new Map(options.story.nodes.map((node) => [node.id, node]))
    const { baseline } = options
    // #EDGE: data-integrity: a saved read still on its opening node (path of
    // length 1) is recorded as a fresh `start`, because nothing distinguishes
    // it from one; reopening an untouched book therefore counts as a new
    // read. Harmless for the owner's questions (no choice was ever made).
    // #VERIFY: readingTrail.test.ts "records a saved read past its first node
    // as a resume".
    if (baseline === undefined || baseline.path.length <= 1) {
      this.openRead('start', baseline?.current_node ?? this.story.start_node)
    } else {
      this.openRead('resume', baseline.current_node)
    }
  }

  /** The machine applied a transition for this story. */
  onTransition(transition: ReaderTransition): void {
    if (this.closed || this.disabled) return
    switch (transition.type) {
      case 'choose':
        this.recordMove(transition.from, transition.choiceId, transition.to.current_node)
        break
      case 'back':
        this.push('back', transition.to.current_node)
        this.position = transition.to.current_node
        break
      case 'restart':
        this.push('restart', this.position ?? transition.to.current_node)
        this.flush()
        this.openRead('start', transition.to.current_node)
        break
      case 'jump':
        this.push('jump', transition.to.current_node)
        this.position = transition.to.current_node
        break
    }
  }

  /**
   * A reading state the page saw. Transitions normally explain it already;
   * one that does not (the Reader remounted on an adopted server row after a
   * sync conflict, which emits no transition) is recorded as a `jump`.
   */
  observe(state: ReadingState): void {
    if (this.closed || this.disabled) return
    if (state.current_node !== this.position && this.nodes.has(state.current_node)) {
      this.push('jump', state.current_node)
      this.position = state.current_node
    }
  }

  /** The child left the book: record the abandon marker and flush. Idempotent. */
  leave(): void {
    if (this.closed) return
    if (!this.disabled && this.position !== null) {
      this.push('leave', this.position)
    }
    this.flush({ keepalive: true })
    this.closed = true
  }

  /** Send whatever is buffered for the current read. Fire-and-forget. */
  flush(options: { keepalive?: boolean } = {}): void {
    if (this.disabled || this.buffer.length === 0) {
      this.buffer = []
      return
    }
    const body: ReadingTrailBatchBody = {
      read_id: this.readId,
      version: this.version,
      steps: this.buffer,
    }
    this.buffer = []
    void this.send(body, { keepalive: options.keepalive === true })
      .then((outcome) => {
        // The environment records nothing: stop for the rest of this mount
        // rather than keep sending batches the server will discard.
        if (outcome === 'disabled') this.disable()
      })
      .catch(() => {
        // A send function that rejects despite its contract; nothing to do.
      })
  }

  private disable(): void {
    this.disabled = true
    this.buffer = []
  }

  private openRead(kind: 'start' | 'resume', node: string): void {
    this.readId = this.newId()
    this.seq = 0
    this.openedAt = this.now()
    this.position = node
    this.push(kind, node)
  }

  private recordMove(from: string, choiceId: string, to: string): void {
    const declared = this.nodes.get(from)?.choices ?? []
    // Single-choice node: a flowed walk or a tap on the only option (see the
    // module docstring for why it is marked rather than dropped).
    this.push(declared.length === 1 ? 'auto' : 'choice', from, choiceId)
    this.position = to
    if (this.nodes.get(to)?.is_ending === true) {
      this.push('end', to)
      this.flush()
    }
  }

  private push(kind: StepKind, node: string, choiceId?: string): void {
    if (this.seq >= MAX_STEPS_PER_READ) return
    const elapsed = Math.floor((this.now() - this.openedAt) / 1000)
    this.buffer.push({
      seq: this.seq,
      kind,
      node_id: node,
      choice_id: choiceId ?? null,
      elapsed_s: Math.min(Math.max(elapsed, 0), MAX_ELAPSED_SECONDS),
    })
    this.seq += 1
    if (this.buffer.length >= FLUSH_AT_STEPS) this.flush()
  }
}
