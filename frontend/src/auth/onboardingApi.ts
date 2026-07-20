/**
 * Adapter for POST /v1/onboarding: JIT guardian provisioning, the self-signup
 * approval track, and Phase 2 VPC consent capture. Called from AuthContext
 * right after a Supabase session is established (before GET /v1/me, since an
 * awaiting-approval or unconsented guardian would just fail that call), and
 * again from GuardianConsentPage when the guardian submits their signature.
 *
 * Wire-shape types come from the generated client (`client/types.gen`), same
 * pattern as deviceGrantApi.ts.
 */

import type { AxiosInstance } from 'axios'

import type { OnboardingConsent, OnboardingView } from '../client/types.gen'

/**
 * The consent-language version stamped on every recorded consent
 * (User.consent_policy_version). Bump this whenever the Privacy Notice /
 * consent copy materially changes; a bump does not retroactively invalidate
 * an existing guardian's recorded consent (there is no re-consent-on-bump
 * flow yet -- see docs/compliance/privacy-notice.md's version history for
 * what each value covers).
 */
export const CONSENT_POLICY_VERSION = '2026-07-20'

export interface OnboardingApi {
  /**
   * Resolve (or, on first login, create) the caller's family/guardian
   * identity. `consent` is omitted for the plain post-sign-in call and
   * supplied only when the guardian is actively submitting the VPC
   * signature-capture step.
   */
  onboard(consent?: OnboardingConsent): Promise<OnboardingView>
}

export function makeOnboardingApi(api: AxiosInstance): OnboardingApi {
  return {
    async onboard(consent?: OnboardingConsent): Promise<OnboardingView> {
      const res = await api.post<OnboardingView>(
        '/v1/onboarding',
        consent === undefined ? {} : { consent }
      )
      return res.data
    },
  }
}
