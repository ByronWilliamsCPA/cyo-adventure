/**
 * Adapter for the one outbound leg of KWS parent verification the browser
 * calls: POST /v1/consent/kws/start (ADR-018 D1).
 *
 * The other two legs never reach this code. KWS delivers the result to
 * `api/kws_webhook.py` server-to-server, and the parent's browser returns to
 * `api/kws_redirect.py`, a backend-rendered page outside this SPA. So there is
 * nothing here to poll for the result: the app learns an attempt resolved the
 * same way it learns anything else about the account, by re-running onboarding.
 *
 * Wire-shape types come from the generated client (`client/types.gen`), same
 * pattern as onboardingApi.ts and deviceGrantApi.ts.
 */

import type { AxiosInstance } from 'axios'

import type { KwsVerificationStartView } from '../client/types.gen'

export interface ConsentApi {
  /**
   * Ask KWS to email the CURRENT adult a verification link.
   *
   * Note what this does not take: an email address. The recipient is fixed
   * server-side from the caller's verified token claim, and the request body
   * has no field for it, so this adapter could not point the mail at a third
   * party even if a caller wanted to. See `api/consent.py`.
   */
  startKwsVerification(location: string): Promise<KwsVerificationStartView>
}

export function makeConsentApi(api: AxiosInstance): ConsentApi {
  return {
    async startKwsVerification(location: string): Promise<KwsVerificationStartView> {
      const res = await api.post<KwsVerificationStartView>('/v1/consent/kws/start', {
        location,
      })
      return res.data
    },
  }
}
