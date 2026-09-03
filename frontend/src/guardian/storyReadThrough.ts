/**
 * Pure, backend-blob-shaped helpers for reading a loosely typed storybook
 * blob into a strongly typed read-through, and for finding one node's
 * editable fields. No React/DOM dependency.
 *
 * Split out of `admin/reviewDiff.ts` (register G6, the edit half): both the
 * admin `ReviewDetailPage` and the guardian review/edit page need the same
 * read-through and edit-target lookups, but only the admin page needs the
 * version-diff helpers, which stay in `admin/reviewDiff.ts` (re-exported from
 * there for backward compatibility so no existing admin import breaks).
 */

export interface ChoiceView {
  label: string
  target: string
}

export interface EndingView {
  kind: string | null
  valence: string | null
}

export interface StoryNodeView {
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
export function readNodes(blob: Record<string, unknown>): StoryNodeView[] {
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

export interface EditableChoice {
  id: string
  label: string
  target: string
}

export interface EditableNode {
  body: string
  choices: EditableChoice[]
}

/**
 * Read one node's editable fields (body plus each choice's id/label/target)
 * straight from the raw blob, bypassing `readNodes`/`ChoiceView` (which never
 * carry a choice's `id` -- the read-through and diff views key choices by
 * `target` instead, deliberately, see `admin/reviewDiff.ts::diffChoices`). The
 * G6 edit dialog needs the real choice id to build a
 * `choice_labels: {choice_id: label}` PATCH body, so this reads it directly
 * rather than widening the read-through's own types for a value only the
 * edit dialog uses.
 *
 * Returns `null` when the node id is not found or the node has no usable
 * prose id -- the Edit button that opens this dialog only ever passes an id
 * already rendered from `readNodes`, so this is a defensive fallback, not an
 * expected path.
 */
export function findEditableNode(
  blob: Record<string, unknown>,
  nodeId: string
): EditableNode | null {
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

export interface ReadThrough {
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
export function buildReadThrough(blob: Record<string, unknown>): ReadThrough {
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
 * Pluralize a count for a UI label; shared by ReviewDetailPage (coverage,
 * finding-count), ReviewCompare's diff summary line, and the guardian review
 * page. Kept here rather than in any one component file so none imports from
 * another.
 */
/**
 * Pluralize a count, with an optional explicit plural for irregular nouns.
 *
 * `RS-A3`: the naive `+ "s"` default rendered `5 advisorys` on a live review
 * page, and "advisory" is the most common noun on that surface. An explicit
 * plural is opt-in rather than a lookup table, so a caller states the
 * irregular form beside the noun it belongs to instead of relying on this
 * function to know English.
 */
export function pluralize(count: number, noun: string, plural?: string): string {
  if (count === 1) return `${count} ${noun}`
  return `${count} ${plural ?? `${noun}s`}`
}
