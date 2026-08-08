import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'

import { KidShell } from './KidShell'
import { useKidOutletContext } from './kidOutletContext'
import { KID_PICKER_PATH } from '../routes'
import { ThemeProvider } from '../theme/ThemeProvider'
import { _resetKidProfileFetch } from './useKidProfile'

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
    // ThemeProvider: KidShell's always-on ThemeToggle calls useTheme(),
    // which throws outside one; every real route already sits under it
    // (App.tsx).
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<KidShell />}>
            <Route path={KID_PICKER_PATH.slice(1)} element={<div>Picker Page</div>} />
            <Route path="library/:profileId" element={<div>Library Page</div>} />
            <Route path="read/:profileId/:storybookId/:version" element={<div>Reader Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({ data: { profiles: PROFILES } })
  _resetKidProfileFetch()
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

  it('shares one profiles fetch between the shell and the nav on a library view', async () => {
    renderShellAt('/library/p1')
    // Both consumers have rendered from the lookup: the nav shows the name,
    // and the shell has stamped the band attribute.
    expect(await screen.findByText('Mia')).toBeInTheDocument()
    expect(document.querySelector('.kid-shell')).toHaveAttribute('data-age-band', '5-8')
    // KidShell and KidNav each run useKidProfile, but the in-flight request
    // is shared, so the API sees a single GET /v1/profiles -- counted by URL
    // (not raw call count) since W3.4 added KidNav's own independent
    // GET /v1/me/progress fetch (the ring/badge case data source), which
    // this test is not about and must not make it flaky.
    const profilesCalls = mockGet.mock.calls.filter((call) => call[0] === '/v1/profiles')
    expect(profilesCalls).toHaveLength(1)
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

/**
 * These assertions keep querying data-age-band / data-reduce-motion directly:
 * those attributes are the ONLY signal KidShell exposes for band theming. They
 * exist solely to drive band-tokens.css (visual sizing/spacing per age band and
 * a reduce-motion switch), producing no role, accessible-name, or text change
 * that jsdom can observe. The user-facing effect is CSS-only, so the attribute
 * is the narrowest honest proxy; each test also asserts an observable signal
 * (the visible "Library Page" / profile name) alongside.
 */
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

const LUNA = {
  id: 'char-1',
  profile_id: 'p1',
  name: 'Luna',
  archetype: 'scout',
  look: 'avatar_01',
  is_active: true,
  books_completed: 0,
  attributes: {},
  seed_var_state: {},
  created_at: '2026-08-01T00:00:00Z',
  retired_at: null,
}

/**
 * Routes the shell's GETs by URL so the character lookup can be varied
 * independently of the profiles lookup every one of these renders also
 * performs. `characters` may be a value to resolve, a rejection, or a
 * never-settling promise (the in-flight case).
 */
function mockCharacterList(characters: { resolve?: unknown; reject?: Error; pending?: true }) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/characters') {
      if (characters.pending) return new Promise(() => {})
      if (characters.reject !== undefined) return Promise.reject(characters.reject)
      return Promise.resolve({ data: { characters: characters.resolve } })
    }
    return Promise.resolve({ data: { profiles: PROFILES } })
  })
}

/**
 * The library-route character lookup and its Outlet plumbing, mounted
 * through KidShell rather than through the two character components in
 * isolation. This used to be a first-run gate that swapped the whole
 * library Outlet for CharacterCreator whenever a profile had no character
 * yet; the owner rejected that (every kid hard-gated with no skip
 * affordance, while zero catalog books could use one), so the gate now
 * lives per book in LibraryPage.tsx instead. This suite keeps proving the
 * lookup itself: it only runs on the library route, it hands its result
 * through the Outlet context regardless of status, and the library Outlet
 * always renders no matter what that status is. The component tests in
 * src/characters/ never mount KidShell, so none of them can catch a
 * regression back to the old route-wide gate.
 */
describe('KidShell library route character lookup', () => {
  let errorSpy: MockInstance

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    errorSpy.mockRestore()
  })

  it('renders the library Outlet even when the profile has no character', async () => {
    mockCharacterList({ resolve: [] })
    renderShellAt('/library/p1')

    // The owner-decided behaviour: a profile with no character yet goes
    // straight to the library, same as any other profile. Nothing about
    // 'none' specifically should ever swap the Outlet for the creator here
    // again; that decision now belongs to LibraryPage per book.
    expect(await screen.findByText('Library Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Make your character/i })).not.toBeInTheDocument()
  })

  it('renders the library Outlet when the profile already has an active character', async () => {
    mockCharacterList({ resolve: [LUNA] })
    renderShellAt('/library/p1')

    expect(await screen.findByText('Library Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Make your character/i })).not.toBeInTheDocument()
  })

  it('renders the library Outlet while the character lookup is still in flight', async () => {
    mockCharacterList({ pending: true })
    renderShellAt('/library/p1')

    // The fail-safe: 'loading' is not 'none'. A gate that treated "we do not
    // know yet" as "no character" would bounce a returning child into
    // re-creating one on every slow connection.
    expect(await screen.findByText('Library Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Make your character/i })).not.toBeInTheDocument()
  })

  it('renders the library Outlet when the character lookup fails', async () => {
    mockCharacterList({ reject: new Error('characters down') })
    renderShellAt('/library/p1')

    // Same fail-safe on the other unknown: a failed lookup must not be read
    // as an empty one. useActiveCharacter maps an unparseable or failed
    // response to 'error' precisely so this branch cannot be reached.
    expect(await screen.findByText('Library Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Make your character/i })).not.toBeInTheDocument()
  })

  it('does not look up a character at all off the library route', async () => {
    mockCharacterList({ resolve: [] })
    renderShellAt('/read/p1/s1/1')

    await screen.findByText('Reader Page')
    // The gate is library-route-only, so the reader route must not pay for
    // the lookup, and a reader-route child must never see the creator even
    // with an empty character list.
    expect(mockGet.mock.calls.filter((call) => call[0] === '/v1/characters')).toHaveLength(0)
    expect(screen.queryByRole('heading', { name: /Make your character/i })).not.toBeInTheDocument()
  })

  it('hands the resolved character to the library route through the Outlet', async () => {
    mockCharacterList({ resolve: [LUNA] })
    // A leaf that reads the context rather than the usual inert stub: this
    // is the half of the de-duplication that lives in the shell. Its other
    // half (LibraryPage consuming this instead of fetching again) is
    // asserted in LibraryPage.test.tsx.
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/library/p1']}>
          <Routes>
            <Route element={<KidShell />}>
              <Route path="library/:profileId" element={<CharacterContextProbe />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    )

    expect(await screen.findByText('context character: Luna')).toBeInTheDocument()
    // One lookup for the route, not one per consumer.
    expect(mockGet.mock.calls.filter((call) => call[0] === '/v1/characters')).toHaveLength(1)
  })
})

function CharacterContextProbe() {
  const context = useKidOutletContext()
  const state = context?.activeCharacter?.state
  return <p>context character: {state?.status === 'ready' ? state.character.name : 'none'}</p>
}
