import type { StoryNodeView } from '../guardian/storyReadThrough'

/**
 * `RS-A4`: a bounded false-negative spot check.
 *
 * Owner ruling (2026-08-31): "I dont expect that a reviewer can read the
 * entire book. They are trying to catch false positives and false negatives."
 * The findings sections above serve the false-POSITIVE half: everything the
 * gate raised is there to be dismissed or acted on. Nothing served the
 * false-negative half, and the only affordance the page offered was the full
 * read-through: 250-plus screens on a large book, which is not sampling, it is
 * the failure mode.
 *
 * This module draws a small, structured sample instead, so the reviewer's
 * question becomes "did the gate miss anything here" over a known number of
 * screens. Three properties make the sample worth trusting:
 *
 * - **Spread, not sequential.** Reading the first 15 passages of a branching
 *   story samples one region of the graph. The draw strides across the whole
 *   read-through so the sample covers early, middle, and late passages.
 * - **Weighted toward passages with NO findings.** A flagged passage is
 *   already on the page above. The value of a sample is entirely in the
 *   regions the gate said nothing about.
 * - **Deterministic.** The same book and version always draw the same sample,
 *   so a reviewer who returns to a book sees the passages they were part-way
 *   through rather than a fresh draw, and a second reviewer can be asked about
 *   the same passages. No seeded RNG is involved; the stride is a pure
 *   function of the read-through's order.
 */

/** One sampled passage, with why it was eligible. */
export interface ReviewSampleNode {
  id: string
  body: string
  /** True when a moderation finding names this node, i.e. a topped-up draw. */
  hasFinding: boolean
  /** 1-based position in the read-through, so the sample can say "of N". */
  position: number
}

export interface ReviewSample {
  /** The drawn passages, in read-through order for a coherent read. */
  nodes: ReviewSampleNode[]
  /** Passages in the whole read-through, the denominator of the draw. */
  totalPassages: number
  /** Passages no finding names: the population the draw prefers. */
  unflaggedTotal: number
  /**
   * How many passages were requested.
   *
   * #CRITICAL: security: this number is NOT statistically derived. Ruling 2
   * (2026-08-31) settled that it ships labelled provisional until `RS-CAL3`
   * measures a false-negative rate, because a bare "15 of 550 passages
   * checked" manufactures confidence in exactly the channel this feature
   * exists to make trustworthy. Any UI rendering a sample MUST render
   * `SAMPLE_NOT_CALIBRATED` alongside the count.
   * #VERIFY: ReviewDetailPage.test.tsx "labels the spot check as
   * uncalibrated" asserts the caveat renders with the count.
   */
  requestedSize: number
}

/**
 * The working sample size: one sitting's worth of passages, not a derived
 * figure. See `requestedSize` for why this must stay labelled.
 */
export const DEFAULT_SAMPLE_SIZE = 15

/** The caveat every sample UI must show beside the count (ruling 2). */
export const SAMPLE_NOT_CALIBRATED = 'sample size not yet calibrated'

/**
 * Pick `count` items spread evenly across `items`, preserving order.
 *
 * Midpoint striding (`(i + 0.5) * len / count`) rather than endpoint striding
 * (`i * (len - 1) / (count - 1)`): the endpoint form always draws the first and
 * last item, which on a story graph means always drawing the start node and
 * always drawing the same final ending, and it divides by zero at count 1.
 */
function stride<T>(items: T[], count: number): T[] {
  if (count <= 0 || items.length === 0) return []
  if (count >= items.length) return [...items]
  const picked: T[] = []
  for (let i = 0; i < count; i += 1) {
    picked.push(items[Math.floor(((i + 0.5) * items.length) / count)])
  }
  return picked
}

/**
 * Draw the spot-check sample.
 *
 * @param nodes The read-through, in graph order (reachable first).
 * @param flaggedNodeIds Node ids any moderation finding names.
 * @param size How many passages to draw; defaults to `DEFAULT_SAMPLE_SIZE`.
 *
 * #ASSUME: data integrity: `nodes` arrives in the read-through's own order,
 * which is reachable-from-start first and then unreachable, so striding it
 * spreads the draw across the branch shape. Handing this function an
 * arbitrarily ordered node list still returns a valid sample, just not a
 * spread one.
 * #VERIFY: reviewSample.test.ts "spreads the draw across the read-through
 * rather than taking a prefix".
 */
export function buildReviewSample(
  nodes: StoryNodeView[],
  flaggedNodeIds: Set<string>,
  size: number = DEFAULT_SAMPLE_SIZE
): ReviewSample {
  const positioned = nodes.map((node, index) => ({
    id: node.id,
    body: node.body,
    hasFinding: flaggedNodeIds.has(node.id),
    position: index + 1,
  }))
  const unflagged = positioned.filter((node) => !node.hasFinding)
  const flagged = positioned.filter((node) => node.hasFinding)
  const drawn = stride(unflagged, size)
  // Top up from the flagged passages only once the unflagged ones run out, so
  // a heavily flagged book still yields a sample of the requested size rather
  // than a short one the reviewer cannot interpret. These passages are already
  // shown above with their findings; they are marked so the UI can say so.
  const toppedUp = drawn.length < size ? stride(flagged, size - drawn.length) : []
  return {
    nodes: [...drawn, ...toppedUp].sort((a, b) => a.position - b.position),
    totalPassages: positioned.length,
    unflaggedTotal: unflagged.length,
    requestedSize: size,
  }
}

/** The band context a reviewer needs to judge a passage they are reading. */
export interface SampleBandContext {
  ageBand: string | null
  readingLevel: string | null
}

/**
 * Read the band context from a Storybook blob's metadata.
 *
 * Deliberately only the two fields the story-overview panel does NOT already
 * show. Reproducing a band expectations table here would make the frontend a
 * second source of truth for backend policy, which is the defect `RS-A3` just
 * finished removing; the per-band thresholds themselves arrive server-side
 * with `RS-B1`/`RS-B2`.
 *
 * #ASSUME: data integrity: metadata is absent on a malformed or mid-fetch
 * blob, in which case both fields are null and the caller renders no context
 * line rather than an empty one that reads as "no band declared".
 * #VERIFY: reviewSample.test.ts "reads band context, and degrades to nulls on
 * a blob with no metadata".
 */
export function readSampleBandContext(blob: Record<string, unknown>): SampleBandContext {
  const raw = blob.metadata
  const metadata: Record<string, unknown> =
    typeof raw === 'object' && raw !== null && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {}
  const str = (value: unknown): string | null =>
    typeof value === 'string' && value !== '' ? value : null
  return {
    ageBand: str(metadata.age_band),
    readingLevel: str(metadata.reading_level),
  }
}
