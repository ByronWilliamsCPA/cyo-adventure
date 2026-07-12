import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { OfflineError } from '../offline/sync'
import type { ReadingState } from '../player/types'
import {
  ForbiddenError,
  StoryNotFoundError,
  UnauthenticatedError,
  makeFetchServerState,
  makeFetchSeriesNext,
  makeFetchStory,
  makeRecordCompletion,
  makeSyncApi,
} from './readerApi'
import type { SaveBody } from '../offline/sync'

/**
 * Real axios rejections are `AxiosError` instances (an `Error` subclass), so
 * these test doubles build a real `Error` carrying the same shape axios
 * attaches (`isAxiosError`, `response`) rather than rejecting with a bare
 * object, keeping the mocks faithful to what the code under test actually
 * receives.
 */
function mockAxiosError(props: Record<string, unknown>): Error {
  return Object.assign(new Error('mock axios error'), props)
}

function axiosLike(reject: Error): AxiosInstance {
  return { get: () => Promise.reject(reject) } as unknown as AxiosInstance
}

function axiosGetResolve(data: unknown): AxiosInstance {
  return { get: () => Promise.resolve(data) } as unknown as AxiosInstance
}

function axiosGetReject(error: Error): AxiosInstance {
  return { get: () => Promise.reject(error) } as unknown as AxiosInstance
}

describe('makeFetchStory', () => {
  it('maps a 404 response to StoryNotFoundError', async () => {
    const fetchStory = makeFetchStory(
      axiosLike(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
    )
    await expect(fetchStory('missing', 1)).rejects.toBeInstanceOf(StoryNotFoundError)
  })

  it('maps a 403 response to ForbiddenError', async () => {
    const fetchStory = makeFetchStory(
      axiosLike(mockAxiosError({ isAxiosError: true, response: { status: 403 } }))
    )
    await expect(fetchStory('locked', 1)).rejects.toBeInstanceOf(ForbiddenError)
  })

  it('maps a 401 response to UnauthenticatedError', async () => {
    const fetchStory = makeFetchStory(
      axiosLike(mockAxiosError({ isAxiosError: true, response: { status: 401 } }))
    )
    await expect(fetchStory('expired', 1)).rejects.toBeInstanceOf(UnauthenticatedError)
  })

  it('maps a no-response (transport) failure to OfflineError', async () => {
    const fetchStory = makeFetchStory(
      axiosLike(mockAxiosError({ isAxiosError: true, response: undefined }))
    )
    await expect(fetchStory('s', 1)).rejects.toBeInstanceOf(OfflineError)
  })

  it('rethrows other HTTP errors unchanged', async () => {
    const err = mockAxiosError({ isAxiosError: true, response: { status: 500 } })
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
    const fetchServerState = makeFetchServerState(axiosGetResolve({ data: SERVER_ROW }))
    await expect(fetchServerState('p1', 's1')).resolves.toEqual(SERVER_ROW)
  })

  it('maps a 404 (no server state) to null', async () => {
    const fetchServerState = makeFetchServerState(
      axiosGetReject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
    )
    await expect(fetchServerState('p1', 's1')).resolves.toBeNull()
  })

  it('maps a no-response transport failure to OfflineError', async () => {
    const fetchServerState = makeFetchServerState(
      axiosGetReject(mockAxiosError({ isAxiosError: true, response: undefined }))
    )
    await expect(fetchServerState('p1', 's1')).rejects.toBeInstanceOf(OfflineError)
  })

  it('rethrows other HTTP errors unchanged', async () => {
    const err = mockAxiosError({ isAxiosError: true, response: { status: 500 } })
    const fetchServerState = makeFetchServerState(axiosGetReject(err))
    await expect(fetchServerState('p1', 's1')).rejects.toBe(err)
  })
})

describe('makeSyncApi.putReadingState', () => {
  const SAVE_BODY: SaveBody = { ...SERVER_ROW, event_id: 'evt-1' }

  function axiosPutResolve(data: unknown): AxiosInstance {
    return { put: () => Promise.resolve(data) } as unknown as AxiosInstance
  }

  function axiosPutReject(error: Error): AxiosInstance {
    return { put: () => Promise.reject(error) } as unknown as AxiosInstance
  }

  it('returns the saved row on a 200', async () => {
    const sync = makeSyncApi(axiosPutResolve({ data: SERVER_ROW }))
    await expect(sync.putReadingState('p1', 's1', SAVE_BODY)).resolves.toEqual({
      status: 200,
      row: SERVER_ROW,
    })
  })

  it('maps a 409 to a conflict carrying the server current_row', async () => {
    const sync = makeSyncApi(
      axiosPutReject(
        mockAxiosError({
          isAxiosError: true,
          response: { status: 409, data: { current_row: SERVER_ROW } },
        })
      )
    )
    await expect(sync.putReadingState('p1', 's1', SAVE_BODY)).resolves.toEqual({
      status: 409,
      currentRow: SERVER_ROW,
    })
  })

  it('maps a 401 to UnauthenticatedError so the reader stops persisting', async () => {
    const sync = makeSyncApi(
      axiosPutReject(mockAxiosError({ isAxiosError: true, response: { status: 401 } }))
    )
    await expect(sync.putReadingState('p1', 's1', SAVE_BODY)).rejects.toBeInstanceOf(
      UnauthenticatedError
    )
  })

  it('maps a no-response transport failure to OfflineError', async () => {
    const sync = makeSyncApi(
      axiosPutReject(mockAxiosError({ isAxiosError: true, response: undefined }))
    )
    await expect(sync.putReadingState('p1', 's1', SAVE_BODY)).rejects.toBeInstanceOf(OfflineError)
  })

  it('rethrows other HTTP errors unchanged', async () => {
    const err = mockAxiosError({ isAxiosError: true, response: { status: 500 } })
    const sync = makeSyncApi(axiosPutReject(err))
    await expect(sync.putReadingState('p1', 's1', SAVE_BODY)).rejects.toBe(err)
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

describe('makeFetchSeriesNext', () => {
  const NEXT_BOOK = {
    storybook_id: 's_book2',
    version: 3,
    title: 'Book 2',
    series_entry_node: 'n_start',
    carries_state: true,
  }

  it('resolves the next-book payload from the series-next endpoint', async () => {
    const get = vi.fn(() => Promise.resolve({ data: { next: NEXT_BOOK } }))
    const fetchSeriesNext = makeFetchSeriesNext({ get } as unknown as AxiosInstance)
    await expect(fetchSeriesNext('p1', 's1')).resolves.toEqual(NEXT_BOOK)
    expect(get).toHaveBeenCalledWith('/v1/series-next/p1/s1')
  })

  it('maps next: null (every expected absence) to null', async () => {
    const fetchSeriesNext = makeFetchSeriesNext(axiosGetResolve({ data: { next: null } }))
    await expect(fetchSeriesNext('p1', 's1')).resolves.toBeNull()
  })

  it('propagates a 404 unchanged: absence is next: null, an error means the current book', async () => {
    const err = mockAxiosError({ isAxiosError: true, response: { status: 404 } })
    const fetchSeriesNext = makeFetchSeriesNext(axiosGetReject(err))
    await expect(fetchSeriesNext('p1', 's1')).rejects.toBe(err)
  })

  it('propagates a server error unchanged (the caller treats any failure as no continuation)', async () => {
    const err = mockAxiosError({ isAxiosError: true, response: { status: 500 } })
    const fetchSeriesNext = makeFetchSeriesNext(axiosGetReject(err))
    await expect(fetchSeriesNext('p1', 's1')).rejects.toBe(err)
  })
})
