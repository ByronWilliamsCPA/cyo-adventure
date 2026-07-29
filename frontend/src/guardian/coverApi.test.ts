import { describe, expect, it, vi } from 'vitest'
import { makeCoverApi } from './coverApi'

describe('coverApi', () => {
  it('POSTs to the versioned cover endpoint', async () => {
    const post = vi
      .fn()
      .mockResolvedValue({ data: { cover_status: 'generating', cover_url: null } })
    const get = vi.fn()
    const api = makeCoverApi({ post, get } as never)
    const res = await api.generate('s1', 2)
    expect(post).toHaveBeenCalledWith('/v1/storybooks/s1/versions/2/cover')
    expect(res.cover_status).toBe('generating')
  })

  it('GETs the cover status', async () => {
    const get = vi.fn().mockResolvedValue({ data: { cover_status: 'ready', cover_url: 'u' } })
    const api = makeCoverApi({ post: vi.fn(), get } as never)
    const res = await api.status('s1', 2)
    expect(get).toHaveBeenCalledWith('/v1/storybooks/s1/versions/2/cover')
    expect(res.cover_url).toBe('u')
  })

  it('POSTs to the cover approve endpoint', async () => {
    const post = vi.fn().mockResolvedValue({
      data: {
        cover_status: 'ready',
        cover_url: 'u',
        cover_approved_by: 'admin-1',
        cover_approved_at: '2026-07-28T00:00:00Z',
      },
    })
    const get = vi.fn()
    const api = makeCoverApi({ post, get } as never)
    const res = await api.approve('s1', 2)
    expect(post).toHaveBeenCalledWith('/v1/storybooks/s1/versions/2/cover/approve')
    expect(res.cover_status).toBe('ready')
    expect(res.cover_approved_by).toBe('admin-1')
  })
})
