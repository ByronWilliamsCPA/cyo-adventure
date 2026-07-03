import type { AxiosInstance } from 'axios'
import { describe, expect, it } from 'vitest'
import { OfflineError } from '../offline/sync'
import { ForbiddenError, StoryNotFoundError, makeFetchStory } from './readerApi'

function axiosLike(reject: unknown): AxiosInstance {
  return { get: () => Promise.reject(reject) } as unknown as AxiosInstance
}

describe('makeFetchStory', () => {
  it('maps a 404 response to StoryNotFoundError', async () => {
    const fetchStory = makeFetchStory(axiosLike({ isAxiosError: true, response: { status: 404 } }))
    await expect(fetchStory('missing', 1)).rejects.toBeInstanceOf(StoryNotFoundError)
  })

  it('maps a 403 response to ForbiddenError', async () => {
    const fetchStory = makeFetchStory(axiosLike({ isAxiosError: true, response: { status: 403 } }))
    await expect(fetchStory('locked', 1)).rejects.toBeInstanceOf(ForbiddenError)
  })

  it('maps a no-response (transport) failure to OfflineError', async () => {
    const fetchStory = makeFetchStory(axiosLike({ isAxiosError: true, response: undefined }))
    await expect(fetchStory('s', 1)).rejects.toBeInstanceOf(OfflineError)
  })

  it('rethrows other HTTP errors unchanged', async () => {
    const err = { isAxiosError: true, response: { status: 500 } }
    const fetchStory = makeFetchStory(axiosLike(err))
    await expect(fetchStory('s', 1)).rejects.toBe(err)
  })
})
