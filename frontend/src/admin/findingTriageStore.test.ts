import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { FindingView } from '../guardian/reviewApi'
import { findingKey, readReviewedKeys, toggleReviewed } from './findingTriageStore'

const finding = (over: Partial<FindingView> = {}): FindingView => ({
  stage: 1,
  source: 'llm_safety',
  category: 'safety',
  node_id: 'n1',
  verdict: 'flag',
  score: 0.5,
  message: 'possibly scary',
  severity: 'high',
  ...over,
})

describe('findingKey', () => {
  it('keys two identical findings the same and any differing field apart', () => {
    // There is no stable finding id in the persisted report, so the key is
    // content-derived. A refetch of the same report must reproduce it.
    expect(findingKey(finding())).toBe(findingKey(finding()))
    expect(findingKey(finding({ message: 'other' }))).not.toBe(findingKey(finding()))
    expect(findingKey(finding({ node_id: 'n2' }))).not.toBe(findingKey(finding()))
    expect(findingKey(finding({ verdict: 'advisory' }))).not.toBe(findingKey(finding()))
    expect(findingKey(finding({ severity: 'low' }))).not.toBe(findingKey(finding()))
    expect(findingKey(finding({ stage: 2 }))).not.toBe(findingKey(finding()))
    expect(findingKey(finding({ source: 'validator' }))).not.toBe(findingKey(finding()))
    expect(findingKey(finding({ category: 'peril' }))).not.toBe(findingKey(finding()))
  })

  it('does not key on the score, so a rescore keeps the reviewer marker', () => {
    // A finding whose score moved is the same finding; losing its marker on
    // every rescore would make the progress tracker useless.
    expect(findingKey(finding({ score: 0.91 }))).toBe(findingKey(finding({ score: null })))
  })

  it('distinguishes an absent severity or node from an empty one without colliding', () => {
    // '' is the encoding for absent; a finding whose node_id is genuinely ''
    // is not producible by the backend (node ids are non-empty), so the only
    // requirement is that absent fields do not throw or collide across kinds.
    expect(findingKey(finding({ severity: null, node_id: null }))).toBe(
      findingKey(finding({ severity: undefined, node_id: null }))
    )
    expect(findingKey(finding({ severity: null }))).not.toBe(findingKey(finding({ node_id: null })))
  })
})

describe('reviewed marker storage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  // Unconditional, not a restore at the end of the one test that spies: the
  // storage spies below patch Storage.prototype, which every later test in
  // this file shares. Restoring only on the success path meant a single failed
  // assertion left getItem/setItem throwing for the rest of the run, burying
  // the real failure under a cascade of unrelated ones.
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('round-trips markers per book version', () => {
    const key = findingKey(finding())
    expect(readReviewedKeys('s1', 1)).toEqual(new Set())
    const next = toggleReviewed('s1', 1, key, new Set())
    expect(next.has(key)).toBe(true)
    expect(readReviewedKeys('s1', 1)).toEqual(new Set([key]))
    // Scoped to the version: v2 of the same book is a different report.
    expect(readReviewedKeys('s1', 2)).toEqual(new Set())
    expect(readReviewedKeys('s2', 1)).toEqual(new Set())
  })

  it('toggles off, and returns a new set rather than mutating', () => {
    const key = findingKey(finding())
    const first = new Set<string>()
    const marked = toggleReviewed('s1', 1, key, first)
    expect(first.size).toBe(0)
    const unmarked = toggleReviewed('s1', 1, key, marked)
    expect(unmarked.has(key)).toBe(false)
    expect(readReviewedKeys('s1', 1)).toEqual(new Set())
  })

  it('treats a corrupted or foreign stored value as nothing marked', () => {
    localStorage.setItem('cyo:review:triage:s1:1', 'not json')
    expect(readReviewedKeys('s1', 1)).toEqual(new Set())
    localStorage.setItem('cyo:review:triage:s1:1', '{"reviewed":["a"]}')
    expect(readReviewedKeys('s1', 1)).toEqual(new Set())
    localStorage.setItem('cyo:review:triage:s1:1', '[1,2,"c"]')
    expect(readReviewedKeys('s1', 1)).toEqual(new Set(['c']))
  })

  it('degrades to empty when storage throws, rather than breaking the review page', () => {
    // A reviewer in private browsing or a locked-down profile must still be
    // able to review; a progress marker is never worth an unusable page.
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(readReviewedKeys('s1', 1)).toEqual(new Set())
    const key = findingKey(finding())
    expect(toggleReviewed('s1', 1, key, new Set()).has(key)).toBe(true)
  })
})
