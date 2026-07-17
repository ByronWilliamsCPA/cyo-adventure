import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    expect(
      screen.queryByRole('textbox', { name: /what should your story be about/i })
    ).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    expect(
      screen.getByRole('textbox', { name: /what should your story be about/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^send$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('sends the idea and refreshes the status list', async () => {
    mockGet.mockResolvedValueOnce(emptyList()).mockResolvedValueOnce({
      data: { requests: [{ id: 'req1', status: 'pending' }] },
    })
    mockPost.mockResolvedValue({ data: { id: 'req1', status: 'pending' } })

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
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
    expect(
      screen.queryByRole('textbox', { name: /what should your story be about/i })
    ).not.toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('does not send an empty or whitespace-only idea', async () => {
    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    const sendButton = screen.getByRole('button', { name: /^send$/i })
    expect(sendButton).toBeDisabled()

    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: '   ' },
    })
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
    expect(screen.getByText(/your story is being written/i)).toBeInTheDocument()
    expect(screen.getByText(/not this time\. try another idea!/i)).toBeInTheDocument()
    expect(screen.getByText(/let's try a different idea!/i)).toBeInTheDocument()
  })

  describe('K12: approved generation status', () => {
    it('shows "being written" with no library data to match against', async () => {
      mockGet.mockResolvedValue({
        data: { requests: [{ id: 'req1', status: 'approved', proposed_series_title: null }] },
      })
      render(<RequestStory profileId="p1" />)
      const item = await screen.findByText(/your story is being written/i)
      expect(item.closest('li')).toHaveAttribute('data-status', 'generating')
    })

    it('shows "being written" even with library data when the request has no series title', async () => {
      mockGet.mockResolvedValue({
        data: { requests: [{ id: 'req1', status: 'approved', proposed_series_title: null }] },
      })
      render(<RequestStory profileId="p1" libraryTitles={['The Cupcake Chronicles: Book One']} />)
      expect(await screen.findByText(/your story is being written/i)).toBeInTheDocument()
    })

    it('shows "it\'s on your shelf" once a shelf title matches the confirmed series title', async () => {
      mockGet.mockResolvedValue({
        data: {
          requests: [
            { id: 'req1', status: 'approved', proposed_series_title: 'The Cupcake Chronicles' },
          ],
        },
      })
      render(<RequestStory profileId="p1" libraryTitles={['The Cupcake Chronicles: Book One']} />)
      const item = await screen.findByText(/it's on your shelf!/i)
      expect(item.closest('li')).toHaveAttribute('data-status', 'published')
      expect(screen.queryByText(/your story is being written/i)).not.toBeInTheDocument()
    })

    it('matching is case-insensitive', async () => {
      mockGet.mockResolvedValue({
        data: {
          requests: [
            { id: 'req1', status: 'approved', proposed_series_title: 'the cupcake chronicles' },
          ],
        },
      })
      render(<RequestStory profileId="p1" libraryTitles={['THE CUPCAKE CHRONICLES']} />)
      expect(await screen.findByText(/it's on your shelf!/i)).toBeInTheDocument()
    })

    it('does not match an unrelated shelf title', async () => {
      mockGet.mockResolvedValue({
        data: {
          requests: [
            { id: 'req1', status: 'approved', proposed_series_title: 'The Cupcake Chronicles' },
          ],
        },
      })
      render(<RequestStory profileId="p1" libraryTitles={['Sky Pirates']} />)
      expect(await screen.findByText(/your story is being written/i)).toBeInTheDocument()
      expect(screen.queryByText(/it's on your shelf!/i)).not.toBeInTheDocument()
    })
  })

  it('shows a friendly error and keeps the form open when create fails', async () => {
    mockPost.mockRejectedValue(new Error('network exploded'))

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'A brave mouse' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/something went wrong\. try again!/i)
    // No raw error text ever reaches the child.
    expect(screen.queryByText(/network exploded/i)).not.toBeInTheDocument()
    // The form stays open with the idea intact so the child can retry.
    expect(screen.getByRole('textbox', { name: /what should your story be about/i })).toHaveValue(
      'A brave mouse'
    )
  })

  it('shows a friendly busy message when the pending cap (409) is hit', async () => {
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: 'too many pending requests for this profile' } },
    })

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'One more idea' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/wait for a few to be looked at/i)
    expect(screen.queryByText(/too many pending requests/i)).not.toBeInTheDocument()
  })

  it('a rapid second click on Send while saving does not fire a duplicate create', async () => {
    // send() guards with `if (saving) return`, set synchronously before the
    // first await; a rapid second click on the same render must not slip
    // through and fire a second create.
    let resolveCreate: (() => void) | undefined
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = () => resolve({ data: { id: 'req1', status: 'pending' } })
        })
    )

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'A dragon who loves cupcakes' },
    })
    const sendButton = screen.getByRole('button', { name: /^send$/i })
    fireEvent.click(sendButton)
    fireEvent.click(sendButton)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(sendButton).toBeDisabled()

    resolveCreate?.()
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
  })

  it('posts proposed_series_title alongside the idea when a series name is given', async () => {
    mockPost.mockResolvedValue({ data: { id: 'req1', status: 'pending' } })

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'A dragon who loves cupcakes' },
    })
    fireEvent.change(screen.getByLabelText(/part of a series\? give it a name!/i), {
      target: { value: 'The Cupcake Chronicles' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests', {
        profile_id: 'p1',
        request_text: 'A dragon who loves cupcakes',
        proposed_series_title: 'The Cupcake Chronicles',
      })
    )
  })

  it('omits proposed_series_title from the body when the series name is left blank', async () => {
    mockPost.mockResolvedValue({ data: { id: 'req1', status: 'pending' } })

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'A dragon who loves cupcakes' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests', {
        profile_id: 'p1',
        request_text: 'A dragon who loves cupcakes',
      })
    )
  })

  it('anchor mode: opens the form with a continuing chip and no series input', async () => {
    render(<RequestStory profileId="p1" anchor={{ id: 's_1', title: 'The Fox' }} />)

    expect(await screen.findByText(/continuing: the fox/i)).toBeInTheDocument()
    expect(
      screen.getByRole('textbox', { name: /what should your story be about/i })
    ).toBeInTheDocument()
    expect(screen.queryByLabelText(/part of a series\? give it a name!/i)).not.toBeInTheDocument()
  })

  it('anchor mode: posts anchor_storybook_id and no proposed_series_title on send', async () => {
    mockPost.mockResolvedValue({ data: { id: 'req1', status: 'pending' } })

    render(<RequestStory profileId="p1" anchor={{ id: 's_1', title: 'The Fox' }} />)
    await screen.findByText(/continuing: the fox/i)
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'What happens next to the fox' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests', {
        profile_id: 'p1',
        request_text: 'What happens next to the fox',
        anchor_storybook_id: 's_1',
      })
    )
  })

  it('Cancel closes the form and resets the idea and series name', async () => {
    const user = userEvent.setup()
    render(<RequestStory profileId="p1" />)
    await user.click(await screen.findByRole('button', { name: /request a story/i }))
    await user.type(
      screen.getByRole('textbox', { name: /what should your story be about/i }),
      'A dragon who loves cupcakes'
    )
    await user.type(
      screen.getByLabelText(/part of a series\? give it a name!/i),
      'The Cupcake Chronicles'
    )

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(
      screen.queryByRole('textbox', { name: /what should your story be about/i })
    ).not.toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()

    // Reopening shows a fresh, empty form: cancel really reset the state.
    await user.click(screen.getByRole('button', { name: /request a story/i }))
    expect(
      screen.getByRole('textbox', { name: /what should your story be about/i })
    ).toHaveValue('')
    expect(screen.getByLabelText(/part of a series\? give it a name!/i)).toHaveValue('')
  })

  it('Cancel in anchor mode also calls onClearAnchor', async () => {
    const user = userEvent.setup()
    const onClearAnchor = vi.fn()
    render(
      <RequestStory
        profileId="p1"
        anchor={{ id: 's_1', title: 'The Fox' }}
        onClearAnchor={onClearAnchor}
      />
    )
    await screen.findByText(/continuing: the fox/i)

    await user.click(screen.getByRole('button', { name: /^cancel$/i }))

    expect(onClearAnchor).toHaveBeenCalled()
  })

  it('recovers from a stale anchor: clears the anchor and shows a retry message on a 404 send', async () => {
    // A stale anchor (the anchored storybook is gone or no longer eligible by
    // the time the request lands) fails with 404/422; the component must
    // clear the anchor via onClearAnchor so a retry sends a fresh, anchor-less
    // request instead of resending the same doomed anchor.
    const onClearAnchor = vi.fn()
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404 },
    })

    render(
      <RequestStory
        profileId="p1"
        anchor={{ id: 's_1', title: 'The Fox' }}
        onClearAnchor={onClearAnchor}
      />
    )
    await screen.findByText(/continuing: the fox/i)
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'What happens next to the fox' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/can.t be continued right now/i)
    expect(onClearAnchor).toHaveBeenCalled()
  })

  it('opening the form never shows a stale error from an earlier attempt (debt T3: error-clears-on-open)', async () => {
    // Debt U1: a rejection that lands after the dialog has closed can re-arm
    // `error`; the guard is that OPENING always clears it, so whatever raced
    // in while the form was closed is never shown on the next open.
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('network exploded'))

    render(<RequestStory profileId="p1" />)
    await user.click(await screen.findByRole('button', { name: /request a story/i }))
    await user.type(
      screen.getByRole('textbox', { name: /what should your story be about/i }),
      'A brave mouse'
    )
    await user.click(screen.getByRole('button', { name: /^send$/i }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    await user.click(screen.getByRole('button', { name: /request a story/i }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it("an anchor-driven open clears the previous attempt's error (debt T3)", async () => {
    // The child's failed free-idea send leaves an error showing; tapping
    // "Ask for the next book" on a card re-opens the form in anchor mode,
    // which is a fresh start: the old error must not greet the child there.
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('network exploded'))

    const { rerender } = render(<RequestStory profileId="p1" />)
    await user.click(await screen.findByRole('button', { name: /request a story/i }))
    await user.type(
      screen.getByRole('textbox', { name: /what should your story be about/i }),
      'A brave mouse'
    )
    await user.click(screen.getByRole('button', { name: /^send$/i }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    rerender(<RequestStory profileId="p1" anchor={{ id: 's_1', title: 'The Fox' }} />)

    expect(await screen.findByText(/continuing: the fox/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('Cancel is disabled while a send is in flight', async () => {
    // Companion to the error-clears-on-open guard (debt U1): the child cannot
    // close the form mid-send, so the in-flight outcome always lands on an
    // open form.
    let resolveCreate: (() => void) | undefined
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = () => resolve({ data: { id: 'req1', status: 'pending' } })
        })
    )

    render(<RequestStory profileId="p1" />)
    fireEvent.click(await screen.findByRole('button', { name: /request a story/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what should your story be about/i }), {
      target: { value: 'A brave mouse' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()

    resolveCreate?.()
    await waitFor(() =>
      expect(
        screen.queryByRole('textbox', { name: /what should your story be about/i })
      ).not.toBeInTheDocument()
    )
  })

  it('"Not this one" calls onClearAnchor', async () => {
    const onClearAnchor = vi.fn()
    render(
      <RequestStory
        profileId="p1"
        anchor={{ id: 's_1', title: 'The Fox' }}
        onClearAnchor={onClearAnchor}
      />
    )

    fireEvent.click(await screen.findByRole('button', { name: /not this one/i }))
    expect(onClearAnchor).toHaveBeenCalled()
  })
})
