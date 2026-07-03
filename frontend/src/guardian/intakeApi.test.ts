import { describe, expect, it, vi } from 'vitest'

import { buildBrief, makeIntakeApi, statusPill } from './intakeApi'

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
})
