/* eslint-disable react-refresh/only-export-components --
 * This file's export list is deliberately mixed: `passageDomId` is a plain
 * function shared by both ReviewDetailPage (admin) and
 * GuardianReviewDetailPage (guardian) to compute the same DOM id from a node
 * id, so a jump target resolves identically for both audiences. Splitting it
 * into its own file would only add an import for a single one-line helper;
 * see routeElements.tsx's file-level disable for the same reasoning applied
 * to this project's router chunk file.
 */
import { Button } from '@ds/components/Button'
import { PassageText } from '@ds/components/PassageText'
import { FlagBadge } from './FlagBadge'
import { verdictTone } from './verdictTone'
import type { FindingView } from './reviewApi'
import type { StoryNodeView } from './storyReadThrough'

/**
 * DOM id for a passage container. encodeURIComponent keeps the id free of
 * whitespace (node ids are arbitrary strings on this defensive surface) while
 * staying deterministic from both a blob node id and a finding's node_id.
 * Duplicate node ids share a DOM id; a jump lands on the first (reachable)
 * copy, and the duplicate still renders in the unreachable section.
 *
 * Shared by the admin ReviewDetailPage and the guardian review/edit page
 * (register G6, the edit half): both jump to a passage by the same scheme.
 */
export function passageDomId(nodeId: string): string {
  return `passage-${encodeURIComponent(nodeId)}`
}

export function Finding({ finding }: { finding: FindingView }) {
  return (
    <li className="review-finding">
      <FlagBadge tone={verdictTone(finding.verdict)} />
      <span className="review-finding__category">{finding.category}</span>
      <span className="review-finding__message">{finding.message}</span>
    </li>
  )
}

/**
 * A ranked/structural/low-advisory finding (Stage B3, design doc 2.6): the
 * same badge/category/message as `Finding` above, plus a severity pill and
 * score when present, and an on-demand node drill-down. The finding's
 * affected nodes (`node_ids` when the merge stage fanned it across several,
 * falling back to the single `node_id` otherwise) stay collapsed behind a
 * <details> so the ranked list itself stays scannable; expanding it offers a
 * jump-to-passage button per node that resolves in the current read-through.
 *
 * `RS-A2`: pass `proseFor` to make the finding the entry point to its own
 * affected passages, rather than a triage row whose prose lives only in a
 * separate flat list further down the page. The prose renders inside the
 * already-collapsed node drill-down, so the scannable list is unchanged until
 * a reviewer asks for context on one finding. Omitting `proseFor` keeps the
 * pre-`RS-A2` behaviour (ids and jump buttons only), which is what the
 * guardian surface wants: it renders no story prose of its own.
 */
export function RankedFinding({
  finding,
  onJump,
  knownIds,
  proseFor,
}: {
  finding: FindingView
  onJump: (nodeId: string) => void
  knownIds: Set<string>
  proseFor?: (nodeId: string) => string | null
}) {
  const nodeIds =
    finding.node_ids && finding.node_ids.length > 0
      ? finding.node_ids
      : finding.node_id !== null && finding.node_id !== undefined
        ? [finding.node_id]
        : []
  return (
    <li className="review-finding review-finding--ranked">
      <FlagBadge tone={verdictTone(finding.verdict)} />
      {finding.severity ? (
        <span className={`review-finding__severity review-finding__severity--${finding.severity}`}>
          {finding.severity}
        </span>
      ) : null}
      <span className="review-finding__category">{finding.concern ?? finding.category}</span>
      {/*
        `RS-A2`: a reviewer told "advisory, violence, 0.41" can calibrate
        against the band's threshold; one told "advisory, violence" cannot.
        Rendered only when the classifier actually returned a score:
        typeof-number rather than a truthiness test, because a genuine 0 is a
        bright-line score, and `null` (deterministic, unscored) must stay
        blank rather than reading as 0.00.
      */}
      {typeof finding.score === 'number' ? (
        <span className="review-finding__score">{finding.score.toFixed(2)}</span>
      ) : null}
      <span className="review-finding__message">{finding.message}</span>
      {nodeIds.length > 0 ? (
        <details className="review-finding__nodes">
          <summary>
            {nodeIds.length} affected node{nodeIds.length === 1 ? '' : 's'}
          </summary>
          <ul>
            {nodeIds.map((nodeId) => {
              const prose = proseFor ? proseFor(nodeId) : null
              return (
                <li key={nodeId}>
                  {knownIds.has(nodeId) ? (
                    <button type="button" className="review-jump" onClick={() => onJump(nodeId)}>
                      {nodeId}
                    </button>
                  ) : (
                    <span className="cyo-text-muted">{nodeId}</span>
                  )}
                  {prose !== null ? (
                    <div className="review-finding__prose">
                      <PassageText text={prose} />
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ul>
        </details>
      ) : null}
    </li>
  )
}

export interface PassageProps {
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
 * choice labels); `editDisabled` mirrors the admin actionbar's own status
 * guard (and the guardian page's own status message) so an edit is never
 * offered on a published/archived/draft version the backend would reject
 * anyway.
 */
export function Passage({
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
