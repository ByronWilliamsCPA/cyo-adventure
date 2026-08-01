import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeKidStoryRequestApi } from './storyRequestApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  return { api: { get, post } as unknown as AxiosInstance, get, post }
}

describe('makeKidStoryRequestApi', () => {
  it('create posts a story request and returns id, status, and proposedSeriesTitle', async () => {
    const { api, post } = fakeAxios({ id: 'req1', status: 'pending' })
    const result = await makeKidStoryRequestApi(api).create('p1', 'Please write a dragon story')
    expect(post).toHaveBeenCalledWith('/v1/story-requests', {
      profile_id: 'p1',
      request_text: 'Please write a dragon story',
    })
    expect(result).toEqual({
      id: 'req1',
      status: 'pending',
      proposedSeriesTitle: null,
      resultingStorybookId: null,
      kidSummary: null,
    })
  })

  it('create maps proposed_series_title from the wire response (K12)', async () => {
    const { api } = fakeAxios({
      id: 'req1',
      status: 'pending',
      proposed_series_title: 'The Cupcake Chronicles',
    })
    const result = await makeKidStoryRequestApi(api).create('p1', 'A dragon who loves cupcakes')
    expect(result.proposedSeriesTitle).toBe('The Cupcake Chronicles')
  })

  it('create strips guardian-facing fields from the full wire response', async () => {
    // The create endpoint returns the same full row shape as the list endpoint;
    // the adapter must strip it at runtime, not just hide it behind a type cast.
    const { api } = fakeAxios({
      id: 'req1',
      status: 'pending',
      profile_id: 'p1',
      request_text: 'Please write a dragon story',
      created_at: '2026-07-04T12:00:00Z',
      moderation_flags: [{ category: 'language', verdict: 'clean', message: '' }],
    })
    const result = await makeKidStoryRequestApi(api).create('p1', 'Please write a dragon story')
    // Returned object carries ONLY the kid-safe keys: id, status, the child's
    // own request_text (UX-K3), the proposed series title (K12), and the
    // resulting storybook id (W0.4). Guardian-facing fields (created_at,
    // moderation_flags, profile_id) are stripped.
    expect(Object.keys(result).sort()).toEqual([
      'id',
      'kidSummary',
      'proposedSeriesTitle',
      'request_text',
      'resultingStorybookId',
      'status',
    ])
    expect(result).toEqual({
      id: 'req1',
      status: 'pending',
      request_text: 'Please write a dragon story',
      proposedSeriesTitle: null,
      resultingStorybookId: null,
      kidSummary: null,
    })
  })

  it('listForProfile gets the requests for a profile and returns the list', async () => {
    const { api, get } = fakeAxios({
      requests: [
        { id: 'req1', status: 'pending' },
        { id: 'req2', status: 'approved' },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(get).toHaveBeenCalledWith('/v1/story-requests?profile_id=p1')
    expect(result).toEqual([
      {
        id: 'req1',
        status: 'pending',
        proposedSeriesTitle: null,
        resultingStorybookId: null,
        kidSummary: null,
      },
      {
        id: 'req2',
        status: 'approved',
        proposedSeriesTitle: null,
        resultingStorybookId: null,
        kidSummary: null,
      },
    ])
  })

  it('listForProfile handles an empty request list', async () => {
    const { api, get } = fakeAxios({ requests: [] })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(get).toHaveBeenCalledWith('/v1/story-requests?profile_id=p1')
    expect(result).toEqual([])
  })

  it('create handles declined status', async () => {
    const { api } = fakeAxios({ id: 'req3', status: 'declined' })
    const result = await makeKidStoryRequestApi(api).create('p2', 'Another story idea')
    expect(result.status).toBe('declined')
  })

  it('listForProfile includes all possible statuses', async () => {
    const { api } = fakeAxios({
      requests: [
        { id: 'req1', status: 'pending' },
        { id: 'req2', status: 'approved' },
        { id: 'req3', status: 'declined' },
        { id: 'req4', status: 'blocked' },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(result).toHaveLength(4)
    expect(result.map((r) => r.status)).toEqual(['pending', 'approved', 'declined', 'blocked'])
  })

  it('listForProfile maps proposed_series_title per row (K12)', async () => {
    const { api } = fakeAxios({
      requests: [
        { id: 'req1', status: 'approved', proposed_series_title: 'Fox Tales' },
        { id: 'req2', status: 'approved', proposed_series_title: null },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(result.map((r) => r.proposedSeriesTitle)).toEqual(['Fox Tales', null])
  })

  it('listForProfile maps resulting_storybook_id per row (W0.4)', async () => {
    const { api } = fakeAxios({
      requests: [
        { id: 'req1', status: 'approved', resulting_storybook_id: 's_fox_tales' },
        { id: 'req2', status: 'approved', resulting_storybook_id: null },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(result.map((r) => r.resultingStorybookId)).toEqual(['s_fox_tales', null])
  })

  it('listForProfile strips guardian-facing fields from full wire response', async () => {
    // Realistic full wire fixture with all backend fields
    const { api } = fakeAxios({
      requests: [
        {
          id: 'req1',
          status: 'pending',
          profile_id: 'p1',
          request_text: 'Please write a dragon story',
          created_at: '2026-07-04T12:00:00Z',
          moderation_flags: [{ category: 'language', verdict: 'clean', message: '' }],
        },
        {
          id: 'req2',
          status: 'approved',
          profile_id: 'p1',
          request_text: 'Can you make a wizard adventure',
          created_at: '2026-07-04T12:15:00Z',
          moderation_flags: [],
        },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    // Returned objects contain ONLY the kid-safe keys: id, status, request_text
    // (UX-K3), proposedSeriesTitle (K12), and resultingStorybookId (W0.4).
    // Guardian-facing fields (profile_id, created_at, moderation_flags) are
    // stripped.
    expect(result).toHaveLength(2)
    expect(Object.keys(result[0]).sort()).toEqual([
      'id',
      'kidSummary',
      'proposedSeriesTitle',
      'request_text',
      'resultingStorybookId',
      'status',
    ])
    expect(Object.keys(result[1]).sort()).toEqual([
      'id',
      'kidSummary',
      'proposedSeriesTitle',
      'request_text',
      'resultingStorybookId',
      'status',
    ])
    expect(result[0]).toEqual({
      id: 'req1',
      status: 'pending',
      request_text: 'Please write a dragon story',
      proposedSeriesTitle: null,
      resultingStorybookId: null,
      kidSummary: null,
    })
    expect(result[1]).toEqual({
      id: 'req2',
      status: 'approved',
      request_text: 'Can you make a wizard adventure',
      proposedSeriesTitle: null,
      resultingStorybookId: null,
      kidSummary: null,
    })
  })

  it('create maps interpretation.kid_summary as kidSummary (K19 reflect-back)', async () => {
    const { api } = fakeAxios({
      id: 'req1',
      status: 'pending',
      interpretation: {
        kid_summary: 'We built in 1 of your ideas.',
        guardian_summary: "Skeleton 'the-cave-of-echoes': 1 built_in.",
        elements: [
          {
            element: 'a dragon',
            disposition: 'built_in',
            reason: 'bound_to_slot',
            kid_text: 'Yay! Your story has a dragon in it!',
            guardian_text: "'a dragon' was built into the story (slot HERO_COMPANION).",
          },
        ],
      },
    })
    const result = await makeKidStoryRequestApi(api).create('p1', 'A dragon story')
    // Only kid_summary is surfaced; guardian_summary and every element's
    // guardian_text/kid_text/element phrase are dropped at this boundary.
    expect(result.kidSummary).toBe('We built in 1 of your ideas.')
    expect(Object.keys(result)).not.toContain('elements')
    expect(Object.keys(result)).not.toContain('guardianSummary')
  })

  it('listForProfile maps interpretation.kid_summary per row, null when absent', async () => {
    const { api } = fakeAxios({
      requests: [
        {
          id: 'req1',
          status: 'pending',
          interpretation: { kid_summary: 'We are getting your adventure ready!' },
        },
        { id: 'req2', status: 'declined' },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(result.map((r) => r.kidSummary)).toEqual([
      'We are getting your adventure ready!',
      null,
    ])
  })
})
