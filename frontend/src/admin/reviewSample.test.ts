import { describe, expect, it } from 'vitest'

import type { StoryNodeView } from '../guardian/storyReadThrough'
import { DEFAULT_SAMPLE_SIZE, buildReviewSample, readSampleBandContext } from './reviewSample'

const node = (id: string): StoryNodeView => ({
  blobIndex: Number(id.replace('n', '')),
  id,
  body: `Body of ${id}.`,
  choices: [],
  isEnding: false,
  ending: null,
})

const nodes = (count: number): StoryNodeView[] =>
  Array.from({ length: count }, (_, index) => node(`n${index + 1}`))

describe('buildReviewSample', () => {
  it('spreads the draw across the read-through rather than taking a prefix', () => {
    // The defect this replaces: "read the book" on a 250-passage story, where
    // any bounded prefix samples one region of the graph.
    const sample = buildReviewSample(nodes(100), new Set(), 10)
    const positions = sample.nodes.map((n) => n.position)
    expect(positions).toHaveLength(10)
    // Every decile is represented, which a prefix cannot do.
    expect(positions[0]).toBeLessThan(10)
    expect(positions[9]).toBeGreaterThan(90)
    // And the draw is monotonic with no repeats, so the reviewer reads forward.
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
    expect(new Set(positions).size).toBe(10)
  })

  it('draws only unflagged passages while enough of them exist', () => {
    // The whole value of the sample is the regions the gate said nothing
    // about; a flagged passage is already rendered above with its finding.
    const flagged = new Set(['n2', 'n4', 'n6', 'n8'])
    const sample = buildReviewSample(nodes(20), flagged, 5)
    expect(sample.nodes.every((n) => !n.hasFinding)).toBe(true)
    expect(sample.nodes.map((n) => n.id)).not.toContain('n2')
    expect(sample.unflaggedTotal).toBe(16)
    expect(sample.totalPassages).toBe(20)
  })

  it('tops up from flagged passages only when the unflagged run out', () => {
    // A heavily flagged book must still yield a readable sample; a short one
    // leaves the reviewer unable to tell "few unflagged" from "sampling broke".
    const flagged = new Set(['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7'])
    const sample = buildReviewSample(nodes(10), flagged, 6)
    expect(sample.nodes).toHaveLength(6)
    expect(sample.nodes.filter((n) => !n.hasFinding)).toHaveLength(3)
    expect(sample.nodes.filter((n) => n.hasFinding)).toHaveLength(3)
  })

  it('is deterministic: the same book draws the same sample every time', () => {
    // No seeded RNG. A reviewer who returns to a part-read book must see the
    // passages they were working through, and a second reviewer must be
    // answerable about the same ones.
    const first = buildReviewSample(nodes(60), new Set(['n5']))
    const second = buildReviewSample(nodes(60), new Set(['n5']))
    expect(first.nodes.map((n) => n.id)).toEqual(second.nodes.map((n) => n.id))
    expect(first.nodes).toHaveLength(DEFAULT_SAMPLE_SIZE)
  })

  it('returns every passage when the book is smaller than the sample', () => {
    const sample = buildReviewSample(nodes(4), new Set())
    expect(sample.nodes.map((n) => n.id)).toEqual(['n1', 'n2', 'n3', 'n4'])
    expect(sample.totalPassages).toBe(4)
  })

  it('returns an empty sample for an empty read-through, and does not throw', () => {
    const sample = buildReviewSample([], new Set())
    expect(sample.nodes).toEqual([])
    expect(sample.totalPassages).toBe(0)
    expect(sample.unflaggedTotal).toBe(0)
  })
})

describe('readSampleBandContext', () => {
  it('reads band context, and degrades to nulls on a blob with no metadata', () => {
    expect(
      readSampleBandContext({ metadata: { age_band: '8-11', reading_level: 'grade_3' } })
    ).toEqual({ ageBand: '8-11', readingLevel: 'grade_3' })
    expect(readSampleBandContext({})).toEqual({ ageBand: null, readingLevel: null })
    // A non-object metadata (a malformed blob) must not throw or half-read.
    expect(readSampleBandContext({ metadata: 'nope' })).toEqual({
      ageBand: null,
      readingLevel: null,
    })
    // An empty string is a missing value, not a band called "".
    expect(readSampleBandContext({ metadata: { age_band: '' } })).toEqual({
      ageBand: null,
      readingLevel: null,
    })
  })
})
