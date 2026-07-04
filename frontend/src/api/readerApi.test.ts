import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { OfflineError } from '../offline/sync'
import type { ReadingState } from '../player/types'
import {
  ForbiddenError,
  StoryNotFoundError,
  makeFetchServerState,
  makeFetchStory,
  makeRecordCompletion,
} from './readerApi'

function axiosLike(reject: unknown): AxiosInstance {
  return { get: () => Promise.reject(reject) } as unknown as AxiosInstance
}

function axiosGet(result: unknown, reject = false): AxiosInstance {
  return {
    get: () => (reject ? Promise.reject(result) : Promise.resolve(result)),
  } as unknown as AxiosInstance
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

const SERVER_ROW: ReadingState = {
  current_node: 'n_cave_fork',
  var_state: { has_lantern: true },
  path: ['n_entrance', 'n_cave_fork'],
  visit_set: ['n_entrance', 'n_cave_fork'],
  version: 1,
  state_revision: 4,
  save_slots: {},
}

describe('makeFetchServerState', () => {
  it('returns the row on a 200', async () => {
    const fetchServerState = makeFetchServerState(axiosGet({ data: SERVER_ROW }))
    await expect(fetchServerState('p1', 's1')).resolves.toEqual(SERVER_ROW)
  })

  it('maps a 404 (no server state) to null', async () => {
    const fetchServerState = makeFetchServerState(
      axiosGet({ isAxiosError: true, response: { status: 404 } }, true)
    )
    await expect(fetchServerState('p1', 's1')).resolves.toBeNull()
  })

  it('maps a no-response transport failure to OfflineError', async () => {
    const fetchServerState = makeFetchServerState(
      axiosGet({ isAxiosError: true, response: undefined }, true)
    )
    await expect(fetchServerState('p1', 's1')).rejects.toBeInstanceOf(OfflineError)
  })

  it('rethrows other HTTP errors unchanged', async () => {
    const err = { isAxiosError: true, response: { status: 500 } }
    const fetchServerState = makeFetchServerState(axiosGet(err, true))
    await expect(fetchServerState('p1', 's1')).rejects.toBe(err)
  })
})

describe('makeRecordCompletion', () => {
  it('posts the completion body to /v1/completions', async () => {
    const post = vi.fn(() => Promise.resolve({ data: {} }))
    const recordCompletion = makeRecordCompletion({ post } as unknown as AxiosInstance)
    await recordCompletion({
      profile_id: 'p1',
      storybook_id: 's1',
      version: 1,
      ending_id: 'e_treasure_found',
    })
    expect(post).toHaveBeenCalledWith('/v1/completions', {
      profile_id: 'p1',
      storybook_id: 's1',
      version: 1,
      ending_id: 'e_treasure_found',
    })
  })
})
