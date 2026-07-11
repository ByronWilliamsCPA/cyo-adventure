/**
 * The illustrated avatar catalog (C4a-2, expanded in issue #65 phase 1
 * "Bucket B").
 *
 * Deliberately NOT child photos: the photo privacy decision (wireframe 4.1
 * open flag) is unresolved, so profiles store one of these opaque preset ids
 * in ChildProfile.avatar, or null for the initial-letter fallback.
 *
 * The original 8 ids (fox through frog) predate this file and are stored in
 * existing ChildProfile rows; they are kept exactly as-is so existing
 * profiles are not orphaned. The 14 new ids were added alongside illustrated
 * artwork replacing the emoji glyphs used before this catalog.
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

export function avatarSrc(id: string | null): string | undefined {
  return AVATARS.find((a) => a.id === id)?.src
}
