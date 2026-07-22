import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { VersionDiffView } from './ReviewCompare'
import type { StoryNodeView, VersionDiff } from './reviewDiff'

function node(overrides: Partial<StoryNodeView> & { id: string }): StoryNodeView {
  return {
    blobIndex: 0,
    body: 'Some prose.',
    choices: [],
    isEnding: false,
    ending: null,
    ...overrides,
  }
}

describe('VersionDiffView / ChangedNodeDetail', () => {
  it('renders the summary line plus added/removed passage lists', () => {
    const diff: VersionDiff = {
      added: [node({ id: 'n-added' })],
      removed: [node({ id: 'n-removed' })],
      changed: [],
    }
    render(<VersionDiffView diff={diff} />)
    expect(screen.getByText('1 passage added, 0 changed, 1 removed')).toBeInTheDocument()
    expect(screen.getByText('Added: passage n-added')).toBeInTheDocument()
    expect(screen.getByText('Removed: passage n-removed')).toBeInTheDocument()
  })

  it('shows a body-only diff without a choice-detail list', () => {
    const diff: VersionDiff = {
      added: [],
      removed: [],
      changed: [
        {
          id: 'n1',
          previous: node({ id: 'n1', body: 'Old body.' }),
          current: node({ id: 'n1', body: 'New body.' }),
          bodyChanged: true,
          choicesChanged: false,
        },
      ],
    }
    render(<VersionDiffView diff={diff} />)
    expect(screen.getByText('Passage n1 changed')).toBeInTheDocument()
    expect(screen.getByText('Old body.')).toBeInTheDocument()
    expect(screen.getByText('New body.')).toBeInTheDocument()
    expect(screen.queryByText(/Choices changed/)).not.toBeInTheDocument()
  })

  it('lists reworded, added, and removed choices for a choices-changed passage', () => {
    const previous = node({
      id: 'n1',
      choices: [
        { label: 'Go left', target: 'left' },
        { label: 'Go away', target: 'gone' },
      ],
    })
    const current = node({
      id: 'n1',
      choices: [
        { label: 'Turn left', target: 'left' },
        { label: 'Go new', target: 'newnode' },
      ],
    })
    const diff: VersionDiff = {
      added: [],
      removed: [],
      changed: [
        {
          id: 'n1',
          previous,
          current,
          bodyChanged: false,
          choicesChanged: true,
        },
      ],
    }
    render(<VersionDiffView diff={diff} />)
    expect(screen.getByText('Choices changed:')).toBeInTheDocument()
    expect(screen.getByText('"Go left" reworded to "Turn left"')).toBeInTheDocument()
    expect(screen.getByText('Added choice "Go new"')).toBeInTheDocument()
    expect(screen.getByText('Removed choice "Go away"')).toBeInTheDocument()
  })

  it('falls back to "(missing label)" for an added/removed choice with an empty label', () => {
    const previous = node({ id: 'n1', choices: [{ label: '', target: 'gone' }] })
    const current = node({ id: 'n1', choices: [{ label: '', target: 'new' }] })
    const diff: VersionDiff = {
      added: [],
      removed: [],
      changed: [{ id: 'n1', previous, current, bodyChanged: false, choicesChanged: true }],
    }
    render(<VersionDiffView diff={diff} />)
    expect(screen.getByText('Added choice "(missing label)"')).toBeInTheDocument()
    expect(screen.getByText('Removed choice "(missing label)"')).toBeInTheDocument()
  })
})
