import './profiles.css'

import { avatarGlyph } from './avatars'

interface AvatarCircleProps {
  avatar: string | null
  name: string
}

/**
 * Bordered avatar circle (wireframe 4.1): an illustrated glyph when the
 * profile has one, otherwise the name's first letter in a dashed circle.
 */
export function AvatarCircle({ avatar, name }: AvatarCircleProps) {
  const glyph = avatarGlyph(avatar)
  if (glyph) {
    return (
      <span className="avatar-circle" aria-hidden="true">
        {glyph}
      </span>
    )
  }
  // Spread iterates code points, so an emoji-leading name renders whole
  // instead of as a lone UTF-16 surrogate (charAt would split it).
  const initial = [...name.trim()][0]
  return (
    <span className="avatar-circle avatar-circle--fallback" aria-hidden="true">
      {initial?.toUpperCase() ?? '?'}
    </span>
  )
}
