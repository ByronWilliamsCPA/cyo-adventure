import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react'
import { Link } from 'react-router'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { BookDetailsDialog } from '../guardian/BookDetailsDialog'
import { FlagBadge } from '../guardian/FlagBadge'
import { queueItemCounts, tierBreakdownLabel } from '../guardian/findingCounts'
import { formatRelativeTime } from '../guardian/intakeApi'
import { pluralize } from '../guardian/storyReadThrough'
import { ageBandLabel } from '../guardian/storyRequestOptions'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  makeReviewApi,
  type ReviewQueueItem,
  type StillProcessingItem,
} from '../guardian/reviewApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | {
      kind: 'ready'
      items: ReviewQueueItem[]
      processing: StillProcessingItem[]
      // True when `processing` is empty because the generation-jobs load
      // failed, not because nothing is generating. Kept separate from the
      // list so the empty state can say which of the two it is; a guardian-only
      // 403 (the expected admin outcome) is NOT degraded.
      processingDegraded: boolean
      updatedAt: Date
    }

/**
 * A story that was never screened, screened with at least one finding, or
 * whose moderation report was collapsed to an unusable structural row
 * (Task 4: the report_unusable marker means the review pipeline could not
 * produce trustworthy findings, so flagged_count is zeroed alongside it).
 *
 * #ASSUME: data integrity: report_unusable is only ever set on a report the
 * collapse logic (review_surface.py) has also zeroed flagged_count for, so
 * checking both here never double-counts a story into this bucket twice.
 * #VERIFY: AdminConsolePage.test.tsx asserts a report_unusable item with
 * flagged_count 0 still lands under Flagged, not Ready.
 */
function isFlagged(item: ReviewQueueItem): boolean {
  return !item.screened || item.report_unusable === true || item.flagged_count > 0
}

/**
 * Sort rule for the flagged bucket: decision weight, not volume. Hard blocks
 * first (the safety gate refused those stories outright), then reports that
 * could not be scored at all, then the distinct tier counts in gate order:
 * blocks, then flags, then advisories. Everything else keeps the backend's
 * queue order (Array.prototype.sort is stable, so equal ranks never
 * reshuffle).
 *
 * `RS-A7`: the only tiebreak used to be `flagged_count` descending, and that
 * field counts OCCURRENCES. One merged advisory fanned across 380 nodes
 * outranked a book holding a distinct block, which is backwards: the
 * reviewer's work is per distinct finding, and one block outweighs any number
 * of advisories. queueItemCounts() is the same module the row's badge label
 * reads, so the order a reviewer sees and the number they are shown cannot
 * disagree.
 *
 * `distinct` stays on as the LAST key rather than being dropped, because it is
 * the tier sum on a payload that carries the tiers (so it discriminates
 * nothing the three comparisons above have not already settled) and falls back
 * to `flagged_count` on one that does not. Dropping it would leave every
 * pre-tier row tied, which loses the only ordering signal such a row has.
 *
 * #ASSUME: data-integrity: block_findings/flag_findings/advisory_findings are
 * distinct-finding counts from the same merge the review detail page renders
 * (api/review_surface.py::build_review_queue_item).
 * #VERIFY: AdminConsolePage.test.tsx "ranks the flagged bucket by tier
 * weight, not by occurrence count" and "ranks a flag above an advisory at
 * equal block count".
 */
function bySeverity(a: ReviewQueueItem, b: ReviewQueueItem): number {
  const aBlock = a.summary?.hard_block === true
  const bBlock = b.summary?.hard_block === true
  if (aBlock !== bBlock) return aBlock ? -1 : 1

  // A report_unusable book needs a re-run, not a read: rank it right after
  // hard blocks so it is not lost among ordinary tier sorting.
  const aUnusable = a.report_unusable === true
  const bUnusable = b.report_unusable === true
  if (aUnusable !== bUnusable) return aUnusable ? -1 : 1

  const aCounts = queueItemCounts(a)
  const bCounts = queueItemCounts(b)
  if (aCounts.block !== bCounts.block) return bCounts.block - aCounts.block
  if (aCounts.flag !== bCounts.flag) return bCounts.flag - aCounts.flag
  if (aCounts.advisory !== bCounts.advisory) return bCounts.advisory - aCounts.advisory
  return bCounts.distinct - aCounts.distinct
}

/** Local-clock HH:MM (24-hour), deterministic across runner locales. */
function formatUpdatedAt(at: Date): string {
  const hours = String(at.getHours()).padStart(2, '0')
  const minutes = String(at.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}

/**
 * Badge label for a flagged row: tiered block/flag/advisory counts when the
 * backend supplies them, falling back to the flat flagged_count for a report
 * from before those fields existed.
 *
 * `RS-A3`: the tiers and their pluralization now come from
 * `guardian/findingCounts.ts`, the one module that defines these counts, so
 * this row and the review detail page cannot drift apart. Two defects went
 * with the hand-rolled version: it rendered `2 block` and `1 flags`, and its
 * fallback labelled `flagged_count` as "flags" when that field counts
 * OCCURRENCES (one merged finding across 380 nodes counted 380 times), which
 * is a different number from the tiers above it and now says so.
 *
 * #ASSUME: data integrity: block_findings/flag_findings/advisory_findings are
 * either all present (a Stage-B-or-later report) or all absent (an older
 * cached queue payload); a partial set would silently under-report the
 * missing tiers rather than fail, since each is defaulted to 0 independently.
 * A report carrying ONLY structural findings also lands on the fallback, since
 * the backend excludes structural rows from flag_findings; the fallback's
 * wording therefore has to hold for that case too, not just for a legacy row.
 * #VERIFY: AdminConsolePage.test.tsx asserts the tiered string replaces the
 * flat count when the tiered fields are present.
 */
function tierLabel(item: ReviewQueueItem): string {
  return (
    tierBreakdownLabel(queueItemCounts(item)) ?? pluralize(item.flagged_count, 'flagged occurrence')
  )
}

/**
 * Severity cluster for one queue row, driven by the moderation summary.
 * Every badge pairs text with its tone; color is never the only signal.
 *
 * #ASSUME: data integrity: hard_block and soft_flag are mutually exclusive
 * (ModerationReport.has_soft_flag excludes blocked reports), so one primary
 * badge is exact, never lossy; "Repaired" stacks alongside because repair is
 * orthogonal to the gate verdict. report_unusable (Task 4's collapsed-report
 * marker) is checked ahead of flagged_count so a book whose report could not
 * be scored still reads as needing action, not as clean.
 * #VERIFY: AdminConsolePage.test.tsx asserts a hard-block row shows
 * "Hard block" with no flag count, a repaired soft-flag row shows both
 * "N flags" and "Repaired", and a report_unusable row shows the
 * moderation-unavailable label even when flagged_count is 0.
 */
function SeverityBadges({ item }: { item: ReviewQueueItem }): ReactElement {
  if (!item.screened) return <FlagBadge tone="unscreened" />
  return (
    <span className="admin-severity">
      {item.summary?.hard_block ? (
        <span className="flag-badge admin-severity__hard-block">Hard block</span>
      ) : item.report_unusable === true ? (
        <FlagBadge tone="flag" label="Moderation unavailable · re-run required" />
      ) : item.flagged_count > 0 ? (
        <FlagBadge tone="flag" label={tierLabel(item)} />
      ) : (
        <FlagBadge tone="clean" />
      )}
      {item.summary?.repaired ? (
        <span className="flag-badge admin-severity__repaired">Repaired</span>
      ) : null}
    </span>
  )
}

/** At-a-glance triage metadata: age band and how long the story has waited (UX-A3). */
function QueueRowMeta({ item, nowMs }: { item: ReviewQueueItem; nowMs: number }) {
  const waited =
    typeof item.waiting_since === 'string' ? formatRelativeTime(item.waiting_since, nowMs) : null
  if (!item.age_band && !waited) return null
  return (
    <span className="console-row__meta cyo-text-muted">
      {item.age_band ? <span>{ageBandLabel(item.age_band)}</span> : null}
      {item.age_band && waited ? <span aria-hidden="true"> · </span> : null}
      {waited ? <span>Waiting {waited}</span> : null}
    </span>
  )
}

/**
 * `RS-A7`: the top-ranked finding's concern and reason, on the row.
 *
 * The queue row used to name the severity ("Hard block", "3 flags") and
 * nothing else, so learning WHAT the block was cost a full review-detail
 * load: 2.5 MB of blob and ~10,900 DOM nodes to read one sentence. The
 * backend now sends the same finding the detail page ranks first, so the
 * reviewer can triage, and often dismiss, from the queue.
 *
 * #ASSUME: data integrity: top_finding is the first entry of the same ranked
 * bucket the detail page renders first (api/review_surface.py derives it from
 * build_review_surface's ranked/structural/low-advisory buckets in that
 * order), so the row's reason is the reason the reviewer will land on. It is
 * absent on a clean book and on a payload cached before the field existed;
 * both render nothing rather than a guess.
 * #VERIFY: tests/unit/test_review_surface.py::test_queue_top_finding_is_the_first_ranked_finding
 * pins the backend half; AdminConsolePage.test.tsx "names the top finding on
 * the queue row" pins this half.
 */
function QueueRowReason({ item }: { item: ReviewQueueItem }): ReactElement | null {
  const finding = item.top_finding
  if (finding === null || finding === undefined) return null
  const concern = finding.concern ?? finding.category
  return (
    <span className="console-row__reason cyo-text-muted">
      <span className="console-row__reason-concern">{concern}</span>
      <span aria-hidden="true"> · </span>
      <span>{finding.message}</span>
    </span>
  )
}

function QueueRow({
  item,
  queue,
  nowMs,
  onShowDetails,
}: {
  item: ReviewQueueItem
  queue: string[]
  nowMs: number
  onShowDetails: (storybookId: string) => void
}) {
  return (
    <li className="console-row console-row--with-details cyo-card cyo-card--interactive">
      {/* Pass the ordered ids of this bucket so the detail page can show queue
          position and auto-advance to the next item after a decision (UX-A1). */}
      <Link
        className="console-row__link"
        to={`/admin/review/${item.storybook_id}`}
        state={{ reviewQueue: queue }}
      >
        {/* Title, triage metadata and the top finding's reason stack in one
            column so the reason gets a line of its own instead of competing
            with the badges for horizontal room (RS-A7). */}
        <span className="console-row__primary">
          <span className="console-row__headline">
            <span className="console-row__title">{item.title}</span>
            <QueueRowMeta item={item} nowMs={nowMs} />
          </span>
          <QueueRowReason item={item} />
        </span>
        <SeverityBadges item={item} />
      </Link>
      <Button
        variant="ghost"
        size="sm"
        className="book-details__trigger"
        onClick={() => onShowDetails(item.storybook_id)}
        aria-label={`View details for ${item.title}`}
      >
        Details
      </Button>
    </li>
  )
}

/**
 * Admin console home (C4a-4): the safety operator's severity-ordered review
 * queue, moved from the guardian console when admin functions gained their
 * own surface. Flagged stories sort to the top (hard blocks first, see
 * bySeverity), then ready-to-review, then still processing. The route is
 * admin-gated (router.tsx), and the queue endpoint independently requires
 * the admin capability server-side (ADR-005: the approver is the global
 * safety reviewer, not any guardian).
 */
export function AdminConsolePage() {
  usePageTitle('Admin Console')
  const api = useApi()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [refreshing, setRefreshing] = useState(false)
  const [refreshFailed, setRefreshFailed] = useState(false)
  const [query, setQuery] = useState('')
  const [detailsFor, setDetailsFor] = useState<string | null>(null)

  const fetchQueue = useCallback(async () => {
    const [items, stillProcessing] = await Promise.all([
      reviewApi.queue(),
      reviewApi.stillProcessing(),
    ])
    return { items, processing: stillProcessing.jobs, processingDegraded: stillProcessing.degraded }
  }, [reviewApi])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const { items, processing, processingDegraded } = await fetchQueue()
        if (!cancelled)
          setState({ kind: 'ready', items, processing, processingDegraded, updatedAt: new Date() })
      } catch (err) {
        // #CRITICAL: security: the route is admin-gated, but the backend
        // check is independent (defense in depth); a 403 here means the
        // capability was revoked mid-session, an expected outcome, not a
        // failure, so surface a clear notice.
        // #VERIFY: AdminConsolePage.test.tsx asserts the notice on a 403 and
        // the generic error on a 500.
        if (classifyApiError(err).kind === 'forbidden') {
          if (!cancelled) setState({ kind: 'forbidden' })
          return
        }
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('review queue load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) setState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [fetchQueue])

  // Manual refetch only (no polling): the button disables while in flight,
  // and a failure keeps the last good queue on screen behind an inline alert
  // instead of discarding it for the full-page error state.
  // #EDGE: timing dependencies: a refresh can settle after an unmount (route
  // change mid-flight); React 18+ makes setState on an unmounted component a
  // safe no-op, so no cancellation flag is needed for this handler.
  // #VERIFY: guaranteed by React, not by this code; nothing to assert.
  async function refresh() {
    setRefreshing(true)
    setRefreshFailed(false)
    try {
      const { items, processing, processingDegraded } = await fetchQueue()
      setState({ kind: 'ready', items, processing, processingDegraded, updatedAt: new Date() })
    } catch (err) {
      // #ASSUME: security: a 403 on refresh means the admin capability was
      // revoked mid-session; fail closed to the same no-access notice as the
      // initial load rather than keeping the now-stale queue visible.
      // #VERIFY: AdminConsolePage.test.tsx asserts a 403 refresh swaps the
      // queue for the notice and a 500 refresh keeps the queue with an alert.
      if (classifyApiError(err).kind === 'forbidden') {
        setState({ kind: 'forbidden' })
      } else {
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('review queue refresh failed:', err instanceof Error ? err.message : err)
        setRefreshFailed(true)
      }
    } finally {
      setRefreshing(false)
    }
  }

  let content: ReactElement
  if (state.kind === 'loading') {
    content = <LoadingStatus>Loading review queue…</LoadingStatus>
  } else if (state.kind === 'forbidden') {
    content = (
      <section className="console">
        <h1>Review queue</h1>
        <p className="console__notice cyo-text-muted">
          Your account does not have review access. Reviews are handled by the safety reviewer.
        </p>
      </section>
    )
  } else if (state.kind === 'error') {
    content = (
      <ErrorBanner className="console__error">
        We could not load the review queue. Please reload.
      </ErrorBanner>
    )
  } else {
    const trimmedQuery = query.trim()
    const needle = trimmedQuery.toLowerCase()
    const searching = needle.length > 0
    const matchesTitle = (title: string): boolean => title.toLowerCase().includes(needle)

    // Sort before filtering so severity order is independent of the search.
    const flagged = state.items
      .filter(isFlagged)
      .sort(bySeverity)
      .filter((item) => !searching || matchesTitle(item.title))
    // The complement of isFlagged, not an independently-written condition:
    // a separately spelled-out negation drifted out of sync with isFlagged
    // once report_unusable was added there, double-listing an unusable
    // report under both Flagged and Ready.
    const ready = state.items.filter(
      (item) => !isFlagged(item) && (!searching || matchesTitle(item.title))
    )
    const processing = state.processing.filter((job) => !searching || matchesTitle(job.title))
    const nothingPending = state.items.length === 0 && state.processing.length === 0
    const noMatches =
      searching && flagged.length === 0 && ready.length === 0 && processing.length === 0
    const detailsItem =
      detailsFor !== null
        ? (state.items.find((item) => item.storybook_id === detailsFor) ?? null)
        : null

    content = (
      <>
        <section className="console">
          <div className="admin-console__header">
            <h1>Review queue</h1>
            <div className="admin-console__meta">
              <span className="admin-console__updated cyo-text-muted">
                Updated {formatUpdatedAt(state.updatedAt)}
              </span>
              <button
                type="button"
                className="admin-console__refresh"
                onClick={() => void refresh()}
                disabled={refreshing}
              >
                Refresh
              </button>
            </div>
          </div>
          {refreshFailed ? (
            <ErrorBanner className="admin-console__refresh-error">
              Refresh failed. Showing the queue from {formatUpdatedAt(state.updatedAt)}.
            </ErrorBanner>
          ) : null}
          {nothingPending ? (
            <EmptyState
              title="Nothing to review"
              description="New stories appear here once they finish generating."
            />
          ) : (
            <>
              <label className="admin-search cyo-field" htmlFor="admin-queue-search">
                Search by title
                <input
                  id="admin-queue-search"
                  type="search"
                  className="cyo-field__control"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              {noMatches ? (
                <p role="status" className="admin-search__no-matches cyo-text-muted">
                  No matches for &quot;{trimmedQuery}&quot;
                </p>
              ) : (
                <>
                  {flagged.length > 0 ? (
                    <div className="console-group">
                      <h2 className="console-group__heading">Flagged (review carefully)</h2>
                      <ul className="console-list">
                        {flagged.map((item) => (
                          <QueueRow
                            key={item.storybook_id}
                            item={item}
                            queue={flagged.map((i) => i.storybook_id)}
                            nowMs={state.updatedAt.getTime()}
                            onShowDetails={setDetailsFor}
                          />
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {ready.length > 0 ? (
                    <div className="console-group">
                      <h2 className="console-group__heading">Ready to review</h2>
                      <ul className="console-list">
                        {ready.map((item) => (
                          <QueueRow
                            key={item.storybook_id}
                            item={item}
                            queue={ready.map((i) => i.storybook_id)}
                            nowMs={state.updatedAt.getTime()}
                            onShowDetails={setDetailsFor}
                          />
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {searching && processing.length === 0 && !state.processingDegraded ? null : (
                    <div className="console-group">
                      <h2 className="console-group__heading">Still processing</h2>
                      {processing.length === 0 ? (
                        <p className="console__muted cyo-text-muted">
                          {state.processingDegraded
                            ? 'Could not load what is generating right now. Refresh to try again.'
                            : 'No stories are generating right now.'}
                        </p>
                      ) : (
                        <ul className="console-list">
                          {processing.map((job) => (
                            <li key={job.job_id} className="console-row cyo-card">
                              <span className="console-row__title">{job.title}</span>
                              <FlagBadge tone="processing" />
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </section>
        {detailsItem !== null ? (
          <BookDetailsDialog
            title={detailsItem.title}
            ageBand={detailsItem.age_band ?? null}
            themes={detailsItem.themes ?? []}
            contentFlags={detailsItem.content_flags}
            moderationBadge={<SeverityBadges item={detailsItem} />}
            onClose={() => setDetailsFor(null)}
          />
        ) : null}
      </>
    )
  }

  return content
}
