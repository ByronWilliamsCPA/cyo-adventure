import { describe, expect, it } from 'vitest'

import {
  affectedPassagesLabel,
  distinctFindingsLabel,
  queueItemCounts,
  surfaceCounts,
  surfacePopulation,
  tierBreakdownLabel,
  verdictTally,
} from './findingCounts'
import type { FindingView, ReviewQueueItem, ReviewSurface } from './reviewApi'

const finding = (over: Partial<FindingView> = {}): FindingView => ({
  stage: 2,
  source: 'llm_safety',
  category: 'safety',
  node_id: 'n1',
  verdict: 'flag',
  score: 0.5,
  message: 'possibly scary',
  ...over,
})

const surface = (over: Partial<ReviewSurface> = {}): ReviewSurface => ({
  storybook_id: 'sb1',
  version: 1,
  status: 'in_review',
  blob: {},
  screened: true,
  summary: null,
  flagged_passages: [],
  story_level_findings: [],
  ...over,
})

const queueItem = (over: Partial<ReviewQueueItem> = {}): ReviewQueueItem => ({
  storybook_id: 'sb1',
  title: 'The Teddy Bears’ Picnic',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 0,
  summary: null,
  ...over,
})

describe('verdictTally', () => {
  it('counts each verdict into its own tier and ignores passes', () => {
    const tally = verdictTally([
      { verdict: 'block' },
      { verdict: 'flag' },
      { verdict: 'flag' },
      { verdict: 'advisory' },
      { verdict: 'advisory' },
      { verdict: 'advisory' },
      { verdict: 'pass' },
    ])
    expect(tally).toEqual({ block: 1, flag: 2, advisory: 3 })
  })

  it('excludes structural findings from the flag tier only, matching the backend', () => {
    // The exclusion is verdict-scoped on purpose: the backend drops structural
    // rows from flag_findings and from nothing else, so a structural block
    // still gates. A tally that dropped structural rows wholesale, or kept
    // them in the flag tier, disagrees with the queue badge by exactly the
    // number of structural rows.
    const tally = verdictTally([
      { verdict: 'flag', structural: true },
      { verdict: 'flag', structural: false },
      { verdict: 'flag' },
      { verdict: 'block', structural: true },
      { verdict: 'advisory', structural: true },
    ])
    expect(tally).toEqual({ block: 1, flag: 2, advisory: 1 })
  })

  it('counts nothing for an empty population', () => {
    expect(verdictTally([])).toEqual({ block: 0, flag: 0, advisory: 0 })
  })
})

describe('surfacePopulation', () => {
  it('unions the three merged buckets and ignores the fan-out when any is present', () => {
    // The fan-out (flagged_passages x findings) is the SAME findings, so
    // including it alongside the merged buckets is the over-count this module
    // exists to remove: one merged finding covering three nodes would count
    // four times.
    const ranked = finding({ message: 'ranked' })
    const structural = finding({ message: 'structural', structural: true })
    const low = finding({ message: 'low', verdict: 'advisory' })
    const population = surfacePopulation(
      surface({
        ranked_findings: [ranked],
        structural_findings: [structural],
        low_advisory_findings: [low],
        flagged_passages: [{ node_id: 'n1', prose: 'p', findings: [ranked, ranked, ranked] }],
        story_level_findings: [finding({ message: 'story level' })],
      })
    )
    expect(population).toEqual([ranked, structural, low])
  })

  it('still returns the merged set when only one of the three buckets is filled', () => {
    const low = finding({ verdict: 'advisory', message: 'low only' })
    expect(surfacePopulation(surface({ low_advisory_findings: [low] }))).toEqual([low])
  })

  it('falls back to the fan-out plus story-level findings on a legacy report', () => {
    // A pre-Stage-B stored report projects all three merged buckets empty
    // while the fan-out still carries findings; falling through to nothing
    // would tell a reviewer a flagged book is clean.
    const fanned = finding({ message: 'fanned' })
    const storyLevel = finding({ message: 'story level', node_id: null })
    const population = surfacePopulation(
      surface({
        ranked_findings: [],
        structural_findings: [],
        low_advisory_findings: [],
        flagged_passages: [
          { node_id: 'n1', prose: 'p1', findings: [fanned] },
          { node_id: 'n2', prose: 'p2', findings: [fanned] },
        ],
        story_level_findings: [storyLevel],
      })
    )
    expect(population).toEqual([fanned, fanned, storyLevel])
  })

  it('returns nothing for a surface with no findings anywhere', () => {
    expect(surfacePopulation(surface())).toEqual([])
  })
})

describe('surfaceCounts', () => {
  it('names each denominator from its own population', () => {
    const counts = surfaceCounts(
      surface({
        ranked_findings: [finding({ verdict: 'block' }), finding({ verdict: 'flag' })],
        structural_findings: [finding({ verdict: 'flag', structural: true })],
        low_advisory_findings: [finding({ verdict: 'advisory' }), finding({ verdict: 'advisory' })],
        flagged_passages: [
          { node_id: 'n1', prose: 'p1', findings: [] },
          { node_id: 'n2', prose: 'p2', findings: [] },
          { node_id: 'n3', prose: 'p3', findings: [] },
        ],
      })
    )
    expect(counts).toEqual({
      // Five merged findings, three rendered passage cards: the two numbers
      // disagreeing is the normal case, which is why both are named.
      distinct: 5,
      affectedPassages: 3,
      lowAdvisory: 2,
      block: 1,
      // The structural flag is excluded here for the same reason as in
      // verdictTally, so this is 1 and not 2.
      flag: 1,
      advisory: 2,
    })
  })

  it('counts only the collapsed bucket as lowAdvisory, not every advisory', () => {
    // `RS-A1` collapses a SUBSET of advisories out of the default view. An
    // advisory ranked into the main list is not collapsed, so a lowAdvisory
    // equal to the advisory tier would promise a reviewer a longer collapsed
    // section than the page renders.
    const counts = surfaceCounts(
      surface({
        ranked_findings: [finding({ verdict: 'advisory' })],
        low_advisory_findings: [finding({ verdict: 'advisory' })],
      })
    )
    expect(counts.advisory).toBe(2)
    expect(counts.lowAdvisory).toBe(1)
  })

  it('reports no low advisories when the backend never sent the field', () => {
    expect(surfaceCounts(surface()).lowAdvisory).toBe(0)
  })

  it('counts the legacy fan-out as occurrences rather than reporting zero', () => {
    const counts = surfaceCounts(
      surface({
        flagged_passages: [
          { node_id: 'n1', prose: 'p1', findings: [finding({ verdict: 'flag' })] },
          { node_id: 'n2', prose: 'p2', findings: [finding({ verdict: 'flag' })] },
        ],
      })
    )
    expect(counts.distinct).toBe(2)
    expect(counts.affectedPassages).toBe(2)
    expect(counts.flag).toBe(2)
  })
})

describe('queueItemCounts', () => {
  it('sums the three tiers into the distinct count', () => {
    const counts = queueItemCounts(
      queueItem({ block_findings: 1, flag_findings: 2, advisory_findings: 3, flagged_count: 99 })
    )
    // 6, not the payload's own flagged_count: the tiered fields are the
    // distinct population and flagged_count is the occurrence one.
    expect(counts).toEqual({
      distinct: 6,
      affectedPassages: 0,
      lowAdvisory: 0,
      block: 1,
      flag: 2,
      advisory: 3,
    })
  })

  it('prefers a tiered total of exactly one over flagged_count', () => {
    // The boundary the fallback turns on: one tiered finding must NOT be read
    // as "no tiered fields", which is what a `tiered > 1` or `tiered >= 0`
    // test would do.
    const counts = queueItemCounts(
      queueItem({ block_findings: 1, flag_findings: 0, advisory_findings: 0, flagged_count: 42 })
    )
    expect(counts.distinct).toBe(1)
  })

  it('falls back to flagged_count when all three tiers are zero', () => {
    const counts = queueItemCounts(
      queueItem({ block_findings: 0, flag_findings: 0, advisory_findings: 0, flagged_count: 42 })
    )
    expect(counts.distinct).toBe(42)
  })

  it('falls back to flagged_count when the tiered fields are absent (older payload)', () => {
    const counts = queueItemCounts(queueItem({ flagged_count: 7 }))
    expect(counts).toEqual({
      distinct: 7,
      affectedPassages: 0,
      lowAdvisory: 0,
      block: 0,
      flag: 0,
      advisory: 0,
    })
  })

  it('reports zero on a clean row rather than inventing a finding', () => {
    expect(queueItemCounts(queueItem({ flagged_count: 0 })).distinct).toBe(0)
  })
})

describe('distinctFindingsLabel', () => {
  it('states the noun and pluralizes it', () => {
    expect(distinctFindingsLabel(surfaceCounts(surface()))).toBe('0 findings')
    expect(distinctFindingsLabel(queueItemCounts(queueItem({ flagged_count: 1 })))).toBe(
      '1 finding'
    )
    expect(distinctFindingsLabel(queueItemCounts(queueItem({ flagged_count: 4 })))).toBe(
      '4 findings'
    )
  })
})

describe('affectedPassagesLabel', () => {
  const withPassages = (count: number) =>
    surfaceCounts(
      surface({
        flagged_passages: Array.from({ length: count }, (_unused, index) => ({
          node_id: `n${index}`,
          prose: 'p',
          findings: [],
        })),
      })
    )

  it('returns null rather than "0 flagged passages below" when there are none', () => {
    // Null is the contract, not an empty string: the caller renders the whole
    // element conditionally, and "0 flagged passages below" beside a distinct
    // count reads as a contradiction.
    expect(affectedPassagesLabel(withPassages(0))).toBeNull()
  })

  it('names the passage cards on the page, singular and plural', () => {
    expect(affectedPassagesLabel(withPassages(1))).toBe('1 flagged passage below')
    expect(affectedPassagesLabel(withPassages(3))).toBe('3 flagged passages below')
  })
})

describe('tierBreakdownLabel', () => {
  it('returns null when nothing is counted', () => {
    expect(tierBreakdownLabel({ block: 0, flag: 0, advisory: 0 })).toBeNull()
  })

  it('lists every non-zero tier in block/flag/advisory order, middot separated', () => {
    expect(tierBreakdownLabel({ block: 1, flag: 2, advisory: 3 })).toBe(
      '1 block · 2 flags · 3 advisories'
    )
  })

  it('omits a zero tier instead of printing it', () => {
    expect(tierBreakdownLabel({ block: 0, flag: 2, advisory: 0 })).toBe('2 flags')
    expect(tierBreakdownLabel({ block: 3, flag: 0, advisory: 1 })).toBe('3 blocks · 1 advisory')
  })

  it('pluralizes advisory irregularly rather than as "advisorys"', () => {
    expect(tierBreakdownLabel({ block: 0, flag: 0, advisory: 2 })).toBe('2 advisories')
  })
})
