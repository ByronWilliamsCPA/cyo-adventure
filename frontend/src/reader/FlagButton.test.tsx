import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FlagCapReachedError, type SubmitFlagParams } from '../api/readerApi'
import { clearChildSession, setChildSession } from '../auth/childSession'
import type { KidFlagCreatedView } from '../client/types.gen'
import { ToastProvider } from '../notifications/ToastProvider'
import { FlagButton } from './FlagButton'

type SubmitFlagMock = (params: SubmitFlagParams) => Promise<KidFlagCreatedView>

function renderFlagButton(submitFlag: SubmitFlagMock, profileId = 'p1') {
  return render(
    <ToastProvider>
      <FlagButton
        profileId={profileId}
        storybookId="s1"
        version={1}
        getNodeId={() => 'n1'}
        submitFlag={submitFlag}
      />
    </ToastProvider>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  clearChildSession()
})

describe('FlagButton (K15)', () => {
  it('hidden when no valid child session exists for any profile', () => {
    renderFlagButton(vi.fn<SubmitFlagMock>())
    expect(screen.queryByRole('button', { name: /tell a grown-up/i })).not.toBeInTheDocument()
  })

  it('hidden when the stored session is for a different profile', () => {
    setChildSession({ token: 't', expiresAt: '2100-01-01T00:00:00Z', profileId: 'someone-else' })
    renderFlagButton(vi.fn<SubmitFlagMock>(), 'p1')
    expect(screen.queryByRole('button', { name: /tell a grown-up/i })).not.toBeInTheDocument()
  })

  it('hidden when the stored session has expired', () => {
    setChildSession({ token: 't', expiresAt: '2020-01-01T00:00:00Z', profileId: 'p1' })
    renderFlagButton(vi.fn<SubmitFlagMock>(), 'p1')
    expect(screen.queryByRole('button', { name: /tell a grown-up/i })).not.toBeInTheDocument()
  })

  describe('with a valid session for this profile', () => {
    beforeEach(() => {
      setChildSession({ token: 't', expiresAt: '2100-01-01T00:00:00Z', profileId: 'p1' })
    })

    it('opens a dialog with exactly the three structured reasons and no free-text field', () => {
      renderFlagButton(vi.fn<SubmitFlagMock>())
      fireEvent.click(screen.getByRole('button', { name: /tell a grown-up/i }))
      expect(screen.getByRole('dialog', { name: /tell a grown-up/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^i didn't like it$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^it scared me$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^it was confusing$/i })).toBeInTheDocument()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('submits the picked reason with profile/storybook/version/node and shows the confirmation', async () => {
      const submitFlag = vi.fn<SubmitFlagMock>().mockResolvedValue({ id: 'flag1', reason: 'scared_me' })
      renderFlagButton(submitFlag)
      fireEvent.click(screen.getByRole('button', { name: /tell a grown-up/i }))
      fireEvent.click(screen.getByRole('button', { name: /^it scared me$/i }))

      await waitFor(() =>
        expect(submitFlag).toHaveBeenCalledWith({
          profileId: 'p1',
          storybookId: 's1',
          version: 1,
          reason: 'scared_me',
          nodeId: 'n1',
        })
      )
      expect(
        await screen.findByText(/thanks for telling us\. a grown-up will take a look\./i)
      ).toBeInTheDocument()
      // The dialog closes after a successful submit.
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('shows a gentle cap-reached message on a 409 and closes the dialog', async () => {
      const submitFlag = vi.fn<SubmitFlagMock>().mockRejectedValue(new FlagCapReachedError())
      renderFlagButton(submitFlag)
      fireEvent.click(screen.getByRole('button', { name: /tell a grown-up/i }))
      fireEvent.click(screen.getByRole('button', { name: /^it was confusing$/i }))

      expect(await screen.findByText(/you've told us a lot already\./i)).toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      // The gentle cap message must never repeat the raw error.
      expect(screen.queryByText(/FlagCapReachedError/i)).not.toBeInTheDocument()
    })

    it('shows an inline retry message on a generic failure and keeps the dialog open', async () => {
      const submitFlag = vi.fn<SubmitFlagMock>().mockRejectedValue(new Error('network exploded'))
      renderFlagButton(submitFlag)
      fireEvent.click(screen.getByRole('button', { name: /tell a grown-up/i }))
      fireEvent.click(screen.getByRole('button', { name: /^i didn't like it$/i }))

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(/something went wrong/i)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.queryByText(/network exploded/i)).not.toBeInTheDocument()
    })

    it('Cancel closes the dialog without submitting', () => {
      const submitFlag = vi.fn<SubmitFlagMock>()
      renderFlagButton(submitFlag)
      fireEvent.click(screen.getByRole('button', { name: /tell a grown-up/i }))
      fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(submitFlag).not.toHaveBeenCalled()
    })

    it('a rapid second tap on a reason while submitting does not fire a duplicate POST', async () => {
      let resolveSubmit: (() => void) | undefined
      const submitFlag = vi.fn<SubmitFlagMock>().mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveSubmit = () => resolve({ id: 'flag1', reason: 'confusing' })
          })
      )
      renderFlagButton(submitFlag)
      fireEvent.click(screen.getByRole('button', { name: /tell a grown-up/i }))
      const reasonButton = screen.getByRole('button', { name: /^it was confusing$/i })
      fireEvent.click(reasonButton)
      fireEvent.click(reasonButton)

      expect(submitFlag).toHaveBeenCalledTimes(1)
      resolveSubmit?.()
      await waitFor(() => expect(submitFlag).toHaveBeenCalledTimes(1))
    })
  })
})
