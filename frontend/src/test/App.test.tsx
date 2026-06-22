import 'fake-indexeddb/auto'

import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { _resetDbHandle } from '../offline/db'

// Mock the API adapters so the App mounts deterministically without a backend.
vi.mock('../api/readerApi', () => ({
  makeSyncApi: () => ({
    // Echo a full ReadingState row (revision bumped) so the mock matches the real
    // adapter contract; a truncated row would hide write-back regressions.
    putReadingState: (_profileId: string, _storybookId: string, body: { state_revision?: number }) =>
      Promise.resolve({
        status: 200,
        row: { ...body, state_revision: (body.state_revision ?? 0) + 1 },
      }),
  }),
  makeFetchStory: () => () =>
    Promise.resolve({
      schema_version: '1.0',
      id: 's_demo',
      version: 1,
      title: 'Demo',
      metadata: {},
      variables: [],
      start_node: 'n0',
      nodes: [
        {
          id: 'n0',
          body: 'Hello reader',
          is_ending: false,
          choices: [{ id: 'c', label: 'Go', target: 'n1' }],
        },
        {
          id: 'n1',
          body: 'The end',
          is_ending: true,
          ending: { id: 'e', type: 'good', title: 'End' },
          choices: [],
        },
      ],
    }),
}))

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})

describe('App', () => {
  it('renders the reader for the configured story', async () => {
    render(<App />)
    expect(await screen.findByTestId('reader')).toBeInTheDocument()
    expect(screen.getByText('Hello reader')).toBeInTheDocument()
  })

  it('shows the app title', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'CYO Adventure' })).toBeInTheDocument()
    // Let the async story load settle so no state update lands after teardown.
    await screen.findByTestId('reader')
  })
})
