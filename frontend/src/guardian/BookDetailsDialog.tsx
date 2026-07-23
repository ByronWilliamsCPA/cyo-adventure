/**
 * Book-detail popover shared by the guardian browse-and-assign list
 * (BooksPage.tsx) and the admin review queue / master library
 * (AdminConsolePage.tsx, AdminLibraryPage.tsx). A click on a row's "Details"
 * button opens this dialog with the age band, themes, and content-sensitivity
 * flags already carried on the list item (ReviewQueueItem / StorybookSummary /
 * GuardianBookItem all now project `themes`/`content_flags` alongside
 * `age_band`), so no extra fetch is needed just to see them.
 *
 * The moderation badge is deliberately a caller-supplied slot rather than
 * computed here: each console already has its own badge component
 * (BooksPage's ContentBadge, AdminConsolePage's SeverityBadges) tuned to that
 * list's exact signals (e.g. hard-block/repaired only exist in the admin
 * queue), and duplicating that logic here would let the two drift.
 */

import type { ReactNode } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { ageBandLabel } from './storyRequestOptions'
import type { ContentFlagLevel, ContentFlags } from './reviewApi'
import './guardian.css'

const FLAG_LABELS: Record<keyof ContentFlags, string> = {
  violence: 'Violence',
  scariness: 'Scariness',
  peril: 'Peril',
}

function flagLevel(level: ContentFlagLevel | undefined): string {
  return level ?? 'none'
}

export interface BookDetailsDialogProps {
  title: string
  ageBand: string | null
  themes: string[]
  contentFlags: ContentFlags | null | undefined
  /**
   * Page-specific moderation badge. Omitted on surfaces whose list item
   * carries no moderation signal (e.g. AdminLibraryPage's master library,
   * which lists every lifecycle status but not screened/flagged_count); the
   * Moderation row is skipped rather than showing a misleading placeholder.
   */
  moderationBadge?: ReactNode
  onClose: () => void
}

export function BookDetailsDialog({
  title,
  ageBand,
  themes,
  contentFlags,
  moderationBadge,
  onClose,
}: BookDetailsDialogProps) {
  const hasContentFlags =
    contentFlags != null &&
    ((contentFlags.violence ?? 'none') !== 'none' ||
      (contentFlags.scariness ?? 'none') !== 'none' ||
      (contentFlags.peril ?? 'none') !== 'none')

  return (
    <Dialog title={title} onClose={onClose} actions={<Button onClick={onClose}>Close</Button>}>
      <dl className="book-details">
        {ageBand ? (
          <div className="book-details__row">
            <dt>Age band</dt>
            <dd>{ageBandLabel(ageBand)}</dd>
          </div>
        ) : null}
        {moderationBadge !== undefined ? (
          <div className="book-details__row">
            <dt>Moderation</dt>
            <dd>{moderationBadge}</dd>
          </div>
        ) : null}
        {themes.length > 0 ? (
          <div className="book-details__row">
            <dt>Themes</dt>
            <dd>{themes.join(', ')}</dd>
          </div>
        ) : null}
        {contentFlags ? (
          <div className="book-details__row">
            <dt>Content flags</dt>
            <dd>
              {hasContentFlags ? (
                <ul className="book-details__flags">
                  {(Object.keys(FLAG_LABELS) as (keyof ContentFlags)[]).map((key) => (
                    <li key={key}>
                      {FLAG_LABELS[key]}: {flagLevel(contentFlags[key])}
                    </li>
                  ))}
                </ul>
              ) : (
                'None reported'
              )}
            </dd>
          </div>
        ) : null}
      </dl>
    </Dialog>
  )
}
