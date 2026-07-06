import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReviewDetailPage } from './ReviewDetailPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const SURFACE = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: { count: 1, hard_block: false, soft_flag: true, repaired: false, reviewer_independent: true },
  blob: {
    title: 'The Cave',
    nodes: [
      { id: 'n1', body: 'A dark cave yawned ahead.' },
      { id: 'n2', body: 'The path forked left and right.' },
    ],
  },
  flagged_passages: [
    {
      node_id: 'n1',
      prose: 'A dark cave yawned ahead.',
      findings: [
        { stage: 1, source: 'llm_safety', category: 'safety', node_id: 'n1', verdict: 'flag', score: null, message: 'possibly scary' },
      ],
    },
  ],
  story_level_findings: [],
}

function renderAt(storybookId: string) {
  return render(
    <MemoryRouter initialEntries={[`/guardian/review/${storybookId}`]}>
      <Routes>
        <Route path="/guardian/review/:storybookId" element={<ReviewDetailPage />} />
        <Route path="/guardian" element={<div>CONSOLE HOME</div>} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: SURFACE })
  mockPost.mockReset()
})

describe('ReviewDetailPage', () => {
  it('shows flagged passages with their findings first', async () => {
    renderAt('s1')
    expect(await screen.findByText('possibly scary')).toBeInTheDocument()
    expect(screen.getAllByText(/A dark cave yawned ahead/).length).toBeGreaterThan(0)
    expect(screen.getByText(/The path forked/)).toBeInTheDocument()
  })

  it('warns when the version was never screened', async () => {
    mockGet.mockResolvedValue({
      data: { ...SURFACE, screened: false, summary: null, flagged_passages: [], story_level_findings: [] },
    })
    renderAt('s1')
    expect(await screen.findByText(/never screened/i)).toBeInTheDocument()
  })

  it('approves after confirmation and returns to the console', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve')
    expect(await screen.findByText('CONSOLE HOME')).toBeInTheDocument()
  })

  it('requires a reason before sending back', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'needs_revision' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /Send Back/i }))
    const submit = await screen.findByRole('button', { name: /Confirm send back/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/reason/i), 'too intense for this age')
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/send-back', {
      reason: 'too intense for this age',
    })
    expect(await screen.findByText('CONSOLE HOME')).toBeInTheDocument()
  })

  it('keeps send back disabled for a whitespace-only reason', async () => {
    const user = userEvent.setup()
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /Send Back/i }))
    const submit = await screen.findByRole('button', { name: /Confirm send back/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/reason/i), '   ')
    expect(submit).toBeDisabled()
  })

  it('surfaces a backend rejection without navigating away', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 400 } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
    expect(screen.queryByText('CONSOLE HOME')).not.toBeInTheDocument()
  })

  it.each(['published', 'draft'] as const)(
    'disables Approve and Send Back for a %s story while keeping their labels',
    async (status) => {
      mockGet.mockResolvedValue({ data: { ...SURFACE, status } })
      renderAt('s1')
      // The buttons keep their action names ("Approve" / "Send Back"); the
      // disabled reason is carried by an aria-describedby hint, not by
      // overwriting the accessible name.
      const approve = await screen.findByRole('button', { name: /^Approve$/i })
      const sendBack = screen.getByRole('button', { name: /^Send Back$/i })
      expect(approve).toBeDisabled()
      expect(sendBack).toBeDisabled()

      const hint = screen.getByText(/only stories in review can be approved or sent back/i)
      expect(approve).toHaveAttribute('aria-describedby', hint.id)
      expect(sendBack).toHaveAttribute('aria-describedby', hint.id)
    }
  )

  it('keeps Approve and Send Back enabled for a story in review', async () => {
    renderAt('s1')
    const approve = await screen.findByRole('button', { name: /^Approve$/i })
    const sendBack = screen.getByRole('button', { name: /^Send Back$/i })
    expect(approve).toBeEnabled()
    expect(sendBack).toBeEnabled()
  })

  it('does not bleed a prior action error into the other dialog', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 400 } })
    renderAt('s1')
    // Fail an approve so actionError is set on the approve dialog.
    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
    expect(await screen.findByText(/could not approve/i)).toBeInTheDocument()
    // Cancel, then open Send Back: the prior approve failure must not render a
    // stale "could not send back" alert for an action never attempted.
    await user.click(screen.getByRole('button', { name: /^Cancel$/i }))
    await user.click(screen.getByRole('button', { name: /^Send Back$/i }))
    expect(screen.queryByText(/could not send this story back/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/could not approve/i)).not.toBeInTheDocument()
  })
})
