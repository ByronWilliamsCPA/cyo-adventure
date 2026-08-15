/**
 * The landing page's ten-second sample adventure: a hand-written, four-ending
 * mini story that demonstrates the product's core mechanic (read a passage,
 * pick a choice, reach an ending) right on the marketing page.
 *
 * Deliberately static content, not a real Storybook: the landing page is
 * chunk-neutral and fetches nothing (see LandingPage.tsx), so this never
 * touches the player engine, the API, or the offline cache. It only has to
 * FEEL like the reader, which it does by rendering with the same
 * ChoiceButton primitive the real reader uses.
 *
 * Kept to two hops (start -> scene -> ending) so a curious parent, or a kid
 * peeking over their shoulder, gets the point in seconds; the DemoAdventure
 * test suite asserts the two-hop shape and that every ending stays reachable.
 * All endings are positive-valence on purpose: this is the first taste of the
 * product's tone.
 */

export type DemoNodeId =
  'start' | 'cave' | 'hill' | 'end_glowbug' | 'end_echo' | 'end_letter' | 'end_race'

export interface DemoChoice {
  label: string
  to: DemoNodeId
}

/**
 * Discriminated: a node is either a branch (at least one choice, no ending
 * title) or an ending (a title, no choices). The union makes a dead end, a
 * node with neither, or a confused node with both a type error rather than a
 * runtime state DemoAdventure has to defend against. Nodes are identified by
 * their key in DEMO_STORY; there is deliberately no `id` field to drift out
 * of sync with the key.
 */
export type DemoNode = { text: string } & (
  | { choices: [DemoChoice, ...DemoChoice[]]; endingTitle?: undefined }
  | { choices?: undefined; endingTitle: string }
)

export const DEMO_START: DemoNodeId = 'start'

export const DEMO_STORY: Record<DemoNodeId, DemoNode> = {
  start: {
    text:
      'A brass lantern swings at the mouth of Fernwhistle Cave. Pip the fox ' +
      'sniffs the evening air and looks up at you. “Two trails,” Pip ' +
      'whispers. “You pick.”',
    choices: [
      { label: 'Slip into the glittering cave', to: 'cave' },
      { label: 'Climb the mossy stairs up the hill', to: 'hill' },
    ],
  },
  cave: {
    text:
      'Inside, the walls sparkle like a sky full of green stars. Behind a ' +
      'round stone, something tiny giggles.',
    choices: [
      { label: 'Peek behind the stone', to: 'end_glowbug' },
      { label: 'Giggle back, twice', to: 'end_echo' },
    ],
  },
  hill: {
    text:
      'From the hilltop you spot a paper boat riding the creek below, a tiny ' +
      'letter tucked in its fold.',
    choices: [
      { label: 'Splash in and rescue the letter', to: 'end_letter' },
      { label: 'Race the boat along the bank', to: 'end_race' },
    ],
  },
  end_glowbug: {
    endingTitle: 'A New Friend',
    text:
      'A baby glowbug! She hops onto your shoulder and lights the whole way ' +
      'home. Pip names her Twinkle.',
  },
  end_echo: {
    endingTitle: 'The Laughing Cave',
    text:
      'The giggle giggles back. Then the cave giggles. Soon the whole hill ' +
      'is laughing with you, and Pip laughs loudest of all.',
  },
  end_letter: {
    endingTitle: 'The Moon Picnic',
    text:
      'The letter says: “You found me! The otters are throwing a moon ' +
      'picnic, and you are invited.” Pip is already packing snacks.',
  },
  end_race: {
    endingTitle: 'Won by a Whisker',
    text:
      'You win by a whisker! The boat bumps ashore at your feet and unfolds ' +
      'into a map of tomorrow\u2019s adventure.',
  },
}

/**
 * Number of distinct endings, shown in the "you found N of M" line. Derived
 * from the data rather than hand-counted, so adding a fifth ending can never
 * leave the user-visible copy claiming four.
 */
export const DEMO_ENDING_COUNT = Object.values(DEMO_STORY).filter(
  (node) => node.endingTitle !== undefined
).length

/**
 * Reverse edges: for each node, the branch that links to it. Drives the
 * outro's "Back one choice" action (the demo's miniature of the reader's
 * real go-back feature) without hand-maintaining a second copy of the graph.
 * Derived, so it can never disagree with DEMO_STORY.
 */
export const DEMO_PARENTS: Partial<Record<DemoNodeId, DemoNodeId>> = (() => {
  const parents: Partial<Record<DemoNodeId, DemoNodeId>> = {}
  for (const [id, node] of Object.entries(DEMO_STORY) as [DemoNodeId, DemoNode][]) {
    for (const choice of node.choices ?? []) {
      parents[choice.to] = id
    }
  }
  return parents
})()
