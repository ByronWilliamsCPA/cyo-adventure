/**
 * The full v1 badge roster (W3.2, gamification recommendation section 2.2),
 * for the badge case screen: `GET /v1/me/progress` returns only EARNED
 * badges, but the case needs the full catalog to render unearned entries as
 * silhouettes with a kid-readable hint.
 *
 * Hand-mirrored from `src/cyo_adventure/progress/badges.py::BADGE_CATALOG`
 * rather than fetched: this is static display metadata (kid-readable names
 * and hints), not a per-profile wire contract, so there is no live endpoint
 * to regenerate a client from. Deliberately excludes badges 9 ("Wish Come
 * True") and 12 ("Forty Days of Stories"): both trail dependencies not yet
 * live (the request-loop fix; W3.3's reading-time accrual reaching 40 days)
 * per the plan's v1 cut line, exactly mirroring `BADGE_CATALOG`'s own
 * current entry count (10).
 *
 * #VERIFY: badgeCatalog.test.ts pins every id/name/description pair against
 * a literal copy of the Python catalog; a drift between the two files fails
 * that test loudly rather than silently showing a stale hint.
 */

export interface BadgeCatalogEntry {
  id: string
  name: string
  description: string
}

export const BADGE_CATALOG: readonly BadgeCatalogEntry[] = [
  { id: 'first_ending', name: 'First Ending', description: 'You found your very first story ending!' },
  {
    id: 'path_not_taken',
    name: 'The Path Not Taken',
    description: 'You went back into a story and found a different ending.',
  },
  {
    id: 'every_path_walked',
    name: 'Every Path Walked',
    description: 'You found every single ending in one book!',
  },
  { id: 'bookworm', name: 'Bookworm', description: 'You started 5 different books.' },
  { id: 'shelf_hero', name: 'Shelf Hero', description: 'You finished 10 different books.' },
  {
    id: 'ending_collector',
    name: 'Ending Collector',
    description: 'You found 25 story endings altogether.',
  },
  {
    id: 'brave_reader',
    name: 'Brave Reader',
    description: 'After a tricky ending, you tried again and found a new one.',
  },
  { id: 'story_wisher', name: 'Story Wisher', description: 'You asked for your very own story idea.' },
  { id: 'star_giver', name: 'Star Giver', description: 'You rated 3 different books.' },
  {
    id: 'series_finisher',
    name: 'Series Finisher',
    description: 'You finished every book in a series!',
  },
] as const
