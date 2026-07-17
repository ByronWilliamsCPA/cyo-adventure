/**
 * Adapter for the guardian/admin family-budget summary (ADR-015 G7/G3,
 * G13 interim balance).
 *
 * Hand-typed like the sibling adapters in this directory (readingApi.ts,
 * notificationsApi.ts): useApi()'s axios instance carries the auth/refresh/
 * correlation behavior this call needs, and none of that is wired into the
 * generated sdk.gen.ts client. The row shapes mirror FamilyBudgetView /
 * ChildEnvelopeUsageView in api/schemas.py (also present, unused, in the
 * generated src/client/types.gen.ts, which this file deliberately does not
 * import from -- see profilesApi.ts's header comment for why every adapter
 * in this directory stays hand-typed instead of split across two client
 * styles).
 */

import { type AxiosInstance, isAxiosError } from 'axios'

/**
 * One child's ADR-015 G3 pre-authorization envelope usage this month, as
 * returned by GET /v1/families/me/budget. This is the ONLY place these two
 * fields round-trip from the backend today: ProfileView (profilesApi.ts)
 * does not carry them (see profilesApi.ts's ProfileEnvelopeFields doc for
 * the full picture, including the write-side gap).
 */
export interface ChildEnvelopeUsage {
  profile_id: string
  display_name: string
  request_auto_approve: boolean
  monthly_request_envelope: number | null
  used_this_month: number
}

/** GET /v1/families/me/budget: the caller's family monthly story budget. */
export interface FamilyBudgetView {
  quota: number
  spent_this_month: number
  remaining: number
  children: ChildEnvelopeUsage[]
}

export interface BudgetApi {
  get(): Promise<FamilyBudgetView>
}

export function makeBudgetApi(api: AxiosInstance): BudgetApi {
  return {
    async get(): Promise<FamilyBudgetView> {
      const res = await api.get<FamilyBudgetView>('/v1/families/me/budget')
      return res.data
    },
  }
}

/**
 * Friendly "N of M stories left this month" banner copy (G13 interim
 * balance). Pure so BudgetBanner.tsx and any other caller share identical
 * wording; singular/plural on `quota` only (a family with a quota of 1 is
 * the only case where "story" reads naturally; `remaining` stays plural-
 * agnostic since "1 of 5 stories left" is correct either way).
 */
export function formatBudgetBanner(budget: FamilyBudgetView): string {
  const noun = budget.quota === 1 ? 'story' : 'stories'
  return `${budget.remaining} of ${budget.quota} ${noun} left this month`
}

/**
 * The friendly copy for the ADR-015 G7 family-budget-exhausted 409, shown
 * in place of a generic "could not save/update" message wherever a
 * budget-gated action (approve, submit) can hit it.
 */
export const BUDGET_EXCEEDED_MESSAGE =
  "You've used this month's story budget. New requests can be made after it resets next month."

/**
 * Whether a thrown error is the ADR-015 G7 family-budget-exhausted 409
 * ("monthly story budget reached", raised by
 * story_requests/service.py::enforce_family_quota), as opposed to some
 * other 409 an approve/submit call can also hit: the per-profile pending
 * cap, the per-family active-generation-job cap, or a request that was
 * already decided by another reviewer. The backend's StateTransitionError
 * carries no distinguishing error_code (core/exceptions.py), so this
 * matches on the message text rather than the status alone.
 *
 * #ASSUME: data-integrity: the backend message stays "monthly story budget
 * reached" or close enough to keep matching /budget/i; a future wording
 * change that drops the word "budget" would silently fall back to the
 * generic conflict copy at the call site rather than mis-blaming a
 * different 409 on the budget, which is the safer failure direction.
 * #VERIFY: budgetApi.test.ts covers the budget-409, a non-budget 409, a
 * non-409 error, and a non-axios error.
 */
export function isBudgetExceededError(err: unknown): boolean {
  if (!isAxiosError(err) || err.response?.status !== 409) return false
  const data = err.response.data as { message?: unknown } | undefined
  const message = typeof data?.message === 'string' ? data.message : ''
  return /budget/i.test(message)
}
