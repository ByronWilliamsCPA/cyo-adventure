import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeAuthoringPlanApi } from './authoringPlanApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  return { api: { get, post } as unknown as AxiosInstance, get, post }
}

describe('makeAuthoringPlanApi', () => {
  it('listApproved fetches approved requests', async () => {
    const requests = [{ id: 'req-1', status: 'approved' }]
    const { api, get } = fakeAxios({ requests })
    const result = await makeAuthoringPlanApi(api).listApproved()
    expect(get).toHaveBeenCalledWith('/v1/admin/story-requests?status=approved')
    expect(result).toEqual(requests)
  })

  it('createPlan posts the chosen method/mechanism/model', async () => {
    const response = {
      request_id: 'req-1',
      concept_id: 'c1',
      job_id: 'job-1',
      method: 'skeleton_fill',
      mechanism: 'automated_provider',
      status: 'queued',
      skeleton_slug: null,
      skeleton_alternatives: [],
      warnings: [],
    }
    const { api, post } = fakeAxios(response)
    const body = {
      method: 'skeleton_fill' as const,
      mechanism: 'automated_provider' as const,
      prep_model: 'claude-sonnet-4-6',
      provider: 'anthropic' as const,
      model: 'claude-sonnet-4-6',
    }
    const result = await makeAuthoringPlanApi(api).createPlan('req-1', body)
    expect(post).toHaveBeenCalledWith('/v1/story-requests/req-1/authoring-plan', body)
    expect(result).toEqual(response)
  })
})
