import { expect, test } from '@playwright/test'

/**
 * Guardian story-request review (Task 3.0/G4) e2e: two pending requests
 * render, Approve removes the approved row (posting to its approve
 * endpoint), and Decline (through its confirm dialog) then empties the list.
 *
 * Like assignments.spec.ts, the guardian surface mounts GuardianAuthLayout ->
 * AuthProvider, which resolves the principal from a real Supabase
 * (GoTrueClient) session before ProtectedRoute will render RequestsPage. A
 * plain `auth_token` localStorage entry only feeds useApi's bearer
 * interceptor, so this spec also seeds a far-future GoTrueClient session
 * under the SDK's storage key and mocks GET /v1/me to resolve a guardian
 * principal. See assignments.spec.ts's header comment for the storage-key
 * derivation (`sb-<ref>-auth-token`, ref = `example` from
 * VITE_SUPABASE_URL=https://example.supabase.co in playwright.config.ts).
 * API traffic beyond that is still page.route-mocked; no live backend runs.
 */

const SUPABASE_SESSION_KEY = 'sb-example-auth-token'

const GUARDIAN_SESSION = {
  access_token: 'e2e-guardian-access-token',
  refresh_token: 'e2e-guardian-refresh-token',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: 4102444800, // 2100-01-01, comfortably non-expired
  user: {
    id: 'guardian-a',
    aud: 'authenticated',
    role: 'authenticated',
    app_metadata: {},
    user_metadata: {},
    created_at: '2026-07-02T00:00:00Z',
  },
}

const ME = {
  subject: 'guardian-a',
  role: 'guardian',
  family_id: 'fam-a',
  profile_ids: ['p1', 'p2'],
}

const DRAGON_REQUEST = {
  id: 'req-1',
  profile_id: 'p1',
  status: 'pending',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child',
  age_band: '5-8',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const PIRATE_REQUEST = {
  id: 'req-2',
  profile_id: 'p2',
  status: 'pending',
  request_text: 'A pirate adventure',
  moderation_flags: [],
  created_at: '2026-07-04T10:05:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const DRAGON_TALES_REQUEST = {
  id: 'req-3',
  profile_id: 'p1',
  status: 'pending',
  request_text: 'A story about a dragon who collects maps',
  moderation_flags: [],
  created_at: '2026-07-04T10:10:00Z',
  initiator_role: 'child',
  age_band: '5-8',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: 'Dragon Tales',
  anchor_storybook_id: null,
}

test.beforeEach(async ({ context }) => {
  await context.addInitScript(
    ([key, session]) => {
      window.localStorage.setItem('auth_token', 'guardian-a')
      window.localStorage.setItem(key, session)
    },
    [SUPABASE_SESSION_KEY, JSON.stringify(GUARDIAN_SESSION)] as const
  )
})

test('approve removes the approved row, then decline empties the list', async ({ page }) => {
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: ME }))

  let requests = [DRAGON_REQUEST, PIRATE_REQUEST]
  await page.route('**/api/v1/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests } })
  )

  let approveCalls = 0
  let approveBody: unknown = null
  await page.route('**/api/v1/story-requests/req-1/approve', (route) => {
    approveCalls += 1
    approveBody = route.request().postDataJSON()
    requests = requests.filter((r) => r.id !== 'req-1')
    return route.fulfill({
      json: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
  })
  await page.route('**/api/v1/story-requests/req-2/decline', (route) => {
    requests = requests.filter((r) => r.id !== 'req-2')
    return route.fulfill({ json: { id: 'req-2', status: 'declined' } })
  })

  await page.goto('/guardian/requests')

  await expect(page.getByText('A story about a friendly dragon')).toBeVisible()
  await expect(page.getByText('A pirate adventure')).toBeVisible()

  const dragonRow = page.getByTestId('request-req-1')
  await dragonRow.getByLabel('Story length').selectOption('medium')
  await dragonRow.getByRole('button', { name: 'Approve' }).click()

  await expect.poll(() => approveCalls).toBe(1)
  expect(approveBody).toEqual({ age_band: '5-8', length: 'medium', narrative_style: 'prose' })
  await expect(page.getByText('A story about a friendly dragon')).toHaveCount(0)
  await expect(page.getByText('A pirate adventure')).toBeVisible()

  const pirateRow = page.getByTestId('request-req-2')
  await pirateRow.getByRole('button', { name: 'Decline' }).click()

  // Decline confirms first: the dialog quotes the request so the reviewer
  // knows exactly what they are declining.
  const confirmDialog = page.getByRole('dialog', { name: 'Decline this request?' })
  await expect(confirmDialog.getByText('A pirate adventure')).toBeVisible()
  await confirmDialog.getByRole('button', { name: 'Decline request' }).click()

  await expect(page.getByText('No requests to review')).toBeVisible()
})

test('approving a proposed-series request includes the prefilled series title', async ({
  page,
}) => {
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: ME }))

  const requests = [DRAGON_TALES_REQUEST]
  await page.route('**/api/v1/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests } })
  )

  let approveCalls = 0
  let approveBody: unknown = null
  await page.route('**/api/v1/story-requests/req-3/approve', (route) => {
    approveCalls += 1
    approveBody = route.request().postDataJSON()
    return route.fulfill({
      json: { id: 'req-3', status: 'approved', concept_id: 'concept-3', job_id: 'job-3' },
    })
  })

  await page.goto('/guardian/requests')

  const row = page.getByTestId('request-req-3')
  await expect(row.getByLabel('Series title (optional)')).toHaveValue('Dragon Tales')
  await row.getByLabel('Story length').selectOption('medium')
  await row.getByRole('button', { name: 'Approve' }).click()

  await expect.poll(() => approveCalls).toBe(1)
  expect(approveBody).toEqual({
    age_band: '5-8',
    length: 'medium',
    narrative_style: 'prose',
    series_title: 'Dragon Tales',
  })
})
