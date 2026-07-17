/**
 * Guardian/admin skim aid (register G5, Phase 4b): a structure/branch overview
 * plus a compact content summary, so a reviewer can size up a generated story
 * without reading every passage.
 *
 * Pure client-side projection of a Storybook content blob (the same blob both
 * the admin review surface and the guardian's fetched published version
 * already carry -- see ReviewDetailPage.tsx and AssignChildrenDialog.tsx).
 * Nothing here reads or infers moderation internals beyond the counts the
 * caller already has permission to see: the `findings`/`flaggedCount`/
 * `screened` props are handed in by the caller, never derived from a raw
 * moderation report, so this component cannot leak anything the caller could
 * not already show.
 */

import { useMemo } from 'react'

import type { FindingVerdict } from './reviewApi'
import { FlagBadge } from './FlagBadge'

const WORDS_PER_MINUTE = 200

export interface StoryStructureFinding {
  verdict: FindingVerdict
}

export interface StoryStructureEnding {
  id: string
  title: string
  valence: string | null
  kind: string | null
}

export interface StoryStructureContentFlags {
  violence: string
  scariness: string
  peril: string
}

export interface StoryStructureData {
  nodeCount: number
  endingCount: number
  endings: StoryStructureEnding[]
  /** Minutes to read, from metadata when present; else a word-count estimate. */
  estimatedMinutes: number | null
  /** True when estimatedMinutes was derived from word count, not authored metadata. */
  estimateIsDerived: boolean
  themes: string[]
  contentFlags: StoryStructureContentFlags | null
  startNodeId: string | null
  /** Decision points (nodes with more than one choice) on the shortest path
   * from start to the nearest ending, or null when not cheaply computable
   * (missing/dangling start node, or no ending reachable at all). */
  decisionCount: number | null
}

interface StructureNode {
  id: string
  isEnding: boolean
  ending: StoryStructureEnding | null
  choiceTargets: string[]
  wordCount: number
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null
}

function asStringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Read structure-relevant fields from the blob's nodes array. Deliberately
 * defensive like ReviewDetailPage.tsx's readNodes: a malformed node is kept
 * (with a synthetic id / empty fields) rather than dropped, since dropping a
 * node here would silently undercount a skim aid.
 */
function readStructureNodes(blob: Record<string, unknown>): StructureNode[] {
  const raw = blob.nodes
  if (!Array.isArray(raw)) return []
  const nodes: StructureNode[] = []
  raw.forEach((entry, index) => {
    const record = asRecord(entry)
    if (!record) return
    const id = typeof record.id === 'string' ? record.id : ''
    const body = typeof record.body === 'string' ? record.body : ''
    if (!id && !body) return
    const endingRecord = asRecord(record.ending)
    const nodeId = id || `node-${index}`
    let ending: StoryStructureEnding | null = null
    if (endingRecord) {
      const title = asStringOrNull(endingRecord.title)
      ending = {
        id: asStringOrNull(endingRecord.id) || nodeId,
        title: title && title.length > 0 ? title : nodeId,
        valence: asStringOrNull(endingRecord.valence),
        kind: asStringOrNull(endingRecord.kind),
      }
    }
    const choiceTargets: string[] = []
    if (Array.isArray(record.choices)) {
      for (const choice of record.choices) {
        const choiceRecord = asRecord(choice)
        const target = choiceRecord ? choiceRecord.target : undefined
        if (typeof target === 'string' && target) choiceTargets.push(target)
      }
    }
    nodes.push({
      id: nodeId,
      isEnding: record.is_ending === true || ending !== null,
      ending,
      choiceTargets,
      wordCount: body.trim() ? body.trim().split(/\s+/).length : 0,
    })
  })
  return nodes
}

/**
 * Shortest (fewest-hops) path from `startId` to the nearest ending node, by
 * breadth-first search over choice targets. First-occurrence-wins on a
 * duplicate node id, matching ReviewDetailPage.tsx's traversal rule. Returns
 * null when the start node is missing/dangling or no ending is reachable --
 * the "else omit" case for the branch-shape line.
 */
function shortestPathToEnding(nodes: StructureNode[], startId: string): StructureNode[] | null {
  const byId = new Map<string, StructureNode>()
  for (const node of nodes) {
    if (!byId.has(node.id)) byId.set(node.id, node)
  }
  const start = byId.get(startId)
  if (!start) return null
  if (start.isEnding) return [start]
  const prev = new Map<string, string>()
  const visited = new Set<string>([start.id])
  const queue: string[] = [start.id]
  let endingId: string | null = null
  for (let head = 0; head < queue.length && endingId === null; head += 1) {
    const current = byId.get(queue[head])
    if (!current) continue
    for (const target of current.choiceTargets) {
      if (visited.has(target)) continue
      visited.add(target)
      prev.set(target, current.id)
      const targetNode = byId.get(target)
      if (targetNode?.isEnding) {
        endingId = target
        break
      }
      queue.push(target)
    }
  }
  if (endingId === null) return null
  const path: StructureNode[] = []
  let cursor: string | null = endingId
  while (cursor !== null) {
    const node = byId.get(cursor)
    if (!node) break
    path.unshift(node)
    cursor = prev.get(cursor) ?? null
  }
  return path
}

/** Decision points (>1 choice) strictly before the terminal ending on a path. */
function decisionCountOnPath(path: StructureNode[]): number {
  return path.slice(0, -1).filter((node) => node.choiceTargets.length > 1).length
}

function readContentFlags(metadata: Record<string, unknown>): StoryStructureContentFlags | null {
  const raw = asRecord(metadata.content_flags)
  if (!raw) return null
  const level = (value: unknown): string => (typeof value === 'string' && value ? value : 'none')
  const flags = {
    violence: level(raw.violence),
    scariness: level(raw.scariness),
    peril: level(raw.peril),
  }
  const allNone = flags.violence === 'none' && flags.scariness === 'none' && flags.peril === 'none'
  return allNone ? null : flags
}

/**
 * Project a raw Storybook blob into skim-aid data. Pure and defensive: every
 * field degrades to an empty/null default rather than throwing, since a blob
 * arriving here has already passed the backend's own validation (or, for the
 * guardian path, is mid-fetch and briefly `{}`).
 */
export function readStoryStructure(blob: Record<string, unknown>): StoryStructureData {
  const nodes = readStructureNodes(blob)
  const endings = nodes
    .filter((node): node is StructureNode & { ending: StoryStructureEnding } => node.ending !== null)
    .map((node) => node.ending)
  const metadata = asRecord(blob.metadata) ?? {}
  const themes = Array.isArray(metadata.themes)
    ? metadata.themes.filter((theme): theme is string => typeof theme === 'string')
    : []
  const declaredMinutes = metadata.estimated_minutes
  let estimatedMinutes: number | null =
    typeof declaredMinutes === 'number' && Number.isFinite(declaredMinutes) ? declaredMinutes : null
  let estimateIsDerived = false
  if (estimatedMinutes === null) {
    const totalWords = nodes.reduce((sum, node) => sum + node.wordCount, 0)
    if (totalWords > 0) {
      estimatedMinutes = Math.max(1, Math.round(totalWords / WORDS_PER_MINUTE))
      estimateIsDerived = true
    }
  }
  const startNodeId = typeof blob.start_node === 'string' && blob.start_node ? blob.start_node : null
  const path = startNodeId ? shortestPathToEnding(nodes, startNodeId) : null
  return {
    nodeCount: nodes.length,
    endingCount: nodes.filter((node) => node.isEnding).length,
    endings,
    estimatedMinutes,
    estimateIsDerived,
    themes,
    contentFlags: readContentFlags(metadata),
    startNodeId,
    decisionCount: path ? decisionCountOnPath(path) : null,
  }
}

function pluralize(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

interface SeverityCounts {
  block: number
  flag: number
  advisory: number
}

function severityCounts(findings: StoryStructureFinding[]): SeverityCounts {
  const counts: SeverityCounts = { block: 0, flag: 0, advisory: 0 }
  for (const finding of findings) {
    if (finding.verdict === 'block') counts.block += 1
    else if (finding.verdict === 'flag') counts.flag += 1
    else if (finding.verdict === 'advisory') counts.advisory += 1
  }
  return counts
}

export interface StoryStructureSummaryProps {
  /** The Storybook content blob (nodes, start_node, metadata). */
  blob: Record<string, unknown>
  /** Whether this version has been moderation-screened. */
  screened: boolean
  /** Total flagged-passage count: per-node plus story-level findings. */
  flaggedCount: number
  /**
   * Per-finding verdicts for a block/flag/advisory severity split. Admin-only:
   * the guardian content summary does not carry per-node finding detail, so
   * the guardian call site omits this.
   */
  findings?: StoryStructureFinding[]
  /**
   * Hides node count, branch shape, and the severity split -- the admin-only
   * structural detail a guardian does not need to decide whether to assign a
   * book. Endings, read time, themes, and the flagged badge still show.
   */
  compact?: boolean
  className?: string
}

/**
 * G5 skim aid: story structure (node/ending counts, branch shape, read time,
 * themes) plus a flagged-content indicator, built entirely from data the
 * caller already has permission to show. See the module doc for the
 * redaction contract.
 */
export function StoryStructureSummary({
  blob,
  screened,
  flaggedCount,
  findings,
  compact = false,
  className,
}: StoryStructureSummaryProps) {
  const structure = useMemo(() => readStoryStructure(blob), [blob])
  const severity = !compact && findings ? severityCounts(findings) : null
  const classes = ['story-structure', compact ? 'story-structure--compact' : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={classes}>
      <dl className="story-structure__stats">
        {!compact ? (
          <div className="story-structure__stat">
            <dt>Passages</dt>
            <dd>{structure.nodeCount}</dd>
          </div>
        ) : null}
        <div className="story-structure__stat">
          <dt>Endings</dt>
          <dd>{structure.endingCount}</dd>
        </div>
        <div className="story-structure__stat">
          <dt>Read time</dt>
          <dd>
            {structure.estimatedMinutes !== null
              ? `${pluralize(structure.estimatedMinutes, 'minute')}${
                  structure.estimateIsDerived ? ' (estimated)' : ''
                }`
              : 'Unknown'}
          </dd>
        </div>
        {!compact && structure.decisionCount !== null && structure.startNodeId !== null ? (
          <div className="story-structure__stat">
            <dt>Branch shape</dt>
            <dd>
              Starts at &quot;{structure.startNodeId}&quot;,{' '}
              {pluralize(structure.decisionCount, 'decision point')} to the nearest ending
            </dd>
          </div>
        ) : null}
      </dl>

      {structure.themes.length > 0 ? (
        <p className="story-structure__themes">
          <span className="story-structure__label">Themes:</span> {structure.themes.join(', ')}
        </p>
      ) : null}

      {!compact && structure.contentFlags ? (
        <p className="story-structure__content-flags">
          <span className="story-structure__label">Content flags:</span> violence{' '}
          {structure.contentFlags.violence}, scariness {structure.contentFlags.scariness}, peril{' '}
          {structure.contentFlags.peril}
        </p>
      ) : null}

      {structure.endings.length > 0 ? (
        <div className="story-structure__endings">
          <h4>Endings</h4>
          <ul>
            {structure.endings.map((ending, index) => (
              // Ending ids can repeat on a malformed blob; index disambiguates.
              <li key={`${ending.id}-${index}`}>
                <span className="story-structure__ending-title">{ending.title}</span>
                {ending.valence || ending.kind ? (
                  <span className="story-structure__ending-detail cyo-text-muted">
                    {' '}
                    (
                    {[ending.valence, ending.kind]
                      .filter((part): part is string => part !== null)
                      .join(', ')}
                    )
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="story-structure__flags">
        {!screened ? (
          <FlagBadge tone="unscreened" />
        ) : flaggedCount > 0 ? (
          <>
            <FlagBadge tone="flag" label={`${flaggedCount} flagged`} />
            {severity ? (
              <span className="story-structure__severity cyo-text-muted">
                {[
                  severity.block > 0 ? pluralize(severity.block, 'block') : null,
                  severity.flag > 0 ? pluralize(severity.flag, 'flag') : null,
                  severity.advisory > 0 ? pluralize(severity.advisory, 'advisory') : null,
                ]
                  .filter((part): part is string => part !== null)
                  .join(', ')}
              </span>
            ) : null}
          </>
        ) : (
          <FlagBadge tone="clean" />
        )}
      </div>
    </div>
  )
}
