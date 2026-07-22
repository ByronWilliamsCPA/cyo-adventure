/**
 * Presentational version-compare views for ReviewDetailPage: given a
 * `VersionDiff` (see reviewDiff.ts), render the summary line, added/removed
 * lists, and expandable per-node detail. Pure props-in/JSX-out; neither
 * component here reads any ReviewDetailPage state or hook.
 */

import { PassageText } from '@ds/components/PassageText'

import { diffChoices, pluralize, type ChangedNodeDiff, type VersionDiff } from './reviewDiff'

/** One changed passage: old vs new body (when the body itself changed), plus
 * a choices note. Collapsed behind <details> since a version can change many
 * passages and the reviewer scans the summary line first. */
export function ChangedNodeDetail({ entry }: { entry: ChangedNodeDiff }) {
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
export function VersionDiffView({ diff }: { diff: VersionDiff }) {
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
