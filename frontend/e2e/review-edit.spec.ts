import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * G6 passage-edit save path (admin review detail): PATCH
 * /v1/storybooks/{storybook_id}/versions/{version}/nodes/{node_id}
 * (frontend/src/admin/passageEditApi.ts, wired through usePassageEdit.ts).
 * Until now this write path had component coverage only
 * (ReviewDetailPage.test.tsx mocks the axios instance directly); nothing
 * drove it through a real browser click on an "Edit passage" button, through
 * the Dialog's focus trap, to a PATCH request and back into the page's
 * single review-surface state slot (ReviewDetailPage.tsx's `[state,
 * setState]`, fed by `onSurfaceRefreshed`).
 *
 * The blob below mirrors guardian-review.spec.ts's SURFACE (n1 -> n2) plus an
 * 'orphan' node with no incoming choice, so one fixture drives both the
 * reachable-section edit (n1, which also carries a choice label, so its PATCH
 * body includes choice_labels) and the unreachable-section edit (orphan,
 * body-only: no choices means usePassageEdit.ts's saveEdit omits
 * choice_labels entirely). Both sections render from the same <Passage>
 * component and share the same onEdit/openEditDialog wiring
 * (ReviewDetailPage.tsx), so this proves the shared wiring works from both
 * render sites, not just the reachable one the component test exercises.
 */

const SURFACE = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: {
    count: 1,
    hard_block: false,
    soft_flag: true,
    repaired: false,
    reviewer_independent: true,
  },
  blob: {
    title: 'The Cave',
    start_node: 'n1',
    nodes: [
      {
        id: 'n1',
        body: 'A dark cave yawned ahead.',
        choices: [{ id: 'c1', label: 'Step inside', target: 'n2' }],
      },
      { id: 'n2', body: 'The path forked left and right.', choices: [] },
      // No node's choices target this id, so buildReadThrough (reviewDiff.ts)
      // puts it in the unreachable section alongside n1/n2's reachable one.
      { id: 'orphan', body: 'A forgotten grotto sparkles.', choices: [] },
    ],
  },
  flagged_passages: [
    {
      node_id: 'n1',
      prose: 'A dark cave yawned ahead.',
      findings: [
        {
          stage: 1,
          source: 'llm_safety',
          category: 'safety',
          node_id: 'n1',
          verdict: 'flag',
          score: null,
          message: 'possibly scary',
        },
      ],
    },
  ],
  story_level_findings: [],
}

interface CapturedPatch {
  method: string
  body: unknown
}

/**
 * Mock the PATCH endpoint for one node id, capturing the exact method/body
 * the app sent, and fulfill with a refreshed surface whose matching node's
 * body is replaced by `newBody`. This mirrors the backend's real contract:
 * per passageEditApi.ts's doc comment, the PATCH response is a full refreshed
 * ReviewSurface (the same shape a GET would return), which is why
 * ReviewDetailPage can drop it straight into its single `state` slot.
 */
async function mockNodeEdit(
  page: Page,
  nodeId: string,
  newBody: string
): Promise<() => CapturedPatch | null> {
  let captured: CapturedPatch | null = null
  await page.route(`**/api/v1/storybooks/s1/versions/1/nodes/${nodeId}`, (route) => {
    captured = { method: route.request().method(), body: route.request().postDataJSON() }
    const refreshed = {
      ...SURFACE,
      blob: {
        ...SURFACE.blob,
        nodes: SURFACE.blob.nodes.map((node) =>
          node.id === nodeId ? { ...node, body: newBody } : node
        ),
      },
    }
    return route.fulfill({ json: refreshed })
  })
  return () => captured
}

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await page.route('**/api/v1/storybooks/s1/review*', (route) => route.fulfill({ json: SURFACE }))
  // useCoverGeneration (ReviewDetailPage.tsx) seeds cover status from this GET
  // on mount, unconditionally and best-effort (admin-review-cover.spec.ts);
  // mock it so this mounted-on-every-test call never falls through to the
  // absent real backend.
  await page.route('**/api/v1/storybooks/s1/versions/1/cover', (route) =>
    route.fulfill({ json: { cover_status: 'none', cover_url: null } })
  )
})

test('reachable-passage edit: saving n1 PATCHes body + choice_labels and updates the page', async ({
  page,
}) => {
  const patched = await mockNodeEdit(page, 'n1', 'A NEWLY WRITTEN cave entrance.')

  await page.goto('/admin/review/s1')
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()

  const n1Passage = page.locator('#passage-n1')
  await n1Passage.getByRole('button', { name: 'Edit passage' }).click()

  const dialog = page.getByRole('dialog', { name: 'Edit passage n1' })
  await expect(dialog).toBeVisible()
  const textarea = dialog.getByLabel('Passage text')
  await expect(textarea).toHaveValue('A dark cave yawned ahead.')
  await textarea.fill('A NEWLY WRITTEN cave entrance.')
  await dialog.getByRole('button', { name: 'Save' }).click()

  // The dialog closing means the async save resolved and
  // ReviewDetailPage's onSurfaceRefreshed wiring already swapped the state
  // slot to the refreshed surface.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(patched()).toEqual({
    method: 'PATCH',
    body: { body: 'A NEWLY WRITTEN cave entrance.', choice_labels: { c1: 'Step inside' } },
  })
  await expect(page.getByText('A NEWLY WRITTEN cave entrance.')).toBeVisible()
})

test('unreachable-passage edit: saving orphan PATCHes body-only and updates the page', async ({
  page,
}) => {
  const patched = await mockNodeEdit(page, 'orphan', 'A treasure room, freshly rewritten.')

  await page.goto('/admin/review/s1')
  await expect(page.getByRole('heading', { name: 'Unreachable passages' })).toBeVisible()

  const orphanPassage = page.locator('#passage-orphan')
  await orphanPassage.getByRole('button', { name: 'Edit passage' }).click()

  const dialog = page.getByRole('dialog', { name: 'Edit passage orphan' })
  await expect(dialog).toBeVisible()
  const textarea = dialog.getByLabel('Passage text')
  await expect(textarea).toHaveValue('A forgotten grotto sparkles.')
  await textarea.fill('A treasure room, freshly rewritten.')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(patched()).toEqual({
    method: 'PATCH',
    // orphan has no choices, so editChoices is empty and saveEdit
    // (usePassageEdit.ts) omits choice_labels from the request body entirely.
    body: { body: 'A treasure room, freshly rewritten.' },
  })
  await expect(page.getByText('A treasure room, freshly rewritten.')).toBeVisible()
})
