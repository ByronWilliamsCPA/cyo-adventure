/**
 * Adapters from the axios instance to the reader's ports.
 *
 * `makeSyncApi` maps the reading-state PUT (and its 409 conflict body) onto the
 * sync layer's SyncApi; `makeFetchStory` fetches an immutable story version blob.
 * Endpoints sit under the `/v1` prefix relative to the axios `/api` baseURL.
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import { OfflineError, type PutResponse, type SaveBody, type SyncApi } from '../offline/sync'
import type { ReadingState, Storybook } from '../player/types'

interface ConflictBody {
  current_row: ReadingState
}

export function makeSyncApi(api: AxiosInstance): SyncApi {
  return {
    async putReadingState(
      profileId: string,
      storybookId: string,
      body: SaveBody
    ): Promise<PutResponse> {
      try {
        const res = await api.put<ReadingState>(
          `/v1/reading-state/${profileId}/${storybookId}`,
          body
        )
        return { status: 200, row: res.data }
      } catch (error) {
        if (isAxiosError(error)) {
          if (error.response?.status === 409) {
            const data = error.response.data as ConflictBody
            return { status: 409, currentRow: data.current_row }
          }
          // No HTTP response means a transport failure (offline/timeout); signal
          // it distinctly so the sync layer queues only true offline writes. An
          // HTTP error response (auth/validation/server) propagates as itself.
          if (!error.response) {
            throw new OfflineError()
          }
        }
        throw error
      }
    },
  }
}

/** Thrown when a story version does not exist (HTTP 404), as opposed to an
 * offline/transport failure (OfflineError). Lets the reader show an honest
 * "not found" screen instead of the offline "download again" copy. */
export class StoryNotFoundError extends Error {
  constructor(message = 'story not found') {
    super(message)
    this.name = 'StoryNotFoundError'
  }
}

/** Thrown when the profile lacks access to a story (HTTP 403). Distinct from
 * StoryNotFoundError so the reader can show a non-retryable screen instead of
 * a generic "Try again" that would just fail with the same 403 forever. */
export class ForbiddenError extends Error {
  constructor(message = 'access denied') {
    super(message)
    this.name = 'ForbiddenError'
  }
}

export function makeFetchStory(
  api: AxiosInstance
): (storybookId: string, version: number) => Promise<Storybook> {
  return async (storybookId: string, version: number): Promise<Storybook> => {
    try {
      const res = await api.get<Storybook>(`/v1/storybooks/${storybookId}/versions/${version}`)
      return res.data
    } catch (error) {
      if (isAxiosError(error)) {
        if (error.response?.status === 404) {
          throw new StoryNotFoundError()
        }
        if (error.response?.status === 403) {
          throw new ForbiddenError()
        }
        // No HTTP response means a transport failure (offline/timeout); signal it
        // distinctly so the reader shows the offline screen, not "not found".
        if (!error.response) {
          throw new OfflineError()
        }
      }
      throw error
    }
  }
}

/** A request body for POST /v1/completions (mirrors CompletionBody server-side). */
export interface CompletionRequest {
  profile_id: string
  storybook_id: string
  version: number
  ending_id: string
  event_id?: string
}

/**
 * Fetch the server's saved reading state for cross-device resume. Returns null
 * when the server has no state (HTTP 404) so the caller can start fresh; a
 * transport failure surfaces as OfflineError so the caller can degrade to local
 * play instead of treating it as "no progress".
 */
export function makeFetchServerState(
  api: AxiosInstance
): (profileId: string, storybookId: string) => Promise<ReadingState | null> {
  return async (profileId: string, storybookId: string): Promise<ReadingState | null> => {
    try {
      const res = await api.get<ReadingState>(`/v1/reading-state/${profileId}/${storybookId}`)
      return res.data
    } catch (error) {
      if (isAxiosError(error)) {
        // 404 is the honest "no saved progress on the server" answer, not an error.
        if (error.response?.status === 404) {
          return null
        }
        // No HTTP response means a transport failure (offline/timeout); signal it
        // distinctly so the caller degrades to local play, not "start fresh".
        if (!error.response) {
          throw new OfflineError()
        }
      }
      throw error
    }
  }
}

/**
 * Record a story completion. Best-effort: the server dedupes on
 * (profile, storybook, version, ending), so a repeat post is a no-op row-wise.
 */
// #ASSUME: data-integrity: the server dedupes completions on the (profile, storybook, version, ending) primary key, so a client retry after a dropped response cannot double-count.
// #VERIFY: backend api/reading.py record_completion PK-dedupe; if the dedup key or window changes, revisit this fire-and-forget call.
export function makeRecordCompletion(
  api: AxiosInstance
): (body: CompletionRequest) => Promise<void> {
  return async (body: CompletionRequest): Promise<void> => {
    await api.post('/v1/completions', body)
  }
}
