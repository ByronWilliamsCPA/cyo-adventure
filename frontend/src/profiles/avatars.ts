/**
 * The illustrated avatar catalog (C4a-2).
 *
 * Deliberately NOT child photos: the photo privacy decision (wireframe 4.1
 * open flag) is unresolved, so profiles store one of these opaque glyph ids
 * in ChildProfile.avatar, or null for the initial-letter fallback.
 */

export interface AvatarOption {
  id: string
  glyph: string
  label: string
}

export const AVATARS: readonly AvatarOption[] = [
  { id: 'fox', glyph: '\u{1F98A}', label: 'Fox' },
  { id: 'owl', glyph: '\u{1F989}', label: 'Owl' },
  { id: 'dragon', glyph: '\u{1F409}', label: 'Dragon' },
  { id: 'cat', glyph: '\u{1F431}', label: 'Cat' },
  { id: 'unicorn', glyph: '\u{1F984}', label: 'Unicorn' },
  { id: 'robot', glyph: '\u{1F916}', label: 'Robot' },
  { id: 'rocket', glyph: '\u{1F680}', label: 'Rocket' },
  { id: 'frog', glyph: '\u{1F438}', label: 'Frog' },
]

export function avatarGlyph(id: string | null): string | null {
  return AVATARS.find((a) => a.id === id)?.glyph ?? null
}
