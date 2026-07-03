/**
 * The illustrated avatar catalog.
 *
 * Child avatars are preset-only, permanently: no custom uploads and no child
 * photos, ever (product decision 2026-07-02, closing the wireframe 4.1
 * privacy flag). Profiles store one of these opaque preset ids in
 * ChildProfile.avatar, or null for the initial-letter fallback. The emoji
 * glyphs are placeholders until the generated illustrated set lands
 * (tracked in issue #65); the ids are the stable contract.
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
