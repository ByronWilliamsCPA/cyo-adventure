/**
 * Version-diff helpers for the admin review-detail surface, plus a
 * backward-compatible re-export of the shared read-through/edit-target
 * helpers. Split history (register G6, the edit half): the read-through and
 * `findEditableNode` used to live here but moved to
 * `guardian/storyReadThrough.ts` so the guardian review/edit page can use
 * them without importing from `admin/`; this file re-exports them unchanged
 * so no existing admin import (ReviewDetailPage.tsx, ReviewCompare.tsx,
 * useVersionCompare.ts, usePassageEdit.ts) needed to change. Only the
 * version-diff functions below (used solely by the admin-only
 * version-compare feature) are still defined here.
 */

import type { ChoiceView, StoryNodeView } from '../guardian/storyReadThrough'
import { readNodes } from '../guardian/storyReadThrough'

export type {
  ChoiceView,
  EditableChoice,
  EditableNode,
  EndingView,
  ReadThrough,
  StoryNodeView,
} from '../guardian/storyReadThrough'
export {
  buildReadThrough,
  findEditableNode,
  pluralize,
  readNodes,
} from '../guardian/storyReadThrough'

export interface ChangedNodeDiff {
  id: string
  previous: StoryNodeView
  current: StoryNodeView
  bodyChanged: boolean
  choicesChanged: boolean
}

export interface VersionDiff {
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
 * `changed` when its body text differs OR its choices differ per `diffChoices`
 * (matched by target, not position, so a reworded label, an added/removed
 * choice, or a retargeted one counts, but a pure reorder does not).
 *
 * #ASSUME: data integrity: this is a reviewer-facing summary, not the
 * safety-critical read-through above; it does not attempt to distinguish a
 * reordered node list from an untouched one, and a duplicate id still
 * collapses to its first occurrence on each side.
 * #VERIFY: ReviewDetailPage.test.tsx compare-diff tests assert added/removed/
 * changed counts and that an untouched node produces no changed entry.
 */
export function diffNodes(
  previousBlob: Record<string, unknown>,
  currentBlob: Record<string, unknown>
): VersionDiff {
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

export interface ChoiceDiff {
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
export function diffChoices(previous: ChoiceView[], current: ChoiceView[]): ChoiceDiff {
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
