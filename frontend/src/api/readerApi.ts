/**
 * Adapters from the axios instance to the reader's ports.
 *
 * `makeSyncApi` maps the reading-state PUT (and its 409 conflict body) onto the
 * sync layer's SyncApi; `makeFetchStory` fetches an immutable story version blob.
 * Endpoints sit under the `/v1` prefix relative to the axios `/api` baseURL.
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import type {
  ConflictView,
  KidFlagCreateBody,
  KidFlagCreatedView,
  ReadingHistoryItem,
  ReadingHistoryView,
  ReadingStateResultView,
  SeriesNextView,
} from '../client/types.gen'
import { OfflineError, type PutResponse, type SaveBody, type SyncApi } from '../offline/sync'
import type { ReadingState, Storybook } from '../player/types'

// Alias, not a hand-typed shadow interface: the shape is the generated
// OpenAPI client's ConflictView (frontend/src/client/types.gen.ts), the
// single source of truth for the 409 body PUT /v1/reading-state returns
// (Finding 7).
type ConflictBody = ConflictView

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
          // A 401 means the child session token expired/was revoked mid-read.
          // Surface it as UnauthenticatedError so the reader stops persisting
          // (every retry would 401 too) and shows the ask-a-grown-up gate,
          // instead of the misleading "we'll keep trying" save banner.
          if (error.response?.status === 401) {
            throw new UnauthenticatedError()
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

/** Thrown on an HTTP 401: the bearer the request carried (a child session
 * token, most commonly an expired one) is no longer valid. Distinct from
 * ForbiddenError so the reader shows an ask-a-grown-up gate and STOPS, rather
 * than a "Try again" or a "we'll keep trying" save banner that can never
 * succeed until a grown-up signs in again. */
export class UnauthenticatedError extends Error {
  constructor(message = 'session expired') {
    super(message)
    this.name = 'UnauthenticatedError'
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
        // A 401 means the child session token is no longer valid; the reader
        // maps this to an ask-a-grown-up gate, not the generic error screen.
        if (error.response?.status === 401) {
          throw new UnauthenticatedError()
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
 * The celebration-relevant fields of POST /v1/completions' response (mirrors
 * CompletionRecordedView server-side; W0.3, design review 2026-08-01 section
 * 3.4). Hand-typed narrowing of the regenerated client's
 * `CompletionRecordedView` (`client/types.gen.ts`); retained for the
 * celebration-relevant subset. Follow-up: assert parity in
 * `apiContractParity.ts`.
 */
export interface CompletionResult {
  is_new: boolean
  found: number
  total: number
}

/**
 * The reader's knowledge of a just-reached ending's completion POST, as
 * tracked by ReaderPage and consumed by EndingsProgress (W0.3). A
 * discriminated union, not a nullable result, so "no answer yet" (racing the
 * POST would under-report) and "the POST failed, use the fallback fetch" are
 * distinguishable at the type level instead of collapsing to one falsy value.
 */
export type CompletionOutcome =
  { status: 'pending' } | { status: 'ready'; result: CompletionResult } | { status: 'unavailable' }

/**
 * Fetch the server's saved reading state for cross-device resume. Returns null
 * when the server has no state (200 with `state: null`, per
 * ReadingStateResultView) so the caller can start fresh; a transport failure
 * surfaces as OfflineError so the caller can degrade to local play instead of
 * treating it as "no progress".
 */
export function makeFetchServerState(
  api: AxiosInstance
): (profileId: string, storybookId: string) => Promise<ReadingState | null> {
  return async (profileId: string, storybookId: string): Promise<ReadingState | null> => {
    try {
      const res = await api.get<ReadingStateResultView>(
        `/v1/reading-state/${profileId}/${storybookId}`
      )
      // #CRITICAL: data-integrity: the server answers "no saved progress" as
      // 200 { state: null }, never a 404, for a first-time reader. If this
      // ever coerced a malformed or undefined body to "has progress", a
      // first-time reader would look like a returning one: ADR-028
      // active-character seeding would be skipped entirely
      // (ReaderPage.tsx's start-a-read branch), and the "ignores a
      // continuation when saved progress exists" guard would misfire. The
      // `?? null` below is the entire contract: it must map only an
      // explicit `state: null`, never coerce absence-of-field to "has
      // progress".
      // #VERIFY: readerApi.test.ts::makeFetchServerState covers the 200
      // null-state, 200 with-state, legacy-404, and transport-failure cases;
      // ReaderPage.test.tsx's continuation guard depends on this mapping
      // staying accurate.
      return res.data.state ?? null
    } catch (error) {
      if (isAxiosError(error)) {
        // #EDGE: security: a 404 on this route is now always a genuine
        // error, never "no saved progress" (see the #CRITICAL note above):
        // either _load_readable_storybook found the story missing or
        // unreadable, or _require_assignment is existence-hiding an
        // unassigned/cross-family profile-story pair
        // (src/cyo_adventure/api/reading.py). This branch deliberately
        // degrades that error to "start fresh" instead of rethrowing, which
        // silently converts an authorization denial into a fresh read. That
        // is safe only because the sole production caller, ReaderPage.tsx,
        // already catches every throw from this function and sets
        // `saved = undefined` regardless of the reason, so the two paths are
        // observationally identical there today. If a future caller needs to
        // tell "no progress" apart from "denied", it must not reuse this
        // function; it should call the endpoint directly and read the body.
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
 * Record a story completion. The server dedupes on
 * (profile, storybook, version, ending), so a repeat post is a no-op
 * row-wise; the response's `is_new`/`found`/`total` (W0.3) still reflect the
 * true post-call state either way, so the caller (ReaderPage) can render the
 * ending screen's tracker directly from it instead of a second, racing GET.
 */
// #ASSUME: data-integrity: the server dedupes completions on the (profile, storybook, version, ending) primary key, so a client retry after a dropped response cannot double-count.
// #VERIFY: backend api/reading.py record_completion PK-dedupe; if the dedup key or window changes, revisit this fire-and-forget call.
export function makeRecordCompletion(
  api: AxiosInstance
): (body: CompletionRequest) => Promise<CompletionResult> {
  return async (body: CompletionRequest): Promise<CompletionResult> => {
    const res = await api.post<CompletionResult>('/v1/completions', body)
    return res.data
  }
}

/** The generated non-null payload of GET /v1/series-next (single source of truth). */
export type SeriesNextBookInfo = NonNullable<SeriesNextView['next']>

/**
 * Resolve the next readable book in a series for a profile. Returns null when
 * the server answers next: null (every expected absence). Errors propagate;
 * the caller treats any failure as "no continuation offered" (best-effort).
 */
// #ASSUME: external-resources: GET /v1/series-next answers every expected absence (non-series book, no next book, next unpublished or unreadable) as 200 with next: null, never a 404; errors are reserved for the CURRENT book, so this adapter maps nothing and lets any failure propagate.
// #VERIFY: backend api/reading.py get_series_next null-body contract; ContinueSeries.tsx swallows rejections to "no button" (readerApi.test.ts makeFetchSeriesNext tests).
export function makeFetchSeriesNext(
  api: AxiosInstance
): (profileId: string, storybookId: string) => Promise<SeriesNextBookInfo | null> {
  return async (profileId, storybookId) => {
    const res = await api.get<SeriesNextView>(`/v1/series-next/${profileId}/${storybookId}`)
    return res.data.next ?? null
  }
}

/**
 * Fetch a profile's reading-history listing (the endings tracker, K6): one row
 * per storybook the profile has any completion for. The ending screen matches
 * on `storybook_id` to find the current book's row; the caller treats a
 * rejection as best-effort ("no tracker shown"), same convention as
 * makeFetchSeriesNext.
 */
export function makeFetchReadingHistory(
  api: AxiosInstance
): (profileId: string) => Promise<ReadingHistoryItem[]> {
  return async (profileId: string): Promise<ReadingHistoryItem[]> => {
    const res = await api.get<ReadingHistoryView>(`/v1/reading-history/${profileId}`)
    // #ASSUME: data-integrity: a well-formed response always has `books` as
    // an array; defend against a malformed body anyway so a bad payload
    // degrades to "no tracker" (EndingsProgress renders nothing for an
    // empty array) rather than throwing.
    return Array.isArray(res.data.books) ? res.data.books : []
  }
}

/** The three structured reasons a child can flag a passage for (K15). No
 * free-text field exists on the wire: KidFlagCreateBody's `reason` is the
 * entire signal (see its backend docstring). */
export type FlagReason = KidFlagCreateBody['reason']

export interface SubmitFlagParams {
  profileId: string
  storybookId: string
  version: number
  reason: FlagReason
  /** The node the child was reading when they tapped "Tell a grown-up";
   * omitted when unavailable rather than guessed. */
  nodeId?: string | null
}

/** Thrown when POST /v1/flags 409s: the profile has hit its open-flag cap
 * (StateTransitionError server-side). Distinct from a generic failure so the
 * caller can show the gentle "you've told us a lot already" copy instead of a
 * retry prompt that would just 409 again. */
export class FlagCapReachedError extends Error {
  constructor(message = 'flag cap reached') {
    super(message)
    this.name = 'FlagCapReachedError'
  }
}

/**
 * Submit a child's structured flag (K15). Never carries free text; `reason`
 * is one of exactly three kid-simple choices (see FlagReason). A 409 maps to
 * FlagCapReachedError; every other failure propagates so the caller can log it
 * and reassure the child (FlagButton shows the same gentle confirmation as
 * success, never a retry prompt, on the app's most emotionally sensitive path).
 */
export function makeSubmitFlag(
  api: AxiosInstance
): (params: SubmitFlagParams) => Promise<KidFlagCreatedView> {
  return async (params: SubmitFlagParams): Promise<KidFlagCreatedView> => {
    try {
      const res = await api.post<KidFlagCreatedView>('/v1/flags', {
        profile_id: params.profileId,
        storybook_id: params.storybookId,
        version: params.version,
        reason: params.reason,
        node_id: params.nodeId ?? null,
      })
      return res.data
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 409) {
        throw new FlagCapReachedError()
      }
      throw error
    }
  }
}

export interface ReportDownloadParams {
  deviceId: string
  profileId: string
  storybookId: string
}

/**
 * G15 storage/download view (backend: api/offline_downloads.py): report
 * that this device has (or still has) a book cached offline. Best-effort by
 * contract, matching FlagButton's own failure posture: a report failure
 * must never block or interrupt reading, which is already in hand from the
 * IndexedDB cache regardless of whether the server ever learns about it.
 * Callers should not await this for anything user-visible; it exists to
 * make the guardian console eventually consistent, not to gate the read.
 */
export function makeReportDownload(
  api: AxiosInstance
): (params: ReportDownloadParams) => Promise<void> {
  return async (params: ReportDownloadParams): Promise<void> => {
    await api.put('/v1/device-downloads', {
      device_id: params.deviceId,
      profile_id: params.profileId,
      storybook_id: params.storybookId,
    })
  }
}

export interface RemoveDownloadParams {
  deviceId: string
  storybookId: string
}

/**
 * G15 storage/download view (backend: api/offline_downloads.py): report that
 * this device no longer has a book cached offline. The mirror image of
 * makeReportDownload above, wired to the client's own eviction paths
 * (offline/db.ts's cacheStorybook space-pressure eviction and
 * offline/revocation.ts's reconcileOfflineCache shared-content purge)
 * instead of the reader's load path. Best-effort by the same contract as
 * makeReportDownload: a failed or missing report must never block, delay, or
 * fail the local eviction it describes, which is already final by the time
 * this is called (the guardian console eventually catches up, not the other
 * way around). No profile_id on the wire: the endpoint removes every row the
 * caller may act on for this (device, storybook) pair, matching
 * deleteStorybooksById's own device-wide (not per-profile) scope, see
 * remove_device_download's docstring for why. Callers should not await this
 * for anything user-visible.
 */
export function makeRemoveDownload(
  api: AxiosInstance
): (params: RemoveDownloadParams) => Promise<void> {
  return async (params: RemoveDownloadParams): Promise<void> => {
    await api.delete('/v1/device-downloads', {
      params: {
        device_id: params.deviceId,
        storybook_id: params.storybookId,
      },
    })
  }
}
