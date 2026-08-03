import { createContext } from 'react'

import type { Principal } from './types'

/**
 * 'awaiting-approval': a self-signed-up guardian whose account an admin has
 * not yet approved (api/onboarding.py's self-signup track,
 * User.status='awaiting_approval'); GET /v1/me would 401 for them, so this
 * status short-circuits before ever calling it.
 * 'needs-consent': an approved (or admin-invited) guardian who has not yet
 * completed the Phase 2 / ADR-018 D1 signature-capture consent step. Never
 * set for a non-guardian role (an admin-only adult has no VPC consent
 * concept).
 * 'backend-unreachable': a Supabase session exists, but principal resolution
 * failed for a reason that says nothing about whether the session is valid
 * (network error, timeout, or a 5xx from our own API). Distinct from
 * 'signed-out' because the session is deliberately KEPT: the failure is
 * transient, so a retry can reach 'signed-in' without a re-login. Only ever
 * set by classifyPrincipalError's transient branch, which fails closed; see
 * AuthContext.tsx.
 */
export type AuthStatus =
  | 'loading'
  | 'signed-out'
  | 'awaiting-approval'
  | 'needs-consent'
  | 'signed-in'
  | 'backend-unreachable'

/**
 * A session was established with Supabase but the backend could not resolve it
 * to a Principal (GET /me failed, the JWT was rejected, the role was
 * unrecognized, or the Supabase subject has no backend User row). Distinct from
 * plain 'signed-out' (no session at all) so the login form can tell the user
 * "you're signed in, but we couldn't load your account" instead of stranding
 * them on an idle form. Null when there is no such error.
 */
export type AuthError = 'principal-unresolved'

export interface Credentials {
  email: string
  password: string
}

export interface AuthContextValue {
  status: AuthStatus
  principal: Principal | null
  authError: AuthError | null
  /**
   * True while this page load is the return leg of a password-recovery link
   * (Supabase fired PASSWORD_RECOVERY, the landing hash carried
   * type=recovery, or another guardian tab broadcast a recovery landing).
   * LoginPage renders the set-new-password form instead of redirecting while
   * this is set; it clears on a successful password update or on sign-out.
   */
  recovery: boolean
  /**
   * Set when this page load is the FAILED return leg of a recovery link (an
   * expired or already-used link). Distinct from `recovery`: no session was
   * established, so LoginPage should show its normal sign-in form with an
   * explanatory message rather than the set-new-password gate. Null when
   * this load is not a failed recovery return.
   */
  recoveryError: { code: string; description: string } | null
  signInWithOAuth: (provider: 'google' | 'apple') => Promise<void>
  signInWithPassword: (credentials: Credentials) => Promise<void>
  signOut: () => Promise<void>
  /**
   * Emails a password-reset link to `email`. Resolves whether or not the
   * address exists (Supabase does not reveal it), so callers must show a
   * neutral confirmation and never leak account existence.
   */
  requestPasswordReset: (email: string) => Promise<void>
  /**
   * Sets a new password on the current (recovery) session and, on success,
   * clears {@link recovery} so the app auto-continues to the console. Rethrows
   * Supabase's error so the form can surface a retryable failure.
   */
  updatePassword: (newPassword: string) => Promise<void>
  /**
   * Submits the Phase 2 / ADR-018 D1 VPC signature-capture consent
   * (GuardianConsentPage), plus the O-117 residence-country signal. On
   * success, re-resolves the principal via GET /v1/me and transitions
   * status to 'signed-in'; rethrows on failure (e.g. a 422 for a
   * missing/invalid signer name or country code) so the form can show it.
   * Only meaningful while status === 'needs-consent'. The O-119 adulthood
   * attestation is not a parameter here: submitting this call at all is
   * only possible once the form's adulthood checkbox is checked (mirrors
   * how `accepted: true` is likewise hardcoded rather than passed in), so
   * `adulthood_attested: true` is sent unconditionally by the
   * implementation.
   */
  recordConsent: (signerName: string, residenceCountry: string) => Promise<void>
  /**
   * P-6d: re-resolves status/principal from the CURRENT Supabase session,
   * without submitting anything. Used by GuardianAwaitingApprovalPage's
   * "Check again" recheck (and its background poll) so an admin's approval
   * can be picked up without a sign-out/sign-in round trip. Shares
   * syncPrincipal with recordConsent's tail, so it correctly short-circuits
   * before ever calling GET /v1/me for a still-awaiting-approval guardian
   * (see AuthStatus's 'awaiting-approval' doc).
   */
  refreshStatus: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
