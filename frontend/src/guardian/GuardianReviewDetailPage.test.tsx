import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianReviewDetailPage } from './GuardianReviewDetailPage'

const mockGet = vi.fn()
const mockPatch = vi.fn()
const fakeApi = { get: mockGet, patch: mockPatch }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

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

function renderAt(storybookId: string) {
  return render(
    <MemoryRouter initialEntries={[`/guardian/review/${storybookId}`]}>
      <Routes>
        <Route path="/guardian/review/:storybookId" element={<GuardianReviewDetailPage />} />
        <Route path="/guardian/intake" element={<div>MY REQUESTS</div>} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: SURFACE })
  mockPatch.mockReset()
})

describe('GuardianReviewDetailPage', () => {
  it("loads the requesting family's own story via the review-surface GET", async () => {
    renderAt('s1')
    expect(await screen.findByText('possibly scary')).toBeInTheDocument()
    expect(screen.getAllByText(/A dark cave yawned ahead/).length).toBeGreaterThan(0)
    expect(screen.getByText(/The path forked/)).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('/v1/storybooks/s1/review', undefined)
  })

  it('renders no Approve, Send Back, Archive, cover-generation, or version-compare controls', async () => {
    renderAt('s1')
    await screen.findAllByText(/A dark cave yawned ahead/)
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send Back' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate cover' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Compare with version/ })).not.toBeInTheDocument()
  })

  it('links back to My Requests', async () => {
    renderAt('s1')
    await screen.findAllByText(/A dark cave yawned ahead/)
    expect(screen.getByRole('link', { name: 'Back to My Requests' })).toHaveAttribute(
      'href',
      '/guardian/intake'
    )
  })

  it("denies access to another family's story with a clear message and a way back", async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderAt('other-family-story')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This story belongs to a different family.'
    )
    expect(screen.getByRole('link', { name: 'Back to My Requests' })).toBeInTheDocument()
    expect(screen.queryByText(/A dark cave yawned ahead/)).not.toBeInTheDocument()
  })

  it('jumps from a flagged card to its passage, highlights it, and restarts the fade on a re-click', async () => {
    // This page carries its own copy of jumpToPassage (the admin page's
    // equivalent is covered in admin/ReviewDetailPage.test.tsx), so the
    // affordance needs its own test here rather than inheriting that one.
    // The second click is the point: it exercises the clearTimeout guard that
    // stops two jumps from racing to clear the same highlight, which a single
    // click leaves untested.
    const user = userEvent.setup()
    renderAt('s1')
    const jump = await screen.findByRole('button', { name: 'Show in story' })

    await user.click(jump)
    const passage = document.getElementById('passage-n1')
    expect(passage).not.toBeNull()
    expect(document.activeElement).toBe(passage)
    expect(passage).toHaveClass('review-node--highlight')

    await user.click(jump)
    expect(passage).toHaveClass('review-node--highlight')
  })

  describe('passage edit (G6)', () => {
    it('opens the edit dialog prefilled with the passage body and choice labels', async () => {
      const user = userEvent.setup()
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      await user.click(editButtons[0])

      const dialog = await screen.findByRole('dialog', { name: 'Edit passage n1' })
      const scoped = within(dialog)
      expect(scoped.getByLabelText('Passage text')).toHaveValue('A dark cave yawned ahead.')
      expect(scoped.getByLabelText('Choice to n2')).toHaveValue('Step inside')
    })

    it('saves an edit and refreshes the surface with the response', async () => {
      const user = userEvent.setup()
      const refreshed = {
        ...SURFACE,
        blob: {
          ...SURFACE.blob,
          nodes: [
            {
              id: 'n1',
              body: 'A NEWLY WRITTEN cave entrance.',
              choices: [{ id: 'c1', label: 'Step inside', target: 'n2' }],
            },
            SURFACE.blob.nodes[1],
          ],
        },
        flagged_passages: [],
      }
      mockPatch.mockResolvedValue({ data: refreshed })
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      await user.click(editButtons[0])

      const dialog = await screen.findByRole('dialog', { name: 'Edit passage n1' })
      const textarea = within(dialog).getByLabelText('Passage text')
      await user.clear(textarea)
      await user.type(textarea, 'A NEWLY WRITTEN cave entrance.')
      await user.click(within(dialog).getByRole('button', { name: 'Save' }))

      expect(mockPatch).toHaveBeenCalledWith('/v1/storybooks/s1/versions/1/nodes/n1', {
        body: 'A NEWLY WRITTEN cave entrance.',
        choice_labels: { c1: 'Step inside' },
      })
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(await screen.findByText(/A NEWLY WRITTEN cave entrance/)).toBeInTheDocument()
    })

    it('renders inline rule messages on a 422 gate failure and leaves the blob unchanged', async () => {
      const user = userEvent.setup()
      mockPatch.mockRejectedValue({
        isAxiosError: true,
        response: {
          status: 422,
          data: {
            error: 'ValidationError',
            message: 'edited passage failed the validation gate',
            details: {
              findings: [
                {
                  rule_id: 'L1-7',
                  severity: 'error',
                  story_id: 's1',
                  node_id: null,
                  choice_id: null,
                  message: 'node/word budget exceeded',
                },
              ],
            },
          },
        },
      })
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      await user.click(editButtons[0])

      const dialog = await screen.findByRole('dialog', { name: 'Edit passage n1' })
      await user.click(within(dialog).getByRole('button', { name: 'Save' }))

      expect(
        await within(dialog).findByText(/L1-7: node\/word budget exceeded/)
      ).toBeInTheDocument()
      expect(within(dialog).getByLabelText('Passage text')).toHaveValue('A dark cave yawned ahead.')
    })

    it('disables editing once the story is published', async () => {
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      for (const button of editButtons) {
        expect(button).toBeDisabled()
      }
      expect(
        screen.getByText('This story is published and can no longer be edited here.')
      ).toBeInTheDocument()
    })

    it('shows a needs_revision status hint and keeps editing enabled', async () => {
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'needs_revision' } })
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      expect(editButtons[0]).not.toBeDisabled()
      expect(screen.getByText(/A reviewer sent this back for changes/)).toBeInTheDocument()
    })
  })
})
