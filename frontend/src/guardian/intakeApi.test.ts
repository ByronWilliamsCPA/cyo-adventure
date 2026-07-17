import { describe, expect, it, vi } from 'vitest'

import { buildBrief, formatRelativeTime, makeIntakeApi, statusPill } from './intakeApi'

function fakeAxios() {
  return { get: vi.fn(), post: vi.fn() }
}

describe('makeIntakeApi', () => {
  it('creates a concept via POST /v1/concepts', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { concept_id: 'c1' } })
    const brief = buildBrief({
      premise: 'A quiet garden adventure.',
      tone: 'gentle',
      ageBand: '5-8',
      readingLevelCap: 3,
    })
    const result = await makeIntakeApi(api as never).createConcept(brief)
    expect(api.post).toHaveBeenCalledWith('/v1/concepts', { brief })
    expect(result.concept_id).toBe('c1')
  })

  it('enqueues generation via POST /v1/concepts/:id/generate', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { job_id: 'j1', status: 'queued' } })
    const result = await makeIntakeApi(api as never).generate('c1')
    expect(api.post).toHaveBeenCalledWith('/v1/concepts/c1/generate')
    expect(result.job_id).toBe('j1')
  })

  it('lists jobs via GET /v1/generation-jobs', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({ data: { jobs: [{ id: 'j1' }] } })
    const result = await makeIntakeApi(api as never).listJobs()
    expect(api.get).toHaveBeenCalledWith('/v1/generation-jobs')
    expect(result).toEqual([{ id: 'j1' }])
  })
})

describe('buildBrief', () => {
  it('fills every required field with band-derived defaults', () => {
    const brief = buildBrief({
      premise: 'Into the tide pools.',
      tone: 'adventurous',
      ageBand: '8-11',
      readingLevelCap: 4,
    })
    expect(brief.tier).toBe(1)
    expect(brief.point_of_view).toBe('second')
    expect(brief.structure_pattern).toBe('branch_and_bottleneck')
    expect(brief.target_node_count).toBe(15)
    expect(brief.ending_count).toBe(3)
    expect(brief.protagonist.age).toBe(8)
    expect(brief.age_band).toBe('8-11')
    expect(brief.reading_level_target).toBe(4)
  })

  it('falls back to the band-default target when the cap is the 99 sentinel', () => {
    const brief = buildBrief({
      premise: 'Into the tide pools.',
      tone: 'adventurous',
      ageBand: '8-11',
      readingLevelCap: 99,
    })
    expect(brief.reading_level_target).toBe(4)
    const teen = buildBrief({
      premise: 'Into the tide pools.',
      tone: 'adventurous',
      ageBand: '13-16',
      readingLevelCap: 99,
    })
    expect(teen.reading_level_target).toBe(8)
  })

  it('never puts a child display name into the brief', () => {
    const brief = buildBrief({
      premise: 'A trip to the market.',
      tone: 'silly',
      ageBand: '3-5',
      readingLevelCap: 1,
      childDisplayName: 'Reader A',
    })
    expect(JSON.stringify(brief)).not.toContain('Reader A')
    expect(brief.protagonist.name).toBe('Explorer')
  })

  it('uses an overridden protagonist name when the guardian provides one', () => {
    const brief = buildBrief({
      premise: 'A trip to the market.',
      tone: 'silly',
      ageBand: '3-5',
      readingLevelCap: 1,
      protagonistName: 'Captain Rosa',
    })
    expect(brief.protagonist.name).toBe('Captain Rosa')
  })

  // G2: the selected child's banned_themes flow into content_nogo.
  it('folds bannedThemes into content_nogo when provided', () => {
    const brief = buildBrief({
      premise: 'Into the tide pools.',
      tone: 'adventurous',
      ageBand: '8-11',
      readingLevelCap: 4,
      bannedThemes: ['spiders', 'magic'],
    })
    expect(brief.content_nogo).toEqual(['spiders', 'magic'])
  })

  it('defaults content_nogo to an empty list when bannedThemes is omitted', () => {
    const brief = buildBrief({
      premise: 'Into the tide pools.',
      tone: 'adventurous',
      ageBand: '8-11',
      readingLevelCap: 4,
    })
    expect(brief.content_nogo).toEqual([])
  })
})

describe('formatRelativeTime', () => {
  const NOW = Date.parse('2026-07-04T12:00:00Z')

  it('renders minute granularity with singular/plural forms', () => {
    expect(formatRelativeTime('2026-07-04T11:56:00Z', NOW)).toBe('4 minutes ago')
    expect(formatRelativeTime('2026-07-04T11:59:00Z', NOW)).toBe('1 minute ago')
    expect(formatRelativeTime('2026-07-04T11:01:00Z', NOW)).toBe('59 minutes ago')
  })

  it('renders sub-minute ages as just now', () => {
    expect(formatRelativeTime('2026-07-04T11:59:30Z', NOW)).toBe('just now')
    expect(formatRelativeTime('2026-07-04T12:00:00Z', NOW)).toBe('just now')
  })

  it('clamps a future timestamp (client clock behind server) to just now', () => {
    expect(formatRelativeTime('2026-07-04T12:05:00Z', NOW)).toBe('just now')
  })

  it('renders hour granularity between one hour and one day', () => {
    expect(formatRelativeTime('2026-07-04T11:00:00Z', NOW)).toBe('1 hour ago')
    expect(formatRelativeTime('2026-07-04T01:00:00Z', NOW)).toBe('11 hours ago')
    expect(formatRelativeTime('2026-07-03T12:30:00Z', NOW)).toBe('23 hours ago')
  })

  it('renders day granularity beyond 24 hours', () => {
    expect(formatRelativeTime('2026-07-03T11:00:00Z', NOW)).toBe('1 day ago')
    expect(formatRelativeTime('2026-06-30T12:00:00Z', NOW)).toBe('4 days ago')
  })

  it('returns null for an unparseable timestamp', () => {
    expect(formatRelativeTime('not-a-date', NOW)).toBeNull()
  })
})

describe('statusPill', () => {
  it('maps queued/running to Generating', () => {
    expect(
      statusPill({ status: 'queued', storybook_id: null, storybook_status: null })
    ).toBe('Generating')
    expect(
      statusPill({ status: 'running', storybook_id: null, storybook_status: null })
    ).toBe('Generating')
  })

  it('maps a published storybook to Approved', () => {
    expect(
      statusPill({ status: 'passed', storybook_id: 's1', storybook_status: 'published' })
    ).toBe('Approved')
  })

  it('maps failed to Failed', () => {
    expect(
      statusPill({ status: 'failed', storybook_id: null, storybook_status: null })
    ).toBe('Failed')
  })

  it('maps a gate-failed needs_review (no storybook) to Failed', () => {
    expect(
      statusPill({ status: 'needs_review', storybook_id: null, storybook_status: null })
    ).toBe('Failed')
  })

  it('maps review-pending states to Waiting for review', () => {
    expect(
      statusPill({ status: 'passed', storybook_id: 's1', storybook_status: 'in_review' })
    ).toBe('Waiting for review')
    // Future-proofing: needs_review WITH a storybook stays review-pending.
    expect(
      statusPill({
        status: 'needs_review',
        storybook_id: 's2',
        storybook_status: 'needs_revision',
      })
    ).toBe('Waiting for review')
  })

  it('maps an archived (published-then-pulled) storybook to Archived', () => {
    // A terminal state: it must not fall through to the "Waiting for review"
    // default, which would read as though the story were still pending.
    expect(
      statusPill({ status: 'passed', storybook_id: 's1', storybook_status: 'archived' })
    ).toBe('Archived')
  })
})
