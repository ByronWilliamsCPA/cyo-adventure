import './AvatarCircle.css'

import { avatarGlyph } from './avatars'

export interface AvatarCircleProps {
  /** Preset avatar id from the AVATARS catalog, or null for no avatar. */
  avatar: string | null
  /** Display name; its first letter is the fallback when avatar is null/unknown. */
  name: string
}

/**
 * Bordered avatar circle (wireframe 4.1): an illustrated glyph when the
 * profile has a preset avatar, otherwise the name's first letter in a
 * dashed circle. Decorative by design (aria-hidden): the surrounding tile
 * or row carries the accessible name.
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
