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
  return (
    <span className="avatar-circle avatar-circle--fallback" aria-hidden="true">
      {name.trim().charAt(0).toUpperCase() || '?'}
    </span>
  )
}
