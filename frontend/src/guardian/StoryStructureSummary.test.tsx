import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StoryStructureSummary } from './StoryStructureSummary'

const BLOB: Record<string, unknown> = {
  title: 'The Cave',
  start_node: 'start',
  metadata: {
    themes: ['friendship', 'courage'],
    estimated_minutes: 12,
    content_flags: { violence: 'mild', scariness: 'none', peril: 'moderate' },
  },
  nodes: [
    {
      id: 'start',
      body: 'A dark cave yawned ahead.',
      choices: [
        { label: 'Go left', target: 'left' },
        { label: 'Go right', target: 'end-good' },
      ],
    },
    {
      id: 'left',
      body: 'The path narrows.',
      choices: [{ label: 'Continue', target: 'end-bad' }],
    },
    {
      id: 'end-good',
      body: 'You find the treasure.',
      is_ending: true,
      choices: [],
      ending: { id: 'end-good', title: 'Treasure Found', valence: 'positive', kind: 'success' },
    },
    {
      id: 'end-bad',
      body: 'The path collapses.',
      is_ending: true,
      choices: [],
      ending: { id: 'end-bad', title: 'A Close Call', valence: 'negative', kind: 'setback' },
    },
  ],
}

const FINDINGS = [
  { verdict: 'block' as const },
  { verdict: 'flag' as const },
  { verdict: 'flag' as const },
  { verdict: 'advisory' as const },
]

describe('StoryStructureSummary (full, admin variant)', () => {
  it('renders node count, ending count, read time, themes, and branch shape from the blob', () => {
    render(
      <StoryStructureSummary blob={BLOB} screened={true} flaggedCount={0} />
    )
    expect(screen.getByText('4')).toBeInTheDocument() // passages
    expect(screen.getByText('2')).toBeInTheDocument() // endings
    expect(screen.getByText('12 minutes')).toBeInTheDocument()
    expect(screen.getByText('friendship, courage', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/Starts at "start"/)).toBeInTheDocument()
    expect(screen.getByText(/1 decision point/)).toBeInTheDocument()
  })

  it('lists each ending with its title, valence, and kind', () => {
    render(<StoryStructureSummary blob={BLOB} screened={true} flaggedCount={0} />)
    const endingsHeading = screen.getByRole('heading', { level: 4, name: 'Endings' })
    const endingsSection = endingsHeading.closest('.story-structure__endings')
    expect(endingsSection).not.toBeNull()
    const within_ = within(endingsSection as HTMLElement)
    expect(within_.getByText('Treasure Found')).toBeInTheDocument()
    expect(within_.getByText(/positive, success/)).toBeInTheDocument()
    expect(within_.getByText('A Close Call')).toBeInTheDocument()
    expect(within_.getByText(/negative, setback/)).toBeInTheDocument()
  })

  it('shows content flags declared in metadata', () => {
    render(<StoryStructureSummary blob={BLOB} screened={true} flaggedCount={0} />)
    expect(screen.getByText(/violence mild/)).toBeInTheDocument()
    expect(screen.getByText(/peril moderate/)).toBeInTheDocument()
  })

  it('shows a flagged-count badge with a block/flag/advisory severity split', () => {
    render(<StoryStructureSummary blob={BLOB} screened={true} flaggedCount={4} findings={FINDINGS} />)
    expect(screen.getByText('4 flagged')).toBeInTheDocument()
    expect(screen.getByText(/1 block/)).toBeInTheDocument()
    expect(screen.getByText(/2 flags/)).toBeInTheDocument()
    expect(screen.getByText(/1 advisory/)).toBeInTheDocument()
  })

  it('shows a clean badge when screened with nothing flagged', () => {
    render(<StoryStructureSummary blob={BLOB} screened={true} flaggedCount={0} />)
    expect(screen.getByText('Clean')).toBeInTheDocument()
  })

  it('shows an unscreened badge instead of a flag count when not yet screened', () => {
    render(<StoryStructureSummary blob={BLOB} screened={false} flaggedCount={0} />)
    expect(screen.getByText('Unscreened')).toBeInTheDocument()
    expect(screen.queryByText(/flagged/)).not.toBeInTheDocument()
  })

  it('omits the branch-shape line when the start node is missing', () => {
    const blob = { ...BLOB, start_node: 'no-such-node' }
    render(<StoryStructureSummary blob={blob} screened={true} flaggedCount={0} />)
    expect(screen.queryByText('Branch shape')).not.toBeInTheDocument()
  })

  it('falls back to a word-count read-time estimate when metadata omits it', () => {
    const blob = {
      ...BLOB,
      metadata: { ...(BLOB.metadata as Record<string, unknown>), estimated_minutes: undefined },
    }
    render(<StoryStructureSummary blob={blob} screened={true} flaggedCount={0} />)
    expect(screen.getByText(/\(estimated\)/)).toBeInTheDocument()
  })

  it('degrades gracefully on a blob with no nodes array', () => {
    render(<StoryStructureSummary blob={{}} screened={true} flaggedCount={0} />)
    expect(screen.getByText('Unknown')).toBeInTheDocument() // read time
    expect(screen.getByText('Clean')).toBeInTheDocument()
  })
})

describe('StoryStructureSummary (compact, guardian variant)', () => {
  it('hides node count, branch shape, content flags, and the severity split', () => {
    render(
      <StoryStructureSummary
        compact
        blob={BLOB}
        screened={true}
        flaggedCount={4}
        findings={FINDINGS}
      />
    )
    expect(screen.queryByText('Passages')).not.toBeInTheDocument()
    expect(screen.queryByText(/Starts at/)).not.toBeInTheDocument()
    expect(screen.queryByText(/violence mild/)).not.toBeInTheDocument()
    expect(screen.queryByText(/1 block/)).not.toBeInTheDocument()
  })

  it('still shows endings, read time, themes, and the flagged-count badge', () => {
    render(<StoryStructureSummary compact blob={BLOB} screened={true} flaggedCount={4} />)
    expect(screen.getByText('2')).toBeInTheDocument() // endings
    expect(screen.getByText('12 minutes')).toBeInTheDocument()
    expect(screen.getByText('friendship, courage', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('4 flagged')).toBeInTheDocument()
    expect(screen.getByText('Treasure Found')).toBeInTheDocument()
  })
})
