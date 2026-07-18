import { useAuth } from '../auth/useAuth'
import { BudgetBanner } from './BudgetBanner'
import { RequestStoryForm } from './RequestStoryForm'
import { StoryRequestQueue } from './StoryRequestQueue'

/**
 * Guardian story-request review (Task 3.0): the family-scoped pending queue
 * (a guardian approves or declines their own children's requests), with an
 * embedded RequestStoryForm (WS-B PR 2) above it for authoring a
 * pre-approved request of their own. The cross-family queue lives on the
 * admin console (AdminRequestsPage), not here: this surface is family-scoped
 * for every caller, including a dual-role adult.
 */
export function RequestsPage() {
  const { principal } = useAuth()

  return (
    <>
      {principal?.role === 'guardian' ? <RequestStoryForm mode="guardian" /> : null}
      {/* G13 (interim) balance: "N of M stories left this month". This
          queue is always family-scoped (see the component doc above), so
          the banner's own family-budget read is always the right one here,
          for either a guardian or a dual-role admin. */}
      <BudgetBanner />
      {/* The tracking hint is guardian-specific (this family's Story
          requests view); the admin cross-family queue keeps the component's
          neutral default message. */}
      <StoryRequestQueue
        scope="family"
        approveSuccessMessage="Approved! The story is being made; track it under Story requests."
      />
    </>
  )
}
