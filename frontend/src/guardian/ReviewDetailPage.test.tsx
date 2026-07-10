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

  it('approves with family visibility by default', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
      visibility: 'family',
    })
    expect(await screen.findByText('CONSOLE HOME')).toBeInTheDocument()
  })

  it('approves to the catalog when the admin selects it', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('radio', { name: /Catalog/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
      visibility: 'catalog',
    })
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

  it('surfaces a failed alert when cover generation errors, and re-enables the button', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderAt('s1')
    const generateButton = await screen.findByRole('button', { name: /Generate cover/i })
    await user.click(generateButton)
    expect(await screen.findByRole('alert')).toHaveTextContent(/cover failed; try again/i)
    expect(generateButton).toBeEnabled()
  })

  it('reflects an in-flight cover job on mount by seeding status from the server', async () => {
    // The review surface load and the cover-status seed are both GETs; return
    // an in-flight cover for the cover endpoint and the surface for the rest.
    mockGet.mockImplementation((url: string) =>
      typeof url === 'string' && url.endsWith('/cover')
        ? Promise.resolve({ data: { cover_status: 'generating', cover_url: null } })
        : Promise.resolve({ data: SURFACE })
    )
    renderAt('s1')
    // Without any click, the button reflects the in-flight job and is disabled,
    // so the reviewer cannot trigger a duplicate enqueue.
    const generating = await screen.findByRole('button', { name: /Generating cover/i })
    expect(generating).toBeDisabled()
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

  it('shows an error state when the review surface fails to load', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderAt('s1')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not load this story for review/i
    )
    expect(screen.queryByRole('button', { name: /^Approve$/i })).not.toBeInTheDocument()
  })

  it('renders story-level notes when the surface carries story-level findings', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        story_level_findings: [
          {
            stage: 2,
            source: 'llm_safety',
            category: 'tone',
            node_id: null,
            verdict: 'flag',
            score: null,
            message: 'overall tone is tense',
          },
        ],
      },
    })
    renderAt('s1')
    expect(await screen.findByText('Story-level notes')).toBeInTheDocument()
    expect(screen.getByText('overall tone is tense')).toBeInTheDocument()
  })

  it('keeps malformed node entries a reviewer must still see, and skips only unusable ones', async () => {
    // readNodes is deliberately lenient on a safety surface: prose with a
    // broken id must not silently drop out of the read-through. Entries that
    // are not objects or have neither id nor prose are the only ones skipped.
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        blob: {
          // No title: the heading falls back to the storybook id.
          nodes: [
            null, // not an object: skipped
            {}, // neither id nor body: skipped
            { id: 42, body: 'Prose with a malformed id survives.' }, // synthetic id
            { id: 'n_tail', body: 'A normal closing passage.' },
          ],
        },
        flagged_passages: [],
        story_level_findings: [],
      },
    })
    renderAt('s1')
    expect(
      await screen.findByRole('heading', { name: 's1', level: 1 })
    ).toBeInTheDocument()
    expect(screen.getByText('Prose with a malformed id survives.')).toBeInTheDocument()
    expect(screen.getByText('A normal closing passage.')).toBeInTheDocument()
  })

  it('renders no read-through nodes when the blob has a non-array nodes field', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        blob: { title: 'The Cave', nodes: 'not-an-array' },
        flagged_passages: [],
        story_level_findings: [],
      },
    })
    renderAt('s1')
    await screen.findByRole('heading', { name: 'The Cave', level: 1 })
    const fullStory = document.getElementById('full-story')
    expect(fullStory).not.toBeNull()
    expect(fullStory?.querySelectorAll('.review-node')).toHaveLength(0)
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
