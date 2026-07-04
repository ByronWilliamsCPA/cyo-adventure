import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequestStory } from './RequestStory'

const mockGet = vi.fn()
const mockPost = vi.fn()
// #ASSUME: timing dependencies: RequestStory memoizes the api client via
// useMemo (mirroring the real useApi hook's stable reference when config is
// unchanged); a mock returning a fresh object per call would break that
// memoization and re-fire the load effect on every render.
// #VERIFY: keep a single stable fakeApi reference across calls, matching
// LibraryPage.test.tsx's pattern.
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function emptyList() {
  return { data: { requests: [] } }
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockGet.mockResolvedValue(emptyList())
})

describe('RequestStory', () => {
  it('reveals the idea form when the request button is clicked', async () => {
    render(<RequestStory profileId="p1" />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^send$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('sends the idea and refreshes the status list', async () => {
    mockGet
      .mockResolvedValueOnce(emptyList())
      .mockResolvedValueOnce({
        data: { requests: [{ id: 'req1', status: 'pending' }] },
      })
    mockPost.mockResolvedValue({ data: { id: 'req1', status: 'pending' } })

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'A dragon who loves cupcakes' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests', {
        profile_id: 'p1',
        request_text: 'A dragon who loves cupcakes',
      })
    )
    expect(await screen.findByText(/waiting for a grown-up to say yes/i)).toBeInTheDocument()
    // Form closes and resets after a successful send.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('does not send an empty or whitespace-only idea', async () => {
    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    const sendButton = screen.getByRole('button', { name: /^send$/i })
    expect(sendButton).toBeDisabled()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } })
    expect(sendButton).toBeDisabled()
    fireEvent.click(sendButton)

    expect(mockPost).not.toHaveBeenCalled()
  })

  it('renders friendly copy for every request status', async () => {
    mockGet.mockResolvedValue({
      data: {
        requests: [
          { id: 'req1', status: 'pending' },
          { id: 'req2', status: 'approved' },
          { id: 'req3', status: 'declined' },
          { id: 'req4', status: 'blocked' },
        ],
      },
    })

    render(<RequestStory profileId="p1" />)

    expect(await screen.findByText(/waiting for a grown-up to say yes/i)).toBeInTheDocument()
    expect(screen.getByText(/yay! your story is being made/i)).toBeInTheDocument()
    expect(screen.getByText(/not this time\. try another idea!/i)).toBeInTheDocument()
    expect(screen.getByText(/let's try a different idea!/i)).toBeInTheDocument()
  })

  it('shows a friendly error and keeps the form open when create fails', async () => {
    mockPost.mockRejectedValue(new Error('network exploded'))

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'A brave mouse' } })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/something went wrong\. try again!/i)
    // No raw error text ever reaches the child.
    expect(screen.queryByText(/network exploded/i)).not.toBeInTheDocument()
    // The form stays open with the idea intact so the child can retry.
    expect(screen.getByRole('textbox')).toHaveValue('A brave mouse')
  })

  it('shows a friendly busy message when the pending cap (409) is hit', async () => {
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: 'too many pending requests for this profile' } },
    })

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'One more idea' } })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/wait for a few to be looked at/i)
    expect(screen.queryByText(/too many pending requests/i)).not.toBeInTheDocument()
  })
})
