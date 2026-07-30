import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DedicationOverlay } from './DedicationOverlay'
import type { ValuesPayload } from '../player/personalization'

function payload(values: Record<string, string>): ValuesPayload {
  return {
    subject_profile_id: 'p_1',
    ring: 1,
    policy_version: 'ring1-no-consent-required',
    resolved_at: '2026-07-29T00:00:00Z',
    values,
    sentinel_pattern: "\\{~([A-Z][A-Z0-9_]*):([^{}<>'~]+)~\\}",
    slot_bindings: {},
  }
}

describe('DedicationOverlay', () => {
  it('renders the full template when both halves are present', () => {
    render(
      <DedicationOverlay
        personalization={payload({ protagonist_first_name: 'Maya', dedication: 'Grandma' })}
      />
    )
    expect(screen.getByTestId('dedication')).toHaveTextContent('For Maya, love Grandma')
  })

  it('renders the name alone when no kinship value is available', () => {
    // The dedication kinship is a closed enum whose vocabulary is still empty
    // (personalization_values.py CLOSED_VOCABULARIES), so this is today's real
    // path and it must still carry the child's name: that is the Stage R
    // "dedication guaranteed" clause.
    render(<DedicationOverlay personalization={payload({ protagonist_first_name: 'Maya' })} />)
    expect(screen.getByTestId('dedication')).toHaveTextContent('For Maya')
    expect(screen.getByTestId('dedication')).not.toHaveTextContent('love')
  })

  it('renders nothing without a name', () => {
    render(<DedicationOverlay personalization={payload({ dedication: 'Grandma' })} />)
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
  })

  it('renders nothing without a payload', () => {
    render(<DedicationOverlay personalization={null} />)
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
  })

  it('renders nothing for a ring-2 payload', () => {
    // Ring 1 only: a dedication is addressed to its own household and means
    // nothing in another one (design plan section 9). The DB CHECK and predicate
    // condition 7 already prevent a ring-2 dedication reaching the payload; this
    // is the client-side belt and braces.
    render(
      <DedicationOverlay
        personalization={{
          ...payload({ protagonist_first_name: 'Maya', dedication: 'Grandma' }),
          ring: 2,
        }}
      />
    )
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
  })
})
