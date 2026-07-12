import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConsolePage } from './ConsolePage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

function principal(role: 'guardian' | 'admin', isAdmin = role === 'admin') {
  return { principal: { subject: 's', role, isAdmin, familyId: 'f', profileIds: [] } }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConsolePage />
    </MemoryRouter>
  )
}

function mockProfiles(profiles: unknown[]) {
  mockGet.mockImplementation((url: string) =>
    url === '/v1/profiles'
      ? Promise.resolve({ data: { profiles } })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockProfiles([{ id: 'p1' }])
  mockPost.mockReset()
  mockUseAuth.mockReset()
  mockUseAuth.mockReturnValue(principal('guardian'))
})

describe('ConsolePage', () => {
  it('renders the family home with quick links for a family with children', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: /request a story/i })).toHaveAttribute(
      'href',
      '/guardian/intake'
    )
    expect(screen.getByRole('link', { name: /story requests/i })).toHaveAttribute(
      'href',
      '/guardian/requests'
    )
    expect(screen.getByRole('link', { name: /browse and assign books/i })).toHaveAttribute(
      'href',
      '/guardian/books'
    )
    expect(screen.getByRole('link', { name: /manage child profiles/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
  })

  it('nudges a childless family to add a profile instead of quick links', async () => {
    mockProfiles([])
    renderPage()
    const link = await screen.findByRole('link', { name: /add a child profile/i })
    expect(link).toHaveAttribute('href', '/guardian/profiles')
    expect(screen.queryByRole('link', { name: /request a story/i })).not.toBeInTheDocument()
  })

  it('tells a plain guardian that reviews are handled by the safety reviewer', async () => {
    renderPage()
    expect(await screen.findByText(/safety reviewer/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /admin console/i })).not.toBeInTheDocument()
  })

  it('points a dual-role adult at the admin console', async () => {
    mockUseAuth.mockReturnValue(principal('guardian', true))
    renderPage()
    expect(await screen.findByRole('link', { name: /open the admin console/i })).toHaveAttribute(
      'href',
      '/admin'
    )
  })

  it('still renders quick links when the profiles fetch fails (childCount stays null)', async () => {
    // The onboarding read is best-effort: on failure childCount stays null, so
    // the nudge is suppressed but the quick links (childCount !== 0) still show.
    mockGet.mockRejectedValue(new Error('profiles fetch failed'))
    renderPage()
    expect(await screen.findByRole('link', { name: /request a story/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /add a child profile/i })).not.toBeInTheDocument()
  })

  it('does not render the review queue or the request-a-story form here', async () => {
    // Both moved to the admin console (AdminConsolePage / AdminRequestsPage)
    // when admin functions gained their own surface.
    renderPage()
    await screen.findByText(/Family console/)
    expect(screen.queryByText(/review queue/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/what should the story be about/i)).not.toBeInTheDocument()
  })
})
