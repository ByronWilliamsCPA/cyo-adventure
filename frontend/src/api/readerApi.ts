/**
 * Adapters from the axios instance to the reader's ports.
 *
 * `makeSyncApi` maps the reading-state PUT (and its 409 conflict body) onto the
 * sync layer's SyncApi; `makeFetchStory` fetches an immutable story version blob.
 * Endpoints sit under the `/v1` prefix relative to the axios `/api` baseURL.
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import type { PutResponse, SaveBody, SyncApi } from '../offline/sync'
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
        if (isAxiosError(error) && error.response?.status === 409) {
          const data = error.response.data as ConflictBody
          return { status: 409, currentRow: data.current_row }
        }
        throw error
      }
    },
  }
}

export function makeFetchStory(
  api: AxiosInstance
): (storybookId: string, version: number) => Promise<Storybook> {
  return async (storybookId: string, version: number): Promise<Storybook> => {
    const res = await api.get<Storybook>(`/v1/storybooks/${storybookId}/versions/${version}`)
    return res.data
  }
}
