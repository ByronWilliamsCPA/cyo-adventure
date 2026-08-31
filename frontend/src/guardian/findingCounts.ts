import type { FindingVerdict, FindingView, ReviewQueueItem, ReviewSurface } from './reviewApi'
import { pluralize } from './storyReadThrough'

/**
 * `RS-A3`: the one place any review surface count is derived or labelled.
 *
 * One book used to render four mutually inconsistent numbers. `The Teddy
 * Bears' Picnic` reported `2 advisories` on the queue row, `4 findings` in the
 * detail header, "The moderation gate raised no content concerns" in the gate
 * summary, and `5 flagged` / `5 advisorys` in the overview footer, over 5
 * rendered passage cards. Every one of those was computed at its own call
 * site, from a different population, with its own pluralization.
 *
 * The fix is not one number. Distinct findings and affected passages are
 * genuinely different counts and both are legitimate; what was missing is that
 * neither was named, so a reviewer had no way to tell a disagreement from a
 * bug. Every count here therefore travels with a label that states its
 * denominator, and the labels live beside the counts so a new call site cannot
 * invent a fifth phrasing.
 */
export interface FindingCounts {
  /**
   * Distinct findings: a merged finding fanned across N nodes counts ONCE.
   *
   * Mirrors the backend's queue-badge population exactly
   * (api/review_surface.py::build_review_queue_item, `merged`): the three
   * merged buckets together are every non-PASS finding the surface produced.
   */
  distinct: number
  /** Passages carrying at least one finding, i.e. rendered passage cards. */
  affectedPassages: number
  /** Distinct BLOCK findings. Gating. */
  block: number
  /** Distinct FLAG findings, excluding structural ones, matching the backend. */
  flag: number
  /** Distinct ADVISORY findings. Never gating. */
  advisory: number
  /** The subset of advisories collapsed out of the default view by `RS-A1`. */
  lowAdvisory: number
}

/** The minimum a finding must carry to be tallied by verdict. */
export interface VerdictTallyInput {
  verdict: FindingVerdict
  structural?: boolean
}

/** The three tier counts, the only part of `FindingCounts` a tally produces. */
export type VerdictTally = Pick<FindingCounts, 'block' | 'flag' | 'advisory'>

/**
 * Tally findings by verdict.
 *
 * `RS-A3`: exported because the story-overview footer used to tally verdicts
 * itself, and its copy counted structural findings as flags while the backend
 * and the queue row excluded them. Two tallies over one population that
 * disagree by a hidden rule are exactly the defect this module exists to
 * remove, so there is one tally and every caller uses it.
 */
export function verdictTally(findings: VerdictTallyInput[]): VerdictTally {
  return {
    block: findings.filter((f) => f.verdict === 'block').length,
    // Structural findings describe the pipeline, not the book; the backend
    // excludes them from flag_findings, so this must too or the queue badge
    // and the detail header disagree again by exactly that many rows.
    flag: findings.filter((f) => f.verdict === 'flag' && f.structural !== true).length,
    advisory: findings.filter((f) => f.verdict === 'advisory').length,
  }
}

/**
 * The findings one admin review surface is about: the distinct merged set.
 *
 * #ASSUME: data integrity: on a pre-Stage-B stored report all three merged
 * buckets project empty while flagged_passages/story_level_findings still
 * carry findings, so `distinct` falls back to those. That fallback counts
 * occurrences, not distinct findings, because a legacy report has no merge
 * information to recover the distinct set from; it is an over-count on a
 * legacy row, never an under-count, so a reviewer is never told there is less
 * to look at than there is.
 * #VERIFY: ReviewDetailPage.test.tsx "invents no findings when the backend has
 * not sent the additive fields" renders exactly that shape.
 */
export function surfacePopulation(surface: ReviewSurface): FindingView[] {
  const merged = [
    ...(surface.ranked_findings ?? []),
    ...(surface.structural_findings ?? []),
    ...(surface.low_advisory_findings ?? []),
  ]
  if (merged.length > 0) return merged
  return [
    ...surface.flagged_passages.flatMap((passage) => passage.findings),
    ...surface.story_level_findings,
  ]
}

/** The canonical counts for one admin review surface. */
export function surfaceCounts(surface: ReviewSurface): FindingCounts {
  const population = surfacePopulation(surface)
  return {
    distinct: population.length,
    affectedPassages: surface.flagged_passages.length,
    lowAdvisory: (surface.low_advisory_findings ?? []).length,
    ...verdictTally(population),
  }
}

/**
 * The canonical counts for one review queue row.
 *
 * A queue payload carries the backend's tiered counts but no finding list and
 * no structural count, so `distinct` is the sum of the three tiers rather than
 * a separate field. When the tiered fields are absent (an older cached
 * payload) it falls back to `flagged_count`, which counts occurrences; the
 * label names that difference rather than hiding it.
 */
export function queueItemCounts(item: ReviewQueueItem): FindingCounts {
  const block = item.block_findings ?? 0
  const flag = item.flag_findings ?? 0
  const advisory = item.advisory_findings ?? 0
  const tiered = block + flag + advisory
  return {
    distinct: tiered > 0 ? tiered : item.flagged_count,
    affectedPassages: 0,
    lowAdvisory: 0,
    block,
    flag,
    advisory,
  }
}

/** "4 findings": the distinct-finding count, with its noun stated. */
export function distinctFindingsLabel(counts: FindingCounts): string {
  return pluralize(counts.distinct, 'finding')
}

/**
 * "3 flagged passages below", or null when there are none to name.
 *
 * Rendered beside the distinct count, never instead of it. The two numbers
 * disagreeing is normal, not a bug: one merged finding can cover many
 * passages, and `RS-A1` keeps low advisories out of the passage cards
 * entirely. This counts the passage cards actually on the page, which is the
 * only denominator a reviewer can check against what they see.
 */
export function affectedPassagesLabel(counts: FindingCounts): string | null {
  if (counts.affectedPassages === 0) return null
  return `${pluralize(counts.affectedPassages, 'flagged passage')} below`
}

/**
 * "1 block, 2 flags, 3 advisories", or null when nothing is counted.
 *
 * The tier breakdown for a queue row or the overview footer. Advisories are
 * listed separately and never folded into the flag count, because they do not
 * gate approval and a reviewer reads a combined number as gating.
 *
 * `RS-A3`: the separator is the queue badge's existing middot rather than the
 * overview footer's old comma, so the two surfaces that show this breakdown
 * now read identically. The choice is cosmetic; having one of them is not.
 */
export function tierBreakdownLabel(counts: VerdictTally): string | null {
  const parts = [
    counts.block > 0 ? pluralize(counts.block, 'block') : null,
    counts.flag > 0 ? pluralize(counts.flag, 'flag') : null,
    counts.advisory > 0 ? pluralize(counts.advisory, 'advisory', 'advisories') : null,
  ].filter((part): part is string => part !== null)
  return parts.length > 0 ? parts.join(' · ') : null
}
