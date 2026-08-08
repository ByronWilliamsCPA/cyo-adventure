import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'

import { CharacterCreator } from './CharacterCreator'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

const CREATED_CHARACTER = {
  id: 'char-1',
  profile_id: 'p1',
  name: 'Luna',
  archetype: 'scout',
  look: 'avatar_01',
  is_active: true,
  books_completed: 0,
  attributes: {},
  created_at: '2026-08-01T00:00:00Z',
  retired_at: null,
}

describe('CharacterCreator', () => {
  it('submits name, archetype, and look and calls the API once', async () => {
    mockPost.mockResolvedValue({ data: CREATED_CHARACTER })
    const onCreated = vi.fn()
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" onCreated={onCreated} />)

    await user.type(screen.getByLabelText("What's their name?"), 'Luna')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/v1/characters', {
      profile_id: 'p1',
      name: 'Luna',
      archetype: 'scout',
      look: 'avatar_01',
    })
    await screen.findByRole('button', { name: /Start my adventure/i })
    expect(onCreated).toHaveBeenCalledWith(CREATED_CHARACTER)
  })

  it('blocks a name over 32 characters client-side and never calls the API', async () => {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    const tooLongName = 'a'.repeat(33)
    await user.type(screen.getByLabelText("What's their name?"), tooLongName)
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    const error = await screen.findByRole('alert')
    expect(error.textContent).toMatch(/32/)
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('renders exactly the six roster archetypes, in roster order', () => {
    render(<CharacterCreator profileId="p1" />)

    const radios = screen.getAllByRole('radio', {
      name: /Scout|Guardian|Trickster|Scholar|Healer|Wildheart/,
    })
    const values = radios.map((radio) => (radio as HTMLInputElement).value)
    // A literal list, not a constant imported from the component: a
    // reordering of the component's roster must fail this test rather than
    // move with it, since the order is the backend's wire format.
    expect(values).toEqual(['scout', 'guardian', 'trickster', 'scholar', 'healer', 'wildheart'])
  })

  it('surfaces the server naming-violation message verbatim on a 422', async () => {
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 422,
        data: { error: 'ValidationError', message: 'That name is not allowed. Try another.' },
      },
    })
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    await user.type(screen.getByLabelText("What's their name?"), 'Bad Name')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(await screen.findByText('That name is not allowed. Try another.')).toBeInTheDocument()
  })

  it('labels each look with its color, not just its position', () => {
    render(<CharacterCreator profileId="p1" />)

    // The visible text is the bare ordinal by design (the swatch carries the
    // visual), so the accessible name is the only channel that says WHICH
    // look this is, and it must not be the emoji: an emoji's spoken name is
    // the platform's to choose, not this app's.
    expect(screen.getByRole('radio', { name: 'Look 1, red' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Look 12, gold star' })).toBeInTheDocument()
    // WCAG 2.5.3: the visible label is a prefix of the accessible name, so
    // "tap Look 1" as spoken by a voice-control user still matches.
    expect(screen.getAllByRole('radio', { name: /^Look \d+, / })).toHaveLength(12)
  })

  it('points the name field at its error message while the error stands', async () => {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    const input = screen.getByLabelText("What's their name?")
    expect(input).toHaveAttribute('aria-invalid', 'false')
    expect(input).not.toHaveAttribute('aria-describedby')

    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    // role="alert" announces once, on appearance. The association is what a
    // child gets when they tab BACK to the field afterwards.
    const alert = await screen.findByRole('alert')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAttribute('aria-describedby', alert.id)
    expect(alert.id).not.toBe('')

    // Typing clears the error, and the association goes with it rather than
    // dangling at a removed node.
    await user.type(input, 'L')
    expect(input).toHaveAttribute('aria-invalid', 'false')
    expect(input).not.toHaveAttribute('aria-describedby')
  })
})

/**
 * The three input guards and the two submit-failure branches. Each is a
 * distinct message a child sees, and none of them is reachable from the
 * happy path: the guards return before the API call, and the failure fork
 * needs a rejection that is NOT the 422 the naming test above uses.
 */
describe('CharacterCreator refusals', () => {
  it('asks for a name before calling the API', async () => {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Give them a name to get started.')
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('treats a whitespace-only name as no name at all', async () => {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    await user.type(screen.getByLabelText("What's their name?"), '   ')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Give them a name to get started.')
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('asks for a role before calling the API', async () => {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    await user.type(screen.getByLabelText("What's their name?"), 'Luna')
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a role for your character.')
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('asks for a look before calling the API', async () => {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)

    await user.type(screen.getByLabelText("What's their name?"), 'Luna')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a look for your character.')
    expect(mockPost).not.toHaveBeenCalled()
  })
})

/**
 * The non-422 submit-failure fork, both directions. A permission failure is
 * something only a grown-up can clear, so telling a child to "try again"
 * would send them into a loop; anything else is worth another tap. The two
 * arms must be asserted separately, since a single one passes whichever way
 * the ternary is wired.
 */
describe('CharacterCreator submit failures', () => {
  let errorSpy: MockInstance

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    errorSpy.mockRestore()
  })

  async function submitOnce() {
    const user = userEvent.setup()
    render(<CharacterCreator profileId="p1" />)
    await user.type(screen.getByLabelText("What's their name?"), 'Luna')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))
  }

  it.each([
    ['a 401', 401],
    ['a 403', 403],
  ])('tells a child to ask a grown-up on %s', async (_label, status) => {
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status, data: {} } })
    await submitOnce()

    expect(await screen.findByText('Ask a grown-up to help with this.')).toBeInTheDocument()
    expect(screen.queryByText("That didn't work. Let's try again.")).toBeNull()
  })

  it.each([
    ['a 500', { isAxiosError: true, response: { status: 500, data: {} } }],
    ['a transport failure with no response', new Error('network down')],
  ])('offers a retry on %s', async (_label, rejection) => {
    mockPost.mockRejectedValue(rejection)
    await submitOnce()

    expect(await screen.findByText("That didn't work. Let's try again.")).toBeInTheDocument()
    expect(screen.queryByText('Ask a grown-up to help with this.')).toBeNull()
  })

  it('re-enables the submit button after a failure so the child can retry', async () => {
    mockPost.mockRejectedValue(new Error('network down'))
    await submitOnce()

    await screen.findByText("That didn't work. Let's try again.")
    const submit = screen.getByRole('button', { name: /Start my adventure/i })
    expect(submit).toBeEnabled()
  })

  it('writes no state after the component unmounts mid-submit', async () => {
    let rejectCreate!: (err: unknown) => void
    mockPost.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectCreate = reject
        })
    )
    const user = userEvent.setup()
    const { unmount } = render(<CharacterCreator profileId="p1" />)
    await user.type(screen.getByLabelText("What's their name?"), 'Luna')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))
    unmount()
    rejectCreate(new Error('late boom'))

    // The redacted log still fires (it precedes the mounted check); the
    // point is that no state write follows on the unmounted component.
    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith('character create failed', 'late boom')
    )
    expect(document.body.textContent).toBe('')
  })
})
