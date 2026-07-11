import './profiles.css'

import { avatarSrc } from './avatars'

interface AvatarCircleProps {
  avatar: string | null
  name: string
}

/**
 * Bordered avatar circle (wireframe 4.1): an illustrated avatar image when
 * the profile has one, otherwise the name's first letter in a dashed circle.
 */
export function AvatarCircle({ avatar, name }: AvatarCircleProps) {
  const src = avatarSrc(avatar)
  if (src) {
    return (
      <span className="avatar-circle" aria-hidden="true">
        <img className="avatar-circle__img" src={src} alt="" draggable={false} />
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
