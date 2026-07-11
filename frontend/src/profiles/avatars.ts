/**
 * The illustrated avatar catalog (C4a-2, expanded in issue #65 phase 1
 * "Bucket B").
 *
 * Deliberately NOT child photos: issue #65 resolved the photo privacy
 * question (2026-07-02) as preset-only, permanently. Profiles store one of
 * these opaque preset ids in ChildProfile.avatar, or null for the
 * initial-letter fallback.
 *
 * #ASSUME: data-integrity: the original 8 ids (fox through frog) predate
 * this file and are stored in existing ChildProfile rows, so renaming or
 * removing any of them would silently orphan those profiles onto the
 * initial-letter fallback.
 * #VERIFY: treat ids as append-only; the backend AvatarId Literal in
 * src/cyo_adventure/api/schemas.py must list the same ids in the same order,
 * enforced by tests/unit/test_frontend_contract_parity.py (CI fails on
 * drift). The 14 new ids were added alongside illustrated artwork replacing
 * the emoji glyphs used before this catalog.
 */

import alicornSrc from '../assets/avatars/alicorn.webp'
import baseballGearSrc from '../assets/avatars/baseball-gear.webp'
import baseballKidSrc from '../assets/avatars/baseball-kid.webp'
import butterflySrc from '../assets/avatars/butterfly.webp'
import catSrc from '../assets/avatars/cat.webp'
import cheerGearSrc from '../assets/avatars/cheer-gear.webp'
import cheerKidSrc from '../assets/avatars/cheer-kid.webp'
import dragonSrc from '../assets/avatars/dragon.webp'
import emberDragonSrc from '../assets/avatars/ember-dragon.webp'
import foxSrc from '../assets/avatars/fox.webp'
import frogSrc from '../assets/avatars/frog.webp'
import hawkSrc from '../assets/avatars/hawk.webp'
import owlSrc from '../assets/avatars/owl.webp'
import pantherSrc from '../assets/avatars/panther.webp'
import pegasusSrc from '../assets/avatars/pegasus.webp'
import ravenSrc from '../assets/avatars/raven.webp'
import robotSrc from '../assets/avatars/robot.webp'
import rocketSrc from '../assets/avatars/rocket.webp'
import sharkSrc from '../assets/avatars/shark.webp'
import soccerSrc from '../assets/avatars/soccer.webp'
import unicornSrc from '../assets/avatars/unicorn.webp'
import wolfSrc from '../assets/avatars/wolf.webp'

export interface AvatarOption {
  id: string
  src: string
  label: string
}

export const AVATARS: readonly AvatarOption[] = [
  // Original 8 (ids fixed: stored in existing ChildProfile rows).
  { id: 'fox', src: foxSrc, label: 'Fox' },
  { id: 'owl', src: owlSrc, label: 'Owl' },
  { id: 'dragon', src: dragonSrc, label: 'Dragon' },
  { id: 'cat', src: catSrc, label: 'Cat' },
  { id: 'unicorn', src: unicornSrc, label: 'Unicorn' },
  { id: 'robot', src: robotSrc, label: 'Robot' },
  { id: 'rocket', src: rocketSrc, label: 'Rocket' },
  { id: 'frog', src: frogSrc, label: 'Frog' },
  // New in issue #65 phase 1 (Bucket B).
  { id: 'wolf', src: wolfSrc, label: 'Wolf' },
  { id: 'panther', src: pantherSrc, label: 'Panther' },
  { id: 'ember-dragon', src: emberDragonSrc, label: 'Ember Dragon' },
  { id: 'hawk', src: hawkSrc, label: 'Hawk' },
  { id: 'raven', src: ravenSrc, label: 'Raven' },
  { id: 'pegasus', src: pegasusSrc, label: 'Pegasus' },
  { id: 'alicorn', src: alicornSrc, label: 'Alicorn' },
  { id: 'butterfly', src: butterflySrc, label: 'Butterfly' },
  { id: 'shark', src: sharkSrc, label: 'Shark' },
  { id: 'soccer', src: soccerSrc, label: 'Soccer Ball' },
  { id: 'baseball-gear', src: baseballGearSrc, label: 'Baseball Gear' },
  { id: 'cheer-gear', src: cheerGearSrc, label: 'Cheer Pom-Poms' },
  { id: 'baseball-kid', src: baseballKidSrc, label: 'Baseball Player' },
  { id: 'cheer-kid', src: cheerKidSrc, label: 'Cheerleader' },
]

// The null-in / undefined-out asymmetry is deliberate: callers pass
// ChildProfile.avatar (null means "no avatar chosen"), while an unknown id
// falls through Array.find to undefined. Both render AvatarCircle's
// initial-letter fallback.
export function avatarSrc(id: string | null): string | undefined {
  return AVATARS.find((a) => a.id === id)?.src
}
