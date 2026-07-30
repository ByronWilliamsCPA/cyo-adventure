/**
 * Adapter from the axios instance to the personalization values port (ADR-023 P6).
 *
 * One route serves both rings (design plan 8.3): the client never names a
 * connection or a subject profile, and the server derives both from the caller's
 * own principal and the book. So this module has one function, the reader has one
 * call site, and neither branches on a fact a child session could not determine.
 *
 * The route is keyed on the book, is never guardian-gated (a kid's tablet has to
 * be able to call it), and answers every predicate failure with an identical
 * empty payload rather than a 403 or a 404. There is therefore nothing here to
 * map onto the error classes `readerApi.ts` defines: any failure at all resolves
 * to null, which the resolver treats as "render generic".
 */

import { isAxiosError, type AxiosInstance } from 'axios'

import type { ValuesPayload } from '../player/personalization'

/**
 * Build the values fetcher.
 *
 * @param api - The axios instance from `useApi()`.
 * @returns A function taking a storybook id and resolving to its values payload,
 *   or to null on any failure.
 */
export function makeFetchPersonalizationValues(
  api: AxiosInstance
): (storybookId: string) => Promise<ValuesPayload | null> {
  return async (storybookId: string): Promise<ValuesPayload | null> => {
    try {
      const res = await api.get<ValuesPayload>(
        `/v1/storybooks/${storybookId}/personalization-values`
      )
      return res.data
    } catch (error) {
      // #ASSUME: data-integrity: EVERY failure resolves to null, including a 500
      // and an auth error, and none of them is re-thrown or surfaced. This
      // deliberately differs from readerApi.ts, which maps 404/403/401 onto
      // distinct error classes so the reader can show an honest screen. There is
      // no honest screen to show here: a missing values payload is not a broken
      // story, it is the generic story, which is the correct and complete reading
      // experience for every family that has not opted in. A reader that surfaced
      // a personalization failure would be telling a child about a feature their
      // guardian never enabled.
      // #VERIFY: personalizationApi.test.ts covers the thrown-Error and the
      // transport-failure shapes; Reader.test.tsx covers the render outcome.
      //
      // Child-facing silence preserved, console.warn only: without this, a
      // persistent 500 is indistinguishable from a family that never opted in.
      // Value-free by design: the failure kind (an HTTP status or a transport
      // label) and the book id only, never slot values, resolved text, or any
      // payload contents.
      const kind = isAxiosError(error) ? (error.response?.status ?? 'network') : 'non-http'
      console.warn('[personalization] values fetch failed; rendering generic', {
        storybookId,
        kind,
      })
      return null
    }
  }
}
