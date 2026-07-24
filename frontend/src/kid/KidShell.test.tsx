import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KidShell } from './KidShell'
import { KID_PICKER_PATH } from '../routes'

/**
 * Route-gating coverage for KidShell (mirrors ReaderLeave.test.tsx's
 * MemoryRouter + Routes + stub-leaf convention): the persistent KidNav bar
 * (its "Switch reader" link, or the nav's accessible role) must appear only
 * on the library route, not on the picker or a reader route, per KidShell's
 * own matchPath('/library/:profileId') gate.
 */

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const PROFILES = [
  {
    id: 'p1',
    display_name: 'Mia',
    age_band: '5-8',
    reading_level_cap: 99,
    avatar: 'fox',
    tts_enabled: false,
    reduce_motion: false,
    created_at: '2026-07-02T00:00:00Z',
  },
  {
    id: 'p2',
    display_name: 'Theo',
    age_band: '10-13',
    reading_level_cap: 99,
    avatar: 'owl',
    tts_enabled: false,
    reduce_motion: true,
    created_at: '2026-07-02T00:00:00Z',
  },
]

function renderShellAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<KidShell />}>
          <Route path={KID_PICKER_PATH.slice(1)} element={<div>Picker Page</div>} />
          <Route path="library/:profileId" element={<div>Library Page</div>} />
          <Route path="read/:profileId/:storybookId/:version" element={<div>Reader Page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({ data: { profiles: PROFILES } })
})

describe('KidShell route gating', () => {
  it('renders KidNav on the library route', async () => {
    renderShellAt('/library/p1')
    expect(
      await screen.findByRole('navigation', { name: /reader navigation/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /switch reader/i })).toBeInTheDocument()
    expect(screen.getByText('Library Page')).toBeInTheDocument()
  })

  it('does not render KidNav on the picker route (/kids)', () => {
    renderShellAt('/kids')
    expect(screen.queryByRole('navigation', { name: /reader navigation/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /switch reader/i })).not.toBeInTheDocument()
    expect(screen.getByText('Picker Page')).toBeInTheDocument()
  })

  it('does not render KidNav on a reader route', async () => {
    renderShellAt('/read/p1/s1/1')
    expect(screen.queryByRole('navigation', { name: /reader navigation/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /switch reader/i })).not.toBeInTheDocument()
    expect(screen.getByText('Reader Page')).toBeInTheDocument()
    // Settle the reader-route profile lookup KidShell now also performs (for
    // the data-age-band/data-reduce-motion attributes below) so it doesn't
    // resolve after the test has already moved on.
    await screen.findByText('Reader Page')
  })
})

describe('KidShell band-tokens.css attributes', () => {
  it('sets data-age-band from the library route profile once it loads', async () => {
    renderShellAt('/library/p1')
    await screen.findByText('Library Page')
    expect(await screen.findByText('Library Page')).toBeInTheDocument()
    expect(document.querySelector('.kid-shell')).toHaveAttribute('data-age-band', '5-8')
    expect(document.querySelector('.kid-shell')).not.toHaveAttribute('data-reduce-motion')
  })

  it('sets data-reduce-motion="true" when the profile has it enabled', async () => {
    renderShellAt('/library/p2')
    await screen.findByText('Library Page')
    expect(document.querySelector('.kid-shell')).toHaveAttribute('data-age-band', '10-13')
    expect(document.querySelector('.kid-shell')).toHaveAttribute('data-reduce-motion', 'true')
  })

  it('sets data-age-band from the reader route profile too', async () => {
    renderShellAt('/read/p2/s1/1')
    await screen.findByText('Reader Page')
    expect(document.querySelector('.kid-shell')).toHaveAttribute('data-age-band', '10-13')
    expect(document.querySelector('.kid-shell')).toHaveAttribute('data-reduce-motion', 'true')
  })

  it('leaves both attributes unset on the picker route', () => {
    renderShellAt('/kids')
    expect(document.querySelector('.kid-shell')).not.toHaveAttribute('data-age-band')
    expect(document.querySelector('.kid-shell')).not.toHaveAttribute('data-reduce-motion')
  })
})
