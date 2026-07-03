import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AVATARS, avatarGlyph } from './avatars'
import { AvatarCircle } from './AvatarCircle'

describe('AvatarCircle', () => {
  it('renders the catalog glyph for a known avatar id', () => {
    const { container } = render(<AvatarCircle avatar="fox" name="Remy" />)
    const circle = container.querySelector('.cyo-avatar')
    expect(circle).not.toBeNull()
    expect(circle).toHaveTextContent('\u{1F98A}')
    expect(circle).not.toHaveClass('cyo-avatar--fallback')
  })

  it('falls back to the name initial in a dashed circle when avatar is null', () => {
    const { container } = render(<AvatarCircle avatar={null} name="zoe" />)
    const circle = container.querySelector('.cyo-avatar--fallback')
    expect(circle).not.toBeNull()
    expect(circle).toHaveTextContent('Z')
  })

  it('falls back to the initial for an unknown avatar id', () => {
    const { container } = render(<AvatarCircle avatar="not-a-preset" name="Ada" />)
    expect(container.querySelector('.cyo-avatar--fallback')).toHaveTextContent('A')
  })

  it('renders ? when the name is blank', () => {
    const { container } = render(<AvatarCircle avatar={null} name="   " />)
    expect(container.querySelector('.cyo-avatar--fallback')).toHaveTextContent('?')
  })

  it('is decorative: aria-hidden on both variants', () => {
    const glyph = render(<AvatarCircle avatar="owl" name="Ori" />)
    const fallback = render(<AvatarCircle avatar={null} name="Ori" />)
    expect(glyph.container.querySelector('[aria-hidden="true"]')).not.toBeNull()
    expect(fallback.container.querySelector('[aria-hidden="true"]')).not.toBeNull()
  })
})

describe('avatars catalog', () => {
  it('has 8 presets with unique ids and non-empty labels', () => {
    const ids = AVATARS.map((a) => a.id)
    expect(ids).toHaveLength(8)
    expect(new Set(ids).size).toBe(8)
    for (const option of AVATARS) {
      expect(option.label.length).toBeGreaterThan(0)
      expect(option.glyph.length).toBeGreaterThan(0)
    }
  })

  it('avatarGlyph resolves known ids and returns null otherwise', () => {
    expect(avatarGlyph('fox')).toBe('\u{1F98A}')
    expect(avatarGlyph('nope')).toBeNull()
    expect(avatarGlyph(null)).toBeNull()
  })
})
