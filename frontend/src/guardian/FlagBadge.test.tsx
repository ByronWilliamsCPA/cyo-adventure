import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { type BadgeTone, FlagBadge, verdictTone } from './FlagBadge'

describe('FlagBadge', () => {
  it('renders the default label for a tone', () => {
    render(<FlagBadge tone="clean" />)
    expect(screen.getByText('Clean')).toBeInTheDocument()
  })

  // Pin every tone's default label text and its tone class so a typo in any
  // TONE_LABEL entry or class name fails a test rather than shipping silently.
  it.each([
    ['block', 'Blocked'],
    ['flag', 'Flagged'],
    ['advisory', 'Advisory'],
    ['clean', 'Clean'],
    ['processing', 'Processing…'],
    ['unscreened', 'Unscreened'],
  ] as const satisfies ReadonlyArray<readonly [BadgeTone, string]>)(
    'renders the default label and tone class for %s',
    (tone, label) => {
      const { container } = render(<FlagBadge tone={tone} />)
      expect(screen.getByText(label)).toBeInTheDocument()
      expect(container.querySelector(`.flag-badge--${tone}`)).not.toBeNull()
    }
  )

  it('renders a custom label and the tone class', () => {
    const { container } = render(<FlagBadge tone="flag" label="2 flagged" />)
    expect(screen.getByText('2 flagged')).toBeInTheDocument()
    expect(container.querySelector('.flag-badge--flag')).not.toBeNull()
  })

  it('maps verdicts to tones', () => {
    expect(verdictTone('block')).toBe('block')
    expect(verdictTone('flag')).toBe('flag')
    expect(verdictTone('advisory')).toBe('advisory')
    expect(verdictTone('pass')).toBe('advisory')
  })
})
