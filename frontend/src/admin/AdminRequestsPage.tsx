import { RequestStoryForm } from '../guardian/RequestStoryForm'
import { StoryRequestQueue } from '../guardian/StoryRequestQueue'

/**
 * Admin story-request review: the cross-family pending queue (backed by the
 * admin-only GET /v1/admin/story-requests), with the admin-mode
 * RequestStoryForm (WS-B PR 2) above it for authoring a pre-approved request
 * against a chosen family. The family-scoped counterpart for guardians lives
 * at /guardian/requests (RequestsPage).
 */
export function AdminRequestsPage() {
  return (
    <>
      <RequestStoryForm mode="admin" />
      <StoryRequestQueue scope="all" />
    </>
  )
}
