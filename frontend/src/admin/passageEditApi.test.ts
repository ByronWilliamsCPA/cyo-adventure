import { describe, expect, it, vi } from 'vitest'

import { asGateFailure, makePassageEditApi } from './passageEditApi'

function fakeAxios() {
  return {
    patch: vi.fn(),
  }
}

describe('makePassageEditApi', () => {
  it('edits a node via PATCH /v1/storybooks/:id/versions/:v/nodes/:nodeId', async () => {
    const api = fakeAxios()
    api.patch.mockResolvedValue({ data: { storybook_id: 's1', version: 1 } })
    const result = await makePassageEditApi(api as never).editNode('s1', 1, 'n1', {
      body: 'New prose.',
    })
    expect(api.patch).toHaveBeenCalledWith('/v1/storybooks/s1/versions/1/nodes/n1', {
      body: 'New prose.',
    })
    expect(result).toEqual({ storybook_id: 's1', version: 1 })
  })

  it('sends choice_labels alongside body when both are supplied', async () => {
    const api = fakeAxios()
    api.patch.mockResolvedValue({ data: {} })
    await makePassageEditApi(api as never).editNode('s1', 2, 'n1', {
      body: 'New prose.',
      choice_labels: { c1: 'New label' },
    })
    expect(api.patch).toHaveBeenCalledWith('/v1/storybooks/s1/versions/2/nodes/n1', {
      body: 'New prose.',
      choice_labels: { c1: 'New label' },
    })
  })

  it('URL-encodes a node id that needs it', async () => {
    const api = fakeAxios()
    api.patch.mockResolvedValue({ data: {} })
    await makePassageEditApi(api as never).editNode('s1', 1, 'n one/two', { body: 'x' })
    expect(api.patch).toHaveBeenCalledWith(
      '/v1/storybooks/s1/versions/1/nodes/n%20one%2Ftwo',
      { body: 'x' }
    )
  })
})

describe('asGateFailure', () => {
  it('extracts findings from a 422 gate-failure body', () => {
    const err = {
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          message: 'edited passage failed the validation gate',
          details: {
            findings: [
              {
                rule_id: 'L1-7',
                severity: 'error',
                story_id: 's1',
                node_id: null,
                choice_id: null,
                message: 'node/word budget exceeded',
              },
            ],
          },
        },
      },
    }
    const result = asGateFailure(err)
    expect(result).not.toBeNull()
    expect(result?.message).toBe('edited passage failed the validation gate')
    expect(result?.findings).toHaveLength(1)
    expect(result?.findings[0]?.rule_id).toBe('L1-7')
  })

  it('returns null for a non-422 error', () => {
    const err = { isAxiosError: true, response: { status: 500, data: {} } }
    expect(asGateFailure(err)).toBeNull()
  })

  it('returns null for a 422 with no details.findings (e.g. FastAPI request-body validation)', () => {
    const err = {
      isAxiosError: true,
      response: { status: 422, data: { detail: [{ type: 'missing', loc: ['body'] }] } },
    }
    expect(asGateFailure(err)).toBeNull()
  })

  it('returns null for a non-axios error', () => {
    expect(asGateFailure(new Error('boom'))).toBeNull()
  })
})
