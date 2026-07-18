import { useCallback, useEffect, useMemo, useState } from 'react'

import { useApi } from '../hooks/useApi'
import { formatBudgetBanner, makeBudgetApi, type FamilyBudgetView } from './budgetApi'
import { STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'

type BannerState =
  | { kind: 'loading' }
  | { kind: 'ready'; budget: FamilyBudgetView }
  | { kind: 'absent' }

/**
 * G13 (interim) balance banner: "N of M stories left this month", sourced
 * from GET /v1/families/me/budget. Used on RequestsPage (above the queue)
 * and IntakePage (near the submit button).
 *
 * Deliberately renders nothing while loading and on ANY fetch failure
 * (network error, session hiccup, or a role this endpoint does not cover):
 * this is a secondary, informational widget, not a gate, so its own
 * failure must never block or clutter the page it sits on.
 * #ASSUME: external-resources: a transient failure here just means the
 * banner stays absent until the next STORY_REQUESTS_CHANGED_EVENT or
 * remount; there is no retry affordance, unlike the pages' own primary-data
 * load errors, because a missing budget hint is not actionable the way a
 * missing request queue is.
 * #VERIFY: BudgetBanner.test.tsx "absent on fetch failure".
 *
 * Refetches on STORY_REQUESTS_CHANGED_EVENT, the same window event
 * StoryRequestQueue's approve/decline and IntakePage's submit dispatch
 * after a server-confirmed change, so the count never goes stale after an
 * action taken on the very page the banner sits on.
 */
export function BudgetBanner() {
  const api = useApi()
  const budgetApi = useMemo(() => makeBudgetApi(api), [api])
  const [state, setState] = useState<BannerState>({ kind: 'loading' })

  const refresh = useCallback(async () => {
    try {
      const budget = await budgetApi.get()
      setState({ kind: 'ready', budget })
    } catch (err) {
      console.error('budget banner load failed:', err instanceof Error ? err.message : err)
      setState({ kind: 'absent' })
    }
  }, [budgetApi])

  // #ASSUME: timing-dependencies: the initial fetch is deferred through
  // setTimeout(fn, 0) rather than called directly in the effect body; a
  // direct `void refresh()` here would call an outside (useCallback)
  // setState-calling function synchronously from the effect body, which
  // react-hooks/set-state-in-effect flags as a cascading-render risk (the
  // established fix elsewhere in this codebase, e.g. NotificationBell.tsx's
  // refreshUnread and ModerationThresholdsPage.tsx).
  useEffect(() => {
    const initial = setTimeout(() => void refresh(), 0)
    const onChanged = () => void refresh()
    window.addEventListener(STORY_REQUESTS_CHANGED_EVENT, onChanged)
    return () => {
      clearTimeout(initial)
      window.removeEventListener(STORY_REQUESTS_CHANGED_EVENT, onChanged)
    }
  }, [refresh])

  if (state.kind !== 'ready') return null

  const warning = state.budget.remaining <= 0
  return (
    <p
      className={`budget-banner${warning ? ' budget-banner--warning' : ''}`}
      role="status"
      data-testid="budget-banner"
    >
      {formatBudgetBanner(state.budget)}
    </p>
  )
}
