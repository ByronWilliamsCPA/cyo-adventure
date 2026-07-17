import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AuthoringPlanDialog } from './AuthoringPlanDialog'
import type { StoryRequestView } from '../guardian/storyRequestQueueApi'

const REQUEST: StoryRequestView = {
  id: 'req-1',
  profile_id: 'p1',
  status: 'approved',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: 'short',
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const ALLOWLIST_ROWS = [
  { id: 'a1', provider: 'anthropic' as const, model_id: 'claude-sonnet-4-6', enabled: true, display_name: 'Sonnet' },
  { id: 'a2', provider: 'anthropic' as const, model_id: 'claude-haiku-4-5', enabled: false, display_name: 'Haiku (disabled)' },
  { id: 'a3', provider: 'ollama' as const, model_id: 'qwen2.5:14b', enabled: true, display_name: null },
]

describe('AuthoringPlanDialog', () => {
  it('shows the request context read-only', () => {
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('8-11')).toBeInTheDocument()
    expect(screen.getByText('short')).toBeInTheDocument()
    expect(screen.getByText('prose')).toBeInTheDocument()
  })

  it('disables the skill mechanism once fresh generation is chosen', async () => {
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await user.click(screen.getByRole('radio', { name: 'Fresh generation' }))
    expect(screen.getByRole('radio', { name: /cyo-author skill/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: 'Automated provider' })).toBeChecked()
  })

  it('only lists enabled allowlist rows for the chosen provider', async () => {
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await user.click(screen.getByRole('radio', { name: 'Automated provider' }))
    await user.selectOptions(screen.getByLabelText('Provider'), 'anthropic')

    const modelSelect = screen.getByLabelText('Model')
    expect(screen.getByText('Sonnet')).toBeInTheDocument()
    expect(modelSelect).not.toHaveTextContent('Haiku (disabled)')
  })

  it('requires provider and model before Create plan is enabled for an automated job', async () => {
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await user.click(screen.getByRole('radio', { name: 'Automated provider' }))
    await user.type(screen.getByLabelText('Prep model'), 'claude-sonnet-4-6')
    expect(screen.getByRole('button', { name: 'Create plan' })).toBeDisabled()

    await user.selectOptions(screen.getByLabelText('Provider'), 'anthropic')
    await user.selectOptions(screen.getByLabelText('Model'), 'claude-sonnet-4-6')
    expect(screen.getByRole('button', { name: 'Create plan' })).toBeEnabled()
  })

  it('submits the skill mechanism with its default prep model and no provider/model fields', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )
    // Skill mechanism is the default, and its prep model defaults to the
    // first recognized Claude Code session model; Create plan is enabled
    // immediately, with no input required.
    await user.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        method: 'skeleton_fill',
        mechanism: 'skill',
        prep_model: 'sonnet',
      })
    )
  })

  it('constrains the skill mechanism prep model to a recognized Claude Code session model', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )
    await user.selectOptions(screen.getByLabelText('Prep model'), 'opus')
    await user.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ mechanism: 'skill', prep_model: 'opus' })
      )
    )
  })

  it('submits an automated-provider plan with the chosen provider/model', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )
    // prep_model becomes free text only once mechanism is switched away from
    // 'skill' (selectMechanism clears it); switch first, then type.
    await user.click(screen.getByRole('radio', { name: 'Automated provider' }))
    await user.type(screen.getByLabelText('Prep model'), 'claude-sonnet-4-6')
    await user.selectOptions(screen.getByLabelText('Provider'), 'anthropic')
    await user.selectOptions(screen.getByLabelText('Model'), 'claude-sonnet-4-6')
    await user.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        method: 'skeleton_fill',
        mechanism: 'automated_provider',
        prep_model: 'claude-sonnet-4-6',
        provider: 'anthropic',
        model: 'claude-sonnet-4-6',
      })
    )
  })

  it('shows a classified error and stays open when onSubmit rejects', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('boom'))
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <AuthoringPlanDialog
        request={REQUEST}
        allowlistRows={ALLOWLIST_ROWS}
        onSubmit={onSubmit}
        onClose={onClose}
      />
    )
    await user.click(screen.getByRole('button', { name: 'Create plan' }))

    expect(
      await screen.findByText(
        'We could not create the authoring plan. Check the model choice and try again.'
      )
    ).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})
