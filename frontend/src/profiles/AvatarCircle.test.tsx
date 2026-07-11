import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AVATARS } from './avatars'
import { AvatarCircle } from './AvatarCircle'

describe('AvatarCircle', () => {
  it('renders an illustrated avatar image for a known preset id', () => {
    const { container } = render(<AvatarCircle avatar="fox" name="Remy" />)

    const wrapper = container.querySelector('span.avatar-circle')
    expect(wrapper).toHaveAttribute('aria-hidden', 'true')

    // alt="" makes this a "presentation" role, not "img", so query by tag
    // rather than screen.getByRole.
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img).toHaveAttribute('alt', '')
    // draggable is reflected as the string "false" (not removed), matching
    // the JSX draggable={false} prop.
    expect(img).toHaveAttribute('draggable', 'false')
    expect(img).toHaveClass('avatar-circle__img')
    expect(img).toHaveAttribute('src', expect.stringContaining('fox'))
  })

  it("falls back to the name's initial letter for an unknown avatar id", () => {
    const { container } = render(<AvatarCircle avatar="not-a-real-preset" name="Zoe" />)
    expect(container.querySelector('img')).toBeNull()

    const fallback = screen.getByText('Z')
    expect(fallback).toHaveAttribute('aria-hidden', 'true')
    expect(fallback).toHaveClass('avatar-circle', 'avatar-circle--fallback')
  })

  it('falls back to the initial letter when avatar is null', () => {
    const { container } = render(<AvatarCircle avatar={null} name="Robin" />)
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('R')).toBeInTheDocument()
  })

  it('falls back to "?" for a blank name', () => {
    render(<AvatarCircle avatar={null} name="   " />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('has 22 unique ids, each with a non-empty label and src', () => {
    expect(AVATARS).toHaveLength(22)

    const ids = AVATARS.map((a) => a.id)
    expect(new Set(ids).size).toBe(ids.length)

    for (const option of AVATARS) {
      expect(option.label.length).toBeGreaterThan(0)
      expect(option.src.length).toBeGreaterThan(0)
    }
  })
})
