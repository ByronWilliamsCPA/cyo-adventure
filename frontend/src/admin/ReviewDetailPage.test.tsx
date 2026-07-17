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
        choices: [{ label: 'Step inside', target: 'n2' }],
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

/**
 * Branching fixture for the traversal-ordered read-through: the blob stores
 * nodes deliberately OUT of read order, includes an ending with kind/valence,
 * a choice whose target does not exist ('ghost'), and a node unreachable from
 * the start ('orphan'). Depth-first from 'start' following choice order gives
 * start, left, end-a; orphan must still render, labeled unreachable.
 */
const TRAVERSAL_SURFACE = {
  ...SURFACE,
  blob: {
    title: 'The Cave',
    start_node: 'start',
    nodes: [
      { id: 'orphan', body: 'A forgotten grotto sparkles.', choices: [] },
      {
        id: 'end-a',
        body: 'You find the treasure.',
        choices: [],
        is_ending: true,
        ending: { kind: 'success', valence: 'positive' },
      },
      {
        id: 'start',
        body: 'A dark cave yawned ahead.',
        choices: [
          { label: 'Go left', target: 'left' },
          { label: 'Go right', target: 'end-a' },
        ],
      },
      {
        id: 'left',
        body: 'The left path narrows.',
        choices: [
          { label: 'Squeeze through', target: 'end-a' },
          { label: 'Peek into the crack', target: 'ghost' },
        ],
      },
    ],
  },
  flagged_passages: [
    {
      node_id: 'left',
      prose: 'The left path narrows.',
      findings: [
        {
          stage: 1,
          source: 'llm_safety',
          category: 'safety',
          node_id: 'left',
          verdict: 'flag',
          score: null,
          message: 'tight spaces',
        },
      ],
    },
  ],
}

/**
 * Two-version fixture for the version-compare feature: version 1 is the
 * base, version 2 changes n1's body, drops n3, and adds n4, so a compare
 * exercises all three diff outcomes (changed, removed, added) in one fixture.
 * n2 is identical in both (including its now-dangling choice to the dropped
 * n3) so it must NOT show up as changed.
 */
const BASE_SURFACE = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: {
    count: 0,
    hard_block: false,
    soft_flag: false,
    repaired: false,
    reviewer_independent: true,
  },
  blob: {
    title: 'The Cave',
    start_node: 'n1',
    nodes: [
      { id: 'n1', body: 'Original opening.', choices: [{ label: 'Go on', target: 'n2' }] },
      { id: 'n2', body: 'Middle passage.', choices: [{ label: 'Finish', target: 'n3' }] },
      {
        id: 'n3',
        body: 'The old ending.',
        choices: [],
        is_ending: true,
        ending: { kind: 'success', valence: 'positive' },
      },
    ],
  },
  flagged_passages: [],
  story_level_findings: [],
}

const CURRENT_SURFACE = {
  ...BASE_SURFACE,
  version: 2,
  blob: {
    title: 'The Cave',
    start_node: 'n1',
    nodes: [
      { id: 'n1', body: 'Revised opening.', choices: [{ label: 'Go on', target: 'n2' }] },
      { id: 'n2', body: 'Middle passage.', choices: [{ label: 'Finish', target: 'n3' }] },
      {
        id: 'n4',
        body: 'A brand new twist.',
        choices: [],
        is_ending: true,
        ending: { kind: 'success', valence: 'positive' },
      },
    ],
  },
}

/**
 * A 404 shaped like axios's, but as an Error instance (prefer-promise-reject-
 * errors requires the rejection reason to be an Error); isAxiosError() only
 * checks the two properties below, so this still satisfies the component's
 * `isAxiosError(err) && err.response?.status === 404` check.
 */
function notFoundError(): Error & { isAxiosError: true; response: { status: number } } {
  return Object.assign(new Error('Not Found'), {
    isAxiosError: true as const,
    response: { status: 404 },
  })
}

/**
 * Routes review-surface GETs by their `version` query param, and cover-status
 * GETs (identified by the URL suffix, same as the "reflects an in-flight
 * cover job" test above) to a neutral status: no param resolves the current
 * (version 2) surface, `version: 1` resolves the base surface, and any other
 * version 404s like a pruned or nonexistent one.
 */
function mockCompareRoutes() {
  mockGet.mockImplementation((url: string, config?: { params?: { version?: number } }) => {
    if (typeof url === 'string' && url.endsWith('/cover')) {
      return Promise.resolve({ data: { cover_status: 'none', cover_url: null } })
    }
    const version = config?.params?.version
    if (version === undefined || version === 2) return Promise.resolve({ data: CURRENT_SURFACE })
    if (version === 1) return Promise.resolve({ data: BASE_SURFACE })
    return Promise.reject(notFoundError())
  })
}

function renderAt(storybookId: string) {
  return render(
    <MemoryRouter initialEntries={[`/admin/review/${storybookId}`]}>
      <Routes>
        <Route path="/admin/review/:storybookId" element={<ReviewDetailPage />} />
        <Route path="/admin" element={<div>CONSOLE HOME</div>} />
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

  it('orders the read-through depth-first from start_node, unreachable passages last', async () => {
    mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
    renderAt('s1')
    await screen.findByRole('heading', { name: 'Full story' })
    const fullStory = document.getElementById('full-story')
    expect(fullStory).not.toBeNull()
    const bodies = Array.from(fullStory?.querySelectorAll('.review-node') ?? []).map(
      (el) => el.textContent ?? ''
    )
    // All four blob nodes render exactly once: nothing drops out.
    expect(bodies).toHaveLength(4)
    // Blob order was orphan, end-a, start, left; read order must be the
    // depth-first walk (start, left via first choice, end-a) with the
    // unreachable orphan at the end.
    expect(bodies[0]).toContain('A dark cave yawned ahead.')
    expect(bodies[1]).toContain('The left path narrows.')
    expect(bodies[2]).toContain('You find the treasure.')
    expect(bodies[3]).toContain('A forgotten grotto sparkles.')
    // The unreachable section is clearly labeled and holds the orphan.
    const heading = screen.getByRole('heading', { name: 'Unreachable passages', level: 3 })
    expect(heading).toBeInTheDocument()
    expect(screen.getByText(/no choice path from the start/i)).toBeInTheDocument()
  })

  it('renders choice labels with jump buttons, and a missing-target note for dead links', async () => {
    mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
    renderAt('s1')
    expect(await screen.findByText('Go left')).toBeInTheDocument()
    expect(screen.getByText('Go right')).toBeInTheDocument()
    expect(screen.getByText('Squeeze through')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to left' })).toBeInTheDocument()
    // Two choices target end-a (from start and from left).
    expect(screen.getAllByRole('button', { name: 'Go to end-a' })).toHaveLength(2)
    // 'Peek into the crack' targets 'ghost', which is not in the blob: the
    // label still renders, with a note instead of a dead jump link.
    expect(screen.getByText('Peek into the crack')).toBeInTheDocument()
    expect(screen.getByText('missing target')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Go to ghost' })).not.toBeInTheDocument()
  })

  it('moves focus to the target passage when a choice jump button is clicked', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: 'Go to left' }))
    const passage = document.getElementById('passage-left')
    expect(passage).not.toBeNull()
    expect(document.activeElement).toBe(passage)
  })

  it('badges the start passage and endings with their kind and valence', async () => {
    mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
    renderAt('s1')
    const startBadge = await screen.findByText('Start')
    expect(document.getElementById('passage-start')).toContainElement(startBadge)
    const endingBadge = screen.getByText('Ending: success, positive')
    expect(document.getElementById('passage-end-a')).toContainElement(endingBadge)
  })

  it('shows the coverage line: total, reachable, and ending counts', async () => {
    mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
    renderAt('s1')
    expect(
      await screen.findByText('4 passages, 3 reachable from the start, 1 ending')
    ).toBeInTheDocument()
  })

  it('renders the moderation summary header with soft flags and independent review', async () => {
    renderAt('s1')
    expect(await screen.findByText('1 finding')).toBeInTheDocument()
    expect(screen.getByText('Soft flags')).toBeInTheDocument()
    expect(screen.getByText('Independent review')).toBeInTheDocument()
    expect(screen.queryByText('Hard block')).not.toBeInTheDocument()
    expect(screen.queryByText('Repaired')).not.toBeInTheDocument()
  })

  it('renders hard-block and repaired badges when the summary carries them', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        summary: {
          count: 3,
          hard_block: true,
          soft_flag: false,
          repaired: true,
          reviewer_independent: false,
        },
      },
    })
    renderAt('s1')
    expect(await screen.findByText('3 findings')).toBeInTheDocument()
    expect(screen.getByText('Hard block')).toBeInTheDocument()
    expect(screen.getByText('Repaired')).toBeInTheDocument()
    expect(screen.getByText('Not independently reviewed')).toBeInTheDocument()
    expect(screen.queryByText('Soft flags')).not.toBeInTheDocument()
  })

  it('shows a degraded-screening alert when a classifier_degraded finding is present', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        story_level_findings: [
          {
            stage: 0,
            source: 'openai',
            category: 'classifier_degraded',
            node_id: null,
            verdict: 'advisory',
            score: null,
            message: 'openai classifier unavailable: not configured',
          },
        ],
      },
    })
    renderAt('s1')
    const alert = await screen.findByText(/Automated screening was degraded/i)
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent('openai')
  })

  it('does not show a degraded alert when no classifier_degraded finding is present', async () => {
    renderAt('s1')
    await screen.findByText('1 finding')
    expect(screen.queryByText(/Automated screening was degraded/i)).not.toBeInTheDocument()
  })

  it('jumps from a flagged card to its passage in the read-through and highlights it', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: 'Show in story' }))
    const passage = document.getElementById('passage-left')
    expect(passage).not.toBeNull()
    expect(document.activeElement).toBe(passage)
    expect(passage).toHaveClass('review-node--highlight')
  })

  it('shows a note instead of a jump link when a flagged node id is not in the blob', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        flagged_passages: [{ node_id: 'vanished', prose: 'Ghost passage prose.', findings: [] }],
      },
    })
    renderAt('s1')
    expect(await screen.findByText('Ghost passage prose.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show in story' })).not.toBeInTheDocument()
    expect(screen.getByText(/not found in the story below/i)).toBeInTheDocument()
  })

  it('warns when the version was never screened', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        screened: false,
        summary: null,
        flagged_passages: [],
        story_level_findings: [],
      },
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
    expect(await screen.findByRole('heading', { name: 's1', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Prose with a malformed id survives.')).toBeInTheDocument()
    expect(screen.getByText('A normal closing passage.')).toBeInTheDocument()
    // No start_node in this blob: the walk falls back to the first kept node,
    // and the other node still renders in the unreachable section, so the
    // coverage line accounts for every kept node.
    expect(
      screen.getByText('2 passages, 1 reachable from the start, 0 endings')
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Unreachable passages', level: 3 })
    ).toBeInTheDocument()
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
    // A safety surface must say so out loud, not render an empty section.
    expect(screen.getByRole('alert')).toHaveTextContent(/no readable passages/i)
    expect(
      screen.getByText('0 passages, 0 reachable from the start, 0 endings')
    ).toBeInTheDocument()
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

  describe('version compare', () => {
    it('shows the compare toggle only when the version is greater than 1', async () => {
      // The default beforeEach mock resolves SURFACE, whose version is 1.
      renderAt('s1')
      await screen.findByRole('heading', { name: 'The Cave', level: 1 })
      expect(
        screen.queryByRole('button', { name: /Compare with version/i })
      ).not.toBeInTheDocument()
    })

    it('fetches the previous version and shows the diff summary counts on click', async () => {
      const user = userEvent.setup()
      mockCompareRoutes()
      renderAt('s1')
      const toggle = await screen.findByRole('button', { name: 'Compare with version 1' })
      await user.click(toggle)
      expect(await screen.findByText('1 passage added, 1 changed, 1 removed')).toBeInTheDocument()
    })

    it('shows a loading indicator while the comparison fetch is in flight', async () => {
      const user = userEvent.setup()
      // A no-op default keeps the type a plain function (not a nullable one)
      // so TS can track the reassignment inside the executor below; the
      // no-op is never actually invoked before it is replaced.
      let resolvePrevious: (value: { data: unknown }) => void = () => undefined
      mockGet.mockImplementation((url: string, config?: { params?: { version?: number } }) => {
        if (typeof url === 'string' && url.endsWith('/cover')) {
          return Promise.resolve({ data: { cover_status: 'none', cover_url: null } })
        }
        if (config?.params?.version === undefined) {
          return Promise.resolve({ data: CURRENT_SURFACE })
        }
        // The previous-version fetch hangs until the test resolves it below,
        // so the loading state is observable rather than racing past it.
        return new Promise((resolve) => {
          resolvePrevious = resolve
        })
      })
      renderAt('s1')
      const toggle = await screen.findByRole('button', { name: 'Compare with version 1' })
      await user.click(toggle)
      expect(await screen.findByText('Loading version 1…')).toBeInTheDocument()
      resolvePrevious({ data: BASE_SURFACE })
      expect(await screen.findByText('1 passage added, 1 changed, 1 removed')).toBeInTheDocument()
    })

    it('retries the comparison fetch after closing and reopening past a transient error', async () => {
      const user = userEvent.setup()
      let callCount = 0
      mockGet.mockImplementation((url: string, config?: { params?: { version?: number } }) => {
        if (typeof url === 'string' && url.endsWith('/cover')) {
          return Promise.resolve({ data: { cover_status: 'none', cover_url: null } })
        }
        const version = config?.params?.version
        if (version === undefined) return Promise.resolve({ data: CURRENT_SURFACE })
        callCount += 1
        // First attempt fails with a non-404 (transient) error; a retry
        // after closing and reopening the panel succeeds.
        return callCount === 1
          ? Promise.reject(new Error('network blip'))
          : Promise.resolve({ data: BASE_SURFACE })
      })
      renderAt('s1')
      const toggle = await screen.findByRole('button', { name: 'Compare with version 1' })
      await user.click(toggle)
      expect(
        await screen.findByText('We could not load the previous version for comparison.')
      ).toBeInTheDocument()
      await user.click(toggle) // close
      await user.click(toggle) // reopen: must retry, not stay stuck on the cached error
      expect(await screen.findByText('1 passage added, 1 changed, 1 removed')).toBeInTheDocument()
    })

    it('shows a graceful message when the previous version is no longer available (404)', async () => {
      const user = userEvent.setup()
      mockGet.mockImplementation((url: string, config?: { params?: { version?: number } }) => {
        if (typeof url === 'string' && url.endsWith('/cover')) {
          return Promise.resolve({ data: { cover_status: 'none', cover_url: null } })
        }
        if (config?.params?.version === undefined) {
          return Promise.resolve({ data: CURRENT_SURFACE })
        }
        return Promise.reject(notFoundError())
      })
      renderAt('s1')
      const toggle = await screen.findByRole('button', { name: 'Compare with version 1' })
      await user.click(toggle)
      expect(await screen.findByText('Version 1 is no longer available.')).toBeInTheDocument()
      // Fails gracefully, not by crashing the page.
      expect(screen.getByRole('heading', { name: 'The Cave', level: 1 })).toBeInTheDocument()
    })

    it('does not flag a passage as changed when only its choice order changed', async () => {
      // n1 has the exact same two choices (same labels, same targets) in both
      // versions, only reordered; n2 and n3 are untouched. diffNodes must
      // match diffChoices' order-insensitive semantics, so this must show as
      // zero changes, not a false-positive "changed" with an empty detail.
      const reorderBase = {
        ...BASE_SURFACE,
        blob: {
          title: 'The Cave',
          start_node: 'n1',
          nodes: [
            {
              id: 'n1',
              body: 'Opening.',
              choices: [
                { label: 'Go on', target: 'n2' },
                { label: 'Finish', target: 'n3' },
              ],
            },
            { id: 'n2', body: 'Middle passage.', choices: [] },
            {
              id: 'n3',
              body: 'The ending.',
              choices: [],
              is_ending: true,
              ending: { kind: 'success', valence: 'positive' },
            },
          ],
        },
      }
      const reorderCurrent = {
        ...reorderBase,
        version: 2,
        blob: {
          ...reorderBase.blob,
          nodes: [
            {
              id: 'n1',
              body: 'Opening.',
              choices: [
                { label: 'Finish', target: 'n3' },
                { label: 'Go on', target: 'n2' },
              ],
            },
            reorderBase.blob.nodes[1],
            reorderBase.blob.nodes[2],
          ],
        },
      }
      const user = userEvent.setup()
      mockGet.mockImplementation((url: string, config?: { params?: { version?: number } }) => {
        if (typeof url === 'string' && url.endsWith('/cover')) {
          return Promise.resolve({ data: { cover_status: 'none', cover_url: null } })
        }
        const version = config?.params?.version
        if (version === undefined) return Promise.resolve({ data: reorderCurrent })
        if (version === 1) return Promise.resolve({ data: reorderBase })
        return Promise.reject(notFoundError())
      })
      renderAt('s1')
      const toggle = await screen.findByRole('button', { name: 'Compare with version 1' })
      await user.click(toggle)
      expect(await screen.findByText('0 passages added, 0 changed, 0 removed')).toBeInTheDocument()
    })

    it('renders the auto-repaired hint when the summary carries repaired: true', async () => {
      mockGet.mockResolvedValue({
        data: { ...SURFACE, summary: { ...SURFACE.summary, repaired: true } },
      })
      renderAt('s1')
      expect(await screen.findByText('Repaired')).toBeInTheDocument()
      expect(
        screen.getByText(
          'This story was auto-repaired. Compare with the previous version to see what changed.'
        )
      ).toBeInTheDocument()
    })
  })
})
