import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
    await user.click(screen.getByRole('radio', { name: 'Look 1' }))
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
    await user.click(screen.getByRole('radio', { name: 'Look 1' }))
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
    await user.click(screen.getByRole('radio', { name: 'Look 1' }))
    await user.click(screen.getByRole('button', { name: /Start my adventure/i }))

    expect(await screen.findByText('That name is not allowed. Try another.')).toBeInTheDocument()
  })
})
