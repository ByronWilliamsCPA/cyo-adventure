import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ContinueSeries } from './ContinueSeries'

afterEach(cleanup)

const NEXT = {
  storybook_id: 's_book2',
  version: 1,
  title: 'Book 2',
  series_entry_node: 'n_start',
  carries_state: true,
}

function Probe() {
  const location = useLocation()
  return (
    <p data-testid="probe">
      {location.pathname}|{JSON.stringify(location.state)}
    </p>
  )
}

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={['/end']}>
      <Routes>
        <Route path="/end" element={ui} />
        <Route path="/read/:profileId/:storybookId/:version" element={<Probe />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ContinueSeries', () => {
  it('shows the button when a next book resolves, and navigates with the seed', async () => {
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockResolvedValue(NEXT)}
        finalVarState={{ courage: 3 }}
        carriesState={true}
      />
    )
    const button = await screen.findByTestId('continue-series')
    fireEvent.click(button)
    const probe = await screen.findByTestId('probe')
    expect(probe.textContent).toContain('/read/p1/s_book2/1')
    expect(probe.textContent).toContain('"entryNode":"n_start"')
    expect(probe.textContent).toContain('"courage":3')
  })

  it('omits the carried var state for an episodic series', async () => {
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockResolvedValue(NEXT)}
        finalVarState={{ courage: 3 }}
        carriesState={false}
      />
    )
    fireEvent.click(await screen.findByTestId('continue-series'))
    const probe = await screen.findByTestId('probe')
    expect(probe.textContent).not.toContain('courage')
  })

  it('renders nothing when there is no next book', async () => {
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockResolvedValue(null)}
        finalVarState={{}}
        carriesState={true}
      />
    )
    await waitFor(() => {
      expect(screen.queryByTestId('continue-series')).toBeNull()
    })
  })

  it('renders nothing when the lookup fails', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderWithRouter(
      <ContinueSeries
        profileId="p1"
        storybookId="s_book1"
        fetchSeriesNext={vi.fn().mockRejectedValue(new Error('boom'))}
        finalVarState={{}}
        carriesState={true}
      />
    )
    await waitFor(() => {
      expect(spy).toHaveBeenCalled()
    })
    expect(screen.queryByTestId('continue-series')).toBeNull()
    spy.mockRestore()
  })
})
