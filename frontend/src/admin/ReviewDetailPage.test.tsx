import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReviewDetailPage } from './ReviewDetailPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, patch: mockPatch }
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

/**
 * A navigation control OUTSIDE the <Routes>, so clicking it changes the
 * :storybookId param the way auto-advance through the review queue does:
 * a route change under the same route pattern, rather than the fresh mount a
 * second renderAt() would give. What the page does with that change (remount
 * via `key`, or re-run an effect) is the thing under test, so the harness
 * must not decide it.
 */
function NextBookLink({ to }: { to: string }) {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => void navigate(to)}>
      NEXT BOOK
    </button>
  )
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
  mockPatch.mockReset()
  // RS-A5's triage markers live in localStorage, which jsdom shares across
  // every test in this file. Without this, a marker one case set would change
  // what a later case renders.
  localStorage.clear()
})

describe('ReviewDetailPage', () => {
  it('shows flagged passages with their findings', async () => {
    renderAt('s1')
    expect(await screen.findByText('possibly scary')).toBeInTheDocument()
    expect(screen.getAllByText(/A dark cave yawned ahead/).length).toBeGreaterThan(0)
    expect(screen.getByText(/The path forked/)).toBeInTheDocument()
  })

  describe('Stage B3 decision surfaces (design doc 2.6)', () => {
    it('renders ranked findings with a severity pill and an on-demand node drill-down', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          ranked_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n1',
              verdict: 'block',
              score: null,
              message: 'graphic violence',
              severity: 'high',
              node_ids: ['n1', 'n2'],
              structural: false,
              concern: 'violence',
            },
          ],
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Ranked findings' })
      expect(screen.getByText('graphic violence')).toBeInTheDocument()
      expect(screen.getByText('violence')).toBeInTheDocument()
      expect(screen.getByText('high')).toBeInTheDocument()
      // The affected nodes stay collapsed behind a <details> until expanded.
      const user = userEvent.setup()
      await user.click(screen.getByText('2 affected nodes'))
      expect(screen.getByRole('button', { name: 'n1' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'n2' })).toBeInTheDocument()
    })

    it('renders the ranked findings section above the flagged passages, even with nothing ranked', async () => {
      /*
        `RS-A2`. Two claims, one test, because they fail together in practice.

        Order: triage before prose. A ranked list that sits below a flat
        passage list is not a triage surface; it is a footnote a reviewer
        reaches after the reading they were trying to avoid.

        Unconditional: the section used to disappear when ranked_findings was
        empty, which on the four queued books whose findings are all
        low-severity advisories removed the most decision-useful section from
        exactly the books a reviewer could clear fastest. SURFACE carries
        flagged_passages and no ranked_findings, so it is that shape.
      */
      renderAt('s1')
      const ranked = await screen.findByRole('heading', { name: 'Ranked findings' })
      const flagged = screen.getByRole('heading', { name: 'Flagged passages' })
      expect(
        ranked.compareDocumentPosition(flagged) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy()
      expect(
        screen.getByText(/No findings are ranked for triage on this version/)
      ).toBeInTheDocument()
    })

    it('surfaces the classifier score on a ranked finding and stays blank when unscored', async () => {
      /*
        `RS-A2`: "advisory, violence, 0.41" lets a reviewer calibrate against
        the band threshold; "advisory, violence" does not. A deterministic,
        unscored finding must render no score rather than 0.00, so the two
        cases are asserted together: a printed 0.00 for `score: null` would
        tell the reviewer the classifier judged this passage maximally safe
        when it never scored it at all.
      */
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          ranked_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n1',
              verdict: 'advisory',
              score: 0.41,
              message: 'mild scuffle',
              severity: 'medium',
              node_ids: ['n1'],
              structural: false,
              concern: 'violence',
            },
            {
              stage: 1,
              source: 'validator',
              category: 'reading_level',
              node_id: 'n2',
              verdict: 'advisory',
              score: null,
              message: 'sentence length above band',
              severity: 'low',
              node_ids: ['n2'],
              structural: false,
              concern: null,
            },
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n2',
              verdict: 'block',
              score: 0,
              message: 'bright-line refusal',
              severity: 'high',
              node_ids: ['n2'],
              structural: false,
              concern: 'self_harm',
            },
          ],
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Ranked findings' })
      const scored = screen.getByText('mild scuffle').closest('li') as HTMLElement
      const unscored = screen.getByText('sentence length above band').closest('li') as HTMLElement
      const zero = screen.getByText('bright-line refusal').closest('li') as HTMLElement
      expect(within(scored).getByText('0.41')).toBeInTheDocument()
      expect(unscored.querySelector('.review-finding__score')).toBeNull()
      // A genuine 0 is a score, and a falsy one: rendering it by truthiness
      // would drop it, which is why the component tests typeof. Without this
      // case that distinction is a comment nothing enforces.
      expect(within(zero).getByText('0.00')).toBeInTheDocument()
    })

    it('makes a ranked finding the entry point to its own affected passages', async () => {
      /*
        `RS-A2`: the finding, not a separate flat list, is where a reviewer
        gets context. Expanding one finding's node drill-down shows that
        node's prose in place.

        This matters most for the findings `RS-A1` keeps out of
        flagged_passages: a low advisory has no passage card anywhere on the
        page, so if its prose were sourced from flagged_passages the collapsed
        lane would be the one tier with no context at all, which is the
        opposite of "counted and available for a reviewer to dig into". The
        finding below is a low advisory for exactly that reason.
      */
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          ranked_findings: [
            {
              stage: 3,
              source: 'llm_coherence',
              category: 'coherence',
              node_id: 'n2',
              verdict: 'advisory',
              score: null,
              message: 'the fork is abrupt',
              severity: 'medium',
              node_ids: ['n2'],
              structural: false,
              concern: null,
            },
          ],
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Ranked findings' })
      const row = screen.getByText('the fork is abrupt').closest('li') as HTMLElement
      // Collapsed until asked for, so the triage list itself stays scannable.
      // A closed <details> keeps its children in the DOM, so presence is the
      // wrong probe here and would pass either way; visibility is the claim.
      expect(within(row).getByText(/The path forked/)).not.toBeVisible()
      const user = userEvent.setup()
      await user.click(within(row).getByText('1 affected node'))
      expect(within(row).getByText(/The path forked/)).toBeVisible()
    })

    it('splits structural findings into their own block', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          structural_findings: [
            {
              stage: 1,
              source: 'pipeline',
              category: 'topology',
              node_id: 'n1',
              verdict: 'flag',
              score: null,
              message: 'unreachable ending',
              severity: 'medium',
              node_ids: null,
              structural: true,
              concern: null,
            },
          ],
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Structural findings' })
      expect(screen.getByText('unreachable ending')).toBeInTheDocument()
    })

    it('collapses low-priority advisories behind a toggle', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          low_advisory_findings: [
            {
              stage: 1,
              source: 'llm_engagement',
              category: 'pacing',
              node_id: 'n2',
              verdict: 'advisory',
              score: null,
              message: 'slow middle section',
              severity: 'low',
              node_ids: null,
              structural: false,
              concern: null,
            },
          ],
        },
      })
      renderAt('s1')
      const toggle = await screen.findByText('Low-priority advisories (1)')
      // Collapsed by default (no `open` attribute on the <details>).
      const details = toggle.closest('details')
      expect(details).not.toBeNull()
      expect(details).not.toHaveAttribute('open')
      const user = userEvent.setup()
      await user.click(toggle)
      expect(screen.getByText('slow middle section')).toBeInTheDocument()
    })

    it('projects validator findings read-only from the stored validation report', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          validator_findings: [
            { rule_id: 'RL-13', severity: 'warning', node_id: 'n1', message: 'reading level high' },
            { rule_id: 'PL-19', severity: 'error', node_id: null, message: 'story mean too long' },
          ],
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Validator findings' })
      expect(screen.getByText('RL-13')).toBeInTheDocument()
      expect(screen.getByText('reading level high')).toBeInTheDocument()
      expect(screen.getByText('PL-19')).toBeInTheDocument()
      expect(screen.getByText('story mean too long')).toBeInTheDocument()
    })

    it('invents no findings when the backend has not sent the additive fields', async () => {
      /*
        A pre-Stage-B stored report projects all four additive buckets empty.
        The page must not throw on the absent fields and must not manufacture
        rows, so the three optional sections stay absent.

        `RS-A2` changed one of the four: "Ranked findings" now renders
        unconditionally, with an explicit empty state instead of vanishing.
        The assertion below therefore checks the heading is present while its
        list is not, which is the distinction that matters here: an empty
        state is a statement about the book, a missing section is
        indistinguishable from a page that failed to load.
      */
      mockGet.mockResolvedValue({ data: SURFACE })
      renderAt('s1')
      await screen.findByText('possibly scary')
      expect(screen.getByRole('heading', { name: 'Ranked findings' })).toBeInTheDocument()
      expect(
        screen.getByText(/No findings are ranked for triage on this version/)
      ).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Structural findings' })).not.toBeInTheDocument()
      expect(screen.queryByText(/Low-priority advisories/)).not.toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Validator findings' })).not.toBeInTheDocument()
    })
  })

  describe('one canonical count (RS-A3)', () => {
    /*
      One book used to render four mutually inconsistent numbers: `2
      advisories` on its queue row, `4 findings` in this header, "no content
      concerns" in the gate summary, and `5 flagged` / `5 advisorys` in the
      overview footer, over 5 passage cards. Every assertion here is against
      the rendered DOM rather than the source, because Prettier-wrapped JSX
      prose defeats a source grep: a zero result for a claim AND for its
      negation means the probe is broken, not that the bug is gone.
    */
    /** The header verdict strip, one of the two places a count is shown. */
    const headerStrip = () => {
      const strip = document.querySelector('.review-summary')
      expect(strip).not.toBeNull()
      return within(strip as HTMLElement)
    }
    /** The story-overview footer, the other place a count is shown. */
    const overviewFooter = () => {
      const details = document.querySelector('.review-overview')
      expect(details).not.toBeNull()
      return within(details as HTMLElement)
    }

    const finding = (over: Record<string, unknown>) => ({
      stage: 1,
      source: 'llm_safety',
      category: 'safety',
      node_id: 'n1',
      verdict: 'advisory',
      score: null,
      message: 'a finding',
      severity: 'low',
      node_ids: ['n1'],
      structural: false,
      concern: null,
      ...over,
    })

    it('counts the findings it renders, not the report summary persisted total', async () => {
      // summary.count is `len(persisted)` from moderation/report.py::to_dict,
      // taken BEFORE the admin noise floor filters anything, so a floored
      // report leaves the header claiming rows the page never shows. 99 here
      // is deliberately impossible for this surface.
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          summary: { ...SURFACE.summary, count: 99 },
          flagged_passages: [],
          story_level_findings: [],
          ranked_findings: [
            finding({ verdict: 'block', severity: 'high', message: 'one' }),
            finding({ verdict: 'flag', severity: 'high', message: 'two' }),
          ],
        },
      })
      renderAt('s1')
      expect(await screen.findByText('2 findings')).toBeInTheDocument()
      expect(screen.queryByText('99 findings')).not.toBeInTheDocument()
    })

    it('names the passage denominator instead of leaving two bare numbers', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          ranked_findings: [finding({ verdict: 'flag', severity: 'high', message: 'one' })],
        },
      })
      renderAt('s1')
      // One finding, one passage card: both numbers are 1 here, and the point
      // is that each says what it counted. SURFACE has a single flagged
      // passage, so the scope line has something to name.
      expect(await screen.findByText('1 finding')).toBeInTheDocument()
      expect(screen.getByText('1 flagged passage below')).toBeInTheDocument()
    })

    it('gives the header and the story-overview footer the same number', async () => {
      /*
        The regression that produced Teddy's four numbers: one merged advisory
        spanning three nodes plus two flags. The footer used to count the
        fan-out (allFindings.length) while the header counted the persisted
        total, so they could not agree by construction.
      */
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          summary: { ...SURFACE.summary, count: 7 },
          ranked_findings: [
            finding({ verdict: 'flag', severity: 'high', message: 'first flag' }),
            finding({ verdict: 'flag', severity: 'medium', message: 'second flag' }),
          ],
          low_advisory_findings: [
            finding({ message: 'spans the book', node_ids: ['n1', 'n2', 'n3'] }),
          ],
        },
      })
      renderAt('s1')
      expect(await screen.findByText('3 findings')).toBeInTheDocument()
      expect(overviewFooter().getByText('3 flagged findings')).toBeInTheDocument()
      // And both surfaces' tier splits agree with the totals beside them.
      // Scoped per surface on purpose: an unscoped query throws "found
      // multiple", which would pass a weaker assertion for the wrong reason.
      expect(headerStrip().getByText('2 flags · 1 advisory')).toBeInTheDocument()
      expect(overviewFooter().getByText('2 flags · 1 advisory')).toBeInTheDocument()
    })

    it('pluralizes advisories as advisories', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          story_level_findings: [],
          low_advisory_findings: [
            finding({ message: 'first' }),
            finding({ message: 'second' }),
            finding({ message: 'third' }),
          ],
        },
      })
      renderAt('s1')
      expect(await screen.findByText('3 findings')).toBeInTheDocument()
      expect(headerStrip().getByText('3 advisories')).toBeInTheDocument()
      expect(overviewFooter().getByText('3 advisories')).toBeInTheDocument()
      expect(screen.queryByText(/advisorys/)).not.toBeInTheDocument()
    })

    it('keeps structural findings out of the flag tier, matching the backend', async () => {
      // review_surface.py excludes structural rows from flag_findings, so a
      // surface with one real flag and one structural flag must read "1 flag".
      // The overview footer used to tally them itself and said "2 flags".
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          story_level_findings: [],
          ranked_findings: [finding({ verdict: 'flag', severity: 'high', message: 'real flag' })],
          structural_findings: [
            finding({
              verdict: 'flag',
              severity: 'medium',
              message: 'report incomplete',
              structural: true,
              category: 'coverage',
            }),
          ],
        },
      })
      renderAt('s1')
      expect(await screen.findByText('2 findings')).toBeInTheDocument()
      expect(headerStrip().getByText('1 flag')).toBeInTheDocument()
      expect(overviewFooter().getByText('1 flag')).toBeInTheDocument()
      expect(screen.queryByText(/2 flags/)).not.toBeInTheDocument()
    })
  })

  describe('false-negative spot check (RS-A4)', () => {
    /**
     * A book large enough that reading it all is the failure mode: 40
     * passages in one chain. `SURFACE` has 2, which is why the section does
     * not render there (the full read-through already is the sample).
     */
    const bigSurface = (over: Record<string, unknown> = {}) => ({
      ...SURFACE,
      blob: {
        title: 'The Long Cave',
        start_node: 'p1',
        metadata: { age_band: '8-11', reading_level: 'grade_3' } as Record<string, unknown>,
        nodes: Array.from({ length: 40 }, (_, index) => ({
          id: `p${index + 1}`,
          body: `Passage ${index + 1} prose.`,
          choices:
            index === 39 ? [] : [{ id: `c${index}`, label: 'Onward', target: `p${index + 2}` }],
        })),
      },
      flagged_passages: [],
      story_level_findings: [],
      ...over,
    })

    it('labels the spot check sample as uncalibrated, beside the count', async () => {
      // Ruling 2 (2026-08-31): 15 is a working figure, not a derived one.
      // "15 of 550 passages checked" with no qualifier manufactures exactly
      // the false confidence this section exists to prevent, so the caveat
      // ships with the count or the feature does not ship.
      mockGet.mockResolvedValue({ data: bigSurface() })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Spot check for missed content' })
      const note = screen.getByRole('note')
      expect(note.textContent).toContain('15 passages drawn across')
      expect(note.textContent).toContain("story's 40 passages")
      expect(note.textContent).toContain('sample size not yet calibrated')
      expect(note.textContent).toContain('a clean sample is not evidence the book is clean')
    })

    it('draws a spread of passages, not a prefix of the story', async () => {
      mockGet.mockResolvedValue({ data: bigSurface() })
      renderAt('s1')
      const section = await screen.findByRole('heading', { name: 'Spot check for missed content' })
      const group = section.closest('.review-group')
      expect(group).not.toBeNull()
      const positions = Array.from(
        (group as HTMLElement).querySelectorAll('.review-sample__position')
      ).map((el) => Number(/passage (\d+) of/.exec(el.textContent ?? '')?.[1]))
      expect(positions).toHaveLength(15)
      // A prefix draw would end in the low single digits; this must reach the
      // far end of the story.
      expect(positions[0]).toBeLessThan(5)
      expect(positions[14]).toBeGreaterThan(35)
    })

    it('names the band a reviewer should judge the passages against', async () => {
      mockGet.mockResolvedValue({ data: bigSurface() })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Spot check for missed content' })
      expect(screen.getByText(/Judge these passages against Ages 8-11/)).toBeInTheDocument()
      expect(screen.getByText(/reading level grade_3/)).toBeInTheDocument()
    })

    it('renders no band line when the blob declares no band, rather than an empty one', async () => {
      const noMetadata = bigSurface()
      noMetadata.blob = { ...noMetadata.blob, metadata: {} }
      mockGet.mockResolvedValue({ data: noMetadata })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Spot check for missed content' })
      expect(screen.queryByText(/Judge these passages against/)).not.toBeInTheDocument()
    })

    it('excludes passages a collapsed low advisory names, not just flagged_passages', async () => {
      /*
        The trap `RS-A1` created: a low advisory is deliberately kept out of
        flagged_passages, so a node named ONLY by one is absent there. Sampling
        it as "the gate raised nothing here" would be false, and would send the
        reviewer hunting for a miss the gate had already reported.
      */
      const covered = Array.from({ length: 30 }, (_, index) => `p${index + 1}`)
      mockGet.mockResolvedValue({
        data: bigSurface({
          low_advisory_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: null,
              verdict: 'advisory',
              score: 0.1,
              message: 'mild peril throughout',
              severity: 'low',
              node_ids: covered,
              structural: false,
              concern: 'peril',
            },
          ],
        }),
      })
      renderAt('s1')
      const section = await screen.findByRole('heading', { name: 'Spot check for missed content' })
      const group = section.closest('.review-group') as HTMLElement
      const ids = Array.from(group.querySelectorAll('.review-sample__node')).map(
        (el) => el.textContent
      )
      // 10 unflagged passages exist (p31..p40); they are all drawn first, and
      // the remaining 5 are topped up from the advisory-covered ones, which
      // the UI marks so the reviewer knows they are not fresh ground.
      expect(ids).toHaveLength(15)
      const unflagged = ids.filter((id) => Number((id ?? 'p0').slice(1)) > 30)
      expect(unflagged).toHaveLength(10)
      expect(group.querySelectorAll('.flag-badge')).toHaveLength(5)
    })

    it('omits the section entirely when the whole story fits in one sitting', async () => {
      // SURFACE is a 2-passage book: the read-through below IS the sample, and
      // rendering every passage twice would add noise to the page this plan
      // exists to de-noise.
      mockGet.mockResolvedValue({ data: SURFACE })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Full story' })
      expect(
        screen.queryByRole('heading', { name: 'Spot check for missed content' })
      ).not.toBeInTheDocument()
    })
  })

  describe('what the automated gate measured (R-2)', () => {
    /*
      The approval screen showed findings without showing the measurements
      behind the routing decision, so an approver could not tell a book that
      scraped past a floor from one that cleared it comfortably. Every value
      here is a read of something already persisted on the version row.
    */
    it('shows the fill rate against the floor it was judged on', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          generation_measures: {
            fill_rate: 0.82,
            fill_rate_floor: 0.6,
            fill_rate_downgrade: false,
            safety_concerns: [],
          },
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'What the automated gate measured' })
      const block = document.getElementById('generation-measures')
      expect(block?.textContent).toContain('82%')
      expect(block?.textContent).toContain('60%')
    })

    it('names the fill floor as the reason for review when it was breached', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          generation_measures: {
            fill_rate: 0.41,
            fill_rate_floor: 0.6,
            fill_rate_downgrade: true,
            safety_concerns: [],
          },
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'What the automated gate measured' })
      expect(screen.getByText(/below the fill floor/i)).toBeInTheDocument()
    })

    it('says the fill rate was not recorded rather than showing it as zero', async () => {
      // A book with no measurement is not a book that filled nothing: an
      // imported story, or one generated before the rate was stamped.
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          generation_measures: {
            fill_rate: null,
            fill_rate_floor: null,
            fill_rate_downgrade: false,
            safety_concerns: [],
          },
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'What the automated gate measured' })
      const block = document.getElementById('generation-measures')
      expect(block?.textContent).toMatch(/not recorded/i)
      expect(block?.textContent).not.toContain('0%')
    })

    it('shows a measured fill rate of zero rather than calling it unrecorded', async () => {
      // The inverse of the test above, and the reading an approver most needs:
      // nothing filled. Zero is the value a falsy check silently converts into
      // "not recorded", which would present a total generation failure as an
      // ordinary missing measurement.
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          generation_measures: {
            fill_rate: 0,
            fill_rate_floor: 0.6,
            fill_rate_downgrade: true,
            safety_concerns: [],
          },
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'What the automated gate measured' })
      const block = document.getElementById('generation-measures')
      expect(block?.textContent).toContain('0%')
      expect(block?.textContent).not.toMatch(/not recorded/i)
      expect(screen.getByText(/below the fill floor/i)).toBeInTheDocument()
    })

    it('rolls up the moderation gate concerns with their counts', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          generation_measures: {
            fill_rate: 0.9,
            fill_rate_floor: 0.6,
            fill_rate_downgrade: false,
            safety_concerns: [
              { concern: 'safety', count: 3 },
              { concern: 'pacing', count: 1 },
            ],
          },
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'What the automated gate measured' })
      const block = document.getElementById('generation-measures')
      // Concern and count together: `toContain('3')` alone also matched the
      // '3' inside an unrelated percentage elsewhere in the block.
      expect(block?.textContent).toContain('safety (3)')
      expect(block?.textContent).toContain('pacing (1)')
    })

    it('states plainly that the gate raised no content concerns', async () => {
      // The empty case must read as a measured result, not as a missing
      // section a reviewer might mistake for "nothing ran".
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          generation_measures: {
            fill_rate: 0.9,
            fill_rate_floor: 0.6,
            fill_rate_downgrade: false,
            safety_concerns: [],
          },
        },
      })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'What the automated gate measured' })
      // `RS-A3`: the old copy said "The moderation gate raised no content
      // concerns" while the findings sections rendered below it. The line
      // reports only LABELLED safety concerns, so it now says so.
      expect(screen.getByText(/no safety concern labels were recorded/i)).toBeInTheDocument()
      expect(screen.queryByText(/raised no content concerns/i)).not.toBeInTheDocument()
    })

    it('renders nothing at all when an older backend omits the block', async () => {
      mockGet.mockResolvedValue({ data: SURFACE })
      renderAt('s1')
      await screen.findByText('possibly scary')
      expect(
        screen.queryByRole('heading', { name: 'What the automated gate measured' })
      ).not.toBeInTheDocument()
    })
  })

  it('renders sentinels visibly for the reviewer', async () => {
    // ADR-023 section 10: markers are shown DELIBERATELY in review and never in
    // the reader. This asserts the negative, that the admin surface does not
    // resolve, so a future refactor cannot quietly route review prose through the
    // reader's resolver.
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        blob: {
          ...SURFACE.blob,
          nodes: [
            { ...SURFACE.blob.nodes[0], body: 'Then {~HERO:Explorer~} ran.' },
            SURFACE.blob.nodes[1],
          ],
        },
      },
    })
    renderAt('s1')
    expect(await screen.findByText(/\{~HERO:Explorer~\}/)).toBeInTheDocument()
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
    // `RS-A3`: the count comes from the rendered surface (one finding here),
    // NOT from summary.count, which is deliberately 3 in this fixture. See
    // "counts the findings it renders, not the report's persisted total".
    expect(await screen.findByText('1 finding')).toBeInTheDocument()
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

  it('shows queue position and auto-advances to the next item after a decision (UX-A1)', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/admin/review/s1', state: { reviewQueue: ['s1', 's2'] } }]}
      >
        <Routes>
          <Route path="/admin/review/:storybookId" element={<ReviewDetailPage />} />
          <Route path="/admin" element={<div>CONSOLE HOME</div>} />
        </Routes>
      </MemoryRouter>
    )
    // Position indicator for the first item.
    expect(await screen.findByText(/Reviewing 1 of 2 in the queue/i)).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))

    // Auto-advanced to s2 (the next item), not back to the console home.
    expect(await screen.findByText(/Reviewing 2 of 2 in the queue/i)).toBeInTheDocument()
    expect(screen.queryByText('CONSOLE HOME')).not.toBeInTheDocument()
  })

  it('clears the approve dialog and its override reason when the queue advances to a new story', async () => {
    // Regression test for the queue-auto-advance state leak: s1 needs an
    // override reason (a block finding), s2 is clean and needs none. Before
    // the fix, the same component instance carried the open dialog and s1's
    // override text straight into s2's render.
    const user = userEvent.setup()
    const s1NeedsOverride = {
      ...SURFACE,
      storybook_id: 's1',
      flagged_passages: [],
      story_level_findings: [
        {
          stage: 1,
          source: 'llm_safety',
          category: 'safety',
          node_id: 'n1',
          verdict: 'block',
          score: null,
          message: 'graphic violence',
        },
      ],
    }
    const s2Clean = {
      ...SURFACE,
      storybook_id: 's2',
      flagged_passages: [],
      story_level_findings: [],
    }
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.startsWith('/v1/storybooks/s2/')) {
        return Promise.resolve({ data: s2Clean })
      }
      return Promise.resolve({ data: s1NeedsOverride })
    })
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })

    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/admin/review/s1', state: { reviewQueue: ['s1', 's2'] } }]}
      >
        <Routes>
          <Route path="/admin/review/:storybookId" element={<ReviewDetailPage />} />
          <Route path="/admin" element={<div>CONSOLE HOME</div>} />
        </Routes>
      </MemoryRouter>
    )

    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.type(
      screen.getByLabelText(/override reason/i),
      'Reviewed the flagged passage in full; appropriate for this reader.'
    )
    const confirm = await screen.findByRole('button', { name: /Confirm approve/i })
    expect(confirm).toBeEnabled()
    await user.click(confirm)

    // Auto-advanced to s2, a clean surface that needs no override.
    await screen.findByText(/Reviewing 2 of 2 in the queue/i)

    // The dialog and its override reason must not have carried over: no
    // confirm button (and no override textarea) should render until the
    // reviewer explicitly reopens Approve for this new, unrelated story.
    expect(screen.queryByRole('button', { name: /Confirm approve/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/override reason/i)).not.toBeInTheDocument()
  })

  it('re-enables the confirm button for a second action after the first succeeds', async () => {
    // Regression test: `submitting` was previously reset to false only in
    // runAction's catch block, never on the success path, so every Confirm
    // button stayed permanently disabled after one successful action.
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/admin/review/s1', state: { reviewQueue: ['s1', 's2'] } }]}
      >
        <Routes>
          <Route path="/admin/review/:storybookId" element={<ReviewDetailPage />} />
          <Route path="/admin" element={<div>CONSOLE HOME</div>} />
        </Routes>
      </MemoryRouter>
    )

    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))

    // Auto-advanced to s2 (same default SURFACE fixture, no override needed).
    await screen.findByText(/Reviewing 2 of 2 in the queue/i)
    await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
    expect(await screen.findByRole('button', { name: /Confirm approve/i })).toBeEnabled()
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

  it('requires a reason before sending back, and defaults the reason code to other', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'needs_revision' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /Send Back/i }))
    const submit = await screen.findByRole('button', { name: /Confirm send back/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/reason for sending back/i), 'too intense for this age')
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/send-back', {
      reason: 'too intense for this age',
      reason_code: 'other',
    })
    expect(await screen.findByText('CONSOLE HOME')).toBeInTheDocument()
  })

  it('sends the selected reason code alongside the reason', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'needs_revision' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /Send Back/i }))
    await user.selectOptions(screen.getByLabelText(/reason category/i), 'reading_level')
    await user.type(screen.getByLabelText(/reason for sending back/i), 'too advanced for band')
    const submit = await screen.findByRole('button', { name: /Confirm send back/i })
    await user.click(submit)
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/send-back', {
      reason: 'too advanced for band',
      reason_code: 'reading_level',
    })
  })

  it('keeps send back disabled for a whitespace-only reason', async () => {
    const user = userEvent.setup()
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /Send Back/i }))
    const submit = await screen.findByRole('button', { name: /Confirm send back/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/reason for sending back/i), '   ')
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

  // ---------------------------------------------------------------------
  // A16 (capability-register.md), H2 human-approval half
  // (security-hardening-plan-2026-07.md): a generated cover sits at
  // cover_status "pending_review" until an admin reviews the image on this
  // surface and approves it. These tests cover the review-image render and
  // the approve action; the real authz boundary (a non-admin gets 403 from
  // the backend regardless of what this page renders) is covered server-side
  // by tests/integration/test_cover_api.py::test_approve_cover_non_admin_forbidden.
  // ---------------------------------------------------------------------

  it('renders the pending cover image and an Approve action when a cover is pending review', async () => {
    mockGet.mockImplementation((url: string) =>
      typeof url === 'string' && url.endsWith('/cover')
        ? Promise.resolve({
            data: { cover_status: 'pending_review', cover_url: 'https://x/pending.webp' },
          })
        : Promise.resolve({ data: SURFACE })
    )
    renderAt('s1')
    const image = await screen.findByRole('img', { name: /pending review/i })
    expect(image).toHaveAttribute('src', 'https://x/pending.webp')
    expect(screen.getByRole('button', { name: /Approve cover/i })).toBeEnabled()
  })

  it('offers the Approve action without an image when a pending cover has no URL yet', async () => {
    // #EDGE: external resources: R2 can be unconfigured or briefly unavailable
    // between the job finishing and a presigned URL being issued, so
    // cover_status can reach "pending_review" while cover_url is still null.
    // The preview must not render a broken <img src="">; it renders the
    // Approve action alone so the reviewer can still act on record.
    // #VERIFY: this test. It asserts the Approve action is present and enabled
    // while no cover image is rendered, so deleting the coverUrl guard (which
    // would emit an <img> with no src but a real alt, still role="img") fails
    // here.
    mockGet.mockImplementation((url: string) =>
      typeof url === 'string' && url.endsWith('/cover')
        ? Promise.resolve({ data: { cover_status: 'pending_review', cover_url: null } })
        : Promise.resolve({ data: SURFACE })
    )
    renderAt('s1')
    const approveButton = await screen.findByRole('button', { name: /Approve cover/i })
    expect(approveButton).toBeEnabled()
    expect(screen.queryByRole('img', { name: /Generated cover for/i })).not.toBeInTheDocument()
  })

  it('renders the cover approval above the fold, below the verdict strip and safety alerts', async () => {
    // #ASSUME: UI state: the whole point of this block's placement is that a
    // reviewer sees an outstanding cover decision without scrolling past every
    // passage and the full story text. A code comment cannot enforce that, so
    // assert DOM order directly: the block must follow the moderation verdict
    // strip and precede the "Full story" section it used to sit below.
    //
    // The third assertion pins the other half of the ordering ruling: a
    // classifier_degraded alert says part of the automated safety net never
    // ran, which outranks a cover decision, so the cover block must fall
    // BELOW that alert and not above it. Without this assertion the two
    // remaining checks are satisfied by either order, since both elements sit
    // between the verdict strip and "Full story".
    // #VERIFY: this test.
    mockGet.mockImplementation((url: string) =>
      typeof url === 'string' && url.endsWith('/cover')
        ? Promise.resolve({
            data: { cover_status: 'pending_review', cover_url: 'https://r2.example/c.png' },
          })
        : Promise.resolve({
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
    )
    const { container } = renderAt('s1')
    await screen.findByRole('button', { name: /Approve cover/i })

    const summary = container.querySelector('.review-summary')
    const cover = container.querySelector('.review-cover-preview')
    expect(summary).not.toBeNull()
    expect(cover).not.toBeNull()
    if (!summary || !cover) return

    const fullStory = screen.getByRole('heading', { name: /Full story/i })
    const degraded = screen.getByText(/Automated screening was degraded/i)
    const following = Node.DOCUMENT_POSITION_FOLLOWING

    // strip -> degraded alert -> cover -> full story, in that order
    expect(summary.compareDocumentPosition(cover) & following).toBeTruthy()
    expect(cover.compareDocumentPosition(fullStory) & following).toBeTruthy()
    expect(degraded.compareDocumentPosition(cover) & following).toBeTruthy()
  })

  it('approves a pending cover and reflects the approved state', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      typeof url === 'string' && url.endsWith('/cover')
        ? Promise.resolve({
            data: { cover_status: 'pending_review', cover_url: 'https://x/pending.webp' },
          })
        : Promise.resolve({ data: SURFACE })
    )
    mockPost.mockResolvedValue({
      data: {
        cover_status: 'ready',
        cover_url: 'https://x/ready.webp',
        cover_approved_by: 'admin-1',
        cover_approved_at: '2026-07-28T00:00:00Z',
      },
    })
    renderAt('s1')
    const approveButton = await screen.findByRole('button', { name: /Approve cover/i })
    await user.click(approveButton)
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/versions/1/cover/approve')
    const approvedImage = await screen.findByRole('img', { name: /approved cover/i })
    expect(approvedImage).toHaveAttribute('src', 'https://x/ready.webp')
    expect(screen.getByText(/cover approved\./i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Approve cover/i })).not.toBeInTheDocument()
  })

  it('surfaces an alert when cover approval fails, and keeps the cover pending', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) =>
      typeof url === 'string' && url.endsWith('/cover')
        ? Promise.resolve({
            data: { cover_status: 'pending_review', cover_url: 'https://x/pending.webp' },
          })
        : Promise.resolve({ data: SURFACE })
    )
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderAt('s1')
    const approveButton = await screen.findByRole('button', { name: /Approve cover/i })
    await user.click(approveButton)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not approve the cover/i)
    // The cover stays pending: the review image and Approve action remain.
    expect(screen.getByRole('img', { name: /pending review/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Approve cover/i })).toBeEnabled()
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

  it('archives a published story and returns to the console', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
    mockPost.mockResolvedValue({ data: { id: 's1', status: 'archived' } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /^Archive$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm archive/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/archive')
    expect(await screen.findByText('CONSOLE HOME')).toBeInTheDocument()
  })

  it.each(['in_review', 'draft', 'needs_revision'] as const)(
    'disables Archive for a %s story while keeping its label',
    async (status) => {
      mockGet.mockResolvedValue({ data: { ...SURFACE, status } })
      renderAt('s1')
      const archive = await screen.findByRole('button', { name: /^Archive$/i })
      expect(archive).toBeDisabled()
      const hint = screen.getByText(/only published stories can be archived/i)
      expect(archive).toHaveAttribute('aria-describedby', hint.id)
    }
  )

  it('keeps Archive enabled for a published story', async () => {
    mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
    renderAt('s1')
    expect(await screen.findByRole('button', { name: /^Archive$/i })).toBeEnabled()
  })

  it('surfaces a backend rejection when archive fails without navigating away', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 409 } })
    renderAt('s1')
    await user.click(await screen.findByRole('button', { name: /^Archive$/i }))
    await user.click(await screen.findByRole('button', { name: /Confirm archive/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not archive/i)
    expect(screen.queryByText('CONSOLE HOME')).not.toBeInTheDocument()
  })

  describe('re-screen (register A4)', () => {
    it.each(['in_review', 'draft', 'needs_revision'] as const)(
      'disables Re-screen for a %s story while keeping its label',
      async (status) => {
        mockGet.mockResolvedValue({ data: { ...SURFACE, status } })
        renderAt('s1')
        const rescreen = await screen.findByRole('button', { name: /^Re-screen$/i })
        expect(rescreen).toBeDisabled()
        const hint = screen.getByText(/only published stories can be re-screened/i)
        expect(rescreen).toHaveAttribute('aria-describedby', hint.id)
      }
    )

    it('keeps Re-screen enabled for a published story', async () => {
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      renderAt('s1')
      expect(await screen.findByRole('button', { name: /^Re-screen$/i })).toBeEnabled()
    })

    it('re-screens a published story and shows the outcome (happy path)', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      mockPost.mockResolvedValue({
        data: {
          checked: 1,
          passed: 0,
          flagged: 1,
          errored: 0,
          results: [
            {
              storybook_id: 's1',
              version: 1,
              outcome: 'flagged',
              reasons: ['band_profile: reading level exceeds threshold'],
              error: null,
            },
          ],
        },
      })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Re-screen$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm re-screen/i }))
      expect(mockPost).toHaveBeenCalledWith('/v1/admin/rescreen', { storybook_ids: ['s1'] })
      // Scoped to the dialog: the page's "Story overview" panel already
      // renders an unrelated "1 flagged" badge for this fixture's finding,
      // so an unscoped query would match both.
      const dialog = await screen.findByRole('status')
      expect(within(dialog).getByText('flagged')).toBeInTheDocument()
      expect(within(dialog).getByText(/reading level exceeds threshold/i)).toBeInTheDocument()
      // The story stays put; a re-screen never navigates away or changes status.
      expect(screen.queryByText('CONSOLE HOME')).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /^Close$/i }))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('surfaces a backend rejection when re-screen fails', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Re-screen$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm re-screen/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not re-screen/i)
      expect(screen.queryByText('CONSOLE HOME')).not.toBeInTheDocument()
    })

    it('reports an empty sweep when the story was skipped (no longer published)', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      mockPost.mockResolvedValue({
        data: { checked: 0, passed: 0, flagged: 0, errored: 0, results: [] },
      })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Re-screen$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm re-screen/i }))
      expect(await screen.findByText(/not included in the sweep/i)).toBeInTheDocument()
    })

    it('resets a prior error when the dialog is reopened', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Re-screen$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm re-screen/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not re-screen/i)
      await user.click(screen.getByRole('button', { name: /^Cancel$/i }))
      await user.click(await screen.findByRole('button', { name: /^Re-screen$/i }))
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  it('shows an error state when the review surface fails to load', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderAt('s1')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not load this story for review/i
    )
    expect(screen.queryByRole('button', { name: /^Approve$/i })).not.toBeInTheDocument()
  })

  // The "Story-level notes" section (which rendered story_level_findings
  // directly) was removed in Stage B3 as a pure duplicate: ranked_findings
  // and structural_findings are built from the same FindingView objects that
  // populate story_level_findings, so a story-level finding now reaches the
  // admin surface through one of those two sections instead. This test used
  // to assert the finding under a "Story-level notes" heading; it now
  // asserts the same finding reaches the reviewer under "Ranked findings"
  // (non-structural findings land there).
  it('surfaces a story-level finding under ranked findings', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...SURFACE,
        ranked_findings: [
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
    expect(await screen.findByRole('heading', { name: 'Ranked findings' })).toBeInTheDocument()
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

  describe('story-overview skim panel (G5)', () => {
    it('shows a collapsible overview above the flagged passages with a flagged-count badge', async () => {
      renderAt('s1')
      const overviewSummary = await screen.findByText('Story overview')
      const details = overviewSummary.closest('details.review-overview')
      expect(details).not.toBeNull()
      // Open by default: this IS the skim entry point, read before the
      // flagged-passages/full-story sections below it.
      expect(details).toHaveAttribute('open')
      const overview = within(details as HTMLElement)
      // SURFACE has one flagged passage with one 'flag'-verdict finding.
      // `RS-A3`: "1 flagged finding", not a bare "1 flagged": this footer and
      // the header strip count the same population and now say which.
      expect(overview.getByText('1 flagged finding')).toBeInTheDocument()
    })

    it('derives node/ending counts and branch shape from the blob', async () => {
      mockGet.mockResolvedValue({ data: TRAVERSAL_SURFACE })
      renderAt('s1')
      const overviewSummary = await screen.findByText('Story overview')
      const details = overviewSummary.closest('details.review-overview')
      const overview = within(details as HTMLElement)
      // TRAVERSAL_SURFACE's blob has 4 kept nodes and one ending (end-a).
      expect(overview.getByText('4')).toBeInTheDocument()
      expect(overview.getByText('1')).toBeInTheDocument()
      // start has two choices (a decision point) and end-a is one hop away.
      expect(overview.getByText(/Starts at "start"/)).toBeInTheDocument()
      expect(overview.getByText(/1 decision point/)).toBeInTheDocument()
    })
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
      // The dialog closes and the refreshed surface's prose is now shown.
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
      // The dialog stays open (the edit was rejected) and the original prose
      // is still what the page shows -- the stored blob was never touched.
      expect(within(dialog).getByLabelText('Passage text')).toHaveValue('A dark cave yawned ahead.')
    })

    it('surfaces a generic error for a non-gate failure (e.g. 500) without pretending it is a rule violation', async () => {
      const user = userEvent.setup()
      mockPatch.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      await user.click(editButtons[0])

      const dialog = await screen.findByRole('dialog', { name: 'Edit passage n1' })
      await user.click(within(dialog).getByRole('button', { name: 'Save' }))

      expect(
        await within(dialog).findByText('We could not save this edit. Please try again.')
      ).toBeInTheDocument()
    })

    it('disables the Edit affordance when the story is not in_review or needs_revision', async () => {
      mockGet.mockResolvedValue({ data: { ...SURFACE, status: 'published' } })
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      for (const button of editButtons) {
        expect(button).toBeDisabled()
      }
    })
  })

  describe('unusable-report banner, override reason, author-declared label', () => {
    it('shows a moderation-unavailable banner instead of a passage wall', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          report_unusable: true,
          flagged_passages: [],
          structural_findings: [
            {
              stage: 1,
              source: 'pipeline',
              category: 'fail_safe',
              node_id: null,
              verdict: 'flag',
              score: null,
              message: 'moderation pipeline could not produce a report',
              severity: 'medium',
              node_ids: null,
              structural: true,
              concern: null,
            },
          ],
        },
      })
      renderAt('s1')
      expect(await screen.findByText(/re-run moderation before reviewing/i)).toBeInTheDocument()
    })

    it('shows a cause-neutral unusable-report banner regardless of which cause produced it', async () => {
      // moderation_report_unusable() (moderation/report.py) already covers at
      // least four distinct causes: an absent report, a malformed report or
      // finding entry, a non-independent/mock reviewer, and artifact-only
      // findings. The banner must tell the reviewer what to do, not assert
      // which of those caused it, since naming one is wrong for the other
      // three and this list has already grown once. This fixture uses the
      // non-independent-reviewer cause specifically, one the banner used to
      // misdescribe as "pipeline fail-safe artifacts".
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          report_unusable: true,
          flagged_passages: [],
          story_level_findings: [],
        },
      })
      renderAt('s1')
      const banner = await screen.findByRole('alert')
      expect(banner).toHaveTextContent(/cannot be relied on for a content judgment/i)
      expect(banner).toHaveTextContent(/re-run moderation before reviewing/i)
      expect(banner).not.toHaveTextContent(/pipeline fail-safe artifacts/i)
    })

    it('disables Approve and directs the reviewer to re-run moderation when the report is unusable, without disabling Re-screen for an unrelated reason', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          report_unusable: true,
        },
      })
      renderAt('s1')

      const approve = await screen.findByRole('button', { name: /^Approve$/i })
      expect(approve).toBeDisabled()
      // Accessible reason: a screen-reader user hears why Approve is greyed
      // out, not just that it is. Deliberately does not name "Re-screen": that
      // action is published-only and never rewrites moderation_report, so it
      // would not fix this even where it is enabled (see the comment above
      // this hint in ReviewDetailPage.tsx).
      const hint = await screen.findByText(/approval is blocked until moderation is re-run/i)
      expect(approve).toHaveAttribute('aria-describedby', hint.id)

      // Defense in depth: clicking the (disabled) Approve control cannot open
      // the dialog, so there is no confirm button to guarantee a 400 on.
      expect(screen.queryByRole('button', { name: /Confirm approve/i })).not.toBeInTheDocument()

      // Re-screen itself is untouched by this fix: it is still on the page,
      // still gated solely by its own published-only precondition (this
      // fixture is `in_review`, matching the unusable-report banner test
      // above), not hidden or newly disabled because of report_unusable.
      const rescreen = await screen.findByRole('button', { name: /^Re-screen$/i })
      expect(rescreen).toBeDisabled()
      expect(rescreen).toHaveAttribute('aria-describedby', 'review-rescreen-disabled-hint')
    })

    it('requires an override reason before approving over a block finding', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          story_level_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n1',
              verdict: 'block',
              score: null,
              message: 'graphic violence',
            },
          ],
        },
      })
      mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      const confirm = await screen.findByRole('button', { name: /Confirm approve/i })
      expect(confirm).toBeDisabled()
      await user.type(
        screen.getByLabelText(/override reason/i),
        'Reviewed the flagged passage in full; appropriate for 13-16.'
      )
      expect(confirm).toBeEnabled()
      await user.click(confirm)
      expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
        visibility: 'family',
        override_reason: 'Reviewed the flagged passage in full; appropriate for 13-16.',
      })
    })

    it('requires an override reason before approving over a high-severity flag finding', async () => {
      // needsOverride's other arm (verdict flag + severity high). A block-only
      // test cannot tell a correctly-scoped predicate from one that dropped
      // this clause entirely; the backend pins both directions
      // (test_approve_over_block_* and test_approve_over_high_flag_*).
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          story_level_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n1',
              verdict: 'flag',
              severity: 'high',
              score: null,
              message: 'intense peril',
            },
          ],
        },
      })
      mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      const confirm = await screen.findByRole('button', { name: /Confirm approve/i })
      expect(confirm).toBeDisabled()
      await user.type(
        screen.getByLabelText(/override reason/i),
        'Reviewed the flagged passage in full; peril is age-appropriate.'
      )
      expect(confirm).toBeEnabled()
      await user.click(confirm)
      expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
        visibility: 'family',
        override_reason: 'Reviewed the flagged passage in full; peril is age-appropriate.',
      })
    })

    it('does not require an override reason for a flag below high severity', async () => {
      // Negative-direction pin: a regression that widened needsOverride to
      // every flag (not just high-severity ones) would still pass every
      // other test in this describe block, since they only exercise verdicts
      // that DO require an override.
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          story_level_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n1',
              verdict: 'flag',
              severity: 'medium',
              score: null,
              message: 'mild tension',
            },
          ],
        },
      })
      mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      const confirm = await screen.findByRole('button', { name: /Confirm approve/i })
      expect(confirm).toBeEnabled()
      expect(screen.queryByLabelText(/override reason/i)).not.toBeInTheDocument()
      await user.click(confirm)
      expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', { visibility: 'family' })
    })

    it('describes why Confirm approve is disabled for a too-short override reason', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          story_level_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n1',
              verdict: 'block',
              score: null,
              message: 'graphic violence',
            },
          ],
        },
      })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      const confirm = await screen.findByRole('button', { name: /Confirm approve/i })
      const hint = await screen.findByText(/explain why it is appropriate to approve anyway/i)
      expect(confirm).toHaveAttribute('aria-describedby', hint.id)
      await user.type(
        screen.getByLabelText(/override reason/i),
        'Reviewed the flagged passage in full.'
      )
      expect(confirm).not.toHaveAttribute('aria-describedby')
    })

    it('surfaces a rule-specific message when the backend rejects approval for needing an override reason', async () => {
      // The reason this rule is reachable at all even through a correct
      // client: needsOverride is computed once from the surface loaded at
      // page-open and never revalidated before submit, so a concurrent
      // change to the finding's severity between load and submit can still
      // reach this rule on the backend's own re-check.
      const user = userEvent.setup()
      mockPost.mockRejectedValue({
        isAxiosError: true,
        response: {
          status: 400,
          data: {
            error: 'BusinessLogicError',
            message: 'a severe finding requires an override reason',
            code: 'BUSINESS_RULE_VIOLATION',
            details: { rule: 'approve_requires_override_reason' },
          },
        },
      })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(
        /still needs a written override reason/i
      )
    })

    it('surfaces a rule-specific message when the backend rejects approval for an unusable report', async () => {
      // Reachable despite the Approve button being disabled for a surface
      // that already reads unusable: report_unusable is read once at
      // page-open, so a re-moderation that lands between load and submit
      // reaches this rule on the backend's own re-check.
      const user = userEvent.setup()
      mockPost.mockRejectedValue({
        isAxiosError: true,
        response: {
          status: 400,
          data: {
            error: 'BusinessLogicError',
            message: 'moderation report is unusable',
            code: 'BUSINESS_RULE_VIOLATION',
            details: { rule: 'approve_with_unusable_moderation' },
          },
        },
      })
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(
        /Moderation for this story is unavailable/i
      )
    })

    /*
     * The three cases below drive the arms of businessRuleOf() that a
     * well-formed backend rejection never reaches. Each one must degrade to
     * the cause-neutral banner: naming a rule we did not actually read would
     * tell a reviewer to fix the wrong thing, and is worse than saying
     * nothing specific. The negative assertion is the point of each test,
     * since the fallback string is what a crash or a misparse would also
     * fail to produce.
     */
    it.each([
      ['a non-axios rejection', new Error('network stack blew up')],
      [
        'a rejection whose details are null',
        {
          isAxiosError: true,
          response: {
            status: 400,
            data: { error: 'BusinessLogicError', message: 'nope', details: null },
          },
        },
      ],
      [
        'a rejection whose rule is not a string',
        {
          isAxiosError: true,
          response: {
            status: 400,
            data: { error: 'BusinessLogicError', message: 'nope', details: { rule: 42 } },
          },
        },
      ],
    ])('falls back to the cause-neutral approve error for %s', async (_label, rejection) => {
      const user = userEvent.setup()
      mockPost.mockRejectedValue(rejection)
      renderAt('s1')
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      await user.click(await screen.findByRole('button', { name: /Confirm approve/i }))
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(/We could not approve this story/i)
      expect(alert).not.toHaveTextContent(/override reason/i)
      expect(alert).not.toHaveTextContent(/Moderation for this story is unavailable/i)
    })

    it('labels content flags as author-declared', async () => {
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          blob: {
            ...SURFACE.blob,
            metadata: { content_flags: { violence: 'mild', scariness: 'none', peril: 'moderate' } },
          },
        },
      })
      renderAt('s1')
      expect(await screen.findByText(/author-declared/i)).toBeInTheDocument()
    })
  })

  describe('client-local finding triage (RS-A5)', () => {
    const BLOCK_FINDING = {
      stage: 1,
      source: 'llm_safety',
      category: 'safety',
      node_id: 'n1',
      verdict: 'block',
      score: null,
      message: 'graphic violence',
      severity: 'high',
      node_ids: ['n1'],
      structural: false,
      concern: 'violence',
    }
    const FLAG_FINDING = {
      stage: 1,
      source: 'llm_safety',
      category: 'safety',
      node_id: 'n2',
      verdict: 'flag',
      score: null,
      message: 'moderate peril',
      severity: 'medium',
      node_ids: ['n2'],
      structural: false,
      concern: 'peril',
    }

    /**
     * A block finding, so `needsOverride` is true and the approve path has a
     * precondition a broken triage implementation could plausibly satisfy.
     *
     * Both findings appear TWICE, in `ranked_findings` and in the fan-out
     * population, because that is the shape the backend actually produces:
     * `_route_findings` fans every non-low-advisory finding out into
     * `flagged_passages` (or `story_level_findings` when it names no node) and
     * ALSO feeds it to `_rank_and_split`. A fixture carrying the block only in
     * `ranked_findings` would leave `needsOverride` false, and this test would
     * then pass for the wrong reason: no override was ever required.
     */
    const TRIAGE_SURFACE = {
      ...SURFACE,
      story_level_findings: [],
      flagged_passages: [
        { node_id: 'n1', prose: 'A dark cave yawned ahead.', findings: [BLOCK_FINDING] },
        { node_id: 'n2', prose: 'The path forked left and right.', findings: [FLAG_FINDING] },
      ],
      ranked_findings: [BLOCK_FINDING, FLAG_FINDING],
    }

    it('marking every finding reviewed changes nothing about approval', async () => {
      // #CRITICAL: security: triage is browser-local state a cleared cache can
      // wipe. If it ever became an input to approval, a cache eviction would
      // silently reset a safety decision. This is the test both
      // findingTriageStore.ts and RankedFinding's `triage` prop cite.
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: TRIAGE_SURFACE })
      mockPost.mockResolvedValue({ data: { id: 's1', status: 'published' } })
      renderAt('s1')

      const toggles = await screen.findAllByRole('button', { name: /Mark reviewed/i })
      expect(toggles).toHaveLength(2)
      for (const toggle of toggles) await user.click(toggle)
      expect(screen.getAllByRole('button', { name: /^Reviewed$/i })).toHaveLength(2)

      // The override requirement is untouched: confirm is still disabled, and
      // still needs the reason the backend demands.
      await user.click(await screen.findByRole('button', { name: /^Approve$/i }))
      const confirm = await screen.findByRole('button', { name: /Confirm approve/i })
      expect(confirm).toBeDisabled()
      await user.type(
        screen.getByLabelText(/override reason/i),
        'Read both flagged passages in full; appropriate for the band.'
      )
      expect(confirm).toBeEnabled()
      await user.click(confirm)
      // And the request body carries no trace of the triage state.
      expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
        visibility: 'family',
        override_reason: 'Read both flagged passages in full; appropriate for the band.',
      })
    })

    it('names the triage state as browser-local and non-gating', async () => {
      // The affordance is only safe if the reviewer knows what it is not. A
      // toggle that reads as a decision invites treating an untoggled finding
      // as an unresolved gate.
      mockGet.mockResolvedValue({ data: TRIAGE_SURFACE })
      renderAt('s1')
      const progress = await screen.findByText(/marked reviewed in this browser/i)
      expect(progress).toHaveTextContent('0 of 2 findings marked reviewed')
      expect(progress).toHaveTextContent(/no effect on approval/i)
    })

    it('counts marked findings as the reviewer works through the list', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: TRIAGE_SURFACE })
      renderAt('s1')
      const toggles = await screen.findAllByRole('button', { name: /Mark reviewed/i })
      await user.click(toggles[0])
      expect(screen.getByText(/marked reviewed in this browser/i)).toHaveTextContent(
        '1 of 2 findings marked reviewed'
      )
      // Toggling back off decrements: a mis-click must be recoverable, or the
      // count stops meaning "where I am" and starts meaning "what I clicked".
      await user.click(screen.getByRole('button', { name: /^Reviewed$/i }))
      expect(screen.getByText(/marked reviewed in this browser/i)).toHaveTextContent(
        '0 of 2 findings marked reviewed'
      )
    })

    it('keeps a marker across a reload of the same book and version', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: TRIAGE_SURFACE })
      const first = renderAt('s1')
      const toggles = await screen.findAllByRole('button', { name: /Mark reviewed/i })
      await user.click(toggles[0])
      first.unmount()

      renderAt('s1')
      // Proves the load effect reads the store back, not just that the store
      // round-trips (findingTriageStore.test.ts pins that separately).
      expect(await screen.findByRole('button', { name: /^Reviewed$/i })).toBeInTheDocument()
      expect(screen.getByText(/marked reviewed in this browser/i)).toHaveTextContent(
        '1 of 2 findings marked reviewed'
      )
    })

    it('does not carry a marker onto a different book', async () => {
      // A fresh visit to another book. This case cannot see a stale dependency
      // array (the remount re-runs the load effect regardless); the
      // same-instance case below is the one that pins that.
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: TRIAGE_SURFACE })
      const first = renderAt('s1')
      await user.click((await screen.findAllByRole('button', { name: /Mark reviewed/i }))[0])
      first.unmount()

      mockGet.mockResolvedValue({ data: { ...TRIAGE_SURFACE, storybook_id: 's2' } })
      renderAt('s2')
      expect(await screen.findByText(/marked reviewed in this browser/i)).toHaveTextContent(
        '0 of 2 findings marked reviewed'
      )
      expect(screen.queryByRole('button', { name: /^Reviewed$/i })).not.toBeInTheDocument()
    })

    it('shows the next book unmarked when the queue advances to it', async () => {
      // Auto-advance navigates to another book under the SAME route pattern,
      // which is the one path where triage could bleed between books. Two
      // independent guards stop it: ReviewDetailPage's `key={storybookId}`
      // remounts the inner page, and the triage load effect names
      // storybookId in its dependency array. Verified by mutation: removing
      // either one alone leaves all 111 tests green (the remount case is
      // caught by "clears the approve dialog ... when the queue advances");
      // removing BOTH fails this case. So this is the assertion that keeps
      // triage from silently inheriting its correctness from the `key`.
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ data: TRIAGE_SURFACE })
      render(
        <MemoryRouter initialEntries={['/admin/review/s1']}>
          <NextBookLink to="/admin/review/s2" />
          <Routes>
            <Route path="/admin/review/:storybookId" element={<ReviewDetailPage />} />
          </Routes>
        </MemoryRouter>
      )
      await user.click((await screen.findAllByRole('button', { name: /Mark reviewed/i }))[0])
      expect(screen.getByText(/marked reviewed in this browser/i)).toHaveTextContent(
        '1 of 2 findings marked reviewed'
      )

      mockGet.mockResolvedValue({ data: { ...TRIAGE_SURFACE, storybook_id: 's2' } })
      await user.click(screen.getByRole('button', { name: 'NEXT BOOK' }))
      await screen.findByText('0 of 2 findings marked reviewed', { exact: false })
      expect(screen.queryByRole('button', { name: /^Reviewed$/i })).not.toBeInTheDocument()
    })

    it('offers triage on low-priority advisories too', async () => {
      // The low-advisory bucket is where a long tail of findings actually
      // accumulates (RS-A1 moved it out of the default view), so it is the
      // section that most needs a place-keeper.
      mockGet.mockResolvedValue({
        data: {
          ...TRIAGE_SURFACE,
          // A low advisory is never fanned out (RS-A1), so a realistic
          // low-advisory-only surface has no flagged passages at all.
          flagged_passages: [],
          ranked_findings: [],
          low_advisory_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n2',
              verdict: 'advisory',
              score: 0.04,
              message: 'faint gloom',
              severity: 'low',
              node_ids: ['n2'],
              structural: false,
              concern: 'scariness',
            },
          ],
        },
      })
      renderAt('s1')
      const details = await screen.findByText(/Low-priority advisories \(1\)/i)
      expect(details).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Mark reviewed/i })).toBeInTheDocument()
      expect(screen.getByText(/marked reviewed in this browser/i)).toHaveTextContent(
        '0 of 1 finding marked reviewed'
      )
    })

    it('renders no triage control on a surface with nothing to triage', async () => {
      mockGet.mockResolvedValue({ data: SURFACE })
      renderAt('s1')
      await screen.findByRole('heading', { name: 'Ranked findings' })
      expect(screen.queryByRole('button', { name: /Mark reviewed/i })).not.toBeInTheDocument()
      expect(screen.queryByText(/marked reviewed in this browser/i)).not.toBeInTheDocument()
    })
  })

  describe('edit-path context (RS-A6)', () => {
    async function openEditDialog(user: ReturnType<typeof userEvent.setup>, nodeId: string) {
      renderAt('s1')
      const editButtons = await screen.findAllByRole('button', { name: 'Edit passage' })
      for (const button of editButtons) {
        await user.click(button)
        const dialog = screen.queryByRole('dialog', { name: `Edit passage ${nodeId}` })
        if (dialog !== null) return dialog
        await user.click(screen.getByRole('button', { name: 'Cancel' }))
      }
      throw new Error(`no Edit passage control opened a dialog for ${nodeId}`)
    }

    it('shows the findings that name the passage being edited', async () => {
      const user = userEvent.setup()
      const dialog = await openEditDialog(user, 'n1')
      // SURFACE flags n1 with "possibly scary". Scoped to the dialog: the page
      // renders the same finding in its own list, so an unscoped query would
      // pass with the dialog showing nothing at all.
      expect(within(dialog).getByText('possibly scary')).toBeInTheDocument()
      expect(within(dialog).getByText('safety')).toBeInTheDocument()
      expect(
        within(dialog).getByRole('heading', { name: /what the gate said about this passage/i })
      ).toBeInTheDocument()
    })

    it('says so when no finding names the passage being edited', async () => {
      // Reachable from the RS-A4 spot check, which offers passages nothing
      // flagged. An empty findings list must read as "nothing was recorded",
      // never as a section that failed to load.
      const user = userEvent.setup()
      const dialog = await openEditDialog(user, 'n2')
      expect(within(dialog).getByText(/no finding names this passage/i)).toBeInTheDocument()
      expect(within(dialog).queryByText('possibly scary')).not.toBeInTheDocument()
    })

    it('shows a low advisory that names the passage, though it is not fanned out', async () => {
      // `RS-A1` deliberately keeps low advisories out of flagged_passages, so
      // an edit dialog sourced from the fan-out alone would tell a reviewer
      // nothing was recorded about a passage the gate did comment on.
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [],
          low_advisory_findings: [
            {
              stage: 1,
              source: 'llm_safety',
              category: 'safety',
              node_id: 'n2',
              verdict: 'advisory',
              score: 0.06,
              message: 'a faint gloom in the fork',
              severity: 'low',
              node_ids: ['n2'],
              structural: false,
              concern: 'scariness',
            },
          ],
        },
      })
      const dialog = await openEditDialog(user, 'n2')
      expect(within(dialog).getByText('a faint gloom in the fork')).toBeInTheDocument()
      expect(within(dialog).getByText('scariness')).toBeInTheDocument()
      expect(within(dialog).getByText('0.06')).toBeInTheDocument()
    })

    it('lists a finding once when both populations carry it', async () => {
      // A node-bearing finding is in the fan-out AND in ranked_findings by
      // construction. Without the dedupe, every ranked finding would render
      // twice in this dialog.
      const user = userEvent.setup()
      const finding = {
        stage: 1,
        source: 'llm_safety',
        category: 'safety',
        node_id: 'n1',
        verdict: 'block',
        score: null,
        message: 'graphic violence',
        severity: 'high',
        node_ids: ['n1'],
        structural: false,
        concern: 'violence',
      }
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          flagged_passages: [
            { node_id: 'n1', prose: 'A dark cave yawned ahead.', findings: [finding] },
          ],
          ranked_findings: [finding],
        },
      })
      const dialog = await openEditDialog(user, 'n1')
      expect(within(dialog).getAllByText('graphic violence')).toHaveLength(1)
    })

    it('states the band the rewrite has to hold', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        data: {
          ...SURFACE,
          blob: {
            ...SURFACE.blob,
            metadata: { age_band: '9-12', reading_level: 'grade_4' },
          },
        },
      })
      const dialog = await openEditDialog(user, 'n1')
      const band = within(dialog).getByText(/Write for/i)
      expect(band).toHaveTextContent(/9-12/)
      expect(band).toHaveTextContent(/reading level grade_4/)
      // And that the gate, not this dialog, is what enforces it.
      expect(band).toHaveTextContent(/re-runs the deterministic gate/i)
    })

    it('omits the band line when the blob records no band', async () => {
      // Rather than printing "the target band, reading level undefined": an
      // invented target is worse than an absent one.
      const user = userEvent.setup()
      const dialog = await openEditDialog(user, 'n1')
      expect(within(dialog).queryByText(/Write for/i)).not.toBeInTheDocument()
    })
  })
})
